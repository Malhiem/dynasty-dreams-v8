"""Paging the eligible-players list must be stable: players tied on points
used to repeat on one page and vanish from another because the sort had no
tiebreaker, so clients that load page after page saw duplicates and gaps."""
import requests
from bson import ObjectId

from security_http_fixtures import API_URL, security_db, security_users  # noqa: F401


def test_pages_do_not_overlap_or_skip(security_db, security_users):
    user = security_users()
    draft_id = str(security_db.drafts.insert_one({
        "league_id": "000000000000000000000001", "status": "scheduled", "picks": [], "player_criteria": "all",
    }).inserted_id)
    try:
        def page(n):
            r = requests.get(f"{API_URL}/api/drafts/{draft_id}/eligible-players",
                             params={"page": n, "limit": 25}, headers=user["headers"], timeout=15)
            assert r.status_code == 200, r.text
            return r.json()

        first = page(1)
        pages = min(first["pages"], 6)
        assert first["total"] > 25 * 3, "needs a pool with ties across several pages"
        seen, ranks = [], []
        for n in range(1, pages + 1):
            body = page(n)
            seen += [p["id"] for p in body["players"]]
            ranks += [p["ranking"] for p in body["players"]]
        assert len(seen) == len(set(seen)), "a player appeared on more than one page"
        assert ranks == list(range(1, len(seen) + 1)), "ranking has gaps or repeats across pages"
    finally:
        security_db.drafts.delete_one({"_id": ObjectId(draft_id)})
