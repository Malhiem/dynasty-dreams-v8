"""Live regression for iter232N.2 shared status_flags + undrafted_only filter."""
import os, requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://dynasty-preview.preview.emergentagent.com").rstrip("/")
LEAGUE = "6a3a0781a842ea2f7bcdc7cb"  # TFHL
DRAFT = "6a3c00447f735c0f8adc92f8"    # Summer Entry


def _ok(r):
    assert r.status_code == 200, f"{r.request.url} -> {r.status_code} {r.text[:200]}"
    return r.json()


def test_players_undrafted_only_shrinks_and_stamps():
    all_p = _ok(requests.get(f"{BASE}/api/players", params={"league_id": LEAGUE, "limit": 2000}))
    und_p = _ok(requests.get(f"{BASE}/api/players", params={"league_id": LEAGUE, "undrafted_only": "true", "limit": 2000}))
    a_list = all_p if isinstance(all_p, list) else all_p.get("players", all_p.get("data", []))
    u_list = und_p if isinstance(und_p, list) else und_p.get("players", und_p.get("data", []))
    print(f"players all={len(a_list)} undrafted={len(u_list)}")
    assert len(u_list) <= len(a_list)
    # status_flags stamped on every row
    for row in a_list[:20]:
        assert "status_flags" in row, f"missing status_flags: {list(row.keys())[:10]}"
    for row in u_list[:20]:
        assert row["status_flags"]["undrafted"] is True


def test_waivers_undrafted_only_excludes_drafted():
    all_w = _ok(requests.get(f"{BASE}/api/waivers/available", params={"league_id": LEAGUE}))
    und_w = _ok(requests.get(f"{BASE}/api/waivers/available", params={"league_id": LEAGUE, "undrafted_only": "true"}))
    a_list = all_w if isinstance(all_w, list) else all_w.get("players", all_w.get("data", []))
    u_list = und_w if isinstance(und_w, list) else und_w.get("players", und_w.get("data", []))
    print(f"waivers all={len(a_list)} undrafted={len(u_list)}")
    assert len(u_list) <= len(a_list)
    for row in a_list[:20]:
        assert "status_flags" in row


def test_draft_eligible_undrafted_only_shrinks():
    all_e = _ok(requests.get(f"{BASE}/api/drafts/{DRAFT}/eligible-players"))
    und_e = _ok(requests.get(f"{BASE}/api/drafts/{DRAFT}/eligible-players", params={"undrafted_only": "true"}))
    a_list = all_e if isinstance(all_e, list) else all_e.get("players", all_e.get("data", []))
    u_list = und_e if isinstance(und_e, list) else und_e.get("players", und_e.get("data", []))
    print(f"eligible all={len(a_list)} undrafted={len(u_list)}")
    assert len(u_list) <= len(a_list)


def test_roster_stamps_status_flags():
    # Find a TFHL team
    teams = _ok(requests.get(f"{BASE}/api/leagues/{LEAGUE}/teams"))
    t_list = teams if isinstance(teams, list) else teams.get("teams", [])
    assert t_list, "no teams"
    team_id = t_list[0].get("id") or t_list[0].get("_id") or t_list[0].get("team_id")
    r = _ok(requests.get(f"{BASE}/api/roster/{team_id}"))
    players = r if isinstance(r, list) else r.get("players", r.get("roster", []))
    print(f"roster team={team_id} players={len(players)}")
    assert players, "empty roster"
    for p in players[:10]:
        assert "status_flags" in p, f"missing status_flags on roster row: {list(p.keys())[:10]}"
