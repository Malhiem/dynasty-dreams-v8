"""Players + Watchlist routes — extracted from server.py.

Carries the heavy /api/players query endpoint plus per-player news,
watchlist toggling, and ownership aggregation. Logic is verbatim from
server.py; helpers (db, get_current_user) are injected via _deps.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Request

from utils.roster_rules import compute_minor_eligible

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
    undrafted_only: bool = False,
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
    # Iter 181 — fetch the league doc (with the minors_max_age /
    # minors_max_career_games thresholds) so per-player minor-eligibility
    # can be computed against the same rules the rest of the app uses.
    league_doc: dict = {}
    if league_id:
        try:
            league_doc = await db.leagues.find_one({"_id": ObjectId(league_id)}) or {}
        except Exception:
            league_doc = {}
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

    # Iter 232N.2 — Undrafted-only filter + shared status_flags helper.
    from routes.player_status import (
        compute_player_status_flags,
        get_previously_drafted_pids,
    )
    previously_drafted_pids: set = set()
    if league_id:
        previously_drafted_pids = await get_previously_drafted_pids(db, league_id)
    if undrafted_only and league_id:
        existing_id = query.get("_id")
        already_nin: list = []
        already_in: list = []
        if isinstance(existing_id, dict):
            if "$nin" in existing_id:
                already_nin = list(existing_id["$nin"])
            if "$in" in existing_id:
                already_in = list(existing_id["$in"])
        combined_nin = {oid for oid in already_nin}
        for pid in previously_drafted_pids:
            try:
                combined_nin.add(ObjectId(pid))
            except Exception:
                continue
        new_id_clause: dict = {}
        if combined_nin:
            new_id_clause["$nin"] = list(combined_nin)
        if already_in:
            new_id_clause["$in"] = already_in
        if new_id_clause:
            query["_id"] = new_id_clause

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
    # Pre-load the league's scoring config once per page so we can compute
    # per-player fantasy points (FPTS) for the Players-page table column.
    list_scoring_cfg = await _scoring_cfg_for(league_id) if league_id else None
    calc_fn = _deps.get("calculate_fantasy_points")
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

        # Fantasy points + per-game (league-aware when league_id is supplied,
        # platform default otherwise). Always populated so the table column
        # works even without a selected league.
        is_g = (player.get("position") == "G")
        # Iter 181 — surface minor-eligibility so the Players directory
        # renders the same Sprout badge as the rest of the app.
        player["minor_eligible"] = compute_minor_eligible(player, league_doc)
        # Iter 232N.2 — status_flags for the badge layer.
        player["status_flags"] = compute_player_status_flags(
            player, previously_drafted_pids if league_id else None,
        )
        stats_for_fpts = {
            "goals": player.get("goals", 0), "assists": player.get("assists", 0),
            "points": player.get("points", 0), "plus_minus": player.get("plus_minus", 0),
            "shots": player.get("shots", 0),
            "ppg": player.get("power_play_goals", 0),
            "ppp": player.get("power_play_points", 0),
            "shg": player.get("short_handed_goals", 0),
            "pim": player.get("penalty_minutes", 0),
            "saves": player.get("saves", 0),
            "goals_against": player.get("goals_against", 0),
            "wins": player.get("wins", 0), "losses": player.get("losses", 0),
            "shutouts": player.get("shutouts", 0),
            "position": player.get("position") or "C",
            "player_type": "goalie" if is_g else "skater",
        }
        if calc_fn:
            fpts = calc_fn(stats_for_fpts, list_scoring_cfg)
            player["fantasy_points"] = round(fpts, 2)
            gp = player.get("games_played", 0) or 0
            player["fantasy_points_per_game"] = round(fpts / gp, 2) if gp else 0.0
        out.append(player)

    if (sort_by or "").lower() in {"league_pct", "global_pct", "pct_change", "start_pct", "fantasy_points", "fpts", "fantasy_points_per_game", "fp_per_game", "fpg"}:
        key_map = {
            "pct_change": "pct_change_7d",
            "fpts": "fantasy_points",
            "fp_per_game": "fantasy_points_per_game",
            "fpg": "fantasy_points_per_game",
        }
        key = key_map.get(sort_by.lower(), sort_by.lower())
        out.sort(key=lambda x: (x.get(key) is None, x.get(key) or 0),
                 reverse=(direction == -1))

    timeframe_supported = (timeframe == "season")
    if out and timeframe and timeframe != "season":
        days_map = {"today": 1, "7d": 7, "14d": 14, "30d": 30, "60d": 60, "90d": 90}
        days = days_map.get(timeframe)
        # Iter 182 — also accept prior-season + playoffs + current
        # matchup-period filters. Prior seasons resolve from a
        # pre-cached `player_season_stats` collection (populated by
        # the iter182 NHL-API backfill script). "matchup" computes a
        # rolling window from the active league's matchup config.
        prior_season_match: Optional[dict] = None
        if timeframe in ("2024-25", "2023-24"):
            prior_season_match = {"season": timeframe, "season_type": "regular"}
        elif timeframe in ("2024-playoffs", "2023-playoffs"):
            year = timeframe.split("-")[0]
            # Stored as e.g. season="2023-24", season_type="playoffs"
            season_lookup = "2024-25" if year == "2024" else "2023-24"
            prior_season_match = {"season": season_lookup, "season_type": "playoffs"}
        elif timeframe == "matchup" and league_doc:
            # Use the active matchup window: lookup the current
            # matchup period from the league's schedule_metadata.
            md = league_doc.get("schedule_metadata") or {}
            cur = md.get("current_matchup_period") or {}
            start_iso = cur.get("start_date")
            end_iso = cur.get("end_date")
            if start_iso and end_iso:
                try:
                    start_dt = datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
                    end_dt = datetime.fromisoformat(end_iso.replace("Z", "+00:00"))
                except ValueError:
                    start_dt = end_dt = None
                if start_dt and end_dt:
                    days = max(1, (end_dt - start_dt).days + 1)
                    cutoff = end_dt - timedelta(days=days)

        if prior_season_match is not None:
            # Cached historical season lookup.
            page_pids_str = [str(p["_id"]) for p in out]
            cached = await db.player_season_stats.find(
                {**prior_season_match, "player_id": {"$in": page_pids_str}}
            ).to_list(len(page_pids_str))
            if cached:
                timeframe_supported = True
                by_pid = {row["player_id"]: row for row in cached}
                for p in out:
                    a = by_pid.get(p["_id"])
                    if not a:
                        p["goals"] = 0; p["assists"] = 0; p["points"] = 0
                        p["plus_minus"] = 0
                        p["category_breakdown"] = {
                            "G": 0, "A": 0, "+/-": 0, "SOG": 0, "PPP": 0,
                            "SHP": 0, "HIT": 0, "BLK": 0,
                        }
                        p["games_played"] = 0
                        continue
                    p["goals"] = a.get("goals", 0)
                    p["assists"] = a.get("assists", 0)
                    p["points"] = a.get("points", 0)
                    p["plus_minus"] = a.get("plus_minus", 0)
                    p["games_played"] = a.get("games_played", 0)
                    p["category_breakdown"] = {
                        "G": a.get("goals", 0), "A": a.get("assists", 0),
                        "+/-": a.get("plus_minus", 0),
                        "SOG": a.get("sog", 0), "PPP": a.get("ppg", 0),
                        "SHP": a.get("shg", 0), "HIT": a.get("hits", 0),
                        "BLK": a.get("blocks", 0),
                    }
        elif days is not None:
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
async def get_player(player_id: str, league_id: Optional[str] = None, request: Request = None):
    """Player detail with optional bio/contract enrichment when ?league_id is
    provided. Bio fields (height, weight, birth, draft) come from the NHL
    public API and are cached for 24h via `_career_cache`."""
    db = _db()
    player = await db.players.find_one({"_id": ObjectId(player_id)})
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    player["_id"] = str(player["_id"])

    # ── Bio + draft (NHL API, 24h cached) ────────────────────────────────
    nhl_id = player.get("nhl_id")
    if nhl_id:
        cached = _career_cache.get(nhl_id)
        now_ts = datetime.now(timezone.utc).timestamp()
        raw = None
        if cached and (now_ts - cached[0]) < _CAREER_CACHE_TTL:
            raw = cached[1]
        else:
            try:
                from nhlpy import NHLClient
                raw = NHLClient().stats.player_career_stats(player_id=int(nhl_id))
                _career_cache[nhl_id] = (now_ts, raw)
                # Iter 211 — stamp last_synced_at on the player doc so the
                # Sync Monitor reflects fresh activity from the live cache
                # path (not just live_scoring_worker).
                try:
                    await _db().players.update_one(
                        {"nhl_id": nhl_id},
                        {"$set": {"last_synced_at": datetime.now(timezone.utc).isoformat()}},
                    )
                except Exception:
                    pass
            except Exception:
                raw = None
        if raw:
            def _default(v):
                return v.get("default") if isinstance(v, dict) else v
            player["height_inches"] = raw.get("heightInInches")
            player["weight_pounds"] = raw.get("weightInPounds")
            player["birth_date"] = raw.get("birthDate")
            player["birth_city"] = _default(raw.get("birthCity"))
            player["birth_state"] = _default(raw.get("birthStateProvince"))
            player["birth_country"] = raw.get("birthCountry")
            player["headshot"] = raw.get("headshot")
            d = raw.get("draftDetails") or {}
            player["draft_year"] = d.get("year")
            player["draft_round"] = d.get("round")
            player["draft_pick_in_round"] = d.get("pickInRound")
            player["draft_overall"] = d.get("overallPick")
            player["draft_team_abbr"] = d.get("teamAbbrev")
            # NHL seasons = count of NHL regular-season rows
            seasons = [s for s in (raw.get("seasonTotals") or [])
                       if s.get("leagueAbbrev") == "NHL" and s.get("gameTypeId") == 2]
            player["nhl_seasons"] = len({s.get("season") for s in seasons})

    # ── Position eligibility (multi-position when available) ──────────────
    pos = player.get("position") or ""
    eligible = list({pos} | set(player.get("eligible_positions") or []))
    if pos in {"LW", "RW", "C"}:
        # NHL doesn't track multi-pos officially; fall back to primary only
        eligible = [pos]
    player["eligible_positions"] = eligible

    # ── League-scoped enrichment ─────────────────────────────────────────
    if league_id:
        league = await db.leagues.find_one({"_id": ObjectId(league_id)})
        if league:
            # Owner in THIS league
            owning_team = await db.teams.find_one({"league_id": league_id, "roster": player_id})
            player["owned_by_team_id"] = str(owning_team["_id"]) if owning_team else None
            player["owned_by_team_name"] = owning_team.get("name") if owning_team else None
            player["owned_by_owner_name"] = owning_team.get("owner_name") if owning_team else None

            # Fantasy points + per-game using league config
            scoring_cfg = await _scoring_cfg_for(league_id)
            stats = {
                "goals": player.get("goals", 0), "assists": player.get("assists", 0),
                "points": player.get("points", 0), "plus_minus": player.get("plus_minus", 0),
                "shots": player.get("shots", 0),
                "ppg": player.get("power_play_goals", 0),
                "ppp": player.get("power_play_points", 0),
                "shg": player.get("short_handed_goals", 0),
                "pim": player.get("penalty_minutes", 0),
                "saves": player.get("saves", 0),
                "goals_against": player.get("goals_against", 0),
                "wins": player.get("wins", 0), "losses": player.get("losses", 0),
                "shutouts": player.get("shutouts", 0),
            }
            is_goalie = (pos == "G")
            fpts = _calc_fpts(stats, is_goalie, scoring_cfg)
            player["fantasy_points"] = round(fpts, 2)
            gp = max(1, player.get("games_played", 0) or 0)
            player["fantasy_points_per_game"] = round(fpts / gp, 2) if gp else 0.0

            # Minors eligibility — use league's stored criteria with a
            # sensible default of "≤25 NHL career games OR ≤22 years old".
            max_games = league.get("minors_max_career_games", 25)
            max_age = league.get("minors_max_age", 22)
            career_games = 0
            if nhl_id and _career_cache.get(nhl_id):
                career = _career_cache[nhl_id][1].get("careerTotals", {}).get("regularSeason") or {}
                career_games = career.get("gamesPlayed", 0)
            age = None
            bd = player.get("birth_date")
            if bd:
                try:
                    bd_dt = datetime.fromisoformat(bd)
                    age = (datetime.now(timezone.utc).replace(tzinfo=None) - bd_dt).days // 365
                except Exception:
                    pass
            player["minors_eligible"] = bool(
                (career_games and career_games <= max_games) or
                (age is not None and age <= max_age)
            )
            player["minors_criteria"] = {
                "max_career_games": max_games,
                "max_age": max_age,
                "career_games": career_games,
                "age": age,
            }
        else:
            player["fantasy_points"] = None
            player["fantasy_points_per_game"] = None

    return player


# ══════════════════════════════════════════════════════════════════════════
# Player Profile Detail Endpoints
# ══════════════════════════════════════════════════════════════════════════
# Each endpoint below powers a single tab/section of the player profile page.
# All use the league's `scoring_configs` (skater_scoring + goalie_scoring) when
# `league_id` is provided so fantasy points are computed against the user's
# OWN league rules rather than a global default.


def _calc_fpts(stats: dict, is_goalie: bool, scoring_cfg: Optional[dict]):
    """Local fantasy-points calculator — uses the league's stored scoring_cfg
    when supplied, otherwise falls back to the platform default. Mirrors
    calculate_fantasy_points() in server.py without coupling to its internal
    DEFAULT_*_SCORING constants (those are imported via _deps)."""
    fn = _deps.get("calculate_fantasy_points")
    if not fn:
        return 0.0
    payload = dict(stats)
    payload["position"] = "G" if is_goalie else (payload.get("position") or "C")
    payload["player_type"] = "goalie" if is_goalie else "skater"
    return fn(payload, scoring_cfg)


async def _scoring_cfg_for(league_id: Optional[str]) -> Optional[dict]:
    if not league_id:
        return None
    db = _db()
    return await db.scoring_configs.find_one({"league_id": league_id})


@router.get("/players/{player_id}/news")
async def get_player_news_history(player_id: str, limit: int = 20):
    """All news items for this player, newest first."""
    db = _db()
    cursor = db.player_news.find({"player_id": player_id}).sort("published_at", -1).limit(limit)
    out = []
    async for n in cursor:
        n["_id"] = str(n["_id"])
        pub = n.get("published_at")
        n["published_at"] = pub.isoformat() if hasattr(pub, "isoformat") else pub
        out.append(n)
    return {"player_id": player_id, "news": out}


@router.get("/players/{player_id}/recent-games")
async def get_player_recent_games(player_id: str, league_id: Optional[str] = None, limit: int = 10):
    """Per-game performance: date, team, opponent, stat line, fantasy points
    using the league's scoring config (or platform default when no league)."""
    db = _db()
    player = await db.players.find_one({"_id": ObjectId(player_id)})
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    is_goalie = (player.get("position") == "G")

    scoring_cfg = await _scoring_cfg_for(league_id)
    cursor = db.player_game_logs.find({"player_id": player_id}).sort("date_dt", -1).limit(limit)
    games = []
    async for g in cursor:
        # Resolve opponent — game logs don't always store it explicitly. We
        # query the games collection by nhl_game_id to find both teams.
        opponent = None
        home_away = None
        nhl_game_id = g.get("nhl_game_id")
        if nhl_game_id:
            game_doc = await db.games.find_one({"nhl_game_id": nhl_game_id})
            if game_doc:
                home = game_doc.get("home_team_abbr")
                away = game_doc.get("away_team_abbr")
                if g.get("team_abbr") == home:
                    opponent = away
                    home_away = "home"
                else:
                    opponent = home
                    home_away = "away"

        stats = {
            "goals": g.get("goals", 0), "assists": g.get("assists", 0),
            "points": g.get("points", 0), "plus_minus": g.get("plus_minus", 0),
            "shots": g.get("sog", 0), "hits": g.get("hits", 0),
            "blocks": g.get("blocks", 0), "pim": g.get("pim", 0),
            "ppg": g.get("ppg", 0), "shg": g.get("shg", 0),
            "ppp": g.get("ppp", 0), "shp": g.get("shp", 0),
            "saves": g.get("saves", 0),
            "goals_against": g.get("goals_against", 0),
            "wins": g.get("wins", 0), "losses": g.get("losses", 0),
            "shutouts": g.get("shutouts", 0),
            "shots_against": g.get("shots_against", 0),
        }
        fpts = _calc_fpts(stats, is_goalie, scoring_cfg)

        games.append({
            "game_id": str(g["_id"]),
            "nhl_game_id": nhl_game_id,
            "date": str(g.get("date") or ""),
            "team": g.get("team_abbr"),
            "opponent": opponent,
            "home_away": home_away,
            "toi": g.get("toi"),
            "position": g.get("position"),
            "fantasy_points": fpts,
            **stats,
        })
    return {"player_id": player_id, "is_goalie": is_goalie, "games": games}


# Cache NHL career-stats fetches to avoid hammering the public API
_career_cache: dict[int, tuple] = {}
_CAREER_CACHE_TTL = 24 * 60 * 60  # 24h


@router.get("/players/{player_id}/historical-stats")
async def get_player_historical_stats(player_id: str, league_id: Optional[str] = None):
    """Career season-by-season stats from the NHL public API (cached 24h),
    annotated with fantasy points computed against the league's scoring
    config when supplied. Even if the league didn't exist in those years,
    the fantasy column is still populated — that's exactly the spec."""
    db = _db()
    logger = _deps.get("logger")
    player = await db.players.find_one({"_id": ObjectId(player_id)})
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    nhl_id = player.get("nhl_id")
    if not nhl_id:
        return {"player_id": player_id, "seasons": [], "career_totals": None,
                "note": "No NHL ID associated with this player."}

    is_goalie = (player.get("position") == "G")
    scoring_cfg = await _scoring_cfg_for(league_id)

    # Cache lookup
    cached = _career_cache.get(nhl_id)
    now_ts = datetime.now(timezone.utc).timestamp()
    if cached and (now_ts - cached[0]) < _CAREER_CACHE_TTL:
        raw = cached[1]
    else:
        try:
            from nhlpy import NHLClient
            client = NHLClient()
            raw = client.stats.player_career_stats(player_id=int(nhl_id))
            _career_cache[nhl_id] = (now_ts, raw)
        except Exception as e:
            if logger:
                logger.warning("nhlpy career-stats failed for %s: %s", nhl_id, e)
            return {"player_id": player_id, "seasons": [], "career_totals": None,
                    "error": "Career stats unavailable from NHL API."}

    season_totals = (raw or {}).get("seasonTotals") or []
    # Filter to NHL regular-season only
    nhl_reg = [s for s in season_totals
               if s.get("leagueAbbrev") == "NHL" and s.get("gameTypeId") == 2]

    seasons_out = []
    for s in nhl_reg:
        # season is stored as 20232024 → "2023-24"
        season_int = s.get("season")
        season_str = f"{str(season_int)[:4]}-{str(season_int)[6:]}" if season_int else None
        team = s.get("teamName", {}).get("default") if isinstance(s.get("teamName"), dict) else (s.get("teamName") or s.get("teamCommonName") or "")
        if is_goalie:
            stats = {
                "goals_against": s.get("goalsAgainst", 0),
                "saves": s.get("saves", 0),
                "wins": s.get("wins", 0),
                "losses": s.get("losses", 0),
                "shutouts": s.get("shutouts", 0),
                "overtime_losses": s.get("otLosses", 0),
            }
            row = {
                "season": season_str, "team": team,
                "games_played": s.get("gamesPlayed", 0),
                "wins": s.get("wins", 0), "losses": s.get("losses", 0),
                "ot_losses": s.get("otLosses", 0),
                "shutouts": s.get("shutouts", 0),
                "goals_against_avg": s.get("goalsAgainstAvg", 0),
                "save_pct": s.get("savePctg", 0),
                "saves": s.get("saves", 0),
                "shots_against": s.get("shotsAgainst", 0),
            }
        else:
            stats = {
                "goals": s.get("goals", 0), "assists": s.get("assists", 0),
                "points": s.get("points", 0), "plus_minus": s.get("plusMinus", 0),
                "shots": s.get("shots", 0),
                "ppg": s.get("powerPlayGoals", 0), "shg": s.get("shorthandedGoals", 0),
                "ppp": s.get("powerPlayPoints", 0),
                "pim": s.get("pim", 0),
            }
            row = {
                "season": season_str, "team": team,
                "games_played": s.get("gamesPlayed", 0),
                "goals": s.get("goals", 0), "assists": s.get("assists", 0),
                "points": s.get("points", 0),
                "plus_minus": s.get("plusMinus", 0),
                "shots": s.get("shots", 0),
                "shooting_pct": round((s.get("shootingPctg") or 0) * 100, 1),
                "power_play_goals": s.get("powerPlayGoals", 0),
                "power_play_points": s.get("powerPlayPoints", 0),
                "short_handed_goals": s.get("shorthandedGoals", 0),
                "game_winning_goals": s.get("gameWinningGoals", 0),
                "pim": s.get("pim", 0),
                "avg_toi": s.get("avgToi", ""),
                "faceoff_win_pct": round((s.get("faceoffWinningPctg") or 0) * 100, 1),
            }
        row["fantasy_points"] = _calc_fpts(stats, is_goalie, scoring_cfg)
        seasons_out.append(row)

    seasons_out.sort(key=lambda r: r["season"] or "", reverse=True)
    career = (raw or {}).get("careerTotals", {}).get("regularSeason") or {}
    return {
        "player_id": player_id,
        "is_goalie": is_goalie,
        "seasons": seasons_out,
        "career_totals": career or None,
    }


@router.get("/players/{player_id}/recent-performance")
async def get_player_recent_performance(player_id: str, league_id: Optional[str] = None):
    """Aggregated stats over rolling windows: last 7d, prior 7d, last 14d,
    last 30d. Fantasy points use the league's scoring config when supplied."""
    db = _db()
    player = await db.players.find_one({"_id": ObjectId(player_id)})
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    is_goalie = (player.get("position") == "G")
    scoring_cfg = await _scoring_cfg_for(league_id)
    now = datetime.now(timezone.utc)

    def _window(days_start: int, days_end: int):
        return {
            "$gte": now - timedelta(days=days_end),
            "$lt": now - timedelta(days=days_start),
        }

    windows = {
        "last_7d":  _window(0, 7),
        "prev_7d":  _window(7, 14),
        "last_14d": _window(0, 14),
        "last_30d": _window(0, 30),
    }

    out: dict[str, dict] = {}
    for label, rng in windows.items():
        cursor = db.player_game_logs.find({
            "player_id": player_id,
            "date_dt": rng,
        })
        agg = {
            "games_played": 0, "goals": 0, "assists": 0, "points": 0,
            "plus_minus": 0, "shots": 0, "hits": 0, "blocks": 0,
            "pim": 0, "ppg": 0, "shg": 0, "ppp": 0, "shp": 0,
            "saves": 0, "goals_against": 0, "wins": 0, "losses": 0,
            "shutouts": 0, "shots_against": 0,
        }
        async for g in cursor:
            agg["games_played"] += 1
            agg["goals"] += g.get("goals", 0)
            agg["assists"] += g.get("assists", 0)
            agg["points"] += g.get("points", 0)
            agg["plus_minus"] += g.get("plus_minus", 0)
            agg["shots"] += g.get("sog", 0)
            agg["hits"] += g.get("hits", 0)
            agg["blocks"] += g.get("blocks", 0)
            agg["pim"] += g.get("pim", 0)
            agg["ppg"] += g.get("ppg", 0)
            agg["shg"] += g.get("shg", 0)
            agg["saves"] += g.get("saves", 0)
            agg["goals_against"] += g.get("goals_against", 0)
            agg["wins"] += g.get("wins", 0)
            agg["losses"] += g.get("losses", 0)
            agg["shutouts"] += g.get("shutouts", 0)
            agg["shots_against"] += g.get("shots_against", 0)
        agg["fantasy_points"] = _calc_fpts(agg, is_goalie, scoring_cfg)
        out[label] = agg

    return {"player_id": player_id, "is_goalie": is_goalie, "windows": out}


@router.get("/players/{player_id}/cross-league-ownership")
async def get_player_cross_league_ownership(player_id: str, request: Request):
    """List of the user's leagues, with which team (if any) owns this player
    in each. Used by the Cross-League Ownership tab."""
    db = _db()
    user = await _get_user(request)
    # Discover all leagues this user has a team in (or is commissioner of)
    my_team_leagues = await db.teams.distinct("league_id", {"owner_id": user["_id"]})
    commish_leagues = await db.leagues.distinct("_id", {"commissioner_id": user["_id"]})
    league_ids = list({*my_team_leagues, *[str(lid) for lid in commish_leagues]})

    if not league_ids:
        return {"player_id": player_id, "leagues": []}

    leagues = await db.leagues.find({"_id": {"$in": [ObjectId(lid) for lid in league_ids]}}).to_list(100)

    rows = []
    for lg in leagues:
        lid = str(lg["_id"])
        # Find which team in this league rosters the player
        team = await db.teams.find_one({"league_id": lid, "roster": player_id})
        my_team = await db.teams.find_one({"league_id": lid, "owner_id": user["_id"]})
        rows.append({
            "league_id": lid,
            "league_name": lg.get("name"),
            "scoring_format": lg.get("scoring_format"),
            "owned_by_team_id": str(team["_id"]) if team else None,
            "owned_by_team_name": team.get("name") if team else None,
            "owned_by_owner_name": team.get("owner_name") if team else None,
            "owned_by_me": bool(team and my_team and str(team["_id"]) == str(my_team["_id"])),
            "is_free_agent": team is None,
        })
    rows.sort(key=lambda r: (not r["owned_by_me"], r["is_free_agent"], r["league_name"] or ""))
    return {"player_id": player_id, "leagues": rows}


@router.get("/players/{player_id}/transactions")
async def get_player_transactions(player_id: str, league_id: Optional[str] = None, limit: int = 50):
    """All fantasy transactions involving this player: drafts, adds, drops,
    waiver wins, and trades. Filtered to one league when `league_id` given."""
    db = _db()
    query = {
        "$or": [
            {"metadata.player_id": player_id},
            {"metadata.player_ids": player_id},
        ],
        "event_type": {"$in": [
            "roster_add", "roster_drop", "trade_executed",
            "waiver_won", "draft_pick",
        ]},
    }
    if league_id:
        query["league_id"] = league_id
    cursor = db.activity_feed.find(query).sort("created_at", -1).limit(limit)
    out = []
    async for ev in cursor:
        ev["_id"] = str(ev["_id"])
        ts = ev.get("created_at")
        ev["created_at"] = ts.isoformat() if hasattr(ts, "isoformat") else ts
        out.append(ev)
    return {"player_id": player_id, "transactions": out}


@router.get("/players/{player_id}/usage")
async def get_player_usage(player_id: str, league_id: str, request: Request):
    """Per-week usage of this player in a specific league. For each completed
    week's matchup, returns: which team rostered the player, what slot they
    filled (active C/LW/RW/D/G or Bench/IR), and matchup result.

    NOTE: persistent slot history requires team.lineup snapshots per week.
    Today we approximate using the team's current `lineup` field (set by
    `POST /api/roster/{team_id}/lineup`); historical weeks default to
    "active — slot unknown" until weekly snapshotting ships.
    """
    db = _db()
    user = await _get_user(request)

    # Find the team in this league that rostered this player at any point
    teams = await db.teams.find(
        {"league_id": league_id, "roster": player_id},
        {"_id": 1, "name": 1, "lineup": 1, "owner_id": 1},
    ).to_list(50)

    if not teams:
        return {"player_id": player_id, "league_id": league_id, "weeks": []}

    # All weekly matchups in this league
    matchups = await db.matchups.find({"league_id": league_id}).sort("week", 1).to_list(200)
    if not matchups:
        return {"player_id": player_id, "league_id": league_id, "weeks": []}

    weeks_out = []
    for m in matchups:
        team_id = None
        team_name = None
        for t in teams:
            tid = str(t["_id"])
            if m.get("home_team_id") == tid or m.get("away_team_id") == tid:
                team_id = tid
                team_name = t.get("name")
                break
        if not team_id:
            continue
        # Determine slot from current lineup (best available approximation)
        owning = next((t for t in teams if str(t["_id"]) == team_id), None)
        slot_info = (owning or {}).get("lineup", {}).get(player_id) or {}
        section = slot_info.get("section") or "active"
        slot = slot_info.get("slot")

        is_home = m.get("home_team_id") == team_id
        opp_name = m.get("away_team_name") if is_home else m.get("home_team_name")
        my_score = m.get("home_score" if is_home else "away_score") or 0
        opp_score = m.get("away_score" if is_home else "home_score") or 0
        result = None
        if (m.get("status") or "").lower() in ("completed", "final"):
            if my_score > opp_score: result = "W"
            elif my_score < opp_score: result = "L"
            else: result = "T"

        weeks_out.append({
            "week": m.get("week"),
            "team_id": team_id,
            "team_name": team_name,
            "opponent_name": opp_name,
            "section": section,    # "forward"/"defense"/"goalie"/"bench"/"ir"/"active"
            "slot": slot,          # "C", "LW", "RW", "D1", "G1", etc., or None
            "is_active": section in ("forward", "defense", "goalie", "active"),
            "result": result,
            "score_for": my_score,
            "score_against": opp_score,
            "status": m.get("status"),
        })
    return {"player_id": player_id, "league_id": league_id, "weeks": weeks_out}



@router.post("/players/sync-status-flags")
async def sync_status_flags(request: Request, league_id: Optional[str] = None):
    """Iter 232N.3 — Admin/cron trigger for the status-flag change detector.

    Sweeps every player (or every player in the given league — union of
    all rostered pids), diffs their currently-computed status_flags
    against the stored snapshot, and emits `player_status_change`
    websocket events + persistent notifications for every flip.

    Guarded to admins only. Safe to run repeatedly — first run seeds
    the snapshot silently, subsequent runs only fire on genuine changes.
    """
    user = await _get_user(request)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin only")

    db = _db()
    from services.player_status_change_detector import detect_and_emit_status_changes

    if league_id:
        # Union of every roster in the league.
        pids: set[str] = set()
        async for team in db.teams.find(
            {"league_id": league_id}, {"roster": 1},
        ):
            for p in team.get("roster") or []:
                pids.add(str(p))
        # Also include every player currently on the players collection
        # that has an amateur/pro flag — cheap and catches recall events
        # on players not currently rostered.
        player_ids = list(pids)
    else:
        player_ids = [
            str(p["_id"]) async for p in db.players.find({}, {"_id": 1})
        ]

    return await detect_and_emit_status_changes(
        db,
        player_ids,
        broadcast_fn=_deps.get("broadcast_to_room"),
        create_notification_fn=_deps.get("create_notification"),
        league_id_for_undrafted=league_id,
    )
