"""League payroll and season-scoped retained obligations.

Explicit league contracts override a player's inline price for that player only.
Pending trades do not consume slots; execution revalidates under the league lock.
Completed obligations remain available for historical schedules.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from bson import ObjectId
from fastapi import HTTPException
from utils.cap_treatment import _player_is_in_minors, apply_minors_treatment


def season_year(league):
    return int(league.get("current_season_year") or datetime.now(timezone.utc).year)


def season_end(league):
    value = league.get("season_end_date")
    if not value:
        return None
    try:
        end = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if len(str(value)) == 10:
            end += timedelta(days=1)  # A date includes the entire final day.
        return end.replace(tzinfo=timezone.utc) if end.tzinfo is None else end
    except ValueError:
        return None


def season_ended(league, now=None):
    if league.get("current_season_status") == "complete":
        return True
    end = season_end(league)
    # Renewed leagues retain old wizard dates until their schedule is configured.
    calendar_year = int(str(league.get("season_end_date"))[:4]) if end else None
    return bool(end and calendar_year >= season_year(league)
                and (now or datetime.now(timezone.utc)) >= end)


def applicable_season(league, now=None):
    return season_year(league) + int(season_ended(league, now))


def obligation_year(row, league):
    value = row.get("season_year", row.get("year"))
    if value is not None:
        return int(value)
    created = row.get("created_at")
    if created:
        try:
            return datetime.fromisoformat(str(created).replace("Z", "+00:00")).year
        except ValueError:
            if isinstance(created, datetime):
                return created.year
    return season_year(league)


def active(row, league, now=None):
    if row.get("status") in ("expired", "cancelled"):
        return False
    year = obligation_year(row, league)
    current = season_year(league)
    # Upcoming obligations are committed during the offseason.
    return year == applicable_season(league, now) and year >= current


async def obligations(db, league, team=None, now=None, include_history=False):
    query = {"league_id": str(league["_id"])}
    if team:
        query["retainer_team_id"] = str(team["_id"])
    rows = await db.salary_retentions.find(query).to_list(2000)
    if team:
        known = {str(r.get("player_id")) for r in rows}
        for r in team.get("salary_retentions") or []:
            if str(r.get("player_id")) not in known:
                rows.append({**r, "retainer_team_id": str(team["_id"])})
        # Schedule-only legacy obligations are deduplicated against ledger rows.
        for r in team.get("dead_cap_schedule") or []:
            if r.get("source") == "retention" and str(r.get("player_id")) not in known:
                rows.append({**r, "retainer_team_id": str(team["_id"]),
                             "season_year": r.get("year")})
    dedup = {}
    for r in rows:
        key = (r.get("retainer_team_id"), r.get("player_id"), obligation_year(r, league))
        if key not in dedup and (include_history or active(r, league, now)):
            dedup[key] = r
    return list(dedup.values())


def player_base_price(player, league, config=None):
    from routes.roster import _synthesize_player_salary
    explicit = [(player.get("contract") or {}).get("aav"), (player.get("contract") or {}).get("salary"), player.get("salary"), player.get("cap_hit")]
    if all(v is None for v in explicit) and "default_rookie_aav" in league:
        return float(league["default_rookie_aav"])
    return _synthesize_player_salary(player, config)


def assignment_charge(player, base, assignment, league):
    from utils.cap_treatment import apply_minors_treatment
    section = (assignment or {}).get("section")
    if section == "ir":
        return base * float(league.get("ir_salary_charge_pct", 100)) / 100
    return apply_minors_treatment(player, base_aav=base, is_in_minors=section == "minors",
        treatment=league.get("minors_cap_treatment") or "full", default_rookie_aav=league.get("default_rookie_aav", 950000))


async def payroll(db, team, league=None, roster=None, contract_overrides=None, extra_retained=None, now=None):
    from routes.roster import _synthesize_player_salary
    league = league or await db.leagues.find_one({"_id": ObjectId(team["league_id"])}) or {}
    lid = team["league_id"]
    contracts = await db.contracts.find({"league_id": lid, "team_id": str(team["_id"]),
                                       "status": "active"}).to_list(1000)
    prices = {str(c["player_id"]): float(c.get("aav") or 0) for c in contracts}
    prices.update(contract_overrides or {})
    ids = list(dict.fromkeys(roster if roster is not None else list(team.get("roster") or []) + list(prices)))
    object_ids = [ObjectId(p) for p in ids if ObjectId.is_valid(p)]
    players = await db.players.find({"_id": {"$in": object_ids}}).to_list(1000)
    found = {str(p["_id"]) for p in players}
    # A persisted contract remains payable even if its player row is unavailable.
    players += [{"_id": pid} for pid in ids if pid in prices and pid not in found]
    config = await db.scoring_configs.find_one({"league_id": lid})
    retained = await obligations(db, league, team, now)
    all_retained = [row for row in await obligations(db, league, now=now, include_history=True)
                    if discount_active(row, league, now)]
    all_retained += extra_retained or []
    player_charges = {}
    base_prices = {}
    for p in players:
        pid = str(p["_id"])
        base = prices[pid] if pid in prices else player_base_price(p, league, config)
        base_prices[pid] = base
        discount = sum(float(r.get("amount") or 0) for r in all_retained if r.get("player_id") == pid)
        remaining = max(0, base - discount)
        player_charges[pid] = assignment_charge(p, remaining, (team.get("lineup") or {}).get(pid), league)
    retained_total = sum(float(r.get("amount") or 0) for r in retained)
    retained_total += sum(float(r["amount"]) for r in extra_retained or [] if r["retainer_team_id"] == str(team["_id"]))
    buyout_total = sum(float(row.get("amount") or 0) for row in team.get("dead_cap_schedule") or []
                       if row.get("source") == "buyout" and active(row, league, now))
    return {"used": sum(player_charges.values()) + retained_total + buyout_total,
            "buyout_total": buyout_total,
            "players": player_charges, "base_prices": base_prices,
            "retained": retained, "retained_total": retained_total}


def discount_active(row, league, now=None):
    if row.get("status") == "cancelled" and row.get("forgiveness_policy") == "league_waives":
        return active({**row, "status": "active"}, league, now)
    return active(row, league, now)


def trade_transfers(trade):
    if trade.get("is_multi_party"):
        parties = trade.get("parties") or []
        transfers = []
        for party in parties:
            for asset in party.get("sends") or []:
                if asset.get("asset_type") != "player":
                    continue
                to = asset.get("to_team_id")
                if not to:
                    to = next((p["team_id"] for p in parties if p["team_id"] != party["team_id"] and
                               any(r.get("player_id") == asset.get("player_id") for r in p.get("receives") or [])), None)
                transfers.append((party["team_id"], to, asset))
        return transfers
    return [(trade["proposer_team_id"], trade["target_team_id"], a) for a in trade.get("assets_offered") or [] if a.get("asset_type") == "player"] +            [(trade["target_team_id"], trade["proposer_team_id"], a) for a in trade.get("assets_requested") or [] if a.get("asset_type") == "player"]


async def validate_trade(db, trade):
    league = await db.leagues.find_one({"_id": ObjectId(trade["league_id"])})
    transfers = trade_transfers(trade)
    tids = {t for s, d, a in transfers for t in (s, d)}
    teams, rosters, totals = {}, {}, {}
    for tid in tids:
        if not tid:
            raise HTTPException(400, "Trade recipient missing")
        team = await db.teams.find_one({"_id": ObjectId(tid)})
        if not team or team.get("league_id") != trade["league_id"]:
            raise HTTPException(400, "Trade team does not belong to league")
        teams[tid] = team
        rosters[tid] = list(team.get("roster") or [])
        totals[tid] = await payroll(db, team, league)
    retentions = []
    prices = {t: {} for t in tids}
    seen = set()
    for sender, receiver, asset in transfers:
        pid = asset.get("player_id")
        if pid in seen or pid not in rosters[sender] or sender == receiver:
            raise HTTPException(400, "Trade player is no longer owned by sender")
        seen.add(pid)
        pct = float(asset.get("salary_retained_pct") or 0)
        maximum = league.get("salary_retention_max_pct", 50)
        if not 0 <= pct <= maximum:
            raise HTTPException(400, "Salary retention percentage exceeds league maximum")
        if pct and not league.get("salary_retention_enabled"):
            raise HTTPException(400, "Salary retention is disabled")
        if pct:
            slots = min(3, league.get("salary_retention_slots", 3))
            used = len(totals[sender]["retained"]) + sum(r["retainer_team_id"] == sender for r in retentions)
            if used >= slots:
                raise HTTPException(400, "No salary retention slots available")
            prior = [row for row in await obligations(db, league, include_history=True) if discount_active(row, league)]
            remaining = max(0, totals[sender]["base_prices"][pid] - sum(float(r.get("amount") or 0) for r in prior if r.get("player_id") == pid))
            amount = float((Decimal(str(remaining)) * Decimal(str(pct)) / 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
            retentions.append({"player_id": pid, "retainer_team_id": sender,
                               "receiver_team_id": receiver, "pct": pct, "amount": amount,
                               "season_year": applicable_season(league), "status": "active",
                               "original_aav": totals[sender]["base_prices"][pid]})
        rosters[sender].remove(pid)
        rosters[receiver].append(pid)
        prices[receiver][pid] = totals[sender]["base_prices"][pid]
    for tid, team in teams.items():
        projected = await payroll(db, team, league, roster=rosters[tid], contract_overrides=prices[tid], extra_retained=retentions)
        if league.get("salary_adherence_mode") != "informal" and league.get("salary_cap_enabled") and projected["used"] > float(league.get("salary_cap") or 0):
            raise HTTPException(400, f"Trade exceeds salary cap for {team.get('name')}")
        if league.get("salary_adherence_mode") == "strict":
            draft = await db.drafts.find_one({"league_id": trade["league_id"], "status": "active"})
            if draft:
                from services.draft_salary import load_context, evaluate_roster
                ctx = await load_context(db, draft, {**team, "roster": rosters[tid]}, league)
                ctx["state"] = projected
                validation = evaluate_roster(ctx)
                if not validation["allowed"]:
                    raise HTTPException(409, detail=validation)
    return retentions


async def persist_trade_finances(db, trade, retentions):
    await db.drafts.update_many({"league_id": trade["league_id"], "status": "active"}, {"$set": {"salary_blocked": False}})
    league_id = trade["league_id"]
    for sender, receiver, asset in trade_transfers(trade):
        await db.contracts.update_many({"league_id": league_id, "team_id": sender,
                                       "player_id": asset["player_id"], "status": "active"},
                                      {"$set": {"team_id": receiver}})
    for r in retentions:
        player = await db.players.find_one({"_id": ObjectId(r["player_id"])}) or {}
        doc = {**r, "league_id": league_id, "trade_id": str(trade["_id"]),
               "created_at": datetime.now(timezone.utc)}
        await db.salary_retentions.update_one(
            {"league_id": league_id, "trade_id": str(trade["_id"]),
             "player_id": r["player_id"], "retainer_team_id": r["retainer_team_id"]},
            {"$set": doc}, upsert=True)
        entry = {**doc, "year": r["season_year"], "source": "retention",
                 "player_name": player.get("name", "Retained player")}
        await db.teams.update_one({"_id": ObjectId(r["retainer_team_id"])}, {"$push": {"dead_cap_schedule": entry}})
    tids = {t for s, d, a in trade_transfers(trade) for t in (s, d)}
    for tid in tids:
        team = await db.teams.find_one({"_id": ObjectId(tid)})
        state = await payroll(db, team)
        await db.teams.update_one({"_id": team["_id"]}, {"$set": {"salary_used": state["used"]}})
