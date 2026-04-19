# Dynasty Dreams - PRD

## Original Problem Statement
Build Dynasty Dreams, a robust NHL fantasy sports platform with multiple league formats, scoring types, salary cap, drafts, trades, waivers, payments, real-time updates, and responsive design.

## Architecture
- **Frontend**: React 19, Tailwind CSS, Radix UI (shadcn), Phosphor Icons, Socket.IO client
- **Backend**: FastAPI, Motor (async MongoDB), python-socketio, nhlpy, Stripe (emergentintegrations)
- **Database**: MongoDB (collections: users, leagues, teams, players, drafts, trades, trade_block, waiver_claims, waiver_budgets, payment_transactions)
- **User's Lovable Frontend**: Vite+React+TypeScript at github.com/Malhiem/dynasty-dreams

## What's Been Implemented (April 2026)

### Phase 1: Core Platform (Complete)
- JWT auth with httpOnly cookies, brute force protection, admin seeding
- League CRUD (5 formats, 5 scoring types), Team management, Standings
- NHL Player Data: 1,038 real players from all 32 teams (2025-2026 season via nhlpy)
- Stripe payments (subscriptions + league fees)
- WebSocket infrastructure
- Responsive UI: Landing, Login, Register, Dashboard, Leagues, Players, Drafts

### Phase 2: Draft Engine (Complete)
- 11 API endpoints: create, list, get, start, board, eligible-players, pick, pause, chat, chat-history, config
- Snake draft ordering, turn validation, duplicate pick prevention
- Real-time WebSocket broadcasting for all draft events
- Testing: 65/66 passed

### Phase 3: Trade Center (Complete - NEW)
**Trade Block:**
- POST /api/trade-block - Add player/pick to trade block
- GET /api/trade-block - List all trade block items
- DELETE /api/trade-block/{id} - Remove item (validates ownership)
- Duplicate prevention

**Trade Proposals:**
- POST /api/trades - Create proposal with assets offered/requested
- GET /api/trades - List trades (filter: league_id, status, my_trades)
- GET /api/trades/{id} - Trade details with full asset info
- POST /api/trades/{id}/accept - Target team accepts
- POST /api/trades/{id}/reject - Target team rejects
- POST /api/trades/{id}/withdraw - Proposer withdraws
- POST /api/trades/{id}/vote - League members vote (approve/veto, duplicate prevention)
- 72-hour review period, veto threshold at >50% of league
- WebSocket: trade_proposed, trade_accepted, trade_vetoed

### Phase 4: Waiver Wire (Complete - NEW)
**FAAB Bidding:**
- GET /api/waivers/available - Available players with search/position filter
- POST /api/waivers/claim - Place FAAB bid (validates budget, prevents duplicates)
- GET /api/waivers/claims - List claims (filter: league_id, my_claims, status)
- DELETE /api/waivers/claims/{id} - Cancel pending claim
- GET /api/waivers/budget - FAAB budget tracking ($100 default, auto-init)
- GET /api/waivers/order - Waiver priority (inverse standings)
- GET /api/waivers/history - Processed claim history
- POST /api/waivers/process - Commissioner processes (highest bid wins, FAAB deducted)
- WebSocket: waivers_processed

### Testing Summary
- Phase 1: 27/27 (100%)
- Phase 2: 38/38 + 27 existing = 65/66 (98.5%)
- Phase 3+4: 56/56 + 65 existing = 121/122 (99.2%)

## Prioritized Backlog

### P0 (Next)
- Port Lovable frontend components to CRA (DraftRoom, TradeBlock, Waivers, Transactions)
- Roster management UI (set lineup, drop players)

### P1 (High)
- Weekly matchup/scoring engine
- Commissioner tools panel
- Player detail page with full stats

### P2 (Medium)
- Salary cap management UI
- Auction draft UI
- Draft Board page (pick ownership)
- Draft Lottery page

### P3 (Future)
- Multi-sport expansion
- Mobile app (React Native)
- Social features
