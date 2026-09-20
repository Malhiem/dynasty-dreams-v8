"""
Iteration 163: Playoff Bracket Advancement Bug Fix Tests

Bug: Elimination playoffs do not advance correctly into the semifinals.
- 8-team bracket should have 4 QF, 2 SF, 1 Final = 7 matchups total
- Double-halving bug in surviving count only created 1 SF instead of 2
- simulate-week did not advance winners to next-round TBD slots
- Final round matchups didn't have is_final flag so auto-crown never triggered

Tests verify:
1. 8-team bracket generates exactly 7 matchups (4 QF + 2 SF + 1 Final)
2. Final round matchup has is_final=True and bracket='championship'
3. QF simulation advances winners to SF matchups
4. SF simulation advances winners to Final matchup
5. Final simulation crowns a champion
6. Team names are correctly propagated to next round
7. 4-team bracket generates 3 matchups (2 SF + 1 Final) and works correctly
"""

import pytest
import requests
import os
from pymongo import MongoClient
from bson import ObjectId
from datetime import datetime, timezone

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
MONGO_URL = "mongodb://localhost:27017"
DB_NAME = "test_database"

# Test league: Perennial Keepers (12 teams, head_to_head)
LEAGUE_ID = "69e46af167999bfb85c3962b"


@pytest.fixture(scope="module")
def db():
    """MongoDB connection fixture"""
    client = MongoClient(MONGO_URL)
    return client[DB_NAME]


@pytest.fixture(scope="module")
def auth_token():
    """Get admin auth token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": "admin@dynastydreams.com",
        "password": "Admin123!"
    })
    assert response.status_code == 200, f"Login failed: {response.text}"
    return response.json().get("access_token")


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Auth headers for API calls"""
    return {"Authorization": f"Bearer {auth_token}"}


def reset_league_for_8_team_playoff(db):
    """Reset league for 8-team playoff bracket test"""
    # Delete all matchups for the league
    db.matchups.delete_many({"league_id": LEAGUE_ID})
    
    # Delete week_summaries for the league
    db.week_summaries.delete_many({"league_id": LEAGUE_ID})
    
    # Reset all teams: wins, losses, championship_won_at, playoff_runner_up_at
    db.teams.update_many(
        {"league_id": LEAGUE_ID},
        {"$set": {"wins": 0, "losses": 0, "ties": 0, "points_for": 0, "points_against": 0},
         "$unset": {"championship_won_at": "", "playoff_runner_up_at": ""}}
    )
    
    # Configure league for 8-team playoff_tree with 3 rounds (weeks 25-27)
    db.leagues.update_one(
        {"_id": ObjectId(LEAGUE_ID)},
        {"$set": {
            "playoff_format": "playoff_tree",
            "playoff_teams": 8,
            "playoff_rounds": 3,
            "playoff_start_week": 25,
            "playoff_end_week": 27,
            "playoff_seeding_method": "high_vs_low"
        }}
    )


def reset_league_for_4_team_playoff(db):
    """Reset league for 4-team playoff bracket test"""
    # Delete all matchups for the league
    db.matchups.delete_many({"league_id": LEAGUE_ID})
    
    # Delete week_summaries for the league
    db.week_summaries.delete_many({"league_id": LEAGUE_ID})
    
    # Reset all teams
    db.teams.update_many(
        {"league_id": LEAGUE_ID},
        {"$set": {"wins": 0, "losses": 0, "ties": 0, "points_for": 0, "points_against": 0},
         "$unset": {"championship_won_at": "", "playoff_runner_up_at": ""}}
    )
    
    # Configure league for 4-team playoff_tree with 2 rounds (weeks 25-26)
    db.leagues.update_one(
        {"_id": ObjectId(LEAGUE_ID)},
        {"$set": {
            "playoff_format": "playoff_tree",
            "playoff_teams": 4,
            "playoff_rounds": 2,
            "playoff_start_week": 25,
            "playoff_end_week": 26,
            "playoff_seeding_method": "high_vs_low"
        }}
    )


class Test8TeamPlayoffBracket:
    """Test 8-team playoff bracket generation and advancement"""
    
    def test_01_setup_and_generate_8_team_bracket(self, db, auth_headers):
        """Setup: Configure league for 8-team playoff and generate schedule"""
        reset_league_for_8_team_playoff(db)
        
        # Generate schedule
        response = requests.post(
            f"{BASE_URL}/api/matchups/generate-schedule",
            json={"league_id": LEAGUE_ID},
            headers=auth_headers
        )
        assert response.status_code == 200, f"Generate schedule failed: {response.text}"
        data = response.json()
        print(f"Schedule generated: {data.get('message')}")
        print(f"Playoff matchups: {data.get('playoff_matchups')}")
        
    def test_02_verify_bracket_has_7_matchups(self, db):
        """Verify 8-team bracket has exactly 7 matchups: 4 QF + 2 SF + 1 Final"""
        playoff_matchups = list(db.matchups.find({
            "league_id": LEAGUE_ID,
            "is_playoff": True
        }))
        
        total_playoff = len(playoff_matchups)
        assert total_playoff == 7, f"Expected 7 playoff matchups, got {total_playoff}"
        
        # Count by round
        round_1 = [m for m in playoff_matchups if m.get("bracket_round") == 1]
        round_2 = [m for m in playoff_matchups if m.get("bracket_round") == 2]
        round_3 = [m for m in playoff_matchups if m.get("bracket_round") == 3]
        
        assert len(round_1) == 4, f"Expected 4 QF matchups (round 1), got {len(round_1)}"
        assert len(round_2) == 2, f"Expected 2 SF matchups (round 2), got {len(round_2)}"
        assert len(round_3) == 1, f"Expected 1 Final matchup (round 3), got {len(round_3)}"
        
        print(f"✓ Bracket structure correct: 4 QF + 2 SF + 1 Final = 7 matchups")
        
    def test_03_verify_final_has_is_final_and_championship_bracket(self, db):
        """Verify round 3 (final) matchup has is_final=True and bracket='championship'"""
        final_matchup = db.matchups.find_one({
            "league_id": LEAGUE_ID,
            "is_playoff": True,
            "bracket_round": 3
        })
        
        assert final_matchup is not None, "Final matchup not found"
        assert final_matchup.get("is_final") == True, f"Final matchup is_final should be True, got {final_matchup.get('is_final')}"
        assert final_matchup.get("bracket") == "championship", f"Final matchup bracket should be 'championship', got {final_matchup.get('bracket')}"
        
        print(f"✓ Final matchup has is_final=True and bracket='championship'")
        
    def test_04_verify_qf_matchups_have_real_teams(self, db):
        """Verify QF (round 1) matchups have real team IDs (not TBD)"""
        qf_matchups = list(db.matchups.find({
            "league_id": LEAGUE_ID,
            "is_playoff": True,
            "bracket_round": 1
        }))
        
        for m in qf_matchups:
            assert m.get("home_team_id") is not None, f"QF matchup missing home_team_id"
            assert m.get("away_team_id") is not None, f"QF matchup missing away_team_id"
            assert m.get("home_team_tbd") == False, f"QF home_team_tbd should be False"
            assert m.get("away_team_tbd") == False, f"QF away_team_tbd should be False"
            
        print(f"✓ All 4 QF matchups have real team IDs")
        
    def test_05_verify_sf_matchups_are_tbd_before_simulation(self, db):
        """Verify SF (round 2) matchups have TBD teams before QF simulation"""
        sf_matchups = list(db.matchups.find({
            "league_id": LEAGUE_ID,
            "is_playoff": True,
            "bracket_round": 2
        }))
        
        for m in sf_matchups:
            assert m.get("home_team_id") is None, f"SF home_team_id should be None before QF sim"
            assert m.get("away_team_id") is None, f"SF away_team_id should be None before QF sim"
            assert m.get("home_team_tbd") == True, f"SF home_team_tbd should be True"
            assert m.get("away_team_tbd") == True, f"SF away_team_tbd should be True"
            
        print(f"✓ Both SF matchups have TBD teams before QF simulation")
        
    def test_06_simulate_week_25_qf_round(self, auth_headers):
        """Simulate week 25 (QF round) and verify all 4 matchups complete"""
        response = requests.post(
            f"{BASE_URL}/api/matchups/simulate-week",
            json={"league_id": LEAGUE_ID, "week": 25},
            headers=auth_headers
        )
        assert response.status_code == 200, f"Simulate week 25 failed: {response.text}"
        data = response.json()
        
        assert data.get("matchups_simulated") == 4, f"Expected 4 QF matchups simulated, got {data.get('matchups_simulated')}"
        assert len(data.get("results", [])) == 4, f"Expected 4 results, got {len(data.get('results', []))}"
        
        print(f"✓ Week 25 (QF) simulated: {data.get('matchups_simulated')} matchups")
        for r in data.get("results", []):
            print(f"  {r.get('home')} vs {r.get('away')}: {r.get('home_score')}-{r.get('away_score')} → {r.get('winner')}")
            
    def test_07_verify_sf_matchups_have_qf_winners(self, db):
        """After QF simulation, verify SF matchups have non-null team IDs (QF winners advanced)"""
        sf_matchups = list(db.matchups.find({
            "league_id": LEAGUE_ID,
            "is_playoff": True,
            "bracket_round": 2
        }))
        
        for i, m in enumerate(sf_matchups):
            assert m.get("home_team_id") is not None, f"SF {i+1} home_team_id should be set after QF sim"
            assert m.get("away_team_id") is not None, f"SF {i+1} away_team_id should be set after QF sim"
            assert m.get("home_team_name") not in (None, "", "TBD"), f"SF {i+1} home_team_name should be set"
            assert m.get("away_team_name") not in (None, "", "TBD"), f"SF {i+1} away_team_name should be set"
            print(f"  SF {i+1}: {m.get('home_team_name')} vs {m.get('away_team_name')}")
            
        print(f"✓ Both SF matchups have QF winners advanced with team names")
        
    def test_08_simulate_week_26_sf_round(self, auth_headers):
        """Simulate week 26 (SF round) and verify both matchups complete"""
        response = requests.post(
            f"{BASE_URL}/api/matchups/simulate-week",
            json={"league_id": LEAGUE_ID, "week": 26},
            headers=auth_headers
        )
        assert response.status_code == 200, f"Simulate week 26 failed: {response.text}"
        data = response.json()
        
        assert data.get("matchups_simulated") == 2, f"Expected 2 SF matchups simulated, got {data.get('matchups_simulated')}"
        
        print(f"✓ Week 26 (SF) simulated: {data.get('matchups_simulated')} matchups")
        for r in data.get("results", []):
            print(f"  {r.get('home')} vs {r.get('away')}: {r.get('home_score')}-{r.get('away_score')} → {r.get('winner')}")
            
    def test_09_verify_final_matchup_has_sf_winners(self, db):
        """After SF simulation, verify Final matchup has non-null team IDs (SF winners advanced)"""
        final_matchup = db.matchups.find_one({
            "league_id": LEAGUE_ID,
            "is_playoff": True,
            "bracket_round": 3
        })
        
        assert final_matchup.get("home_team_id") is not None, "Final home_team_id should be set after SF sim"
        assert final_matchup.get("away_team_id") is not None, "Final away_team_id should be set after SF sim"
        assert final_matchup.get("home_team_name") not in (None, "", "TBD"), "Final home_team_name should be set"
        assert final_matchup.get("away_team_name") not in (None, "", "TBD"), "Final away_team_name should be set"
        
        print(f"✓ Final matchup has SF winners: {final_matchup.get('home_team_name')} vs {final_matchup.get('away_team_name')}")
        
    def test_10_simulate_week_27_final_and_verify_champion(self, db, auth_headers):
        """Simulate week 27 (Final) and verify a champion is declared"""
        response = requests.post(
            f"{BASE_URL}/api/matchups/simulate-week",
            json={"league_id": LEAGUE_ID, "week": 27},
            headers=auth_headers
        )
        assert response.status_code == 200, f"Simulate week 27 failed: {response.text}"
        data = response.json()
        
        assert data.get("matchups_simulated") == 1, f"Expected 1 Final matchup simulated, got {data.get('matchups_simulated')}"
        
        print(f"✓ Week 27 (Final) simulated: {data.get('matchups_simulated')} matchup")
        for r in data.get("results", []):
            print(f"  {r.get('home')} vs {r.get('away')}: {r.get('home_score')}-{r.get('away_score')} → {r.get('winner')}")
            
        # Verify a team has championship_won_at set
        champion = db.teams.find_one({
            "league_id": LEAGUE_ID,
            "championship_won_at": {"$exists": True, "$ne": None}
        })
        
        assert champion is not None, "No champion found - championship_won_at not set on any team"
        print(f"✓ Champion declared: {champion.get('name')} (championship_won_at: {champion.get('championship_won_at')})")


class Test4TeamPlayoffBracket:
    """Test 4-team playoff bracket generation and advancement"""
    
    def test_01_setup_and_generate_4_team_bracket(self, db, auth_headers):
        """Setup: Configure league for 4-team playoff and generate schedule"""
        reset_league_for_4_team_playoff(db)
        
        # Generate schedule
        response = requests.post(
            f"{BASE_URL}/api/matchups/generate-schedule",
            json={"league_id": LEAGUE_ID},
            headers=auth_headers
        )
        assert response.status_code == 200, f"Generate schedule failed: {response.text}"
        data = response.json()
        print(f"Schedule generated: {data.get('message')}")
        print(f"Playoff matchups: {data.get('playoff_matchups')}")
        
    def test_02_verify_4_team_bracket_has_3_matchups(self, db):
        """Verify 4-team bracket has exactly 3 matchups: 2 SF + 1 Final"""
        playoff_matchups = list(db.matchups.find({
            "league_id": LEAGUE_ID,
            "is_playoff": True
        }))
        
        total_playoff = len(playoff_matchups)
        assert total_playoff == 3, f"Expected 3 playoff matchups for 4-team bracket, got {total_playoff}"
        
        # Count by round
        round_1 = [m for m in playoff_matchups if m.get("bracket_round") == 1]
        round_2 = [m for m in playoff_matchups if m.get("bracket_round") == 2]
        
        assert len(round_1) == 2, f"Expected 2 SF matchups (round 1), got {len(round_1)}"
        assert len(round_2) == 1, f"Expected 1 Final matchup (round 2), got {len(round_2)}"
        
        print(f"✓ 4-team bracket structure correct: 2 SF + 1 Final = 3 matchups")
        
    def test_03_verify_4_team_final_has_is_final(self, db):
        """Verify 4-team bracket final has is_final=True"""
        final_matchup = db.matchups.find_one({
            "league_id": LEAGUE_ID,
            "is_playoff": True,
            "bracket_round": 2
        })
        
        assert final_matchup is not None, "Final matchup not found"
        assert final_matchup.get("is_final") == True, f"Final matchup is_final should be True"
        assert final_matchup.get("bracket") == "championship", f"Final matchup bracket should be 'championship'"
        
        print(f"✓ 4-team final has is_final=True and bracket='championship'")
        
    def test_04_simulate_4_team_sf_round(self, auth_headers):
        """Simulate week 25 (SF round for 4-team bracket)"""
        response = requests.post(
            f"{BASE_URL}/api/matchups/simulate-week",
            json={"league_id": LEAGUE_ID, "week": 25},
            headers=auth_headers
        )
        assert response.status_code == 200, f"Simulate week 25 failed: {response.text}"
        data = response.json()
        
        assert data.get("matchups_simulated") == 2, f"Expected 2 SF matchups simulated, got {data.get('matchups_simulated')}"
        
        print(f"✓ Week 25 (SF) simulated: {data.get('matchups_simulated')} matchups")
        
    def test_05_verify_4_team_final_has_sf_winners(self, db):
        """Verify 4-team final has SF winners advanced"""
        final_matchup = db.matchups.find_one({
            "league_id": LEAGUE_ID,
            "is_playoff": True,
            "bracket_round": 2
        })
        
        assert final_matchup.get("home_team_id") is not None, "Final home_team_id should be set"
        assert final_matchup.get("away_team_id") is not None, "Final away_team_id should be set"
        
        print(f"✓ 4-team final has SF winners: {final_matchup.get('home_team_name')} vs {final_matchup.get('away_team_name')}")
        
    def test_06_simulate_4_team_final_and_verify_champion(self, db, auth_headers):
        """Simulate week 26 (Final for 4-team bracket) and verify champion"""
        response = requests.post(
            f"{BASE_URL}/api/matchups/simulate-week",
            json={"league_id": LEAGUE_ID, "week": 26},
            headers=auth_headers
        )
        assert response.status_code == 200, f"Simulate week 26 failed: {response.text}"
        data = response.json()
        
        assert data.get("matchups_simulated") == 1, f"Expected 1 Final matchup simulated"
        
        # Verify champion
        champion = db.teams.find_one({
            "league_id": LEAGUE_ID,
            "championship_won_at": {"$exists": True, "$ne": None}
        })
        
        assert champion is not None, "No champion found for 4-team bracket"
        print(f"✓ 4-team bracket champion: {champion.get('name')}")


class TestCleanup:
    """Cleanup after tests"""
    
    def test_cleanup(self, db):
        """Reset league to original state"""
        # Reset teams
        db.teams.update_many(
            {"league_id": LEAGUE_ID},
            {"$set": {"wins": 0, "losses": 0, "ties": 0, "points_for": 0, "points_against": 0},
             "$unset": {"championship_won_at": "", "playoff_runner_up_at": ""}}
        )
        
        # Delete test matchups
        db.matchups.delete_many({"league_id": LEAGUE_ID})
        
        # Delete week_summaries
        db.week_summaries.delete_many({"league_id": LEAGUE_ID})
        
        # Reset league playoff config to reasonable defaults
        db.leagues.update_one(
            {"_id": ObjectId(LEAGUE_ID)},
            {"$set": {
                "playoff_format": "playoff_tree",
                "playoff_teams": 8,
                "playoff_rounds": 3,
                "playoff_start_week": 25,
                "playoff_end_week": 27
            }}
        )
        
        print("✓ Cleanup complete")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
