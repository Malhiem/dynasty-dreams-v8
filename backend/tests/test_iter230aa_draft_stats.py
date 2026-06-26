"""
Iter 230aa — `/drafts/{id}/stats` endpoint backs the Draft Live tile's
compact metrics strip (current pick / total picks, avg time per pick,
fastest + slowest team, floor trades). This test seeds a draft with
hand-crafted pick timestamps and asserts every aggregate.
"""
import os
import sys
import pytest
from bson import ObjectId
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from httpx import AsyncClient


def _backend_url():
    env = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", ".env")
    with open(env) as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip()
    raise RuntimeError("REACT_APP_BACKEND_URL not found")


BASE = _backend_url()


async def _connect_db():
    from motor.motor_asyncio import AsyncIOMotorClient
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
    return AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


@pytest.mark.asyncio
async def test_draft_stats_aggregates_per_team_and_overall():
    db = await _connect_db()
    league_id = str(ObjectId())
    draft_id = ObjectId()
    started_at = datetime.now(timezone.utc).replace(microsecond=0)

    # Pick cadence (seconds elapsed from `started_at`):
    #   pick 1 (TOR): 10s  → delta 10s
    #   pick 2 (HC):  70s  → delta 60s
    #   pick 3 (TOR): 80s  → delta 10s
    #   pick 4 (HC): 800s  → delta 720s
    # Per-team averages → TOR avg 10s (2 picks), HC avg 390s (2 picks).
    # Overall avg = (10 + 60 + 10 + 720) / 4 = 200s.
    cadence = [(10, "TOR"), (70, "HC"), (80, "TOR"), (800, "HC")]
    picks = []
    for i, (off, team) in enumerate(cadence, start=1):
        picks.append({
            "round": (i - 1) // 2 + 1,
            "pick_in_round": ((i - 1) % 2) + 1,
            "overall": i,
            "team": team,
            "player_id": f"player_{i}",
            "player": {"name": f"P{i}"},
            "picked_by": "test",
            "timestamp": (started_at + timedelta(seconds=off)).isoformat().replace("+00:00", "Z"),
        })

    await db.drafts.insert_one({
        "_id": draft_id,
        "league_id": league_id,
        "name": "iter230aa stats draft",
        "status": "active",
        "team_abbrs": ["TOR", "HC"],
        "team_map": {
            "TOR": {"id": "t1", "name": "Toronto"},
            "HC":  {"id": "t2", "name": "Hamilton"},
        },
        "snake_draft": True,
        "total_rounds": 3,
        "current_pick": 5,
        "picks": picks,
        "started_at": started_at.isoformat().replace("+00:00", "Z"),
    })

    try:
        async with AsyncClient(base_url=BASE, timeout=30) as client:
            r = await client.get(f"/api/drafts/{draft_id}/stats")
            assert r.status_code == 200, r.text
            s = r.json()

            assert s["current_pick"] == 5
            assert s["total_picks"] == 6   # 3 rounds × 2 teams
            assert s["picks_made"] == 4

            # Overall avg = 200s (computed above)
            assert s["avg_seconds_per_pick"] is not None
            assert abs(s["avg_seconds_per_pick"] - 200.0) < 0.5, s

            # TOR is fastest @ 10s avg, HC slowest @ 390s avg.
            assert s["fastest"]["team"] == "TOR"
            assert abs(s["fastest"]["avg_seconds"] - 10.0) < 0.5, s["fastest"]
            assert s["fastest"]["picks"] == 2

            assert s["slowest"]["team"] == "HC"
            assert abs(s["slowest"]["avg_seconds"] - 390.0) < 0.5, s["slowest"]
            assert s["slowest"]["picks"] == 2

            # No trades seeded → 0.
            assert s["floor_trades"] == 0
    finally:
        await db.drafts.delete_one({"_id": draft_id})


@pytest.mark.asyncio
async def test_draft_stats_no_picks_returns_null_aggregates():
    """A freshly-started draft with zero picks should return stable
    null fields rather than 500-ing or omitting keys."""
    db = await _connect_db()
    draft_id = ObjectId()
    await db.drafts.insert_one({
        "_id": draft_id,
        "league_id": str(ObjectId()),
        "status": "scheduled",
        "team_abbrs": ["A", "B", "C"],
        "total_rounds": 5,
        "current_pick": 1,
        "picks": [],
    })
    try:
        async with AsyncClient(base_url=BASE, timeout=30) as client:
            r = await client.get(f"/api/drafts/{draft_id}/stats")
            assert r.status_code == 200, r.text
            s = r.json()
            assert s["total_picks"] == 15
            assert s["picks_made"] == 0
            assert s["avg_seconds_per_pick"] is None
            assert s["fastest"] is None
            assert s["slowest"] is None
            assert s["floor_trades"] == 0
    finally:
        await db.drafts.delete_one({"_id": draft_id})
