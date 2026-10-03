#!/usr/bin/env python3
"""
Dynasty Dreams Backend API Testing
Tests all API endpoints for the NHL fantasy sports platform
"""

import requests
import sys
import json
from datetime import datetime
from typing import Dict, Any, Optional

class DynastyDreamsAPITester:
    def __init__(self, base_url: str = "https://dynasty-preview.preview.emergentagent.com"):
        self.base_url = base_url.rstrip('/')
        self.session = requests.Session()
        self.access_token = None
        self.refresh_token = None
        self.tests_run = 0
        self.tests_passed = 0
        self.test_results = []
        
        # Test data
        self.admin_email = "admin@dynastydreams.com"
        self.admin_password = "Admin123!"
        self.test_user_email = f"test_user_{datetime.now().strftime('%H%M%S')}@test.com"
        self.test_user_password = "TestPass123!"
        self.test_league_id = None
        self.test_team_id = None

    def log_test(self, name: str, success: bool, details: str = "", response_data: Any = None):
        """Log test result"""
        self.tests_run += 1
        if success:
            self.tests_passed += 1
            print(f"✅ {name}")
        else:
            print(f"❌ {name} - {details}")
        
        self.test_results.append({
            "test": name,
            "success": success,
            "details": details,
            "response_data": response_data
        })

    def make_request(self, method: str, endpoint: str, data: Optional[Dict] = None, 
                    expected_status: int = 200, use_auth: bool = False) -> tuple[bool, Any]:
        """Make API request and return success status and response data"""
        url = f"{self.base_url}/api{endpoint}"
        headers = {'Content-Type': 'application/json'}
        
        if use_auth and self.access_token:
            headers['Authorization'] = f'Bearer {self.access_token}'
        
        try:
            if method == 'GET':
                response = self.session.get(url, headers=headers)
            elif method == 'POST':
                response = self.session.post(url, json=data, headers=headers)
            elif method == 'PUT':
                response = self.session.put(url, json=data, headers=headers)
            elif method == 'DELETE':
                response = self.session.delete(url, headers=headers)
            else:
                return False, f"Unsupported method: {method}"

            success = response.status_code == expected_status
            try:
                response_data = response.json()
            except:
                response_data = {"status_code": response.status_code, "text": response.text}
            
            return success, response_data
            
        except Exception as e:
            return False, f"Request failed: {str(e)}"

    def test_health_endpoints(self):
        """Test basic health endpoints"""
        print("\n🔍 Testing Health Endpoints...")
        
        # Test root endpoint
        success, data = self.make_request('GET', '/')
        self.log_test("GET /api/", success, 
                     "" if success else f"Failed: {data}")
        
        # Test health endpoint
        success, data = self.make_request('GET', '/health')
        self.log_test("GET /api/health", success,
                     "" if success else f"Failed: {data}")

    def test_auth_registration(self):
        """Test user registration"""
        print("\n🔍 Testing User Registration...")
        
        # Test user registration
        user_data = {
            "email": self.test_user_email,
            "password": self.test_user_password,
            "name": "Test User"
        }
        
        success, data = self.make_request('POST', '/auth/register', user_data, 200)
        self.log_test("POST /api/auth/register", success,
                     "" if success else f"Failed: {data}")
        
        if success:
            # Check if we got user data back
            if 'id' in data and 'email' in data:
                self.log_test("Registration returns user data", True)
            else:
                self.log_test("Registration returns user data", False, "Missing user data in response")

    def test_auth_login(self):
        """Test user login with admin credentials"""
        print("\n🔍 Testing User Login...")
        
        # Test admin login
        login_data = {
            "email": self.admin_email,
            "password": self.admin_password
        }
        
        success, data = self.make_request('POST', '/auth/login', login_data, 200)
        self.log_test("POST /api/auth/login (admin)", success,
                     "" if success else f"Failed: {data}")
        
        if success and 'id' in data:
            # Login successful, check for cookies or token
            self.log_test("Login returns user data", True)
            # Note: In real implementation, we'd extract token from cookies
            # For testing, we'll create a mock token for subsequent requests
            self.access_token = "mock_token_for_testing"
        else:
            self.log_test("Login returns user data", False, "No user data in response")

    def test_auth_endpoints(self):
        """Test other auth endpoints"""
        print("\n🔍 Testing Auth Endpoints...")
        
        # Test /auth/me (requires authentication)
        success, data = self.make_request('GET', '/auth/me', use_auth=True, expected_status=401)
        # We expect 401 since we don't have real auth token
        self.log_test("GET /api/auth/me (without auth)", success,
                     "" if success else f"Expected 401, got: {data}")
        
        # Test logout
        success, data = self.make_request('POST', '/auth/logout')
        self.log_test("POST /api/auth/logout", success,
                     "" if success else f"Failed: {data}")
        
        # Test forgot password
        forgot_data = {"email": self.admin_email}
        success, data = self.make_request('POST', '/auth/forgot-password', forgot_data)
        self.log_test("POST /api/auth/forgot-password", success,
                     "" if success else f"Failed: {data}")

    def test_leagues_endpoints(self):
        """Test league-related endpoints"""
        print("\n🔍 Testing League Endpoints...")
        
        # Test get leagues (public)
        success, data = self.make_request('GET', '/leagues')
        self.log_test("GET /api/leagues", success,
                     "" if success else f"Failed: {data}")
        
        # Test create league (requires auth - will fail)
        league_data = {
            "name": "Test League",
            "format": "dynasty",
            "scoring_format": "head_to_head",
            "max_teams": 12,
            "salary_cap_enabled": False,
            "draft_type": "snake",
            "roster_spots": 20,
            "keepers_allowed": 0,
            "is_private": False
        }
        
        success, data = self.make_request('POST', '/leagues', league_data, 401, use_auth=True)
        # Expect 401 since we don't have real auth
        self.log_test("POST /api/leagues (without real auth)", success,
                     "" if success else f"Expected 401, got: {data}")

    def test_teams_endpoints(self):
        """Test team-related endpoints"""
        print("\n🔍 Testing Team Endpoints...")
        
        # Test get teams
        success, data = self.make_request('GET', '/teams')
        self.log_test("GET /api/teams", success,
                     "" if success else f"Failed: {data}")

    def test_players_endpoints(self):
        """Test player-related endpoints"""
        print("\n🔍 Testing Player Endpoints...")
        
        # Test get players
        success, data = self.make_request('GET', '/players')
        self.log_test("GET /api/players", success,
                     "" if success else f"Failed: {data}")
        
        # Test players with search
        success, data = self.make_request('GET', '/players?search=test')
        self.log_test("GET /api/players?search=test", success,
                     "" if success else f"Failed: {data}")
        
        # Test players with pagination
        success, data = self.make_request('GET', '/players?page=1&limit=10')
        self.log_test("GET /api/players?page=1&limit=10", success,
                     "" if success else f"Failed: {data}")

    def test_drafts_endpoints(self):
        """Test draft-related endpoints"""
        print("\n🔍 Testing Draft Endpoints...")
        
        # Test create draft (requires auth - will fail)
        draft_data = {
            "league_id": "test_league_id",
            "draft_type": "snake",
            "scheduled_time": "2024-01-01T12:00:00Z",
            "rounds": 15,
            "time_per_pick": 60
        }
        
        success, data = self.make_request('POST', '/drafts', draft_data, 401, use_auth=True)
        self.log_test("POST /api/drafts (without real auth)", success,
                     "" if success else f"Expected 401, got: {data}")

    def test_payment_endpoints(self):
        """Test payment-related endpoints"""
        print("\n🔍 Testing Payment Endpoints...")
        
        # Test create checkout (requires auth - will fail)
        payment_data = {
            "package_type": "premium_monthly",
            "origin_url": "https://test.com"
        }
        
        success, data = self.make_request('POST', '/payments/checkout', payment_data, 401, use_auth=True)
        self.log_test("POST /api/payments/checkout (without real auth)", success,
                     "" if success else f"Expected 401, got: {data}")

    def run_all_tests(self):
        """Run all API tests"""
        print("🚀 Starting Dynasty Dreams API Tests...")
        print(f"Testing against: {self.base_url}")
        
        try:
            self.test_health_endpoints()
            self.test_auth_registration()
            self.test_auth_login()
            self.test_auth_endpoints()
            self.test_leagues_endpoints()
            self.test_teams_endpoints()
            self.test_players_endpoints()
            self.test_drafts_endpoints()
            self.test_payment_endpoints()
            
        except Exception as e:
            print(f"❌ Test suite failed with error: {e}")
            return False
        
        # Print summary
        print(f"\n📊 Test Results: {self.tests_passed}/{self.tests_run} passed")
        
        if self.tests_passed < self.tests_run:
            print("\n❌ Failed Tests:")
            for result in self.test_results:
                if not result['success']:
                    print(f"  - {result['test']}: {result['details']}")
        
        return self.tests_passed == self.tests_run

def main():
    """Main test runner"""
    tester = DynastyDreamsAPITester()
    success = tester.run_all_tests()
    
    # Save detailed results
    with open('/app/test_reports/backend_test_results.json', 'w') as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "total_tests": tester.tests_run,
            "passed_tests": tester.tests_passed,
            "success_rate": tester.tests_passed / tester.tests_run if tester.tests_run > 0 else 0,
            "results": tester.test_results
        }, f, indent=2)
    
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())