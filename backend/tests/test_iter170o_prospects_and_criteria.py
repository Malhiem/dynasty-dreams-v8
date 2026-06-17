"""Iter 170o — Real prospect pool + criteria-aware filtering + dynamic
page subheader.

  (1) Seed script `iter170o_seed_prospects.py` upserts 30 real 2026
      NHL Draft-eligible prospects (Misa, McKenna, Hagens, Martone, …)
      into the `players` collection with `player_type: "prospect"` +
      synthetic negative `nhl_id` (so they coexist with NHL skaters
      that share the same name without violating the unique index).
  (2) `get_draft_eligible_players` and `auto_pick_for_on_clock_team`
      now respect `draft.player_criteria`:
        • "entry" → `player_type === "prospect"` only
        • "open" / anything else → all non-prospects (NHL players)
  (3) Draft Room subheader now mirrors `currentDraft.player_criteria`
      and the Draft Criteria info card prefers the backend value over
      the local default.
"""
from pathlib import Path

DRAFTS_ROUTE = Path("/app/backend/routes/drafts.py")
SEED_SCRIPT = Path("/app/backend/scripts/iter170o_seed_prospects.py")
DRAFT_ROOM = Path("/app/frontend/src/lovable/pages/DraftRoom.tsx")


def test_seed_script_stamps_prospect_type_and_safe_nhl_id():
    src = SEED_SCRIPT.read_text()
    # Player_type flag + amateur status so existing dashboards can
    # opt-in to render them.
    assert '"player_type": "prospect"' in src
    assert '"player_status": "amateur"' in src
    # Disambiguate name to avoid unique-index collisions on existing
    # NHL players sharing the same name (Hagens, Ryabkin).
    assert 'prospect_name = f"{name} (Prospect)"' in src
    # Synthetic negative nhl_id sidesteps the nhl_id unique-null
    # collision that bit us on the first run.
    assert '"nhl_id": -(1_000_000 + i)' in src
    # Upsert keyed by name+player_type so re-runs are idempotent.
    assert 'upsert=True' in src


def test_eligible_players_filters_by_criteria():
    src = DRAFTS_ROUTE.read_text()
    block = src.split("async def get_draft_eligible_players")[1].split("# ─── Iter 170g — Auto-init")[0]
    assert 'criteria = (draft.get("player_criteria") or "open").lower()' in block
    assert 'if criteria == "entry":' in block
    assert 'query["player_type"] = "prospect"' in block
    # Open drafts must EXCLUDE the prospect pool so NHL players surface
    # without being polluted by prospect rows.
    assert 'query["player_type"] = {"$ne": "prospect"}' in block


def test_auto_pick_respects_criteria_filter():
    src = DRAFTS_ROUTE.read_text()
    block = src.split("async def auto_pick_for_on_clock_team")[1].split("# ─── Iter 170j — Draft Queue")[0]
    # Same prospect / non-prospect branching when falling back to top
    # eligible.
    assert '"player_type": "prospect"' in block
    assert '"player_type": {"$ne": "prospect"}' in block


def test_draftroom_subheader_mirrors_backend_criteria():
    src = DRAFT_ROOM.read_text()
    assert 'data-testid="draft-room-subheader"' in src
    # Dynamic label based on backend value.
    assert 'currentDraft?.player_criteria === "entry"' in src
    assert "2026 NHL Entry Draft — League Rookie Draft" in src
    assert "Open · all eligible NHL players" in src


def test_draft_criteria_info_uses_backend_value():
    src = DRAFT_ROOM.read_text()
    # The header `Draft Criteria:` label + info card pull from the
    # backend criteria first, falling back to the local selector.
    assert "const effectiveCriteria = currentDraft?.player_criteria || selectedCriteria" in src
