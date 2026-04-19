# Dynasty Dreams - PRD

## Original Problem Statement
Build Dynasty Dreams, a robust NHL fantasy sports platform with multiple league formats, scoring types, salary cap, drafts, trades, waivers, payments, real-time updates, and responsive design.

## Architecture
- **Frontend**: React 19 (CRA), Tailwind CSS, Radix UI (shadcn), Lucide icons, Socket.IO client
- **Backend**: FastAPI, Motor (async MongoDB), python-socketio, nhlpy, Stripe (emergentintegrations)
- **Database**: MongoDB (13 collections)
- **Lovable Frontend**: Ported sidebar layout, DraftRoom, TradeBlock, Waivers, Transactions from user's Vite/TS app

## What's Been Implemented (April 2026)

### Phase 1: Core Platform
- JWT auth, brute force protection, admin seeding
- League CRUD (5 formats, 5 scoring), Team management, Standings
- 1,038 NHL players (32 teams, 2025-2026 season via nhlpy)
- Stripe payments, WebSocket infrastructure
- Landing, Login, Register pages

### Phase 2: Draft Engine (11 endpoints)
- Create/start/pause/pick/board/eligible-players/chat/config
- Snake draft ordering, turn validation, real-time broadcasting

### Phase 3: Trade Center + Waiver Wire (19 endpoints)
- Trade block, proposals, accept/reject/withdraw/vote
- FAAB bidding, claims, processing, waiver order

### Phase 4: Frontend Port + Roster + Scoring (Current)
- **Sidebar Layout**: Ported Lovable AppSidebar + AppLayout with collapsible sidebar
  - Main: Dashboard, Roster, Standings, Transactions
  - Social: Trade Block, Players
  - Management: Scoring, Waivers, Analytics
  - Draft: Draft Board, Draft Room
- **Ported Pages**: DraftRoom (live picks/chat/board), TradeBlock (add/remove/filter), Waivers (FAAB/claims/history), Transactions (pending/accepted/vote)
- **Roster Management**: Add/drop players with validation (ownership, limits, duplicates)
- **Scoring Engine**: Configurable points-based (skater + goalie) AND rotisserie standings
  - Default: G=3, A=2, +/-=1, PIM=-0.5, PPG=1, PPP=0.5, SHG=2, SHP=1, GWG=1, SOG=0.5
  - Goalie: W=5, L=-2, SV=0.2, GA=-1, SO=3
  - Roto: 10 categories configurable via admin

### Testing Summary
- Phase 1: 27/27 (100%)
- Phase 2: 65/66 (98.5%)
- Phase 3: 121/122 (99.2%)
- Phase 4: 24/24 backend + 100% frontend (100%)

## Total API Endpoints: 45+
Auth (7), Leagues (4), Teams (3), Players (2), Drafts (11), Trade Block (3), Trades (6), Waivers (8), Roster (3), Scoring (4), Payments (3), Standings (1)

## Prioritized Backlog

### P0 (Next)
- Migrate Dashboard/Leagues/Players/Drafts pages to sidebar layout
- Real-time WebSocket integration on frontend (currently polling)

### P1
- Weekly matchup simulation engine
- Commissioner tools panel
- Player detail page with full stats

### P2
- Salary cap management UI
- Auction draft UI
- Mobile app (React Native)

### P3
- Multi-sport expansion (NBA, MLB, NFL)
- Trade analyzer (dynasty value calculation)
- Social features (league chat)
