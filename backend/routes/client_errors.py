"""Iter 231aq — Client error sink.

Receives stack traces from the React `<GlobalErrorBoundary>` (and from
the global `window.onerror` / `unhandledrejection` listeners it
installs). Goals:

  • Persist every uncaught client-side error in `client_errors` so we
    learn about crashes before users tell us.
  • Stay cheap on the wire — POST is single-shot with a small JSON
    body; the route caps payloads at 64 KB to defeat noisy stacks.
  • Auth is *optional*: errors can fire on the public landing page
    before login, so we never reject anonymous reports. When a user
    is signed in we record their id for triage.
  • Expose `GET /api/client-errors` for platform admins (Emergent
    operators) to triage; gated behind `is_admin` on `users`.
"""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter()
_deps: dict = {}


def setup(deps: dict) -> None:
    _deps.update(deps)


_MAX_FIELD = 8_000  # Each free-text field truncated independently.
_MAX_PAYLOAD = 64_000  # Hard cap on serialised body.


class ClientErrorIn(BaseModel):
    """The shape the boundary POSTs. All fields optional — even a
    completely empty body is accepted so a crashing component never
    blocks the report path with a validation error."""

    message: Optional[str] = Field(default=None, description="Error.message")
    stack: Optional[str] = Field(default=None, description="Error.stack")
    component_stack: Optional[str] = Field(default=None, description="React componentStack")
    url: Optional[str] = Field(default=None, description="window.location.href")
    user_agent: Optional[str] = Field(default=None, description="navigator.userAgent")
    app_version: Optional[str] = Field(default=None, description="REACT_APP build sha or 'dev'")
    breadcrumbs: Optional[list] = Field(default=None, description="Recent user actions")


def _truncate(s: Optional[str], limit: int = _MAX_FIELD) -> Optional[str]:
    if not s:
        return s
    if len(s) <= limit:
        return s
    return s[: limit - 16] + "…[truncated]"


@router.post("/client-errors")
async def report_client_error(payload: ClientErrorIn, request: Request):
    """Record an uncaught client-side error. Always returns 200 so a
    badly-behaved client doesn't loop on retries."""
    db = _deps["db"]

    # Best-effort auth: we accept anonymous reports but stamp the user
    # id when available. `get_current_user` raises on no-cookie — we
    # swallow that and continue.
    user_id: Optional[str] = None
    user_email: Optional[str] = None
    try:
        get_user = _deps.get("get_current_user")
        if get_user:
            u = await get_user(request)
            if u:
                user_id = str(u.get("_id") or u.get("id") or "") or None
                user_email = u.get("email")
    except Exception:
        pass

    doc = {
        "message": _truncate(payload.message),
        "stack": _truncate(payload.stack, _MAX_FIELD * 2),  # stacks tend to be longer
        "component_stack": _truncate(payload.component_stack),
        "url": _truncate(payload.url, 512),
        "user_agent": _truncate(payload.user_agent, 512),
        "app_version": _truncate(payload.app_version, 64),
        "breadcrumbs": (payload.breadcrumbs or [])[:25],
        "user_id": user_id,
        "user_email": user_email,
        "ip": request.client.host if request.client else None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    # Hard-cap the serialised body so an exotic crash with a 5 MB stack
    # can't fill Mongo. We've already truncated each field; this is the
    # belt-and-braces guard.
    import json
    try:
        size = len(json.dumps(doc, default=str))
    except Exception:
        size = 0
    if size > _MAX_PAYLOAD:
        doc["stack"] = (doc.get("stack") or "")[:_MAX_FIELD] + "…[oversized]"
        doc["component_stack"] = (doc.get("component_stack") or "")[:1_000]

    try:
        res = await db.client_errors.insert_one(doc)
        return {"ok": True, "id": str(res.inserted_id)}
    except Exception as e:
        # Never raise — the client is already crashing.
        return {"ok": False, "error": str(e)[:200]}


@router.get("/client-errors")
async def list_client_errors(request: Request, limit: int = 50, skip: int = 0):
    """Admin-only paginated list, newest first. Platform admins only —
    a regular league commissioner has no business poking at other
    leagues' stack traces. The gate mirrors `db_hygiene._is_platform_admin`:
    `user.role == "admin"` OR the `ADMIN_EMAIL` env override."""
    import os as _os
    db = _deps["db"]
    get_user = _deps.get("get_current_user")
    if not get_user:
        raise HTTPException(status_code=503, detail="auth not wired")
    user = await get_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="login required")
    is_admin = (
        user.get("role") == "admin"
        or user.get("is_admin") is True
        or user.get("email") == _os.environ.get("ADMIN_EMAIL", "admin@dynastydreams.com")
    )
    if not is_admin:
        raise HTTPException(status_code=403, detail="platform-admin required")

    limit = max(1, min(int(limit or 50), 200))
    skip = max(0, int(skip or 0))

    cursor = (
        db.client_errors.find({})
        .sort("created_at", -1)
        .skip(skip)
        .limit(limit)
    )
    rows = await cursor.to_list(limit)
    for r in rows:
        r["_id"] = str(r["_id"])
    total = await db.client_errors.count_documents({})
    return {"total": total, "limit": limit, "skip": skip, "errors": rows}
