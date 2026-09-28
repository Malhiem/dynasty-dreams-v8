# Dynasty Dreams - Fantasy Hockey Platform PRD

## Original Problem Statement
Build a fantasy hockey league management platform with dynasty features — multi-season roster management, trades, waivers, draft management, and comprehensive scoring across Head-to-Head, Rotisserie, and Best Ball formats.

## Architecture
- **Frontend**: React 19 + Vite + TailwindCSS + shadcn/ui
- **Backend**: FastAPI (Python 3.11) + MongoDB (Motor async driver)
- **Key Libraries**: Stripe (payments), SendGrid (email)

## Core Requirements
1. League creation and management (H2H, Roto, Best Ball, Dynasty)
2. Roster management with trades, waivers, drops, pickups
3. Live scoring from NHL stats
4. Draft system (snake, auction, dynasty)
5. Commissioner tools and platform admin dashboard
6. Matchup scheduling and playoff brackets

## What's Been Implemented

### Historical Scoring Allocation Engine (P0 — COMPLETE)
- **Point-in-Time Ownership Tracking** (`/app/backend/utils/scoring_roster.py`):
  Records exact timestamps for ownership and lineup eligibility changes.
  All 15 roster mutation paths instrumented.
- **Game-Level Allocation Engine** (`/app/backend/utils/game_allocation.py`):
  Allocates stats by cross-referencing each game's puck-drop time with
  ownership/lineup intervals. Never uses simple period aggregation.
- **Evidence-Based Backfill** (`/app/backend/utils/backfill_ownership.py`):
  Reconstructs ownership and lineup periods from executed trades, activity
  feed events, and roster change logs. Idempotent. Tags each period with
  evidence source (trade, activity_feed, inferred_baseline, etc.).
  Marks periods with insufficient evidence rather than inventing history.
- **Uncertainty-Aware Fallback**: When no ownership data exists and backfill
  hasn't been run, results are flagged `uncertain: true, needs_backfill: true`
  instead of silently giving all stats to the current roster owner.
- **Admin Backfill Endpoints**:
  - `POST /api/admin/platform/backfill-ownership/{league_id}` — Per-league
  - `POST /api/admin/platform/backfill-ownership` — All leagues
- **Verified Behaviors** (18 acceptance tests + 6 API tests, 100% pass):
  - Trade: 10/6 goal split preserved
  - Drop: earlier earnings stay with original owner
  - Reacquisition: unowned gap stats excluded
  - Bench/IR: ineligible period stats excluded
  - Late import/correction: goes to owner at game time
  - Recomputation: fully idempotent
  - Known unowned ≠ missing history (distinct handling)

### Other Completed Features
- League creation wizard and settings
- Roster management (trades, drops, waivers, buyouts)
- Live scoring workers and NHL data ingestion
- Draft system with pick trading
- Commissioner dashboard and audit tools
- Platform admin dashboard
- Matchup scheduling, playoffs, and brackets
- Salary cap management
- Activity feed and chat
- Stripe payment integration (requires user API key)
- SendGrid email integration

## Prioritized Backlog

### P1 (High)
- None pending

### P2 (Medium)
- UX polish on Drag-and-Drop Division step
- Refactor `PlayoffsScheduleCards.tsx` (1150+ lines)
- Modularize `server.py` and `live_scoring_worker.py`

### P3 (Low)
- Trade Review Settings UI
- Additional scoring format enhancements
- Extended reporting and analytics

## Key Technical Conventions
- **Timezones**: Always `datetime(…, tzinfo=timezone.utc)`. Never `datetime.date` in MongoDB queries.
- **Scoring Integrity**: Always use `game_allocation.py` functions. Never simple period aggregation.
- **Ownership Data**: Check `league.ownership_backfilled_at` before trusting allocation results.
- **MongoDB**: All ObjectId fields through `PyObjectId` annotated type. `from_mongo()`/`to_mongo()` helpers.

## Test Credentials
- Admin: `admin@dynastydreams.com` / `Admin123!`
