"""Iter 232N.65 — Live HTTP integration tests against the preview URL.

Covers real admin auth cookie flow + the four new capabilities:
NHL dry-run+apply, CSV preview+commit, bulk actions (with roster safety),
plus a regression on GET /admin/players and GET /admin/players/audit.
"""
from __future__ import annotations

import io
import os
import pytest
import requests

BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL",
    "https://dynasty-preview.preview.emergentagent.com",
).rstrip("/")

ADMIN_EMAIL = "admin@dynastydreams.com"
ADMIN_PASSWORD = "Admin123!"


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=30,
    )
    if r.status_code != 200:
        pytest.skip(f"Admin login failed: {r.status_code} {r.text[:200]}")
    return s


# ── Regression: list + audit ────────────────────────────────────────
def test_admin_list_players(admin_session):
    r = admin_session.get(f"{BASE_URL}/api/admin/players?limit=5", timeout=30)
    assert r.status_code == 200
    body = r.json()
    assert "total" in body and "players" in body
    assert isinstance(body["players"], list)


def test_admin_players_audit(admin_session):
    r = admin_session.get(f"{BASE_URL}/api/admin/players/audit?limit=5", timeout=30)
    assert r.status_code == 200
    body = r.json()
    assert "rows" in body and "count" in body


# ── 232N.65: NHL dry-run + selective apply ──────────────────────────
def test_nhl_sync_dry_run_and_apply(admin_session):
    r = admin_session.post(
        f"{BASE_URL}/api/admin/players/sync",
        json={"dry_run": True, "team_codes": ["TOR", "MTL"]},
        timeout=60,
    )
    assert r.status_code == 200, r.text[:400]
    body = r.json()
    assert body["ok"] is True
    assert body["dry_run"] is True
    token = body["sync_token"]
    assert isinstance(token, str) and len(token) >= 16
    counts = body["diff"]["counts"]
    for k in ("new_players", "age_changes", "team_changes",
              "position_changes", "prospect_changes", "removed"):
        assert k in counts and isinstance(counts[k], int)

    # Apply nothing (empty selections) — must succeed but write zero rows.
    apply_r = admin_session.post(
        f"{BASE_URL}/api/admin/players/sync/apply",
        json={"sync_token": token},
        timeout=60,
    )
    assert apply_r.status_code == 200, apply_r.text[:400]
    ares = apply_r.json()
    assert ares["ok"] is True
    assert ares["inserted"] == 0
    assert ares["updated_age"] == 0
    assert ares["deleted"] == 0

    # Re-submit the same token → 410 (single-use).
    replay = admin_session.post(
        f"{BASE_URL}/api/admin/players/sync/apply",
        json={"sync_token": token},
        timeout=30,
    )
    assert replay.status_code == 410


def test_nhl_sync_apply_unknown_token(admin_session):
    r = admin_session.post(
        f"{BASE_URL}/api/admin/players/sync/apply",
        json={"sync_token": "nope-does-not-exist-abcdef"},
        timeout=30,
    )
    assert r.status_code == 410


# ── 232N.65: CSV preview + commit ───────────────────────────────────
CSV_BODY = (
    "name,team,position,age,is_prospect,nhl_id\n"
    "TEST_Valid One,TOR,C,25,false,TEST_csv_valid_1\n"
    "TEST_Bad Position,MTL,ZZ,26,false,TEST_csv_bad_pos\n"
    ",,,,,\n"
    "TEST_Age Range,BOS,D,99,false,TEST_csv_bad_age\n"
)


def test_csv_preview_and_commit(admin_session):
    files = {"file": ("preview.csv", io.BytesIO(CSV_BODY.encode()), "text/csv")}
    r = admin_session.post(
        f"{BASE_URL}/api/admin/players/csv/preview",
        files=files,
        timeout=30,
    )
    assert r.status_code == 200, r.text[:400]
    body = r.json()
    assert body["ok"] is True
    assert body["totals"]["valid"] == 1
    assert body["totals"]["errors"] >= 2
    rows = body["rows"]
    assert rows[0]["valid"] is True
    assert rows[1]["valid"] is False
    assert any("position" in e for e in rows[1]["errors"])
    token = body["preview_token"]
    assert isinstance(token, str)

    # Commit only the first valid row.
    commit = admin_session.post(
        f"{BASE_URL}/api/admin/players/csv/commit",
        json={"preview_token": token, "apply_indices": [0]},
        timeout=30,
    )
    assert commit.status_code == 200, commit.text[:400]
    cbody = commit.json()
    assert cbody["ok"] is True
    assert cbody["upserted"] == 1

    # Second commit with same token → 410
    replay = admin_session.post(
        f"{BASE_URL}/api/admin/players/csv/commit",
        json={"preview_token": token},
        timeout=30,
    )
    assert replay.status_code == 410

    # Cleanup — remove the TEST_ row we upserted
    listing = admin_session.get(
        f"{BASE_URL}/api/admin/players?q=TEST_Valid", timeout=30
    ).json()
    for p in listing.get("players", []):
        admin_session.delete(f"{BASE_URL}/api/admin/players/{p['id']}", timeout=15)


# ── 232N.65: Bulk actions ───────────────────────────────────────────
@pytest.fixture
def two_test_players(admin_session):
    ids = []
    for i in range(2):
        r = admin_session.post(
            f"{BASE_URL}/api/admin/players",
            json={
                "name": f"TEST_BulkPlayer_{i}",
                "team": "TOR",
                "position": "C",
                "age": 25,
                "is_prospect": False,
                "league": "NHL",
                "nhl_id": f"TEST_bulk_{i}_" + os.urandom(3).hex(),
            },
            timeout=15,
        )
        assert r.status_code == 200, r.text[:200]
        ids.append(r.json()["id"])
    yield ids
    # Cleanup
    for pid in ids:
        admin_session.delete(f"{BASE_URL}/api/admin/players/{pid}", timeout=15)


def test_bulk_mark_and_unmark_prospect(admin_session, two_test_players):
    ids = two_test_players
    r = admin_session.post(
        f"{BASE_URL}/api/admin/players/bulk",
        json={"action": "mark_prospect", "player_ids": ids},
        timeout=30,
    )
    assert r.status_code == 200, r.text[:400]
    body = r.json()
    assert body["ok"] is True
    assert body["affected"] == 2

    # Verify persisted
    for pid in ids:
        # Fetch via list search then check the flag
        lst = admin_session.get(
            f"{BASE_URL}/api/admin/players?q=TEST_BulkPlayer", timeout=15
        ).json()
        match = [p for p in lst["players"] if p["id"] == pid]
        assert match and match[0].get("is_prospect") is True

    # Unmark
    r2 = admin_session.post(
        f"{BASE_URL}/api/admin/players/bulk",
        json={"action": "unmark_prospect", "player_ids": ids},
        timeout=30,
    )
    assert r2.status_code == 200
    assert r2.json()["affected"] == 2


def test_bulk_requires_scope(admin_session):
    r = admin_session.post(
        f"{BASE_URL}/api/admin/players/bulk",
        json={"action": "delete"},
        timeout=15,
    )
    assert r.status_code == 400


def test_bulk_delete_affects_created_players(admin_session):
    # Create two players just to delete
    ids = []
    for i in range(2):
        r = admin_session.post(
            f"{BASE_URL}/api/admin/players",
            json={
                "name": f"TEST_DeleteMe_{i}",
                "team": "TOR",
                "position": "C",
                "age": 25,
                "league": "NHL",
                "nhl_id": f"TEST_del_{i}_" + os.urandom(3).hex(),
            },
            timeout=15,
        )
        assert r.status_code == 200
        ids.append(r.json()["id"])

    r = admin_session.post(
        f"{BASE_URL}/api/admin/players/bulk",
        json={"action": "delete", "player_ids": ids},
        timeout=30,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["affected"] == 2
    assert body["skipped_on_roster"] == 0
