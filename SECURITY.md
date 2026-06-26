# Dynasty Dreams — Security Threat Model & Conventions

> **Audience**: backend + frontend contributors. Read this before adding any
> new HTTP endpoint, Socket.IO room, or admin action. Last updated
> Iter 230L–230m (post-audit hardening).

This document is the source of truth for the conventions enforced by the
February 2026 security audit. Every finding had a remediation pattern,
and those patterns are listed here as one-liners you can copy into new
code. If your endpoint or surface area can't be described by one of the
patterns below, it probably needs a security review.

---

## 1. Threat Model

We protect against three primary classes of attacker:

| # | Class                            | Example                                                                      |
| - | -------------------------------- | ---------------------------------------------------------------------------- |
| 1 | **Unauthenticated internet**     | Anonymous client hitting the public preview URL.                             |
| 2 | **Authenticated league outsider**| A logged-in user trying to read another league's data they don't belong to. |
| 3 | **Adjacent league member**       | A league mate trying to mutate someone else's team / proposed trade.         |

The three OWASP categories that map to those attackers — and that this
repo has had real findings against — are:

* **BOLA / IDOR (Broken Object-Level Authorization)** — the resource-id
  in the URL is trusted without checking the caller owns it.
  *(Cause of audit findings SEC-001 & SEC-002.)*
* **A01:2025 Broken Access Control** — admin / commissioner / read-only
  impersonation gates not enforced uniformly.
  *(Cause of P3 hardening: impersonation read-only.)*
* **A07:2025 Identification & Authentication Failures** —
  enumeration, missing rate limits, refresh tokens outliving a reset.
  *(Cause of P3 hardening: register enumeration, forgot-password
  throttle, refresh-token revocation.)*

---

## 2. The Seven-Endpoint Auth Pattern

Every `GET /resource/{id}` endpoint that returns league-scoped data
MUST follow this pattern, in this exact order:

```python
@router.get("/resource/{resource_id}")
async def get_resource(resource_id: str, request: Request):
    # ── 1. Auth FIRST, before any DB lookup ─────────────────────────
    # This is critical — without it, attackers can probe id-existence
    # via the 404-vs-401 timing difference even though the data is
    # nominally gated. SEC-002 specifically called this out.
    await _require_user(request)

    # ── 2. Then load the resource ───────────────────────────────────
    resource = await db.collection.find_one({"_id": _safe_object_id(resource_id, "resource_id")})
    if not resource:
        raise HTTPException(status_code=404, detail="Resource not found")

    # ── 3. Then enforce league membership ───────────────────────────
    await _require_league_member(request, str(resource.get("league_id") or ""))

    return resource_to_response(resource)
```

The helpers (`_require_user`, `_require_league_member`,
`_require_league_member_for_team`) live next to the routes that use them
(`routes/teams.py`, `routes/roster.py`). Membership semantics:

* Platform admin (`roles: ["admin"]`) — always passes.
* League commissioner / league admin / league owner — passes.
* Team owner or co-owner inside the league — passes.
* Anyone else — `403 Not a member of this league`.

### Why "auth first, then lookup"

If you reverse the order (lookup → existence check → auth check) an
attacker gets `404` for "doesn't exist" and `401` for "exists but not
auth'd". That's enough to enumerate every team-id in the system.
The whole point of P1+P2 was to close that channel.

### Endpoints currently following this pattern

* `GET /api/teams` *(any auth'd user; per-league check when scoped)*
* `GET /api/teams/{id}`
* `GET /api/teams/{id}/dead-cap-schedule`
* `GET /api/teams/{id}/depth-projections`
* `GET /api/teams/{id}/depth-lineup`
* `GET /api/teams/{id}/roster-truncated`
* `GET /api/roster/{team_id}`
* `GET /api/roster/{team_id}/detail`

---

## 3. Socket.IO Room Allowlist

Real-time eavesdropping is the second-easiest cross-user leak in any
multi-tenant app. Ours has two invariants:

### Connect handshake
Every Socket.IO connection MUST present a valid JWT. The order checked
is:

1. `auth: { token: "<jwt>" }` from `io(url, { auth })` (preferred).
2. `Authorization: Bearer <jwt>` header.
3. `access_token=<jwt>` cookie (web browsers — httpOnly cookies still
   flow on same-origin handshake).

If none of those decode to a valid `access` or `impersonation` token,
the server raises `socketio.exceptions.ConnectionRefusedError("authentication required")`.

### Join-room authorization
Once connected, `join_room` calls go through `_user_can_join_room(user_id, room_id)`
which enforces an **allowlist** (deny by default — adding a new room
namespace requires touching this function):

| Room prefix       | Who may join                                                                              |
| ----------------- | ----------------------------------------------------------------------------------------- |
| `user_{X}`        | Only the user whose authenticated id matches X.                                           |
| `league_{X}`      | Team owner / co-owner / league commissioner / league `admin_ids` / platform admin.        |
| `draft_{X}`       | Same membership rule, but evaluated against the draft's parent `league_id`.               |
| *(anything else)* | **DENIED**. Don't add a new namespace without extending the allowlist + this table.       |

The client-supplied `user_id` field in `join_room` payloads is
**ignored** — the server uses the verified id stamped on the session
during `connect`. Personal notification rooms always derive from the
authenticated id.

When a join is denied the server emits `room_join_denied` with
`{ room_id, reason: "not_authorized" }` so the client can react instead
of silently failing.

---

## 4. Auth Hardening Conventions

The P3 hardening pass added four invariants:

### 4.1 No register enumeration
`POST /api/auth/register` returns a **single generic** error for any
collision (`"Email or username is already in use"`). The error text
MUST be identical whether the email collides, the username collides, or
both. Test: `tests/test_iter230m_p3_hardening.py::test_p3_register_collision_uses_generic_error`.

### 4.2 Forgot-password throttle
`POST /api/auth/forgot-password` enforces:

* per-email: 1/min, 5/h
* per-IP: 3/min, 10/h

When throttled, the response shape is **identical to the success
branch** — this preserves the non-enumeration invariant (no `429`,
no different message). Every request — even for a non-existent email
— writes a row to `db.password_reset_throttle` so silent-drop timing
doesn't leak existence either.

### 4.3 Password reset revokes refresh tokens
On successful `POST /api/auth/reset-password` the user doc receives
`password_changed_at = now()`. The refresh endpoint compares the
incoming refresh token's `iat` against `password_changed_at`; any
older token returns `401 Session revoked — please sign in again` and
the cookies are cleared. This stops a stolen 7-day refresh token from
outliving a password reset.

### 4.4 Impersonation = read-only
When an admin starts impersonation (`POST /api/auth/impersonate-start`)
the resulting token carries `type=impersonation, mode=read_only`.
`get_current_user` in `server.py` blocks any HTTP method outside
`GET/HEAD/OPTIONS` while that mode is active, returning
`403 Impersonation session is read-only — writes are blocked.` This
guarantee is enforced **globally** — every endpoint that calls
`get_current_user` inherits it automatically; no per-endpoint opt-in
required.

---

## 5. Reporting Issues

Found a new BOLA / IDOR / auth-bypass / room-leak in this codebase?

* If you can confirm exploitability: do **not** open a public PR.
  File an issue tagged `security:p1` with the affected file paths and
  reproduction steps.
* Pure hardening suggestions (rate limits, log redaction, CSP, etc.):
  file as `security:hardening` — those can go through normal review.

---

## 6. Regression Tests

The security invariants are guarded by:

* `backend/tests/test_iter230L_security_fixes.py` — SEC-001 + SEC-002
* `backend/tests/test_iter230m_p3_hardening.py` — P3 hardening pass

Both files are part of the standard pytest suite. **CI must run them
on every PR.** If any test in those files fails, treat it as a release
blocker — the audit findings have regressed.
