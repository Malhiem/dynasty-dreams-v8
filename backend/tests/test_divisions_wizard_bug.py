"""
Test: Wizard setup doesn't see existing divisions and conference alignment
Bug: Setup wizard should accurately depict all league administration settings if previously configured.

Fix verification:
1. GET /api/teams?league_id={id} now returns 'division' and 'conference' fields for each team
2. GET /api/leagues/{id}/divisions returns the full division structure including team assignments
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://dynasty-preview.preview.emergentagent.com')

# Test leagues from the bug report
STAT_CHASERS_ROTO_ID = "69e46af167999bfb85c39629"  # 14 teams, 2 divisions (North/South), 1 conference (Test)
FROZEN_DYNASTY_ID = "69e46af167999bfb85c3962a"     # 16 teams, 4 divisions, 2 conferences


@pytest.fixture(scope="module")
def auth_session():
    """Authenticated session for API calls"""
    session = requests.Session()
    resp = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": os.environ.get("ADMIN_EMAIL", "admin@e2e.dynastydreams.com"),
        "password": os.environ.get("ADMIN_PASSWORD", "e2e-admin-password")
    })
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return session


class TestTeamsEndpointDivisionFields:
    """Verify GET /api/teams returns division and conference fields"""

    def test_stat_chasers_teams_have_division_fields(self, auth_session):
        """Stat Chasers Roto teams should have division and conference fields"""
        resp = auth_session.get(f"{BASE_URL}/api/teams?league_id={STAT_CHASERS_ROTO_ID}")
        assert resp.status_code == 200
        teams = resp.json()

        # Should have 14 teams
        assert len(teams) == 14, f"Expected 14 teams, got {len(teams)}"

        # All teams should have division and conference fields
        for team in teams:
            assert "division" in team, f"Team {team.get('name')} missing 'division' field"
            assert "conference" in team, f"Team {team.get('name')} missing 'conference' field"
            # Verify they're not null (this league has divisions configured)
            assert team["division"] is not None, f"Team {team.get('name')} has null division"
            assert team["conference"] is not None, f"Team {team.get('name')} has null conference"

    def test_stat_chasers_correct_divisions(self, auth_session):
        """Stat Chasers Roto should have North and South divisions"""
        resp = auth_session.get(f"{BASE_URL}/api/teams?league_id={STAT_CHASERS_ROTO_ID}")
        assert resp.status_code == 200
        teams = resp.json()

        divisions = set(t["division"] for t in teams)
        assert divisions == {"North", "South"}, f"Expected North/South divisions, got {divisions}"

        conferences = set(t["conference"] for t in teams)
        assert conferences == {"Test"}, f"Expected Test conference, got {conferences}"

    def test_frozen_dynasty_teams_have_division_fields(self, auth_session):
        """Frozen Dynasty teams should have division and conference fields"""
        resp = auth_session.get(f"{BASE_URL}/api/teams?league_id={FROZEN_DYNASTY_ID}")
        assert resp.status_code == 200
        teams = resp.json()

        # Should have 16 teams
        assert len(teams) == 16, f"Expected 16 teams, got {len(teams)}"

        # All teams should have division and conference fields
        for team in teams:
            assert "division" in team, f"Team {team.get('name')} missing 'division' field"
            assert "conference" in team, f"Team {team.get('name')} missing 'conference' field"
            assert team["division"] is not None, f"Team {team.get('name')} has null division"
            assert team["conference"] is not None, f"Team {team.get('name')} has null conference"

    def test_frozen_dynasty_correct_divisions(self, auth_session):
        """Frozen Dynasty should have 4 NHL-style divisions in 2 conferences"""
        resp = auth_session.get(f"{BASE_URL}/api/teams?league_id={FROZEN_DYNASTY_ID}")
        assert resp.status_code == 200
        teams = resp.json()

        divisions = set(t["division"] for t in teams)
        expected_divisions = {"Atlantic", "Metropolitan", "Central", "Pacific"}
        assert divisions == expected_divisions, f"Expected {expected_divisions}, got {divisions}"

        conferences = set(t["conference"] for t in teams)
        expected_conferences = {"Eastern", "Western"}
        assert conferences == expected_conferences, f"Expected {expected_conferences}, got {conferences}"

        # Verify correct division-conference mapping
        for team in teams:
            if team["division"] in ["Atlantic", "Metropolitan"]:
                assert team["conference"] == "Eastern", f"Team {team['name']} in {team['division']} should be Eastern"
            else:
                assert team["conference"] == "Western", f"Team {team['name']} in {team['division']} should be Western"

    def test_frozen_dynasty_4_teams_per_division(self, auth_session):
        """Frozen Dynasty should have 4 teams per division"""
        resp = auth_session.get(f"{BASE_URL}/api/teams?league_id={FROZEN_DYNASTY_ID}")
        assert resp.status_code == 200
        teams = resp.json()

        by_division = {}
        for team in teams:
            div = team["division"]
            by_division.setdefault(div, []).append(team["name"])

        for div, team_names in by_division.items():
            assert len(team_names) == 4, f"Division {div} should have 4 teams, got {len(team_names)}: {team_names}"


class TestDivisionsEndpoint:
    """Verify GET /api/leagues/{id}/divisions returns full structure"""

    def test_stat_chasers_divisions_endpoint(self, auth_session):
        """Stat Chasers Roto divisions endpoint should return full structure"""
        resp = auth_session.get(f"{BASE_URL}/api/leagues/{STAT_CHASERS_ROTO_ID}/divisions")
        assert resp.status_code == 200
        data = resp.json()

        # Should have divisions array
        assert "divisions" in data
        divisions = data["divisions"]
        assert len(divisions) == 2, f"Expected 2 divisions, got {len(divisions)}"

        # Each division should have required fields
        for div in divisions:
            assert "division" in div
            assert "conference" in div
            assert "team_ids" in div
            assert "teams" in div
            assert len(div["teams"]) > 0, f"Division {div['division']} has no teams"

        # Should have no unassigned teams
        assert len(data.get("unassigned", [])) == 0, "Should have no unassigned teams"

        # Should have division_conference_map
        assert "division_conference_map" in data
        dcm = data["division_conference_map"]
        assert dcm.get("North") == "Test"
        assert dcm.get("South") == "Test"

    def test_frozen_dynasty_divisions_endpoint(self, auth_session):
        """Frozen Dynasty divisions endpoint should return full structure"""
        resp = auth_session.get(f"{BASE_URL}/api/leagues/{FROZEN_DYNASTY_ID}/divisions")
        assert resp.status_code == 200
        data = resp.json()

        # Should have 4 divisions
        divisions = data["divisions"]
        assert len(divisions) == 4, f"Expected 4 divisions, got {len(divisions)}"

        # Verify division names and conferences
        div_names = {d["division"] for d in divisions}
        assert div_names == {"Atlantic", "Metropolitan", "Central", "Pacific"}

        # Verify each division has correct conference
        for div in divisions:
            if div["division"] in ["Atlantic", "Metropolitan"]:
                assert div["conference"] == "Eastern"
            else:
                assert div["conference"] == "Western"

            # Each division should have 4 teams
            assert len(div["teams"]) == 4, f"Division {div['division']} should have 4 teams"

        # Should have no unassigned teams
        assert len(data.get("unassigned", [])) == 0


class TestLeagueSettingsHydration:
    """Verify league settings are correctly returned for wizard hydration"""

    def test_stat_chasers_league_settings(self, auth_session):
        """Stat Chasers Roto league settings should be returned"""
        resp = auth_session.get(f"{BASE_URL}/api/leagues/{STAT_CHASERS_ROTO_ID}")
        assert resp.status_code == 200
        league = resp.json()

        # Verify key fields exist
        assert league.get("id") == STAT_CHASERS_ROTO_ID
        assert league.get("name") == "Stat Chasers Roto"
        assert "max_teams" in league
        assert "roster_spots" in league
        assert "playoffs_enabled" in league

    def test_frozen_dynasty_league_settings(self, auth_session):
        """Frozen Dynasty league settings should be returned"""
        resp = auth_session.get(f"{BASE_URL}/api/leagues/{FROZEN_DYNASTY_ID}")
        assert resp.status_code == 200
        league = resp.json()

        assert league.get("id") == FROZEN_DYNASTY_ID
        assert league.get("name") == "Frozen Dynasty"
        assert "max_teams" in league
        assert "roster_spots" in league
        assert "playoffs_enabled" in league


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
