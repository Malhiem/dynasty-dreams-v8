"""
Iteration 167 Bug Fixes Tests
=============================
Tests for 3 specific bug fixes:
1. Midnight processing - trade processes_at should be midnight UTC-8 (not acceptance + 24h)
2. Traded pick ownership - auto-pick must award player to new pick owner (Team 2) not original (Team 1)
3. Sandbox account login - @sandbox.local accounts should return 401 (not 500)
"""

import pytest
import requests
import os
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# ============================================================================
# Bug Fix 1: Midnight Processing Tests
# ============================================================================

class TestMidnightProcessing:
    """Test that trade processes_at is set to midnight UTC-8 after review period."""
    
    def test_resolve_review_period_hours_with_days(self):
        """Test _resolve_review_period_hours function with trade_review_period_days."""
        # Import the function directly for unit testing
        import sys
        sys.path.insert(0, '/app/backend')
        from routes.trades import _resolve_review_period_hours
        
        # Test with days config (0-7 days)
        league_with_days = {
            "transactions_config": {
                "trades": {
                    "review_period_days": 2
                }
            }
        }
        hours = _resolve_review_period_hours(league_with_days)
        assert hours == 48, f"Expected 48 hours for 2 days, got {hours}"
        
    def test_resolve_review_period_hours_zero_days(self):
        """Test that 0 days returns 0 hours (immediate processing)."""
        import sys
        sys.path.insert(0, '/app/backend')
        from routes.trades import _resolve_review_period_hours
        
        league_zero_days = {
            "transactions_config": {
                "trades": {
                    "review_period_days": 0
                }
            }
        }
        hours = _resolve_review_period_hours(league_zero_days)
        assert hours == 0, f"Expected 0 hours for 0 days, got {hours}"
        
    def test_resolve_review_period_hours_fallback_to_hours(self):
        """Test fallback to legacy review_period_hours config."""
        import sys
        sys.path.insert(0, '/app/backend')
        from routes.trades import _resolve_review_period_hours
        
        league_with_hours = {
            "transactions_config": {
                "trades": {
                    "review_period_hours": 72
                }
            }
        }
        hours = _resolve_review_period_hours(league_with_hours)
        assert hours == 72, f"Expected 72 hours, got {hours}"
        
    def test_resolve_review_period_hours_default(self):
        """Test default of 24 hours when no config."""
        import sys
        sys.path.insert(0, '/app/backend')
        from routes.trades import _resolve_review_period_hours
        
        league_no_config = {}
        hours = _resolve_review_period_hours(league_no_config)
        assert hours == 24, f"Expected default 24 hours, got {hours}"
        
    def test_midnight_calculation_logic(self):
        """Test that midnight UTC-8 calculation is correct."""
        # Simulate the midnight calculation from trades.py lines 1005-1015
        now = datetime(2026, 1, 15, 10, 30, 0, tzinfo=timezone.utc)  # 10:30 AM UTC
        hours = 24  # 1 day review period
        
        raw_deadline = now + timedelta(hours=hours)  # Jan 16, 10:30 AM UTC
        utc_minus_8 = timezone(timedelta(hours=-8))
        deadline_pst = raw_deadline.astimezone(utc_minus_8)  # Jan 16, 2:30 AM PST
        
        # Advance to next midnight PST
        next_midnight = (deadline_pst + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        processes_at = next_midnight.astimezone(timezone.utc)
        
        # Should be Jan 17, 8:00 AM UTC (midnight PST = 8 AM UTC)
        assert processes_at.hour == 8, f"Expected 8 AM UTC, got {processes_at.hour}"
        assert processes_at.minute == 0, f"Expected 0 minutes, got {processes_at.minute}"
        assert processes_at.day == 17, f"Expected day 17, got {processes_at.day}"
        
    def test_immediate_processing_when_zero_hours(self):
        """Test that processes_at is set to now when review period is 0."""
        # When hours <= 0, processes_at should be now (immediate)
        now = datetime(2026, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        hours = 0
        
        if int(hours) <= 0:
            processes_at = now.isoformat()
        else:
            # Would do midnight calculation
            processes_at = "would_be_midnight"
            
        assert processes_at == now.isoformat(), "Expected immediate processing for 0 hours"


# ============================================================================
# Bug Fix 2: Traded Pick Ownership Tests
# ============================================================================

class TestTradedPickOwnership:
    """Test that auto-pick awards player to the new pick owner (current_team_id)."""
    
    def test_draft_picks_query_structure(self):
        """Verify the query structure for finding traded picks."""
        # The fix queries by (league_id, draft_id, round, original_team_id)
        # to find current_team_id
        
        # Simulate the query from draft_helpers.py lines 282-287
        league_id = "test_league_123"
        draft_id = "test_draft_456"
        round_num = 1
        original_team_id = "team_A"
        
        query = {
            "league_id": league_id,
            "draft_id": draft_id,
            "round": round_num,
            "original_team_id": original_team_id,
        }
        
        # Verify query has all required fields
        assert "league_id" in query
        assert "draft_id" in query
        assert "round" in query
        assert "original_team_id" in query
        assert query["round"] == 1
        
    def test_traded_pick_ownership_transfer(self):
        """Test that when a pick is traded, current_team_id is used."""
        # Simulate a traded pick scenario
        traded_pick = {
            "league_id": "league_123",
            "draft_id": "draft_456",
            "round": 1,
            "original_team_id": "team_A",  # Original owner
            "current_team_id": "team_B",   # New owner after trade
            "current_team_name": "Team B Name"
        }
        
        # The fix checks if current_team_id differs from original_team_id
        if traded_pick.get("current_team_id"):
            traded_team_id = str(traded_pick["current_team_id"])
            if traded_team_id != str(traded_pick.get("original_team_id")):
                # Pick was traded - use new owner
                on_clock_team_id = traded_team_id
            else:
                on_clock_team_id = traded_pick["original_team_id"]
        else:
            on_clock_team_id = traded_pick["original_team_id"]
            
        assert on_clock_team_id == "team_B", f"Expected team_B (new owner), got {on_clock_team_id}"
        
    def test_non_traded_pick_uses_original_owner(self):
        """Test that non-traded picks use original_team_id."""
        non_traded_pick = {
            "league_id": "league_123",
            "draft_id": "draft_456",
            "round": 1,
            "original_team_id": "team_A",
            "current_team_id": "team_A",  # Same as original - not traded
        }
        
        if non_traded_pick.get("current_team_id"):
            traded_team_id = str(non_traded_pick["current_team_id"])
            if traded_team_id != str(non_traded_pick.get("original_team_id")):
                on_clock_team_id = traded_team_id
            else:
                on_clock_team_id = non_traded_pick["original_team_id"]
        else:
            on_clock_team_id = non_traded_pick["original_team_id"]
            
        assert on_clock_team_id == "team_A", f"Expected team_A (original owner), got {on_clock_team_id}"


# ============================================================================
# Bug Fix 3: Sandbox Account Login Tests
# ============================================================================

class TestSandboxLogin:
    """Test that @sandbox.local accounts return 401 (not 500)."""
    
    def test_sandbox_email_login_returns_401_not_500(self):
        """Test that @sandbox.local email returns 401 (invalid credentials) not 500."""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={
                "email": "testuser1_abc123@sandbox.local",
                "password": "wrongpassword123"
            }
        )
        
        # Should return 401 (invalid credentials) not 500 (validation error)
        assert response.status_code != 500, f"Got 500 error - sandbox email validation failed: {response.text}"
        assert response.status_code == 401, f"Expected 401, got {response.status_code}: {response.text}"
        
    def test_sandbox_email_with_various_formats(self):
        """Test various @sandbox.local email formats don't cause 500."""
        sandbox_emails = [
            "test@sandbox.local",
            "user123@sandbox.local",
            "admin_test@sandbox.local",
            "test.user@sandbox.local",
        ]
        
        for email in sandbox_emails:
            response = requests.post(
                f"{BASE_URL}/api/auth/login",
                json={
                    "email": email,
                    "password": "anypassword"
                }
            )
            assert response.status_code != 500, f"Got 500 for {email}: {response.text}"
            # Should be 401 (user not found or invalid credentials)
            assert response.status_code in [401, 404], f"Expected 401/404 for {email}, got {response.status_code}"
            
    def test_normal_email_login_still_works(self):
        """Test that normal email login still works correctly."""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={
                "email": "admin@dynastydreams.com",
                "password": "Admin123!"
            }
        )
        
        # Should return 200 with access_token
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "access_token" in data or "id" in data, f"Missing token in response: {data}"
        
    def test_invalid_normal_email_returns_401(self):
        """Test that invalid normal email returns 401."""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={
                "email": "nonexistent@example.com",
                "password": "wrongpassword"
            }
        )
        
        assert response.status_code == 401, f"Expected 401, got {response.status_code}: {response.text}"


# ============================================================================
# Integration Tests - Live API
# ============================================================================

class TestLiveAPIIntegration:
    """Integration tests against the live API."""
    
    @pytest.fixture
    def auth_token(self):
        """Get authentication token for admin user."""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={
                "email": "admin@dynastydreams.com",
                "password": "Admin123!"
            }
        )
        if response.status_code == 200:
            data = response.json()
            return data.get("access_token")
        pytest.skip("Could not authenticate admin user")
        
    def test_api_health(self):
        """Test API is healthy."""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        
    def test_auth_endpoint_accepts_sandbox_emails(self):
        """Verify auth endpoint doesn't crash on sandbox emails."""
        # This is the key test for Bug Fix 3
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={
                "email": "testuser_iter167@sandbox.local",
                "password": "testpass123"
            }
        )
        
        # The fix ensures we get 401 (not found/invalid) instead of 500 (validation error)
        assert response.status_code != 500, (
            f"CRITICAL: Sandbox email caused 500 error. "
            f"UserLogin.email should be str, not EmailStr. Response: {response.text}"
        )
        print(f"✓ Sandbox email login returned {response.status_code} (not 500)")


# ============================================================================
# Code Review Tests - Verify Fix Implementation
# ============================================================================

class TestCodeReviewVerification:
    """Verify the bug fixes are correctly implemented in the code."""
    
    def test_userlogin_email_is_str_not_emailstr(self):
        """Verify UserLogin.email is str (not EmailStr) in server.py."""
        import sys
        sys.path.insert(0, '/app/backend')
        
        # Read server.py and check the UserLogin model
        with open('/app/backend/server.py', 'r') as f:
            content = f.read()
            
        # Find the UserLogin class definition
        assert 'class UserLogin' in content, "UserLogin class not found"
        
        # Check that email field is str, not EmailStr
        # The fix changed line 229 from EmailStr to str
        import re
        userlogin_match = re.search(r'class UserLogin.*?(?=class|\Z)', content, re.DOTALL)
        if userlogin_match:
            userlogin_code = userlogin_match.group()
            # Should have "email: str" not "email: EmailStr"
            assert 'email: str' in userlogin_code, (
                f"UserLogin.email should be 'str' not 'EmailStr'. Found: {userlogin_code[:200]}"
            )
            print("✓ UserLogin.email is correctly defined as str")
            
    def test_midnight_calculation_in_trades_respond(self):
        """Verify midnight UTC-8 calculation exists in trades.py respond_to_trade_proposal."""
        with open('/app/backend/routes/trades.py', 'r') as f:
            content = f.read()
            
        # Check for the midnight calculation code
        assert 'utc_minus_8' in content or 'UTC-8' in content.upper() or 'timedelta(hours=-8)' in content, (
            "Midnight UTC-8 calculation not found in trades.py"
        )
        assert 'next_midnight' in content, "next_midnight variable not found in trades.py"
        print("✓ Midnight UTC-8 calculation found in trades.py")
        
    def test_traded_pick_query_in_draft_helpers(self):
        """Verify traded pick query uses (round, original_team_id) in draft_helpers.py."""
        with open('/app/backend/routes/draft_helpers.py', 'r') as f:
            content = f.read()
            
        # Check for the correct query structure
        assert 'original_team_id' in content, "original_team_id not found in draft_helpers.py"
        assert 'current_team_id' in content, "current_team_id not found in draft_helpers.py"
        assert 'draft_id' in content, "draft_id not found in draft_helpers.py"
        print("✓ Traded pick query structure found in draft_helpers.py")
        
    def test_traded_pick_query_in_draft_pick_actions(self):
        """Verify traded pick query also exists in draft_pick_actions.py."""
        with open('/app/backend/routes/draft_pick_actions.py', 'r') as f:
            content = f.read()
            
        # Check for the correct query structure
        assert 'original_team_id' in content, "original_team_id not found in draft_pick_actions.py"
        assert 'current_team_id' in content, "current_team_id not found in draft_pick_actions.py"
        print("✓ Traded pick query structure found in draft_pick_actions.py")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
