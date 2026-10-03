"""
Iter 175b — Daily player-data backfill worker.

The Iter 175 backfill ran as a one-shot script. To keep ages +
career-GP fresh as the NHL season progresses (new call-ups, birthdays
rolling over, players crossing the 25-career-GP threshold and flipping
minor-eligibility), we schedule it as a background task that re-runs
every 24h. Matches the pattern of `ownership_snapshot_worker` and
`playoff_tbd_worker` already running in production.
"""
from pathlib import Path

WORKER = Path("/app/backend/player_data_backfill_worker.py")
SERVER = Path("/app/backend/server.py")


def test_worker_file_exists_with_documented_intent():
    assert WORKER.exists()
    src = WORKER.read_text()
    # Module docstring spells out WHY this exists (knowledge transfer).
    assert "Daily player-data backfill worker" in src
    # Public API surface that server.py imports.
    assert "async def player_data_backfill_loop" in src
    assert "async def backfill_once" in src


def test_worker_runs_on_24h_cadence_with_calendar_aware_age_math():
    src = WORKER.read_text()
    # 24h default keeps birthday rollovers + crossing 25-career-GP
    # threshold reflected within a day.
    assert "DEFAULT_INTERVAL_SEC = 24 * 60 * 60" in src
    # Same calendar-aware age computation as the one-shot script.
    assert "((today.month, today.day) < (bd.month, bd.day))" in src


def test_worker_query_targets_missing_or_stale_rows_only():
    """Re-runs must NOT hammer the NHL API for every player every
    day. The query selects rows that are either missing the data OR
    have a `nhl_data_synced_at` older than 1 day. Synthetic prospect
    IDs (negative) + explicit prospect rows are excluded so we don't
    spray 404s at the public endpoint."""
    src = WORKER.read_text()
    assert "DEFAULT_STALE_AFTER = timedelta(days=1)" in src
    assert "\"$gt\": 0" in src
    assert "\"player_type\": {\"$ne\": \"prospect\"}" in src
    assert "\"nhl_data_synced_at\": {\"$exists\": False}" in src
    assert "\"nhl_data_synced_at\": {\"$lt\": cutoff}" in src


def test_worker_uses_official_public_endpoint_and_polite_headers():
    src = WORKER.read_text()
    assert "api-web.nhle.com/v1/player/{nhl_id}/landing" in src
    # Identifiable User-Agent so NHL ops can reach out if we're noisy.
    assert "User-Agent" in src and "DynastyDreams" in src


def test_worker_is_resilient_to_single_row_failures():
    """One bad row never breaks the loop — the per-player processor
    swallows exceptions and `backfill_once` retries on the next tick
    after a generous backoff."""
    src = WORKER.read_text()
    # try/except around _process_player call inside the worker function.
    assert "_process_player(http, db, p)" in src
    # Tight-loop guard — wait 5 minutes after a top-level crash before
    # retrying so we don't burn CPU + API quota on persistent failures.
    assert "await asyncio.sleep(300)" in src
    # First-pass deferral so we don't compete with app boot.
    assert "await asyncio.sleep(60)" in src


def test_worker_respects_concurrency_env_knob():
    """Ops can tune parallelism via PLAYER_DATA_BACKFILL_CONCURRENCY
    without a code change."""
    src = WORKER.read_text()
    assert 'os.environ.get("PLAYER_DATA_BACKFILL_CONCURRENCY", "8")' in src
    assert "asyncio.Semaphore(concurrency)" in src


def test_server_wires_worker_into_startup_and_shutdown():
    src = SERVER.read_text()
    # Imported + task created with the same loop.create_task pattern
    # used for live_scoring / ownership_snapshot / playoff_tbd.
    assert "from player_data_backfill_worker import player_data_backfill_loop" in src
    assert "player_data_backfill_loop(db)" in src
    assert "fastapi_app.state.player_data_backfill_task" in src
    # Cancelled cleanly on shutdown — matches the existing pattern.
    assert 'getattr(fastapi_app.state, "player_data_backfill_task", None)' in src
    assert "backfill_task.cancel()" in src


def test_server_skips_worker_under_pytest():
    """Unit tests must not bind to the public NHL endpoint. Server
    startup checks PYTEST_CURRENT_TEST and skips this worker, the way
    a lot of integration shops do."""
    src = SERVER.read_text()
    assert 'os.environ.get("PYTEST_CURRENT_TEST")' in src
    # Specifically gates the player-data backfill (not other workers).
    idx_guard = src.find('if not os.environ.get("PYTEST_CURRENT_TEST"):')
    idx_import = src.find("from player_data_backfill_worker import")
    assert idx_guard > 0 and idx_import > idx_guard, (
        "PYTEST guard must precede the import so the worker never starts under pytest"
    )
