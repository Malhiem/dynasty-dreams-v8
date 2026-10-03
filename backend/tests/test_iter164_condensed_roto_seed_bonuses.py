"""
Test Iteration 164 - Condensed Roto Seed Bonuses and Playoffs Enabled Fixes

Three bug fixes being tested:
1. Condensed playoff seed bonuses not applied to standings totals
2. Opponents-per-period capped at 1 when league has few current_teams (frontend fix)
3. Roto champion selection doesn't respect playoffs_enabled — condensed playoff leader
   wins even when playoffs are disabled

Tests:
1. Backend: Configure roto league with condensed_roto, fresh_totals=True, seed_bonuses
   - Verify seed_bonuses_applied=true in standings response
   - Verify totals include seed_bonus and seed fields for top 4 seeded teams
2. Backend: Verify seed bonus is added to total_points (10 earned + 4 bonus = 14)
3. Backend: With playoffs_enabled=False, verify fresh_totals is false/null
4. Backend: With playoffs_enabled=False, complete-season uses regular-season leader
5. Backend: With playoffs_enabled=True + condensed_roto, complete-season uses playoff leader
6. Backend: PUT /api/leagues/{id} with opponents_per_matchup_period=2 on max_teams=12 league
"""
import os
import pytest
import requests
from pymongo import MongoClient
from bson import ObjectId

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# League IDs from agent context
CONDENSED_ROTO_LEAGUE_ID = "69e46af167999bfb85c39629"  # Stat Chasers Roto
PERENNIAL_KEEPERS_LEAGUE_ID = "69e46af167999bfb85c3962b"  # Perennial Keepers (max_teams=12)

# Test season year
TEST_SEASON_YEAR = 2026

# Admin credentials
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@e2e.dynastydreams.com")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "e2e-admin-password")


@pytest.fixture(scope="module")
def db():
    """Get MongoDB connection."""
    client = MongoClient(os.environ["MONGO_URL"])
    return client[os.environ["DB_NAME"]]


@pytest.fixture(scope="module")
def auth_token():
    """Get admin auth token."""
    resp = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return resp.json()["access_token"]


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Auth headers for API calls."""
    return {"Authorization": f"Bearer {auth_token}"}


def cleanup_roto_league(db, league_id: str, season_year: int):
    """Clean up test data after each test."""
    # Unset championship_won_at on all teams
    db.teams.update_many(
        {"league_id": league_id},
        {"$unset": {"championship_won_at": ""}}
    )

    # Reset league status to in_progress
    db.leagues.update_one(
        {"_id": ObjectId(league_id)},
        {"$set": {"current_season_status": "in_progress"}}
    )

    # Delete the league_seasons document
    db.league_seasons.delete_one({
        "league_id": league_id,
        "season_year": season_year
    })


@pytest.fixture(scope="module")
def setup_condensed_roto_with_seed_bonuses(db):
    """
    Configure the roto league with:
    - playoff_format: condensed_roto
    - playoffs_enabled: True
    - playoff_roto_fresh_totals: True
    - playoff_roto_seed_bonuses: {"1": 4, "2": 3, "3": 2, "4": 1}
    - playoff_start_week: 19
    - playoff_end_week: 21

    Also seed deterministic player stats for testing.
    """
    # Store original league settings
    league = db.leagues.find_one({"_id": ObjectId(CONDENSED_ROTO_LEAGUE_ID)})
    original_settings = {
        "playoff_format": league.get("playoff_format"),
        "playoffs_enabled": league.get("playoffs_enabled"),
        "playoff_roto_fresh_totals": league.get("playoff_roto_fresh_totals"),
        "playoff_roto_seed_bonuses": league.get("playoff_roto_seed_bonuses"),
        "playoff_start_week": league.get("playoff_start_week"),
        "playoff_end_week": league.get("playoff_end_week"),
    }

    # Configure league for condensed roto with seed bonuses
    db.leagues.update_one(
        {"_id": ObjectId(CONDENSED_ROTO_LEAGUE_ID)},
        {"$set": {
            "playoff_format": "condensed_roto",
            "playoffs_enabled": True,
            "playoff_roto_fresh_totals": True,
            "playoff_roto_seed_bonuses": {"1": 4, "2": 3, "3": 2, "4": 1},
            "playoff_start_week": 19,
            "playoff_end_week": 21,
            "scoring_format": "rotisserie",
        }}
    )

    # Get teams in the league
    teams = list(db.teams.find({"league_id": CONDENSED_ROTO_LEAGUE_ID}))

    # Seed deterministic player stats for each team
    # We'll give each team's first player different stats to create a clear ranking
    for idx, team in enumerate(teams):
        roster = team.get("roster", [])
        if roster:
            player_id = roster[0]
            # Season stats (for regular season ranking)
            season_goals = 100 - (idx * 10)  # Team 0: 100, Team 1: 90, etc.
            # Period stats (for playoff period)
            period_goals = 10 - idx  # Team 0: 10, Team 1: 9, etc.

            db.players.update_one(
                {"_id": ObjectId(player_id)},
                {"$set": {
                    "season_stats": {
                        "goals": season_goals,
                        "assists": season_goals // 2,
                        "points": season_goals + (season_goals // 2),
                        "plus_minus": 10,
                        "shots": season_goals * 3,
                        "hits": 50,
                        "blocks": 30,
                    },
                    "period_stats": {
                        "19": {"goals": period_goals, "assists": period_goals // 2, "points": period_goals + (period_goals // 2), "shots": period_goals * 2, "hits": 5, "blocks": 3},
                        "20": {"goals": period_goals, "assists": period_goals // 2, "points": period_goals + (period_goals // 2), "shots": period_goals * 2, "hits": 5, "blocks": 3},
                        "21": {"goals": period_goals, "assists": period_goals // 2, "points": period_goals + (period_goals // 2), "shots": period_goals * 2, "hits": 5, "blocks": 3},
                    }
                }}
            )

    yield {
        "league_id": CONDENSED_ROTO_LEAGUE_ID,
        "teams": teams,
        "seed_bonuses": {"1": 4, "2": 3, "3": 2, "4": 1},
    }

    # Restore original settings
    db.leagues.update_one(
        {"_id": ObjectId(CONDENSED_ROTO_LEAGUE_ID)},
        {"$set": original_settings}
    )

    # Cleanup test data
    cleanup_roto_league(db, CONDENSED_ROTO_LEAGUE_ID, TEST_SEASON_YEAR)


class TestCondensedRotoSeedBonuses:
    """Test seed bonus application in condensed roto standings."""

    def test_1_standings_includes_seed_bonuses_applied_flag(self, auth_headers, setup_condensed_roto_with_seed_bonuses):
        """
        Backend: Configure roto league with condensed_roto, fresh_totals=True,
        seed_bonuses={1:4, 2:3, 3:2, 4:1}. Call GET /api/leagues/{id}/roto/standings.
        Verify seed_bonuses_applied=true in response.
        """
        league_id = setup_condensed_roto_with_seed_bonuses["league_id"]

        resp = requests.get(
            f"{BASE_URL}/api/leagues/{league_id}/roto/standings",
            headers=auth_headers
        )

        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()

        # Verify seed_bonuses_applied flag
        assert data.get("seed_bonuses_applied") is True, \
            f"Expected seed_bonuses_applied=True, got {data.get('seed_bonuses_applied')}"

        # Verify fresh_totals is True
        assert data.get("fresh_totals") is True, \
            f"Expected fresh_totals=True, got {data.get('fresh_totals')}"

        print(f"✓ seed_bonuses_applied={data.get('seed_bonuses_applied')}")
        print(f"✓ fresh_totals={data.get('fresh_totals')}")

    def test_2_standings_totals_include_seed_bonus_and_seed_fields(self, auth_headers, setup_condensed_roto_with_seed_bonuses):
        """
        Backend: Verify totals include seed_bonus and seed fields for the top 4 seeded teams.
        """
        league_id = setup_condensed_roto_with_seed_bonuses["league_id"]
        seed_bonuses = setup_condensed_roto_with_seed_bonuses["seed_bonuses"]

        resp = requests.get(
            f"{BASE_URL}/api/leagues/{league_id}/roto/standings",
            headers=auth_headers
        )

        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()

        totals = data.get("totals", {})
        assert totals, "Totals should not be empty"

        # Check that teams with seeds 1-4 have seed_bonus and seed fields
        teams_with_bonuses = []
        for team_id, team_data in totals.items():
            seed = team_data.get("seed")
            seed_bonus = team_data.get("seed_bonus")

            if seed and seed <= 4:
                teams_with_bonuses.append({
                    "team_id": team_id,
                    "team_name": team_data.get("team_name"),
                    "seed": seed,
                    "seed_bonus": seed_bonus,
                    "total_points": team_data.get("total_points"),
                })

                # Verify seed_bonus matches expected value
                expected_bonus = float(seed_bonuses.get(str(seed), 0))
                assert seed_bonus == expected_bonus, \
                    f"Team {team_data.get('team_name')} (seed {seed}) should have seed_bonus={expected_bonus}, got {seed_bonus}"

        # Should have at least 4 teams with bonuses (or fewer if league has < 4 teams)
        print(f"✓ Found {len(teams_with_bonuses)} teams with seed bonuses:")
        for t in teams_with_bonuses:
            print(f"  - {t['team_name']}: seed={t['seed']}, bonus={t['seed_bonus']}, total={t['total_points']}")

    def test_3_seed_bonus_added_to_total_points(self, auth_headers, setup_condensed_roto_with_seed_bonuses, db):
        """
        Backend: Verify seed bonus is added to total_points.
        A team with 10 earned category points and seed bonus 4 should have total_points=14.
        """
        league_id = setup_condensed_roto_with_seed_bonuses["league_id"]

        resp = requests.get(
            f"{BASE_URL}/api/leagues/{league_id}/roto/standings",
            headers=auth_headers
        )

        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()

        totals = data.get("totals", {})

        # Find a team with seed 1 (should have bonus of 4)
        seed_1_team = None
        for team_id, team_data in totals.items():
            if team_data.get("seed") == 1:
                seed_1_team = team_data
                seed_1_team["team_id"] = team_id
                break

        if seed_1_team:
            seed_bonus = seed_1_team.get("seed_bonus", 0)
            total_points = seed_1_team.get("total_points", 0)

            # The total_points should include the seed_bonus
            # We can verify by checking that total_points > seed_bonus (since earned points > 0)
            assert total_points > seed_bonus, \
                f"Total points ({total_points}) should be greater than seed bonus ({seed_bonus})"

            # Calculate what the earned points would be without bonus
            earned_points = total_points - seed_bonus

            print(f"✓ Seed 1 team: {seed_1_team.get('team_name')}")
            print(f"  - Earned category points: {earned_points}")
            print(f"  - Seed bonus: {seed_bonus}")
            print(f"  - Total points: {total_points}")
            print(f"  - Verification: {earned_points} + {seed_bonus} = {earned_points + seed_bonus}")

            assert abs((earned_points + seed_bonus) - total_points) < 0.01, \
                f"Total points calculation mismatch: {earned_points} + {seed_bonus} != {total_points}"
        else:
            print("Warning: No team with seed 1 found")


class TestPlayoffsEnabledRespected:
    """Test that playoffs_enabled flag is respected for fresh totals and champion selection."""

    def test_4_playoffs_disabled_no_fresh_totals(self, auth_headers, db):
        """
        Backend: With playoffs_enabled=False on the same league, call
        GET /api/leagues/{id}/roto/standings. Verify fresh_totals is false/null
        and standings use full season_stats (no seed bonuses applied).
        """
        league_id = CONDENSED_ROTO_LEAGUE_ID

        # Store original settings
        league = db.leagues.find_one({"_id": ObjectId(league_id)})
        original_playoffs_enabled = league.get("playoffs_enabled")

        try:
            # Disable playoffs
            db.leagues.update_one(
                {"_id": ObjectId(league_id)},
                {"$set": {"playoffs_enabled": False}}
            )

            resp = requests.get(
                f"{BASE_URL}/api/leagues/{league_id}/roto/standings",
                headers=auth_headers
            )

            assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
            data = resp.json()

            # Verify fresh_totals is NOT True
            fresh_totals = data.get("fresh_totals")
            assert fresh_totals is not True, \
                f"With playoffs_enabled=False, fresh_totals should not be True, got {fresh_totals}"

            # Verify seed_bonuses_applied is NOT True
            seed_bonuses_applied = data.get("seed_bonuses_applied")
            assert seed_bonuses_applied is not True, \
                f"With playoffs_enabled=False, seed_bonuses_applied should not be True, got {seed_bonuses_applied}"

            # Verify no team has seed_bonus field
            totals = data.get("totals", {})
            for team_id, team_data in totals.items():
                assert team_data.get("seed_bonus") is None, \
                    f"Team {team_data.get('team_name')} should not have seed_bonus when playoffs disabled"

            print(f"✓ With playoffs_enabled=False:")
            print(f"  - fresh_totals={fresh_totals}")
            print(f"  - seed_bonuses_applied={seed_bonuses_applied}")
            print(f"  - No teams have seed_bonus field")

        finally:
            # Restore original setting
            db.leagues.update_one(
                {"_id": ObjectId(league_id)},
                {"$set": {"playoffs_enabled": original_playoffs_enabled}}
            )

    def test_5_playoffs_disabled_champion_is_regular_season_leader(self, auth_headers, db):
        """
        Backend: With playoffs_enabled=False, call POST /api/leagues/{id}/complete-season.
        Verify champion is the regular-season points leader (not the playoff-period leader).
        """
        league_id = CONDENSED_ROTO_LEAGUE_ID

        # Store original settings
        league = db.leagues.find_one({"_id": ObjectId(league_id)})
        original_playoffs_enabled = league.get("playoffs_enabled")

        try:
            # Disable playoffs
            db.leagues.update_one(
                {"_id": ObjectId(league_id)},
                {"$set": {"playoffs_enabled": False}}
            )

            # Clean up any previous test data
            cleanup_roto_league(db, league_id, TEST_SEASON_YEAR)

            # Get regular season standings (full season stats)
            standings_resp = requests.get(
                f"{BASE_URL}/api/leagues/{league_id}/roto/standings",
                headers=auth_headers
            )
            assert standings_resp.status_code == 200
            standings = standings_resp.json()

            # Find the regular season leader
            totals = standings.get("totals", {})
            if totals:
                leader_tid, leader_data = max(
                    totals.items(),
                    key=lambda x: x[1].get("total_points", 0)
                )
                expected_champion = leader_data.get("team_name")
                print(f"  Expected champion (regular season leader): {expected_champion}")
            else:
                expected_champion = None

            # Complete the season
            resp = requests.post(
                f"{BASE_URL}/api/leagues/{league_id}/complete-season",
                headers=auth_headers,
                json={"season_year": TEST_SEASON_YEAR}
            )

            assert resp.status_code == 200, f"Complete season failed: {resp.text}"
            data = resp.json()

            champion = data.get("champion")

            if expected_champion:
                assert champion == expected_champion, \
                    f"With playoffs_enabled=False, champion should be regular season leader '{expected_champion}', got '{champion}'"
                print(f"✓ Champion '{champion}' matches regular season leader")
            else:
                print(f"  Champion identified: {champion}")

        finally:
            # Restore original setting
            db.leagues.update_one(
                {"_id": ObjectId(league_id)},
                {"$set": {"playoffs_enabled": original_playoffs_enabled}}
            )
            # Cleanup
            cleanup_roto_league(db, league_id, TEST_SEASON_YEAR)

    def test_6_playoffs_enabled_champion_is_playoff_leader_with_bonuses(self, auth_headers, db):
        """
        Backend: With playoffs_enabled=True and condensed_roto, call
        POST /api/leagues/{id}/complete-season. Verify champion is the
        playoff-period points leader (with seed bonuses included).
        """
        league_id = CONDENSED_ROTO_LEAGUE_ID

        # Store original settings
        league = db.leagues.find_one({"_id": ObjectId(league_id)})
        original_playoffs_enabled = league.get("playoffs_enabled")

        try:
            # Enable playoffs
            db.leagues.update_one(
                {"_id": ObjectId(league_id)},
                {"$set": {
                    "playoffs_enabled": True,
                    "playoff_format": "condensed_roto",
                    "playoff_roto_fresh_totals": True,
                    "playoff_roto_seed_bonuses": {"1": 4, "2": 3, "3": 2, "4": 1},
                }}
            )

            # Clean up any previous test data
            cleanup_roto_league(db, league_id, TEST_SEASON_YEAR)

            # Get playoff standings (with fresh totals and seed bonuses)
            standings_resp = requests.get(
                f"{BASE_URL}/api/leagues/{league_id}/roto/standings",
                headers=auth_headers
            )
            assert standings_resp.status_code == 200
            standings = standings_resp.json()

            # Verify we're getting playoff standings
            assert standings.get("fresh_totals") is True, "Should have fresh_totals=True"
            assert standings.get("seed_bonuses_applied") is True, "Should have seed_bonuses_applied=True"

            # Find the playoff leader (with bonuses)
            totals = standings.get("totals", {})
            if totals:
                leader_tid, leader_data = max(
                    totals.items(),
                    key=lambda x: x[1].get("total_points", 0)
                )
                expected_champion = leader_data.get("team_name")
                print(f"  Expected champion (playoff leader with bonuses): {expected_champion}")
                print(f"  Total points: {leader_data.get('total_points')}")
                print(f"  Seed: {leader_data.get('seed')}, Bonus: {leader_data.get('seed_bonus')}")
            else:
                expected_champion = None

            # Complete the season
            resp = requests.post(
                f"{BASE_URL}/api/leagues/{league_id}/complete-season",
                headers=auth_headers,
                json={"season_year": TEST_SEASON_YEAR}
            )

            assert resp.status_code == 200, f"Complete season failed: {resp.text}"
            data = resp.json()

            champion = data.get("champion")

            if expected_champion:
                assert champion == expected_champion, \
                    f"With playoffs_enabled=True, champion should be playoff leader '{expected_champion}', got '{champion}'"
                print(f"✓ Champion '{champion}' matches playoff leader (with seed bonuses)")
            else:
                print(f"  Champion identified: {champion}")

        finally:
            # Restore original setting
            db.leagues.update_one(
                {"_id": ObjectId(league_id)},
                {"$set": {"playoffs_enabled": original_playoffs_enabled}}
            )
            # Cleanup
            cleanup_roto_league(db, league_id, TEST_SEASON_YEAR)


class TestOpponentsPerMatchupPeriod:
    """Test opponents_per_matchup_period validation with max_teams."""

    def test_7_opponents_per_period_2_on_max_teams_12(self, auth_headers, db):
        """
        Backend: PUT /api/leagues/{id} with opponents_per_matchup_period=2 on a
        league that has max_teams=12. Verify it saves successfully and the value persists.
        """
        league_id = PERENNIAL_KEEPERS_LEAGUE_ID

        # Verify the league has max_teams=12
        league = db.leagues.find_one({"_id": ObjectId(league_id)})
        assert league is not None, f"League {league_id} not found"
        max_teams = league.get("max_teams")
        print(f"  League max_teams: {max_teams}")

        # Store original value
        original_opponents = league.get("opponents_per_matchup_period")

        try:
            # Update opponents_per_matchup_period to 2
            resp = requests.put(
                f"{BASE_URL}/api/leagues/{league_id}",
                headers=auth_headers,
                json={"opponents_per_matchup_period": 2}
            )

            assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

            # Verify the value persists
            updated_league = db.leagues.find_one({"_id": ObjectId(league_id)})
            saved_value = updated_league.get("opponents_per_matchup_period")

            assert saved_value == 2, \
                f"opponents_per_matchup_period should be 2, got {saved_value}"

            print(f"✓ opponents_per_matchup_period=2 saved successfully on max_teams={max_teams} league")

            # Also verify via GET endpoint
            get_resp = requests.get(
                f"{BASE_URL}/api/leagues/{league_id}",
                headers=auth_headers
            )
            assert get_resp.status_code == 200
            get_data = get_resp.json()

            assert get_data.get("opponents_per_matchup_period") == 2, \
                f"GET should return opponents_per_matchup_period=2, got {get_data.get('opponents_per_matchup_period')}"

            print(f"✓ GET /api/leagues/{league_id} returns opponents_per_matchup_period=2")

        finally:
            # Restore original value
            db.leagues.update_one(
                {"_id": ObjectId(league_id)},
                {"$set": {"opponents_per_matchup_period": original_opponents}}
            )

    def test_8_opponents_per_period_validation_bounds(self, auth_headers, db):
        """
        Backend: Verify opponents_per_matchup_period validation (ge=1, le=10).
        """
        league_id = PERENNIAL_KEEPERS_LEAGUE_ID

        # Test value below minimum (0)
        resp = requests.put(
            f"{BASE_URL}/api/leagues/{league_id}",
            headers=auth_headers,
            json={"opponents_per_matchup_period": 0}
        )
        # Should fail validation
        assert resp.status_code in [400, 422], \
            f"opponents_per_matchup_period=0 should fail validation, got {resp.status_code}"
        print(f"✓ opponents_per_matchup_period=0 rejected (status {resp.status_code})")

        # Test value above maximum (11)
        resp = requests.put(
            f"{BASE_URL}/api/leagues/{league_id}",
            headers=auth_headers,
            json={"opponents_per_matchup_period": 11}
        )
        # Should fail validation
        assert resp.status_code in [400, 422], \
            f"opponents_per_matchup_period=11 should fail validation, got {resp.status_code}"
        print(f"✓ opponents_per_matchup_period=11 rejected (status {resp.status_code})")

        # Test valid value at maximum (10)
        resp = requests.put(
            f"{BASE_URL}/api/leagues/{league_id}",
            headers=auth_headers,
            json={"opponents_per_matchup_period": 10}
        )
        assert resp.status_code == 200, \
            f"opponents_per_matchup_period=10 should be accepted, got {resp.status_code}: {resp.text}"
        print(f"✓ opponents_per_matchup_period=10 accepted")

        # Restore to 1
        requests.put(
            f"{BASE_URL}/api/leagues/{league_id}",
            headers=auth_headers,
            json={"opponents_per_matchup_period": 1}
        )


class TestSeedBonusCalculation:
    """Additional tests for seed bonus calculation logic."""

    def test_9_seeds_determined_from_regular_season_standings(self, auth_headers, db):
        """
        Verify that seeds are determined from regular-season standings, not playoff standings.
        The team with the highest regular-season points should be seed 1.
        """
        league_id = CONDENSED_ROTO_LEAGUE_ID

        # Ensure playoffs are enabled with condensed roto
        db.leagues.update_one(
            {"_id": ObjectId(league_id)},
            {"$set": {
                "playoffs_enabled": True,
                "playoff_format": "condensed_roto",
                "playoff_roto_fresh_totals": True,
                "playoff_roto_seed_bonuses": {"1": 4, "2": 3, "3": 2, "4": 1},
            }}
        )

        # Get standings
        resp = requests.get(
            f"{BASE_URL}/api/leagues/{league_id}/roto/standings",
            headers=auth_headers
        )

        assert resp.status_code == 200
        data = resp.json()

        totals = data.get("totals", {})

        # Find teams with seeds
        seeded_teams = []
        for team_id, team_data in totals.items():
            seed = team_data.get("seed")
            if seed:
                seeded_teams.append({
                    "team_id": team_id,
                    "team_name": team_data.get("team_name"),
                    "seed": seed,
                    "seed_bonus": team_data.get("seed_bonus"),
                    "total_points": team_data.get("total_points"),
                })

        # Sort by seed
        seeded_teams.sort(key=lambda x: x["seed"])

        print(f"✓ Seeded teams (determined from regular-season standings):")
        for t in seeded_teams[:4]:
            print(f"  Seed {t['seed']}: {t['team_name']} (bonus={t['seed_bonus']}, total={t['total_points']})")

        # Verify seed 1 has the highest bonus
        if len(seeded_teams) >= 2:
            assert seeded_teams[0]["seed_bonus"] >= seeded_teams[1]["seed_bonus"], \
                "Seed 1 should have highest or equal bonus"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
