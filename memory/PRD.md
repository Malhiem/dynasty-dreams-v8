# Dynasty Dreams - Fantasy Hockey Platform PRD

## Original Problem Statement
Build a fantasy hockey league management platform with dynasty features — multi-season roster management, trades, waivers, draft management, and comprehensive scoring across Head-to-Head, Rotisserie, and Best Ball formats.

## Architecture
- **Frontend**: React 19 + Vite + TailwindCSS + shadcn/ui
- **Backend**: FastAPI (Python 3.11) + MongoDB (Motor async driver)
- **Key Libraries**: Stripe (payments), SendGrid (email)

## Historical Scoring Allocation Engine (P0 — COMPLETE, HARDENED)

### Engine Design
Every scoring calculation resolves stats at the **individual game level** using ownership and lineup intervals. No simple period aggregation is ever used.

### Core Components
1. **`game_allocation.py`** — Game-level allocation engine
   - `allocate_team_period_fpts()` — Fantasy points for a team in a time period
   - `allocate_team_period_roto_stats()` — Roto category stats
   - `_owned_at_mem()` — In-memory ownership check per game
   - `_eligible_at_mem()` — In-memory lineup eligibility check per game
   - `_build_game_date_map()` — Resolves game IDs → game start times (preserves puck-drop time)

2. **`scoring_roster.py`** — Point-in-time ownership and lineup tracking
   - `record_ownership_start()` — Opens new ownership period
   - `record_ownership_end()` — **Creates retroactive period from league season start when no open span exists** (critical for un-seeded initial ownership)
   - `record_lineup_change()` — Records lineup position changes
   - `log_roster_change()` — Entry point for all roster mutations. Accepts optional `timestamp`. On `add`: creates ownership + seeds initial lineup. On `remove`: closes ownership + lineup.
   - `_resolve_league_start_dt()` — Resolves league season start to UTC datetime
   - `_section_to_canonical()` — Maps lineup sections to canonical position names

3. **`backfill_ownership.py`** — Evidence-based backfill engine
   - Reconstructs ownership from executed trades, activity feed, roster change logs
   - Tags each period with evidence source
   - Idempotent (safe to re-run)

### Verified Behaviors (69 tests across 3 suites, 100% pass rate)

**E2E Allocation Suite (38 tests — `test_e2e_allocation.py`)**
- ✅ Fixed roster controls: H2H points, H2H categories, Roto (3 tests)
- ✅ Trade 10/6 split, drop preserves stats, unowned gap excluded, reacquisition, multiple trades (A→B→C), no overlap verification, multi-player partial trade, waiver pickup after gap (8 tests)
- ✅ Active→bench, bench→active, eligibility at puck drop, mid-game lineup no change, IR→active, bench→active→bench sandwich (6 tests)
- ✅ Late import uses game time, correction to original owner, no duplication on reimport, goalie scoring allocation (4 tests)
- ✅ Finalization after trade, finalize-before-trade-then-recalculate, breakdown agrees with total, fpts idempotent with trade (4 tests)
- ✅ Roto historical ownership, no retroactive movement, recomputation idempotent, correction updates allocation (4 tests)
- ✅ Missing vs unowned, uncertain not definitive zero, backfill uses evidence, current roster not season-long, repeated backfill no duplicates (5 tests)
- ✅ Game before transaction → old owner, game exactly at transaction → new owner, timezone equivalence, same-day double-header trade between puck drops (4 tests)

**Complete History Suite (18 tests — `test_complete_history.py`)**
**API Flow Allocation Suite (13 tests — `test_api_flow_allocation.py`)**

### Key Conventions
- **Fixture requirements**: Tests MUST seed initial ownership + lineup periods, use numeric game IDs with matching game records
- **Timezones**: Always `datetime(…, tzinfo=timezone.utc)`. Never `datetime.date` in MongoDB queries.
- **Game dates**: Preserves puck-drop time when available, falls back to midnight UTC
- **Ownership boundaries**: `acquired_at <= game_date` and `(released_at is None or released_at > game_date)`
- **Lineup eligibility**: `position in ACTIVE_SECTIONS` where `ACTIVE_SECTIONS = {"forward", "defense", "goalie"}`

### API Endpoints
- `GET /api/scoring/calculate/{league_id}?week=N` — H2H scoring (uses allocate_team_period_fpts)
- `GET /api/scoring/roto/{league_id}?week=N` — Roto standings (uses allocate_team_period_roto_stats)
- `GET /api/matchups/daily-scoring/{league_id}/{team_id}?week=N` — Daily breakdown (checks ownership + lineup)
- `POST /api/admin/platform/backfill-ownership/{league_id}` — Per-league backfill
- `POST /api/admin/platform/backfill-ownership` — All leagues backfill
- `GET /api/roster/{team_id}/history` — Ownership/lineup history

## Other Completed Features
- League creation wizard and settings
- Roster management (trades, drops, waivers, buyouts)
- Live scoring workers and NHL data ingestion
- Draft system with pick trading
- Commissioner dashboard and audit tools
- Platform admin dashboard
- Matchup scheduling, playoffs, and brackets
- Salary cap management
- Activity feed and chat

## Prioritized Backlog

### P2 (Medium)
- UX polish on Drag-and-Drop Division step
- Refactor `PlayoffsScheduleCards.tsx` (1150+ lines)
- Modularize `server.py` and `live_scoring_worker.py`

### P3 (Low)
- Trade Review Settings UI
- Additional scoring format enhancements
- Extended reporting and analytics

## Test Credentials
- Admin: `admin@dynastydreams.com` / `Admin123!`
