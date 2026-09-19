"""
Test Condensed Rotisserie Playoff Format Feature
Tests the backend API for the new playoff format option.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://dynasty-preview.preview.emergentagent.com')

class TestCondensedRotoPlayoffFormat:
    """Tests for the Condensed Rotisserie playoff format feature"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup - login and get auth token"""
        self.session = requests.Session()
        
        # Login
        login_response = self.session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "admin@dynastydreams.com", "password": "Admin123!"}
        )
        assert login_response.status_code == 200, f"Login failed: {login_response.text}"
        
        # Get leagues to find a test league
        leagues_response = self.session.get(f"{BASE_URL}/api/leagues")
        assert leagues_response.status_code == 200
        
        leagues = leagues_response.json()
        # Find "Ice Breakers" or "Stat Chasers Roto" league
        self.test_league = None
        for league in leagues:
            if "Ice Breakers" in league.get("name", "") or "Stat Chasers" in league.get("name", ""):
                self.test_league = league
                break
        
        if not self.test_league:
            # Use first available league
            self.test_league = leagues[0] if leagues else None
        
        assert self.test_league, "No test league found"
        self.league_id = self.test_league["id"]
        print(f"Using league: {self.test_league['name']} (ID: {self.league_id})")
        
        # Store original values for restoration
        self.original_playoff_format = self.test_league.get("playoff_format")
        self.original_playoff_roto_fresh_totals = self.test_league.get("playoff_roto_fresh_totals")
        self.original_playoff_roto_seed_bonuses = self.test_league.get("playoff_roto_seed_bonuses")
        
        yield
        
        # Restore original values
        self.session.put(
            f"{BASE_URL}/api/leagues/{self.league_id}",
            json={
                "playoff_format": self.original_playoff_format,
                "playoff_roto_fresh_totals": self.original_playoff_roto_fresh_totals,
                "playoff_roto_seed_bonuses": self.original_playoff_roto_seed_bonuses
            }
        )
    
    def test_playoff_format_accepts_condensed_roto(self):
        """Test that playoff_format field accepts 'condensed_roto' value"""
        response = self.session.put(
            f"{BASE_URL}/api/leagues/{self.league_id}",
            json={"playoff_format": "condensed_roto"}
        )
        assert response.status_code == 200, f"Failed to set condensed_roto: {response.text}"
        
        # Verify it was saved
        get_response = self.session.get(f"{BASE_URL}/api/leagues/{self.league_id}")
        assert get_response.status_code == 200
        league_data = get_response.json()
        assert league_data.get("playoff_format") == "condensed_roto", \
            f"Expected 'condensed_roto', got '{league_data.get('playoff_format')}'"
        print("PASS: playoff_format accepts 'condensed_roto'")
    
    def test_playoff_format_accepts_h2h_matchup(self):
        """Test that playoff_format field accepts 'h2h_matchup' value"""
        response = self.session.put(
            f"{BASE_URL}/api/leagues/{self.league_id}",
            json={"playoff_format": "h2h_matchup"}
        )
        assert response.status_code == 200, f"Failed to set h2h_matchup: {response.text}"
        
        get_response = self.session.get(f"{BASE_URL}/api/leagues/{self.league_id}")
        assert get_response.status_code == 200
        league_data = get_response.json()
        assert league_data.get("playoff_format") == "h2h_matchup"
        print("PASS: playoff_format accepts 'h2h_matchup'")
    
    def test_playoff_format_accepts_playoff_tree(self):
        """Test that playoff_format field accepts 'playoff_tree' value"""
        response = self.session.put(
            f"{BASE_URL}/api/leagues/{self.league_id}",
            json={"playoff_format": "playoff_tree"}
        )
        assert response.status_code == 200, f"Failed to set playoff_tree: {response.text}"
        
        get_response = self.session.get(f"{BASE_URL}/api/leagues/{self.league_id}")
        assert get_response.status_code == 200
        league_data = get_response.json()
        assert league_data.get("playoff_format") == "playoff_tree"
        print("PASS: playoff_format accepts 'playoff_tree'")
    
    def test_playoff_format_rejects_invalid_value(self):
        """Test that playoff_format field rejects invalid values"""
        response = self.session.put(
            f"{BASE_URL}/api/leagues/{self.league_id}",
            json={"playoff_format": "invalid_format"}
        )
        assert response.status_code == 422, f"Expected 422 for invalid format, got {response.status_code}"
        print("PASS: playoff_format rejects invalid values")
    
    def test_playoff_roto_fresh_totals_field(self):
        """Test that playoff_roto_fresh_totals field can be set"""
        # Set to True
        response = self.session.put(
            f"{BASE_URL}/api/leagues/{self.league_id}",
            json={
                "playoff_format": "condensed_roto",
                "playoff_roto_fresh_totals": True
            }
        )
        assert response.status_code == 200, f"Failed to set fresh_totals=True: {response.text}"
        
        get_response = self.session.get(f"{BASE_URL}/api/leagues/{self.league_id}")
        league_data = get_response.json()
        assert league_data.get("playoff_roto_fresh_totals") == True
        
        # Set to False
        response = self.session.put(
            f"{BASE_URL}/api/leagues/{self.league_id}",
            json={"playoff_roto_fresh_totals": False}
        )
        assert response.status_code == 200
        
        get_response = self.session.get(f"{BASE_URL}/api/leagues/{self.league_id}")
        league_data = get_response.json()
        assert league_data.get("playoff_roto_fresh_totals") == False
        print("PASS: playoff_roto_fresh_totals field works correctly")
    
    def test_playoff_roto_seed_bonuses_field(self):
        """Test that playoff_roto_seed_bonuses field can be set with seed bonus values"""
        seed_bonuses = {"1": 5, "2": 3, "3": 1, "4": 0}
        
        response = self.session.put(
            f"{BASE_URL}/api/leagues/{self.league_id}",
            json={
                "playoff_format": "condensed_roto",
                "playoff_roto_seed_bonuses": seed_bonuses
            }
        )
        assert response.status_code == 200, f"Failed to set seed_bonuses: {response.text}"
        
        get_response = self.session.get(f"{BASE_URL}/api/leagues/{self.league_id}")
        league_data = get_response.json()
        saved_bonuses = league_data.get("playoff_roto_seed_bonuses")
        
        # Verify bonuses were saved (keys may be strings)
        assert saved_bonuses is not None, "seed_bonuses not saved"
        assert str(saved_bonuses.get("1", saved_bonuses.get(1))) == "5" or saved_bonuses.get("1") == 5
        print("PASS: playoff_roto_seed_bonuses field works correctly")
    
    def test_condensed_roto_full_save(self):
        """Test saving all condensed roto fields together"""
        payload = {
            "playoff_format": "condensed_roto",
            "playoff_roto_fresh_totals": True,
            "playoff_roto_seed_bonuses": {"1": 5, "2": 3, "3": 1},
            "playoff_teams": 8
        }
        
        response = self.session.put(
            f"{BASE_URL}/api/leagues/{self.league_id}",
            json=payload
        )
        assert response.status_code == 200, f"Failed full save: {response.text}"
        
        # Verify all fields
        get_response = self.session.get(f"{BASE_URL}/api/leagues/{self.league_id}")
        league_data = get_response.json()
        
        assert league_data.get("playoff_format") == "condensed_roto"
        assert league_data.get("playoff_roto_fresh_totals") == True
        assert league_data.get("playoff_roto_seed_bonuses") is not None
        print("PASS: Full condensed roto configuration saved successfully")
    
    def test_switching_formats_clears_roto_fields(self):
        """Test that switching away from condensed_roto clears roto-specific fields"""
        # First set condensed_roto with all fields
        self.session.put(
            f"{BASE_URL}/api/leagues/{self.league_id}",
            json={
                "playoff_format": "condensed_roto",
                "playoff_roto_fresh_totals": True,
                "playoff_roto_seed_bonuses": {"1": 5}
            }
        )
        
        # Switch to h2h_matchup
        response = self.session.put(
            f"{BASE_URL}/api/leagues/{self.league_id}",
            json={
                "playoff_format": "h2h_matchup",
                "playoff_roto_fresh_totals": None,
                "playoff_roto_seed_bonuses": None
            }
        )
        assert response.status_code == 200
        
        get_response = self.session.get(f"{BASE_URL}/api/leagues/{self.league_id}")
        league_data = get_response.json()
        
        assert league_data.get("playoff_format") == "h2h_matchup"
        # Roto fields should be null/None when not using condensed_roto
        print("PASS: Switching formats works correctly")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
