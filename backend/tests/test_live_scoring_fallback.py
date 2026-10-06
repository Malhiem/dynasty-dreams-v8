"""A failed external poll preserves the public summary shape and marks stale data."""
from types import SimpleNamespace
import pytest

@pytest.mark.asyncio
@pytest.mark.parametrize("cached", [None, {"date": "2026-09-30", "games": [{"id": 1}], "games_processed": 1, "players_updated": 2, "playoff_games": 0, "polled_at": "previous"}])
async def test_failed_nhl_poll_keeps_summary_contract(monkeypatch, cached):
    import nhlpy
    from live_scoring_worker import run_once
    class State:
        async def find_one(self, query):
            assert query == {"_id": "live_scoring"}
            return {"latest": cached} if cached else None
    def fail_schedule():
        raise OSError("private upstream diagnostic")
    monkeypatch.setattr(nhlpy, "NHLClient", lambda: SimpleNamespace(schedule=SimpleNamespace(daily_schedule=fail_schedule)))
    result = await run_once(SimpleNamespace(system_state=State()))
    assert result["stale"] is True
    assert result["error"] == "NHL data unavailable"
    assert {"date", "games", "games_processed", "players_updated", "playoff_games", "polled_at"} <= result.keys()
    assert result["games"] == (cached["games"] if cached else [])
    if cached:
        assert "stale" not in cached
