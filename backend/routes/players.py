"""Players + Watchlist routes — extracted from server.py.

Carries the heavy /api/players query endpoint plus per-player news,
watchlist toggling, and ownership aggregation. Logic is verbatim from
server.py; helpers (db, get_current_user) are injected via _deps.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Request

router = APIRouter()
_deps: dict = {}


def setup(deps: dict) -> None:
    _deps.update(deps)


def _db(): return _deps["db"]
async def _get_user(request): return await _deps["get_current_user"](request)


@router.get("/players")
async def get_players(
    request: Request,
    search: Optional[str] = None,
    position: Optional[str] = None,
    nhl_team: Optional[str] = None,
    fantasy_team_id: Optional[str] = None,
    league_id: Optional[str] = None,
    availability: str = "all",
    injured: Optional[bool] = None,
    minors_eligible: Optional[bool] = None,
    exclude_team_id: Optional[str] = None,
    timeframe: str = "season",
    sort_by: Optional[str] = None,
    sort_dir: str = "desc",
    page: int = 1,
    limit: int = 50,
):
    """Players page query endpoint with extensive filtering."""
    db = _db()
    query: dict = {}
    if search:
        query["$or"] = [
            {"name": {"$regex": search, "$options": "i"}},
            {"team": {"$regex": search, "$options": "i"}},
        ]
    if nhl_team:
        query["team"] = nhl_team

    if position:
        pos = position.upper()
        if pos in {"W", "WING"}:
            query["position"] = {"$in": ["LW", "RW"]}
        elif pos == "D":
            query["position"] = {"$in": ["D", "LHD", "RHD"]}
        elif pos == "SKT":
            query["position"] = {"$ne": "G"}
        else:
            query["position"] = pos

    if injured is True:
        query["injury_status"] = {"$nin": [None, "", "Healthy", "ACTIVE"]}
    elif injured is False:
        query["$and"] = (query.get("$and") or []) + [{
            "$or": [
                {"injury_status": {"$exists": False}},
                {"injury_status": {"$in": [None, "", "Healthy", "ACTIVE"]}},
            ]
        }]

    if minors_eligible is True:
        query["minors_eligible"] = True
    elif minors_eligible is False:
        query["minors_eligible"] = {"$ne": True}

    owned_by: dict[str, dict] = {}
    league_total_teams = 0
    if league_id:
        teams = await db.teams.find({"league_id": league_id}).to_list(100)
        league_total_teams = len(teams)
        for t in teams:
            for pid in (t.get("roster") or []):
                owned_by[str(pid)] = {
                    "team_id": str(t["_id"]),
                    "team_name": t.get("name"),
                    "team_abbr": t.get("logo_abbr") or (t.get("name") or "")[:3].upper(),
                }

    watch_ids: set[str] = set()
    user = None
    try:
        user = await _get_user(request)
    except Exception:
        user = None
    if user and league_id:
        wl = await db.watchlists.find_one({"user_id": user["_id"], "league_id": league_id})
        if wl:
            watch_ids = set(wl.get("player_ids") or [])

    owned_pids = set(owned_by.keys())
    if availability == "free_agent":
        if league_id:
            query["_id"] = {"$nin": [ObjectId(p) for p in owned_pids]}
    elif availability == "owned":
        if league_id and owned_pids:
            query["_id"] = {"$in": [ObjectId(p) for p in owned_pids]}
        elif league_id:
            query["_id"] = {"$in": []}
    elif availability == "watchlist":
        if watch_ids:
            query["_id"] = {"$in": [ObjectId(p) for p in watch_ids]}
        else:
            query["_id"] = {"$in": []}
    elif availability == "watchlist_or_own":
        own_team_pids: set[str] = set()
        if user and league_id:
            own_team = await db.teams.find_one({"league_id": league_id, "owner_id": user["_id"]})
            if own_team:
                own_team_pids = set(own_team.get("roster") or [])
        union_ids = list(watch_ids | own_team_pids)
        query["_id"] = {"$in": [ObjectId(p) for p in union_ids]} if union_ids else {"$in": []}
    elif availability == "trade_block":
        if league_id:
            tb_items = await db.trade_block_items.find({"league_id": league_id, "player_id": {"$ne": None}}).to_list(1000)
            tb_pids = [str(i["player_id"]) for i in tb_items]
            query["_id"] = {"$in": [ObjectId(p) for p in tb_pids]} if tb_pids else {"$in": []}
    elif availability == "waivers":
        if league_id:
            wclaims = await db.waiver_claims.find({"league_id": league_id, "status": "pending"}).to_list(1000)
            w_pids = list({str(c["player_id"]) for c in wclaims})
            query["_id"] = {"$in": [ObjectId(p) for p in w_pids]} if w_pids else {"$in": []}

    if fantasy_team_id and league_id:
        ft = await db.teams.find_one({"_id": ObjectId(fantasy_team_id)})
        ft_pids = (ft.get("roster") or []) if ft else []
        existing = query.get("_id")
        wanted = [ObjectId(p) for p in ft_pids]
        if isinstance(existing, dict) and "$in" in existing:
            wanted = [oid for oid in wanted if oid in existing["$in"]]
        query["_id"] = {"$in": wanted}

    if exclude_team_id and league_id:
        ex_team = await db.teams.find_one({"_id": ObjectId(exclude_team_id)})
        ex_pids = (ex_team.get("roster") or []) if ex_team else []
        if ex_pids:
            existing_nin = []
            existing_id = query.get("_id")
            if isinstance(existing_id, dict) and "$nin" in existing_id:
                existing_nin = list(existing_id["$nin"])
            existing_nin.extend([ObjectId(p) for p in ex_pids])
            query["_id"] = {"$nin": existing_nin}

    skip = (page - 1) * limit
    sort_field_map = {
        "points": "points", "goals": "goals", "assists": "assists",
        "plus_minus": "plus_minus", "name": "name", "team": "team",
        "position": "position", "fpts": "points",
    }
    primary_sort = sort_field_map.get((sort_by or "").lower(), "points")
    direction = -1 if (sort_dir or "desc").lower() != "asc" else 1
    cursor = db.players.find(query).sort(primary_sort, direction).skip(skip).limit(limit)
    players = await cursor.to_list(limit)
    total = await db.players.count_documents(query)

    page_counts: dict[str, int] = {}
    if league_id and players:
        page_pids = [str(p["_id"]) for p in players]
        async for row in db.teams.aggregate([
            {"$match": {"league_id": league_id, "roster": {"$in": page_pids}}},
            {"$project": {"matched": {"$setIntersection": ["$roster", page_pids]}}},
            {"$unwind": "$matched"},
            {"$group": {"_id": "$matched", "count": {"$sum": 1}}},
        ]):
            page_counts[str(row["_id"])] = int(row["count"])

    tb_set: set[str] = set()
    wv_set: set[str] = set()
    if league_id:
        async for it in db.trade_block_items.find({"league_id": league_id, "player_id": {"$ne": None}}, {"player_id": 1}):
            tb_set.add(str(it["player_id"]))
        async for c in db.waiver_claims.find({"league_id": league_id, "status": "pending"}, {"player_id": 1}):
            wv_set.add(str(c["player_id"]))

    pct_change_map: dict[str, float] = {}
    if players:
        page_pids = [str(p["_id"]) for p in players]
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        async for snap in db.ownership_snapshots.find({
            "player_id": {"$in": page_pids},
            "snapshot_at": {"$lte": cutoff},
        }).sort("snapshot_at", -1):
            pid = str(snap["player_id"])
            if pid in pct_change_map:
                continue
            pct_change_map[pid] = float(snap.get("global_pct") or 0)

    news_map: dict[str, dict] = {}
    if players:
        page_pids = [str(p["_id"]) for p in players]
        async for n in db.player_news.find(
            {"player_id": {"$in": page_pids}},
            {"player_id": 1, "headline": 1, "summary": 1, "url": 1, "source": 1, "published_at": 1},
        ).sort("published_at", -1):
            pid = str(n["player_id"])
            if pid not in news_map:
                news_map[pid] = {
                    "headline": n.get("headline"),
                    "summary": n.get("summary"),
                    "source": n.get("source"),
                    "url": n.get("url"),
                    "published_at": (n.get("published_at").isoformat()
                                     if hasattr(n.get("published_at"), "isoformat")
                                     else n.get("published_at")),
                }

    start_count_map: dict[str, int] = {}
    if players:
        page_pids = [str(p["_id"]) for p in players]
        async for t in db.teams.find({"roster": {"$in": page_pids}}, {"roster": 1, "lineup": 1}):
            lineup = t.get("lineup") or {}
            for pid in (t.get("roster") or []):
                if pid not in page_pids:
                    continue
                info = lineup.get(pid)
                if info is None:
                    start_count_map[pid] = start_count_map.get(pid, 0) + 1
                elif info.get("section") in ("forward", "defense", "goalie"):
                    start_count_map[pid] = start_count_map.get(pid, 0) + 1

    out = []
    global_team_total = await db.teams.count_documents({})
    for player in players:
        pid = str(player["_id"])
        player["_id"] = pid
        info = owned_by.get(pid)
        player["owned_by_team_id"] = info.get("team_id") if info else None
        player["owned_by_team_name"] = info.get("team_name") if info else None
        player["owned_by_team_abbr"] = info.get("team_abbr") if info else None
        player["is_on_trade_block"] = pid in tb_set
        player["is_on_waivers"] = pid in wv_set
        player["is_in_watchlist"] = pid in watch_ids
        if league_id and league_total_teams:
            count = page_counts.get(pid, 0)
            player["league_pct"] = round(100 * count / league_total_teams, 1)
        global_owned = await db.teams.count_documents({"roster": pid}) if global_team_total else 0
        global_pct = round(100 * global_owned / global_team_total, 1) if global_team_total else 0.0
        player["global_pct"] = global_pct
        if pid in pct_change_map:
            player["pct_change_7d"] = round(global_pct - pct_change_map[pid], 1)
        else:
            player["pct_change_7d"] = None
        if global_team_total:
            if (player.get("injury_status") or "").upper() in {"IR", "OUT", "INJURED RESERVE"}:
                player["start_pct"] = round(0.0, 1)
            else:
                start_count = start_count_map.get(pid, 0)
                player["start_pct"] = round(100 * start_count / global_team_total, 1)
        if pid in news_map:
            n = news_map[pid]
            player["news_headline"] = n.get("headline")
            player["news_summary"] = n.get("summary")
            player["news_source"] = n.get("source")
            player["news_url"] = n.get("url")
            player["news_published_at"] = n.get("published_at")
            try:
                pub = datetime.fromisoformat(str(n["published_at"]).replace("Z", "+00:00"))
                if pub.tzinfo is None:
                    pub = pub.replace(tzinfo=timezone.utc)
                age_days = (datetime.now(timezone.utc) - pub).days
            except Exception:
                age_days = None
            player["news_age_days"] = age_days
            if age_days is None:
                player["news_signal"] = None
            elif age_days <= 7:
                player["news_signal"] = "fresh"
            elif age_days <= 21:
                player["news_signal"] = "stale"
            elif age_days <= 35:
                player["news_signal"] = "cold"
            else:
                player["news_signal"] = None
        out.append(player)

    if (sort_by or "").lower() in {"league_pct", "global_pct", "pct_change", "start_pct"}:
        key = {"pct_change": "pct_change_7d"}.get(sort_by.lower(), sort_by.lower())
        out.sort(key=lambda x: (x.get(key) is None, x.get(key) or 0),
                 reverse=(direction == -1))

    timeframe_supported = (timeframe == "season")
    if out and timeframe and timeframe != "season":
        days_map = {"today": 1, "7d": 7, "14d": 14, "30d": 30, "60d": 60, "90d": 90}
        days = days_map.get(timeframe)
        if days is not None:
            cutoff = datetime.now(timezone.utc) - timedelta(days=days)
            page_pids = [p["_id"] for p in out]
            agg = {}
            async for row in db.player_game_logs.aggregate([
                {"$match": {"player_id": {"$in": page_pids}, "date_dt": {"$gte": cutoff}}},
                {"$group": {
                    "_id": "$player_id",
                    "G": {"$sum": "$goals"}, "A": {"$sum": "$assists"},
                    "PTS": {"$sum": "$points"}, "PM": {"$sum": "$plus_minus"},
                    "SOG": {"$sum": "$sog"}, "PPP": {"$sum": "$ppg"},
                    "SHP": {"$sum": "$shg"}, "HIT": {"$sum": "$hits"},
                    "BLK": {"$sum": "$blocks"}, "GP": {"$sum": 1},
                }},
            ]):
                agg[str(row["_id"])] = row
            if agg:
                timeframe_supported = True
                for p in out:
                    a = agg.get(p["_id"])
                    if not a:
                        p["goals"] = 0; p["assists"] = 0; p["points"] = 0
                        p["plus_minus"] = 0
                        p["category_breakdown"] = {
                            "G": 0, "A": 0, "+/-": 0, "SOG": 0, "PPP": 0,
                            "SHP": 0, "HIT": 0, "BLK": 0,
                        }
                        p["games_played_window"] = 0
                        continue
                    p["goals"] = a["G"]; p["assists"] = a["A"]; p["points"] = a["PTS"]
                    p["plus_minus"] = a["PM"]
                    p["category_breakdown"] = {
                        "G": a["G"], "A": a["A"], "+/-": a["PM"],
                        "SOG": a["SOG"], "PPP": a["PPP"], "SHP": a["SHP"],
                        "HIT": a["HIT"], "BLK": a["BLK"],
                    }
                    p["games_played_window"] = a["GP"]

    return {
        "players": out,
        "total": total,
        "page": page,
        "pages": (total + limit - 1) // limit,
        "timeframe": timeframe,
        "timeframe_supported": timeframe_supported,
    }


@router.get("/watchlist")
async def get_watchlist(request: Request, league_id: Optional[str] = None):
    db = _db()
    user = await _get_user(request)
    wl = await db.watchlists.find_one({"user_id": user["_id"], "league_id": league_id})
    return {"player_ids": (wl.get("player_ids") if wl else []) or []}


@router.post("/players/news-bulk")
async def get_player_news_bulk(payload: dict, request: Request):
    """Bulk news-signal lookup. Body: {"player_ids": [...]}.
    Returns a dict keyed by player_id with the most-recent news headline +
    age + signal band (fresh/stale/cold) + summary.
    """
    db = _db()
    pids = [str(x) for x in (payload.get("player_ids") or []) if x]
    if not pids:
        return {"news": {}}
    out: dict[str, dict] = {}
    now = datetime.now(timezone.utc)
    async for n in db.player_news.find(
        {"player_id": {"$in": pids}},
        {"player_id": 1, "headline": 1, "summary": 1, "url": 1, "source": 1, "published_at": 1},
    ).sort("published_at", -1):
        pid = str(n["player_id"])
        if pid in out:
            continue
        pub = n.get("published_at")
        try:
            if hasattr(pub, "isoformat"):
                if pub.tzinfo is None:
                    pub_aware = pub.replace(tzinfo=timezone.utc)
                else:
                    pub_aware = pub
                age = (now - pub_aware).days
                pub_iso = pub.isoformat()
            else:
                age = None
                pub_iso = str(pub) if pub else None
        except Exception:
            age, pub_iso = None, None

        if age is None:
            signal = None
        elif age <= 7:
            signal = "fresh"
        elif age <= 21:
            signal = "stale"
        elif age <= 35:
            signal = "cold"
        else:
            signal = None

        if signal is None:
            continue
        out[pid] = {
            "news_headline": n.get("headline"),
            "news_summary": n.get("summary"),
            "news_source": n.get("source"),
            "news_url": n.get("url"),
            "news_published_at": pub_iso,
            "news_age_days": age,
            "news_signal": signal,
        }
    return {"news": out}


@router.post("/watchlist/toggle")
async def toggle_watchlist(payload: dict, request: Request):
    db = _db()
    user = await _get_user(request)
    pid = str(payload.get("player_id") or "")
    league_id = payload.get("league_id")
    if not pid:
        raise HTTPException(status_code=400, detail="player_id required")
    wl = await db.watchlists.find_one({"user_id": user["_id"], "league_id": league_id})
    ids = set((wl.get("player_ids") if wl else []) or [])
    added = pid not in ids
    if added:
        ids.add(pid)
    else:
        ids.discard(pid)
    await db.watchlists.update_one(
        {"user_id": user["_id"], "league_id": league_id},
        {"$set": {"user_id": user["_id"], "league_id": league_id,
                  "player_ids": list(ids),
                  "updated_at": datetime.now(timezone.utc)}},
        upsert=True,
    )
    return {"player_id": pid, "added": added, "in_watchlist": added}


@router.post("/players/ownership-bulk")
async def get_players_ownership(payload: dict, request: Request):
    """Compute % ownership for a batch of players."""
    db = _db()
    player_ids = [str(pid) for pid in (payload.get("player_ids") or []) if pid]
    if not player_ids:
        return {"ownership": {}}
    league_id = payload.get("league_id")

    global_total = await db.teams.count_documents({})
    pipeline = [
        {"$match": {"roster": {"$in": player_ids}}},
        {"$project": {"matched": {"$setIntersection": ["$roster", player_ids]}}},
        {"$unwind": "$matched"},
        {"$group": {"_id": "$matched", "count": {"$sum": 1}}},
    ]
    global_counts: dict[str, int] = {}
    async for row in db.teams.aggregate(pipeline):
        global_counts[str(row["_id"])] = int(row["count"])

    league_counts: dict[str, int] = {}
    league_total = 0
    if league_id:
        league_total = await db.teams.count_documents({"league_id": league_id})
        pipeline_l = [
            {"$match": {"league_id": league_id, "roster": {"$in": player_ids}}},
            {"$project": {"matched": {"$setIntersection": ["$roster", player_ids]}}},
            {"$unwind": "$matched"},
            {"$group": {"_id": "$matched", "count": {"$sum": 1}}},
        ]
        async for row in db.teams.aggregate(pipeline_l):
            league_counts[str(row["_id"])] = int(row["count"])

    out: dict[str, dict] = {}
    for pid in player_ids:
        g = global_counts.get(pid, 0)
        entry = {
            "global_owned": g,
            "global_total": global_total,
            "global_pct": round(100 * g / global_total, 1) if global_total else 0.0,
        }
        if league_id:
            l = league_counts.get(pid, 0)
            entry["league_owned"] = l
            entry["league_total"] = league_total
            entry["league_pct"] = round(100 * l / league_total, 1) if league_total else 0.0
        out[pid] = entry
    return {"ownership": out}


@router.get("/players/{player_id}")
async def get_player(player_id: str):
    db = _db()
    player = await db.players.find_one({"_id": ObjectId(player_id)})
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    player["_id"] = str(player["_id"])
    return player
