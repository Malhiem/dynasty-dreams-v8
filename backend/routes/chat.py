"""Chat routes — channels (≤12 per league, commissioner-managed), DMs (one
per team-pair), messages, unread tracking, and per-user mute settings.

Collections used (auto-created on first write):
- chat_channels: { league_id, name, kind: 'channel'|'dm', participants: [user_ids],
                   team_pair: [tid_a, tid_b]?, created_by, created_at }
- chat_messages: { channel_id, user_id, sender_name, content, is_system,
                   metadata, created_at }
- chat_reads:    { user_id, channel_id, last_read_at }   (compound key)
- chat_mutes:    { user_id, channel_id, mute_until }     (null = indefinite,
                  absent = not muted)
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Request

router = APIRouter()
_deps: dict = {}

MAX_CHANNELS_PER_LEAGUE = 12
DEFAULT_CHANNELS = ["general", "trades", "trash-talk"]
MUTE_DURATIONS = {
    "30m": timedelta(minutes=30),
    "1h": timedelta(hours=1),
    "4h": timedelta(hours=4),
    "12h": timedelta(hours=12),
    "24h": timedelta(hours=24),
    "indefinite": None,  # null mute_until = forever
}


def setup(deps: dict) -> None:
    _deps.update(deps)
    _deps["post_chat_system_message"] = post_system_message


def _db(): return _deps["db"]
async def _get_user(request): return await _deps["get_current_user"](request)


def _serialize(doc: dict) -> dict:
    if not doc:
        return doc
    out = dict(doc)
    if "_id" in out:
        out["_id"] = str(out["_id"])
    for k in ("created_at", "last_read_at", "mute_until"):
        v = out.get(k)
        if hasattr(v, "isoformat"):
            out[k] = v.isoformat()
    return out


async def _ensure_default_channels(db, league_id: str):
    existing = await db.chat_channels.count_documents({
        "league_id": league_id, "kind": "channel",
    })
    if existing >= len(DEFAULT_CHANNELS):
        return
    have = set()
    async for c in db.chat_channels.find({"league_id": league_id, "kind": "channel"}, {"name": 1}):
        have.add(c["name"])
    for name in DEFAULT_CHANNELS:
        if name in have:
            continue
        await db.chat_channels.insert_one({
            "league_id": league_id,
            "name": name,
            "kind": "channel",
            "participants": [],   # empty = open to all league members
            "created_by": None,
            "created_at": datetime.now(timezone.utc),
            "is_default": True,
        })


async def _is_commissioner(db, league_id: str, user_id: str) -> bool:
    league = await db.leagues.find_one({"_id": ObjectId(league_id)})
    if not league:
        return False
    return (
        league.get("commissioner_id") == user_id or
        user_id in (league.get("co_commissioners") or [])
    )


async def _user_team(db, league_id: str, user_id: str) -> Optional[dict]:
    return await db.teams.find_one({"league_id": league_id, "owner_id": user_id})


async def _ensure_dm_channel(db, league_id: str, team_a_id: str, team_b_id: str) -> dict:
    """Get or create the DM channel between two teams. Pair is order-independent."""
    pair = sorted([team_a_id, team_b_id])
    chan = await db.chat_channels.find_one({
        "league_id": league_id, "kind": "dm", "team_pair": pair,
    })
    if chan:
        return chan
    # Resolve team docs for participants + display name
    teams = await db.teams.find({"_id": {"$in": [ObjectId(p) for p in pair]}}).to_list(2)
    participants = [t.get("owner_id") for t in teams if t.get("owner_id")]
    display = " ↔ ".join(t.get("name", "?") for t in teams)
    doc = {
        "league_id": league_id,
        "name": display,
        "kind": "dm",
        "participants": participants,
        "team_pair": pair,
        "created_by": None,
        "created_at": datetime.now(timezone.utc),
    }
    res = await db.chat_channels.insert_one(doc)
    doc["_id"] = res.inserted_id
    return doc


# ─────────────── Endpoints ──────────────────────────────────────────


@router.get("/chat/channels")
async def list_channels(league_id: str, request: Request):
    db = _db()
    user = await _get_user(request)
    await _ensure_default_channels(db, league_id)

    # Teams in this league — used to materialize one DM per team-pair
    # the user is part of (the user's own team paired with each other team).
    my_team = await _user_team(db, league_id, user["_id"])
    if my_team:
        other_teams = await db.teams.find(
            {"league_id": league_id, "_id": {"$ne": my_team["_id"]}}, {"_id": 1}
        ).to_list(50)
        for ot in other_teams:
            await _ensure_dm_channel(db, league_id, str(my_team["_id"]), str(ot["_id"]))

    cursor = db.chat_channels.find({"league_id": league_id})
    channels = []
    async for c in cursor:
        # Open channels are visible to all members; DMs only to participants.
        if c["kind"] == "dm" and user["_id"] not in (c.get("participants") or []):
            continue
        sc = _serialize(c)
        # Unread count
        read = await db.chat_reads.find_one({"user_id": user["_id"], "channel_id": str(c["_id"])})
        last_read = read.get("last_read_at") if read else None
        unread_q = {"channel_id": str(c["_id"])}
        if last_read:
            unread_q["created_at"] = {"$gt": last_read}
        sc["unread"] = await db.chat_messages.count_documents(unread_q)
        # Mute info
        mute = await db.chat_mutes.find_one({"user_id": user["_id"], "channel_id": str(c["_id"])})
        sc["muted"] = False
        sc["mute_until"] = None
        if mute:
            mu = mute.get("mute_until")
            if mu is None:
                sc["muted"] = True  # indefinite
            else:
                if mu.tzinfo is None:
                    mu = mu.replace(tzinfo=timezone.utc)
                if mu > datetime.now(timezone.utc):
                    sc["muted"] = True
                    sc["mute_until"] = mu.isoformat()
        channels.append(sc)

    # Stable ordering: channels first (alpha), then DMs (alpha).
    channels.sort(key=lambda c: (c["kind"] != "channel", c["name"].lower()))
    return {"channels": channels, "max_channels": MAX_CHANNELS_PER_LEAGUE}


@router.post("/chat/channels")
async def create_channel(payload: dict, request: Request):
    """Commissioner-only. Caps at 12 non-DM channels per league."""
    db = _db()
    user = await _get_user(request)
    league_id = payload.get("league_id")
    name = (payload.get("name") or "").strip().lower().replace(" ", "-")
    if not league_id or not name:
        raise HTTPException(status_code=400, detail="league_id and name required")
    if len(name) > 32:
        raise HTTPException(status_code=400, detail="Channel name too long (max 32 chars)")

    if not await _is_commissioner(db, league_id, user["_id"]):
        raise HTTPException(status_code=403, detail="Only commissioners can create channels")

    cnt = await db.chat_channels.count_documents({"league_id": league_id, "kind": "channel"})
    if cnt >= MAX_CHANNELS_PER_LEAGUE:
        raise HTTPException(
            status_code=400,
            detail=f"This league already has the maximum of {MAX_CHANNELS_PER_LEAGUE} channels.",
        )
    existing = await db.chat_channels.find_one({"league_id": league_id, "kind": "channel", "name": name})
    if existing:
        raise HTTPException(status_code=400, detail=f"Channel '{name}' already exists")

    doc = {
        "league_id": league_id,
        "name": name,
        "kind": "channel",
        "participants": [],
        "created_by": user["_id"],
        "created_at": datetime.now(timezone.utc),
        "is_default": False,
    }
    res = await db.chat_channels.insert_one(doc)
    doc["_id"] = res.inserted_id
    return _serialize(doc)


@router.delete("/chat/channels/{channel_id}")
async def delete_channel(channel_id: str, request: Request):
    db = _db()
    user = await _get_user(request)
    chan = await db.chat_channels.find_one({"_id": ObjectId(channel_id)})
    if not chan:
        raise HTTPException(status_code=404, detail="Channel not found")
    if chan.get("is_default"):
        raise HTTPException(status_code=400, detail="Default channels can't be deleted")
    if chan["kind"] == "dm":
        raise HTTPException(status_code=400, detail="DMs can't be deleted")
    if not await _is_commissioner(db, chan["league_id"], user["_id"]):
        raise HTTPException(status_code=403, detail="Only commissioners can delete channels")

    await db.chat_channels.delete_one({"_id": ObjectId(channel_id)})
    await db.chat_messages.delete_many({"channel_id": channel_id})
    await db.chat_reads.delete_many({"channel_id": channel_id})
    await db.chat_mutes.delete_many({"channel_id": channel_id})
    return {"deleted": channel_id}


@router.get("/chat/channels/{channel_id}/messages")
async def list_messages(channel_id: str, request: Request, limit: int = 100):
    db = _db()
    user = await _get_user(request)
    chan = await db.chat_channels.find_one({"_id": ObjectId(channel_id)})
    if not chan:
        raise HTTPException(status_code=404, detail="Channel not found")
    # DM access check
    if chan["kind"] == "dm" and user["_id"] not in (chan.get("participants") or []):
        raise HTTPException(status_code=403, detail="Not a participant")

    cursor = db.chat_messages.find({"channel_id": channel_id}).sort("created_at", -1).limit(limit)
    msgs = [_serialize(m) async for m in cursor]
    msgs.reverse()  # ascending so caller can render bottom-anchored

    # Mark read
    now = datetime.now(timezone.utc)
    await db.chat_reads.update_one(
        {"user_id": user["_id"], "channel_id": channel_id},
        {"$set": {"user_id": user["_id"], "channel_id": channel_id, "last_read_at": now}},
        upsert=True,
    )
    return {"messages": msgs}


@router.post("/chat/channels/{channel_id}/messages")
async def post_message(channel_id: str, payload: dict, request: Request):
    db = _db()
    user = await _get_user(request)
    chan = await db.chat_channels.find_one({"_id": ObjectId(channel_id)})
    if not chan:
        raise HTTPException(status_code=404, detail="Channel not found")
    if chan["kind"] == "dm" and user["_id"] not in (chan.get("participants") or []):
        raise HTTPException(status_code=403, detail="Not a participant")
    text = (payload.get("content") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Message empty")
    if len(text) > 2000:
        raise HTTPException(status_code=400, detail="Message too long (max 2000 chars)")

    team = await _user_team(db, chan["league_id"], user["_id"])
    sender_name = team.get("name") if team else user.get("name") or user.get("email") or "Member"
    msg = {
        "channel_id": channel_id,
        "league_id": chan["league_id"],
        "user_id": user["_id"],
        "sender_name": sender_name,
        "content": text,
        "is_system": False,
        "metadata": payload.get("metadata") or {},
        "created_at": datetime.now(timezone.utc),
    }
    res = await db.chat_messages.insert_one(msg)
    msg["_id"] = res.inserted_id

    # Iter 206 — Content Moderation Phase 2: scan against banned keywords.
    try:
        from routes import moderation as _mod
        match = await _mod.scan_text(text)
        if match:
            await _mod.queue_for_review(
                source="chat",
                content=text,
                author_id=str(user["_id"]),
                author_email=user.get("email"),
                context={
                    "channel_id": channel_id,
                    "league_id": chan["league_id"],
                    "message_id": str(res.inserted_id),
                    "sender_name": sender_name,
                },
                matched_word=match["matched_word"],
                severity=match["severity"],
            )
    except Exception:
        # Non-fatal — chat must never break on moderation errors.
        pass

    # Mark sender as read (don't increment their own unread)
    await db.chat_reads.update_one(
        {"user_id": user["_id"], "channel_id": channel_id},
        {"$set": {"user_id": user["_id"], "channel_id": channel_id, "last_read_at": msg["created_at"]}},
        upsert=True,
    )

    # ─── @mention push notifications ─────────────────────────────
    # Parse @username and @teamname tokens; fire one Expo push per unique
    # mentioned user (excluding the sender). Best-effort, non-blocking.
    try:
        import re as _re
        import asyncio as _asyncio
        from routes.push import send_push
        mentioned_handles = {m.lower() for m in _re.findall(r"@([\w-]+)", text)}
        if mentioned_handles:
            target_ids: set = set()
            league_teams = await db.teams.find(
                {"league_id": chan["league_id"]},
                {"_id": 1, "owner_id": 1, "name": 1},
            ).to_list(200)
            owner_ids = list({t["owner_id"] for t in league_teams})
            users_by_id = {}
            if owner_ids:
                async for u in db.users.find(
                    {"_id": {"$in": owner_ids}},
                    {"username": 1, "name": 1, "email": 1},
                ):
                    users_by_id[u["_id"]] = u
            for t in league_teams:
                tname = (t.get("name") or "").lower().replace(" ", "-")
                u = users_by_id.get(t["owner_id"]) or {}
                handles = {
                    tname,
                    (u.get("username") or "").lower(),
                    (u.get("name") or "").lower().replace(" ", "-"),
                }
                if handles & mentioned_handles and t["owner_id"] != user["_id"]:
                    target_ids.add(t["owner_id"])
            if target_ids:
                _asyncio.create_task(send_push(
                    list(target_ids),
                    title=f"💬 {sender_name} mentioned you",
                    body=text[:140],
                    data={
                        "type": "chat_mention",
                        "channel_id": channel_id,
                        "league_id": chan["league_id"],
                        "link": f"/chat?channel={channel_id}",
                    },
                ))
    except Exception:
        # @mention push is best-effort; never break message posting.
        pass

    # Iter 230 — Fan out a `league_chat_message` in-app notification to all
    # league members for non-DM channels (off by default in the user's
    # preferences — they have to opt in to get noisier chat pings).
    try:
        if chan.get("kind") != "dm":
            create_notif = _deps.get("create_notification")
            if create_notif:
                from routes.notification_events import EVT_LEAGUE_CHAT_MESSAGE
                teams = await db.teams.find(
                    {"league_id": chan["league_id"]},
                    {"owner_id": 1, "co_owner_ids": 1},
                ).to_list(200)
                recipients: set = set()
                for t in teams:
                    if t.get("owner_id"):
                        recipients.add(t["owner_id"])
                    for co in (t.get("co_owner_ids") or []):
                        if co:
                            recipients.add(co)
                recipients.discard(user["_id"])
                preview = text if len(text) <= 80 else text[:77] + "…"
                for uid in recipients:
                    try:
                        await create_notif(
                            uid,
                            EVT_LEAGUE_CHAT_MESSAGE,
                            f"{sender_name} in league chat",
                            preview,
                            chan["league_id"],
                            f"/chat?channel={channel_id}",
                        )
                    except Exception:
                        pass
    except Exception:
        pass

    return _serialize(msg)


@router.get("/chat/unread")
async def total_unread(request: Request, league_id: Optional[str] = None):
    """Aggregate unread count across all of the user's visible channels —
    powers the sidebar badge. Excludes channels the user has muted."""
    db = _db()
    user = await _get_user(request)

    chan_q: dict = {}
    if league_id:
        chan_q["league_id"] = league_id

    # Visible channels = open channels in user's leagues + DMs they're in
    cursor = db.chat_channels.find(chan_q)
    channel_ids: list[str] = []
    async for c in cursor:
        if c["kind"] == "dm" and user["_id"] not in (c.get("participants") or []):
            continue
        channel_ids.append(str(c["_id"]))
    if not channel_ids:
        return {"unread": 0, "by_channel": {}}

    # Fetch read cursors and mute states in bulk
    reads = {}
    async for r in db.chat_reads.find({"user_id": user["_id"], "channel_id": {"$in": channel_ids}}):
        reads[r["channel_id"]] = r.get("last_read_at")
    mutes = {}
    async for m in db.chat_mutes.find({"user_id": user["_id"], "channel_id": {"$in": channel_ids}}):
        mu = m.get("mute_until")
        if mu is None:
            mutes[m["channel_id"]] = True  # indefinite
        else:
            if mu.tzinfo is None:
                mu = mu.replace(tzinfo=timezone.utc)
            if mu > datetime.now(timezone.utc):
                mutes[m["channel_id"]] = True

    by_channel = {}
    total = 0
    for cid in channel_ids:
        if mutes.get(cid):
            by_channel[cid] = 0
            continue
        q = {"channel_id": cid, "user_id": {"$ne": user["_id"]}}
        if reads.get(cid):
            q["created_at"] = {"$gt": reads[cid]}
        n = await db.chat_messages.count_documents(q)
        by_channel[cid] = n
        total += n
    return {"unread": total, "by_channel": by_channel}


@router.post("/chat/channels/{channel_id}/mute")
async def set_mute(channel_id: str, payload: dict, request: Request):
    """Mute or unmute. `payload.duration` ∈ {"30m","1h","4h","12h","24h",
    "indefinite"} or null to UNMUTE."""
    db = _db()
    user = await _get_user(request)
    chan = await db.chat_channels.find_one({"_id": ObjectId(channel_id)})
    if not chan:
        raise HTTPException(status_code=404, detail="Channel not found")

    duration = payload.get("duration")
    if duration is None:
        await db.chat_mutes.delete_one({"user_id": user["_id"], "channel_id": channel_id})
        return {"channel_id": channel_id, "muted": False, "mute_until": None}

    if duration not in MUTE_DURATIONS:
        raise HTTPException(status_code=400, detail=f"Bad duration. Use one of {list(MUTE_DURATIONS.keys())} or null to unmute")

    if duration == "indefinite":
        mute_until = None
    else:
        mute_until = datetime.now(timezone.utc) + MUTE_DURATIONS[duration]

    await db.chat_mutes.update_one(
        {"user_id": user["_id"], "channel_id": channel_id},
        {"$set": {
            "user_id": user["_id"],
            "channel_id": channel_id,
            "mute_until": mute_until,
        }},
        upsert=True,
    )
    return {
        "channel_id": channel_id,
        "muted": True,
        "mute_until": mute_until.isoformat() if mute_until else None,
        "duration": duration,
    }


@router.get("/chat/league/{league_id}/members")
async def list_league_members(league_id: str, request: Request):
    """League members for @mention autocomplete. Returns one row per team in
    the league: { team_id, team_name, owner_name, abbr }."""
    db = _db()
    await _get_user(request)
    teams = await db.teams.find(
        {"league_id": league_id},
        {"_id": 1, "name": 1, "owner_id": 1, "owner_name": 1, "abbreviation": 1},
    ).to_list(50)
    out = []
    for t in teams:
        owner_name = t.get("owner_name")
        if not owner_name and t.get("owner_id"):
            try:
                u = await db.users.find_one({"_id": ObjectId(t["owner_id"])}, {"name": 1, "email": 1})
                if u:
                    owner_name = u.get("name") or u.get("email")
            except Exception:
                pass
        out.append({
            "team_id": str(t["_id"]),
            "team_name": t.get("name", ""),
            "owner_name": owner_name or "Owner",
            "abbr": t.get("abbreviation") or (t.get("name", "")[:3].upper() if t.get("name") else "?"),
        })
    out.sort(key=lambda x: x["team_name"].lower())
    return {"members": out}


# ─────────────── Helpers used by other modules ─────────────────────


async def post_system_message(
    db,
    league_id: str,
    text: str,
    *,
    channel_name: Optional[str] = None,
    team_pair: Optional[list[str]] = None,
    metadata: Optional[dict] = None,
):
    """Insert a system message into either a named channel (e.g. 'general')
    or a DM identified by `team_pair=[team_a_id, team_b_id]`. Used by the
    trade engine and the team-rename hook.

    Best-effort: failures are logged & swallowed so they don't break the
    business action that triggered them.
    """
    try:
        await _ensure_default_channels(db, league_id)
        if team_pair:
            chan = await _ensure_dm_channel(db, league_id, team_pair[0], team_pair[1])
            channel_id = str(chan["_id"])
        else:
            target = channel_name or "general"
            chan = await db.chat_channels.find_one(
                {"league_id": league_id, "kind": "channel", "name": target}
            )
            if not chan:
                return
            channel_id = str(chan["_id"])
        await db.chat_messages.insert_one({
            "channel_id": channel_id,
            "league_id": league_id,
            "user_id": None,
            "sender_name": "System",
            "content": text,
            "is_system": True,
            "metadata": metadata or {},
            "created_at": datetime.now(timezone.utc),
        })
    except Exception as e:
        logger = _deps.get("logger")
        if logger:
            logger.warning("chat system message failed: %s", e)
