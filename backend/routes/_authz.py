"""Iter 231ad — Shared league-admin authorization helper.

Consolidates the `commissioner OR co_commissioners OR role==admin`
check that 6+ draft endpoints duplicate. Before this iter, the check
lived inline in `draft_pick_actions.py` (5 endpoints), `draft_admin.py`
(restart_draft), and was about to spread to `team_invites.py` (admin-
managed-team toggle). One helper → one source of truth.

Usage:
    from routes._authz import is_league_admin

    if not is_league_admin(user, league):
        raise HTTPException(403, "Commissioner / co-commissioner / admin only")

Both `user["_id"]` and `league["commissioner_id"]` are expected to be
strings (the canonical ObjectId-string form used across this codebase).
`co_commissioners` is a list of strings; `role` is the user-level
role tag (`"admin"` for platform admins).
"""
from __future__ import annotations

from typing import Optional


def is_league_admin(user: Optional[dict], league: Optional[dict]) -> bool:
    """Return True if `user` may take commissioner-level actions on `league`.

    Truthy when ANY of:
      • `user._id == league.commissioner_id` (primary commissioner)
      • `user._id` in `league.co_commissioners` (co-commissioners)
      • `user.role == "admin"` (platform-tier admin — can act on any league)

    Falsy when either argument is None/missing (defensive — callers should
    have already verified the user is authenticated and the league exists).
    """
    if not user or not league:
        return False
    if league.get("commissioner_id") == user.get("_id"):
        return True
    if user.get("_id") in (league.get("co_commissioners") or []):
        return True
    if user.get("role") == "admin":
        return True
    return False
