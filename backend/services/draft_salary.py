"""Authoritative draft roster assignments and salary completion feasibility."""
from collections import Counter
from decimal import Decimal, ROUND_HALF_UP
from functools import lru_cache
import time
from datetime import datetime, timezone

from bson import ObjectId
from fastapi import HTTPException
from services.salary_policy import payroll, player_base_price, assignment_charge, obligations, discount_active


def money(value):
    amount = Decimal(str(value))
    if not amount.is_finite() or amount < 0:
        raise ValueError("Salary must be a finite nonnegative amount")
    return float(amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def cents(value):
    return int(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) * 100)


def mode(league):
    return league.get("salary_adherence_mode") or "informal"


def positions(player):
    raw = player.get("eligible_positions") or [player.get("position") or player.get("primary_position") or ""]
    if isinstance(raw, str):
        raw = raw.replace("/", ",").split(",")
    return {str(p).strip().upper() for p in raw} | {str(player.get("position") or "").upper()}


def ir_eligible(player, league):
    status = str(player.get("injury_status") or player.get("status") or "").upper()
    allowed = {str(s).upper() for s in league.get("ir_eligibility_modes") or ["IR", "IR-LT"]}
    return status in allowed


def capacities(league):
    active = (league.get("position_breakdown") or {}).get("active") or league.get("position_limits") or {}
    caps = {str(p).upper(): int(n) for p, n in active.items() if int(n or 0) > 0}
    if not caps:
        caps = {"ACT": int(league.get("roster_spots") or 20)}
    caps.update({"BN": int(league.get("bench_spots") or 0),
                 "MIN": int(league.get("minors_spots") or 0), "IR": int(league.get("ir_slots") or 0)})
    return caps


def fits(player, slot, league):
    pos = positions(player)
    if slot == "IR":
        return ir_eligible(player, league)
    if slot == "MIN":
        return bool(player.get("minor_eligible") or player.get("is_prospect") or player.get("player_type") == "prospect")
    if slot in ("ACT", "BN"):
        return True
    if slot == "S":
        return bool(pos - {"G", ""})
    if slot == "W":
        return bool(pos & {"LW", "RW"})
    return slot in pos


def entry(slot):
    section = {"IR": "ir", "MIN": "minors", "BN": "bench", "G": "goalie", "D": "defense"}.get(slot, "forward")
    return {"section": section, "slot": slot}


def assigned_slot(info):
    section = (info or {}).get("section")
    return {"ir": "IR", "minors": "MIN", "bench": "BN"}.get(section, (info or {}).get("slot", "ACT"))


def normalized_lineup(team, players, league):
    caps = capacities(league)
    lineup = {p: v for p, v in (team.get("lineup") or {}).items() if p in team.get("roster", [])}
    if "ACT" in caps:
        lineup = {pid: entry("ACT") if value.get("section") in ("forward", "defense", "goalie") else value for pid, value in lineup.items()}
    counts = Counter(assigned_slot(v) for v in lineup.values())
    for pid in team.get("roster") or []:
        if pid in lineup:
            continue
        player = players.get(pid, {})
        slot = next((s for s in caps if s != "IR" and counts[s] < caps[s] and fits(player, s, league)), None)
        if slot:
            lineup[pid] = entry(slot)
            counts[slot] += 1
    return lineup


def vacancies(team, league):
    caps = capacities(league)
    counts = Counter(assigned_slot(v) for v in (team.get("lineup") or {}).values())
    required = [s for s, n in caps.items() if s not in ("BN", "MIN", "IR")
                for _ in range(max(0, n - counts[s]))]
    optional = [s for s in ("BN", "MIN") for _ in range(max(0, caps[s] - counts[s]))]
    active_capacity = sum(n for s, n in caps.items() if s not in ("BN", "MIN", "IR"))
    target = int(league.get("draft_roster_target") or sum(n for s, n in caps.items() if s != "IR"))
    optional_required = max(0, target - active_capacity - counts["BN"] - counts["MIN"])
    # Optional reserves never replace a required active position.
    return tuple(required + optional[:optional_required])


def feasible_completion(slots, options, lower, upper, limit=30000):
    """Exact distinct-player assignment search; bounded work returns unknown."""
    if not slots:
        return lower <= 0 <= upper
    if upper < 0 or len(options) < len(slots):
        return False
    slots = tuple(sorted(slots, key=lambda s: sum(s in charges for _, charges in options)))
    target = max(0, lower) / max(1, len(slots))
    options = tuple(sorted(options, key=lambda item: abs(min(item[1].values(), default=0) - target)))
    deadline = time.monotonic() + 0.3
    visits = 0

    @lru_cache(maxsize=limit)
    def search(index, mask, lo, hi):
        nonlocal visits
        visits += 1
        if visits > limit or time.monotonic() > deadline:
            raise TimeoutError
        if index == len(slots):
            return lo <= 0 <= hi
        remaining = len(slots) - index
        prices = [min(charges.values()) for i, (_, charges) in enumerate(options) if not mask & (1 << i) and charges]
        if len(prices) < remaining or sum(sorted(prices)[:remaining]) > hi:
            return False
        maximums = [max(charges.values()) for i, (_, charges) in enumerate(options) if not mask & (1 << i) and charges]
        if sum(sorted(maximums, reverse=True)[:remaining]) < lo:
            return False
        for i, (_, charges) in enumerate(options):
            if mask & (1 << i) or slots[index] not in charges:
                continue
            cost = charges[slots[index]]
            if cost <= hi and search(index + 1, mask | (1 << i), lo - cost, hi - cost):
                return True
        return False
    try:
        return search(0, 0, lower, upper)
    except TimeoutError:
        return None


async def load_context(db, draft, team, league=None):
    if not team:
        raise HTTPException(400, "Draft has no valid receiving team")
    league = league or await db.leagues.find_one({"_id": ObjectId(draft["league_id"])})
    if not league:
        raise HTTPException(404, "Draft league not found")
    all_players = await db.players.find({}).to_list(None)
    players = {str(p["_id"]): p for p in all_players}
    team = {**team, "lineup": normalized_lineup(team, players, league)}
    state = await payroll(db, team, league)
    config = await db.scoring_configs.find_one({"league_id": draft["league_id"]})
    owned = set()
    async for other in db.teams.find({"league_id": draft["league_id"]}):
        owned.update(other.get("roster") or [])
    drafted = {p.get("player_id") for p in draft.get("picks") or []}
    historical = set()
    if draft.get("exclude_previously_drafted"):
        async for old in db.drafts.find({"league_id": draft["league_id"]}):
            historical.update(p.get("player_id") for p in old.get("picks") or [])
    criteria = draft.get("player_criteria") or "open"
    if isinstance(criteria, list):
        criteria = criteria[0] if criteria else "open"
    criteria = str(criteria).lower()
    retained = [r for r in await obligations(db, league, include_history=True) if discount_active(r, league)]
    pool = []
    for pid, player in players.items():
        if pid in owned | drafted | historical:
            continue
        prospect = player.get("player_type") == "prospect"
        if criteria in ("entry", "prospects") and not prospect:
            continue
        if criteria not in ("entry", "prospects", "all") and prospect:
            continue
        if draft.get("minors_eligibility_required") and not fits(player, "MIN", league):
            continue
        try:
            base = player_base_price(player, league, config)
            discount = sum(float(r.get("amount") or 0) for r in retained if r.get("player_id") == pid)
            base = max(0, base - discount)
            charges = {s: cents(assignment_charge(player, base, entry(s), league))
                       for s, n in capacities(league).items() if n and fits(player, s, league)}
        except (ValueError, TypeError, KeyError):
            charges = {}
        pool.append((pid, charges))
    return {"league": league, "team": team, "state": state, "players": players, "pool": pool}


def evaluate(ctx, player_id, destination=None):
    league, team = ctx["league"], ctx["team"]
    caps = capacities(league)
    counts = Counter(assigned_slot(v) for v in team.get("lineup", {}).values())
    options = ctx.setdefault("pool_by_id", dict(ctx["pool"]))
    player = ctx["players"].get(player_id)
    if not player or player_id not in options:
        return {"allowed": False, "reason": "player_unavailable", "message": "Player is not eligible or is already owned."}
    choices = [s for s in caps if caps[s] > counts[s] and fits(player, s, league)]
    slot = destination or next((s for s in choices if s != "IR"), None)
    if slot not in choices:
        return {"allowed": False, "reason": "roster_infeasible", "message": "Destination is ineligible or full."}
    if not vacancies(team, league):
        return {"allowed": False, "reason": "roster_complete", "message": "Required draft roster is already complete."}
    cache_key = (slot, mode(league), league.get("salary_cap"), league.get("cap_floor"), tuple(sorted(options[player_id].items())))
    cache = ctx.setdefault("evaluations", {})
    if cache_key in cache:
        return dict(cache[cache_key])
    charge = options[player_id].get(slot)
    result = {"destination": slot, "mode": mode(league), "charge": charge / 100 if charge is not None else None}
    if charge is None:
        reason = "salary_unavailable"
        completion = None
    else:
        projected = cents(ctx["state"]["used"]) + charge
        new_team = {**team, "lineup": {**team.get("lineup", {}), player_id: entry(slot)}}
        remaining = vacancies(new_team, league)
        floor = cents(league.get("cap_floor") or 0) if league.get("cap_floor_enabled") else 0
        cap = cents(league.get("salary_cap") or 0) if league.get("salary_cap_enabled") else 10**15
        candidates = [(pid, costs) for pid, costs in ctx["pool"] if pid != player_id]
        completion = feasible_completion(remaining, candidates, floor - projected, cap - projected)
        reason = "over_cap" if projected > cap else ("salary_unavailable" if completion is None else "salary_completion_infeasible")
        result.update(projected_payroll=projected / 100, remaining_slots=len(remaining))
    good = completion is True
    if not league.get("salary_cap_enabled") and not league.get("cap_floor_enabled"):
        good = True
    result.update(feasible=good, allowed=good or mode(league) == "informal",
                  reason=None if good else reason,
                  message="" if good else "This selection cannot currently complete the required roster within the salary bounds." )
    cache[cache_key] = dict(result)
    return result


async def validate_selection(db, draft, team, player_id, destination=None):
    ctx = await load_context(db, draft, team)
    result = evaluate(ctx, player_id, destination)
    if not result["allowed"]:
        raise HTTPException(409, detail=result)
    return result, ctx


async def warning(db, draft, team, result):
    """Persist deduplicated in-app salary advice and a final commissioner summary."""
    if result.get("feasible", True):
        await db.draft_salary_issues.update_many({"draft_id": str(draft["_id"]), "team_id": str(team["_id"])},
                                               {"$set": {"resolved": True}})
        return
    key = {"draft_id": str(draft["_id"]), "team_id": str(team["_id"]), "reason": result.get("reason"), "projected_payroll": result.get("projected_payroll")}
    fresh = await db.draft_salary_issues.update_one(key, {"$setOnInsert": {"notified": True},
                                                       "$set": {"resolved": False, "detail": result}}, upsert=True)
    if fresh.upserted_id:
        await db.notifications.insert_one({"user_id": str(team.get("owner_id")), "league_id": draft["league_id"],
            "type": "draft_salary", "title": "Draft salary adjustment needed", "message": result.get("message"),
            "read": False, "link": "/draft-room", "created_at": datetime.now(timezone.utc).isoformat()})


def evaluate_roster(ctx):
    league = ctx["league"]
    remaining = vacancies(ctx["team"], league)
    used = cents(ctx["state"]["used"])
    floor = cents(league.get("cap_floor") or 0) if league.get("cap_floor_enabled") else 0
    cap = cents(league.get("salary_cap") or 0) if league.get("salary_cap_enabled") else 10**15
    feasible = feasible_completion(remaining, ctx["pool"], floor - used, cap - used)
    if not league.get("salary_cap_enabled") and not league.get("cap_floor_enabled"):
        feasible = True
    return {"feasible": feasible is True, "allowed": feasible is True or mode(league) == "informal",
            "reason": None if feasible else "salary_completion_infeasible",
            "message": "" if feasible else "Roster needs salary or slot adjustments to complete within enabled bounds.",
            "remaining_slots": len(remaining), "projected_payroll": used / 100}


def validate_lineup(team, players, league):
    counts = Counter()
    for pid, assignment in (team.get("lineup") or {}).items():
        slot = assigned_slot(assignment)
        if pid not in (team.get("roster") or []) or pid not in players or not fits(players[pid], slot, league):
            raise HTTPException(400, "Invalid player or destination in roster assignment")
        counts[slot] += 1
    caps = capacities(league)
    if any(count > caps.get(slot, 0) for slot, count in counts.items()):
        raise HTTPException(400, "Roster destination capacity exceeded")


async def team_summary(db, draft, team, league):
    players = {str(p["_id"]): p async for p in db.players.find({"_id": {"$in": [ObjectId(p) for p in team.get("roster") or [] if ObjectId.is_valid(p)]}})}
    normalized = {**team, "lineup": normalized_lineup(team, players, league)}
    state = await payroll(db, normalized, league)
    counts = Counter(assigned_slot(v) for v in normalized["lineup"].values())
    used = money(state["used"])
    cap = money(league.get("salary_cap") or 0) if league.get("salary_cap_enabled") else None
    floor = money(league.get("cap_floor") or 0) if league.get("cap_floor_enabled") else None
    return {"team_id": str(team["_id"]), "name": team.get("name"), "owner_id": str(team.get("owner_id")),
            "salary_used": used, "salary_cap": cap, "salary_floor": floor,
            "remaining": cap - used if cap is not None else None,
            "floor_shortfall": max(0, floor - used) if floor is not None else None,
            "over_cap": cap is not None and used > cap,
            "percent_used": round(used * 100 / cap, 1) if cap else 0,
            "approaching": bool(cap and used >= cap * .9),
            "positions": {s: {"filled": counts[s], "capacity": n} for s, n in capacities(league).items()},
            "remaining_slots": len(vacancies(normalized, league)), "lineup": normalized["lineup"],
            "players": [{"id": pid, "name": p.get("name"), "position": p.get("position"),
                         "destinations": [s for s, n in capacities(league).items() if n and fits(p, s, league)]}
                        for pid, p in players.items()],
            "picks_count": sum(p.get("team_id") == str(team["_id"]) for p in draft.get("picks") or []),
            "charges": state["players"], "retained_total": state["retained_total"], "buyout_total": state["buyout_total"]}


async def after_pick(db, draft, team, result, completed=False):
    await warning(db, draft, team, result)
    if not completed:
        return
    draft = await db.drafts.find_one({"_id": draft["_id"]})
    league = await db.leagues.find_one({"_id": ObjectId(draft["league_id"])})
    summaries = [await team_summary(db, draft, t, league) async for t in db.teams.find({"league_id": draft["league_id"]})]
    issues = [t for t in summaries if t["over_cap"] or (t["floor_shortfall"] or 0) > 0 or t["remaining_slots"] > 0]
    await db.drafts.update_one({"_id": draft["_id"]}, {"$set": {"salary_completion_summary": summaries,
        "salary_compliant": not issues}})
    if mode(league) != "informal" or not issues:
        return
    recipients = {str(t["owner_id"]): [t] for t in issues}
    recipients[str(league.get("commissioner_id"))] = issues
    for uid, rows in recipients.items():
        message = "; ".join(f"{r['name']}: cap excess ${max(0, -(r['remaining'] or 0)):,}, floor shortfall ${r['floor_shortfall'] or 0:,}, required vacancies {r['remaining_slots']}" for r in rows)
        await db.notifications.update_one({"_id": f"draft-salary-completion:{draft['_id']}:{uid}"}, {"$setOnInsert": {
            "user_id": uid, "league_id": draft["league_id"], "type": "draft_salary", "read": False,
            "title": "Post-draft roster adjustments", "message": message, "link": "/draft-room",
            "created_at": datetime.now(timezone.utc).isoformat()}}, upsert=True)
