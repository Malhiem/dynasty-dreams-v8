"""Refresh-token revocation with subsecond issue-time precision."""
from datetime import datetime, timezone
from math import isfinite


def predates_password_change(issued_at, changed_at):
    if not changed_at:
        return False
    # Legacy tokens without a usable issue time cannot establish freshness.
    if isinstance(issued_at, bool) or not isinstance(issued_at, (int, float)) or not isfinite(issued_at):
        return True
    try:
        if isinstance(changed_at, str):
            changed_at = datetime.fromisoformat(changed_at)
        if changed_at.tzinfo is None:
            changed_at = changed_at.replace(tzinfo=timezone.utc)
        return issued_at < changed_at.timestamp()
    except (TypeError, ValueError, AttributeError, OverflowError):
        return True
