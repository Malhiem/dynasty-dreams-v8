# Dynasty Dreams - PRD

## Platform Summary
Multi-sport dynasty fantasy sports platform (NHL active; NFL/NBA/MLB sport-agnostic models ready). Web + React Native mobile, real-time draft room, trade center, waiver wire, matchup simulation, salary cap, commissioner tools, shareable invites (link + QR + SendGrid email).

## Implementation Phases (Apr 2026)

| Phase | Features | Tests |
|-------|----------|-------|
| 1 | Auth, Leagues, Teams, 1,038 NHL Players, Stripe, WebSocket | 27/27 |
| 2 | Draft Engine (snake), 11 endpoints | 65/66 |
| 3 | Trade Center + FAAB Waiver Wire, 19 endpoints | 121/122 |
| 4 | Sidebar Layout Port, Roster, Configurable Scoring | 24/24 |
| 5 | Matchup Simulation Engine, Sidebar Migration | 14/14 |
| 6 | WebSocket hooks, Commissioner Tools, Player Detail | 26/26 |
| 7 | Push Notifications, Auction Draft with live bidding | 20/20 |
| 8 | Dynasty Salary Cap (contracts/AAV/NTC/NMC), Activity Feed, RN scaffold | 22/22 |
| 9 | League Invite (links+QR+email), Sport-Agnostic Model, 15 RN screens with API | 18/18 |
| 10 | 5 Demo Leagues Seed + SendGrid Integration (graceful mock fallback) + RN bundle verify | 13/13 |
| 11 | League Premium Stripe Unlock + Personalized Recommendations + Payment pages | 16/16 |
| 12 | Full-fill 86 teams + auto-draft + NHL live scoring worker + /live page & dashboard widget | 14/14 |

## Key Stats
- **65+ REST API endpoints**
- **20 web pages** (React/CRA + sidebar layout)
- **15 mobile screens** (React Native + Expo, 878 modules bundled successfully)
- **17 MongoDB collections**
- **4 sports configured** (NHL active; NFL/NBA/MLB ready)
- **5 demo leagues seeded** across every fantasy format (H2H, Roto, Dynasty, Keeper, Best Ball)
- **League invite system**: shareable link + QR code + SendGrid email (falls back to mock when key missing)

## Demo Leagues (Apr 19, 2026 — filled Apr 20)
| Name | Format | Scoring | Teams | Fee |
|------|--------|---------|-------|-----|
| Ice Kings Head-to-Head | redraft | head_to_head | 12/12 | $50 |
| Stat Chasers Roto | redraft | rotisserie | 14/14 | $25 |
| Frozen Dynasty | dynasty | head_to_head | 16/16 | $100 |
| Perennial Keepers | keeper | head_to_head | 12/12 | $75 |
| Set-and-Forget Best Ball | best_ball | total_points | 32/32 | $20 |

All 86 teams have auto-drafted 20–28-player rosters. Demo owner password: `Demo2026!`

## Live NHL Scoring (Phase 12)
- Backend polling worker `live_scoring_worker.py` — runs every 60s against `nhlpy` `daily_schedule()` + `boxscore()`; falls back to previous-day games on off-days
- Per-player live_stats stored in `players.live_stats.{game_id}`; per-team totals at `teams.live_points`
- Endpoints: `GET /api/live-scoring`, `POST /api/live-scoring/refresh` (20s user cooldown), `GET /api/live-scoring/team/{id}`, `GET /api/live-scoring/league/{id}`
- Socket.IO `live_scoring_update` event broadcast after each poll → frontend auto-refreshes without reload
- UI: `/live` page (NHL games grid + fantasy leaderboard + top-team roster tab) and Dashboard `<LiveScoringWidget />`
- Playoff awareness: `is_playoff` flag set when `gameType == 3`; UI surfaces an amber "PLAYOFFS" badge + ON AIR pulse

## Current Integrations
- **NHL API** (`nhlpy`) — active, 1,038 players
- **SendGrid** — installed; configured with `SENDGRID_API_KEY` + `SENDER_EMAIL` env vars. **Mock fallback** triggers automatically when key is empty/missing
- **Stripe** — `emergentintegrations` SDK; test key `sk_test_emergent` configured

## MOCKED (Still)
- **SendGrid email dispatch** → mock path (status="mocked") when `SENDGRID_API_KEY` is empty. Add the key to `/app/backend/.env` to enable real delivery.

## Backlog
- **P0**: NFL player data ingestion script (sport-agnostic model ready)
- **P1**: Gate premium-only commissioner actions (draft scheduling, multi-year contracts, taxi squad, custom scoring, webhooks) server-side once league.premium=true
- **P1**: Real SendGrid key + sender domain verification to flip mock → real delivery
- **P1**: Trade value analyzer, player projections
- **P2**: Refactor `server.py` (3350+ lines) → modular FastAPI routers (auth, leagues, drafts, trades, players, payments, recommendations)
- **P2**: Compound unique index on `league_invites(league_id, email)`
- **P2**: Switch `EmailInviteRequest.emails` to `list[EmailStr]`
- **P2**: EAS Build for iOS/Android distribution

## Architecture
```
/app/
├── backend/
│   ├── server.py              # FastAPI + WebSocket hub (3180 lines — refactor pending)
│   ├── draft_engine.py        # Snake + Auction draft
│   ├── trade_waiver_engine.py # Trades, waivers, FAAB
│   ├── seed_nhl_data.py       # NHL player ingestion
│   ├── seed_demo_leagues.py   # NEW: 5-format demo league seeder
│   └── tests/                 # pytest regression suite
├── frontend/                  # React (CRA) + Tailwind + shadcn/ui
├── mobile/                    # React Native + Expo (app.json, jsEngine=jsc for bundling)
└── memory/                    # PRD, test_credentials
```
