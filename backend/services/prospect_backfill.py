"""Iter 231ah — Backfill the prospect pool from the last 6 NHL draft
classes (2020-2025) via the NHL public API.

Endpoint: `https://api-web.nhle.com/v1/draft/picks/{year}/all`

Each year returns ~217-225 picks with: firstName, lastName, positionCode,
height, weight, countryCode, amateurClubName, amateurLeague, teamAbbrev
(drafting NHL team), round, pickInRound, overallPick.

Upsert key: synthetic `nhl_id = -2_000_000 - (year * 1000 + overall_pick)`
so re-running the backfill is idempotent and we don't collide with the
existing prospect `nhl_id = -1000000 - x` namespace.

Schema written matches the existing 30-prospect schema (see
db.players.find_one({'player_type': 'prospect'}) for reference):

    name, display_name, nhl_id, player_type="prospect",
    position, team (amateur), team_name ("{league} · {amateur}"),
    amateur_league, player_status="amateur", season ("{year-1}-{year}"),
    draft_year, draft_round, draft_pick_overall, drafted_by_team,
    country_code, height_inches, weight_lbs, seeded_at,
    seed_source="nhl_draft_picks_api"
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

import httpx

logger = logging.getLogger("prospect_backfill")
logger.setLevel(logging.INFO)


NHL_DRAFT_PICKS_URL = "https://api-web.nhle.com/v1/draft/picks/{year}/all"
DEFAULT_YEARS = (2020, 2021, 2022, 2023, 2024, 2025)


def _synthetic_nhl_id(year: int, overall_pick: int) -> int:
    """Generate a stable, collision-free synthetic NHL id for a draft
    pick. Negative numbers reserved for non-NHL-API entries.

    Pattern: `-2_000_000 - (year * 1000 + overall_pick)`. Year 2025
    pick 1 → `-2_002_026_000 - 1 = -2_002_025_001` (negative, unique).
    Reserved range: -2_000_000 to -3_000_000.
    """
    return -2_000_000 - (year * 1000 + overall_pick)


def _normalize_pick(pick: Dict[str, Any], year: int) -> Dict[str, Any]:
    """Transform one NHL API pick payload into our `players` schema."""
    first = (pick.get("firstName") or {}).get("default") or ""
    last = (pick.get("lastName") or {}).get("default") or ""
    name = f"{first} {last}".strip()
    amateur_club = pick.get("amateurClubName") or ""
    amateur_league = pick.get("amateurLeague") or ""
    team_name = (
        f"{amateur_league} · {amateur_club}".strip(" ·")
        if amateur_club or amateur_league
        else "Amateur"
    )
    overall = int(pick.get("overallPick") or 0)
    # Drafted-by NHL team — `teamAbbrev` is the canonical 3-letter.
    drafted_by = pick.get("teamAbbrev") or ""
    drafted_by_name = (pick.get("teamName") or {}).get("default") or ""

    return {
        "name": name,
        "display_name": name,
        "nhl_id": _synthetic_nhl_id(year, overall),
        "player_type": "prospect",
        "player_status": "amateur",
        "position": pick.get("positionCode") or "F",
        "team": amateur_club,            # amateur team for UI display.
        "team_name": team_name,
        "amateur_league": amateur_league,
        "season": f"{year - 1}-{year}",  # eg. "2024-2025" for 2025 draft.
        "draft_year": year,
        "draft_round": int(pick.get("round") or 0),
        "draft_pick_overall": overall,
        "draft_pick_in_round": int(pick.get("pickInRound") or 0),
        "drafted_by_team": drafted_by,
        "drafted_by_team_name": drafted_by_name,
        "country_code": pick.get("countryCode") or "",
        "height_inches": pick.get("height"),
        "weight_lbs": pick.get("weight"),
        # Default per-game stats so the pool ranking endpoints don't
        # blow up when sorting by points/games_played.
        "games_played": 0,
        "goals": 0,
        "assists": 0,
        "points": 0,
        "plus_minus": 0,
        "seeded_at": datetime.now(timezone.utc).isoformat(),
        "seed_source": "nhl_draft_picks_api",
    }


async def fetch_year(year: int, client: httpx.AsyncClient) -> List[Dict[str, Any]]:
    """Fetch + normalize one draft year's picks. Returns [] on HTTP error
    so a single year's outage doesn't blow up the whole backfill."""
    url = NHL_DRAFT_PICKS_URL.format(year=year)
    try:
        resp = await client.get(url, timeout=15.0)
        resp.raise_for_status()
        picks = resp.json().get("picks") or []
        logger.info(f"prospect_backfill year={year}: fetched {len(picks)} picks")
        return [_normalize_pick(p, year) for p in picks]
    except Exception as e:
        logger.error(f"prospect_backfill year={year}: fetch failed — {e}")
        return []


async def backfill_prospects(
    db,
    years: Tuple[int, ...] = DEFAULT_YEARS,
) -> Dict[str, Any]:
    """Pull `picks` for every year in `years` and upsert into players
    keyed on the synthetic `nhl_id`. Returns per-year counts + total
    inserted/updated for observability.

    Idempotent — re-running on the same DB just refreshes the upserts.
    """
    started = datetime.now(timezone.utc)
    per_year: Dict[str, Dict[str, int]] = {}
    inserted_total = 0
    updated_total = 0

    async with httpx.AsyncClient(headers={"User-Agent": "DynastyDreams/1.0"}) as client:
        # Fetch all years in parallel.
        all_picks: List[List[Dict[str, Any]]] = await asyncio.gather(
            *(fetch_year(y, client) for y in years)
        )

    for year, picks in zip(years, all_picks):
        inserted = 0
        updated = 0
        for doc in picks:
            r = await db.players.update_one(
                {"nhl_id": doc["nhl_id"]},
                {"$set": doc, "$setOnInsert": {"created_at": started.isoformat()}},
                upsert=True,
            )
            if r.upserted_id is not None:
                inserted += 1
            elif r.modified_count:
                updated += 1
        per_year[str(year)] = {"fetched": len(picks), "inserted": inserted, "updated": updated}
        inserted_total += inserted
        updated_total += updated
        logger.info(
            f"prospect_backfill year={year} inserted={inserted} updated={updated}"
        )

    return {
        "started_at": started.isoformat(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "years": list(years),
        "per_year": per_year,
        "inserted_total": inserted_total,
        "updated_total": updated_total,
        "total_in_pool": await db.players.count_documents({"player_type": "prospect"}),
    }


async def get_pool_stats(db) -> Dict[str, Any]:
    """Read-only: counts of the current prospect pool by year + source."""
    by_year_cursor = db.players.aggregate([
        {"$match": {"player_type": "prospect"}},
        {"$group": {"_id": "$draft_year", "count": {"$sum": 1}}},
        {"$sort": {"_id": -1}},
    ])
    by_year = []
    async for row in by_year_cursor:
        by_year.append({"draft_year": row["_id"], "count": row["count"]})
    by_source_cursor = db.players.aggregate([
        {"$match": {"player_type": "prospect"}},
        {"$group": {"_id": "$seed_source", "count": {"$sum": 1}}},
    ])
    by_source = []
    async for row in by_source_cursor:
        by_source.append({"source": row["_id"], "count": row["count"]})
    return {
        "total_prospects": await db.players.count_documents({"player_type": "prospect"}),
        "by_draft_year": by_year,
        "by_seed_source": by_source,
    }
