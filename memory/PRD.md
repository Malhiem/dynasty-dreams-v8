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
- Tiebreak rules, Roto Playoff configurations (Condensed Rotisserie)
- Fresh Playoff Totals, Season completion champion declaration

### Phase 4 - Daily Scoring Feature (Complete - Sep 22, 2026)
- `GET /api/matchups/{league_id}/daily-scoring` endpoint
- Matchup Page: 3 view tabs — Matchup Totals, Daily Scores (Day Pill Strip), Daily Grid
- Roster/Team Page: "Daily Scoring" tab with DayPillStrip + DailyGrid
- Live Scoring Page: "Daily Scoring" tab in Fantasy Leaderboard
- Player Card Modal: "Daily Scoring" side menu with expandable accordion

### Phase 5 - Weekly Review, Hot Streaks & Bracket Polish (Complete - Sep 26, 2026)
- **Week Selector Dropdown**: Added to Matchup, Roster, and Live Scoring daily scoring views
- **Hot Streak Badges**: Fire icon for players scoring above average 3+ consecutive days
- **Bracket Visualizer Cleanup**: Enhanced TeamCard with logos, W-L-T records, PF, GB

### Phase 6 - Trade & Draft Bug Fixes (Complete - Sep 26, 2026)
- **Midnight Processing**: Trade `processes_at` now scheduled at midnight UTC-8 after review period
- **Trade Review Period**: Configurable `trade_review_period_days` (0–7 days) in league settings
  - Only commissioners can execute trades during review period
- **Traded Picks in Draft**: Auto-pick and manual pick query `draft_picks` by `(round, original_team_id)` to find `current_team_id`
- **Sandbox Login**: `UserLogin.email` changed from `EmailStr` to `str` for `@sandbox.local` support
- **Lint fixes**: Added missing `Shield` import, added `sectionTimeframe`/`getPlayerPoints` props to `FantasyPointsTable`, `MatchupScheduleTable`, `FullScheduleTable`

## Key Files
- `/app/backend/routes/trades.py` — Trade execution, review period, midnight processing
- `/app/backend/routes/draft_helpers.py` — Auto-pick with traded pick support
- `/app/backend/routes/draft_pick_actions.py` — Manual pick with traded pick support
- `/app/backend/routes/matchups.py` — Daily-scoring endpoint + schedule/bracket logic
- `/app/backend/routes/leagues.py` — League config including trade_review_period_days
- `/app/backend/server.py` — UserLogin model (str email for sandbox support)
- `/app/frontend/src/components/daily-scoring/` — DayPillStrip, DailyGrid, PlayerDailyAccordion, WeekSelector
- `/app/frontend/src/lovable/pages/Matchup.tsx` — Matchup page with 3 view tabs + week selector
- `/app/frontend/src/lovable/pages/Team.tsx` — Roster page with Daily Scoring tab + week selector
- `/app/frontend/src/pages/LiveScoringPage.jsx` — Live scoring with Daily Scoring tab + week selector
- `/app/frontend/src/lovable/pages/PlayoffBracket.tsx` — Enhanced bracket TeamCard
- `/app/frontend/src/lovable/components/dashboard/player-roster/sub-components.tsx` — Roster table components

## Backlog / Upcoming
- P2: UX polish on Drag-and-Drop Division step
- P2: Refactor `PlayoffsScheduleCards.tsx` (1150+ lines → split)
- P3: Additional scoring format enhancements
- P3: Trade Review UI — commissioner settings panel for configuring review period
