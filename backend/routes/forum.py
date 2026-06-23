"""
Iter 217 — Forum feature.

Threads + posts, scoped league-wide (a thread belongs to a league),
with admin/commissioner delete and seamless integration with the
iter 205 user-reports flow via `content_type="forum_post"`.

Collections:
  • forum_threads — { league_id, title, author_id, author_email,
                       created_at, post_count, last_post_at, pinned,
                       locked }
  • forum_posts   — { thread_id, league_id, author_id, author_email,
                       body, created_at, edited_at, deleted_at,
                       deleted_by_admin }
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Request, Query

router = APIRouter(prefix="/forum", tags=["forum"])
_deps: dict = {}


def setup(deps: dict) -> None:
    _deps.update(deps)


def _db():
    return _deps["db"]


def _iso(dt):
    if not dt:
        return None
    if isinstance(dt, str):
        return dt
    return dt.isoformat() if hasattr(dt, "isoformat") else str(dt)


async def _require_user(request: Request) -> dict:
    user = await _deps["get_current_user"](request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    if user.get("_impersonation_mode") == "read_only":
        raise HTTPException(status_code=403, detail="Read-only impersonation — exit view-as to post")
    return user


async def _check_league_member(user: dict, league_id: str) -> None:
    """Ensure the caller has a team in the league or is the commish/admin."""
    if user.get("role") == "admin":
        return
    db = _db()
    try:
        lg = await db.leagues.find_one({"_id": ObjectId(league_id)})
    except Exception:
        lg = None
    if not lg:
        raise HTTPException(status_code=404, detail="League not found")
    uid = str(user["_id"])
    if str(lg.get("commissioner_id")) == uid or uid in (lg.get("co_commissioners") or []):
        return
    has_team = await db.teams.find_one({"league_id": league_id, "owner_id": uid})
    if not has_team:
        raise HTTPException(status_code=403, detail="Not a member of this league")


# ─── Threads ────────────────────────────────────────────────────────
@router.get("/threads")
async def list_threads(
    request: Request,
    league_id: str = Query(...),
    limit: int = Query(50, ge=1, le=100),
    skip: int = Query(0, ge=0),
):
    user = await _require_user(request)
    await _check_league_member(user, league_id)
    db = _db()
    total = await db.forum_threads.count_documents({"league_id": league_id})
    rows = await db.forum_threads.find({"league_id": league_id}).sort(
        [("pinned", -1), ("last_post_at", -1)]
    ).skip(skip).limit(limit).to_list(limit)
    return {
        "total": total,
        "threads": [{
            "id": str(t["_id"]),
            "league_id": t.get("league_id"),
            "title": t.get("title"),
            "author_id": t.get("author_id"),
            "author_email": t.get("author_email"),
            "created_at": _iso(t.get("created_at")),
            "last_post_at": _iso(t.get("last_post_at")),
            "post_count": int(t.get("post_count") or 0),
            "pinned": bool(t.get("pinned")),
            "locked": bool(t.get("locked")),
        } for t in rows],
    }


@router.post("/threads")
async def create_thread(request: Request):
    user = await _require_user(request)
    body = await request.json()
    league_id = (body.get("league_id") or "").strip()
    title = (body.get("title") or "").strip()
    first_post_body = (body.get("body") or "").strip()
    if not (league_id and title and first_post_body):
        raise HTTPException(status_code=400, detail="league_id, title, and body are required")
    if len(title) > 200:
        raise HTTPException(status_code=400, detail="title too long")
    await _check_league_member(user, league_id)
    now = datetime.now(timezone.utc)
    thread_doc = {
        "league_id": league_id,
        "title": title,
        "author_id": str(user["_id"]),
        "author_email": user.get("email"),
        "created_at": now.isoformat(),
        "last_post_at": now.isoformat(),
        "post_count": 1,
        "pinned": False, "locked": False,
    }
    res = await _db().forum_threads.insert_one(thread_doc)
    # First post
    await _db().forum_posts.insert_one({
        "thread_id": str(res.inserted_id),
        "league_id": league_id,
        "author_id": str(user["_id"]),
        "author_email": user.get("email"),
        "body": first_post_body,
        "created_at": now.isoformat(),
    })
    return {"ok": True, "thread_id": str(res.inserted_id)}


@router.get("/threads/{thread_id}")
async def get_thread(thread_id: str, request: Request):
    user = await _require_user(request)
    try:
        t = await _db().forum_threads.find_one({"_id": ObjectId(thread_id)})
    except Exception:
        t = None
    if not t:
        raise HTTPException(status_code=404, detail="Thread not found")
    await _check_league_member(user, t["league_id"])
    return {
        "id": str(t["_id"]),
        "league_id": t.get("league_id"),
        "title": t.get("title"),
        "author_id": t.get("author_id"),
        "author_email": t.get("author_email"),
        "created_at": _iso(t.get("created_at")),
        "last_post_at": _iso(t.get("last_post_at")),
        "post_count": int(t.get("post_count") or 0),
        "pinned": bool(t.get("pinned")),
        "locked": bool(t.get("locked")),
    }


@router.delete("/threads/{thread_id}")
async def delete_thread(thread_id: str, request: Request):
    user = await _require_user(request)
    try:
        t = await _db().forum_threads.find_one({"_id": ObjectId(thread_id)})
    except Exception:
        t = None
    if not t:
        raise HTTPException(status_code=404, detail="Thread not found")
    # Admin or thread author may delete
    if user.get("role") != "admin" and str(user["_id"]) != t.get("author_id"):
        raise HTTPException(status_code=403, detail="Only admin or thread author can delete")
    await _db().forum_threads.delete_one({"_id": t["_id"]})
    await _db().forum_posts.delete_many({"thread_id": str(t["_id"])})
    return {"ok": True}


# ─── Posts ──────────────────────────────────────────────────────────
@router.get("/threads/{thread_id}/posts")
async def list_posts(thread_id: str, request: Request,
                      limit: int = Query(100, ge=1, le=500)):
    user = await _require_user(request)
    try:
        t = await _db().forum_threads.find_one({"_id": ObjectId(thread_id)})
    except Exception:
        t = None
    if not t:
        raise HTTPException(status_code=404, detail="Thread not found")
    await _check_league_member(user, t["league_id"])
    rows = await _db().forum_posts.find({"thread_id": thread_id}).sort(
        "created_at", 1
    ).limit(limit).to_list(limit)
    return {
        "posts": [{
            "id": str(p["_id"]),
            "thread_id": p.get("thread_id"),
            "author_id": p.get("author_id"),
            "author_email": p.get("author_email"),
            "body": "[deleted by admin]" if p.get("deleted_at") else p.get("body"),
            "created_at": _iso(p.get("created_at")),
            "edited_at": _iso(p.get("edited_at")),
            "deleted_at": _iso(p.get("deleted_at")),
        } for p in rows],
    }


@router.post("/threads/{thread_id}/posts")
async def create_post(thread_id: str, request: Request):
    user = await _require_user(request)
    body = await request.json()
    post_body = (body.get("body") or "").strip()
    if not post_body:
        raise HTTPException(status_code=400, detail="body is required")
    try:
        t = await _db().forum_threads.find_one({"_id": ObjectId(thread_id)})
    except Exception:
        t = None
    if not t:
        raise HTTPException(status_code=404, detail="Thread not found")
    if t.get("locked"):
        raise HTTPException(status_code=403, detail="Thread is locked")
    await _check_league_member(user, t["league_id"])
    # Chat-mute check
    if user.get("chat_muted_until"):
        from datetime import datetime as _dt
        try:
            until = _dt.fromisoformat(user["chat_muted_until"].replace("Z", "+00:00"))
            if until > datetime.now(timezone.utc):
                raise HTTPException(status_code=403, detail=f"You are muted until {until.isoformat()}")
        except (ValueError, AttributeError):
            pass
    now = datetime.now(timezone.utc)
    res = await _db().forum_posts.insert_one({
        "thread_id": thread_id,
        "league_id": t["league_id"],
        "author_id": str(user["_id"]),
        "author_email": user.get("email"),
        "body": post_body,
        "created_at": now.isoformat(),
    })
    await _db().forum_threads.update_one(
        {"_id": t["_id"]},
        {"$set": {"last_post_at": now.isoformat()}, "$inc": {"post_count": 1}},
    )
    return {"ok": True, "post_id": str(res.inserted_id)}


@router.delete("/posts/{post_id}")
async def delete_post(post_id: str, request: Request):
    """Admin or post author. Soft delete — keeps audit trail."""
    user = await _require_user(request)
    try:
        p = await _db().forum_posts.find_one({"_id": ObjectId(post_id)})
    except Exception:
        p = None
    if not p:
        raise HTTPException(status_code=404, detail="Post not found")
    is_admin = user.get("role") == "admin"
    if not is_admin and str(user["_id"]) != p.get("author_id"):
        raise HTTPException(status_code=403, detail="Only admin or post author can delete")
    await _db().forum_posts.update_one(
        {"_id": p["_id"]},
        {"$set": {
            "deleted_at": datetime.now(timezone.utc).isoformat(),
            "deleted_by_admin": user.get("email") if is_admin else None,
        }},
    )
    return {"ok": True}
