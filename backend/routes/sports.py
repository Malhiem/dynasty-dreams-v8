"""Sport-agnostic catalogue — extracted from server.py (iter 115).

Endpoint:
    GET /api/sports — list of supported sports with their positions and a
    live player_count (NHL only for now; other sports return 0 until their
    ingestion lands).
"""
from __future__ import annotations

from fastapi import APIRouter


router = APIRouter()
_deps: dict = {}


def setup(deps: dict) -> None:
    _deps.update(deps)


def _db(): return _deps["db"]


@router.get("/sports")
async def get_supported_sports():
    db = _db()
    return [
        {
            "id": "nhl", "name": "NHL",
            "full_name": "National Hockey League",
            "positions": ["C", "LW", "RW", "D", "G"],
            "active": True,
            "player_count": await db.players.count_documents({"season": "2025-2026"}),
        },
        {
            "id": "nfl", "name": "NFL",
            "full_name": "National Football League",
            "positions": ["QB", "RB", "WR", "TE", "K", "DEF"],
            "active": False, "player_count": 0,
        },
        {
            "id": "nba", "name": "NBA",
            "full_name": "National Basketball Association",
            "positions": ["PG", "SG", "SF", "PF", "C"],
            "active": False, "player_count": 0,
        },
        {
            "id": "mlb", "name": "MLB",
            "full_name": "Major League Baseball",
            "positions": ["C", "1B", "2B", "3B", "SS", "OF", "SP", "RP"],
            "active": False, "player_count": 0,
        },
    ]
