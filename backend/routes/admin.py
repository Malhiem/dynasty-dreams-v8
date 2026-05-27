"""Site-admin endpoints — extracted from server.py (iter 115).

Endpoint:
    POST /api/admin/snapshot-ownership — site-admin trigger to capture an
    ownership snapshot RIGHT NOW (instead of waiting for the 24h tick).
"""
from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException, Request


router = APIRouter()
_deps: dict = {}


def setup(deps: dict) -> None:
    _deps.update(deps)


def _db(): return _deps["db"]
async def _get_user(request): return await _deps["get_current_user"](request)


@router.post("/admin/snapshot-ownership")
async def admin_snapshot_ownership(request: Request):
    """Site-admin trigger to capture an ownership snapshot RIGHT NOW.

    Useful when site operators want the % Change column to populate before
    the natural 24h tick fires. Auth: only the user with email ==
    ADMIN_EMAIL can call this.
    """
    user = await _get_user(request)
    admin_email = os.environ.get("ADMIN_EMAIL", "admin@dynastydreams.com")
    if user.get("email") != admin_email:
        raise HTTPException(status_code=403, detail="Site admin only")
    from ownership_snapshot_worker import snapshot_once
    return await snapshot_once(_db())
