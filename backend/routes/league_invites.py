"""League invites, public discovery, email invites + recalculate-stats.

Extracted from server.py during Iter 112 server-extraction sweep. Endpoints,
payloads and auth are identical to the pre-extraction implementation.
"""
import base64
import io
import os
import secrets
from datetime import datetime, timezone
from typing import Optional, List

import qrcode
from bson import ObjectId
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

router = APIRouter()
_deps: dict = {}


def setup(deps: dict) -> None:
    _deps.update(deps)


# ─── Pydantic ────────────────────────────────────────────────
class LeagueInviteResponse(BaseModel):
    invite_code: str
    invite_url: str
    qr_code_base64: str


class JoinByInviteRequest(BaseModel):
    invite_code: str
    team_name: str


class EmailInviteRequest(BaseModel):
    league_id: str
    emails: list[str]


class JoinPublicLeagueRequest(BaseModel):
    team_name: str = Field(..., min_length=1, max_length=80)


def _frontend_base() -> str:
    return os.environ.get(
        "FRONTEND_URL",
        "https://dynasty-preview.preview.emergentagent.com",
    )


# ─── Endpoints ───────────────────────────────────────────────
@router.get("/leagues/{league_id}/invite")
async def get_league_invite(league_id: str, request: Request):
    db = _deps["db"]
    get_current_user = _deps["get_current_user"]
    await get_current_user(request)
    league = await db.leagues.find_one({"_id": ObjectId(league_id)})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")

    invite_code = league.get("invite_code")
    if not invite_code:
        invite_code = secrets.token_urlsafe(8)
        await db.leagues.update_one({"_id": ObjectId(league_id)}, {"$set": {"invite_code": invite_code}})

    invite_url = f"{_frontend_base()}/join/{invite_code}"

    qr = qrcode.QRCode(version=1, box_size=8, border=2)
    qr.add_data(invite_url)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="#00D2FF", back_color="#0A0A0A")
    buffer = io.BytesIO()
    qr_img.save(buffer, format="PNG")
    qr_base64 = base64.b64encode(buffer.getvalue()).decode()

    return LeagueInviteResponse(
        invite_code=invite_code,
        invite_url=invite_url,
        qr_code_base64=qr_base64,
    )


@router.get("/leagues/{league_id}/invite/qr")
async def get_invite_qr_image(league_id: str):
    db = _deps["db"]
    league = await db.leagues.find_one({"_id": ObjectId(league_id)})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")

    invite_code = league.get("invite_code", "")
    invite_url = f"{_frontend_base()}/join/{invite_code}"

    qr = qrcode.QRCode(version=1, box_size=10, border=3)
    qr.add_data(invite_url)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="#00D2FF", back_color="#0A0A0A")
    buffer = io.BytesIO()
    qr_img.save(buffer, format="PNG")
    buffer.seek(0)
    return StreamingResponse(buffer, media_type="image/png")


@router.post("/leagues/{league_id}/recalculate-stats")
async def recalculate_league_stats(league_id: str, request: Request):
    """Commissioner-only: re-derive every team's wins/losses/ties/PF/PA from
    `matchups` where status='completed'.
    """
    db = _deps["db"]
    get_current_user = _deps["get_current_user"]
    _safe_object_id = _deps["_safe_object_id"]
    user = await get_current_user(request)
    league = await db.leagues.find_one({"_id": _safe_object_id(league_id, "league_id")})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    is_comm = league["commissioner_id"] == user["_id"]
    co_comms = league.get("co_commissioners", []) or []
    if not (is_comm or user["_id"] in co_comms):
        raise HTTPException(status_code=403, detail="Only commissioners can recalculate league stats")

    teams = await db.teams.find({"league_id": league_id}).to_list(100)
    completed = await db.matchups.find({"league_id": league_id, "status": "completed"}).to_list(2000)

    agg: dict = {str(t["_id"]): {"wins": 0, "losses": 0, "ties": 0,
                                  "points_for": 0.0, "points_against": 0.0}
                 for t in teams}
    for mm in completed:
        h, a = mm.get("home_team_id"), mm.get("away_team_id")
        hs = float(mm.get("home_score", 0) or 0)
        as_ = float(mm.get("away_score", 0) or 0)
        winner = mm.get("winner")
        if h in agg:
            agg[h]["points_for"] += hs
            agg[h]["points_against"] += as_
            if winner == h:
                agg[h]["wins"] += 1
            elif winner == a:
                agg[h]["losses"] += 1
            else:
                agg[h]["ties"] += 1
        if a in agg:
            agg[a]["points_for"] += as_
            agg[a]["points_against"] += hs
            if winner == a:
                agg[a]["wins"] += 1
            elif winner == h:
                agg[a]["losses"] += 1
            else:
                agg[a]["ties"] += 1

    diffs = []
    for tid, vals in agg.items():
        old = next((t for t in teams if str(t["_id"]) == tid), None)
        if not old:
            continue
        before = {
            "wins": old.get("wins", 0), "losses": old.get("losses", 0),
            "ties": old.get("ties", 0),
            "points_for": round(old.get("points_for", 0.0) or 0.0, 2),
            "points_against": round(old.get("points_against", 0.0) or 0.0, 2),
        }
        after = {
            "wins": vals["wins"], "losses": vals["losses"], "ties": vals["ties"],
            "points_for": round(vals["points_for"], 2),
            "points_against": round(vals["points_against"], 2),
        }
        if before != after:
            await db.teams.update_one({"_id": ObjectId(tid)}, {"$set": after})
            diffs.append({"team_id": tid, "team_name": old.get("name"),
                          "before": before, "after": after})

    await db.audit_log.insert_one({
        "league_id": league_id,
        "actor_id": user["_id"],
        "actor_name": user.get("name", user.get("email", "Unknown")),
        "action": "league_stats_recalculated",
        "role": "commissioner" if is_comm else "co_commissioner",
        "diff": {"completed_matchups": len(completed),
                 "teams_changed": len(diffs)},
        "created_at": datetime.now(timezone.utc),
    })

    return {
        "league_id": league_id,
        "completed_matchups": len(completed),
        "teams_changed": len(diffs),
        "diffs": diffs,
    }


@router.post("/leagues/join-by-invite")
async def join_league_by_invite(input: JoinByInviteRequest, request: Request):
    db = _deps["db"]
    get_current_user = _deps["get_current_user"]
    log_activity = _deps["log_activity"]
    user = await get_current_user(request)

    league = await db.leagues.find_one({"invite_code": input.invite_code})
    if not league:
        raise HTTPException(status_code=404, detail="Invalid invite code")

    league_id = str(league["_id"])

    if league.get("current_teams", 0) >= league["max_teams"]:
        raise HTTPException(status_code=400, detail="League is full")

    existing = await db.teams.find_one({"league_id": league_id, "owner_id": user["_id"]})
    if existing:
        raise HTTPException(status_code=400, detail="You already have a team in this league")

    team_doc = {
        "name": input.team_name,
        "league_id": league_id,
        "owner_id": user["_id"],
        "owner_name": user["name"],
        "roster": [],
        "salary_used": 0.0,
        "wins": 0, "losses": 0, "ties": 0,
        "points_for": 0.0, "points_against": 0.0,
        "created_at": datetime.now(timezone.utc)
    }
    result = await db.teams.insert_one(team_doc)
    await db.leagues.update_one({"_id": ObjectId(league_id)}, {"$inc": {"current_teams": 1}})

    await log_activity(league_id, "team_joined", f"{user['name']} joined with team '{input.team_name}'", user["_id"])

    return {
        "message": f"Joined {league['name']}!",
        "team_id": str(result.inserted_id),
        "league_id": league_id,
        "league_name": league["name"],
    }


@router.get("/public-leagues")
async def discover_public_leagues(request: Request, q: Optional[str] = None, sport: Optional[str] = None, format: Optional[str] = None):
    db = _deps["db"]
    get_current_user = _deps["get_current_user"]
    user_id = None
    try:
        user = await get_current_user(request)
        user_id = user["_id"]
    except HTTPException:
        user_id = None

    query: dict = {"is_private": {"$ne": True}}
    if sport:
        query["sport"] = sport
    if format:
        query["format"] = format
    if q:
        query["name"] = {"$regex": q, "$options": "i"}

    leagues = await db.leagues.find(query).sort("created_at", -1).to_list(200)

    user_league_ids = set()
    if user_id:
        user_teams = await db.teams.find({"owner_id": user_id}, {"league_id": 1}).to_list(500)
        user_league_ids = {t["league_id"] for t in user_teams}

    out = []
    for league in leagues:
        lid = str(league["_id"])
        out.append({
            "id": lid,
            "name": league.get("name"),
            "sport": league.get("sport", "nhl"),
            "format": league.get("format"),
            "scoring_format": league.get("scoring_format"),
            "max_teams": league.get("max_teams"),
            "current_teams": league.get("current_teams", 0),
            "open_spots": max(0, (league.get("max_teams", 0) or 0) - (league.get("current_teams", 0) or 0)),
            "commissioner_name": league.get("commissioner_name"),
            "salary_cap_enabled": bool(league.get("salary_cap_enabled")),
            "salary_cap": league.get("salary_cap"),
            "entry_fee": league.get("entry_fee"),
            "keepers_allowed": league.get("keepers_allowed", 0),
            "is_full": (league.get("current_teams", 0) >= (league.get("max_teams", 0) or 0)),
            "already_member": lid in user_league_ids,
            "created_at": league.get("created_at"),
        })
    return {"leagues": out, "total": len(out)}


@router.post("/leagues/{league_id}/join-public")
async def join_public_league(league_id: str, payload: JoinPublicLeagueRequest, request: Request):
    db = _deps["db"]
    get_current_user = _deps["get_current_user"]
    log_activity = _deps["log_activity"]
    _safe_object_id = _deps["_safe_object_id"]
    user = await get_current_user(request)
    league = await db.leagues.find_one({"_id": _safe_object_id(league_id, "league_id")})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    if league.get("is_private"):
        raise HTTPException(status_code=403, detail="This league is private — invite only")
    if league.get("current_teams", 0) >= league["max_teams"]:
        raise HTTPException(status_code=400, detail="League is full")

    existing = await db.teams.find_one({"league_id": league_id, "owner_id": user["_id"]})
    if existing:
        raise HTTPException(status_code=400, detail="You already have a team in this league")

    team_doc = {
        "name": payload.team_name.strip(),
        "league_id": league_id,
        "owner_id": user["_id"],
        "owner_name": user["name"],
        "roster": [],
        "salary_used": 0.0,
        "wins": 0, "losses": 0, "ties": 0,
        "points_for": 0.0, "points_against": 0.0,
        "created_at": datetime.now(timezone.utc),
    }
    result = await db.teams.insert_one(team_doc)
    await db.leagues.update_one({"_id": ObjectId(league_id)}, {"$inc": {"current_teams": 1}})
    await log_activity(league_id, "team_joined",
                       f"{user['name']} joined with team '{payload.team_name}'", user["_id"])
    return {
        "message": f"Joined {league['name']}!",
        "team_id": str(result.inserted_id),
        "league_id": league_id,
        "league_name": league["name"],
    }


@router.post("/leagues/{league_id}/invite/email")
async def send_email_invites(league_id: str, input: EmailInviteRequest, request: Request):
    db = _deps["db"]
    get_current_user = _deps["get_current_user"]
    send_sendgrid_email = _deps["send_sendgrid_email"]
    logger = _deps["logger"]
    user = await get_current_user(request)
    league = await db.leagues.find_one({"_id": ObjectId(league_id)})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    if league["commissioner_id"] != user["_id"]:
        raise HTTPException(status_code=403, detail="Only commissioner can send invites")

    invite_code = league.get("invite_code", "")
    invite_url = f"{_frontend_base()}/join/{invite_code}"

    subject = f"You're invited to join '{league['name']}' on Dynasty Dreams"
    html_template = f"""
    <div style="font-family: -apple-system, Segoe UI, Roboto, sans-serif; max-width: 560px; margin: auto; padding: 24px; background: #0b1020; color: #e6edf7; border-radius: 12px;">
      <h1 style="margin:0 0 8px; font-size: 22px; color:#7cf9d0;">Dynasty Dreams</h1>
      <p style="margin:0 0 16px; color:#9aa6c2;">Fantasy sports, re-imagined.</p>
      <h2 style="font-size:18px; margin:12px 0;">{user['name']} invited you to <span style="color:#7cf9d0;">{league['name']}</span></h2>
      <p style="color:#c9d3ea; line-height:1.5;">Click the button below to accept your invite, create your team, and join the league.</p>
      <p style="text-align:center; margin: 24px 0;">
        <a href="{invite_url}" style="background:#7cf9d0; color:#0b1020; padding: 12px 24px; border-radius: 999px; text-decoration:none; font-weight:700;">Join League</a>
      </p>
      <p style="color:#7a88a8; font-size:12px;">Or paste this link into your browser:<br/><a href="{invite_url}" style="color:#7cf9d0;">{invite_url}</a></p>
      <p style="color:#7a88a8; font-size:12px;">Invite code: <code>{invite_code}</code></p>
    </div>
    """

    results = []
    for email in input.emails:
        send_result = send_sendgrid_email(email, subject, html_template)
        await db.league_invites.update_one(
            {"league_id": league_id, "email": email.lower()},
            {"$set": {
                "league_id": league_id,
                "league_name": league["name"],
                "email": email.lower(),
                "invite_code": invite_code,
                "invite_url": invite_url,
                "invited_by": user["_id"],
                "status": send_result.get("status", "sent"),
                "provider_response": {k: v for k, v in send_result.items() if k != "to"},
                "sent_at": datetime.now(timezone.utc).isoformat()
            }},
            upsert=True
        )
        results.append(send_result)

    sent_count = sum(1 for r in results if r.get("status") == "sent")
    mocked_count = sum(1 for r in results if r.get("status") == "mocked")
    error_count = sum(1 for r in results if r.get("status") == "error")
    logger.info(
        f"Invites for '{league['name']}': sent={sent_count}, mocked={mocked_count}, errors={error_count}"
    )
    return {
        "message": f"Invites processed for {len(input.emails)} email(s)",
        "invite_url": invite_url,
        "sent": sent_count,
        "mocked": mocked_count,
        "errors": error_count,
        "results": results,
    }


# ── Iter 193 — Pending-team bulk invite roster ──────────────────
# Returns each team in the league with its `is_pending` status plus
# the most recent invite (if any) keyed by an `email` field stashed
# on the team doc. The commissioner UI consumes this to render a
# table with per-row email input + "Send" pill.
@router.get("/leagues/{league_id}/pending-team-invites")
async def get_pending_team_invites(league_id: str, request: Request):
    db = _deps["db"]
    get_current_user = _deps["get_current_user"]
    user = await get_current_user(request)
    league = await db.leagues.find_one({"_id": ObjectId(league_id)})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    if league.get("commissioner_id") != user["_id"]:
        raise HTTPException(status_code=403, detail="Commissioner access required")

    teams = await db.teams.find({"league_id": league_id}).sort("draft_position", 1).to_list(64)

    # Iter 229b — Auto-seed missing slots up to league.max_teams so the
    # Teams & Owners panel always renders the full seat chart (e.g. 1
    # claimed + 23 Open Slots for a 24-team league). Each stub has a
    # real ObjectId so the commissioner can mint invites against it
    # immediately. Idempotent: only inserts rows for `draft_position`
    # values that aren't already represented.
    max_teams = int(league.get("max_teams") or 0)
    if max_teams > 0 and len(teams) < max_teams:
        from datetime import datetime, timezone
        used_positions = {
            t.get("draft_position") for t in teams if t.get("draft_position") is not None
        }
        # Compute the highest assigned position so we can extend cleanly.
        next_pos = 1
        new_docs = []
        for slot_n in range(1, max_teams + 1):
            if slot_n in used_positions:
                continue
            if len(teams) + len(new_docs) >= max_teams:
                break
            new_docs.append({
                "league_id": league_id,
                "name": None,
                "abbreviation": None,
                "owner_id": None,
                "owner_name": None,
                "is_pending": True,
                "draft_position": slot_n,
                "roster": [],
                "lineup": {},
                "created_at": datetime.now(timezone.utc),
                "created_by_auto_seed": True,
            })
        if new_docs:
            res = await db.teams.insert_many(new_docs)
            for doc, _id in zip(new_docs, res.inserted_ids):
                doc["_id"] = _id
                teams.append(doc)
            teams.sort(key=lambda t: t.get("draft_position") or 9999)

    # Pull all invites for the league in one query.
    invites = await db.league_invites.find({"league_id": league_id}).to_list(256)
    invites_by_email: dict = {}
    for inv in invites:
        em = (inv.get("email") or "").lower()
        if em:
            invites_by_email[em] = inv

    out = []
    for t in teams:
        invite_email = (t.get("invite_email") or "").lower() or None
        inv = invites_by_email.get(invite_email) if invite_email else None
        status = "no_email"
        if t.get("owner_id"):
            status = "accepted"
        elif inv:
            status = inv.get("status") or "sent"
        elif invite_email:
            status = "pending"
        out.append({
            "team_id": str(t["_id"]),
            "team_name": t.get("name"),
            "abbreviation": t.get("abbreviation"),
            "draft_position": t.get("draft_position"),
            "is_pending": bool(t.get("is_pending")),
            "owner_id": t.get("owner_id"),
            "owner_name": t.get("owner_name"),
            "invite_email": invite_email,
            "status": status,
            "sent_at": inv.get("sent_at") if inv else None,
        })
    return {
        "league_id": league_id,
        "league_name": league.get("name"),
        "invite_code": league.get("invite_code"),
        "teams": out,
    }


class BulkTeamInviteRow(BaseModel):
    team_id: str
    email: str


class BulkTeamInviteRequest(BaseModel):
    rows: List[BulkTeamInviteRow]


@router.post("/leagues/{league_id}/pending-team-invites/bulk")
async def send_bulk_team_invites(league_id: str, payload: BulkTeamInviteRequest, request: Request):
    """Iter 193 — Bulk-invite owners to a pre-seeded set of pending
    teams. We stash the email on the team doc (`invite_email`) and then
    re-use the existing `send_email_invites` logic per row so the audit
    trail + SendGrid path stay unified."""
    db = _deps["db"]
    get_current_user = _deps["get_current_user"]
    send_sendgrid_email = _deps["send_sendgrid_email"]
    logger = _deps["logger"]
    user = await get_current_user(request)
    league = await db.leagues.find_one({"_id": ObjectId(league_id)})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    if league.get("commissioner_id") != user["_id"]:
        raise HTTPException(status_code=403, detail="Commissioner access required")

    invite_code = league.get("invite_code", "")
    invite_url = f"{_frontend_base()}/join/{invite_code}"
    subject = f"You're invited to manage a team in '{league['name']}' on Dynasty Dreams"

    sent = 0
    errors: list[dict] = []
    for row in payload.rows:
        if not row.email or "@" not in row.email:
            errors.append({"team_id": row.team_id, "error": "invalid_email"})
            continue
        # Find the team
        try:
            team = await db.teams.find_one({"_id": ObjectId(row.team_id), "league_id": league_id})
        except Exception:
            team = None
        if not team:
            errors.append({"team_id": row.team_id, "error": "team_not_found"})
            continue
        team_name = team.get("name") or "your team"
        html_template = f"""
        <div style="font-family: -apple-system, Segoe UI, Roboto, sans-serif; max-width: 560px; margin: auto; padding: 24px; background: #0b1020; color: #e6edf7; border-radius: 12px;">
          <h1 style="margin:0 0 8px; font-size: 22px; color:#7cf9d0;">Dynasty Dreams</h1>
          <h2 style="font-size:18px; margin:12px 0;">{user['name']} reserved <span style="color:#7cf9d0;">{team_name}</span> for you in {league['name']}</h2>
          <p style="color:#c9d3ea; line-height:1.5;">Click below to claim the team, create your account, and prep for the entry draft.</p>
          <p style="text-align:center; margin: 24px 0;">
            <a href="{invite_url}" style="background:#7cf9d0; color:#0b1020; padding: 12px 24px; border-radius: 999px; text-decoration:none; font-weight:700;">Claim {team_name}</a>
          </p>
          <p style="color:#7a88a8; font-size:12px;">Or paste this link into your browser:<br/><a href="{invite_url}" style="color:#7cf9d0;">{invite_url}</a></p>
          <p style="color:#7a88a8; font-size:12px;">Invite code: <code>{invite_code}</code></p>
        </div>
        """
        send_result = send_sendgrid_email(row.email, subject, html_template)
        # Stash the per-team email + persist invite doc.
        await db.teams.update_one(
            {"_id": team["_id"]},
            {"$set": {"invite_email": row.email.lower()}},
        )
        await db.league_invites.update_one(
            {"league_id": league_id, "email": row.email.lower()},
            {"$set": {
                "league_id": league_id,
                "league_name": league["name"],
                "team_id": row.team_id,
                "team_name": team_name,
                "email": row.email.lower(),
                "invite_code": invite_code,
                "invite_url": invite_url,
                "invited_by": user["_id"],
                "status": send_result.get("status", "sent"),
                "provider_response": {k: v for k, v in send_result.items() if k != "to"},
                "sent_at": datetime.now(timezone.utc).isoformat(),
            }},
            upsert=True,
        )
        if send_result.get("status") in ("sent", "mocked"):
            sent += 1
        else:
            errors.append({"team_id": row.team_id, "error": send_result.get("status", "send_failed")})

    logger.info(
        f"Bulk team invites for league {league_id}: sent={sent} errors={len(errors)}"
    )
    return {"sent": sent, "errors": errors}
