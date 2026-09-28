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

### Historical Scoring Allocation Engine (P0 — COMPLETE, HARDENED)

**Core Engine** (`/app/backend/utils/game_allocation.py`):
- Allocates stats by cross-referencing each game's date/time with ownership & lineup intervals
- Never uses simple period aggregation
- Game dates preserve time precision (puck-drop > midnight fallback)

**Point-in-Time Ownership** (`/app/backend/utils/scoring_roster.py`):
- `record_ownership_start/end` manage ownership periods
- **Critical fix**: `record_ownership_end` creates RETROACTIVE ownership period (from league season start) when no initial span exists. This ensures trades/drops correctly preserve the old team's historical stats even when initial ownership was never seeded.
- `log_roster_change` accepts optional `timestamp` for retroactive processing
- On `add`: seeds initial `lineup_status_period` from team's lineup state
- On `remove`: closes both ownership and lineup periods

**Evidence-Based Backfill** (`/app/backend/utils/backfill_ownership.py`):
- Reconstructs ownership from executed trades, activity feed, roster change logs
- Tags each period with evidence source (trade, activity_feed, inferred_baseline, etc.)
- Idempotent and safe to re-run
- Admin endpoints:
  - `POST /api/admin/platform/backfill-ownership/{league_id}`
  - `POST /api/admin/platform/backfill-ownership`

**Uncertainty-Aware Fallback**:
- No ownership data + no backfill → returns `{uncertain: true, needs_backfill: true}` with 0 points
- No ownership data + backfilled → returns 0 (genuine empty result)
- NEVER silently gives all stats to the current roster owner

**Verified Behaviors** (28 tests + 3 API tests, 100% pass):
- Trade: 10/6 goal split (5:3 game ratio) ✓
- Trade: retroactive ownership created for old team ✓
- Drop: earlier earnings preserved ✓
- Drop + reacquisition: unowned gap excluded ✓
- Active→bench: bench-period stats excluded ✓
- Bench→active: pre-activation stats excluded ✓
- Late import/correction: goes to owner at game time ✓
- Roto: follows same ownership rules ✓
- Recomputation: fully idempotent ✓
- Known unowned ≠ missing history ✓
- Backfill: idempotent, evidence-tagged ✓

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
- **Ownership Data**: `record_ownership_end` auto-creates retroactive periods. Check `league.ownership_backfilled_at` for bulk data.
- **MongoDB**: All ObjectId fields through `PyObjectId` annotated type. `from_mongo()`/`to_mongo()` helpers.

## Test Credentials
- Admin: `admin@dynastydreams.com` / `Admin123!`
