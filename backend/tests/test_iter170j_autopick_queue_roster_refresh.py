"""Iter 170j — Auto-pick on Timeout + Draft Queue persistence + Roster
Future-Picks live refresh.

Backend (`routes/drafts.py`):
  (1) `POST /drafts/{id}/auto-pick` — picks for the on-clock team using
      `team.draft_queue` first (first undrafted entry), falling back to
      the top-ranked eligible player. Pushes the player onto the team's
      roster + pulls them from the queue + broadcasts.
  (2) `PUT /teams/{id}/draft-queue` — owner-or-commissioner endpoint to
      persist the team's auto-pick queue. Dedupes + caps at 100 entries.
  (3) `GET /teams/{id}/draft-queue` — read the persisted queue.

Frontend:
  (4) DraftRoom timer effect calls `/auto-pick` exactly once per pick
      (ref-guarded by `lastAutoFireRef`) when the clock expires.
  (5) DraftRoom hydrates + debounced-persists the queue against
      `/teams/{myTeam.id}/draft-queue`.
  (6) TeamDraftPicks accepts `leagueId`, resolves the active draft id,
      subscribes to `draft_{id}` socket events, and bumps `reloadTick`
      on `draft_undo` / `draft_pick_swapped` / `draft_pick` so the
      Future Draft Picks card auto-refreshes after commissioner edits.
"""
from pathlib import Path

DRAFTS_ROUTE = Path("/app/backend/routes/drafts.py")
DRAFT_ROOM = Path("/app/frontend/src/lovable/pages/DraftRoom.tsx")
TEAM_DRAFT_PICKS = Path("/app/frontend/src/lovable/components/dashboard/TeamDraftPicks.tsx")
TEAM_PAGE = Path("/app/frontend/src/lovable/pages/Team.tsx")


# ─── Backend ──────────────────────────────────────────────────────────


def test_auto_pick_endpoint_present_and_queue_first():
    src = DRAFTS_ROUTE.read_text()
    assert '@router.post("/drafts/{draft_id}/auto-pick")' in src
    block = src.split("async def auto_pick_for_on_clock_team")[1].split("# ─── Iter 170j — Draft Queue")[0]
    # Queue is consulted before falling back to top eligible.
    assert 'queue = list((team or {}).get("draft_queue") or [])' in block
    assert 'via = "queue"' in block
    assert 'via = "top_eligible"' in block
    # Pushes to roster + pulls from queue atomically.
    assert '"$addToSet": {"roster": str(chosen_player["_id"])}' in block
    assert '"$pull": {"draft_queue": str(chosen_player["_id"])}' in block
    # Broadcasts a draft_pick (same channel as a manual pick).
    assert '"draft_pick"' in block
    # Stamps `auto_picked: True` on the pick doc so the UI can badge it.
    assert '"auto_picked": True' in block


def test_draft_queue_put_validates_owner_or_commissioner():
    src = DRAFTS_ROUTE.read_text()
    assert '@router.put("/teams/{team_id}/draft-queue")' in src
    block = src.split("async def update_team_draft_queue")[1].split("@router.get")[0]
    # Owner OR commissioner gate.
    assert 'is_owner = team.get("owner_id") == user["_id"]' in block
    assert 'is_comm = league and league.get("commissioner_id") == user["_id"]' in block
    # Dedupe + cap.
    assert "if pid not in seen:" in block
    assert "len(cleaned) >= 100" in block


def test_draft_queue_get_endpoint_present():
    src = DRAFTS_ROUTE.read_text()
    assert '@router.get("/teams/{team_id}/draft-queue")' in src


# ─── Frontend: DraftRoom auto-pick + queue persistence ────────────────


def test_draftroom_auto_pick_on_timeout():
    src = DRAFT_ROOM.read_text()
    # Ref guard + clear on currentPick change so we fire at most once
    # per pick.
    assert "const lastAutoFireRef = useRef<number | null>(null)" in src
    assert "lastAutoFireRef.current = null" in src
    assert "lastAutoFireRef.current !== draftConfig.currentPick" in src
    # POST to /auto-pick when timer expires and a real draft is active.
    assert "api.post(`/drafts/${currentDraft._id}/auto-pick`)" in src


def test_draftroom_queue_hydrate_and_persist():
    src = DRAFT_ROOM.read_text()
    # Hydrate on mount + debounced persist on change.
    assert "api.get(`/teams/${(myTeam as any).id}/draft-queue`)" in src
    assert "api.put(`/teams/${(myTeam as any).id}/draft-queue`, { player_ids: queue })" in src
    # Hydration guard so the very first GET response doesn't kick off
    # a redundant PUT in a loop.
    assert "const hasHydratedQueueRef = useRef(false)" in src


# ─── Frontend: TeamDraftPicks live refresh ───────────────────────────


def test_team_draft_picks_accepts_league_id_and_subscribes():
    src = TEAM_DRAFT_PICKS.read_text()
    # New optional prop + activeDraftId resolution + subscription.
    assert "leagueId?: string;" in src
    assert "const [activeDraftId, setActiveDraftId] = useState<string | null>(null)" in src
    assert "/drafts?league_id=${leagueId}`" in src
    assert "activeDraftId ? `draft_${activeDraftId}` : null" in src
    # Three listeners that bump the reload tick.
    for evt in ("draft_undo", "draft_pick_swapped", "draft_pick"):
        assert f"{evt}: () => setReloadTick" in src
    # Fetch effect dep array includes reloadTick.
    assert "}, [teamId, looksLikeObjectId, reloadTick]);" in src


def test_team_page_passes_league_id():
    src = TEAM_PAGE.read_text()
    # The Team page wires the active league id into TeamDraftPicks.
    assert "<TeamDraftPicks" in src
    assert "leagueId={league?.id}" in src
