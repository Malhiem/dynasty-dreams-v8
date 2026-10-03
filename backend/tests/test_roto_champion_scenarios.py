"""Iter 232N.91j — Rotisserie Champion: Season-Only vs Condensed-Playoff

Separates two champion-selection scenarios that were previously conflated:

1. Season-only (playoffs disabled):
   - Champion = regular-season category-points leader
   - Expects: the team with the highest full-season roto total

2. Condensed-playoff (playoffs enabled, fresh totals):
   - Champion = playoff-period category-points leader (+ seed bonuses if configured)
   - Expects: a DIFFERENT team that leads playoff-only stats

3. Seed bonus swings winner:
   - A large seed bonus can change which team wins the condensed playoff

Each scenario zeroes all player stats first, then seeds controlled values
so that the regular-season leader and playoff-period leader are provably
different teams.
"""
import os
import pytest
import requests
from pymongo import MongoClient
from bson import ObjectId

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ROTO_LEAGUE_ID = "69e46af167999bfb85c39629"
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@e2e.dynastydreams.com")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "e2e-admin-password")
TEST_YEAR = 2097


@pytest.fixture(scope="module")
def auth_headers():
    resp = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    assert resp.status_code == 200
    return {
        "Authorization": f"Bearer {resp.json()['access_token']}",
        "Content-Type": "application/json",
    }


@pytest.fixture(scope="module")
def db():
    client = MongoClient(os.environ["MONGO_URL"])
    yield client[os.environ["DB_NAME"]]
    client.close()


@pytest.fixture(scope="module")
def seeded_league(db, auth_headers):
    """Zero all player stats, then seed controlled values so:
    - Team[0] leads regular season (goals=100)
    - Team[-1] leads playoff period (goals=44)
    These are deterministically different teams.
    """
    teams = list(db.teams.find({"league_id": ROTO_LEAGUE_ID}).sort("_id", 1))

    # Collect all player IDs across the league
    all_pids = set()
    for t in teams:
        for pid in (t.get("roster") or []):
            all_pids.add(pid)

    # Zero everyone
    db.players.update_many(
        {"_id": {"$in": [ObjectId(p) for p in all_pids]}},
        {"$set": {"season_stats": {}, "period_stats": {}}},
    )

    # Seed one player per team with diverging stats
    first_pids = []
    for i, t in enumerate(teams):
        roster = t.get("roster") or []
        if roster:
            pid = roster[0]
            first_pids.append(pid)
            reg_goals = 100 - (i * 5)   # 100, 95, 90, …
            po_goals = 5 + (i * 3)      # 5, 8, 11, …
            db.players.update_one(
                {"_id": ObjectId(pid)},
                {"$set": {
                    "season_stats": {"goals": reg_goals},
                    "period_stats": {"19": {"goals": po_goals}},
                }},
            )

    yield teams

    # Restore: clear test-year snapshots and championship flags
    _cleanup(db)
    # Re-enable playoffs
    requests.put(
        f"{BASE_URL}/api/leagues/{ROTO_LEAGUE_ID}",
        headers=auth_headers,
        json={"playoffs_enabled": True},
    )


def _cleanup(db):
    db.teams.update_many(
        {"league_id": ROTO_LEAGUE_ID},
        {"$unset": {"championship_won_at": ""}},
    )
    db.leagues.update_one(
        {"_id": ObjectId(ROTO_LEAGUE_ID)},
        {"$set": {"current_season_status": "in_progress"}},
    )
    db.league_seasons.delete_many(
        {"league_id": ROTO_LEAGUE_ID, "season_year": TEST_YEAR},
    )


def _standings(auth_headers):
    resp = requests.get(
        f"{BASE_URL}/api/leagues/{ROTO_LEAGUE_ID}/roto/standings",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    return resp.json()


def _complete(auth_headers):
    resp = requests.post(
        f"{BASE_URL}/api/leagues/{ROTO_LEAGUE_ID}/complete-season",
        headers=auth_headers,
        json={"season_year": TEST_YEAR},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _leader(standings):
    totals = standings["totals"]
    tid, td = max(totals.items(), key=lambda x: x[1]["total_points"])
    return tid, td["team_name"], td["total_points"]


class TestSeasonOnlyChampion:
    """Playoffs disabled → champion is the regular-season leader."""

    def test_champion_is_season_leader(self, auth_headers, db, seeded_league):
        _cleanup(db)
        requests.put(
            f"{BASE_URL}/api/leagues/{ROTO_LEAGUE_ID}",
            headers=auth_headers,
            json={"playoffs_enabled": False},
        )

        standings = _standings(auth_headers)
        assert not standings.get("fresh_totals")
        _, leader_name, leader_pts = _leader(standings)

        data = _complete(auth_headers)
        assert data["champion"] == leader_name, (
            f"Season-only: expected '{leader_name}' ({leader_pts} pts), "
            f"got '{data['champion']}'"
        )
        _cleanup(db)


class TestCondensedPlayoffChampion:
    """Condensed playoffs with fresh totals → champion is the playoff leader."""

    def test_champion_is_playoff_leader(self, auth_headers, db, seeded_league):
        _cleanup(db)
        requests.put(
            f"{BASE_URL}/api/leagues/{ROTO_LEAGUE_ID}",
            headers=auth_headers,
            json={
                "playoffs_enabled": True,
                "playoff_format": "condensed_roto",
                "playoff_roto_fresh_totals": True,
                "playoff_roto_seed_bonuses": {},
            },
        )

        standings = _standings(auth_headers)
        assert standings.get("fresh_totals") is True
        _, leader_name, leader_pts = _leader(standings)

        data = _complete(auth_headers)
        assert data["champion"] == leader_name, (
            f"Condensed playoff: expected '{leader_name}' ({leader_pts} pts), "
            f"got '{data['champion']}'"
        )
        _cleanup(db)

    def test_season_and_playoff_leaders_differ(self, auth_headers, db, seeded_league):
        """Prove the two code paths select different champions."""
        # Season standings
        requests.put(
            f"{BASE_URL}/api/leagues/{ROTO_LEAGUE_ID}",
            headers=auth_headers,
            json={"playoffs_enabled": False},
        )
        season_leader_tid, season_leader_name, _ = _leader(_standings(auth_headers))

        # Playoff standings
        requests.put(
            f"{BASE_URL}/api/leagues/{ROTO_LEAGUE_ID}",
            headers=auth_headers,
            json={
                "playoffs_enabled": True,
                "playoff_format": "condensed_roto",
                "playoff_roto_fresh_totals": True,
                "playoff_roto_seed_bonuses": {},
            },
        )
        playoff_leader_tid, playoff_leader_name, _ = _leader(_standings(auth_headers))

        assert season_leader_tid != playoff_leader_tid, (
            f"Season leader ({season_leader_name}) should differ from "
            f"playoff leader ({playoff_leader_name}) with controlled test data"
        )


class TestSeedBonusSwingsWinner:
    """A large seed bonus should change who wins."""

    def test_bonus_changes_champion(self, auth_headers, db, seeded_league):
        _cleanup(db)

        # Playoff standings without bonuses
        requests.put(
            f"{BASE_URL}/api/leagues/{ROTO_LEAGUE_ID}",
            headers=auth_headers,
            json={
                "playoffs_enabled": True,
                "playoff_format": "condensed_roto",
                "playoff_roto_fresh_totals": True,
                "playoff_roto_seed_bonuses": {},
            },
        )
        no_bonus = _standings(auth_headers)
        natural_tid, natural_name, natural_pts = _leader(no_bonus)

        # Get seed 1 (regular-season leader)
        requests.put(
            f"{BASE_URL}/api/leagues/{ROTO_LEAGUE_ID}",
            headers=auth_headers,
            json={"playoffs_enabled": False},
        )
        season = _standings(auth_headers)
        season_sorted = sorted(
            season["totals"].items(),
            key=lambda x: -x[1]["total_points"],
        )
        seed1_tid = season_sorted[0][0]

        # Determine a team that is NOT the natural playoff leader,
        # give it a massive bonus to overtake
        if seed1_tid != natural_tid:
            # Seed 1 trails in playoffs — give it a huge bonus
            seed1_playoff_pts = no_bonus["totals"][seed1_tid]["total_points"]
            gap = natural_pts - seed1_playoff_pts
            bonus_val = int(gap) + 20
            bonuses = {"1": bonus_val}
            expected_winner = season_sorted[0][1]["team_name"]
        else:
            # Seed 1 is also the natural leader — boost seed 2 instead
            seed2_tid = season_sorted[1][0]
            seed2_playoff_pts = no_bonus["totals"][seed2_tid]["total_points"]
            gap = natural_pts - seed2_playoff_pts
            bonus_val = int(gap) + 20
            bonuses = {"2": bonus_val}
            expected_winner = season_sorted[1][1]["team_name"]

        # Apply bonus and complete season
        requests.put(
            f"{BASE_URL}/api/leagues/{ROTO_LEAGUE_ID}",
            headers=auth_headers,
            json={
                "playoffs_enabled": True,
                "playoff_format": "condensed_roto",
                "playoff_roto_fresh_totals": True,
                "playoff_roto_seed_bonuses": bonuses,
            },
        )
        data = _complete(auth_headers)
        assert data["champion"] == expected_winner, (
            f"Seed bonus should swing winner to '{expected_winner}', "
            f"got '{data['champion']}'"
        )

        # Restore
        requests.put(
            f"{BASE_URL}/api/leagues/{ROTO_LEAGUE_ID}",
            headers=auth_headers,
            json={"playoff_roto_seed_bonuses": {}},
        )
        _cleanup(db)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
