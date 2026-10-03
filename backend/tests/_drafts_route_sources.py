"""Shared helper for backend tests that grep `routes/drafts.py` source.

When iter 170 tests originally landed, every draft-related route + helper
lived in `routes/drafts.py`. Across iter 231* refactors the file was
decomposed:

  • iter 231   → `routes/draft_config.py` (keeper/expansion config)
  • iter 231c  → `routes/draft_inspection.py` (read-only endpoints)
  • iter 231k  → `routes/draft_queue.py` + `routes/draft_auction.py`
  • iter 231l  → `routes/draft_picks.py` (defer endpoints)
  • iter 231m  → `routes/draft_pick_actions.py` (make-pick / undo / swap / pause / seed-picks)
  • iter 231n  → `routes/draft_helpers.py` (perform_one_auto_pick + seed helpers)

The iter 170* tests do source-text grep assertions — to keep their
functional intent valid, treat the "drafts route source" as the
concatenation of every file that contributes to the runtime draft
behaviour.
"""
from pathlib import Path

BACKEND_ROUTES = Path("/app/backend/routes")

# Order matters for `.split(...)` based assertions: we want the canonical
# `drafts.py` content first so existing split markers stay valid; the
# extracted modules are appended after so their endpoints / helpers still
# resolve.
_DRAFTS_FAMILY_FILES = [
    "drafts.py",
    "draft_pick_actions.py",
    "draft_helpers.py",
    "draft_picks.py",
    "draft_queue.py",
    "draft_auction.py",
    "draft_inspection.py",
    "draft_config.py",
    "draft_lifecycle.py",
    "draft_admin.py",
    "draft_order.py",
    "draft_chat_config.py",
]


def read_drafts_family() -> str:
    parts: list[str] = []
    for name in _DRAFTS_FAMILY_FILES:
        p = BACKEND_ROUTES / name
        if p.exists() and p.is_file():
            parts.append(p.read_text())
    return "\n".join(parts)


class DraftsRouteFamilyShim:
    """Drop-in replacement for `Path("/app/backend/routes/drafts.py")` —
    exposes `.read_text()` and `.exists()` so legacy tests don't need to
    change their grep / split assertions."""

    def read_text(self) -> str:
        return read_drafts_family()

    def exists(self) -> bool:
        return True
