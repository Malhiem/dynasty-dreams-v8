"""Global pytest configuration for /app/backend/tests/.

Iter 231ad — Establishes a single source of truth for environment
bootstrap + cross-test pollution cleanup. Before this file existed:

  • Each HTTP-mode test had to grab `REACT_APP_BACKEND_URL` /
    `MONGO_URL` / `DB_NAME` from `os.environ` and fail with a noisy
    `KeyError` if the caller forgot to `set -a && source .env`.
  • Test files that seeded persistent docs (players, leagues, teams,
    waiver_claims, etc.) against the SHARED preview MongoDB had no
    common teardown — so leaks accumulated over hundreds of CI runs
    (see iter 231ac: 65 polluting `ForceP-*` / `FutureP-*` /
    `WaiverTarget-*` players, 91 dead `iter228-*` leagues).

This conftest does two things:

  1. **Environment bootstrap** (`pytest_configure`) — auto-loads
     `/app/backend/.env` so `os.environ["MONGO_URL"]` etc. resolve
     without an explicit `source .env`. Also sets a sane
     `REACT_APP_BACKEND_URL` default so HTTP-mode tests don't
     KeyError when CI hasn't exported it. Existing exports win — we
     only fill in gaps.

  2. **Module-level pollution sweep** (`_global_pollution_sweep`
     auto-use fixture) — before AND after every module, scrub any
     documents that match the canonical pollution patterns:

       • players with `_test_seed: True` flag (canonical marker) OR
         legacy name prefixes `ForceP-` / `FutureP-` / `WaiverTarget-`
         / `Iter231q Player` / `i231ab Player`.
       • leagues with name `^iter(228|231)[a-z]?-` (ephemeral CI
         leagues that should never leak into the live preview DB).
       • their teams, drafts, waiver_claims, waiver_budgets, and
         team_invites (referential cleanup).

     Best-effort — never blocks the test run on a sweep failure.
     Module-scoped fixtures survive until their module finishes. The
     disposable-suite baseline is guarded by explicit isolation settings
     and survives sweeps so legacy HTTP tests have deterministic inputs.

NEW test files should tag every seeded doc with `_test_seed: True`
so this sweep finds it automatically. Pattern:

    db.players.insert_one({**player_doc, "_test_seed": True})

Iter 231ah update — Legacy test files that pre-date the `_test_seed`
convention are now AUTO-TAGGED via a `pytest_collection_modifyitems`
hook that monkey-patches both PyMongo's sync `Collection.insert_one
/.insert_many` AND Motor's async `AsyncIOMotorCollection.insert_one
/.insert_many` for the 9 polluted collections (players, leagues,
users, teams, drafts, waiver_claims, waiver_budgets, team_invites,
league_invites). The patch only activates DURING pytest — production
code is untouched. New test files DON'T need to set `_test_seed`
manually; the patch handles it.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

# ─── Pollution patterns ────────────────────────────────────────────────
# Player names — legacy unmarked-seed patterns we MUST sweep until every
# old test file is migrated to tag `_test_seed: True`.
_PLAYER_NAME_PATTERN = re.compile(
    r"^("
    r"ForceP|FutureP|WaiverTarget|RollbackP|"
    # Generic `<Word>P-<hex>` test-player pattern (iter228 style).
    r"[A-Z][a-zA-Z]+P-[a-f0-9]{4,}|"
    r"Iter\s*23\d[a-z]{0,3}\s*Player|"
    r"i\s*23\d[a-z]{0,3}\s*Player|"
    r"i\s*22\d[a-z]{0,3}\s*Player|"
    r"NHL Veteran Forward|Minor Eligible Forward|Repeat Pick|"
    r"TestPlayer|Waiver Player"
    r")",
    re.IGNORECASE,
)
# League names — ephemeral test leagues. Broadened in iter231af to catch
# `i228n-` (was only catching `i23X-` prefixes pre-231af). Pattern now:
# `iter` or `i` + 3-digit year-marker + 0-3 letter suffix + separator.
_LEAGUE_NAME_PATTERN = re.compile(
    # Three flavors of ephemeral test leagues:
    #   1. `iter228-` / `i228n-` / `i231ab-` — HTTP test files.
    #   2. `TEST_*`             — Playwright / E2E suite leagues.
    r"^(iter|i)\s*\d{3}[a-z]{0,3}[-_ ]|^TEST_",
    re.IGNORECASE,
)
# Iter 231af — `@example.com` is RFC-reserved for documentation and is
# the canonical test-user email domain across this codebase. Real
# users register with gmail / outlook / live / dynastydreams etc., so
# any `@example.com` row is by-definition test pollution. Much safer
# + simpler than maintaining a prefix allow-list (which can drift).
_TEST_USER_EMAIL_PATTERN = re.compile(r"@example\.com$", re.IGNORECASE)


def pytest_configure(config):
    """Bootstrap env vars so tests don't KeyError on common settings.

    Iter 231ah — Also installs auto-tagging insert monkey-patches so
    legacy test files that don't manually add `_test_seed: True` still
    get cleaned up. See `_install_auto_seed_tagger` below.
    """
    env_path = Path("/app/backend/.env")
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            # Don't overwrite explicit caller env. Fill in gaps only.
            if key and key not in os.environ:
                os.environ[key] = val
    # Some integration tests assume a preview backend URL even when
    # they don't actually hit the network. Default to the preview host
    # if nobody set it — keeps `os.environ["REACT_APP_BACKEND_URL"]`
    # imports at module-load time from KeyErroring.
    os.environ.setdefault(
        "REACT_APP_BACKEND_URL",
        "https://dynasty-preview.preview.emergentagent.com",
    )
    # Iter 231ah — Install auto-tagger monkey-patches AFTER env bootstrap
    # but BEFORE any test imports motor/pymongo. Idempotent — running
    # twice on the same interpreter is a no-op.
    _install_auto_seed_tagger()


# ─── Iter 231ah — Auto-tag inserts during test runs ─────────────────
# Legacy test files that pre-date the `_test_seed` convention don't
# need to be migrated one-by-one. Instead, while pytest is running we
# transparently wrap `Collection.insert_one` / `insert_many` for the
# 9 polluted collections so every test-driven insert lands with
# `_test_seed: True` already set.
#
# Production code is unaffected — these patches only apply to the
# pytest Python process. App services run in supervisor's own
# interpreter and never load this conftest.

_AUTO_SEED_COLLECTIONS = {
    "players", "leagues", "users", "teams", "drafts",
    "waiver_claims", "waiver_budgets", "team_invites", "league_invites",
}
_AUTO_SEED_INSTALLED = False


def _tag_doc(doc):
    """Insert `_test_seed: True` if it's a dict and doesn't already
    have a value for the key."""
    if isinstance(doc, dict) and "_test_seed" not in doc:
        doc["_test_seed"] = True
    return doc


def _tag_docs(docs):
    if isinstance(docs, list):
        return [_tag_doc(d) for d in docs]
    return docs


def _install_auto_seed_tagger() -> None:
    global _AUTO_SEED_INSTALLED
    if _AUTO_SEED_INSTALLED:
        return
    # ── PyMongo (sync) ───────────────────────────────────────────────
    try:
        from pymongo.collection import Collection
        _orig_sync_insert_one = Collection.insert_one
        _orig_sync_insert_many = Collection.insert_many

        def _wrapped_sync_insert_one(self, document, *args, **kwargs):
            if self.name in _AUTO_SEED_COLLECTIONS:
                _tag_doc(document)
            return _orig_sync_insert_one(self, document, *args, **kwargs)

        def _wrapped_sync_insert_many(self, documents, *args, **kwargs):
            if self.name in _AUTO_SEED_COLLECTIONS:
                _tag_docs(documents)
            return _orig_sync_insert_many(self, documents, *args, **kwargs)

        Collection.insert_one = _wrapped_sync_insert_one
        Collection.insert_many = _wrapped_sync_insert_many
    except Exception as e:  # pragma: no cover
        print(f"[conftest] pymongo auto-tag install failed: {e}")
    # ── Motor (async) ────────────────────────────────────────────────
    try:
        from motor.motor_asyncio import AsyncIOMotorCollection
        _orig_async_insert_one = AsyncIOMotorCollection.insert_one
        _orig_async_insert_many = AsyncIOMotorCollection.insert_many

        async def _wrapped_async_insert_one(self, document, *args, **kwargs):
            if self.name in _AUTO_SEED_COLLECTIONS:
                _tag_doc(document)
            return await _orig_async_insert_one(self, document, *args, **kwargs)

        async def _wrapped_async_insert_many(self, documents, *args, **kwargs):
            if self.name in _AUTO_SEED_COLLECTIONS:
                _tag_docs(documents)
            return await _orig_async_insert_many(self, documents, *args, **kwargs)

        AsyncIOMotorCollection.insert_one = _wrapped_async_insert_one
        AsyncIOMotorCollection.insert_many = _wrapped_async_insert_many
    except Exception as e:  # pragma: no cover
        print(f"[conftest] motor auto-tag install failed: {e}")
    _AUTO_SEED_INSTALLED = True


def _sweep_polluted_artefacts() -> None:
    """Best-effort cleanup of legacy + tagged pollution from MongoDB."""
    mongo_url = os.environ.get("MONGO_URL")
    if not mongo_url:
        return
    try:
        from bson import ObjectId
        from pymongo import MongoClient

        db = MongoClient(mongo_url, serverSelectionTimeoutMS=2000)[
            os.environ.get("DB_NAME", "test_database")
        ]

        # ── 1. Players ───────────────────────────────────────────────
        polluted_players = list(db.players.find(
            {"$or": [
                {"_test_seed": True},
                {"iter228_test_seed": True},  # iter231ac legacy marker
                {"name": {"$regex": _PLAYER_NAME_PATTERN}},
            ]},
            {"_id": 1},
        ))
        pids = [str(p["_id"]) for p in polluted_players]
        if pids:
            # Pull from any team rosters that hold these orphans.
            db.teams.update_many(
                {"roster": {"$in": pids}},
                {"$pull": {"roster": {"$in": pids}}},
            )
            db.waiver_claims.delete_many({"player_id": {"$in": pids}})
            db.players.delete_many({"_id": {"$in": [p["_id"] for p in polluted_players]}})

        # ── 2. Ephemeral leagues + their dependents ─────────────────
        polluted_leagues = list(db.leagues.find(
            {"$or": [
                {"_test_seed": True},
                {"name": {"$regex": _LEAGUE_NAME_PATTERN}},
            ]},
            {"_id": 1},
        ))
        lids = [str(lg["_id"]) for lg in polluted_leagues]
        if lids:
            db.teams.delete_many({"league_id": {"$in": lids}})
            db.drafts.delete_many({"league_id": {"$in": lids}})
            db.waiver_claims.delete_many({"league_id": {"$in": lids}})
            db.waiver_budgets.delete_many({"league_id": {"$in": lids}})
            db.team_invites.delete_many({"league_id": {"$in": lids}})
            db.league_invites.delete_many({"league_id": {"$in": lids}})
            db.leagues.delete_many({"_id": {"$in": [lg["_id"] for lg in polluted_leagues]}})

        # ── 3. Test user accounts + their owned leagues ───────────
        # Iter 231af — Scrub `@example.com` users (RFC-reserved test
        # domain) AND cascade-delete every league they own. Without
        # the cascade, HTTP-mode tests that register fresh users then
        # POST `/api/leagues` would leak thousands of orphan leagues
        # owned by deleted users (seen in iter231af repair: 2,677
        # orphan leagues / 4,974 teams / 1,400 drafts).
        test_users = list(db.users.find(
            {"$or": [
                {"_test_seed": True},
                {"email": {"$regex": _TEST_USER_EMAIL_PATTERN}},
            ]},
            {"_id": 1},
        ))
        if test_users:
            uids = [str(u["_id"]) for u in test_users]
            # Find every league owned by a test user.
            owned_leagues = list(db.leagues.find(
                {"commissioner_id": {"$in": uids}}, {"_id": 1},
            ))
            owned_lids = [str(lg["_id"]) for lg in owned_leagues]
            if owned_lids:
                db.teams.delete_many({"league_id": {"$in": owned_lids}})
                db.drafts.delete_many({"league_id": {"$in": owned_lids}})
                db.waiver_claims.delete_many({"league_id": {"$in": owned_lids}})
                db.waiver_budgets.delete_many({"league_id": {"$in": owned_lids}})
                db.team_invites.delete_many({"league_id": {"$in": owned_lids}})
                db.league_invites.delete_many({"league_id": {"$in": owned_lids}})
                db.leagues.delete_many({"_id": {"$in": [lg["_id"] for lg in owned_leagues]}})
            # Teams the test user owned directly (not via league cascade).
            db.teams.delete_many({"owner_id": {"$in": uids}})
            db.users.delete_many({"_id": {"$in": [u["_id"] for u in test_users]}})
    except Exception as e:
        # Never block the test run on a sweep failure.
        print(f"[conftest] global pollution sweep skipped: {e}")


@pytest.fixture(autouse=True, scope="module")
def _global_pollution_sweep():
    """Sweep before/after each module, preserving module/class-scoped fixtures.

    Each side of the sweep is independent + best-effort — a failure
    on one side doesn't block the other or the test itself.
    """
    from tests.isolated_seed import seed_disposable_suite
    seed_disposable_suite(reset=True)
    _sweep_polluted_artefacts()
    yield
    _sweep_polluted_artefacts()


@pytest.fixture(autouse=True, scope="session")
def _disposable_suite_baseline():
    from tests.isolated_seed import seed_disposable_suite
    seed_disposable_suite()


def pytest_assertrepr_compare(op, left, right):
    """Keep legacy source-string assertion failures useful without dumping files."""
    if op in ("in", "not in") and isinstance(left, str) and isinstance(right, str) and len(right) > 4000:
        return [f"Expected source check: {left!r} {op} source", f"Source length: {len(right)} characters"]
