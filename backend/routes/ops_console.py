"""Iter 187 — Commissioner Ops Console summary endpoint.

Returns a single aggregated payload the new `/commissioner/ops-console`
page consumes to render its four counters + the trade-deadline pill.

Surface kept intentionally small + read-only — destructive ops (force
process waivers, cancel trades, etc.) flow through the existing
endpoints in `routes/waivers.py` + `routes/trades.py` so the audit
trail stays unified.
"""
from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Request

router = APIRouter()
_deps: dict = {}


def setup(deps: dict) -> None:
    _deps.update(deps)


def _db(): return _deps["db"]
async def _get_user(request): return await _deps["get_current_user"](request)


@router.get("/leagues/{league_id}/ops-summary")
async def get_ops_summary(league_id: str, request: Request):
    """Aggregated counters for the Ops Console.

    Returns:
        {
          "league_id": str,
          "trade_deadline": {
            "iso": str | None,
            "passed": bool,
            "ms_remaining": int | None,
          },
          "counters": {
            "pending_waivers": int,
            "pending_trades": int,
            "vetoed_trades": int,
            "teams_with_violations": int,
          },
          "recent_vetoes": [{trade_id, vetoed_at, veto_count, ...}],
          "recent_waivers": [{claim_id, team_name, player_name, processes_at, ...}],
        }
    """
    db = _db()
    user = await _get_user(request)

    league = await db.leagues.find_one({"_id": ObjectId(league_id)})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")

    # Commissioner-only — accept any of the league's commissioner
    # fields (see `_user_is_commish` for the canonical check used by
    # all three ops endpoints).
    if not _user_is_commish(league, user):
        raise HTTPException(status_code=403, detail="Commissioner access required")

    # ── Trade deadline ────────────────────────────────────
    deadline_iso = league.get("trade_deadline_at")
    deadline_block = {"iso": deadline_iso, "passed": False, "ms_remaining": None}
    if deadline_iso:
        try:
            dt = datetime.fromisoformat(str(deadline_iso).replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            delta_ms = int((dt - now).total_seconds() * 1000)
            deadline_block = {
                "iso": deadline_iso,
                "passed": delta_ms <= 0,
                "ms_remaining": delta_ms if delta_ms > 0 else 0,
            }
        except (ValueError, TypeError):
            pass  # leave defaults

    # ── Counter queries (4 in parallel-ish via gather) ────
    pending_waivers_q = db.waiver_claims.count_documents({
        "league_id": league_id, "status": "pending",
    })
    pending_trades_q = db.trades.count_documents({
        "league_id": league_id, "status": "pending",
    })
    vetoed_trades_q = db.trades.count_documents({
        "league_id": league_id, "status": "vetoed",
    })

    pending_waivers = await pending_waivers_q
    pending_trades = await pending_trades_q
    vetoed_trades = await vetoed_trades_q

    # ── Teams with violations (cheap-ish: scan teams + count
    #    teams whose lineup map has a `flagged` entry or salary_used
    #    > salary_cap). Heavy roster-rule scans are deferred to the
    #    per-team commissioner audit endpoint. ────────────────
    teams = await db.teams.find({"league_id": league_id}).to_list(50)
    violations_team_count = 0
    cap_total = float(league.get("salary_cap") or 0)
    cap_enabled = bool(league.get("salary_cap_enabled"))
    for team in teams:
        if cap_enabled and cap_total > 0 and float(team.get("salary_used") or 0) > cap_total:
            violations_team_count += 1
            continue
        lineup = team.get("lineup") or {}
        if any((spot or {}).get("flagged") for spot in lineup.values()):
            violations_team_count += 1

    # ── Recent vetoes (last 5) ────────────────────────────
    recent_vetoes_docs = await db.trades.find({
        "league_id": league_id, "status": "vetoed",
    }).sort("vetoed_at", -1).limit(5).to_list(5)
    recent_vetoes = [
        {
            "trade_id": str(t.get("_id")),
            "vetoed_at": t.get("vetoed_at") or t.get("updated_at"),
            "veto_count": (t.get("votes") or {}).get("veto", 0),
            "proposer_team_name": t.get("proposer_team_name"),
            "receiver_team_name": t.get("receiver_team_name"),
        }
        for t in recent_vetoes_docs
    ]

    # ── Recent pending waivers (next 5 to process) ────────
    recent_waivers_docs = await db.waiver_claims.find({
        "league_id": league_id, "status": "pending",
    }).sort("processes_at", 1).limit(5).to_list(5)
    recent_waivers = [
        {
            "claim_id": str(w.get("_id")),
            "team_name": w.get("team_name"),
            "player_name": w.get("player_name"),
            "bid_amount": w.get("bid_amount"),
            "processes_at": w.get("processes_at"),
        }
        for w in recent_waivers_docs
    ]

    return {
        "league_id": league_id,
        "trade_deadline": deadline_block,
        "counters": {
            "pending_waivers": pending_waivers,
            "pending_trades": pending_trades,
            "vetoed_trades": vetoed_trades,
            "teams_with_violations": violations_team_count,
        },
        "recent_vetoes": recent_vetoes,
        "recent_waivers": recent_waivers,
    }


# ── Iter 189 — Per-team violation drilldown ──────────────────────
@router.get("/leagues/{league_id}/ops-violations")
async def get_ops_violations(league_id: str, request: Request):
    """Returns per-team violation detail used by the Ops Console
    slide-over drilldown. Each entry has the team's identity + a list
    of violations (cap breach, lineup flags, …). Lightweight enough to
    re-fetch on every drilldown open."""
    db = _db()
    user = await _get_user(request)
    league = await db.leagues.find_one({"_id": ObjectId(league_id)})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    if not _user_is_commish(league, user):
        raise HTTPException(status_code=403, detail="Commissioner access required")

    cap_enabled = bool(league.get("salary_cap_enabled"))
    cap_total = float(league.get("salary_cap") or 0)
    teams = await db.teams.find({"league_id": league_id}).to_list(50)

    out = []
    for team in teams:
        violations: list[dict] = []
        salary_used = float(team.get("salary_used") or 0)
        # Cap breach
        if cap_enabled and cap_total > 0 and salary_used > cap_total:
            violations.append({
                "code": "cap_over",
                "severity": "error",
                "message": (
                    f"Team is over the cap: "
                    f"${salary_used / 1_000_000:.2f}M / "
                    f"${cap_total / 1_000_000:.1f}M."
                ),
                "delta": int(salary_used - cap_total),
            })
        # Lineup-spot flags raised by other parts of the app (e.g.
        # roster-rules audit). We bubble them up here verbatim so the
        # commissioner has a single pane of glass.
        lineup = team.get("lineup") or {}
        for spot_key, spot in lineup.items():
            if not isinstance(spot, dict):
                continue
            if spot.get("flagged"):
                violations.append({
                    "code": spot.get("flag_code", "lineup_flagged"),
                    "severity": spot.get("flag_severity", "warning"),
                    "message": spot.get("flag_message") or f"Lineup spot {spot_key} flagged.",
                    "spot": spot_key,
                })
        if violations:
            out.append({
                "team_id": str(team["_id"]),
                "team_name": team.get("name") or "Team",
                "owner_id": team.get("owner_id"),
                "salary_used": int(salary_used),
                "cap_total": int(cap_total) if cap_enabled else None,
                "violations": violations,
            })
    return {"league_id": league_id, "teams": out}


# ── Iter 189 — Audit log viewer ──────────────────────────────────
@router.get("/leagues/{league_id}/ops-audit-log")
async def get_ops_audit_log(
    league_id: str,
    request: Request,
    limit: int = 50,
    event_types: Optional[str] = None,
):
    """Returns the most recent `activity_feed` entries for a league,
    optionally filtered by event_type (comma-separated). Used by the
    Ops Console audit log card.

    Returns max `limit=50` entries sorted by `created_at` desc.
    """
    db = _db()
    user = await _get_user(request)
    league = await db.leagues.find_one({"_id": ObjectId(league_id)})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    if not _user_is_commish(league, user):
        raise HTTPException(status_code=403, detail="Commissioner access required")

    limit = max(1, min(int(limit or 50), 100))
    q: dict = {"league_id": league_id}
    if event_types:
        types = [t.strip() for t in event_types.split(",") if t.strip()]
        if types:
            q["event_type"] = {"$in": types}
    docs = await db.activity_feed.find(q).sort("created_at", -1).limit(limit).to_list(limit)
    entries = []
    for d in docs:
        created_at = d.get("created_at")
        if hasattr(created_at, "isoformat"):
            created_at = created_at.isoformat()
        entries.append({
            "id": str(d.get("_id")),
            "event_type": d.get("event_type"),
            "message": d.get("message"),
            "user_id": d.get("user_id"),
            "metadata": d.get("metadata") or {},
            "created_at": created_at,
        })
    return {"league_id": league_id, "entries": entries, "limit": limit}


# ── Shared commissioner gate (used by all three ops endpoints) ───
def _user_is_commish(league: dict, user: dict) -> bool:
    commish_set = set()
    if league.get("commissioner_id"):
        commish_set.add(str(league["commissioner_id"]))
    for cid in (league.get("commissioner_ids") or []):
        commish_set.add(str(cid))
    if league.get("created_by"):
        commish_set.add(str(league["created_by"]))
    return str(user["_id"]) in commish_set
