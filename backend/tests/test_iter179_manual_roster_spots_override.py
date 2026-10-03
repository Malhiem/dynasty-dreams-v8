"""
Iter 179 — Backend bug: PUT /leagues/{id} was silently overriding the
commissioner's manual `roster_spots` value with the derived sum of the
`position_breakdown.active` row, even when the payload explicitly
included `roster_spots`.

Bug repro (pre-fix):
  1. League has roster_spots=20 (db), position_breakdown.active={S:18, G:2}.
  2. Commissioner sets Active Roster input to 19, leaves caps alone.
  3. PUT /leagues/{id} { "roster_spots": 19,
                        "position_breakdown": {...same... } }
  4. Backend's iter-176 derivation block recomputed active_sum=20 and
     overwrote update["roster_spots"]=20, marking it `derived: true`.
  5. User opens the page again → sees 20 → "the form reset!".

Fix: only auto-derive `roster_spots` from `position_breakdown.active`
when `roster_spots` is NOT in the request body. If the commissioner
explicitly typed a value, that value wins.
"""
from pathlib import Path

LEAGUES_PY = Path("/app/backend/routes/leagues.py")


def test_derivation_guarded_by_explicit_roster_spots_in_body():
    """The iter-176 derivation block must skip whenever the payload
    explicitly includes `roster_spots` — otherwise the commissioner's
    manual override is silently dropped."""
    src = LEAGUES_PY.read_text()
    # The guard reads from `body` (which is
    # payload.model_dump(exclude_unset=True)) — that's the only way
    # to tell whether the field was explicitly set vs left out.
    assert '("position_breakdown" in body) and ("roster_spots" not in body)' in src
    # The previous behaviour (always-on derivation) is gone.
    assert (
        '"position_breakdown" in update or "position_breakdown" in body'
        not in src
    )


def test_iter179_comment_present_for_future_maintainers():
    """Defensive: leave a breadcrumb so the next refactor doesn't
    accidentally re-introduce the override bug."""
    src = LEAGUES_PY.read_text()
    assert "Iter 176/179" in src
    assert "Manual input wins" in src


def test_active_row_derivation_still_fires_when_roster_spots_omitted():
    """The whole point of the breakdown matrix is that filling the
    Active row drives the league's overall roster size. We must keep
    that behaviour when `roster_spots` is NOT in the payload."""
    src = LEAGUES_PY.read_text()
    # The derived flag is still emitted in that branch — UI uses it
    # to badge the auto-computed value.
    assert '"derived": True' in src


def test_rostertab_breakdown_row_visible_when_row_has_saved_data():
    """Iter 179 frontend half: a row that previously had caps saved
    MUST stay visible on reload even if its visibility predicate
    (`benchSpots > 0`, `minors_enabled`) is no longer true. Without
    this, a commissioner who later lowered `bench_spots` to 0 would
    see their bench caps appear to vanish — the surface-level
    symptom of the "menu seems to reset" complaint."""
    rosters_tab = Path("/app/frontend/src/lovable/pages/commissioner/RostersTab.tsx")
    src = rosters_tab.read_text()
    assert "hasExistingData" in src
    assert "|| hasExistingData" in src
    # Iter 180 — the bench-row visibility predicate was simplified
    # (bench2 dropped from UI). A fresh bench row still honours
    # `benchSpots > 0` via the new `benchOn` constant.
    assert "const benchOn = (parseIntOrNull(benchSpots) || 0) > 0;" in src
    assert '(row.key === "bench" && benchOn)' in src
