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
from pymongo import ReturnDocument

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


async def dedupe_dm_channels_and_create_index(db) -> dict:
    """Iter 232N.12 — One-time (idempotent) startup migration.

    Fixes historical duplicate DM channels caused by the pre-232N.12
    non-atomic `_ensure_dm_channel` (two participants opening chat at
    the same moment both saw `find_one() -> None` and both called
    `insert_one()`). For every `(league_id, team_pair)` group we keep
    the OLDEST channel, migrate every message/read/mute row referring
    to newer duplicate ids onto the survivor, then drop the duplicates.

    Then backfills a scalar `dm_pair_key` (sorted `"teamA|teamB"`) on
    every DM doc — we can't put a unique index on the raw `team_pair`
    array (Mongo indexes each element individually, so two DMs sharing
    one team collide on that team's id). Finally creates the partial
    unique index on `{league_id, kind, dm_pair_key}` so future races
    are rejected at the storage layer.
    """
    stats = {"pairs_merged": 0, "channels_deleted": 0,
             "messages_moved": 0, "keys_backfilled": 0}
    # Aggregate all DM pairs with duplicates.
    pipeline = [
        {"$match": {"kind": "dm", "team_pair": {"$exists": True, "$ne": None}}},
        {"$group": {
            "_id": {"league_id": "$league_id", "team_pair": "$team_pair"},
            "ids": {"$push": "$_id"},
            "count": {"$sum": 1},
        }},
        {"$match": {"count": {"$gt": 1}}},
    ]
    async for group in db.chat_channels.aggregate(pipeline):
        ids = group["ids"]
        docs = await db.chat_channels.find({"_id": {"$in": ids}}).to_list(len(ids))
        docs.sort(key=lambda d: d.get("created_at") or datetime.min.replace(tzinfo=timezone.utc))
        keeper = docs[0]
        keeper_id_str = str(keeper["_id"])
        losers = [d["_id"] for d in docs[1:]]
        loser_id_strs = [str(x) for x in losers]

        msg_res = await db.chat_messages.update_many(
            {"channel_id": {"$in": loser_id_strs}},
            {"$set": {"channel_id": keeper_id_str}},
        )
        stats["messages_moved"] += msg_res.modified_count
        await db.chat_reads.update_many(
            {"channel_id": {"$in": loser_id_strs}},
            {"$set": {"channel_id": keeper_id_str}},
        )
        await db.chat_mutes.update_many(
            {"channel_id": {"$in": loser_id_strs}},
            {"$set": {"channel_id": keeper_id_str}},
        )
        del_res = await db.chat_channels.delete_many({"_id": {"$in": losers}})
        stats["channels_deleted"] += del_res.deleted_count
        stats["pairs_merged"] += 1

    # Backfill scalar `dm_pair_key` on every DM doc that doesn't have it.
    async for d in db.chat_channels.find({
        "kind": "dm",
        "team_pair": {"$exists": True, "$type": "array"},
        "dm_pair_key": {"$exists": False},
    }):
        tp = d.get("team_pair") or []
        if len(tp) < 2:
            continue
        pair_key = "|".join(sorted(str(x) for x in tp))
        await db.chat_channels.update_one(
            {"_id": d["_id"]},
            {"$set": {"dm_pair_key": pair_key}},
        )
        stats["keys_backfilled"] += 1

    try:
        await db.chat_channels.create_index(
            [("league_id", 1), ("kind", 1), ("dm_pair_key", 1)],
            unique=True,
            partialFilterExpression={"kind": "dm", "dm_pair_key": {"$exists": True}},
            name="uniq_dm_pair_key_per_league",
        )
    except Exception as e:  # pragma: no cover — log-only
        import logging
        logging.getLogger(__name__).warning(
            "chat_channels unique DM index skipped: %s", e,
        )

    # Iter 232N.12 — Same non-atomic race existed in
    # `_ensure_default_channels` for the auto-seeded `general`/`trades`/
    # `trash-talk` rows — merge the dupes and create a partial unique
    # index on `{league_id, kind, name}` scoped to default channels.
    default_pipeline = [
        {"$match": {"kind": "channel", "is_default": True}},
        {"$group": {
            "_id": {"league_id": "$league_id", "name": "$name"},
            "ids": {"$push": "$_id"},
            "count": {"$sum": 1},
        }},
        {"$match": {"count": {"$gt": 1}}},
    ]
    async for group in db.chat_channels.aggregate(default_pipeline):
        ids = group["ids"]
        docs = await db.chat_channels.find({"_id": {"$in": ids}}).to_list(len(ids))
        docs.sort(key=lambda d: d.get("created_at") or datetime.min.replace(tzinfo=timezone.utc))
        keeper_id_str = str(docs[0]["_id"])
        losers = [d["_id"] for d in docs[1:]]
        loser_id_strs = [str(x) for x in losers]

        msg_res = await db.chat_messages.update_many(
            {"channel_id": {"$in": loser_id_strs}},
            {"$set": {"channel_id": keeper_id_str}},
        )
        stats["messages_moved"] += msg_res.modified_count
        await db.chat_reads.update_many(
            {"channel_id": {"$in": loser_id_strs}},
            {"$set": {"channel_id": keeper_id_str}},
        )
        await db.chat_mutes.update_many(
            {"channel_id": {"$in": loser_id_strs}},
            {"$set": {"channel_id": keeper_id_str}},
        )
        del_res = await db.chat_channels.delete_many({"_id": {"$in": losers}})
        stats["channels_deleted"] += del_res.deleted_count
        stats["pairs_merged"] += 1

    try:
        await db.chat_channels.create_index(
            [("league_id", 1), ("kind", 1), ("name", 1)],
            unique=True,
            partialFilterExpression={"kind": "channel", "is_default": True},
            name="uniq_default_channel_per_league",
        )
    except Exception as e:  # pragma: no cover — log-only
        import logging
        logging.getLogger(__name__).warning(
            "chat_channels unique default-channel index skipped: %s", e,
        )

    # Iter 232N.13 — Same dedup safety net for the new `group_dm` kind
    # so concurrent multi-team-picker submissions can't produce dupes.
    try:
        await db.chat_channels.create_index(
            [("league_id", 1), ("kind", 1), ("group_key", 1)],
            unique=True,
            partialFilterExpression={"kind": "group_dm", "group_key": {"$exists": True}},
            name="uniq_group_dm_key_per_league",
        )
    except Exception as e:  # pragma: no cover — log-only
        import logging
        logging.getLogger(__name__).warning(
            "chat_channels unique group-DM index skipped: %s", e,
        )
    return stats


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
    """Iter 232N.12 — Atomic upsert per default channel name so
    concurrent `/chat/channels` requests can't race and create dupes.
    Backed by the partial unique index on `{league_id, kind, name}`
    (created in `dedupe_default_channels_and_create_index`).
    """
    for name in DEFAULT_CHANNELS:
        await db.chat_channels.find_one_and_update(
            {"league_id": league_id, "kind": "channel", "name": name},
            {
                "$setOnInsert": {
                    "league_id": league_id,
                    "name": name,
                    "kind": "channel",
                    "participants": [],
                    "created_by": None,
                    "created_at": datetime.now(timezone.utc),
                    "is_default": True,
                },
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )


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


async def _is_league_member(db, league_id: str, user_id: str) -> bool:
    """SEC-001 (iter 232h) — league-membership predicate used by every
    chat channel/message endpoint. A user counts as a member when any
    of the following holds:
      • They own (`owner_id`) a team in the league.
      • They co-own a team in the league (present in `co_owner_ids`).
      • They are the league's commissioner or a co-commissioner.
    Global admin / super-admin roles are NOT treated as auto-members
    on purpose — chat is private social space, admins can still read
    it via direct DB inspection if needed but shouldn't casually
    show up as a chatter.
    """
    if not league_id or not user_id:
        return False
    # Team-owner or co-owner check (single roundtrip covers both).
    team = await db.teams.find_one(
        {
            "league_id": league_id,
            "$or": [
                {"owner_id": user_id},
                {"co_owner_ids": user_id},
            ],
        },
        {"_id": 1},
    )
    if team:
        return True
    # Commissioner / co-commissioner check.
    try:
        league = await db.leagues.find_one(
            {"_id": ObjectId(league_id)},
            {"commissioner_id": 1, "co_commissioners": 1},
        )
    except Exception:
        return False
    if not league:
        return False
    return (
        league.get("commissioner_id") == user_id
        or user_id in (league.get("co_commissioners") or [])
    )


async def _require_league_member(db, league_id: str, user_id: str) -> None:
    """Raises 403 unless the user belongs to the league. Used at every
    channel/message boundary that previously only ran `_get_user`."""
    if not await _is_league_member(db, league_id, user_id):
        raise HTTPException(
            status_code=403,
            detail="You are not a member of this league.",
        )


async def _require_channel_access(db, channel: dict, user_id: str) -> None:
    """Combined access gate for a specific channel doc.

    • DMs: must be in `participants`.
    • Non-DM channels: must be a member of the channel's league.

    Both branches raise 403 on failure. `channel` MUST already be
    fetched by the caller so we don't repeat the round-trip.
    """
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    # Iter 232N.13 — Group DMs share the DM access model: participants
    # only. Same code path avoids drift between DM/group_dm gating.
    if channel.get("kind") in ("dm", "group_dm"):
        if user_id not in (channel.get("participants") or []):
            raise HTTPException(status_code=403, detail="Not a participant")
        return
    league_id = channel.get("league_id")
    if not league_id:
        # Malformed channel — deny by default.
        raise HTTPException(status_code=403, detail="Channel has no league scope")
    await _require_league_member(db, league_id, user_id)


async def _ensure_dm_channel(db, league_id: str, team_a_id: str, team_b_id: str) -> dict:
    """Get or create the DM channel between two teams. Pair is order-independent.

    Iter 232N.12 — Uses `find_one_and_update(upsert=True)` on a scalar
    `dm_pair_key` (sorted `"teamA|teamB"`) so concurrent calls can't
    race and produce duplicate DM rows. Backed by a unique index on
    `{league_id, kind, dm_pair_key}` (partial for `kind=dm`). A unique
    index on the raw `team_pair` array wouldn't work — Mongo indexes
    each array element individually, so two DMs sharing one team would
    collide on that team's id.
    """
    pair = sorted([team_a_id, team_b_id])
    pair_key = "|".join(pair)
    # Fast path — DM already exists.
    existing = await db.chat_channels.find_one({
        "league_id": league_id, "kind": "dm", "dm_pair_key": pair_key,
    })
    if existing:
        return existing
    # Resolve team docs for participants + display name.
    teams = await db.teams.find({"_id": {"$in": [ObjectId(p) for p in pair]}}).to_list(2)
    participants = [t.get("owner_id") for t in teams if t.get("owner_id")]
    display = " ↔ ".join((t.get("name") or "?") for t in teams)
    # Atomic upsert — if a parallel request beat us we get their doc
    # back. The unique index on `dm_pair_key` makes this contention-safe.
    doc = await db.chat_channels.find_one_and_update(
        {"league_id": league_id, "kind": "dm", "dm_pair_key": pair_key},
        {
            "$setOnInsert": {
                "league_id": league_id,
                "name": display,
                "kind": "dm",
                "participants": participants,
                "team_pair": pair,
                "dm_pair_key": pair_key,
                "created_by": None,
                "created_at": datetime.now(timezone.utc),
            },
        },
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return doc


async def _ensure_group_dm(db, league_id: str, team_ids: list[str], creator_user_id: str) -> dict:
    """Iter 232N.13 — Get or create a group DM channel for 3+ teams.

    Dedup key is `group_key = "|".join(sorted(team_ids))`, stored as a
    scalar so we can partial-unique-index it (Mongo indexes each array
    element individually, so we can't unique-index the raw team_ids
    array). `participants` is the union of team owner_ids — access
    control reuses the DM path via `_require_channel_access`.

    The name is auto-generated from team names ("Team A · Team B ·
    Team C", truncated at 60 chars); users can rename via
    `PATCH /chat/channels/{id}` if that endpoint is added later.
    """
    sorted_ids = sorted(set(team_ids))
    if len(sorted_ids) < 3:
        raise HTTPException(
            status_code=400,
            detail="Group DMs require at least 3 teams — use a regular DM for 2 teams",
        )
    group_key = "|".join(sorted_ids)
    existing = await db.chat_channels.find_one({
        "league_id": league_id, "kind": "group_dm", "group_key": group_key,
    })
    if existing:
        return existing
    teams = await db.teams.find(
        {"_id": {"$in": [ObjectId(t) for t in sorted_ids]}},
    ).to_list(len(sorted_ids))
    if len(teams) != len(sorted_ids):
        raise HTTPException(status_code=404, detail="One or more teams not found")
    for t in teams:
        if t.get("league_id") != league_id:
            raise HTTPException(
                status_code=400,
                detail="All teams must belong to the same league",
            )
    participants = list({t.get("owner_id") for t in teams if t.get("owner_id")})
    display = " · ".join((t.get("name") or "?") for t in teams)
    if len(display) > 60:
        display = display[:57] + "…"
    doc = await db.chat_channels.find_one_and_update(
        {"league_id": league_id, "kind": "group_dm", "group_key": group_key},
        {
            "$setOnInsert": {
                "league_id": league_id,
                "name": display,
                "kind": "group_dm",
                "participants": participants,
                "team_ids": sorted_ids,
                "group_key": group_key,
                "created_by": creator_user_id,
                "created_at": datetime.now(timezone.utc),
            },
        },
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return doc


# ─────────────── Endpoints ──────────────────────────────────────────


@router.get("/chat/channels")
async def list_channels(league_id: str, request: Request):
    db = _db()
    user = await _get_user(request)
    # SEC-001 (iter 232h) — non-members previously could enumerate
    # every channel id in any league.
    await _require_league_member(db, league_id, user["_id"])
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
        # Open channels are visible to all members; DMs + group DMs only to participants.
        if c["kind"] in ("dm", "group_dm") and user["_id"] not in (c.get("participants") or []):
            continue
        sc = _serialize(c)
        # Unread count
        # Iter 232N.9 — Exclude the user's own messages from their
        # unread badge (was previously counting self-authored messages
        # in channels that had never been marked read, producing a
        # phantom `#` badge on channels the user technically hasn't
        # visited even though nothing NEW from others is there). The
        # sidebar aggregate at `/chat/unread` already applies this
        # filter; the per-channel list must match.
        read = await db.chat_reads.find_one({"user_id": user["_id"], "channel_id": str(c["_id"])})
        last_read = read.get("last_read_at") if read else None
        unread_q: dict = {
            "channel_id": str(c["_id"]),
            "user_id": {"$ne": user["_id"]},
        }
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


@router.post("/chat/group-dm")
async def create_group_dm(payload: dict, request: Request):
    """Iter 232N.13 — Get-or-create a 3+ team group DM channel.

    Body: `{ league_id: str, team_ids: [t1, t2, t3, ...] }`. Caller must
    own one of `team_ids` (i.e. they're inviting themselves in). All
    teams must belong to `league_id`. Returns the resolved channel doc
    so the client can navigate straight to the new thread.
    """
    db = _db()
    user = await _get_user(request)
    league_id = payload.get("league_id")
    team_ids = payload.get("team_ids") or []
    if not league_id or not isinstance(team_ids, list) or len(team_ids) < 3:
        raise HTTPException(
            status_code=400,
            detail="league_id and at least 3 team_ids are required",
        )
    await _require_league_member(db, league_id, user["_id"])
    # Caller must own one of the teams — otherwise anyone in the league
    # could spin up group threads that include them but talk about
    # other people (spam / harassment vector).
    my_team = await _user_team(db, league_id, user["_id"])
    if not my_team or str(my_team["_id"]) not in team_ids:
        raise HTTPException(
            status_code=403,
            detail="You must include your own team in the group DM",
        )
    chan = await _ensure_group_dm(db, league_id, team_ids, user["_id"])
    return _serialize(chan)


@router.delete("/chat/channels/{channel_id}")
async def delete_channel(channel_id: str, request: Request):
    db = _db()
    user = await _get_user(request)
    chan = await db.chat_channels.find_one({"_id": ObjectId(channel_id)})
    if not chan:
        raise HTTPException(status_code=404, detail="Channel not found")
    if chan.get("is_default"):
        raise HTTPException(status_code=400, detail="Default channels can't be deleted")
    if chan["kind"] in ("dm", "group_dm"):
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
    # SEC-001 (iter 232h) — previously only DMs enforced a check;
    # open channels leaked history to any authenticated user.
    await _require_channel_access(db, chan, user["_id"])

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
    # SEC-001 (iter 232h) — previously only DM channels enforced a
    # check; any authenticated user could inject spoofed messages into
    # any league's chat and fan out notifications to all members.
    await _require_channel_access(db, chan, user["_id"])
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
    powers the sidebar badge. Excludes channels the user has muted.

    Iter 230aq — Previously this scanned every chat_channel in the DB
    and only filtered DMs by `participants`. League-scoped channels
    (kind == "channel") were counted regardless of league membership,
    so a user who'd never joined "Ice Kings Head-to-Head" was still
    seeing its 585-unread "trades" channel rolled into their badge.
    Now: derive the set of leagues the user actually belongs to
    (commissioner OR has a team OR is a co-owner), and only count
    channels in those leagues. DMs continue to use the participants
    check.
    """
    db = _db()
    user = await _get_user(request)
    uid = user["_id"]

    # Iter 230aq — Resolve the user's league memberships once. Apply
    # the same filters as the league switcher (archived OUT, name-
    # based test artefacts OUT, per-user hidden OUT) so the badge
    # reflects the leagues the user actually engages with — not
    # 30+ leftover Iter###_* / TEST_* leagues from automated runs.
    raw_member_team_league_ids: set = set()
    async for t in db.teams.find(
        {"$or": [{"owner_id": uid}, {"co_owner_ids": uid}]},
        {"league_id": 1},
    ):
        if t.get("league_id"):
            raw_member_team_league_ids.add(t["league_id"])
    raw_commish_ids: set = set()
    async for lg in db.leagues.find(
        {"commissioner_id": uid},
        {"_id": 1},
    ):
        raw_commish_ids.add(str(lg["_id"]))
    raw_league_ids = raw_member_team_league_ids | raw_commish_ids

    # Hydrate league docs so we can apply the same exclusion rules as
    # `/leagues?my_leagues=true&exclude_archived=true&exclude_test=true`.
    membership_league_ids: set = set()
    if raw_league_ids:
        from routes.leagues import _is_test_artifact_league
        oids = []
        for lid in raw_league_ids:
            try:
                oids.append(ObjectId(lid))
            except Exception:
                continue
        async for lg in db.leagues.find({"_id": {"$in": oids}}):
            if lg.get("archived") or (lg.get("status") or "").lower() == "archived":
                continue
            if _is_test_artifact_league(lg.get("name")):
                continue
            membership_league_ids.add(str(lg["_id"]))

    # Iter 230aq — Also honour per-user hidden leagues so the badge
    # never reports messages from a league the user has chosen to
    # hide from their dashboard.
    try:
        from routes.notification_preferences import get_hidden_league_ids
        hidden = set(await get_hidden_league_ids(uid))
        membership_league_ids -= hidden
    except Exception:
        pass

    chan_q: dict = {}
    if league_id:
        # Explicit league filter — but still enforce membership unless
        # the caller is asking about a league they belong to.
        if league_id not in membership_league_ids:
            return {"unread": 0, "by_channel": {}}
        chan_q["league_id"] = league_id

    # Visible channels = open channels in user's leagues + DMs they're in
    cursor = db.chat_channels.find(chan_q)
    channel_ids: list[str] = []
    async for c in cursor:
        if c["kind"] in ("dm", "group_dm"):
            if uid not in (c.get("participants") or []):
                continue
        else:
            # Iter 230aq — League-scoped channels must belong to a
            # league the user is actually in. Channels with no
            # league_id (rare; admin / system) are skipped.
            lg_id = c.get("league_id")
            if not lg_id or lg_id not in membership_league_ids:
                continue
        channel_ids.append(str(c["_id"]))
    if not channel_ids:
        return {"unread": 0, "by_channel": {}}

    # Fetch read cursors and mute states in bulk
    reads = {}
    async for r in db.chat_reads.find({"user_id": uid, "channel_id": {"$in": channel_ids}}):
        reads[r["channel_id"]] = r.get("last_read_at")
    mutes = {}
    async for m in db.chat_mutes.find({"user_id": uid, "channel_id": {"$in": channel_ids}}):
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
        q = {"channel_id": cid, "user_id": {"$ne": uid}}
        if reads.get(cid):
            q["created_at"] = {"$gt": reads[cid]}
        n = await db.chat_messages.count_documents(q)
        by_channel[cid] = n
        total += n
    return {"unread": total, "by_channel": by_channel}


@router.post("/chat/channels/{channel_id}/mark-read")
async def mark_channel_read(channel_id: str, request: Request):
    """Iter 230au — Zero out the unread count on a single channel
    without forcing the caller to fetch the message list. Used by the
    mobile swipe-right-on-channel gesture in `ChannelList`."""
    db = _db()
    user = await _get_user(request)
    chan = await db.chat_channels.find_one({"_id": ObjectId(channel_id)})
    # SEC-001 (iter 232h) — mark-read must also verify membership so
    # non-members can't silently poke another league's channel.
    await _require_channel_access(db, chan, user["_id"])
    now = datetime.now(timezone.utc)
    await db.chat_reads.update_one(
        {"user_id": user["_id"], "channel_id": channel_id},
        {"$set": {"user_id": user["_id"], "channel_id": channel_id, "last_read_at": now}},
        upsert=True,
    )
    return {"channel_id": channel_id, "last_read_at": now.isoformat()}


@router.post("/chat/channels/{channel_id}/mute")
async def set_mute(channel_id: str, payload: dict, request: Request):
    """Mute or unmute. `payload.duration` ∈ {"30m","1h","4h","12h","24h",
    "indefinite"} or null to UNMUTE."""
    db = _db()
    user = await _get_user(request)
    chan = await db.chat_channels.find_one({"_id": ObjectId(channel_id)})
    # SEC-001 (iter 232h) — enforcing membership here too so a
    # non-member can't silently pin a mute entry on another league's
    # channel (which could pollute the mute collection or, worse, be
    # a fingerprinting side-channel).
    await _require_channel_access(db, chan, user["_id"])

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
    the league: { team_id, team_name, owner_name, abbr }.

    SEC-002 (iter 232h) — gated to league members only. Previously any
    authenticated user could enumerate every other league's rosters and
    the fallback branch below leaked owner emails when `owner_name`
    wasn't set. Emails are never exposed here — if we don't have a
    friendly display name, we fall back to a stable "Owner" placeholder
    so nothing PII-adjacent leaks through the autocomplete surface.
    """
    db = _db()
    user = await _get_user(request)
    await _require_league_member(db, league_id, user["_id"])
    teams = await db.teams.find(
        {"league_id": league_id},
        {"_id": 1, "name": 1, "owner_id": 1, "owner_name": 1, "abbreviation": 1},
    ).to_list(50)
    out = []
    for t in teams:
        owner_name = t.get("owner_name")
        if not owner_name and t.get("owner_id"):
            try:
                # Only fall back to the user's display name — never
                # to their email address.
                u = await db.users.find_one(
                    {"_id": ObjectId(t["owner_id"])}, {"name": 1},
                )
                if u:
                    owner_name = u.get("name")
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
