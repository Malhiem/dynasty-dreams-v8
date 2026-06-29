"""
Iter 173 — Undrafted "N/A" + Minor-eligible prospect badges.

User asks:
  1. Players not yet drafted by a fantasy team show "N/A" in the team
     column (PlayersPage + PlayerPool).
  2. The expanded player card surfaces the actual league + team they
     play for (NHL · {team} for NHL players, {amateur_league} · {team}
     for prospects).
  3. Prospects that are minor-league-eligible (when the league has
     `minors_enabled: true`) get a sprout-icon badge in the Draft Room
     eligible list, the SelectedPlayerCard, and the PlayerCardModal.
"""
from pathlib import Path

# Iter 231 — drafts.py was decomposed; use the family shim so grep
# assertions still resolve against the relocated eligible-players
# endpoint (now in `routes/draft_inspection.py`) and the auto-init
# flag stamp (now in `routes/draft_lifecycle.py`).
from tests._drafts_route_sources import DraftsRouteFamilyShim

FRONTEND = Path("/app/frontend/src")
PLAYERS_PAGE = FRONTEND / "pages" / "PlayersPage.jsx"
PLAYER_POOL = FRONTEND / "lovable" / "pages" / "PlayerPool.tsx"
PLAYER_CARD = FRONTEND / "lovable" / "components" / "dashboard" / "PlayerCardModal.tsx"
PLAYER_SEARCH = FRONTEND / "lovable" / "pages" / "draftroom" / "PlayerSearchPanel.tsx"
SELECTED_CARD = FRONTEND / "lovable" / "pages" / "draftroom" / "SelectedPlayerCard.tsx"
DRAFT_ROOM = FRONTEND / "lovable" / "pages" / "DraftRoom.tsx"
# Iter 231ak — eligible-players hook was extracted from DraftRoom.tsx.
ELIGIBLE_HOOK = FRONTEND / "hooks" / "use-draft-eligible-players.ts"
DRAFTS_ROUTE = DraftsRouteFamilyShim()


def test_players_page_owned_cell_renders_na_for_undrafted():
    src = PLAYERS_PAGE.read_text()
    # The undrafted branch returns the "N/A" pill with a stable testid.
    assert 'data-testid="players-owned-cell-na"' in src
    assert ">\n        N/A\n      </span>" in src or '"N/A"' in src or ">N/A<" in src
    # "FA" badge is gone from the OwnedCell.
    assert '"text-emerald-400 text-xs font-bold">FA<' not in src


def test_player_pool_fantasy_team_cell_renders_na_for_undrafted():
    src = PLAYER_POOL.read_text()
    assert 'data-testid="player-pool-fantasy-team-na"' in src
    # Confirm the "N/A" string is the new label inside the muted branch.
    assert ">\n                              N/A\n                            </span>" in src


def test_player_card_modal_renders_league_and_team():
    src = PLAYER_CARD.read_text()
    # New affiliation span replaces the bare {player.team} subtitle.
    assert 'data-testid="player-card-affiliation"' in src
    # IIFE pulls league + team from a few common shapes.
    assert 'amateur_league' in src
    assert '`${league} · ${teamName}`' in src
    # Minor-eligible badge wired with its own testid + sprout icon.
    assert 'data-testid="player-card-minor-eligible"' in src
    assert 'Sprout' in src


def test_player_search_panel_renders_minor_eligible_badge():
    src = PLAYER_SEARCH.read_text()
    # Gated on the league flag + prospect status.
    assert "minorsEnabled &&" in src
    assert "player.minor_eligible || player.player_type === \"prospect\"" in src
    assert "draft-room-minor-eligible-" in src
    assert "<Sprout" in src


def test_selected_player_card_renders_minor_eligible_badge():
    src = SELECTED_CARD.read_text()
    assert "minorsEnabled = false" in src
    assert 'data-testid="draft-room-selected-card-minor-eligible"' in src
    # Affiliation row prefers human-readable team_name; falls back to
    # nhlTeam abbr / explicit team field.
    assert "player.team_name" in src
    assert "player.nhlTeam" in src


def test_draft_room_wires_minors_enabled_into_subcomponents():
    src = DRAFT_ROOM.read_text() + "\n" + ELIGIBLE_HOOK.read_text()
    # The hook surface — currentDraft.league_minors_enabled — is forwarded
    # to both presentational children so the badge renders consistently.
    assert "league_minors_enabled" in src
    assert "minorsEnabled={!!(currentDraft as any)?.league_minors_enabled}" in src
    # Iter 231ak — Eligible-players mapper was relocated to the
    # `use-draft-eligible-players` hook and now spreads `player_type`
    # conditionally to skip noisy keys on rows that lack it. The
    # `minor_eligible` boolean is always emitted so the sprout badge
    # gating stays deterministic.
    assert "player_type: p.player_type" in src
    assert "minor_eligible: !!p.minor_eligible" in src


def test_eligible_players_endpoint_exposes_minor_eligible_and_real_league():
    src = DRAFTS_ROUTE.read_text()
    # `minor_eligible` mirrors prospect status; `league` reflects the
    # amateur feeder league for prospects instead of hardcoded "NHL".
    assert '"minor_eligible": is_prospect' in src
    assert '"player_type": player_type' in src
    assert 'league_label = p.get("amateur_league") if is_prospect else "NHL"' in src
    # display_name strips the "(Prospect)" suffix added at seed time.
    assert 'display_name = p.get("display_name") or p["name"]' in src
    # Prospects shouldn't render a broken NHL-headshot URL.
    assert "if p.get(\"nhl_id\") and not is_prospect else None" in src


def test_auto_init_surfaces_league_minors_enabled_flag():
    src = DRAFTS_ROUTE.read_text()
    # Both branches (created + existing) must surface the flag so the
    # Draft Room can decide whether to render the sprout badge.
    assert src.count('"league_minors_enabled"] = bool(league.get("minors_enabled"))') >= 2
