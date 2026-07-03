"""Trade engine helpers — extracted from server.py (iter 93).

These were previously module-globals in server.py and depended on the
module-level `db`, `logger`, and `broadcast_to_room` symbols. We rewire
those to injected deps via the `setup(deps)` pattern that the other
extracted routers (`routes/*`) already follow.

Public API (functions imported back into server.py + injected into
`_router_deps`):
    _metric_value_for_player(player, metric)
    _evaluate_conditions(trade)            -> dict
    _evaluate_single_condition(cond, trade)-> (met, actual)
    _format_player_for_trade_msg(pid)      -> str
    _format_pick_for_trade_msg(pick_id, year, round) -> str
    _post_trade_chat_messages(trade, moves)
    _apply_pick_upgrades(trade, *, final_eval=False) -> dict
    _execute_multi_party_trade(trade)      -> dict
    _execute_trade(trade)                  -> dict

The dispatch helper `_execute_trade(trade)` routes 2-team vs multi-party
trades and is the canonical entry point used by `routes/trades.py` and
the matchups/awards re-evaluation hooks.
"""
from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId
from fastapi import HTTPException


_deps: dict = {}


def setup(deps: dict) -> None:
    _deps.update(deps)


def _db():
    return _deps["db"]


def _logger():
    return _deps["logger"]


async def _broadcast(room, event, payload):
    fn = _deps["broadcast_to_room"]
    return await fn(room, event, payload)


async def _create_notification(user_id, notif_type, title, message, league_id=None, link=None):
    """Best-effort notification dispatch. Silently no-ops if the dep is not
    wired (e.g. in isolated unit tests). Routes notifications to the dynasty
    notification bell in the top toolbar AND the Expo push pipeline."""
    fn = _deps.get("create_notification")
    if not fn:
        return None
    try:
        return await fn(user_id, notif_type, title, message, league_id, link)
    except Exception as e:
        _logger().warning("create_notification failed: %s", e)
        return None


async def _notify_conditional_resolution(trade, idx, *, up, cond, met, actual,
                                          new_round=None, new_year=None,
                                          old_round=None, old_year=None,
                                          action="rewrite", to_team_id=None):
    """Notify everyone who should hear that this conditional clause resolved.

    Recipients:
      1. Both trade parties (proposer + target owner) — always informed.
      2. Anyone subscribed via the bell on the Conditional tab card.

    Pushes a notification doc into the `notifications` collection (visible
    in the top toolbar bell). The notification bell already paginates +
    read-syncs on the frontend via `routes/notifications.py`.
    """
    league_id = trade.get("league_id")
    trade_id = str(trade.get("_id"))
    trigger_desc = cond.get("description") or cond.get("metric") or "condition"

    # Build a human-readable summary depending on the outcome.
    if met:
        title = "Conditional trade triggered"
        if action in ("add", "remove") and to_team_id:
            outcome = f"Pick transferred → {to_team_id}"
        elif new_round:
            yr = new_year or old_year or ""
            outcome = f"Pick upgraded to {yr} R{new_round}".strip()
        else:
            outcome = "Pick protection applied"
        msg = f"Trigger met: {trigger_desc}. {outcome}."
    else:
        title = "Conditional trade did not trigger"
        msg = f"Final eval: {trigger_desc} was not met (actual: {actual:g})."

    link = f"/transactions?tab=conditional&trade={trade_id}"

    recipients = set()
    for uid in (trade.get("proposer_id"), trade.get("target_owner_id")):
        if uid:
            recipients.add(uid)
    # Pull explicit subscribers (whole-trade OR per-upgrade-idx)
    try:
        subs = await _db().conditional_subscriptions.find({
            "trade_id": trade_id,
            "$or": [{"pick_upgrade_idx": idx}, {"pick_upgrade_idx": -1}],
        }).to_list(200)
        for s in subs:
            if s.get("user_id"):
                recipients.add(s["user_id"])
    except Exception:
        pass

    notif_type = "conditional_triggered" if met else "conditional_failed"
    for uid in recipients:
        await _create_notification(uid, notif_type, title, msg, league_id=league_id, link=link)

    # Once the clause resolves, remove the now-stale subscriptions so users
    # don't receive duplicate notifications if the trade is re-evaluated.
    try:
        await _db().conditional_subscriptions.delete_many({
            "trade_id": trade_id,
            "$or": [{"pick_upgrade_idx": idx}, {"pick_upgrade_idx": -1}],
        })
    except Exception:
        pass


def _metric_value_for_player(player: dict, metric: str) -> float:
    if metric == "nhl_points":
        return float(player.get("points", 0) or 0)
    if metric == "nhl_goals":
        return float(player.get("goals", 0) or 0)
    if metric == "nhl_assists":
        return float(player.get("assists", 0) or 0)
    if metric == "nhl_wins":
        return float(player.get("wins", 0) or 0)
    if metric == "games_played":
        return float(player.get("games_played", 0) or 0)
    if metric == "fantasy_points":
        return float(player.get("fantasy_points", 0) or 0)
    if metric == "live_fantasy_points":
        live = player.get("live_stats") or {}
        total = 0.0
        for _, ls in live.items():
            total += (ls.get("goals", 0) or 0) * 3 + (ls.get("assists", 0) or 0) * 2
        return total
    return 0.0


async def _evaluate_conditions(trade: dict) -> dict:
    results = []
    all_met = True
    league_id = trade.get("league_id")
    for cond in (trade.get("conditions") or []):
        subject_type = cond.get("subject_type", "player")
        subject = cond.get("subject", "offered")
        side_assets = trade.get(f"assets_{subject}", []) or []
        metric = cond.get("metric")
        operator = (cond.get("operator") or "gte").lower()
        threshold = float(cond.get("threshold", 0) or 0)
        actual = 0.0

        if subject_type == "team":
            # Resolve team: explicit team_id OR the team on the 'subject' side of the trade
            team_id = cond.get("team_id")
            if not team_id:
                team_id = trade["proposer_team_id"] if subject == "offered" else trade["target_team_id"]
            try:
                team = await _db().teams.find_one({"_id": ObjectId(team_id)})
            except Exception:
                team = None
            if team:
                if metric == "team_wins":
                    actual = float(team.get("wins", 0) or 0)
                elif metric == "team_losses":
                    actual = float(team.get("losses", 0) or 0)
                elif metric == "team_points_for":
                    actual = float(team.get("points_for", 0) or 0)
                elif metric == "team_rank":
                    # Lower = better; compute by points_for in league
                    peers = await _db().teams.find({"league_id": league_id}).to_list(100)
                    peers.sort(key=lambda t: -(t.get("points_for", 0) or 0))
                    rank = next((i + 1 for i, t in enumerate(peers) if str(t["_id"]) == team_id), None)
                    actual = float(rank) if rank else 999.0
                elif metric == "made_playoffs":
                    actual = 1.0 if team.get("playoffs_reached_at") else 0.0
                elif metric == "won_division":
                    actual = 1.0 if team.get("division_winner_at") else 0.0
                elif metric == "won_conference":
                    actual = 1.0 if team.get("conference_winner_at") else 0.0
                elif metric == "won_championship":
                    actual = 1.0 if team.get("championship_won_at") else 0.0
                elif metric == "won_consolation":
                    actual = 1.0 if team.get("consolation_won_at") else 0.0
                elif metric == "won_draft_lottery":
                    actual = 1.0 if team.get("draft_lottery_won_at") else 0.0
        elif subject_type == "pick":
            # Pick-level metrics — used for pick protection ("if pick lands top N").
            # Resolves the pick from cond.pick_id (or auto-falls back to a pick
            # found in this side's assets if not specified).
            pick_id = cond.get("pick_id")
            if not pick_id:
                for a in side_assets:
                    if a.get("asset_type") == "pick" and a.get("pick_id"):
                        pick_id = a["pick_id"]; break
            if pick_id:
                try:
                    pick = await _db().draft_picks.find_one({"_id": ObjectId(pick_id)})
                except Exception:
                    pick = None
                if pick:
                    if metric == "pick_slot":
                        # Lower = better. Returns 999 when slot not yet drawn (so
                        # `lte` thresholds correctly stay unmet pre-lottery).
                        actual = float(pick.get("pick_number") or 999)
                    elif metric == "pick_round":
                        actual = float(pick.get("round") or 0)
        else:
            # Player-level. If `player_id` is set explicitly we look the player
            # up directly (works regardless of which side of the trade they're
            # on). Otherwise we scan the assets on `subject` side and take the
            # best metric among them.
            specific_pid = cond.get("player_id")
            candidate_pids = []
            if specific_pid:
                candidate_pids = [specific_pid]
            else:
                for a in side_assets:
                    if a.get("asset_type") != "player":
                        continue
                    if a.get("player_id"):
                        candidate_pids.append(a["player_id"])
            best = 0.0
            for pid in candidate_pids:
                try:
                    player = await _db().players.find_one({"_id": ObjectId(pid)})
                    if player:
                        val = _metric_value_for_player(player, metric)
                        if val > best:
                            best = val
                except Exception:
                    pass
            actual = best

        if operator == "gte":
            met = actual >= threshold
        elif operator == "lte":
            met = actual <= threshold
        elif operator == "eq":
            met = abs(actual - threshold) < 1e-6
        else:
            met = False
        results.append({"condition": cond, "actual_value": actual, "met": met})
        if not met:
            all_met = False
    return {"all_met": all_met, "results": results}


async def _format_player_for_trade_msg(pid: str) -> str:
    try:
        p = await _db().players.find_one({"_id": ObjectId(pid)}, {"name": 1, "position": 1, "team": 1})
    except Exception:
        return pid
    if not p:
        return pid
    bits = [p.get("name", "Unknown")]
    pos = p.get("position")
    team = p.get("team")
    if pos or team:
        bits.append("(" + " · ".join(x for x in [pos, team] if x) + ")")
    return " ".join(bits)


async def _format_pick_for_trade_msg(pick_id: Optional[str], year: Optional[int], rnd: Optional[int]) -> str:
    if pick_id:
        try:
            d = await _db().draft_picks.find_one({"_id": ObjectId(pick_id)}, {"year": 1, "round": 1})
            if d:
                year = d.get("year"); rnd = d.get("round")
        except Exception:
            pass
    if year and rnd:
        return f"{year} R{rnd} pick"
    return "Draft pick"


async def _post_trade_chat_messages(trade: dict, moves) -> None:
    """Best-effort: drop a detailed system message in the league `general`
    channel and in each pairwise DM between the trade participants.
    `moves` is the structured roster-movement dict (singles dict for 2-party,
    list for multi-party). Failures are swallowed so chat hiccups never block
    the underlying trade."""
    try:
        from routes.chat import post_system_message  # local import avoids circular
        league_id = trade["league_id"]
        teams_in_trade: list[tuple[str, str]] = []  # (team_id, team_name)
        per_team_lines: dict[str, list[str]] = {}   # team_id -> ["received: ...", ...]

        if trade.get("is_multi_party") and isinstance(moves, list):
            # Multi-party: moves is a flat list of {asset_type, from, to, ...}
            for p in (trade.get("parties") or []):
                tid = p["team_id"]
                teams_in_trade.append((tid, p.get("team_name", "Team")))
                per_team_lines.setdefault(tid, [])
            for m in moves:
                from_tid, to_tid = m.get("from"), m.get("to")
                if m.get("asset_type") == "player":
                    label = await _format_player_for_trade_msg(m.get("player_id"))
                else:
                    label = await _format_pick_for_trade_msg(m.get("pick_id"), m.get("year"), m.get("round"))
                if to_tid in per_team_lines:
                    per_team_lines[to_tid].append(f"+ {label}  ← from {m.get('from_name','?')}")
                if from_tid in per_team_lines:
                    per_team_lines[from_tid].append(f"− {label}  → to {m.get('to_name','?')}")
        else:
            # Two-party: moves dict with players_out/in + picks_out/in
            ptid = trade.get("proposer_team_id"); pname = trade.get("proposer_team_name", "Team A")
            ttid = trade.get("target_team_id");   tname = trade.get("target_team_name", "Team B")
            teams_in_trade = [(ptid, pname), (ttid, tname)]
            per_team_lines = {ptid: [], ttid: []}
            for it in moves.get("players_out", []):
                lbl = await _format_player_for_trade_msg(it["player_id"])
                per_team_lines[ptid].append(f"− {lbl}  → to {tname}")
                per_team_lines[ttid].append(f"+ {lbl}  ← from {pname}")
            for it in moves.get("players_in", []):
                lbl = await _format_player_for_trade_msg(it["player_id"])
                per_team_lines[ptid].append(f"+ {lbl}  ← from {tname}")
                per_team_lines[ttid].append(f"− {lbl}  → to {pname}")
            for it in moves.get("picks_out", []):
                lbl = await _format_pick_for_trade_msg(it.get("pick_id"), it.get("year"), it.get("round"))
                per_team_lines[ptid].append(f"− {lbl}  → to {tname}")
                per_team_lines[ttid].append(f"+ {lbl}  ← from {pname}")
            for it in moves.get("picks_in", []):
                lbl = await _format_pick_for_trade_msg(it.get("pick_id"), it.get("year"), it.get("round"))
                per_team_lines[ptid].append(f"+ {lbl}  ← from {tname}")
                per_team_lines[ttid].append(f"− {lbl}  → to {pname}")

        names = " ↔ ".join(n for _, n in teams_in_trade)
        general_lines = [f"🤝 Trade executed: {names}"]
        for tid, tname in teams_in_trade:
            received = [ln for ln in per_team_lines.get(tid, []) if ln.startswith("+")]
            if received:
                general_lines.append(f"  • {tname} receives:")
                general_lines.extend(f"      {ln[2:]}" for ln in received)
        general_text = "\n".join(general_lines)
        await post_system_message(_db(), league_id, general_text,
            channel_name="general",
            metadata={"trade_id": str(trade.get("_id")), "kind": "trade_executed"},
        )
        await post_system_message(_db(), league_id, general_text,
            channel_name="trades",
            metadata={"trade_id": str(trade.get("_id")), "kind": "trade_executed"},
        )

        # DMs: one message in every pairwise DM
        for i in range(len(teams_in_trade)):
            for j in range(i + 1, len(teams_in_trade)):
                tid_a, name_a = teams_in_trade[i]
                tid_b, name_b = teams_in_trade[j]
                lines = [f"🤝 Trade complete — {name_a} ↔ {name_b}"]
                a_lines = per_team_lines.get(tid_a, [])
                b_lines = per_team_lines.get(tid_b, [])
                if a_lines:
                    lines.append(f"\n{name_a}:")
                    lines.extend(f"  {ln}" for ln in a_lines)
                if b_lines:
                    lines.append(f"\n{name_b}:")
                    lines.extend(f"  {ln}" for ln in b_lines)
                await post_system_message(_db(), league_id, "\n".join(lines),
                    team_pair=[tid_a, tid_b],
                    metadata={"trade_id": str(trade.get("_id")), "kind": "trade_executed_dm"},
                )
    except Exception as e:
        _logger().warning("trade chat hook failed: %s", e)


async def _evaluate_single_condition(condition: dict, trade: dict) -> tuple[bool, float]:
    """Reuse `_evaluate_conditions` mechanics for a single condition. Returns
    (met, actual_value). The trade context is needed to resolve subject sides."""
    fake = {**trade, "conditions": [condition]}
    res = await _evaluate_conditions(fake)
    if not res.get("results"):
        return (False, 0.0)
    r = res["results"][0]
    return (bool(r.get("met")), float(r.get("actual_value", 0.0)))


async def _apply_pick_upgrades(trade: dict, *, final_eval: bool = False) -> dict:
    """Evaluate every `pick_upgrades` clause attached to the trade. When the
    clause's condition is met and not yet applied, mutate the underlying
    `draft_picks` doc (round + optional year), append a `pick_upgrade` entry
    to its `trade_history`, mark the upgrade entry on the trade as
    `applied_at`, and write a pass audit_log row.

    When `final_eval=True` and the condition is unmet, mark the upgrade as
    `failed_at` and write a fail audit_log row — used at season end to lock
    the outcome in. Otherwise (mid-season), unmet clauses remain pending.

    Returns `{applied: int, failed: int, results: [...]}`."""
    upgrades = trade.get("pick_upgrades") or []
    if not upgrades:
        return {"applied": 0, "failed": 0, "results": []}
    league_id = trade["league_id"]
    trade_id = str(trade.get("_id"))
    applied, failed = 0, 0
    results = []
    now = datetime.now(timezone.utc)

    for idx, up in enumerate(list(upgrades)):
        if up.get("applied_at") or up.get("failed_at"):
            results.append({"index": idx, "skipped": True, "status": "settled"})
            continue
        cond = up.get("condition") or {}
        try:
            met, actual = await _evaluate_single_condition(cond, trade)
        except Exception as e:
            _logger().warning("pick upgrade eval errored trade=%s idx=%s: %s", trade_id, idx, e)
            continue

        if met:
            pick_id = up.get("pick_id")
            action = up.get("action") or "rewrite"
            try:
                pick = await _db().draft_picks.find_one({"_id": ObjectId(pick_id)})
            except Exception:
                pick = None
            if not pick:
                results.append({"index": idx, "met": True, "applied": False, "reason": "pick_not_found"})
                continue

            old_round = pick.get("round")
            old_year = pick.get("year")
            old_owner = pick.get("current_team_id")

            if action == "add" or action == "remove":
                # Transfer ownership: from_team_id → to_team_id
                from_team_id = up.get("from_team_id")
                to_team_id = up.get("to_team_id")
                if not to_team_id:
                    results.append({"index": idx, "met": True, "applied": False,
                                    "reason": "missing_to_team_id"})
                    continue
                history_kind = "pick_added" if action == "add" else "pick_removed"
                history_emoji = "📈" if action == "add" else "📉"
                history_label = "Pick added" if action == "add" else "Pick removed"
                await _db().draft_picks.update_one(
                    {"_id": ObjectId(pick_id)},
                    {
                        "$set": {"current_team_id": to_team_id},
                        "$push": {"trade_history": {
                            "trade_id": trade_id,
                            "kind": history_kind,
                            "from_team_id": from_team_id or old_owner,
                            "to_team_id": to_team_id,
                            "round": old_round,
                            "year": old_year,
                            "trigger": cond.get("description") or cond.get("metric"),
                            "actual_value": actual,
                            "applied_at": now,
                        }},
                    },
                )
                # Resolve team names for chat/audit
                from_team_name = None
                to_team_name = None
                try:
                    if from_team_id or old_owner:
                        ft = await _db().teams.find_one({"_id": ObjectId(from_team_id or old_owner)})
                        from_team_name = (ft or {}).get("name")
                    tt = await _db().teams.find_one({"_id": ObjectId(to_team_id)})
                    to_team_name = (tt or {}).get("name")
                except Exception:
                    pass
                await _db().trades.update_one(
                    {"_id": trade["_id"]},
                    {"$set": {f"pick_upgrades.{idx}.applied_at": now,
                              f"pick_upgrades.{idx}.actual_value": actual}},
                )
                await _db().audit_log.insert_one({
                    "league_id": league_id,
                    "action": f"pick_upgrade_{action}_applied",
                    "result": "pass",
                    "trade_id": trade_id,
                    "pick_id": pick_id,
                    "from_team_id": from_team_id or old_owner,
                    "to_team_id": to_team_id,
                    "round": old_round, "year": old_year,
                    "trigger": cond.get("description") or cond.get("metric"),
                    "actual_value": actual,
                    "created_at": now,
                })
                try:
                    from routes.chat import post_system_message
                    await post_system_message(_db(), league_id,
                        f"{history_emoji} {history_label}: {old_year} R{old_round} "
                        f"{'→' if action == 'add' else 'reverts to'} {to_team_name or to_team_id} "
                        f"(condition: {cond.get('description') or cond.get('metric')})",
                        channel_name="trades",
                        metadata={"trade_id": trade_id, "kind": history_kind},
                    )
                except Exception:
                    pass
                applied += 1
                results.append({"index": idx, "met": True, "applied": True,
                                "action": action,
                                "from_team_id": from_team_id or old_owner,
                                "to_team_id": to_team_id})
                await _notify_conditional_resolution(
                    trade, idx, up=up, cond=cond, met=True, actual=actual,
                    action=action, to_team_id=to_team_id,
                    old_round=old_round, old_year=old_year,
                )
                continue

            # action == "rewrite" (default, back-compat)
            new_round = int(up.get("new_round", 0))
            new_year = up.get("new_year")
            update_set = {"round": new_round}
            if new_year:
                update_set["year"] = int(new_year)
            await _db().draft_picks.update_one(
                {"_id": ObjectId(pick_id)},
                {
                    "$set": update_set,
                    "$push": {"trade_history": {
                        "trade_id": trade_id,
                        "kind": "pick_upgrade",
                        "from_round": old_round, "to_round": new_round,
                        "from_year": old_year, "to_year": new_year or old_year,
                        "trigger": cond.get("description") or cond.get("metric"),
                        "actual_value": actual,
                        "applied_at": now,
                    }},
                },
            )
            await _db().trades.update_one(
                {"_id": trade["_id"]},
                {"$set": {f"pick_upgrades.{idx}.applied_at": now,
                          f"pick_upgrades.{idx}.actual_value": actual,
                          f"pick_upgrades.{idx}.from_round": old_round,
                          f"pick_upgrades.{idx}.from_year": old_year}},
            )
            await _db().audit_log.insert_one({
                "league_id": league_id,
                "action": "pick_upgrade_applied",
                "result": "pass",
                "trade_id": trade_id,
                "pick_id": pick_id,
                "from_round": old_round, "to_round": new_round,
                "from_year": old_year, "to_year": new_year or old_year,
                "trigger": cond.get("description") or cond.get("metric"),
                "actual_value": actual,
                "created_at": now,
            })
            try:
                from routes.chat import post_system_message
                await post_system_message(_db(), league_id,
                    f"📈 Pick upgrade triggered: {old_year} R{old_round} → {new_year or old_year} R{new_round} "
                    f"(condition: {cond.get('description') or cond.get('metric')})",
                    channel_name="trades",
                    metadata={"trade_id": trade_id, "kind": "pick_upgrade"},
                )
            except Exception:
                pass
            applied += 1
            results.append({"index": idx, "met": True, "applied": True,
                            "action": "rewrite",
                            "from_round": old_round, "to_round": new_round})
            await _notify_conditional_resolution(
                trade, idx, up=up, cond=cond, met=True, actual=actual,
                new_round=new_round, new_year=new_year or old_year,
                old_round=old_round, old_year=old_year, action="rewrite",
            )
        else:
            if final_eval:
                await _db().trades.update_one(
                    {"_id": trade["_id"]},
                    {"$set": {f"pick_upgrades.{idx}.failed_at": now,
                              f"pick_upgrades.{idx}.actual_value": actual}},
                )
                await _db().audit_log.insert_one({
                    "league_id": league_id,
                    "action": "pick_upgrade_failed",
                    "result": "fail",
                    "trade_id": trade_id,
                    "pick_id": up.get("pick_id"),
                    "trigger": cond.get("description") or cond.get("metric"),
                    "actual_value": actual,
                    "created_at": now,
                })
                failed += 1
                results.append({"index": idx, "met": False, "final": True})
                await _notify_conditional_resolution(
                    trade, idx, up=up, cond=cond, met=False, actual=actual,
                )
            else:
                results.append({"index": idx, "met": False, "pending": True})
    return {"applied": applied, "failed": failed, "results": results}


async def _execute_multi_party_trade(trade: dict) -> dict:
    """Execute a trade with 3+ parties.
    Each party's `sends` are removed from their roster; the engine then routes
    each sent asset to the receiving party. Routing rules:
      1. If asset has explicit `to_team_id`, send there.
      2. Otherwise, find the unique party whose `receives` lists this asset
         (matched by player_id or pick_id) and send there.
      3. If neither resolves, raise.
    Draft picks update `current_team_id` and append to `trade_history`.
    """
    league_id = trade["league_id"]
    parties = trade.get("parties") or []
    teams_by_id: dict[str, dict] = {}
    rosters: dict[str, list] = {}
    for p in parties:
        team = await _db().teams.find_one({"_id": ObjectId(p["team_id"])})
        if not team:
            raise HTTPException(status_code=404, detail=f"Trade team {p['team_id']} not found")
        teams_by_id[p["team_id"]] = team
        rosters[p["team_id"]] = list(team.get("roster", []) or [])

    moves: list[dict] = []
    retentions: list[dict] = []

    def _find_recipient(asset: dict, sender_team_id: str) -> Optional[str]:
        if asset.get("to_team_id") and asset["to_team_id"] != sender_team_id:
            return asset["to_team_id"]
        match_pid = asset.get("player_id")
        match_pick = asset.get("pick_id")
        for q in parties:
            if q["team_id"] == sender_team_id:
                continue
            for r in q.get("receives", []):
                if match_pid and r.get("player_id") == match_pid:
                    return q["team_id"]
                if match_pick and r.get("pick_id") == match_pick:
                    return q["team_id"]
                # Loose match by year+round when pick_id absent
                if (asset.get("asset_type") == "pick" and not match_pick
                        and r.get("asset_type") == "pick"
                        and r.get("pick_year") == asset.get("pick_year")
                        and str(r.get("pick_round")) == str(asset.get("pick_round"))):
                    return q["team_id"]
        return None

    for p in parties:
        sender_id = p["team_id"]
        sender = teams_by_id[sender_id]
        for a in p.get("sends", []):
            recipient_id = _find_recipient(a, sender_id)
            if not recipient_id:
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot route asset from {sender.get('name')}: no matching recipient party",
                )
            recipient = teams_by_id[recipient_id]

            if a.get("asset_type") == "player" and a.get("player_id"):
                pid = a["player_id"]
                if pid in rosters[sender_id]:
                    rosters[sender_id].remove(pid)
                if pid not in rosters[recipient_id]:
                    rosters[recipient_id].append(pid)
                moves.append({
                    "asset_type": "player", "player_id": pid,
                    "from": sender_id, "from_name": sender.get("name"),
                    "to": recipient_id, "to_name": recipient.get("name"),
                })
                if a.get("salary_retained_pct", 0) > 0:
                    retentions.append({
                        "player_id": pid, "retainer_team_id": sender_id,
                        "pct": a["salary_retained_pct"],
                    })
            elif a.get("asset_type") == "pick":
                query = {"league_id": league_id, "current_team_id": sender_id}
                if a.get("pick_id"):
                    query["_id"] = ObjectId(a["pick_id"])
                else:
                    if a.get("pick_year"):
                        query["year"] = int(a["pick_year"])
                    if a.get("pick_round"):
                        try:
                            query["round"] = int(str(a["pick_round"]).replace("R", "").strip())
                        except Exception:
                            pass
                pick_doc = await _db().draft_picks.find_one(query)
                if pick_doc:
                    await _db().draft_picks.update_one(
                        {"_id": pick_doc["_id"]},
                        {
                            "$set": {
                                "current_team_id": recipient_id,
                                "current_team_name": recipient.get("name"),
                            },
                            "$push": {"trade_history": {
                                "trade_id": str(trade["_id"]),
                                "from_team_id": sender_id,
                                "from_team_name": sender.get("name"),
                                "to_team_id": recipient_id,
                                "to_team_name": recipient.get("name"),
                                "traded_at": datetime.now(timezone.utc),
                            }},
                        },
                    )
                    moves.append({
                        "asset_type": "pick", "pick_id": str(pick_doc["_id"]),
                        "year": pick_doc["year"], "round": pick_doc["round"],
                        "from": sender_id, "from_name": sender.get("name"),
                        "to": recipient_id, "to_name": recipient.get("name"),
                    })

    # Persist all roster updates
    # Iter 218 — Auto-snapshot pre-trade state for every participating team
    from services.auto_snapshot import auto_snapshot
    await auto_snapshot(_db(), list(rosters.keys()),
                        trigger="multi_party_trade_execute",
                        metadata={"trade_id": str(trade["_id"]),
                                  "party_count": len(rosters)})
    for tid, roster in rosters.items():
        await _db().teams.update_one({"_id": ObjectId(tid)}, {"$set": {"roster": roster}})

    for r in retentions:
        retention_doc = {
            **r,
            "league_id": league_id,
            "trade_id": str(trade["_id"]),
            "created_at": datetime.now(timezone.utc),
        }
        await _db().salary_retentions.update_one(
            {"league_id": league_id, "player_id": r["player_id"], "retainer_team_id": r["retainer_team_id"]},
            {"$set": retention_doc},
            upsert=True,
        )
        # Iter 113 — Mirror retention into team.dead_cap_schedule so the
        # schedule endpoint is the single source of truth for both
        # buyouts AND retention (also picked up by the on-the-fly merge
        # in routes/teams.get_dead_cap_schedule for legacy rows).
        try:
            player = await _db().players.find_one({"_id": ObjectId(r["player_id"])})
        except Exception:
            player = None
        if player:
            yrs = int((player.get("contract") or {}).get("yearsRemaining") or 1)
            cur_year = datetime.now(timezone.utc).year
            schedule_entries = [{
                "year": cur_year + i,
                "amount": int(round(float(r.get("amount") or 0))),
                "source": "retention",
                "player_id": r["player_id"],
                "player_name": player.get("name") or "Retained player",
                "trade_id": str(trade["_id"]),
                "created_at": datetime.now(timezone.utc),
            } for i in range(max(1, yrs))]
            await _db().teams.update_one(
                {"_id": ObjectId(r["retainer_team_id"])},
                {"$push": {"dead_cap_schedule": {"$each": schedule_entries}}},
            )

    await _db().trades.update_one(
        {"_id": trade["_id"]},
        {"$set": {
            "status": "executed",
            "processed_at": datetime.now(timezone.utc).isoformat(),
            "execution_moves": moves,
        }}
    )

    description = "Multi-team trade executed: " + " ↔ ".join(p["team_name"] for p in parties)
    # ── Clear trade-block entries for any player that just changed hands ──
    # Multi-party path. `moves` is a list of asset movements; each player move
    # carries `player_id` directly.
    multi_traded_pids = list({
        m["player_id"]
        for m in moves
        if m.get("asset_type") == "player" and m.get("player_id")
    })
    if multi_traded_pids:
        try:
            await _db().trade_block.delete_many({
                "league_id": league_id,
                "player_id": {"$in": multi_traded_pids},
            })
            await _broadcast(
                f"league_{league_id}",
                "trade_block_changed",
                {"action": "cleared_after_trade", "player_ids": multi_traded_pids},
            )
        except Exception:
            pass
    try:
        await _db().activity_feed.insert_one({
            "league_id": league_id,
            "event_type": "trade_executed",
            "description": description,
            "message": description,
            "created_at": datetime.now(timezone.utc),
        })
    except Exception:
        pass
    await _post_trade_chat_messages(trade, moves)
    # Iter 231k — Real-time multi-party toast.
    sio = _deps.get("sio")
    if sio is not None:
        try:
            names = " ↔ ".join(p["team_name"] for p in parties)
            await sio.emit("trade_processed", {
                "league_id": league_id,
                "trade_id": str(trade.get("_id")),
                "proposer_team_name": parties[0]["team_name"] if parties else None,
                "target_team_name": parties[1]["team_name"] if len(parties) > 1 else None,
                "is_multi_party": True,
                "all_team_names": names,
                "asset_count": sum(len(p.get("sends") or []) for p in parties),
            })
        except Exception as e:
            _logger().debug(f"trade_processed multi-party sio.emit skipped: {e}")
    # Initial pick-upgrade eval. Mid-season / not-yet-finalized triggers stay
    # pending and re-evaluate on every award toggle + weekly simulation.
    refreshed = await _db().trades.find_one({"_id": trade["_id"]})
    if refreshed:
        await _apply_pick_upgrades(refreshed, final_eval=False)

    # Iter 232N.24 — XP toast for every party in a multi-team trade.
    try:
        from utils.xp import emit_xp_gain
        broadcast_fn = _deps.get("broadcast_to_room")
        meta = {
            "trade_id": str(trade.get("_id")),
            "parties": [p.get("team_name") for p in parties],
            "is_multi_party": True,
        }
        for p in parties:
            if p.get("owner_id"):
                await emit_xp_gain(
                    _db(), p["owner_id"],
                    source="trade_accepted",
                    broadcast_fn=broadcast_fn,
                    meta=meta,
                )
    except Exception as e:
        _logger().debug(f"xp_awarded emit skipped (multi-party): {e}")

    return {"executed": True, "moves": moves, "parties": [p["team_name"] for p in parties]}


async def _execute_trade(trade: dict) -> dict:
    if trade.get("status") == "executed":
        return {"already_executed": True}

    # ── Iter 232M — Defer during a live matchup lock ─────────────
    # If the league's lineup lock is currently active, do NOT swap
    # rosters mid-scoring-period. Stamp defer metadata on the trade so
    # the UI can surface "Held — pending matchup unlock" and let the
    # auto-processor retry on the next tick after the lock lifts.
    # Multi-party and manual/commissioner-forced calls bypass this via
    # trade.get("force_execute") = True.
    if not trade.get("force_execute"):
        league_doc = await _db().leagues.find_one({"_id": ObjectId(trade["league_id"])})
        if league_doc:
            try:
                from utils.lineup_lock import evaluate_lineup_lock
                lock = evaluate_lineup_lock(league_doc)
            except Exception:
                lock = {"locked": False}
            if lock.get("locked"):
                now_iso = datetime.now(timezone.utc).isoformat()
                await _db().trades.update_one(
                    {"_id": trade["_id"]},
                    {"$set": {
                        "defer_reason": "matchup_locked",
                        "defer_next_unlock": lock.get("next_unlock_iso"),
                        "deferred_at": now_iso,
                    }},
                )
                return {
                    "executed": False,
                    "deferred": True,
                    "reason": "matchup_locked",
                    "next_unlock_iso": lock.get("next_unlock_iso"),
                    "message": lock.get("reason"),
                }
            elif trade.get("defer_reason"):
                # Lock has lifted since the last defer — clear the flag
                # so the UI stops showing the "Held" pill.
                await _db().trades.update_one(
                    {"_id": trade["_id"]},
                    {"$unset": {
                        "defer_reason": "",
                        "defer_next_unlock": "",
                        "deferred_at": "",
                    }},
                )

    # ── Multi-party (3+ teams) execution path ────────────────
    parties = trade.get("parties") or []
    if parties and trade.get("is_multi_party"):
        return await _execute_multi_party_trade(trade)

    league_id = trade["league_id"]
    proposer_tid = trade["proposer_team_id"]
    target_tid = trade["target_team_id"]
    proposer = await _db().teams.find_one({"_id": ObjectId(proposer_tid)})
    target = await _db().teams.find_one({"_id": ObjectId(target_tid)})
    if not proposer or not target:
        raise HTTPException(status_code=404, detail="Trade team(s) not found")
    proposer_roster = list(proposer.get("roster", []) or [])
    target_roster = list(target.get("roster", []) or [])

    # Iter 218 — Auto-snapshot pre-trade state for both teams
    from services.auto_snapshot import auto_snapshot
    await auto_snapshot(_db(), [proposer["_id"], target["_id"]],
                        trigger="trade_execute",
                        metadata={"trade_id": str(trade["_id"])})

    # ── Position-limit pre-flight (iter 83) ────────────────────────
    # Before committing the swap, simulate the post-trade rosters and ensure
    # neither side ends up over `position_limits` when `enforce_position_maxes`
    # is enabled. Loads each player once so the check is O(N+M).
    league_doc = await _db().leagues.find_one({"_id": ObjectId(league_id)}) or {}
    if league_doc.get("enforce_position_maxes") and (league_doc.get("position_limits") or {}):
        from utils.roster_rules import check_position_limits, _position_of
        offered_ids = [a["player_id"] for a in trade.get("assets_offered", [])
                       if a.get("asset_type") == "player" and a.get("player_id")]
        requested_ids = [a["player_id"] for a in trade.get("assets_requested", [])
                         if a.get("asset_type") == "player" and a.get("player_id")]
        # Final rosters after the trade
        final_proposer_ids = [p for p in proposer_roster if p not in offered_ids] + requested_ids
        final_target_ids = [p for p in target_roster if p not in requested_ids] + offered_ids
        all_pid_strs = set(final_proposer_ids) | set(final_target_ids)
        all_oids = []
        for pid in all_pid_strs:
            try:
                all_oids.append(ObjectId(pid))
            except Exception:
                pass
        player_map = {}
        if all_oids:
            async for p in _db().players.find(
                {"_id": {"$in": all_oids}},
                {"name": 1, "position": 1, "primary_position": 1,
                 "eligible_positions": 1, "player_type": 1},
            ):
                player_map[str(p["_id"])] = p

        def _validate(side_name: str, post_ids: list, incoming_ids: list):
            for incoming_pid in incoming_ids:
                incoming = player_map.get(incoming_pid)
                if not incoming:
                    continue
                existing = [
                    player_map[pid] for pid in post_ids
                    if pid != incoming_pid and pid in player_map
                ]
                err = check_position_limits(league_doc, existing, incoming)
                if err:
                    raise HTTPException(
                        status_code=400,
                        detail=f"{side_name} would exceed position limits after this trade: {err}",
                    )

        _validate(proposer.get("name", "Proposer"), final_proposer_ids, requested_ids)
        _validate(target.get("name", "Target"), final_target_ids, offered_ids)

    moves = {"players_out": [], "picks_out": [], "players_in": [], "picks_in": [], "retained": []}

    for a in trade.get("assets_offered", []):
        if a.get("asset_type") == "player" and a.get("player_id"):
            pid = a["player_id"]
            if pid in proposer_roster:
                proposer_roster.remove(pid)
            if pid not in target_roster:
                target_roster.append(pid)
            moves["players_out"].append({"player_id": pid, "from": proposer_tid, "to": target_tid})
            if a.get("salary_retained_pct", 0) > 0:
                moves["retained"].append({"player_id": pid, "retainer_team_id": proposer_tid, "pct": a["salary_retained_pct"]})
        elif a.get("asset_type") == "pick":
            query = {"league_id": league_id, "current_team_id": proposer_tid}
            if a.get("pick_id"):
                query["_id"] = ObjectId(a["pick_id"])
            else:
                if a.get("pick_year"): query["year"] = int(a["pick_year"])
                if a.get("pick_round"):
                    try: query["round"] = int(str(a["pick_round"]).replace("R", "").strip())
                    except Exception: pass
            p = await _db().draft_picks.find_one(query)
            if p:
                await _db().draft_picks.update_one(
                    {"_id": p["_id"]},
                    {
                        "$set": {"current_team_id": target_tid, "current_team_name": target.get("name")},
                        "$push": {"trade_history": {
                            "trade_id": str(trade["_id"]),
                            "from_team_id": proposer_tid,
                            "from_team_name": proposer.get("name"),
                            "to_team_id": target_tid,
                            "to_team_name": target.get("name"),
                            "traded_at": datetime.now(timezone.utc),
                        }},
                    }
                )
                moves["picks_out"].append({"pick_id": str(p["_id"]), "year": p["year"], "round": p["round"],
                                            "from": proposer_tid, "to": target_tid})

    for a in trade.get("assets_requested", []):
        if a.get("asset_type") == "player" and a.get("player_id"):
            pid = a["player_id"]
            if pid in target_roster:
                target_roster.remove(pid)
            if pid not in proposer_roster:
                proposer_roster.append(pid)
            moves["players_in"].append({"player_id": pid, "from": target_tid, "to": proposer_tid})
            if a.get("salary_retained_pct", 0) > 0:
                moves["retained"].append({"player_id": pid, "retainer_team_id": target_tid, "pct": a["salary_retained_pct"]})
        elif a.get("asset_type") == "pick":
            query = {"league_id": league_id, "current_team_id": target_tid}
            if a.get("pick_id"):
                query["_id"] = ObjectId(a["pick_id"])
            else:
                if a.get("pick_year"): query["year"] = int(a["pick_year"])
                if a.get("pick_round"):
                    try: query["round"] = int(str(a["pick_round"]).replace("R", "").strip())
                    except Exception: pass
            p = await _db().draft_picks.find_one(query)
            if p:
                await _db().draft_picks.update_one(
                    {"_id": p["_id"]},
                    {
                        "$set": {"current_team_id": proposer_tid, "current_team_name": proposer.get("name")},
                        "$push": {"trade_history": {
                            "trade_id": str(trade["_id"]),
                            "from_team_id": target_tid,
                            "from_team_name": target.get("name"),
                            "to_team_id": proposer_tid,
                            "to_team_name": proposer.get("name"),
                            "traded_at": datetime.now(timezone.utc),
                        }},
                    }
                )
                moves["picks_in"].append({"pick_id": str(p["_id"]), "year": p["year"], "round": p["round"],
                                           "from": target_tid, "to": proposer_tid})

    await _db().teams.update_one({"_id": proposer["_id"]}, {"$set": {"roster": proposer_roster}})
    await _db().teams.update_one({"_id": target["_id"]}, {"$set": {"roster": target_roster}})

    for r in moves["retained"]:
        await _db().salary_retentions.update_one(
            {"league_id": league_id, "player_id": r["player_id"], "retainer_team_id": r["retainer_team_id"]},
            {"$set": {**r, "league_id": league_id, "trade_id": str(trade["_id"]),
                      "created_at": datetime.now(timezone.utc)}},
            upsert=True,
        )

    await _db().trades.update_one(
        {"_id": trade["_id"]},
        {"$set": {
            "status": "executed",
            "processed_at": datetime.now(timezone.utc).isoformat(),
            "execution_moves": moves,
        }}
    )

    # ── Clear trade-block entries for any player that just changed hands ──
    # Two-team path. If a traded player was on the original owner's block, we
    # remove the listing on execution: they're no longer on the previous
    # roster and the new owner hasn't expressed interest in shopping them.
    traded_player_ids = list({
        m["player_id"]
        for m in (moves.get("players_out") or []) + (moves.get("players_in") or [])
        if m.get("player_id")
    })
    if traded_player_ids:
        try:
            await _db().trade_block.delete_many({
                "league_id": league_id,
                "player_id": {"$in": traded_player_ids},
            })
            await _broadcast(
                f"league_{league_id}",
                "trade_block_changed",
                {"action": "cleared_after_trade", "player_ids": traded_player_ids},
            )
        except Exception:
            pass

    try:
        await _db().activity_feed.insert_one({
            "league_id": league_id,
            "event_type": "trade_executed",
            "description": f"Trade executed: {trade['proposer_team_name']} ↔ {trade['target_team_name']}",
            "message": f"Trade executed: {trade['proposer_team_name']} ↔ {trade['target_team_name']}",
            "created_at": datetime.now(timezone.utc),
        })
    except Exception:
        pass

    # Iter 230 — Fan out "any trade processed" league-wide.
    try:
        from routes.notification_events import EVT_TRADE_PROCESSED
        teams = await _db().teams.find(
            {"league_id": league_id},
            {"owner_id": 1, "co_owner_ids": 1},
        ).to_list(200)
        recipients: set = set()
        for t in teams:
            if t.get("owner_id"):
                recipients.add(t["owner_id"])
            for co in (t.get("co_owner_ids") or []):
                if co:
                    recipients.add(co)
        msg = f"{trade['proposer_team_name']} ↔ {trade['target_team_name']}"
        for uid in recipients:
            try:
                await _create_notification(
                    uid,
                    EVT_TRADE_PROCESSED,
                    "Trade processed",
                    msg,
                    league_id=league_id,
                    link="/transactions",
                )
            except Exception:
                pass

        # Iter 231k — Real-time toast: emit a global Socket.IO event so
        # every league owner sees a live confirmation toast the moment
        # a pending trade auto-processes. Mirrors the championship_crowned
        # pattern (no room arg → broadcasts globally). Frontend filters
        # by league_id in the dashboard banner reload.
        sio = _deps.get("sio")
        if sio is not None:
            try:
                await sio.emit("trade_processed", {
                    "league_id": league_id,
                    "trade_id": str(trade.get("_id")),
                    "proposer_team_name": trade.get("proposer_team_name"),
                    "target_team_name": trade.get("target_team_name"),
                    "asset_count": (
                        len(trade.get("assets_offered") or [])
                        + len(trade.get("assets_requested") or [])
                    ),
                })
            except Exception as e:
                _logger().debug(f"trade_processed sio.emit skipped: {e}")
    except Exception as e:
        _logger().debug(f"trade_processed fanout skipped: {e}")

    await _post_trade_chat_messages(trade, moves)
    refreshed = await _db().trades.find_one({"_id": trade["_id"]})
    if refreshed:
        await _apply_pick_upgrades(refreshed, final_eval=False)

    # Iter 232N.24 — Real-time XP toast for both trade participants.
    # Fires AFTER the trade + notification pipeline runs so the
    # `xp_awarded` broadcast reflects the freshly-incremented career
    # XP total. Best-effort — failures never break the trade path.
    try:
        from utils.xp import emit_xp_gain
        broadcast_fn = _deps.get("broadcast_to_room")
        meta = {
            "trade_id": str(trade.get("_id")),
            "proposer_team": trade.get("proposer_team_name"),
            "target_team": trade.get("target_team_name"),
        }
        for uid in (trade.get("proposer_id"), trade.get("target_owner_id")):
            if uid:
                await emit_xp_gain(
                    _db(), uid,
                    source="trade_accepted",
                    broadcast_fn=broadcast_fn,
                    meta=meta,
                )
    except Exception as e:
        _logger().debug(f"xp_awarded emit skipped (two-team): {e}")

    return {"executed": True, "moves": moves}
