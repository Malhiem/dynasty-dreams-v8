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

### Verified Behaviors (49 tests, 100% pass rate)
- ✅ Fixed roster: 5 games × 2 goals = 10 goals
- ✅ Trade: 10/6 goal split (5:3 game ratio, fpts + roto)
- ✅ Drop: earlier earnings preserved
- ✅ Pickup after drop: unowned gap excluded (2 games not credited)
- ✅ Drop + reacquire: both intervals preserved, gap excluded
- ✅ Active→bench: bench-period stats excluded
- ✅ Bench→active: only post-activation stats counted
- ✅ Historical correction: goes to original owner at game time
- ✅ Multiple trades: three-way split (A→B→C)
- ✅ Recomputation: fully idempotent (3 runs identical)
- ✅ Finalization: stores correct trade split
- ✅ Finalized history: survives post-period trade
- ✅ Waiver pickup: correct split with gap
- ✅ Retroactive ownership: created when initial span missing
- ✅ Backfill: evidence-based, idempotent
- ✅ Uncertainty flagging: 0 with uncertain=true when no data
- ✅ Daily breakdown: checks lineup eligibility

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
