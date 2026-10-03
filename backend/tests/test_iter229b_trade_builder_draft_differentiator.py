"""
Iter 229b — Trade Builder same-year multi-draft differentiator.

Backend contract verification: GET /api/teams/{id}/draft-picks must
return picks with BOTH `draft_id` and `draft_name` populated so the
frontend Trade Builder can render a chip (e.g. 'INAUGURAL' / 'ENTRY')
next to '2026 Rd 2' to disambiguate same-year picks that come from
different parent drafts.

Data-integrity invariant: the tuple (draft_id, year, round,
original_team_id) MUST be unique across picks so the frontend cart's
id generator does not collide between an Inaugural Rd 2 and an Entry
Rd 2 in the same year.
"""
import os
import uuid
import requests
from pymongo import MongoClient

API_URL = os.environ["REACT_APP_BACKEND_URL"]


def _db():
    return MongoClient(os.environ["MONGO_URL"])[os.environ.get("DB_NAME", os.environ["DB_NAME"])]


def _register(prefix="i229b"):
    s = uuid.uuid4().hex[:8]
    email = f"{prefix}_{s}@example.com"
    requests.post(f"{API_URL}/api/auth/register", json={
        "email": email, "password": "Pass123!",
        "username": f"{prefix}_{s}", "name": prefix.title(),
    }).raise_for_status()
    r = requests.post(f"{API_URL}/api/auth/login",
                      json={"email": email, "password": "Pass123!"})
    return email, r.json()["access_token"]


def _seed_tfhl_like_league():
    """Spin up a TFHL-like league with Inaugural(5 rounds) + Entry(5 rounds),
    both in 2026. Returns (league, headers, team_doc)."""
    _, tok = _register()
    H = {"Authorization": f"Bearer {tok}"}
    r = requests.post(f"{API_URL}/api/leagues", headers=H, json={
        "name": f"i229b-{uuid.uuid4().hex[:6]}", "format": "dynasty",
        "scoring_format": "head_to_head", "max_teams": 4,
        "draft_type": "snake", "roster_spots": 25,
    })
    r.raise_for_status()
    league = r.json()

    drafts_payload = [
        ("Inaugural Draft", "2026-05-01T19:00:00Z", 5),
        ("2026 Entry Draft", "2026-07-15T19:00:00Z", 5),
    ]
    draft_ids = []
    for name, sched, rounds in drafts_payload:
        rr = requests.post(f"{API_URL}/api/drafts", headers=H, json={
            "league_id": league["id"], "name": name,
            "scheduled_time": sched,
            "total_rounds": rounds, "time_per_pick": 60,
            "pick_trading_enabled": True, "trading_window_opens": "immediately",
        })
        rr.raise_for_status()
        body = rr.json()
        draft_ids.append(body.get("_id") or body.get("id"))

    db = _db()
    team = db.teams.find_one({"league_id": league["id"]})
    assert team, "Commissioner team should be auto-created"
    return league, H, team, draft_ids


# ─── Trade Builder contract tests ──────────────────────────────────────

def test_picks_carry_both_draft_id_and_draft_name():
    """Every pick must surface BOTH draft_id and draft_name so the
    frontend's TradeDraftPick interface can render the differentiator
    chip."""
    league, H, team, draft_ids = _seed_tfhl_like_league()

    r = requests.get(f"{API_URL}/api/teams/{team['_id']}/draft-picks", headers=H)
    assert r.status_code == 200, r.text
    picks = r.json()["picks"]
    assert len(picks) == 10, f"expected 5+5=10 picks, got {len(picks)}"

    for p in picks:
        assert p.get("draft_id"), f"pick missing draft_id: {p}"
        assert p.get("draft_name"), f"pick missing draft_name: {p}"
        assert isinstance(p["draft_id"], str)
        assert isinstance(p["draft_name"], str)
        # draft_id must point at one of the two drafts we created.
        assert p["draft_id"] in draft_ids, (
            f"draft_id {p['draft_id']} not in {draft_ids}")


def test_same_year_picks_have_distinct_draft_id_and_draft_name():
    """The whole point of iter 229b — two picks at the same (year, round)
    but from different parent drafts MUST surface distinct draft_id +
    draft_name so the Trade Builder chip ('INAUGURAL' vs 'ENTRY')
    renders correctly."""
    league, H, team, draft_ids = _seed_tfhl_like_league()
    r = requests.get(f"{API_URL}/api/teams/{team['_id']}/draft-picks", headers=H)
    picks = r.json()["picks"]

    # Group by (year, round) — every group of size>1 must have unique
    # draft_id AND draft_name within the group.
    from collections import defaultdict
    groups = defaultdict(list)
    for p in picks:
        groups[(int(p["year"]), int(p["round"]))].append(p)

    collisions = [k for k, v in groups.items() if len(v) > 1]
    assert collisions, "expected same-(year,round) collisions across the two drafts"
    for key in collisions:
        ids = {p["draft_id"] for p in groups[key]}
        names = {p["draft_name"] for p in groups[key]}
        assert len(ids) == len(groups[key]), (
            f"{key}: draft_ids not unique — {[p['draft_id'] for p in groups[key]]}")
        assert len(names) == len(groups[key]), (
            f"{key}: draft_names not unique — {[p['draft_name'] for p in groups[key]]}")
        assert "Inaugural Draft" in names
        assert "2026 Entry Draft" in names


def test_tuple_draft_id_year_round_original_team_is_unique():
    """Data-integrity invariant for the frontend cart id generator:
    no two picks may share (draft_id, year, round, original_team_id)."""
    league, H, team, _ = _seed_tfhl_like_league()
    r = requests.get(f"{API_URL}/api/teams/{team['_id']}/draft-picks", headers=H)
    picks = r.json()["picks"]

    seen = set()
    for p in picks:
        key = (p.get("draft_id"), p.get("year"),
               p.get("round"), p.get("original_team_id"))
        assert key not in seen, f"collision on {key}"
        seen.add(key)
    # Sanity — 5 rounds x 2 drafts x 1 own team = 10 unique tuples.
    assert len(seen) == 10


def test_draft_name_matches_parent_draft_record():
    """draft_name surfaced on the pick must equal the parent draft's
    name in the drafts collection (not a fallback like '2026 Draft')."""
    league, H, team, draft_ids = _seed_tfhl_like_league()
    db = _db()
    drafts_by_id = {str(d["_id"]): d["name"]
                    for d in db.drafts.find({"league_id": league["id"]})}

    r = requests.get(f"{API_URL}/api/teams/{team['_id']}/draft-picks", headers=H)
    for p in r.json()["picks"]:
        assert p["draft_name"] == drafts_by_id[p["draft_id"]], (
            f"draft_name mismatch: pick={p['draft_name']!r} "
            f"vs draft record={drafts_by_id[p['draft_id']]!r}")
