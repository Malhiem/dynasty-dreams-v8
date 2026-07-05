"""Iter 232N.27 — Draft leaderboard router.

Endpoint: `GET /api/drafts/{draft_id}/leaderboard`

Computes per-team stats from the recorded picks + trades:
    • picks_made         — count of picks the team wound up with
    • auto_picks         — count where `auto_picked: true`
    • avg_pick_seconds   — mean of `time_taken_seconds` across picks
    • fastest_pick_secs  — min pick time (regular picks only)
    • slowest_pick_secs  — max pick time
    • queue_hit_rate     — % of auto-picks via="queue" (vs top_eligible)
    • trades_count       — accepted trades in this league since the
                            draft's `created_at`

Then buckets teams into flashy "trash-talk" categories:
    • speed_demon   — fastest avg pick time
    • slow_poke     — slowest avg pick time
    • autopilot     — most auto-picks
    • wheeler_dealer — most trades
    • iron_man      — most picks made
    • queue_master  — highest queue-hit-rate among auto-pickers

Live during the draft; a `is_final: true` payload flag flips true when
the draft's `status == "completed"` so the frontend can hide certain
awards until the big reveal.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from statistics import mean

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Request

router = APIRouter()
_deps: dict = {}
logger = logging.getLogger(__name__)


def setup(deps: dict) -> None:
    _deps.update(deps)


def _db():
    return _deps["db"]


async def _get_user(request: Request):
    return await _deps["get_current_user"](request)


def _seconds_of(pick: dict) -> int | None:
    val = pick.get("time_taken_seconds")
    if val is None:
        return None
    try:
        val = int(val)
    except (TypeError, ValueError):
        return None
    return val if val >= 0 else None


def _bucket_awards(rows: list[dict], is_final: bool) -> dict:
    """Pick the champion for each award, tie-breaking by team name."""
    def top(rows_local, key, reverse=True, min_val=0):
        candidates = [r for r in rows_local if r.get(key) not in (None, 0) and (r.get(key) or 0) > min_val - 0.0001]
        if not candidates:
            return None
        candidates.sort(key=lambda r: (r[key], r["team_name"]), reverse=reverse)
        w = candidates[0]
        return {
            "team_id": w["team_id"],
            "team_name": w["team_name"],
            "logo_abbr": w["logo_abbr"],
            "value": w[key],
        }

    def bottom(rows_local, key, min_val=0):
        candidates = [r for r in rows_local if r.get(key) not in (None,) and (r.get(key) or 0) > min_val - 0.0001]
        if not candidates:
            return None
        candidates.sort(key=lambda r: (r[key], r["team_name"]))
        w = candidates[0]
        return {
            "team_id": w["team_id"],
            "team_name": w["team_name"],
            "logo_abbr": w["logo_abbr"],
            "value": w[key],
        }

    speed = bottom(rows, "avg_pick_seconds")
    slow = top(rows, "avg_pick_seconds")
    autopilot = top(rows, "auto_picks")
    wheeler = top(rows, "trades_count")
    iron = top(rows, "picks_made")
    queue_master = top([r for r in rows if (r.get("auto_picks") or 0) > 0], "queue_hit_rate")

    return {
        "speed_demon": speed,
        "slow_poke": slow,
        "autopilot": autopilot,
        "wheeler_dealer": wheeler,
        "iron_man": iron,
        "queue_master": queue_master,
        # Awards visible pre-draft-end vs after the reveal. Frontend
        # dims the "big reveal" categories while the draft is live so
        # managers stay in the dark about who's about to get roasted.
        "hidden_until_final": ["speed_demon", "slow_poke", "autopilot"],
        "is_final": is_final,
    }


@router.get("/drafts/{draft_id}/leaderboard")
async def get_draft_leaderboard(draft_id: str, request: Request):
    """Live-or-final draft leaderboard aggregating pick timings +
    auto-picks + queue-hit-rate + intra-league trades.
    """
    await _get_user(request)   # auth gate — any signed-in user in the league
    try:
        oid = ObjectId(draft_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid draft_id")

    draft = await _db().drafts.find_one({"_id": oid})
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")

    league_id = draft.get("league_id")
    picks = draft.get("picks") or []
    team_map = draft.get("team_map") or {}
    team_abbrs = draft.get("team_abbrs") or []

    # ── Aggregate picks by team ─────────────────────────────────────
    per_team: dict[str, dict] = {}
    for abbr in team_abbrs:
        meta = team_map.get(abbr) or {}
        tid = meta.get("id")
        if not tid:
            continue
        per_team[tid] = {
            "team_id": tid,
            "team_name": meta.get("name") or abbr,
            "logo_abbr": abbr,
            "picks_made": 0,
            "auto_picks": 0,
            "queue_auto_picks": 0,
            "pick_times": [],
        }

    for p in picks:
        tid = p.get("team_id")
        row = per_team.get(tid)
        if not row:
            continue
        row["picks_made"] += 1
        if p.get("auto_picked"):
            row["auto_picks"] += 1
            if p.get("auto_pick_via") == "queue":
                row["queue_auto_picks"] += 1
        secs = _seconds_of(p)
        if secs is not None:
            row["pick_times"].append(secs)

    # ── Intra-league trades since draft creation ─────────────────────
    trades_by_team: dict[str, int] = {}
    if league_id:
        draft_start_raw = draft.get("created_at") or draft.get("scheduled_time")
        anchor: datetime | None = None
        if isinstance(draft_start_raw, datetime):
            anchor = draft_start_raw
        elif isinstance(draft_start_raw, str):
            try:
                anchor = datetime.fromisoformat(draft_start_raw.replace("Z", "+00:00"))
            except ValueError:
                anchor = None
        trade_query: dict = {"league_id": league_id, "status": "accepted"}
        if anchor:
            trade_query["created_at"] = {"$gte": anchor}
        async for t in _db().trades.find(trade_query):
            for key in ("proposer_team_id", "target_team_id"):
                tid_str = str(t.get(key) or "")
                if tid_str:
                    trades_by_team[tid_str] = trades_by_team.get(tid_str, 0) + 1
            # Multi-party trades pack participants into `parties`.
            for party in (t.get("parties") or []):
                pid = str(party.get("team_id") or "")
                if pid:
                    trades_by_team[pid] = trades_by_team.get(pid, 0) + 1

    # ── Finalise per-team stats ─────────────────────────────────────
    rows: list[dict] = []
    for tid, row in per_team.items():
        times = row.pop("pick_times")
        row["avg_pick_seconds"] = round(mean(times), 1) if times else None
        row["fastest_pick_secs"] = min(times) if times else None
        row["slowest_pick_secs"] = max(times) if times else None
        auto_ct = row["auto_picks"]
        row["queue_hit_rate"] = (
            round((row.pop("queue_auto_picks") / auto_ct) * 100, 1)
            if auto_ct else None
        )
        # Drop queue_auto_picks even when auto_ct==0
        row.pop("queue_auto_picks", None)
        row["trades_count"] = trades_by_team.get(tid, 0)
        rows.append(row)

    rows.sort(key=lambda r: (r["team_name"] or "").lower())

    is_final = (draft.get("status") == "completed")
    awards = _bucket_awards(rows, is_final=is_final)

    return {
        "draft_id": draft_id,
        "league_id": league_id,
        "is_final": is_final,
        "total_picks": len(picks),
        "auto_picks_total": sum(r["auto_picks"] for r in rows),
        "rows": rows,
        "awards": awards,
    }


# ─── Iter 232N.28 — Draft Hall of Awards (Trophy Room integration) ────────
@router.get("/leagues/{league_id}/draft-hall-of-awards")
async def get_league_draft_hall_of_awards(league_id: str, request: Request):
    """Returns every completed draft for a league with its final
    leaderboard payload — powers the "Draft Hall of Awards" display
    case in the league Trophy Room. Only the six revealed award
    categories are surfaced (speed_demon, slow_poke, autopilot,
    wheeler_dealer, iron_man, queue_master) plus each draft's meta
    (year, name, total_picks, auto_picks_total).
    """
    await _get_user(request)

    drafts = await _db().drafts.find(
        {"league_id": league_id, "status": "completed"}
    ).sort("completed_at", -1).to_list(200)

    if not drafts:
        return {"league_id": league_id, "drafts": []}

    # Reuse the same aggregation as the live endpoint by re-invoking
    # it per-draft — keeps the two payloads perfectly in sync.
    hall_entries = []
    for d in drafts:
        try:
            payload = await get_draft_leaderboard(str(d["_id"]), request=request)
        except Exception:
            continue
        completed_at = d.get("completed_at") or d.get("updated_at") or d.get("created_at")
        year = None
        if isinstance(completed_at, datetime):
            year = completed_at.year
        elif isinstance(completed_at, str):
            try:
                year = datetime.fromisoformat(completed_at.replace("Z", "+00:00")).year
            except ValueError:
                year = None
        hall_entries.append({
            "draft_id": str(d["_id"]),
            "name": d.get("name") or f"Draft {year or ''}".strip(),
            "year": year,
            "total_picks": payload.get("total_picks", 0),
            "auto_picks_total": payload.get("auto_picks_total", 0),
            "awards": payload.get("awards", {}),
        })
    return {"league_id": league_id, "drafts": hall_entries}
