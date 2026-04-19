#!/usr/bin/env python3
"""
Dynasty Dreams Backend API Tests
Tests all API endpoints for the NHL fantasy sports platform using pytest
"""

import pytest
import requests
import os
from datetime import datetime

# Get BASE_URL from environment
BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials from test_credentials.md
ADMIN_EMAIL = "admin@dynastydreams.com"
ADMIN_PASSWORD = "Admin123!"
TEST_USER_EMAIL = f"test_user_{datetime.now().strftime('%H%M%S%f')}@test.com"
TEST_USER_PASSWORD = "TestPass123"


@pytest.fixture(scope="module")
def api_client():
    """Shared requests session"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


@pytest.fixture(scope="module")
def authenticated_client():
    """Session with auth cookies from login"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    response = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    if response.status_code != 200:
        pytest.skip("Admin login failed - skipping authenticated tests")
    # Session automatically stores cookies from the response
    return session


class TestHealthEndpoints:
    """Health check endpoint tests - run first"""
    
    def test_root_endpoint(self, api_client):
        """Test GET /api/ returns API info"""
        response = api_client.get(f"{BASE_URL}/api/")
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "Dynasty Dreams" in data["message"]
    
    def test_health_endpoint(self, api_client):
        """Test GET /api/health returns healthy status"""
        response = api_client.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"


class TestAuthEndpoints:
    """Authentication endpoint tests"""
    
    def test_register_new_user(self, api_client):
        """Test POST /api/auth/register creates new user"""
        response = api_client.post(f"{BASE_URL}/api/auth/register", json={
            "email": TEST_USER_EMAIL,
            "password": TEST_USER_PASSWORD,
            "name": "Test User"
        })
        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert data["email"] == TEST_USER_EMAIL.lower()
        assert data["name"] == "Test User"
        assert data["role"] == "user"
    
    def test_register_duplicate_email_fails(self, api_client):
        """Test POST /api/auth/register with duplicate email returns 400"""
        response = api_client.post(f"{BASE_URL}/api/auth/register", json={
            "email": ADMIN_EMAIL,
            "password": "SomePassword123",
            "name": "Duplicate User"
        })
        assert response.status_code == 400
        data = response.json()
        assert "already registered" in data["detail"].lower()
    
    def test_login_admin_success(self, api_client):
        """Test POST /api/auth/login with admin credentials"""
        response = api_client.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == ADMIN_EMAIL
        assert data["role"] == "admin"
        assert "id" in data
        # Verify httpOnly cookies are set
        assert "access_token" in response.cookies or "Set-Cookie" in response.headers
    
    def test_login_invalid_credentials(self, api_client):
        """Test POST /api/auth/login with wrong password returns 401"""
        response = api_client.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": "WrongPassword123"
        })
        assert response.status_code == 401
        data = response.json()
        assert "invalid" in data["detail"].lower()
    
    def test_auth_me_without_auth_returns_401(self, api_client):
        """Test GET /api/auth/me without authentication returns 401"""
        # Create a fresh session without cookies
        fresh_session = requests.Session()
        fresh_session.headers.update({"Content-Type": "application/json"})
        response = fresh_session.get(f"{BASE_URL}/api/auth/me")
        assert response.status_code == 401
        data = response.json()
        assert "not authenticated" in data["detail"].lower()
    
    def test_auth_me_with_auth_returns_user(self, authenticated_client):
        """Test GET /api/auth/me with authentication returns user data"""
        response = authenticated_client.get(f"{BASE_URL}/api/auth/me")
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == ADMIN_EMAIL
        assert "id" in data
        assert "role" in data
    
    def test_logout(self, api_client):
        """Test POST /api/auth/logout clears cookies"""
        response = api_client.post(f"{BASE_URL}/api/auth/logout")
        assert response.status_code == 200
        data = response.json()
        assert "logged out" in data["message"].lower()
    
    def test_forgot_password(self, api_client):
        """Test POST /api/auth/forgot-password"""
        response = api_client.post(f"{BASE_URL}/api/auth/forgot-password", json={
            "email": ADMIN_EMAIL
        })
        assert response.status_code == 200
        data = response.json()
        assert "message" in data


class TestPlayersEndpoints:
    """NHL Players endpoint tests - 1038 real players seeded"""
    
    def test_get_players_paginated(self, api_client):
        """Test GET /api/players returns paginated NHL data"""
        response = api_client.get(f"{BASE_URL}/api/players?page=1&limit=50")
        assert response.status_code == 200
        data = response.json()
        assert "players" in data
        assert "total" in data
        assert "page" in data
        assert "pages" in data
        assert len(data["players"]) <= 50
        # Verify we have real NHL data
        assert data["total"] >= 1000  # Should have 1038 players
    
    def test_get_players_search_mcdavid(self, api_client):
        """Test GET /api/players?search=McDavid returns Connor McDavid"""
        response = api_client.get(f"{BASE_URL}/api/players?search=McDavid")
        assert response.status_code == 200
        data = response.json()
        assert len(data["players"]) >= 1
        # Find Connor McDavid
        mcdavid = next((p for p in data["players"] if "Connor McDavid" in p["name"]), None)
        assert mcdavid is not None
        assert mcdavid["team"] == "EDM"
        assert mcdavid["position"] == "C"
        assert "goals" in mcdavid
        assert "assists" in mcdavid
        assert "points" in mcdavid
    
    def test_get_players_search_ovechkin(self, api_client):
        """Test GET /api/players?search=ovechkin returns matching results"""
        response = api_client.get(f"{BASE_URL}/api/players?search=ovechkin")
        assert response.status_code == 200
        data = response.json()
        # Should find Ovechkin
        assert len(data["players"]) >= 1
        ovechkin = next((p for p in data["players"] if "Ovechkin" in p["name"]), None)
        assert ovechkin is not None
    
    def test_get_players_position_goalie(self, api_client):
        """Test GET /api/players?position=G returns goalies only"""
        response = api_client.get(f"{BASE_URL}/api/players?position=G")
        assert response.status_code == 200
        data = response.json()
        assert len(data["players"]) > 0
        # All players should be goalies
        for player in data["players"]:
            assert player["position"] == "G"
        # Should have ~98 goalies
        assert data["total"] >= 90
    
    def test_get_players_position_defensemen(self, api_client):
        """Test GET /api/players?position=D returns defensemen only"""
        response = api_client.get(f"{BASE_URL}/api/players?position=D")
        assert response.status_code == 200
        data = response.json()
        assert len(data["players"]) > 0
        for player in data["players"]:
            assert player["position"] == "D"
    
    def test_get_players_stats_structure(self, api_client):
        """Test player data has correct stats structure"""
        response = api_client.get(f"{BASE_URL}/api/players?limit=1")
        assert response.status_code == 200
        data = response.json()
        player = data["players"][0]
        # Verify required fields
        assert "_id" in player
        assert "name" in player
        assert "team" in player
        assert "position" in player
        assert "games_played" in player


class TestLeaguesEndpoints:
    """League endpoint tests"""
    
    def test_get_leagues_public(self, api_client):
        """Test GET /api/leagues returns public leagues"""
        response = api_client.get(f"{BASE_URL}/api/leagues")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
    
    def test_create_league_without_auth_fails(self, api_client):
        """Test POST /api/leagues without auth returns 401"""
        fresh_session = requests.Session()
        response = fresh_session.post(f"{BASE_URL}/api/leagues", json={
            "name": "Test League",
            "format": "dynasty",
            "scoring_format": "head_to_head",
            "max_teams": 12,
            "salary_cap_enabled": False,
            "draft_type": "snake",
            "roster_spots": 20,
            "keepers_allowed": 0,
            "is_private": False
        })
        assert response.status_code == 401
    
    def test_create_league_with_auth(self, authenticated_client):
        """Test POST /api/leagues creates a new league"""
        league_name = f"TEST_League_{datetime.now().strftime('%H%M%S')}"
        response = authenticated_client.post(f"{BASE_URL}/api/leagues", json={
            "name": league_name,
            "format": "dynasty",
            "scoring_format": "head_to_head",
            "max_teams": 12,
            "salary_cap_enabled": False,
            "draft_type": "snake",
            "roster_spots": 20,
            "keepers_allowed": 0,
            "is_private": False
        })
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == league_name
        assert data["format"] == "dynasty"
        assert data["scoring_format"] == "head_to_head"
        assert data["max_teams"] == 12
        assert "id" in data
        # Store for later tests
        pytest.league_id = data["id"]
    
    def test_get_league_by_id(self, api_client):
        """Test GET /api/leagues/{id} returns league details"""
        if not hasattr(pytest, 'league_id'):
            pytest.skip("No league created in previous test")
        response = api_client.get(f"{BASE_URL}/api/leagues/{pytest.league_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == pytest.league_id
        assert "name" in data
        assert "format" in data
    
    def test_get_league_standings(self, api_client):
        """Test GET /api/leagues/{id}/standings returns standings"""
        if not hasattr(pytest, 'league_id'):
            pytest.skip("No league created in previous test")
        response = api_client.get(f"{BASE_URL}/api/leagues/{pytest.league_id}/standings")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)


class TestTeamsEndpoints:
    """Team endpoint tests"""
    
    def test_get_teams(self, api_client):
        """Test GET /api/teams returns teams list"""
        response = api_client.get(f"{BASE_URL}/api/teams")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
    
    def test_create_team_without_auth_fails(self, api_client):
        """Test POST /api/teams without auth returns 401"""
        fresh_session = requests.Session()
        response = fresh_session.post(f"{BASE_URL}/api/teams", json={
            "name": "Test Team",
            "league_id": "some_id"
        })
        assert response.status_code == 401
    
    def test_create_team_with_auth(self, authenticated_client):
        """Test POST /api/teams creates a team in a league"""
        if not hasattr(pytest, 'league_id'):
            pytest.skip("No league created in previous test")
        team_name = f"TEST_Team_{datetime.now().strftime('%H%M%S')}"
        response = authenticated_client.post(f"{BASE_URL}/api/teams", json={
            "name": team_name,
            "league_id": pytest.league_id
        })
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == team_name
        assert data["league_id"] == pytest.league_id
        assert "id" in data
        pytest.team_id = data["id"]
    
    def test_get_teams_by_league(self, api_client):
        """Test GET /api/teams?league_id={id} returns teams in league"""
        if not hasattr(pytest, 'league_id'):
            pytest.skip("No league created in previous test")
        response = api_client.get(f"{BASE_URL}/api/teams?league_id={pytest.league_id}")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1


class TestDraftsEndpoints:
    """Draft endpoint tests"""
    
    def test_create_draft_without_auth_fails(self, api_client):
        """Test POST /api/drafts without auth returns 401"""
        fresh_session = requests.Session()
        response = fresh_session.post(f"{BASE_URL}/api/drafts", json={
            "league_id": "some_id",
            "draft_type": "snake",
            "scheduled_time": "2026-01-15T12:00:00Z",
            "rounds": 15,
            "time_per_pick": 60
        })
        assert response.status_code == 401


class TestPaymentsEndpoints:
    """Payment endpoint tests"""
    
    def test_create_checkout_without_auth_fails(self, api_client):
        """Test POST /api/payments/checkout without auth returns 401"""
        fresh_session = requests.Session()
        response = fresh_session.post(f"{BASE_URL}/api/payments/checkout", json={
            "package_type": "premium_monthly",
            "origin_url": "https://test.com"
        })
        assert response.status_code == 401


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
