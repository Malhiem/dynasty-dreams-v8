# Dynasty Dreams - PRD

## Original Problem Statement
Build Dynasty Dreams, a robust NHL fantasy sports platform. Features include: multiple league formats (Redraft, Keeper, Dynasty, Best Ball), scoring formats (H2H, Total Points, Rotisserie, Guillotine, All-Play), salary cap/contract management, rookie drafts with custom admin-created drafts, real-time updates via websockets, payment processing (league fees + premium subscriptions), and push notifications. Responsive web design. Mobile app to follow.

## Architecture
- **Frontend**: React 19, Tailwind CSS, Radix UI (shadcn), Phosphor Icons, Socket.IO client
- **Backend**: FastAPI, Motor (async MongoDB), python-socketio, nhlpy (NHL API), Stripe (emergentintegrations)
- **Database**: MongoDB
- **NHL Data**: nhlpy library pulling from official NHL Stats API
- **User's Lovable Frontend**: Vite+React+TypeScript app at github.com/Malhiem/dynasty-dreams (private repo)

## User Personas
1. **Fantasy Manager** - Creates teams, drafts players, manages rosters
2. **League Commissioner** - Creates/configures leagues, manages drafts, sets rules
3. **Admin** - Platform management, user oversight

## Core Requirements (Static)
- JWT authentication with httpOnly cookies
- League CRUD with multiple formats and scoring
- Team management within leagues
- NHL player database with real stats
- Draft system (snake, linear, auction, custom)
- Salary cap/contract management
- Stripe payments (subscriptions + league fees)
- WebSocket real-time updates
- Responsive design

## What's Been Implemented (April 2026)

### Phase 1: Core Platform
- User auth (register, login, logout, refresh, forgot/reset password, brute force protection)
- Admin seeding with configurable credentials
- League creation with all 5 formats and 5 scoring types
- Team creation/joining within leagues
- **NHL Player Data**: 1,038 real players (940 skaters + 98 goalies) from all 32 NHL teams
- Players page with search, position filter, pagination
- Standings system
- Stripe checkout integration (subscriptions + league fees)
- WebSocket infrastructure (rooms, join/leave, broadcast)
- Full responsive UI: Landing, Login, Register, Dashboard, Leagues, Create League, League Detail, Players, Drafts

### Phase 2: Draft Engine Backend (NEW)
- **Draft CRUD**: Create drafts with full config (type, rounds, timer, snake, criteria)
- **Draft Lifecycle**: scheduled → active → paused → completed
- **Draft Board**: 2D grid generation respecting snake draft ordering
- **Pick Engine**: Validates turn order, prevents duplicate picks, auto-advances
- **Eligible Players**: Filters out already-drafted players, search/position filter
- **Draft Chat**: Real-time chat with system messages for picks
- **Timer Control**: Pause/resume with commissioner-only access
- **Config Updates**: Live config changes broadcast via WebSocket
- **WebSocket Events**: draft_started, draft_pick, draft_chat, draft_timer_toggle, draft_config_updated, draft_completed
- **Commissioner Controls**: Only commissioner can start/pause/configure drafts
- **Testing**: 65/66 tests passed (98.5%)

### Draft API Endpoints
- `POST /api/drafts` - Create draft
- `GET /api/drafts` - List drafts (filter by league_id)
- `GET /api/drafts/{id}` - Get draft details
- `POST /api/drafts/{id}/start` - Start draft (early_start param)
- `GET /api/drafts/{id}/board` - Get draft board grid
- `GET /api/drafts/{id}/eligible-players` - Available players with search/filter
- `POST /api/drafts/{id}/pick` - Make a pick
- `POST /api/drafts/{id}/pause` - Toggle timer
- `POST /api/drafts/{id}/chat` - Send chat
- `GET /api/drafts/{id}/chat` - Get chat history
- `PUT /api/drafts/{id}/config` - Update settings

## Prioritized Backlog

### P0 (Critical - Next)
- Port DraftRoom.tsx from Lovable frontend to CRA frontend (connect to real APIs)
- Trade center (propose, accept, reject, veto)
- Waiver wire system

### P1 (High)
- Roster management UI (set lineup, drop players)
- Weekly matchup/scoring engine
- Commissioner tools panel
- Player detail page with full stats

### P2 (Medium)
- Salary cap management UI
- Auction draft UI
- Season schedule generation
- Draft Board page (pick ownership tracking)
- Draft Lottery page

### P3 (Low/Future)
- Multi-sport expansion (NBA, MLB, NFL)
- Mobile app (React Native)
- Social features (chat, forums)
- Keeper/Dynasty keeper selection UI
- League history/archives

## Next Tasks
1. Port DraftRoom.tsx to CRA and wire to backend APIs + WebSocket
2. Create trade center with proposal/acceptance flow
3. Add waiver wire system
4. Build roster management with lineup setting
