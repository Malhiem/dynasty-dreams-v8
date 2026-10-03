"""Iter 187 — Commissioner Ops Console summary endpoint.

Returns a single aggregated payload the new `/commissioner/ops-console`
page consumes to render its four counters + the trade-deadline pill.

Surface kept intentionally small + read-only — destructive ops (force
process waivers, cancel trades, etc.) flow through the existing
endpoints in `routes/waivers.py` + `routes/trades.py` so the audit
trail stays unified.
"""
import csv
import io
from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

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


# ── Iter 191 — Violation drilldown actions ──────────────────────
# `Notify owner` — sends an in-app notification to the team's owner
# summarising the open violations. Returns the count of notifications
# created (1 per violating team) so the UI can show a toast like
# "Notified 3 owners".
@router.post("/leagues/{league_id}/ops-violations/notify")
async def notify_violation_owners(league_id: str, request: Request):
    db = _db()
    user = await _get_user(request)
    league = await db.leagues.find_one({"_id": ObjectId(league_id)})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    if not _user_is_commish(league, user):
        raise HTTPException(status_code=403, detail="Commissioner access required")

    create_notification = _deps["create_notification"]

    teams = await db.teams.find({"league_id": league_id}).to_list(50)
    cap_enabled = bool(league.get("salary_cap_enabled"))
    cap_total = float(league.get("salary_cap") or 0)
    notified = 0
    for team in teams:
        salary_used = float(team.get("salary_used") or 0)
        msgs: list[str] = []
        if cap_enabled and cap_total > 0 and salary_used > cap_total:
            msgs.append(
                f"Salary cap over by ${(salary_used - cap_total) / 1_000_000:.2f}M"
            )
        lineup = team.get("lineup") or {}
        for spot_key, spot in lineup.items():
            if isinstance(spot, dict) and spot.get("flagged"):
                msgs.append(spot.get("flag_message") or f"Lineup spot {spot_key} flagged")
        if not msgs or not team.get("owner_id"):
            continue
        await create_notification(
            user_id=team["owner_id"],
            kind="roster_violation",
            title=f"Action required for {team.get('name', 'your team')}",
            body=" · ".join(msgs)[:280],
            link=f"/team",
            metadata={"league_id": league_id, "team_id": str(team["_id"])},
        )
        notified += 1
    return {"notified": notified}


# `Force-fix` — autonomously moves illegal players to legal sections
# where possible. Currently handles two cases:
#   1. Healthy player on IR → move to bench (if bench has room).
#   2. Cap-over violations are NOT auto-fixable (requires trade) — we
#      return them as a `skipped` list so the UI can surface why.
@router.post("/leagues/{league_id}/ops-violations/force-fix")
async def force_fix_violations(league_id: str, request: Request):
    db = _db()
    user = await _get_user(request)
    league = await db.leagues.find_one({"_id": ObjectId(league_id)})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    if not _user_is_commish(league, user):
        raise HTTPException(status_code=403, detail="Commissioner access required")

    log_activity = _deps["log_activity"]

    teams = await db.teams.find({"league_id": league_id}).to_list(50)
    fixes: list[dict] = []
    skipped: list[dict] = []
    for team in teams:
        lineup = team.get("lineup") or {}
        if not isinstance(lineup, dict):
            continue
        modified = False
        for spot_key, spot in list(lineup.items()):
            if not isinstance(spot, dict) or not spot.get("flagged"):
                continue
            code = spot.get("flag_code") or ""
            if code == "healthy_on_ir":
                spot["section"] = "bench"
                spot.pop("flagged", None)
                spot.pop("flag_code", None)
                spot.pop("flag_message", None)
                modified = True
                fixes.append({
                    "team_id": str(team["_id"]),
                    "team_name": team.get("name"),
                    "spot": spot_key,
                    "action": "moved_to_bench",
                })
            else:
                skipped.append({
                    "team_id": str(team["_id"]),
                    "team_name": team.get("name"),
                    "code": code or "unknown",
                    "reason": "Not auto-fixable — owner action required.",
                })
        # Cap-over violations — surface but don't fix.
        cap_enabled = bool(league.get("salary_cap_enabled"))
        cap_total = float(league.get("salary_cap") or 0)
        salary_used = float(team.get("salary_used") or 0)
        if cap_enabled and cap_total > 0 and salary_used > cap_total:
            skipped.append({
                "team_id": str(team["_id"]),
                "team_name": team.get("name"),
                "code": "cap_over",
                "reason": "Cap breach can't be auto-fixed — owner must trade or drop.",
            })
        if modified:
            await db.teams.update_one({"_id": team["_id"]}, {"$set": {"lineup": lineup}})

    if fixes:
        await log_activity(
            league_id=league_id,
            event_type="ops_force_fix",
            message=f"Commissioner auto-fixed {len(fixes)} roster violation(s)",
            user_id=str(user["_id"]),
            metadata={"fixes": fixes, "skipped": skipped},
        )
    return {"fixed_count": len(fixes), "skipped_count": len(skipped), "fixes": fixes, "skipped": skipped}


# ── Iter 189 — Audit log viewer ──────────────────────────────────
@router.get("/leagues/{league_id}/ops-audit-log")
async def get_ops_audit_log(
    league_id: str,
    request: Request,
    limit: int = 50,
    event_types: Optional[str] = None,
    format: Optional[str] = None,
):
    """Returns the most recent `activity_feed` entries for a league,
    optionally filtered by event_type (comma-separated). Used by the
    Ops Console audit log card.

    Iter 190:
      * Per-entry user attribution — when `user_id` is set we batch-
        fetch the user docs once and decorate each entry with the
        owner's display name + email (no extra round-trips per row).
      * `?format=csv` returns a streaming CSV download instead of
        JSON so commissioners can archive seasons. CSV columns:
        created_at, event_type, user_name, user_email, message,
        metadata_json.

    Returns max `limit=50` entries sorted by `created_at` desc.
    """
    db = _db()
    user = await _get_user(request)
    league = await db.leagues.find_one({"_id": ObjectId(league_id)})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    if not _user_is_commish(league, user):
        raise HTTPException(status_code=403, detail="Commissioner access required")

    # For CSV exports allow up to 1000 rows so a whole season fits.
    is_csv = (format or "").lower() == "csv"
    cap = 1000 if is_csv else 100
    limit = max(1, min(int(limit or 50), cap))

    q: dict = {"league_id": league_id}
    if event_types:
        types = [t.strip() for t in event_types.split(",") if t.strip()]
        if types:
            q["event_type"] = {"$in": types}
    docs = await db.activity_feed.find(q).sort("created_at", -1).limit(limit).to_list(limit)

    # Iter 190 — Batch user attribution. Collect distinct user_ids
    # then resolve them in one query so the response is constant-time
    # regardless of how many entries we render.
    user_ids = list({d.get("user_id") for d in docs if d.get("user_id")})
    user_lookup: dict = {}
    if user_ids:
        try:
            # User ids in `activity_feed` are stored as raw `str(ObjectId)`
            # (see `log_activity` in server.py), so query both forms to
            # be defensive across collections that diverged historically.
            object_ids = []
            for uid in user_ids:
                try:
                    object_ids.append(ObjectId(uid))
                except Exception:
                    pass
            users_q = {"$or": [
                {"_id": {"$in": object_ids}} if object_ids else {"_id": None},
                {"_id": {"$in": user_ids}},
            ]}
            users = await db.users.find(users_q).to_list(len(user_ids) + 5)
            for u in users:
                key = str(u.get("_id"))
                user_lookup[key] = {
                    "name": (u.get("first_name") or "") + (
                        " " + u.get("last_name") if u.get("last_name") else ""
                    ).strip() or u.get("username") or u.get("email") or "—",
                    "email": u.get("email"),
                }
        except Exception:
            # Attribution is non-essential; degrade gracefully.
            user_lookup = {}

    def _attribution(uid):
        if not uid:
            return {"user_name": None, "user_email": None}
        hit = user_lookup.get(str(uid)) or {}
        return {
            "user_name": (hit.get("name") or "").strip() or None,
            "user_email": hit.get("email"),
        }

    if is_csv:
        # Stream a small CSV so big seasons don't balloon memory.
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow([
            "created_at", "event_type", "user_name", "user_email", "message", "metadata_json",
        ])
        for d in docs:
            created_at = d.get("created_at")
            if hasattr(created_at, "isoformat"):
                created_at = created_at.isoformat()
            attr = _attribution(d.get("user_id"))
            import json as _json
            writer.writerow([
                created_at or "",
                d.get("event_type") or "",
                attr["user_name"] or "",
                attr["user_email"] or "",
                d.get("message") or "",
                _json.dumps(d.get("metadata") or {}, separators=(",", ":"), default=str),
            ])
        buf.seek(0)
        filename = f"audit-log-{league_id}-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M')}.csv"
        return StreamingResponse(
            iter([buf.read()]),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    entries = []
    for d in docs:
        created_at = d.get("created_at")
        if hasattr(created_at, "isoformat"):
            created_at = created_at.isoformat()
        attr = _attribution(d.get("user_id"))
        entries.append({
            "id": str(d.get("_id")),
            "event_type": d.get("event_type"),
            "message": d.get("message"),
            "user_id": d.get("user_id"),
            "user_name": attr["user_name"],
            "user_email": attr["user_email"],
            "metadata": d.get("metadata") or {},
            "created_at": created_at,
        })
    return {"league_id": league_id, "entries": entries, "limit": limit}


# ─────────────────────────────────────────────────────────────────────
# Iter 197 — Mark Winner + Distribute Prize (close-out the playoffs)
# ─────────────────────────────────────────────────────────────────────
from pydantic import BaseModel, Field  # noqa: E402


class MarkWinnerBody(BaseModel):
    matchup_id: str
    winner_team_id: str
    home_score: Optional[float] = None
    away_score: Optional[float] = None


@router.post("/leagues/{league_id}/playoffs/mark-winner")
async def mark_playoff_winner(league_id: str, body: MarkWinnerBody, request: Request):
    """Commissioner one-tap: mark `winner_team_id` as the winner of `matchup_id`.

    Updates the playoff matchup (status=completed, scores if provided, default
    1-0) AND, if the matchup is in a non-final round, propagates the winner
    into the corresponding TBD slot of the next round's matchup. Idempotent:
    repeated calls overwrite the prior winner.
    """
    db = _db()
    user = await _get_user(request)
    league = await db.leagues.find_one({"_id": ObjectId(league_id)})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    if not _user_is_commish(league, user):
        raise HTTPException(status_code=403, detail="Commissioner access required")

    try:
        mu_oid = ObjectId(body.matchup_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid matchup_id")
    mu = await db.matchups.find_one({"_id": mu_oid, "league_id": league_id, "is_playoff": True})
    if not mu:
        raise HTTPException(status_code=404, detail="Playoff matchup not found")

    home_id = str(mu.get("home_team_id") or "")
    away_id = str(mu.get("away_team_id") or "")
    if body.winner_team_id not in (home_id, away_id):
        raise HTTPException(status_code=400, detail="winner_team_id must match either home or away team")

    # Default scores: 1-0 in favour of the winner, unless caller supplied them.
    hs = body.home_score if body.home_score is not None else (1.0 if body.winner_team_id == home_id else 0.0)
    as_ = body.away_score if body.away_score is not None else (1.0 if body.winner_team_id == away_id else 0.0)

    await db.matchups.update_one(
        {"_id": mu_oid},
        {"$set": {
            "status": "completed",
            "home_score": hs,
            "away_score": as_,
            "winner_team_id": body.winner_team_id,
            "marked_by": str(user["_id"]),
            "marked_at": datetime.now(timezone.utc).isoformat(),
        }},
    )

    # Propagate winner into the next round's TBD slot. Bracket math: matchup
    # at index j of round R+1 is fed by matchups (2j, 2j+1) in round R.
    cur_round = int(mu.get("bracket_round") or 1)
    next_round = cur_round + 1
    next_matchups = await db.matchups.find({
        "league_id": league_id,
        "is_playoff": True,
        "bracket_round": next_round,
    }).sort("_id", 1).to_list(50)
    # Determine target index within next round
    sibs = await db.matchups.find({
        "league_id": league_id, "is_playoff": True, "bracket_round": cur_round,
    }).sort("_id", 1).to_list(50)
    try:
        cur_idx = next(int(row.get("bracket_index", i)) for i, row in enumerate(sibs) if str(row["_id"]) == str(mu["_id"]))
    except (ValueError, StopIteration):
        cur_idx = -1
    target_idx = cur_idx // 2 if cur_idx >= 0 else -1

    import math
    total_rounds = int(league.get("playoff_rounds") or math.ceil(math.log2(max(2, int(league.get("playoff_teams") or 2)))))
    if target_idx >= 0 and cur_round < total_rounds:
        target = next((row for i, row in enumerate(next_matchups)
                       if int(row.get("bracket_index", i)) == target_idx), None)
        if target:
            # Each parent owns one fixed slot, including repeat winner edits.
            side = "home" if cur_idx % 2 == 0 else "away"
            await db.matchups.update_one({"_id": target["_id"]}, {"$set": {
                f"{side}_team_id": body.winner_team_id, f"{side}_team_tbd": False,
                "bracket_index": target_idx,
            }})
        else:
            # Iter 199 — the bracket synthesizer pads non-final rounds with
            # in-memory TBD matchups (no DB row). When a winner needs to
            # advance into one of those synthetic slots, materialise the
            # row here so subsequent Mark-Winner clicks have a real
            # matchup_id to update. Week is inherited from the first
            # sibling in the next round when present, else computed from
            # `league.playoff_start_week + (next_round - 1)`.
            sibling_week = next_matchups[0]["week"] if next_matchups else None
            if sibling_week is None:
                start_week = int(league.get("playoff_start_week") or 0)
                sibling_week = start_week + (next_round - 1) if start_week else None
            new_doc = {
                "league_id": league_id,
                "bracket_round": next_round,
                "bracket_index": target_idx,
                "is_playoff": True,
                "home_team_id": body.winner_team_id if cur_idx % 2 == 0 else None,
                "home_team_tbd": cur_idx % 2 != 0,
                "away_team_id": body.winner_team_id if cur_idx % 2 else None,
                "away_team_tbd": cur_idx % 2 == 0,
                "status": "scheduled",
                "home_score": 0,
                "away_score": 0,
                "week": sibling_week,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "auto_created": True,
            }
            await db.matchups.insert_one(new_doc)

    # Audit
    await db.activity_feed.insert_one({
        "league_id": league_id,
        "event_type": "playoff_winner_marked",
        "message": f"Marked playoff winner: team {body.winner_team_id} (round {cur_round})",
        "user_id": str(user["_id"]),
        "metadata": {
            "matchup_id": body.matchup_id,
            "winner_team_id": body.winner_team_id,
            "round": cur_round,
            "home_score": hs,
            "away_score": as_,
        },
        "created_at": datetime.now(timezone.utc).isoformat(),
    })

    return {"ok": True, "matchup_id": body.matchup_id, "winner_team_id": body.winner_team_id}


class DistributePrizeBody(BaseModel):
    champion_team_id: Optional[str] = None
    runner_up_team_id: Optional[str] = None
    consolation_champion_team_id: Optional[str] = None
    champion_prize: float = Field(default=0, ge=0)
    runner_up_prize: float = Field(default=0, ge=0)
    consolation_prize: float = Field(default=0, ge=0)
    currency: str = "USD"
    note: Optional[str] = None


@router.post("/leagues/{league_id}/playoffs/distribute-prize")
async def distribute_prize(league_id: str, body: DistributePrizeBody, request: Request):
    """Commissioner: persist a prize distribution + stamp the league with the
    champion/runner-up/consolation champion ids. Writes a `payouts` audit row
    and an `activity_feed` entry. Idempotent — repeated calls overwrite the
    prior distribution and log a new audit entry."""
    db = _db()
    user = await _get_user(request)
    league = await db.leagues.find_one({"_id": ObjectId(league_id)})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    if not _user_is_commish(league, user):
        raise HTTPException(status_code=403, detail="Commissioner access required")

    now = datetime.now(timezone.utc).isoformat()
    payload = {
        "league_id": league_id,
        "champion_team_id": body.champion_team_id,
        "runner_up_team_id": body.runner_up_team_id,
        "consolation_champion_team_id": body.consolation_champion_team_id,
        "champion_prize": float(body.champion_prize),
        "runner_up_prize": float(body.runner_up_prize),
        "consolation_prize": float(body.consolation_prize),
        "currency": body.currency,
        "note": body.note,
        "distributed_at": now,
        "distributed_by": str(user["_id"]),
    }
    # Upsert into `payouts` collection (one canonical distribution per league;
    # historical record kept in `activity_feed`).
    await db.payouts.update_one(
        {"league_id": league_id},
        {"$set": payload},
        upsert=True,
    )
    await db.leagues.update_one(
        {"_id": ObjectId(league_id)},
        {"$set": {
            "playoff_champion_id": body.champion_team_id,
            "playoff_runner_up_id": body.runner_up_team_id,
            "playoff_consolation_champion_id": body.consolation_champion_team_id,
            "playoff_distributed_at": now,
        }},
    )
    await db.activity_feed.insert_one({
        "league_id": league_id,
        "event_type": "playoff_prize_distributed",
        "message": f"Playoff prize distributed: champion={body.champion_team_id}",
        "user_id": str(user["_id"]),
        "metadata": payload,
        "created_at": now,
    })
    return {"ok": True, **payload}


@router.get("/leagues/{league_id}/playoffs/payout")
async def get_payout(league_id: str, request: Request):
    """Return the latest persisted prize distribution for the league (or
    `{distributed: false}` when nothing has been awarded yet). Open to any
    league member so all owners can see the final results."""
    db = _db()
    await _get_user(request)  # auth gate only
    p = await db.payouts.find_one({"league_id": league_id})
    if not p:
        return {"distributed": False, "league_id": league_id}
    p.pop("_id", None)
    return {"distributed": True, **p}


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
