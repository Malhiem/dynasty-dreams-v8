"""League activity feed, transactions and trade history are league-member reads;
the legacy activity chat post is member-only too. They used to need no login."""
import requests

from security_http_fixtures import API_URL, security_db, security_users, private_team  # noqa: F401

READS = ("/api/activity/{lid}", "/api/leagues/{lid}/transactions", "/api/leagues/{lid}/trade-history")


def test_members_can_read_and_everyone_else_cannot(private_team, security_users):
    lid, outsider = private_team["league_id"], security_users()
    for path in READS:
        url = API_URL + path.format(lid=lid)
        assert requests.get(url, headers=private_team["owner"]["headers"], timeout=20).status_code == 200, path
        assert requests.get(url, headers=outsider["headers"], timeout=20).status_code == 403, path
        assert requests.get(url, timeout=20).status_code == 401, path


def test_only_members_can_post_to_the_activity_chat(private_team, security_users, security_db):
    lid, outsider = private_team["league_id"], security_users()
    url = f"{API_URL}/api/activity/{lid}/chat"
    assert requests.post(url, json={"text": "spam"}, headers=outsider["headers"], timeout=20).status_code == 403
    assert requests.post(url, json={"text": "spam"}, timeout=20).status_code == 401
    assert security_db.activity_feed.count_documents({"league_id": lid, "message": "spam"}) == 0
    assert requests.post(url, json={"text": "hello"}, headers=private_team["owner"]["headers"], timeout=20).status_code == 200
