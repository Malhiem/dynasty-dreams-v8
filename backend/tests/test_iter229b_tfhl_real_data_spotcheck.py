"""
Iter 229b — Real TFHL data spot-check for the Trade Builder differentiator.

Verifies the user's actual TFHL league: every pick returned by the
team draft-picks endpoint carries `draft_id` + `draft_name` so the
Trade Builder can render the chip ('INAUGURAL' / 'ENTRY' / 'WINTER').
"""
import os
import requests
from collections import defaultdict
from pymongo import MongoClient

API_URL = os.environ["REACT_APP_BACKEND_URL"]


def _db():
    return MongoClient(os.environ["MONGO_URL"])[os.environ.get("DB_NAME", os.environ["DB_NAME"])]


def test_tfhl_picks_all_carry_draft_id_and_draft_name():
    """Authenticate as TFHL commissioner; fetch picks for any team in
    TFHL; assert every pick has draft_id + draft_name and that two
    picks at the same (year, round) come from different drafts."""
    r = requests.post(f"{API_URL}/api/auth/login", json={
        "email": os.environ.get("TEST_OWNER_EMAIL", "test-owner@e2e.dynastydreams.com"), "password": os.environ.get("TEST_OWNER_PASSWORD", "e2e-owner-password")})
    if r.status_code != 200:
        import pytest
        pytest.skip(f"TFHL commissioner login failed: {r.status_code}")
    tok = r.json()["access_token"]
    H = {"Authorization": f"Bearer {tok}"}

    db = _db()
    league = db.leagues.find_one({"name": "TFHL"})
    if not league:
        import pytest
        pytest.skip("TFHL league not present in db")
    league_id = league.get("id") or str(league["_id"])

    team = db.teams.find_one({"league_id": league_id})
    assert team, "TFHL must have at least one team"

    r2 = requests.get(f"{API_URL}/api/teams/{team['_id']}/draft-picks", headers=H)
    assert r2.status_code == 200, r2.text
    picks = r2.json()["picks"]
    assert len(picks) > 0, "TFHL team should own picks"

    # Every pick must carry draft_id + draft_name
    for p in picks:
        assert p.get("draft_id"), f"missing draft_id on TFHL pick: {p}"
        assert p.get("draft_name"), f"missing draft_name on TFHL pick: {p}"

    # If TFHL has multiple drafts in the same year, those picks must
    # surface distinct draft_id/draft_name within the (year, round) bucket.
    by_year_round = defaultdict(list)
    for p in picks:
        by_year_round[(int(p["year"]), int(p["round"]))].append(p)
    overlaps = {k: v for k, v in by_year_round.items() if len(v) > 1}
    for key, group in overlaps.items():
        ids = {p["draft_id"] for p in group}
        names = {p["draft_name"] for p in group}
        assert len(ids) == len(group), (
            f"TFHL collision on {key}: duplicate draft_ids "
            f"{[p['draft_id'] for p in group]}")
        assert len(names) == len(group), (
            f"TFHL collision on {key}: duplicate draft_names "
            f"{[p['draft_name'] for p in group]}")
    print(f"TFHL picks={len(picks)} overlap-buckets={len(overlaps)} "
          f"distinct-drafts={len({p['draft_id'] for p in picks})}")
