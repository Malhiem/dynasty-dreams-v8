"""Live ingestion must preserve ownership at puck drop across correction polls."""
from datetime import datetime, timezone, timedelta
import pytest
from services.live_roster_allocation import qualifies


@pytest.mark.parametrize("team,at,expected", [
    ("A", -1, True), ("B", -1, False),
    ("A", 0, False), ("B", 0, True),
    ("A", 1, False), ("B", 1, True),
])
def test_half_open_transfer_boundary(team, at, expected):
    transfer = datetime(2026, 10, 5, 20, tzinfo=timezone.utc)
    context = ({1: transfer + timedelta(seconds=at)},
               {("p", "L"): [("A", transfer - timedelta(days=1), transfer), ("B", transfer, None)]},
               {}, {})
    assert qualifies("p", team, "L", "1", ["p"] if team == "B" else [], {}, context) is expected


def test_bench_and_unowned_gaps_do_not_receive_points():
    at = datetime(2026, 10, 5, 20, tzinfo=timezone.utc)
    context = ({1: at}, {("p", "L"): [("B", at - timedelta(hours=1), None)]},
               {("p", "B", "L"): [(at - timedelta(hours=1), at + timedelta(hours=1), False)]}, {})
    assert not qualifies("p", "B", "L", "1", ["p"], {}, context)
    context[1][("p", "L")] = [("A", at - timedelta(days=1), at - timedelta(seconds=1))]
    assert not qualifies("p", "B", "L", "1", ["p"], {}, context)


def test_legacy_current_lineup_does_not_credit_bench():
    context = ({}, {}, {}, {})
    assert not qualifies("p", "B", "L", "unknown", ["p"], {"p": {"section": "bench"}}, context)
    assert qualifies("p", "B", "L", "unknown", ["p"], {"p": {"section": "forward"}}, context)
