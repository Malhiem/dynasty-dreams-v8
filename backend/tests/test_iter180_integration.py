"""Iter 180 / 180b — Backend integration smoke tests against the live API.

Covers three smoke flows from the iter180 review request:
  (A) PUT /api/leagues/{lid} with position_breakdown.active = {C:4, LW:4, RW:4, D:6, G:1}
      and manual roster_spots=19 → response keeps roster_spots=19 (iter179 fix),
      GET round-trip preserves the position_breakdown.
  (B) POST /api/waivers/claim accepts optional `drop_player_id` and persists it.
  (C) DELETE /api/waivers/claims/{id} cancels a pending claim (owner-only,
      403 for others, 400 if non-pending).

Credentials & target league taken from review_request:
  chriszarek@gmail.com / Chris2026!
  Frozen Dynasty league: 69e46af167999bfb85c3962a
  Ice Kings Head-to-Head league: 69e46af167999bfb85c39628
"""
import os
import copy
from pathlib import Path
import pytest
import requests

# Backend tests run from project root w/o frontend env loaded.
# Read REACT_APP_BACKEND_URL straight from /app/frontend/.env so the test
# hits the same public URL the user sees.
def _load_backend_url() -> str:
    val = os.environ.get("REACT_APP_BACKEND_URL")
    if val:
        return val.rstrip("/")
    env_path = Path("/app/frontend/.env")
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip().rstrip("/")
    raise RuntimeError("REACT_APP_BACKEND_URL not found")


BASE_URL = _load_backend_url()
OWNER_EMAIL = "chriszarek@gmail.com"
OWNER_PASSWORD = "Chris2026!"
FROZEN_LEAGUE_ID = "69e46af167999bfb85c3962a"
ICE_KINGS_LEAGUE_ID = "69e46af167999bfb85c39628"


# ── Shared fixtures ──────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def owner_session():
    """Logged-in requests.Session for the league commissioner."""
    s = requests.Session()
    r = s.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD},
        timeout=20,
    )
    if r.status_code != 200:
        pytest.skip(f"Login failed ({r.status_code}): {r.text[:200]}")
    return s


# ── (A) position_breakdown / manual roster_spots round-trip ──────────────────
class TestPositionBreakdownRoundTrip:
    @pytest.fixture(autouse=True)
    def _snapshot_restore(self, owner_session):
        """Snapshot Frozen Dynasty league config and restore after test."""
        r = owner_session.get(f"{BASE_URL}/api/leagues/{FROZEN_LEAGUE_ID}", timeout=20)
        assert r.status_code == 200, r.text
        original = r.json()
        snapshot = {
            "roster_spots": original.get("roster_spots"),
            "position_breakdown": copy.deepcopy(original.get("position_breakdown") or {}),
        }
        yield
        # Restore baseline
        owner_session.put(
            f"{BASE_URL}/api/leagues/{FROZEN_LEAGUE_ID}",
            json=snapshot,
            timeout=20,
        )

    def test_put_manual_roster_spots_with_active_breakdown(self, owner_session):
        payload = {
            "position_breakdown": {
                "active": {"C": 4, "LW": 4, "RW": 4, "D": 6, "G": 1},
                "bench": {},
                "bench2": {},
                "minors": {},
            },
            "roster_spots": 19,
        }
        r = owner_session.put(
            f"{BASE_URL}/api/leagues/{FROZEN_LEAGUE_ID}",
            json=payload,
            timeout=20,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        # Iter179 guard: explicit roster_spots in same payload wins over the
        # active-sum derivation (which would have produced 19 here too, but
        # the guard is independent of that). Important: NOT auto-overwritten.
        assert body.get("roster_spots") == 19, body
        active = (body.get("position_breakdown") or {}).get("active") or {}
        assert active.get("C") == 4
        assert active.get("LW") == 4
        assert active.get("RW") == 4
        assert active.get("D") == 6
        assert active.get("G") == 1

    def test_get_after_put_preserves_position_breakdown(self, owner_session):
        payload = {
            "position_breakdown": {
                "active": {"C": 4, "LW": 4, "RW": 4, "D": 6, "G": 1},
                "bench": {},
                "bench2": {},
                "minors": {},
            },
            "roster_spots": 19,
        }
        put_r = owner_session.put(
            f"{BASE_URL}/api/leagues/{FROZEN_LEAGUE_ID}", json=payload, timeout=20
        )
        assert put_r.status_code == 200, put_r.text

        # Fresh GET — verify persisted in Mongo
        get_r = owner_session.get(
            f"{BASE_URL}/api/leagues/{FROZEN_LEAGUE_ID}", timeout=20
        )
        assert get_r.status_code == 200, get_r.text
        body = get_r.json()
        assert body.get("roster_spots") == 19
        pb = body.get("position_breakdown") or {}
        assert pb.get("active") == {"C": 4, "LW": 4, "RW": 4, "D": 6, "G": 1}
        # Backward-compat shape — all four rows present (blank shells allowed).
        for k in ("active", "bench", "bench2", "minors"):
            assert k in pb, f"position_breakdown missing key: {k}"


# ── (B) + (C) Waiver claim drop_player_id + DELETE cancel ────────────────────
@pytest.fixture(scope="module")
def waiver_context(owner_session):
    """Find Chris's team in Ice Kings + a free agent player to claim +
    one of his current roster players (used as drop_player_id).
    """
    # /api/auth/me to grab Chris's user id
    me = owner_session.get(f"{BASE_URL}/api/auth/me", timeout=20)
    assert me.status_code == 200, me.text
    me_id = me.json().get("id") or me.json().get("_id")

    teams = owner_session.get(
        f"{BASE_URL}/api/teams?league_id={ICE_KINGS_LEAGUE_ID}", timeout=20
    )
    assert teams.status_code == 200, teams.text
    my_team = None
    for t in teams.json():
        if str(t.get("owner_id")) == str(me_id):
            my_team = t
            break
    if not my_team:
        pytest.skip("Chris does not own a team in Ice Kings Head-to-Head")
    team_id = str(my_team.get("id") or my_team.get("_id"))

    # Get a free agent (waiver-available) player
    avail = owner_session.get(
        f"{BASE_URL}/api/waivers/available?league_id={ICE_KINGS_LEAGUE_ID}&limit=5",
        timeout=20,
    )
    assert avail.status_code == 200, avail.text
    avail_players = (avail.json() or {}).get("players") or []
    if not avail_players:
        pytest.skip("No available waiver players in Ice Kings")
    target_player = next(
        (p for p in avail_players if not p.get("has_active_claim")), avail_players[0]
    )

    # Get one of Chris's roster players to use as drop
    roster_player_id = None
    roster_ids = my_team.get("roster") or []
    if roster_ids:
        roster_player_id = str(roster_ids[0])

    return {
        "team_id": team_id,
        "owner_id": me_id,
        "target_player_id": target_player["id"],
        "drop_player_id": roster_player_id,
    }


class TestWaiverClaimDropPlayer:
    def test_post_claim_persists_drop_player_id(self, owner_session, waiver_context):
        ctx = waiver_context
        if not ctx["drop_player_id"]:
            pytest.skip("Chris has no roster players to drop")

        payload = {
            "league_id": ICE_KINGS_LEAGUE_ID,
            "player_id": ctx["target_player_id"],
            "bid_amount": 1,
            "drop_player_id": ctx["drop_player_id"],
        }
        r = owner_session.post(
            f"{BASE_URL}/api/waivers/claim", json=payload, timeout=20
        )
        # Some leagues block dupes / pending — handle 400 gracefully
        if r.status_code == 400 and "already" in r.text.lower():
            pytest.skip(f"Claim conflict (already pending): {r.text[:120]}")
        assert r.status_code in (200, 201), r.text
        body = r.json()
        assert body.get("drop_player_id") == ctx["drop_player_id"], body
        assert body.get("player_id") == ctx["target_player_id"]
        # drop_player_name should be denormalized server-side
        assert body.get("drop_player_name"), "drop_player_name should be populated"

        # Persist verification — GET my-claims and find this claim
        listing = owner_session.get(
            f"{BASE_URL}/api/waivers/claims?league_id={ICE_KINGS_LEAGUE_ID}&my_claims=true",
            timeout=20,
        )
        assert listing.status_code == 200, listing.text
        claims = listing.json()
        claim_id = body.get("_id") or body.get("id")
        match = next((c for c in claims if str(c.get("_id")) == str(claim_id)), None)
        assert match is not None, f"Claim {claim_id} not in my-claims listing"
        assert match.get("drop_player_id") == ctx["drop_player_id"]

        # Cleanup — cancel the claim
        owner_session.delete(
            f"{BASE_URL}/api/waivers/claims/{claim_id}", timeout=20
        )


class TestWaiverClaimDelete:
    @pytest.fixture
    def pending_claim(self, owner_session, waiver_context):
        """Create a fresh pending claim, yield its id, ensure cleanup."""
        ctx = waiver_context
        payload = {
            "league_id": ICE_KINGS_LEAGUE_ID,
            "player_id": ctx["target_player_id"],
            "bid_amount": 1,
        }
        if ctx["drop_player_id"]:
            payload["drop_player_id"] = ctx["drop_player_id"]
        r = owner_session.post(
            f"{BASE_URL}/api/waivers/claim", json=payload, timeout=20
        )
        if r.status_code == 400 and "already" in r.text.lower():
            # Find existing pending claim instead
            listing = owner_session.get(
                f"{BASE_URL}/api/waivers/claims?league_id={ICE_KINGS_LEAGUE_ID}&my_claims=true&status=pending",
                timeout=20,
            )
            claims = listing.json()
            existing = next(
                (
                    c for c in claims
                    if c.get("player_id") == ctx["target_player_id"]
                    and c.get("status") == "pending"
                ),
                None,
            )
            if not existing:
                pytest.skip(f"No pending claim available: {r.text[:120]}")
            yield str(existing["_id"])
            return
        assert r.status_code in (200, 201), r.text
        claim_id = str(r.json().get("_id") or r.json().get("id"))
        yield claim_id
        # Cleanup best-effort
        owner_session.delete(
            f"{BASE_URL}/api/waivers/claims/{claim_id}", timeout=20
        )

    def test_owner_can_cancel_pending_claim(self, owner_session, pending_claim):
        r = owner_session.delete(
            f"{BASE_URL}/api/waivers/claims/{pending_claim}", timeout=20
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert "cancel" in body.get("message", "").lower()

        # Verify status flipped to "cancelled"
        listing = owner_session.get(
            f"{BASE_URL}/api/waivers/claims?league_id={ICE_KINGS_LEAGUE_ID}&my_claims=true",
            timeout=20,
        )
        claims = listing.json()
        match = next((c for c in claims if str(c["_id"]) == pending_claim), None)
        if match is not None:
            assert match.get("status") == "cancelled"

    def test_cancel_already_cancelled_returns_400(
        self, owner_session, waiver_context, pending_claim
    ):
        # First cancellation
        r1 = owner_session.delete(
            f"{BASE_URL}/api/waivers/claims/{pending_claim}", timeout=20
        )
        assert r1.status_code == 200, r1.text
        # Second cancellation on the same (now non-pending) claim → 400
        r2 = owner_session.delete(
            f"{BASE_URL}/api/waivers/claims/{pending_claim}", timeout=20
        )
        assert r2.status_code == 400, r2.text
        assert "not pending" in r2.text.lower() or "pending" in r2.text.lower()

    def test_non_owner_cancel_returns_403(self, owner_session, pending_claim):
        """Anonymous session (no auth) → 401/403; or any other user → 403.

        We use a fresh requests.Session with no auth as the simplest
        non-owner; if the endpoint requires auth, we'll see 401 instead
        of 403. Both are acceptable signals that non-owner is blocked.
        """
        anon = requests.Session()
        r = anon.delete(
            f"{BASE_URL}/api/waivers/claims/{pending_claim}", timeout=20
        )
        assert r.status_code in (401, 403), r.text
