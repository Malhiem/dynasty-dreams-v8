# Dynasty Dreams - PRD

## Original Problem Statement
Build Dynasty Dreams, a robust NHL fantasy sports platform with multiple league formats, scoring types, salary cap, drafts, trades, waivers, payments, real-time updates, and responsive design.

## Architecture
- **Frontend**: React 19 (CRA), Tailwind CSS, Radix UI (shadcn), Lucide + Phosphor icons
- **Backend**: FastAPI, Motor (async MongoDB), python-socketio, nhlpy, Stripe
- **Database**: MongoDB (14 collections)
- **Sidebar Layout**: Ported from Lovable (Vite/TS) to CRA (JS)

## What's Been Implemented (April 2026)

### Phase 1: Core Platform
- JWT auth, brute force protection, admin seeding
- League CRUD (5 formats, 5 scoring), Team management
- 1,038 NHL players (32 teams, 2025-2026 via nhlpy)
- Stripe payments, WebSocket infrastructure

### Phase 2: Draft Engine (11 endpoints)
- Create/start/pause/pick/board/eligible-players/chat/config
- Snake draft, turn validation, real-time broadcasting

### Phase 3: Trade Center + Waiver Wire (19 endpoints)
- Trade block, proposals, accept/reject/withdraw/vote, FAAB bidding

### Phase 4: Frontend Port + Roster + Scoring
- Sidebar layout (4 groups: Main/Social/Management/Draft)
- DraftRoom, TradeBlock, Waivers, Transactions pages
- Roster management (add/drop), Configurable scoring engine

### Phase 5: Matchup Engine + Sidebar Migration (Current)
- **Weekly Matchup Engine**: Round-robin schedule generation, weekly simulation using roster fantasy points, W/L/T updates, supports H2H/All-Play/Guillotine
- **Sidebar Migration**: All pages now use consistent AppLayout sidebar
- **Standings Page**: League standings + weekly matchups + commissioner controls (generate schedule, simulate week, week navigation)

### Testing Summary (Cumulative)
- Phase 1: 27/27 | Phase 2: 65/66 | Phase 3: 121/122 | Phase 4: 24/24 | Phase 5: 14/14
- Frontend: 100% across all iterations

## Total API Endpoints: 50+
Auth(7), Leagues(4), Teams(3), Players(2), Drafts(11), TradeBlock(3), Trades(6), Waivers(8), Roster(3), Scoring(4), Matchups(5), Payments(3), Standings(1)

## Pages (12 total)
Landing, Login, Register, Dashboard, Leagues, CreateLeague, LeagueDetail, Players, Drafts, DraftRoom, TradeBlock, Transactions, Waivers, Roster, Scoring, Standings

## Prioritized Backlog
### P0: Real-time WebSocket on frontend (replace polling)
### P1: Commissioner tools panel, Player detail page
### P2: Salary cap UI, Auction draft, Mobile app (React Native)
### P3: Multi-sport expansion, Trade analyzer, League chat
