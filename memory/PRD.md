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
  - Day Pill Strip: horizontal day pills (Mon-Sun) with daily totals, "Total" pill for period aggregate
  - Daily Grid: full grid with players as rows, days as columns, color-coded FPTS cells
  - Both views show my team vs opponent comparison
- **Roster/Team Page**: New "Daily Scoring" tab between Roster and Franchise Trophy Room
  - DayPillStrip + DailyGrid showing per-day player performance
  - Day filtering: clicking a day pill shows only that day's players and stats
- **Live Scoring Page**: New "Daily Scoring" tab in Fantasy Leaderboard
  - DayPillStrip + DailyGrid + day-specific player table
- **Player Card Modal**: New "Daily Scoring" side menu with expandable day-by-day breakdown
  - PlayerDailyAccordion component: mini table with date | stat line | FPTS
  - Summary cards: Total FPTS, Games, FPTS/Game
  - Period stat line (G/A/SOG for skaters, W/SVS/GA for goalies)

## Key Files
- `/app/backend/routes/matchups.py` — daily-scoring endpoint + schedule/bracket logic
- `/app/backend/routes/roto.py` — Roto standings, fresh totals
- `/app/backend/routes/seasons.py` — Champion declaration
- `/app/frontend/src/hooks/use-daily-scoring.ts` — Daily scoring React hook
- `/app/frontend/src/components/daily-scoring/` — DayPillStrip, DailyGrid, PlayerDailyAccordion
- `/app/frontend/src/lovable/pages/Matchup.tsx` — Matchup page with 3 view tabs
- `/app/frontend/src/lovable/pages/Team.tsx` — Roster page with Daily Scoring tab
- `/app/frontend/src/pages/LiveScoringPage.jsx` — Live scoring with Daily Scoring tab
- `/app/frontend/src/lovable/components/dashboard/PlayerCardModal.tsx` — Player card with Daily Scoring tab

## Backlog / Upcoming
- P2: UX polish on Drag-and-Drop Division step and Bracket Visualizer
- P2: Refactor `PlayoffsScheduleCards.tsx` (1150+ lines → split into smaller components)
- P3: Additional scoring format enhancements
