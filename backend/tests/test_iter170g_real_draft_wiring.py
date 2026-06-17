"""Iter 170g — Wire Simulate Pick → real backend draft endpoint.

Backend changes covered:
  (1) `_derive_team_abbr` + `_abbrs_with_dedup` helpers — align with the
      frontend's `logo_abbr` derivation (honour `logo_abbr_override`,
      hyphen-aware initials, dedup collisions like CC → CC, CC2).
  (2) `create_draft` uses the new helpers.
  (3) `make_draft_pick` pushes the drafted player onto the on-clock
      team's `roster` (idempotent via `$addToSet`).
  (4) Eligible-players response carries a best-effort `headshot` URL.
  (5) New `POST /drafts/auto-init/{league_id}` endpoint — fetches or
      creates a draft for the league (commissioner-only).
"""
from pathlib import Path

DRAFTS_ROUTE = Path("/app/backend/routes/drafts.py")
DRAFT_ROOM = Path("/app/frontend/src/lovable/pages/DraftRoom.tsx")


def _src() -> str:
    return DRAFTS_ROUTE.read_text()


def test_team_abbr_helpers_present():
    src = _src()
    assert "def _derive_team_abbr(team: dict) -> str:" in src
    assert "def _abbrs_with_dedup(teams: list[dict])" in src
    # Honours override first, then hyphen-split initials.
    assert "logo_abbr_override" in src
    assert 'name.replace("-", " ").split()' in src
    # Dedup logic appends a suffix on collision.
    assert 'f"{base}{count + 1}"' in src


def test_create_draft_uses_new_helpers():
    src = _src()
    # create_draft body uses _abbrs_with_dedup, no longer name[:4].upper().
    block = src.split("async def create_draft(input: CreateDraftRequest, request: Request):")[1].split("async def get_drafts")[0]
    assert "_abbrs_with_dedup(teams)" in block
    assert "t[\"name\"][:4].upper()" not in block


def test_make_draft_pick_pushes_to_roster():
    src = _src()
    block = src.split("async def make_draft_pick(draft_id: str")[1].split("async def pause_draft")[0]
    # Pushes the picked player id onto the on-clock team's roster.
    assert '"$addToSet": {"roster": str(player["_id"])}' in block
    # Uses the on-clock team_id resolved via team_map (not the user's
    # team_id — important for commissioner picking for other teams).
    assert "on_clock_team_id" in block
    # Pick doc carries the team_id + richer player object (headshot, stats).
    assert '"team_id": on_clock_team_id' in block
    assert '"headshot"' in block


def test_eligible_players_returns_headshot_url():
    src = _src()
    block = src.split("async def get_draft_eligible_players")[1].split("async def auto_init_draft")[0]
    # NHL CDN URL pattern when nhl_id is set; None otherwise.
    assert 'assets.nhle.com/mugs/nhl' in block
    assert '"headshot": headshot' in block


def test_auto_init_endpoint_present_and_commissioner_only():
    src = _src()
    assert '@router.post("/drafts/auto-init/{league_id}")' in src
    block = src.split("async def auto_init_draft(league_id: str, request: Request):")[1].split("async def start_draft")[0]
    # Commissioner / co-commissioner check
    assert 'is_comm = league["commissioner_id"] == user["_id"]' in block
    assert 'co_commissioners' in block
    # Idempotency — return existing draft when present.
    assert '"draft": existing, "created": False' in block
    # New-draft creation uses the dedup helper for team_abbrs.
    assert "_abbrs_with_dedup(teams)" in block


# ─── Frontend wiring (DraftRoom.tsx) ──────────────────────────────────


def test_draftroom_auto_init_on_mount():
    src = DRAFT_ROOM.read_text()
    # Calls /drafts/auto-init/{league_id} when league context is available.
    assert "/drafts/auto-init/${activeLeagueCtx.id}" in src
    # Saves the draft into currentDraft state.
    assert "const [currentDraft, setCurrentDraft] = useState<any>(null);" in src
    # Hydrates picks + currentPick from the backend draft on mount.
    assert "setPicks(d.picks.map((p: any) => ({" in src


def test_draftroom_posts_pick_to_backend_when_active():
    src = DRAFT_ROOM.read_text()
    # The unified draft handler short-circuits to a real POST when the
    # draft is active and the player id is a real Mongo ObjectId.
    assert "api.post(`/drafts/${currentDraft._id}/pick`, { player_id: nextPlayer.id })" in src
    # Refetches the canonical state after a successful pick.
    assert "api.get(`/drafts/${currentDraft._id}`)" in src


def test_draftroom_start_buttons_wire_to_backend():
    src = DRAFT_ROOM.read_text()
    # Both Start (Early) and Start (With Timer) POST to /drafts/{id}/start
    # when a backend draft exists.
    assert "/drafts/${currentDraft._id}/start?early_start=true" in src
    assert "/drafts/${currentDraft._id}/start?early_start=false" in src


def test_draftroom_fetches_real_eligible_players():
    src = DRAFT_ROOM.read_text()
    assert "/drafts/${currentDraft._id}/eligible-players?limit=100" in src
    # Maps headshot → headshot_url for the SelectedPlayerCard.
    assert "headshot_url: p.headshot" in src
