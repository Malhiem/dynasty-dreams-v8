# Dynasty Dreams - Product Requirements Document

## Original Problem Statement
Build a comprehensive fantasy NHL management platform with advanced admin tools, commissioner controls, and multi-format scoring engines (H2H, Categories, Rotisserie).

## Core Architecture
- **Frontend**: React 19 + TailwindCSS + Shadcn/UI
- **Backend**: FastAPI + Motor (async MongoDB)
- **Database**: MongoDB
- **Real-time**: Socket.IO for live scoring

## What's Been Implemented

### Phase 1 - Core Platform (Complete)
- User auth (JWT), league creation, team management
- NHL roster sync, player search, draft room
- Trade system, waivers, free agency
- Live scoring worker polling NHL API

### Phase 2 - Admin & Commissioner (Complete)
- Admin dashboard with sandbox simulation tools
- Setup Wizard: divisions, schedule calculator, playoff optionality, team limits

### Phase 3 - Rotisserie Scoring (Complete)
- Categories config, ranks, tiebreak rules, Condensed Rotisserie
- Fresh Playoff Totals, Season completion champion declaration

### Phase 4 - Daily Scoring (Complete - Sep 22, 2026)
- `GET /api/matchups/{league_id}/daily-scoring` endpoint
- Matchup/Roster/Live Scoring pages: Day Pill Strip, Daily Grid, PlayerDailyAccordion
- Player Card Modal: Daily Scoring side menu

### Phase 5 - Weekly Review, Hot Streaks & Bracket Polish (Complete - Sep 26, 2026)
- Week Selector dropdown on all daily scoring views
- Hot Streak Badges (fire icon for 3+ consecutive above-avg days)
- Enhanced bracket TeamCard with logos, W-L-T, PF, GB

### Phase 6 - Trade & Draft Bug Fixes (Complete - Sep 26, 2026)
- Midnight UTC-8 processing for trades
- Configurable trade_review_period_days (0-7)
- Traded picks honored in draft auto-pick + manual pick
- Sandbox login fix (UserLogin accepts .local emails)

### Phase 7 - Private League API Security (Complete - Sep 28, 2026)
- **Created**: `/app/backend/routes/league_guards.py` — centralized `require_league_member()` and `verify_team_in_league()` guards
- **21 endpoints protected** across 7 route files:
  - `leagues.py`: get_league, get_standings, get_divisions, get_schedule_config, get_playoff_bracket, roster-limits, lock-status, premium-status, veto-threshold-preview, emergency-swap-budget
  - `scoring.py`: get_scoring_config, calculate_league_scoring, calculate_roto_standings
  - `roto.py`: roto_catalog, roto_standings, roto_matchup, roto_recompute
  - `matchups.py`: get_matchups, get_current_week, get_daily_scoring, get_week_results
  - `live_scoring.py`: get_team_live_scoring, get_league_live_scoring, get_team_week_summary
  - `lineup.py`: get_team_lineup, get_team_compliance
  - `draft_inspection.py`: get_team_draft_picks
- **Guards enforce**:
  - Authentication required (401 for unauthenticated)
  - League membership required (403 for non-members)
  - Team-league cross-validation (404 for mismatched IDs)
  - Handles mixed ObjectId/str commissioner_id comparison

### Phase 8 - Historical Scoring Allocation Fix (Complete - Sep 28, 2026)
- **Problem**: Trades, drops, pickups and lineup changes retroactively reassigned historical stats. Recalculation changed earlier standings.
- **Solution**: Introduced `scoring_rosters` collection (per-team, per-week locked roster snapshots) and `roster_change_log` (append-only ledger of all roster mutations)
- **New module**: `/app/backend/utils/scoring_roster.py` — `log_roster_change()`, `ensure_scoring_roster()`, `get_scoring_roster()`, `lock_league_week()`
- **5 scoring paths updated** to use `get_scoring_roster()` instead of `team.get("roster")`:
  - `scoring.py`: calculate_league_scoring, calculate_roto_standings
  - `matchups.py`: calc_team_score (simulate_week), get_daily_scoring
  - `roto.py`: _team_stat_totals
  - `live_scoring_worker.py`: _recompute_team_live_totals
  - `live_scoring.py`: get_team_live_scoring
- **4 roster mutation points instrumented** with `log_roster_change()`:
  - `trades.py`: trade execution (both sides logged)
  - `roster.py`: add player, drop player
  - `draft_pick_actions.py`: draft pick
- **Admin endpoint**: `POST /api/admin/lock-scoring-rosters` for manual week locking
- **Auto-lock**: simulate_week auto-locks all teams at matchup start
- **Fallback**: When no snapshot exists, falls back to live roster (backward-compatible)

## Key Files
- `/app/backend/utils/scoring_roster.py` — Historical scoring roster module
- `/app/backend/routes/league_guards.py` — Security guards
- `/app/backend/routes/leagues.py` — League endpoints
- `/app/backend/routes/scoring.py` — Scoring endpoints
- `/app/backend/routes/roto.py` — Rotisserie endpoints
- `/app/backend/routes/matchups.py` — Matchup + daily scoring endpoints
- `/app/backend/routes/live_scoring.py` — Live scoring endpoints
- `/app/backend/routes/lineup.py` — Lineup + compliance endpoints
- `/app/backend/routes/draft_inspection.py` — Draft read-only endpoints
- `/app/backend/routes/trades.py` — Trade execution, review period
- `/app/backend/routes/draft_helpers.py` — Auto-pick with traded pick support
- `/app/frontend/src/components/daily-scoring/` — Daily scoring components
- `/app/frontend/src/lovable/pages/PlayoffBracket.tsx` — Bracket visualizer

## Known Issues
- GET /api/teams (without league_id) returns 500 due to pre-existing ObjectId serialization bug in team_to_response (LOW priority)

## Backlog / Upcoming
- P2: UX polish on Drag-and-Drop Division step
- P2: Refactor `PlayoffsScheduleCards.tsx` (1150+ lines)
- P3: Trade Review Settings UI for commissioners
- P3: Additional scoring format enhancements
