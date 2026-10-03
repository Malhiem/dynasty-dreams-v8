"""Iter 232h — Security audit fixes (SEC-001 / SEC-002 / SEC-003).

Read-only security audit (iter 232g `security_audit_agent`) surfaced
three defects; this iteration lands the fixes and the guard tests
that lock them down. The tests are static-source assertions so they
run in <1s and don't need a live DB / SW / browser.

SEC-001 [HIGH] Cross-league chat read + message-injection
  Any authenticated user could enumerate any league's channels + read
  history + post spoofed messages that fan-out notifications to every
  member. Root cause: `_get_user` was called but never followed by a
  league-membership check on non-DM channels.

  Fix: added `_is_league_member()` + `_require_league_member()` +
  `_require_channel_access()` helpers in `routes/chat.py`. Every
  channel/message endpoint (list_channels, list_messages,
  post_message, mark_channel_read, set_mute) now enforces membership.

SEC-002 [MEDIUM] League member email disclosure
  `/chat/league/{id}/members` returned owner emails via a fallback
  branch AND had no membership check. Fix: gated to league members
  and removed the email fallback (falls back to a stable "Owner"
  placeholder instead).

SEC-003 [MEDIUM] Service worker cached per-user data across sessions
  `/api/users/me/*` was in `SWR_PATTERNS`, so on a shared browser
  user A's Week-At-a-Glance could be served to user B on their next
  login before the SWR revalidation kicked in. Fix: `/api/users/me`
  moved to `NEVER_CACHE`, `/api/chat/` also excluded (per-user gated),
  and the client's `logout()` now posts `{type: 'PURGE_API_CACHE'}`
  to the SW so the cache is emptied at the exact moment the session
  ends.
"""
from pathlib import Path


CHAT = Path("/app/backend/routes/chat.py")
SW = Path("/app/frontend/public/service-worker.js")
AUTH_CTX = Path("/app/frontend/src/contexts/AuthContext.js")


# ─── SEC-001 ────────────────────────────────────────────────────────


def test_membership_helper_exists_and_covers_all_membership_paths():
    src = CHAT.read_text()
    assert "async def _is_league_member(" in src
    assert "async def _require_league_member(" in src
    assert "async def _require_channel_access(" in src
    # Three paths counted as members: team owner, team co-owner,
    # (co-)commissioner. Each pattern must appear in the source.
    assert '"owner_id": user_id' in src
    assert '"co_owner_ids": user_id' in src
    assert 'league.get("commissioner_id") == user_id' in src
    assert '"co_commissioners"' in src


def test_list_channels_now_gates_membership():
    src = CHAT.read_text()
    # The endpoint must call _require_league_member BEFORE any
    # data-returning work (the previous version leaked channel ids
    # to any authenticated user).
    idx_endpoint = src.find('@router.get("/chat/channels")')
    idx_next_endpoint = src.find('@router.post("/chat/channels")')
    assert idx_endpoint >= 0 and idx_next_endpoint > idx_endpoint
    block = src[idx_endpoint:idx_next_endpoint]
    assert "_require_league_member(db, league_id, user[" in block


def test_list_and_post_messages_gate_channel_access():
    src = CHAT.read_text()
    # list_messages
    idx = src.find('@router.get("/chat/channels/{channel_id}/messages")')
    assert idx >= 0
    block = src[idx: idx + 900]
    assert "_require_channel_access(db, chan, user[" in block
    # post_message
    idx = src.find('@router.post("/chat/channels/{channel_id}/messages")')
    assert idx >= 0
    block = src[idx: idx + 900]
    assert "_require_channel_access(db, chan, user[" in block


def test_mark_read_and_mute_gate_channel_access():
    src = CHAT.read_text()
    idx = src.find('@router.post("/chat/channels/{channel_id}/mark-read")')
    assert idx >= 0
    assert "_require_channel_access" in src[idx: idx + 700]
    idx = src.find('@router.post("/chat/channels/{channel_id}/mute")')
    assert idx >= 0
    assert "_require_channel_access" in src[idx: idx + 700]


# ─── SEC-002 ────────────────────────────────────────────────────────


def test_league_members_endpoint_gated_and_email_removed():
    src = CHAT.read_text()
    idx = src.find('@router.get("/chat/league/{league_id}/members")')
    assert idx >= 0
    # Grab the whole function body.
    block = src[idx: idx + 2000]
    # Membership gate.
    assert "_require_league_member(db, league_id, user[" in block
    # Email fallback removed — projection must NOT ask for email
    # anymore, and there must be no `u.get("email")` inside the block.
    assert 'u.get("email")' not in block
    # The projection includes ONLY `name` now (no `email: 1`).
    assert '{"name": 1}' in block


# ─── SEC-003 ────────────────────────────────────────────────────────


def test_service_worker_removes_me_endpoints_from_swr():
    src = SW.read_text()
    # /users/me/week-at-a-glance must NOT be in the SWR list anymore.
    # (The regex is a byte-equal match so a rename would surface here.)
    assert "/^\\/api\\/users\\/me\\/week-at-a-glance/" not in src


def test_service_worker_never_cache_covers_per_user_and_chat():
    src = SW.read_text()
    # Explicitly never-cache /users/me/* and /chat/*.
    assert "/^\\/api\\/users\\/me(\\/|$|\\?)/" in src
    assert "/^\\/api\\/chat\\//" in src


def test_service_worker_handles_purge_api_cache_message():
    src = SW.read_text()
    # New message handler receives PURGE_API_CACHE from the client.
    assert 'data.type === "PURGE_API_CACHE"' in src
    # Purge deletes the API cache (not the shell — that's per-build).
    assert "caches.delete(API_CACHE)" in src
    # Still preserves the SKIP_WAITING handshake.
    assert 'data.type === "SKIP_WAITING"' in src


def test_logout_sends_purge_message_to_service_worker():
    src = AUTH_CTX.read_text()
    # Fires the purge on logout so a shared-device next-user
    # doesn't see the outgoing user's cached data.
    assert "postMessage({ type: 'PURGE_API_CACHE' })" in src
    # Message is gated behind an SW registration check so browsers
    # without a live SW don't throw.
    assert "navigator?.serviceWorker?.controller" in src
