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
- Dry-run NHL API sync
- Sandbox: auto-advance playoffs, roll to next season, bulk contract sign, PDF season recap, seed random stats
- Setup Wizard: divisions, smart schedule calculator, playoff optionality, team limits (32/100)

### Phase 3 - Rotisserie Scoring (Complete)
- Categories config, explicit category ranks in standings
- Tiebreak rules
- Roto Playoff configurations (Condensed Rotisserie)
- Fresh Playoff Totals (only aggregate playoff period stats)
- Season completion champion declaration (respects playoff config)

### Phase 4 - Daily Scoring Feature (Complete - Sep 22, 2026)
- **Backend**: `GET /api/matchups/{league_id}/daily-scoring` endpoint
  - Returns per-day fantasy point breakdowns for a team within a matchup period
  - Groups `live_stats` entries by game date, calculates daily FPTS
  - Works for all scoring formats (H2H, Categories, Rotisserie)
- **Matchup Page**: 3 view tabs — Matchup Totals, Daily Scores (Day Pill Strip), Daily Grid
- **Roster/Team Page**: New "Daily Scoring" tab with DayPillStrip + DailyGrid
- **Live Scoring Page**: New "Daily Scoring" tab in Fantasy Leaderboard
- **Player Card Modal**: New "Daily Scoring" side menu with expandable accordion

### Phase 5 - Weekly Review, Hot Streaks, Bracket Polish & Trade Fixes (Complete - Sep 26, 2026)

#### New Features:
- **Week Selector Dropdown**: Added to Matchup, Roster, and Live Scoring daily scoring views. Allows reviewing any past matchup period (not just current week). Shows "• Current" label for the active week. Resets day selection when changing weeks.
- **Hot Streak Badges**: Fire icon (🔥) appears next to players who scored above average on 3+ consecutive days in the DailyGrid. Orange for 3-4 day streaks, pulsing red for 5+ day streaks. Tooltip shows streak length.
- **Bracket Visualizer Cleanup**: Enhanced TeamCard with better layout — team logo, abbreviation, W-L-T record, Points For, Games Back all visible. Improved spacing and visual hierarchy.

#### Bug Fixes:
- **Trade Review Period Enforcement**: Non-commissioner users now receive 403 error when attempting to execute a trade still in its review period. Error message shows remaining time and suggests commissioner override. Only commissioners can push trades through early.
- **Configurable Trade Review Period**: `trade_review_period_days` (0–7 days in 1-day increments) added to league settings. Falls back to legacy `trade_review_period_hours`. Default: 1 day (24h).
- **Traded Picks Honored in Draft**: Both auto-pick (`perform_one_auto_pick`) and manual pick now check the `draft_picks` collection for `current_team_id` to honor traded picks. Previously, picks were always awarded to the original owner from `team_abbrs`.

## Key Files
- `/app/backend/routes/matchups.py` — daily-scoring endpoint + schedule/bracket logic
- `/app/backend/routes/trades.py` — Trade execution with review period enforcement
- `/app/backend/routes/draft_helpers.py` — Auto-pick with traded pick support
- `/app/backend/routes/draft_pick_actions.py` — Manual pick with traded pick support
- `/app/backend/routes/roto.py` — Roto standings, fresh totals
- `/app/backend/routes/leagues.py` — League config including trade_review_period_days
- `/app/frontend/src/hooks/use-daily-scoring.ts` — Daily scoring React hook
- `/app/frontend/src/components/daily-scoring/` — DayPillStrip, DailyGrid, PlayerDailyAccordion, WeekSelector
- `/app/frontend/src/lovable/pages/Matchup.tsx` — Matchup page with 3 view tabs + week selector
- `/app/frontend/src/lovable/pages/Team.tsx` — Roster page with Daily Scoring tab + week selector
- `/app/frontend/src/pages/LiveScoringPage.jsx` — Live scoring with Daily Scoring tab + week selector
- `/app/frontend/src/lovable/pages/PlayoffBracket.tsx` — Enhanced bracket TeamCard

## Backlog / Upcoming
- P2: UX polish on Drag-and-Drop Division step
- P2: Refactor `PlayoffsScheduleCards.tsx` (1150+ lines → split into smaller components)
- P3: Additional scoring format enhancements
