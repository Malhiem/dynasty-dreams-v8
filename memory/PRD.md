# Dynasty Dreams - PRD

## Original Problem Statement
Build Dynasty Dreams, a robust NHL fantasy sports platform. Features include: multiple league formats (Redraft, Keeper, Dynasty, Best Ball), scoring formats (H2H, Total Points, Rotisserie, Guillotine, All-Play), salary cap/contract management, rookie drafts with custom admin-created drafts, real-time updates via websockets, payment processing (league fees + premium subscriptions), and push notifications. Responsive web design. Mobile app to follow.

## Architecture
- **Frontend**: React 19, Tailwind CSS, Radix UI (shadcn), Phosphor Icons, Socket.IO client
- **Backend**: FastAPI, Motor (async MongoDB), python-socketio, nhlpy (NHL API), Stripe (emergentintegrations)
- **Database**: MongoDB
- **NHL Data**: nhlpy library pulling from official NHL Stats API

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
- User auth (register, login, logout, refresh, forgot/reset password, brute force protection)
- Admin seeding with configurable credentials
- League creation with all 5 formats and 5 scoring types
- Team creation/joining within leagues
- **NHL Player Data**: 1,038 real players (940 skaters + 98 goalies) from all 32 NHL teams, seeded from official NHL API for 2025-2026 season
- Players page with search, position filter, pagination
- Standings system
- Draft CRUD and start/pick endpoints
- Stripe checkout integration (subscriptions + league fees)
- WebSocket infrastructure (rooms, join/leave, broadcast)
- Full responsive UI: Landing, Login, Register, Dashboard, Leagues, Create League, League Detail, Players, Drafts
- Testing: 27/27 backend tests pass, 95% frontend coverage

## Prioritized Backlog
### P0 (Critical)
- Live draft room UI with real-time WebSocket picks
- Trade center (propose, accept, reject, veto)
- Waiver wire system

### P1 (High)
- Roster management UI (set lineup, drop players)
- Weekly matchup/scoring engine
- Push notifications (browser)
- Commissioner tools panel
- Player detail page with full stats

### P2 (Medium)
- Salary cap management UI
- Contract creation/editing
- Auction draft UI
- Season schedule generation
- Mobile app (React Native)

### P3 (Low/Future)
- Multi-sport expansion (NBA, MLB, NFL)
- Advanced analytics/projections
- Social features (chat, forums)
- Keeper/Dynasty keeper selection UI
- League history/archives

## Next Tasks
1. Build live draft room with WebSocket integration
2. Create trade center with proposal/acceptance flow
3. Add waiver wire system
4. Build roster management with lineup setting
