"""Shared enforcement for league.transactions_config (iter 117).

Both `routes/roster.py` (FA add/drop) and `routes/waivers.py` (waiver
claims) call into this module so the rules stay in one place:

  • claim_limits (season / week × total / fa / waivers)
  • claim_rules (lock_at_first_game, allow_non_playoff_teams_claims,
                 prevent_injured, prevent_minors)
  • waiver.abuse_window (re-claim after drop within N days)

Raises `fastapi.HTTPException(400, "human reason")` when a rule blocks
the action. Callers pass `tx_kind="fa"` or `tx_kind="waiver"` so the
right limit bucket is checked.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal, Optional

from bson import ObjectId
from fastapi import HTTPException

from routes.transactions_config import TransactionsConfig


TxKind = Literal["fa", "waiver"]


def _cfg(league: dict) -> TransactionsConfig:
    stored = league.get("transactions_config") or {}
    return TransactionsConfig(**stored)


async def _count_claims(db, team_id: str, season: str, week: Optional[int], tx_kind: TxKind) -> int:
    """Count claims of `tx_kind` for the team in the given window.

    For FA: `activity_feed` rows with event_type=roster_add scoped by team.
    For waivers: `waiver_claims` rows scoped by team+season.
    """
    if tx_kind == "fa":
        q = {"metadata.team_id": team_id, "event_type": "roster_add"}
        if season:
            q["metadata.season"] = season
        if week is not None:
            q["metadata.week"] = week
        try:
            return await db.activity_feed.count_documents(q)
        except Exception:
            return 0
    # waivers
    q = {"team_id": team_id, "season": season}
    if week is not None:
        q["week"] = week
    q["status"] = {"$in": ["won", "lost", "pending"]}
    try:
        return await db.waiver_claims.count_documents(q)
    except Exception:
        return 0


async def _enforce_claim_limits(db, team_id: str, league: dict, tx_kind: TxKind) -> None:
    cfg = _cfg(league)
    limits = cfg.claim_limits
    season = league.get("season") or "2025-2026"
    current_week = int(league.get("current_week") or 1)

    # Iter 119 — when the waiver section is enabled AND this is a waiver
    # claim, the waiver-section's per-Setting limits override the global
    # season/week buckets. Force_* gates are enforced upstream in
    # routes/waivers.py + routes/roster.py before this is called.
    if tx_kind == "waiver" and cfg.waiver.enabled:
        wlim = cfg.waiver.claim_limits
        # All-time waiver count for this team (per-Setting, not per-season)
        try:
            cnt = await db.waiver_claims.count_documents({
                "team_id": team_id,
                "status": {"$in": ["won", "lost", "pending"]},
            })
        except Exception:
            cnt = 0
        if wlim.total is not None and cnt >= wlim.total:
            raise HTTPException(status_code=400,
                                detail=f"Waiver setting cap reached ({cnt}/{wlim.total}).")
        if wlim.waivers is not None and cnt >= wlim.waivers:
            raise HTTPException(status_code=400,
                                detail=f"Waiver Wire cap reached ({cnt}/{wlim.waivers}).")
        # Don't short-circuit — also honour global season/week caps below.

    # Season-wide
    season_total = await _count_claims(db, team_id, season, None, "fa") + \
                   await _count_claims(db, team_id, season, None, "waiver")
    season_bucket = await _count_claims(db, team_id, season, None, tx_kind)

    if limits.season.total is not None and season_total >= limits.season.total:
        raise HTTPException(status_code=400,
                            detail=f"Season claim cap reached ({season_total}/{limits.season.total}).")
    bucket_season_cap = limits.season.fa if tx_kind == "fa" else limits.season.waivers
    if bucket_season_cap is not None and season_bucket >= bucket_season_cap:
        kind_label = "free-agency" if tx_kind == "fa" else "waiver"
        raise HTTPException(status_code=400,
                            detail=f"Season {kind_label} cap reached ({season_bucket}/{bucket_season_cap}).")

    # Per-week
    week_total = await _count_claims(db, team_id, season, current_week, "fa") + \
                 await _count_claims(db, team_id, season, current_week, "waiver")
    week_bucket = await _count_claims(db, team_id, season, current_week, tx_kind)

    if limits.week.total is not None and week_total >= limits.week.total:
        raise HTTPException(status_code=400,
                            detail=f"Weekly claim cap reached ({week_total}/{limits.week.total}) for week {current_week}.")
    bucket_week_cap = limits.week.fa if tx_kind == "fa" else limits.week.waivers
    if bucket_week_cap is not None and week_bucket >= bucket_week_cap:
        kind_label = "free-agency" if tx_kind == "fa" else "waiver"
        raise HTTPException(status_code=400,
                            detail=f"Weekly {kind_label} cap reached ({week_bucket}/{bucket_week_cap}) for week {current_week}.")


def _player_is_injured(player: dict, policy: str) -> bool:
    if policy == "off":
        return False
    status = (player.get("injury_status") or player.get("status") or "").lower()
    if policy == "any":
        return bool(status) and status not in ("healthy", "active", "ok")
    if policy == "nhl_ir":
        return status in ("ir", "ltir", "ir-ltir", "long-term-ir")
    if policy == "all_flags":
        return bool(status) and status not in ("healthy", "active", "ok")
    return False


def _player_is_minor(player: dict, league: dict) -> bool:
    """Same rule the lineup compliance check uses."""
    gp = int(player.get("games_played") or 0)
    bd = player.get("birth_date")
    age = None
    if bd:
        try:
            bd_dt = datetime.fromisoformat(bd.split("T")[0]) if isinstance(bd, str) else bd
            age = (datetime.now(timezone.utc).replace(tzinfo=None) - bd_dt).days // 365
        except Exception:
            age = None
    max_age = int(league.get("minors_max_age") or 22)
    max_games = int(league.get("minors_max_career_games") or 25)
    return (gp <= max_games) or (age is not None and age <= max_age)


async def _enforce_player_filters(player: dict, league: dict, tx_kind: TxKind) -> None:
    cfg = _cfg(league)
    rules = cfg.claim_rules
    # Global rules first
    if _player_is_injured(player, rules.prevent_injured):
        raise HTTPException(status_code=400,
                            detail=f"Claims for injured players are blocked by this league ({rules.prevent_injured}).")
    if rules.prevent_minors and _player_is_minor(player, league):
        raise HTTPException(status_code=400,
                            detail="Claims for minor-league-eligible players are blocked by this league.")
    # Iter 119 — when waiver-specific filters are enabled and stricter, they
    # take precedence for waiver claims.
    if tx_kind == "waiver" and cfg.waiver.enabled:
        w = cfg.waiver
        if w.prevent_injured != "off" and _player_is_injured(player, w.prevent_injured):
            raise HTTPException(status_code=400,
                                detail=f"Waiver: claims for injured players ({w.prevent_injured}) are blocked.")
        if w.prevent_minors and _player_is_minor(player, league):
            raise HTTPException(status_code=400,
                                detail="Waiver: claims for minor-league-eligible players are blocked.")
        if w.prevent_prospects and _player_is_prospect(player, league):
            raise HTTPException(status_code=400,
                                detail="Waiver: claims for prospects are blocked by this league.")


def _player_is_prospect(player: dict, league: dict) -> bool:
    """Prospect = player flagged `is_prospect`, OR meeting the league's
    `prospect_max_age` / `prospect_max_career_games` guideline. We default
    to NHL convention: ≤24 yrs and ≤100 career games."""
    if player.get("is_prospect") is True:
        return True
    gp = int(player.get("games_played") or 0)
    bd = player.get("birth_date")
    age = None
    if bd:
        try:
            bd_dt = datetime.fromisoformat(bd.split("T")[0]) if isinstance(bd, str) else bd
            age = (datetime.now(timezone.utc).replace(tzinfo=None) - bd_dt).days // 365
        except Exception:
            age = None
    max_age = int(league.get("prospect_max_age") or 24)
    max_games = int(league.get("prospect_max_career_games") or 100)
    return (gp <= max_games) and (age is not None and age <= max_age)


async def _enforce_lock_at_first_game(db, league: dict) -> None:
    cfg = _cfg(league)
    if not cfg.claim_rules.lock_at_first_game:
        return
    today = datetime.now(timezone.utc).date().isoformat()
    # We rely on `games` collection populated by the live-scoring worker;
    # if at least one game's puck has dropped today, transactions are locked.
    try:
        any_started = await db.games.find_one({
            "game_date": today,
            "$or": [{"status": {"$ne": "scheduled"}}, {"period": {"$gt": 0}}],
        })
    except Exception:
        any_started = None
    if any_started:
        raise HTTPException(status_code=400,
                            detail="Transactions are locked — at least one game has already started today.")


async def _enforce_non_playoff_block(db, league: dict, team: dict) -> None:
    cfg = _cfg(league)
    if cfg.claim_rules.allow_non_playoff_teams_claims:
        return
    in_playoffs = bool(league.get("playoffs_started_at")) or (
        int(league.get("current_week") or 0) >= int(league.get("playoff_start_week") or 999)
    )
    if not in_playoffs:
        return
    # Look at the team's standing — if not in `playoff_teams` ranked slots
    # they cannot claim during the playoff window.
    playoff_teams_cnt = int(league.get("playoff_teams") or 0)
    if playoff_teams_cnt <= 0:
        return
    ranked = await db.teams.find(
        {"league_id": str(league["_id"])},
        {"_id": 1, "wins": 1, "points_for": 1},
    ).sort([("wins", -1), ("points_for", -1)]).to_list(60)
    eligible_ids = {str(t["_id"]) for t in ranked[:playoff_teams_cnt]}
    if str(team["_id"]) not in eligible_ids:
        raise HTTPException(status_code=400,
                            detail="Non-playoff teams are blocked from claims by this league once the playoffs begin.")


async def _enforce_abuse_window(db, team_id: str, league: dict, player_id: str, tx_kind: TxKind) -> None:
    """If the league has the waiver-abuse rule on, the same team can't re-add
    a player they dropped within `abuse_window_days`."""
    cfg = _cfg(league)
    if not cfg.waiver.enabled or not cfg.waiver.abuse_window_enabled:
        return
    if tx_kind != "fa" and tx_kind != "waiver":
        return
    days = int(cfg.waiver.abuse_window_days)
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    recent_drop = await db.activity_feed.find_one({
        "metadata.team_id": team_id,
        "metadata.player_id": player_id,
        "event_type": "roster_drop",
        "created_at": {"$gte": cutoff},
    })
    if recent_drop:
        raise HTTPException(status_code=400,
                            detail=f"Waiver-abuse rule blocks re-adding this player — your team dropped them within the last {days} day(s).")


async def enforce_claim(
    db, *,
    team_id: str,
    league: dict,
    player: dict,
    tx_kind: TxKind,
) -> None:
    """One call that runs every transactions-config gate for an add/claim
    flow. Raises HTTPException(400, …) on the first violation.

    Order matches the user's mental model: limits → player filters →
    time-of-day lock → playoff block → abuse window.
    """
    team = await db.teams.find_one({"_id": ObjectId(team_id)})
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    await _enforce_claim_limits(db, team_id, league, tx_kind)
    await _enforce_player_filters(player, league, tx_kind)
    await _enforce_lock_at_first_game(db, league)
    await _enforce_non_playoff_block(db, league, team)
    await _enforce_abuse_window(db, team_id, league, str(player["_id"]), tx_kind)


async def enforce_drop(
    db, *,
    team_id: str,
    league: dict,
) -> None:
    """Drops are gated by the same time-of-day + playoff rules as adds, but
    the per-bucket claim limits do NOT count drops (the user asked for
    'claims' limits, not 'transactions' limits). Abuse-window is for re-
    adds only."""
    team = await db.teams.find_one({"_id": ObjectId(team_id)})
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    await _enforce_lock_at_first_game(db, league)
    await _enforce_non_playoff_block(db, league, team)
