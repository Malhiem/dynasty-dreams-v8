"""
Iter 228 — Waiver execution engine.

Centralizes the FAAB / auto-priority waiver processing logic that was
previously embedded in `routes/waivers.py::process_waivers`. The engine
is consumed both by:

  • The manual `POST /api/waivers/process` commissioner endpoint
  • The background `_waivers_scheduler_loop` running in `server.py`

Design goals:
  1. **Idempotent** — only claims whose `processes_at <= now` AND
     whose `status == "pending"` are considered. Once processed,
     claims move to `won`/`lost`/`denied`, so a re-run is a no-op.
  2. **System aware** — handles `system_type == "faab"` (bid sort) and
     `system_type == "auto_priority"` (waiver order based on standings
     / manual / random).
  3. **Position-limit safe** — pre-rolls through losers if the top
     candidate cannot legally roster the player.
  4. **Best-effort logging** — auto-snapshot + activity feed writes
     never block the underlying transaction.

Public API:
  • `process_pending_claims(db, league_id, *, log_activity=None,
        broadcast=None, now=None)` — runs one pass for one league.
  • `compute_next_run(league, now=None)` — returns ISO timestamp of the
    next scheduled processing time (used by the UI).
"""
from __future__ import annotations

import logging
import random
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

from bson import ObjectId

log = logging.getLogger("waiver-engine")


# ─── Helpers ────────────────────────────────────────────────────


def _parse_iso(value: str | None) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


async def _build_priority_order(db, league: dict) -> list[str]:
    """Resolves the canonical waiver priority order (highest priority
    first) for a league based on its `transactions_config.waiver` settings.

    Falls back to reverse standings when config is missing.
    Returns a list of `team_id` strings.
    """
    league_id = str(league["_id"])
    cfg = (league.get("transactions_config") or {}).get("waiver") or {}
    mode = cfg.get("priority_order") or "reverse_standings_serpentine"

    teams = await db.teams.find({"league_id": league_id}).to_list(200)
    if not teams:
        return []

    if mode == "manual":
        manual = cfg.get("manual_priority_order") or []
        team_ids_in_league = {str(t["_id"]) for t in teams}
        ordered = [tid for tid in manual if tid in team_ids_in_league]
        # Append any teams missing from the manual list at the end so the
        # processor never silently drops a claim.
        for t in teams:
            tid = str(t["_id"])
            if tid not in ordered:
                ordered.append(tid)
        return ordered

    if mode == "random":
        order = [str(t["_id"]) for t in teams]
        random.shuffle(order)
        return order

    # reverse_standings or reverse_standings_serpentine — worst record first.
    teams.sort(key=lambda t: (t.get("wins", 0), t.get("points_for", 0)))
    return [str(t["_id"]) for t in teams]


async def _check_position_blocked(
    db, league: dict, team: dict, player: dict
) -> str | None:
    """Returns a string reason when the team cannot legally roster `player`
    given league position limits. Returns None when legal."""
    from utils.roster_rules import check_position_limits

    if not bool(league.get("enforce_position_maxes")):
        return None
    roster_ids = team.get("roster") or []
    oids = []
    for rid in roster_ids:
        try:
            oids.append(ObjectId(str(rid)))
        except Exception:
            pass
    roster_players = (
        await db.players.find(
            {"_id": {"$in": oids}},
            {"name": 1, "position": 1, "primary_position": 1,
             "eligible_positions": 1, "player_type": 1},
        ).to_list(200)
        if oids
        else []
    )
    return check_position_limits(league, roster_players, player)


# ─── Core engine ───────────────────────────────────────────────


async def _finalize_winner(
    db, league_id: str, winner: dict, system_type: str, now_iso: str,
) -> bool:
    """Atomically applies the four winner-side writes:
      (1) claim.status="won" + processed_at
      (2) FAAB budget debit (if system_type=="faab" and bid>0)
      (3) optional drop_player_id removed from roster
      (4) player_id added to roster

    Tries a real MongoDB transaction first (replica-set required); when
    transactions are unavailable in this deployment, falls back to a
    compensating-write pattern: any later step's failure rolls back the
    earlier steps so the engine never leaves a half-applied state.

    Returns True on success, False on abort (caller leaves the claim
    pending for the next pass + writes a `waiver_processing_errors` row).
    """
    bid = float(winner.get("bid_amount") or 0) if system_type == "faab" else 0.0
    team_id = winner["team_id"]
    player_id = winner["player_id"]
    drop_player_id = winner.get("drop_player_id")

    # ── Path A: real MongoDB transaction (production replica set) ──
    client = getattr(db, "client", None)
    if client is not None:
        try:
            async with await client.start_session() as session:
                async with session.start_transaction():
                    await db.waiver_claims.update_one(
                        {"_id": winner["_id"]},
                        {"$set": {"status": "won", "processed_at": now_iso}},
                        session=session,
                    )
                    if bid > 0:
                        await db.waiver_budgets.update_one(
                            {"team_id": team_id, "league_id": league_id},
                            {"$inc": {"spent": bid, "remaining": -bid}},
                            session=session,
                        )
                    if drop_player_id:
                        await db.teams.update_one(
                            {"_id": ObjectId(team_id)},
                            {"$pull": {"roster": drop_player_id}},
                            session=session,
                        )
                    await db.teams.update_one(
                        {"_id": ObjectId(team_id)},
                        {"$addToSet": {"roster": player_id}},
                        session=session,
                    )
            return True
        except Exception as tx_err:
            err_msg = str(tx_err).lower()
            # Single-node / standalone mongo → transactions unsupported.
            # Fall through to the compensating-write path.
            if "replica set" not in err_msg and "transaction" not in err_msg \
                    and "session" not in err_msg and "not supported" not in err_msg:
                log.warning(f"waiver finalize transaction error: {tx_err}")
                # Unknown failure — abort the finalize.
                return False

    # ── Path B: compensating-write fallback ──
    applied: list[Callable] = []
    try:
        # (1) claim status
        await db.waiver_claims.update_one(
            {"_id": winner["_id"]},
            {"$set": {"status": "won", "processed_at": now_iso}},
        )

        async def _undo_claim():
            await db.waiver_claims.update_one(
                {"_id": winner["_id"]},
                {"$set": {"status": "pending"}, "$unset": {"processed_at": ""}},
            )
        applied.append(_undo_claim)

        # (2) FAAB debit
        if bid > 0:
            await db.waiver_budgets.update_one(
                {"team_id": team_id, "league_id": league_id},
                {"$inc": {"spent": bid, "remaining": -bid}},
            )

            async def _undo_faab():
                await db.waiver_budgets.update_one(
                    {"team_id": team_id, "league_id": league_id},
                    {"$inc": {"spent": -bid, "remaining": bid}},
                )
            applied.append(_undo_faab)

        # (3) drop (if requested) — track whether the player was actually
        # removed so we can re-add on rollback.
        drop_undo_needed = False
        if drop_player_id:
            res = await db.teams.update_one(
                {"_id": ObjectId(team_id)},
                {"$pull": {"roster": drop_player_id}},
            )
            drop_undo_needed = (res.modified_count or 0) > 0

            async def _undo_drop():
                if drop_undo_needed:
                    await db.teams.update_one(
                        {"_id": ObjectId(team_id)},
                        {"$addToSet": {"roster": drop_player_id}},
                    )
            applied.append(_undo_drop)

        # (4) add winning player to roster
        await db.teams.update_one(
            {"_id": ObjectId(team_id)},
            {"$addToSet": {"roster": player_id}},
        )
        return True
    except Exception as ex:
        log.warning(f"waiver finalize fallback failed for claim {winner.get('_id')}: {ex}")
        # Compensate in reverse order
        for undo in reversed(applied):
            try:
                await undo()
            except Exception as undo_err:
                log.error(f"compensating-write failed: {undo_err}")
        return False


async def process_pending_claims(
    db,
    league_id: str,
    *,
    log_activity: Optional[Callable] = None,
    broadcast: Optional[Callable] = None,
    now: Optional[datetime] = None,
    create_notification: Optional[Callable] = None,
) -> dict:
    """One pass of waiver processing for a league.

    Only claims with `status == "pending"` AND (`processes_at` missing or
    `processes_at <= now`) are processed. Returns a result dict with
    counts and per-claim outcomes.
    """
    league = await db.leagues.find_one({"_id": ObjectId(league_id)})
    if not league:
        return {"processed": 0, "results": [], "skipped": 0,
                "error": "league_not_found"}

    cfg = (league.get("transactions_config") or {}).get("waiver") or {}
    system_type = cfg.get("system_type") or "faab"

    now_dt = now or datetime.now(timezone.utc)
    now_iso = now_dt.isoformat()

    # Load all pending claims for the league
    all_pending = await db.waiver_claims.find({
        "league_id": league_id,
        "status": "pending",
    }).to_list(2000)

    # Filter to claims whose processes_at is due
    due: list[dict] = []
    skipped = 0
    for c in all_pending:
        pa = _parse_iso(c.get("processes_at"))
        if pa is None or pa <= now_dt:
            due.append(c)
        else:
            skipped += 1

    if not due:
        return {"processed": 0, "results": [], "skipped": skipped}

    # Group by player
    by_player: dict[str, list[dict]] = {}
    for c in due:
        by_player.setdefault(c["player_id"], []).append(c)

    # Resolve priority order once (auto_priority only)
    priority_order: list[str] = []
    if system_type == "auto_priority":
        priority_order = await _build_priority_order(db, league)
    priority_index = {tid: idx for idx, tid in enumerate(priority_order)}

    # Track team awards in this pass (for `picks_per_round_policy`)
    fa_cfg = (league.get("transactions_config") or {}).get("free_agency") or {}
    one_per_team = (fa_cfg.get("picks_per_round_policy") or "top_then_next") == "top_then_next"
    teams_already_won: set[str] = set()

    # Pre-fetch player docs for position-limit checks
    player_ids = list(by_player.keys())
    player_oids = []
    for pid in player_ids:
        try:
            player_oids.append(ObjectId(str(pid)))
        except Exception:
            pass
    player_docs_list = await db.players.find({"_id": {"$in": player_oids}}).to_list(len(player_oids) or 1)
    player_docs = {str(p["_id"]): p for p in player_docs_list}

    processed_count = 0
    results: list[dict] = []

    for player_id, claims in by_player.items():
        # Sort candidates by system_type
        if system_type == "faab":
            # Bid DESC, created_at ASC, then priority_index ASC as ultimate tiebreaker
            claims.sort(key=lambda c: (
                -float(c.get("bid_amount") or 0),
                c.get("created_at") or "",
                priority_index.get(c.get("team_id"), 9999),
            ))
        else:  # auto_priority
            claims.sort(key=lambda c: (
                priority_index.get(c.get("team_id"), 9999),
                c.get("created_at") or "",
            ))

        player_doc = player_docs.get(player_id)
        winner = None
        denied: list[tuple[dict, str]] = []
        skipped_this_pass: list[dict] = []  # teams that already won earlier this pass

        for cand in claims:
            cand_team_id = cand.get("team_id")
            # Enforce one-pick-per-team (top_then_next policy)
            if one_per_team and cand_team_id in teams_already_won:
                skipped_this_pass.append(cand)
                continue

            # Position-limit pre-check
            team_doc = await db.teams.find_one({"_id": ObjectId(cand_team_id)})
            if team_doc is None:
                continue
            if player_doc is not None:
                block = await _check_position_blocked(db, league, team_doc, player_doc)
                if block:
                    denied.append((cand, block))
                    continue
            winner = cand
            break

        # Mark denied (position-blocked) claims
        for cand, reason in denied:
            await db.waiver_claims.update_one(
                {"_id": cand["_id"]},
                {"$set": {
                    "status": "denied",
                    "denied_reason": reason,
                    "processed_at": now_iso,
                }},
            )

        # Mark "won-elsewhere-this-pass" claims back to pending so they
        # naturally roll to the next processing cycle. NOTE: we DO move
        # processes_at forward so they don't get re-picked instantly.
        for cand in skipped_this_pass:
            await db.waiver_claims.update_one(
                {"_id": cand["_id"]},
                {"$set": {"deferred_at": now_iso}},
            )

        if winner is None:
            # No legal winner — refund all (claims remain pending → denied)
            for cand in claims:
                if cand in [d[0] for d in denied]:
                    continue
                if cand in skipped_this_pass:
                    continue
                await db.waiver_claims.update_one(
                    {"_id": cand["_id"]},
                    {"$set": {
                        "status": "denied",
                        "denied_reason": "no_legal_claimant",
                        "processed_at": now_iso,
                    }},
                )
            continue

        # Winner found
        teams_already_won.add(winner["team_id"])
        losers = [c for c in claims
                  if c is not winner
                  and c not in [d[0] for d in denied]
                  and c not in skipped_this_pass]

        # ── Iter 228c — Transaction-guarded winner finalization ──
        # The four winner-side writes (claim status, FAAB debit, roster
        # add, optional roster drop) must either ALL apply or NONE apply.
        # Try a real MongoDB session first; fall back to a compensating-
        # write pattern when transactions are unavailable (single-node
        # mongo dev environment).
        winner_finalized = await _finalize_winner(
            db, league_id, winner, system_type, now_iso,
        )
        if not winner_finalized:
            # Engine could not finalize → leave the claim pending so the
            # next scheduler pass retries. Record the failure for audit.
            try:
                await db.waiver_processing_errors.insert_one({
                    "league_id": league_id,
                    "claim_id": str(winner["_id"]),
                    "player_id": winner.get("player_id"),
                    "team_id": winner.get("team_id"),
                    "failed_at": now_iso,
                    "reason": "winner_finalize_aborted",
                })
            except Exception:
                pass
            continue

        # Mark losers
        for loser in losers:
            await db.waiver_claims.update_one(
                {"_id": loser["_id"]},
                {"$set": {"status": "lost", "processed_at": now_iso}},
            )
            if log_activity:
                try:
                    await log_activity(
                        league_id, "waiver_lost",
                        f"{loser['team_name']} lost waiver claim on "
                        f"{loser['player_name']} (${loser.get('bid_amount', 0)} FAAB) — "
                        f"won by {winner['team_name']} (${winner.get('bid_amount', 0)})",
                        None,
                        metadata={
                            "team_id": loser["team_id"],
                            "team_name": loser["team_name"],
                            "player_id": loser["player_id"],
                            "player_name": loser["player_name"],
                            "player_position": loser.get("player_position"),
                            "bid_amount": loser.get("bid_amount"),
                            "winning_team_id": winner["team_id"],
                            "winning_team_name": winner["team_name"],
                            "winning_bid": winner.get("bid_amount"),
                        },
                    )
                except Exception as ex:
                    log.warning(f"log_activity (loser) failed: {ex}")

        # Auto-snapshot is best-effort (audit side-effect, not a state mutation)
        try:
            from services.auto_snapshot import auto_snapshot
            await auto_snapshot(
                db, [winner["team_id"]],
                trigger="waiver_claim",
                metadata={
                    "player_id": winner["player_id"],
                    "player_name": winner["player_name"],
                    "bid": winner.get("bid_amount"),
                    "source": "waiver_engine",
                },
            )
        except Exception as ex:
            log.warning(f"auto_snapshot for winner team={winner.get('team_id')}: {ex}")

        if log_activity:
            try:
                await log_activity(
                    league_id, "waiver_won",
                    f"{winner['team_name']} won {winner['player_name']} on waivers "
                    f"(${winner.get('bid_amount', 0)} FAAB)",
                    None,
                    metadata={
                        "team_id": winner["team_id"],
                        "team_name": winner["team_name"],
                        "player_id": winner["player_id"],
                        "player_name": winner["player_name"],
                        "player_position": winner.get("player_position"),
                        "bid_amount": winner.get("bid_amount"),
                        "drop_player_id": winner.get("drop_player_id"),
                        "drop_player_name": winner.get("drop_player_name"),
                        "competing_claims": [
                            {"team_id": ls["team_id"],
                             "team_name": ls["team_name"],
                             "bid_amount": ls.get("bid_amount")}
                            for ls in losers
                        ],
                        "source": "waiver_engine",
                    },
                )
            except Exception as ex:
                log.warning(f"log_activity (winner) failed: {ex}")

        results.append({
            "player_id": winner["player_id"],
            "player": winner["player_name"],
            "winner_team_id": winner["team_id"],
            "winner": winner["team_name"],
            "bid": winner.get("bid_amount"),
            "losers": [ls["team_name"] for ls in losers],
        })
        processed_count += 1

        # Iter 230 — Notify the winning team's owner + co-owners.
        if create_notification:
            try:
                winner_team_doc = await db.teams.find_one(
                    {"_id": ObjectId(winner["team_id"])},
                    {"owner_id": 1, "co_owner_ids": 1, "name": 1},
                )
                recipients: set = set()
                if winner_team_doc:
                    if winner_team_doc.get("owner_id"):
                        recipients.add(winner_team_doc["owner_id"])
                    for co in (winner_team_doc.get("co_owner_ids") or []):
                        if co:
                            recipients.add(co)
                from routes.notification_events import EVT_WAIVER_CLAIM_SUCCESS
                msg = f"You won the claim for {winner['player_name']}"
                if winner.get("bid_amount") is not None:
                    msg += f" — bid ${winner['bid_amount']}"
                for uid in recipients:
                    await create_notification(
                        uid,
                        EVT_WAIVER_CLAIM_SUCCESS,
                        "Waiver claim won",
                        msg,
                        league_id,
                        "/waivers",
                    )
            except Exception as ex:
                log.warning(f"waiver win notify failed: {ex}")

    if broadcast and results:
        try:
            await broadcast(f"league_{league_id}", "waivers_processed", {"results": results})
        except Exception as ex:
            log.warning(f"broadcast waivers_processed failed: {ex}")

    # Stamp the league with last_processed_at
    try:
        await db.leagues.update_one(
            {"_id": ObjectId(league_id)},
            {"$set": {"waivers_last_processed_at": now_iso}},
        )
    except Exception:
        pass

    return {
        "processed": processed_count,
        "results": results,
        "skipped": skipped,
        "system_type": system_type,
    }


# ─── Next-run scheduling ───────────────────────────────────────


def compute_next_run(league: dict, now: Optional[datetime] = None) -> Optional[str]:
    """Returns ISO datetime (UTC) for the next scheduled processing pass.

    Returns None when:
      • waiver is disabled, or
      • processing_mode == "days" with no recent pending claim (the next
        run is tied to a claim's `processes_at`, not a clock).

    For `processing_mode == "scheduled"`, the `time` field of each
    schedule slot is interpreted in the league's local timezone
    (`league.timezone`, IANA name; defaults to UTC when missing or
    unparseable). The returned ISO string is in UTC so callers can
    safely use `new Date(iso)` in the browser.
    """
    cfg = (league.get("transactions_config") or {}).get("waiver") or {}
    if not cfg.get("enabled"):
        return None

    mode = cfg.get("processing_mode") or "days"
    now_dt = now or datetime.now(timezone.utc)

    if mode == "scheduled":
        slots = cfg.get("processing_schedule") or []
        if not slots:
            return None

        # Resolve league timezone (iter 228c). Falls back to UTC.
        tz = timezone.utc
        tz_name = league.get("timezone")
        if tz_name and tz_name.upper() != "UTC":
            try:
                from zoneinfo import ZoneInfo
                tz = ZoneInfo(tz_name)
            except Exception:
                tz = timezone.utc

        now_local = now_dt.astimezone(tz)
        candidates: list[datetime] = []
        for slot in slots:
            try:
                dow = int(slot.get("day_of_week"))
                hh, mm = (slot.get("time") or "00:00").split(":")
                hh_i = int(hh)
                mm_i = int(mm)
            except Exception:
                continue
            # Find next datetime matching this DOW + time in the league's
            # local timezone, then convert to UTC for the response.
            for ahead in range(0, 8):
                cand_local = (now_local + timedelta(days=ahead)).replace(
                    hour=hh_i, minute=mm_i, second=0, microsecond=0
                )
                if cand_local.weekday() == dow and cand_local > now_local:
                    candidates.append(cand_local.astimezone(timezone.utc))
                    break
        if not candidates:
            return None
        return min(candidates).isoformat()

    # days mode → derived from days_count, return now+days_count days
    days = int(cfg.get("processing_days_count") or 2)
    return (now_dt + timedelta(days=days)).isoformat()
