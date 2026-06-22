"""
Iter 205 — User Reports / Flagging.

Public-facing report submission endpoint. Any authenticated user can
report another user (chat misconduct, offensive username/team name,
suspicious trades, etc.). Reports land in `db.user_reports` for the
platform admin moderation queue (see routes/admin_platform.py).
"""
from datetime import datetime, timezone

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Request

router = APIRouter()
_deps: dict = {}

VALID_REPORT_CATEGORIES = {
    "harassment",
    "spam",
    "offensive_username",
    "offensive_team_name",
    "offensive_avatar",
    "trade_collusion",
    "cheating",
    "other",
}


def setup(deps: dict) -> None:
    _deps.update(deps)


def _db():
    return _deps["db"]


async def _get_user(request):
    return await _deps["get_current_user"](request)


@router.post("/reports")
async def submit_user_report(request: Request):
    """Any logged-in user can submit a report against another user.
    Rate-limited by reporter_id + target_user_id pair: only one OPEN
    report per pair at a time to prevent spam-reporting.

    Body:
      {
        "target_user_id": "<user_id>",     # required
        "category": "harassment"|...,      # required
        "reason": "...",                    # required (<= 2000 chars)
        "target_team_id": "<team_id>?",
        "league_id": "<league_id>?",
        "context_url": "...?"               # e.g. /chat#msg-123
      }
    """
    reporter = await _get_user(request)
    payload = await request.json()
    target_user_id = (payload.get("target_user_id") or "").strip()
    category = (payload.get("category") or "").strip()
    reason = (payload.get("reason") or "").strip()[:2000]

    if not target_user_id:
        raise HTTPException(status_code=400, detail="target_user_id is required")
    if category not in VALID_REPORT_CATEGORIES:
        raise HTTPException(
            status_code=400,
            detail=f"category must be one of: {sorted(VALID_REPORT_CATEGORIES)}",
        )
    if not reason:
        raise HTTPException(status_code=400, detail="reason is required")
    if str(reporter["_id"]) == target_user_id:
        raise HTTPException(status_code=400, detail="You cannot report yourself")

    # Hydrate target email + verify the user exists
    try:
        target = await _db().users.find_one(
            {"_id": ObjectId(target_user_id)}, {"email": 1, "username": 1}
        )
    except Exception:
        target = None
    if not target:
        raise HTTPException(status_code=404, detail="Target user not found")

    # Dedupe: one open report per (reporter, target) pair
    existing = await _db().user_reports.find_one({
        "reporter_id": str(reporter["_id"]),
        "target_user_id": target_user_id,
        "status": "open",
    })
    if existing:
        return {
            "ok": True,
            "report_id": str(existing["_id"]),
            "deduped": True,
            "message": "You already have an open report against this user.",
        }

    doc = {
        "reporter_id": str(reporter["_id"]),
        "reporter_email": reporter.get("email"),
        "target_user_id": target_user_id,
        "target_user_email": target.get("email"),
        "target_team_id": payload.get("target_team_id"),
        "league_id": payload.get("league_id"),
        "category": category,
        "reason": reason,
        "context_url": payload.get("context_url"),
        "status": "open",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    res = await _db().user_reports.insert_one(doc)
    return {"ok": True, "report_id": str(res.inserted_id), "deduped": False}


@router.get("/reports/mine")
async def my_submitted_reports(request: Request):
    """Lets a user see the reports THEY have filed (for transparency)."""
    user = await _get_user(request)
    rows = await _db().user_reports.find(
        {"reporter_id": str(user["_id"])}
    ).sort("created_at", -1).to_list(100)
    out = []
    for r in rows:
        out.append({
            "report_id": str(r["_id"]),
            "target_user_email": r.get("target_user_email"),
            "category": r.get("category"),
            "status": r.get("status"),
            "created_at": r.get("created_at"),
            "resolved_at": r.get("resolved_at"),
        })
    return {"reports": out}
