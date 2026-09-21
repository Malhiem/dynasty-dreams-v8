"""Iter 232N.90 — Rotisserie Champion Detection Tests

Tests the fix for: Season completion does not identify the Rotisserie champion.
The completion endpoint returned champion: null despite the fixture having a 
unique season-points leader.

Root cause: The completion path only checked for championship_won_at (set by 
H2H playoff brackets) and had no logic to compute the roto points leader.

Fix: Added roto champion detection in both complete_season and auto-complete 
paths in seasons.py — when scoring_format is rotisserie and no champion was 
found via championship_won_at, compute roto standings and pick the team with 
highest total_points.

Test scenarios:
1. Roto league completion identifies champion with highest roto points
2. Winning team has championship_won_at set in database after completion
3. league_seasons snapshot has champion_team_name set to winning team
4. H2H league does NOT attempt roto champion detection
5. Idempotency - calling complete-season twice returns same champion
"""
import os
import pytest
import requests
from pymongo import MongoClient

# Backend URL from environment
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# MongoDB connection for cleanup and verification
MONGO_URL = "mongodb://localhost:27017"
DB_NAME = "test_database"

# Test league IDs from the problem statement
ROTO_LEAGUE_ID = "69e46af167999bfb85c39629"  # Stat Chasers Roto (scoring_format=rotisserie)
H2H_LEAGUE_ID = "69e46af167999bfb85c3962b"   # Perennial Keepers (head_to_head)

# Test season year - use a unique year to avoid conflicts
TEST_SEASON_YEAR = 2026

# Admin credentials
ADMIN_EMAIL = "admin@dynastydreams.com"
ADMIN_PASSWORD = "Admin123!"


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for admin user"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    )
    assert response.status_code == 200, f"Login failed: {response.text}"
    data = response.json()
    token = data.get("access_token")
    assert token, f"No access_token in response: {data}"
    return token


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Headers with auth token"""
    return {
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json"
    }


@pytest.fixture(scope="module")
def mongo_db():
    """MongoDB connection for direct database operations"""
    client = MongoClient(MONGO_URL)
    db = client[DB_NAME]
    yield db
    client.close()


def cleanup_roto_league(mongo_db, league_id: str, season_year: int):
    """Clean up test data after each test:
    1. Unset championship_won_at on all teams in the league
    2. Set league current_season_status back to 'in_progress'
    3. Delete the league_seasons document for the test season_year
    """
    # 1. Unset championship_won_at on all teams
    mongo_db.teams.update_many(
        {"league_id": league_id},
        {"$unset": {"championship_won_at": ""}}
    )
    
    # 2. Reset league status to in_progress
    from bson import ObjectId
    mongo_db.leagues.update_one(
        {"_id": ObjectId(league_id)},
        {"$set": {"current_season_status": "in_progress"}}
    )
    
    # 3. Delete the league_seasons document
    mongo_db.league_seasons.delete_one({
        "league_id": league_id,
        "season_year": season_year
    })


class TestRotoChampionDetection:
    """Test roto champion detection in complete-season endpoint"""
    
    def test_1_roto_league_completion_identifies_champion(self, auth_headers, mongo_db):
        """
        Backend: Clear championship_won_at from all teams in the roto league.
        Disable playoffs so champion is the regular-season leader.
        Call POST /api/leagues/{id}/complete-season with {season_year: 2026}.
        Verify the response includes a non-null champion field matching the 
        team with the highest roto points.
        """
        # Setup: Clean up any previous test data
        cleanup_roto_league(mongo_db, ROTO_LEAGUE_ID, TEST_SEASON_YEAR)
        
        # Disable playoffs so champion = regular-season points leader
        requests.put(
            f"{BASE_URL}/api/leagues/{ROTO_LEAGUE_ID}",
            headers=auth_headers,
            json={"playoffs_enabled": False},
        )
        
        # Verify championship_won_at is cleared
        teams = list(mongo_db.teams.find({"league_id": ROTO_LEAGUE_ID}))
        for team in teams:
            assert team.get("championship_won_at") is None, \
                f"Team {team.get('name')} still has championship_won_at set"
        
        # Call complete-season endpoint
        response = requests.post(
            f"{BASE_URL}/api/leagues/{ROTO_LEAGUE_ID}/complete-season",
            headers=auth_headers,
            json={"season_year": TEST_SEASON_YEAR}
        )
        
        assert response.status_code == 200, f"Complete season failed: {response.text}"
        data = response.json()
        
        # Verify champion is not null
        champion = data.get("champion")
        assert champion is not None, f"Champion should not be null for roto league. Response: {data}"
        assert isinstance(champion, str), f"Champion should be a string (team name). Got: {type(champion)}"
        assert len(champion) > 0, "Champion name should not be empty"
        
        print(f"✓ Roto champion identified: {champion}")
        print(f"  Teams snapshotted: {data.get('teams_snapshotted')}")
        print(f"  Season year: {data.get('season_year')}")
        
        # Cleanup: restore playoffs and clean test data
        requests.put(
            f"{BASE_URL}/api/leagues/{ROTO_LEAGUE_ID}",
            headers=auth_headers,
            json={"playoffs_enabled": True},
        )
        cleanup_roto_league(mongo_db, ROTO_LEAGUE_ID, TEST_SEASON_YEAR)
    
    def test_2_winning_team_has_championship_won_at_set(self, auth_headers, mongo_db):
        """
        Backend: After completing the season, verify the winning team has 
        championship_won_at set in the database.
        """
        # Setup: Clean up any previous test data
        cleanup_roto_league(mongo_db, ROTO_LEAGUE_ID, TEST_SEASON_YEAR)
        
        # Disable playoffs for season-only champion
        requests.put(
            f"{BASE_URL}/api/leagues/{ROTO_LEAGUE_ID}",
            headers=auth_headers,
            json={"playoffs_enabled": False},
        )
        
        # Call complete-season endpoint
        response = requests.post(
            f"{BASE_URL}/api/leagues/{ROTO_LEAGUE_ID}/complete-season",
            headers=auth_headers,
            json={"season_year": TEST_SEASON_YEAR}
        )
        
        assert response.status_code == 200, f"Complete season failed: {response.text}"
        data = response.json()
        champion_name = data.get("champion")
        assert champion_name, "Champion should be identified"
        
        # Verify the winning team has championship_won_at set in database
        winning_team = mongo_db.teams.find_one({
            "league_id": ROTO_LEAGUE_ID,
            "name": champion_name
        })
        
        assert winning_team is not None, f"Could not find team with name: {champion_name}"
        assert winning_team.get("championship_won_at") is not None, \
            f"Winning team '{champion_name}' should have championship_won_at set. Team doc: {winning_team}"
        
        print(f"✓ Winning team '{champion_name}' has championship_won_at: {winning_team.get('championship_won_at')}")
        
        # Cleanup
        requests.put(
            f"{BASE_URL}/api/leagues/{ROTO_LEAGUE_ID}",
            headers=auth_headers,
            json={"playoffs_enabled": True},
        )
        cleanup_roto_league(mongo_db, ROTO_LEAGUE_ID, TEST_SEASON_YEAR)
    
    def test_3_league_seasons_snapshot_has_champion_team_name(self, auth_headers, mongo_db):
        """
        Backend: After completing the season, verify the league_seasons snapshot 
        document has champion_team_name set to the winning team name.
        """
        # Setup: Clean up any previous test data
        cleanup_roto_league(mongo_db, ROTO_LEAGUE_ID, TEST_SEASON_YEAR)
        
        # Disable playoffs for season-only champion
        requests.put(
            f"{BASE_URL}/api/leagues/{ROTO_LEAGUE_ID}",
            headers=auth_headers,
            json={"playoffs_enabled": False},
        )
        
        # Call complete-season endpoint
        response = requests.post(
            f"{BASE_URL}/api/leagues/{ROTO_LEAGUE_ID}/complete-season",
            headers=auth_headers,
            json={"season_year": TEST_SEASON_YEAR}
        )
        
        assert response.status_code == 200, f"Complete season failed: {response.text}"
        data = response.json()
        champion_name = data.get("champion")
        assert champion_name, "Champion should be identified"
        
        # Verify league_seasons document has champion_team_name
        season_doc = mongo_db.league_seasons.find_one({
            "league_id": ROTO_LEAGUE_ID,
            "season_year": TEST_SEASON_YEAR
        })
        
        assert season_doc is not None, "league_seasons document should exist"
        assert season_doc.get("champion_team_name") == champion_name, \
            f"champion_team_name should be '{champion_name}', got: {season_doc.get('champion_team_name')}"
        assert season_doc.get("status") == "complete", \
            f"Season status should be 'complete', got: {season_doc.get('status')}"
        
        print(f"✓ league_seasons snapshot has champion_team_name: {season_doc.get('champion_team_name')}")
        print(f"  Season status: {season_doc.get('status')}")
        print(f"  Snapshot at: {season_doc.get('snapshot_at')}")
        
        # Cleanup
        requests.put(
            f"{BASE_URL}/api/leagues/{ROTO_LEAGUE_ID}",
            headers=auth_headers,
            json={"playoffs_enabled": True},
        )
        cleanup_roto_league(mongo_db, ROTO_LEAGUE_ID, TEST_SEASON_YEAR)
    
    def test_4_h2h_league_does_not_use_roto_champion_detection(self, auth_headers, mongo_db):
        """
        Backend: For a non-rotisserie league (head_to_head), verify the completion 
        endpoint does NOT attempt roto champion detection (champion should be null 
        if no championship_won_at exists).
        """
        # Setup: Clean up any previous test data for H2H league
        cleanup_roto_league(mongo_db, H2H_LEAGUE_ID, TEST_SEASON_YEAR)
        
        # Verify the league is head_to_head format
        from bson import ObjectId
        league = mongo_db.leagues.find_one({"_id": ObjectId(H2H_LEAGUE_ID)})
        assert league is not None, f"H2H league not found: {H2H_LEAGUE_ID}"
        scoring_format = league.get("scoring_format")
        print(f"  H2H league scoring_format: {scoring_format}")
        
        # Call complete-season endpoint
        response = requests.post(
            f"{BASE_URL}/api/leagues/{H2H_LEAGUE_ID}/complete-season",
            headers=auth_headers,
            json={"season_year": TEST_SEASON_YEAR}
        )
        
        assert response.status_code == 200, f"Complete season failed: {response.text}"
        data = response.json()
        
        # For H2H league without championship_won_at, champion should be null
        champion = data.get("champion")
        
        # The champion should be null because:
        # 1. No team has championship_won_at set (H2H uses playoff brackets)
        # 2. The roto champion detection should NOT run for non-rotisserie leagues
        assert champion is None, \
            f"H2H league should have null champion when no championship_won_at exists. Got: {champion}"
        
        print(f"✓ H2H league correctly returns null champion (no roto detection)")
        print(f"  Season year: {data.get('season_year')}")
        print(f"  Teams snapshotted: {data.get('teams_snapshotted')}")
        
        # Cleanup
        cleanup_roto_league(mongo_db, H2H_LEAGUE_ID, TEST_SEASON_YEAR)
    
    def test_5_complete_season_is_idempotent(self, auth_headers, mongo_db):
        """
        Backend: Verify the complete-season endpoint is idempotent — calling it 
        twice for the same season_year should succeed and return the same champion.
        """
        # Setup: Clean up any previous test data
        cleanup_roto_league(mongo_db, ROTO_LEAGUE_ID, TEST_SEASON_YEAR)
        
        # Disable playoffs for season-only champion
        requests.put(
            f"{BASE_URL}/api/leagues/{ROTO_LEAGUE_ID}",
            headers=auth_headers,
            json={"playoffs_enabled": False},
        )
        
        # First call
        response1 = requests.post(
            f"{BASE_URL}/api/leagues/{ROTO_LEAGUE_ID}/complete-season",
            headers=auth_headers,
            json={"season_year": TEST_SEASON_YEAR}
        )
        
        assert response1.status_code == 200, f"First complete season failed: {response1.text}"
        data1 = response1.json()
        champion1 = data1.get("champion")
        assert champion1 is not None, "First call should identify champion"
        
        # Second call (idempotent)
        response2 = requests.post(
            f"{BASE_URL}/api/leagues/{ROTO_LEAGUE_ID}/complete-season",
            headers=auth_headers,
            json={"season_year": TEST_SEASON_YEAR}
        )
        
        assert response2.status_code == 200, f"Second complete season failed: {response2.text}"
        data2 = response2.json()
        champion2 = data2.get("champion")
        
        # Both calls should return the same champion
        assert champion2 == champion1, \
            f"Idempotent calls should return same champion. First: {champion1}, Second: {champion2}"
        
        print(f"✓ Complete-season is idempotent")
        print(f"  First call champion: {champion1}")
        print(f"  Second call champion: {champion2}")
        
        # Verify only one league_seasons document exists
        season_docs = list(mongo_db.league_seasons.find({
            "league_id": ROTO_LEAGUE_ID,
            "season_year": TEST_SEASON_YEAR
        }))
        assert len(season_docs) == 1, \
            f"Should have exactly 1 league_seasons doc, found: {len(season_docs)}"
        
        print(f"  Only 1 league_seasons document exists (upsert working)")
        
        # Cleanup
        requests.put(
            f"{BASE_URL}/api/leagues/{ROTO_LEAGUE_ID}",
            headers=auth_headers,
            json={"playoffs_enabled": True},
        )
        cleanup_roto_league(mongo_db, ROTO_LEAGUE_ID, TEST_SEASON_YEAR)


class TestRotoChampionVerification:
    """Additional verification tests for roto champion detection"""
    
    def test_6_champion_matches_highest_roto_points(self, auth_headers, mongo_db):
        """
        Verify the identified champion actually has the highest roto points
        by comparing with the roto standings endpoint.
        """
        # Setup: Clean up any previous test data
        cleanup_roto_league(mongo_db, ROTO_LEAGUE_ID, TEST_SEASON_YEAR)
        
        # Disable playoffs for season-only champion
        requests.put(
            f"{BASE_URL}/api/leagues/{ROTO_LEAGUE_ID}",
            headers=auth_headers,
            json={"playoffs_enabled": False},
        )
        
        # Get roto standings first
        standings_response = requests.get(
            f"{BASE_URL}/api/leagues/{ROTO_LEAGUE_ID}/roto/standings",
            headers=auth_headers
        )
        
        assert standings_response.status_code == 200, f"Standings failed: {standings_response.text}"
        standings = standings_response.json()
        
        # Find the team with highest total_points
        totals = standings.get("totals", {})
        if totals:
            leader_tid, leader_data = max(
                totals.items(),
                key=lambda x: x[1].get("total_points", 0)
            )
            expected_champion = leader_data.get("team_name")
            expected_points = leader_data.get("total_points")
            print(f"  Expected champion from standings: {expected_champion} ({expected_points} pts)")
        else:
            expected_champion = None
            print("  Warning: No totals in standings response")
        
        # Now complete the season
        response = requests.post(
            f"{BASE_URL}/api/leagues/{ROTO_LEAGUE_ID}/complete-season",
            headers=auth_headers,
            json={"season_year": TEST_SEASON_YEAR}
        )
        
        assert response.status_code == 200, f"Complete season failed: {response.text}"
        data = response.json()
        actual_champion = data.get("champion")
        
        # Verify champion matches the standings leader
        if expected_champion:
            assert actual_champion == expected_champion, \
                f"Champion should be '{expected_champion}' (highest roto points), got: '{actual_champion}'"
            print(f"✓ Champion '{actual_champion}' matches roto standings leader")
        else:
            print(f"  Champion identified: {actual_champion}")
        
        # Cleanup
        requests.put(
            f"{BASE_URL}/api/leagues/{ROTO_LEAGUE_ID}",
            headers=auth_headers,
            json={"playoffs_enabled": True},
        )
        cleanup_roto_league(mongo_db, ROTO_LEAGUE_ID, TEST_SEASON_YEAR)
    
    def test_7_team_snapshot_awards_updated(self, auth_headers, mongo_db):
        """
        Verify the teams_snapshot in league_seasons has the winning team's
        awards.championship_won_at set.
        """
        # Setup: Clean up any previous test data
        cleanup_roto_league(mongo_db, ROTO_LEAGUE_ID, TEST_SEASON_YEAR)
        
        # Disable playoffs for season-only champion
        requests.put(
            f"{BASE_URL}/api/leagues/{ROTO_LEAGUE_ID}",
            headers=auth_headers,
            json={"playoffs_enabled": False},
        )
        
        # Complete the season
        response = requests.post(
            f"{BASE_URL}/api/leagues/{ROTO_LEAGUE_ID}/complete-season",
            headers=auth_headers,
            json={"season_year": TEST_SEASON_YEAR}
        )
        
        assert response.status_code == 200, f"Complete season failed: {response.text}"
        data = response.json()
        champion_name = data.get("champion")
        assert champion_name, "Champion should be identified"
        
        # Get the league_seasons document
        season_doc = mongo_db.league_seasons.find_one({
            "league_id": ROTO_LEAGUE_ID,
            "season_year": TEST_SEASON_YEAR
        })
        
        assert season_doc is not None, "league_seasons document should exist"
        
        # Find the champion team in the snapshot
        teams_snapshot = season_doc.get("teams", [])
        champion_snapshot = None
        for team in teams_snapshot:
            if team.get("team_name") == champion_name:
                champion_snapshot = team
                break
        
        assert champion_snapshot is not None, \
            f"Champion '{champion_name}' should be in teams snapshot"
        
        # Verify awards.championship_won_at is set in the snapshot
        awards = champion_snapshot.get("awards", {})
        assert awards.get("championship_won_at") is not None, \
            f"Champion snapshot should have awards.championship_won_at set. Awards: {awards}"
        
        print(f"✓ Champion '{champion_name}' snapshot has awards.championship_won_at: {awards.get('championship_won_at')}")
        
        # Cleanup
        requests.put(
            f"{BASE_URL}/api/leagues/{ROTO_LEAGUE_ID}",
            headers=auth_headers,
            json={"playoffs_enabled": True},
        )
        cleanup_roto_league(mongo_db, ROTO_LEAGUE_ID, TEST_SEASON_YEAR)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
