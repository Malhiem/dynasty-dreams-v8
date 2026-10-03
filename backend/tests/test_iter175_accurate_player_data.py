"""
Iter 175 — Accurate player data (birth_date, age, career_games_played)
+ minor-eligibility derived from real values.

The team page used to display every player as age 27 because the
roster endpoint hard-coded the field. After Iter 174 that was fixed
to use whatever the player doc carried — but the player docs
themselves were missing `birth_date` + `career_games_played`, so the
field was just blank. This iteration:

  1. Backfills `birth_date`, `age`, and `career_games_played` for
     every player with a real NHL ID from the NHL public stats API
     (`https://api-web.nhle.com/v1/player/{id}/landing`).
  2. Updates `/api/roster/{id}/detail` to compute `minor_eligible`
     from BOTH age and career_games_played (with the league's
     `minors_max_age` / `minors_max_career_games` thresholds), with
     explicit `player_type == "prospect"` as an override.
"""
from pathlib import Path

SCRIPT = Path("/app/backend/scripts/iter175_backfill_player_data.py")
ROSTER_PY = Path("/app/backend/routes/roster.py")


# ── Backfill script ────────────────────────────────────────────────


def test_backfill_script_exists_and_uses_official_endpoint():
    assert SCRIPT.exists()
    src = SCRIPT.read_text()
    # Public NHL stats endpoint, no auth needed.
    assert "api-web.nhle.com/v1/player/{nhl_id}/landing" in src
    assert "if __name__ ==" in src
    assert "asyncio.run(main())" in src


def test_backfill_script_skips_synthetic_prospect_ids():
    """Iter 173 seeded prospects use negative nhl_ids (e.g. -1000027).
    Hitting the NHL API for those returns 404 + spams. Skip them, and
    also skip rows already explicitly typed as 'prospect'."""
    src = SCRIPT.read_text()
    assert '"nhl_id": {"$exists": True, "$ne": None, "$gt": 0}' in src
    assert '"player_type": {"$ne": "prospect"}' in src


def test_backfill_script_writes_expected_fields():
    src = SCRIPT.read_text()
    # All four derived fields land on the doc.
    assert '"birth_date" in update_fields or' in src or 'update_fields["birth_date"]' in src
    assert 'update_fields["age"]' in src
    assert 'update_fields["career_games_played"]' in src
    assert 'update_fields["nhl_data_synced_at"]' in src


def test_backfill_script_is_idempotent_by_default():
    """Without --force the query excludes rows that already have the
    backfilled fields, so re-running doesn't re-spam the NHL API."""
    src = SCRIPT.read_text()
    assert "if not args.force:" in src
    assert '"birth_date": {"$in": [None, ""]}' in src
    assert '"career_games_played": {"$in": [None]}' in src
    assert "--force" in src


def test_backfill_script_computes_age_correctly():
    """Age must subtract a year when today is before the player's
    birthday — otherwise McDavid (Jan 13, 1997) reads as 30 in
    early Feb 2026 instead of 29."""
    src = SCRIPT.read_text()
    assert "((today.month, today.day) < (bd.month, bd.day))" in src


# ── /api/roster/{id}/detail ────────────────────────────────────────


def test_roster_endpoint_surfaces_career_games_played():
    src = ROSTER_PY.read_text()
    assert '"career_games_played": career_gp,' in src
    assert "career_gp = p.get(\"career_games_played\")" in src


def test_minor_eligibility_uses_age_and_career_gp():
    """The eligibility predicate is: explicit prospect OR (age <=
    max_age AND career_gp <= max_career_games). League settings
    drive the thresholds (defaults: 22yo / 25 career games)."""
    src = ROSTER_PY.read_text()
    assert 'max_age = int((league or {}).get("minors_max_age") or 22)' in src
    assert 'max_career_gp = int((league or {}).get("minors_max_career_games") or 25)' in src
    assert "age_ok = player_age is None or player_age <= max_age" in src
    assert "gp_ok = career_gp is None or int(career_gp) <= max_career_gp" in src
    # AND combination (both must hold) when no explicit prospect flag.
    assert "or (age_ok and gp_ok)" in src
    # Explicit prospect status still wins.
    assert 'player_type == "prospect"' in src
    assert 'bool(p.get("minor_eligible"))' in src


def test_age_resolution_handles_missing_birth_date_gracefully():
    """When birth_date is missing we fall back to whatever `age`
    field the player doc carries; both being missing yields None,
    which the eligibility check treats as "unknown → permit"."""
    src = ROSTER_PY.read_text()
    assert "player_age = p.get(\"age\")" in src
    assert "if not player_age and bd:" in src
    # Uses calendar-aware year subtraction (same logic as the script).
    assert "today.year - bd_dt.year - (" in src
    assert "(today.month, today.day) < (bd_dt.month, bd_dt.day)" in src
