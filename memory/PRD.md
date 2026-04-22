# Dynasty Dreams - PRD

## Platform Summary
Multi-sport dynasty fantasy sports platform (NHL active; NFL/NBA/MLB sport-agnostic models ready). Web + React Native mobile, real-time draft room, trade center, waiver wire, matchup simulation, salary cap, commissioner tools, shareable invites (link + QR + SendGrid email).

## Implementation Phases (Apr 2026)

| Phase | Features | Tests |
|-------|----------|-------|
| 1-9 | Platform foundation (see CHANGELOG) | 100% |
| 10 | 5 Demo Leagues Seed + SendGrid (mock fallback) + RN bundle verify | 13/13 |
| 11 | League Premium Stripe Unlock + Personalized Recommendations + Payment pages | 16/16 |
| 12 | Full-fill 86 teams + auto-draft + NHL live scoring worker + /live page & widget | 14/14 |
| 13 | My Week at a Glance + Fantasy Level system + clickable leagues/teams + TeamDetailPage | 14/14 + 16/16 |
| 14-16 | **Lovable UI wiring: Team/Roster + Matchup + Standings** bound to live APIs | 7/7 backend + 3/3 pages |
| 17 | **Lovable UI wiring: SalaryCap + Transactions + TradeBlock + Waivers + DraftBoard + Analytics** + TypeScript cleanup (removed TSC_COMPILE_ON_ERROR bypass, clean compile) | 14/14 backend + 6/6 pages |
| 18 | **Sidebar restructure** (User / League Hub / Social / Management / Draft groups) + Renamed Scoring→**League Information**, Commissioner→**League Administration**. Added **League Constitution tab** (5000-char editor, commissioner + co-commissioner permissions, audit log entry on save). **Grey Last-5 dots** for 0-game teams. New **My Matchup H2H card** on /live page | 14/14 backend + full frontend regression, 0 issues |

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
- **P1**: Persist draft-pick ownership / pick trades in DB so DraftBoard.tsx pick matrix can show real team abbrs (currently uses seeded fallback with generic team names)
- **P1**: Historical weekly analytics (PF/PA per week) — Analytics.tsx YoY charts currently use seeded data since no history exists; add a `week_summaries` rollup or weekly snapshots
- **P1**: Gate premium-only commissioner actions (draft scheduling, multi-year contracts, taxi squad, custom scoring, webhooks) server-side once league.premium=true
- **P1**: Real SendGrid key + sender domain verification to flip mock → real delivery
- **P1**: Trade value analyzer, player projections
- **P2**: Wrap Analytics charts with explicit minWidth/minHeight to suppress recharts ResponsiveContainer width(-1)/height(-1) console warnings
- **P2**: Standardize `/api/activity` response to flat list (currently returns paginated `{items, total, page, pages}` dict while other list endpoints like `/api/trades`, `/api/trade-block` return flat lists)
- **P2**: Refactor `server.py` (~4100 lines) → modular FastAPI routers (auth, leagues, drafts, trades, players, payments, live_scoring, rosters, waivers, activity)
- **P2**: Extract shared hook `useLeagueContext(myTeam, opponentTeam)` from Matchup/Standings/Roster
- **P2**: Add opt-in `?include=roster` query param to `GET /api/teams` to keep list lean when rosters not needed
- **P2**: Delete dead mock-generator code in `PlayerRoster.tsx` (fallback path no longer reachable for real teamIds)
- **P2**: Compound unique index on `league_invites(league_id, email)`
- **P2**: Switch `EmailInviteRequest.emails` to `list[EmailStr]`
- **P2**: EAS Build for iOS/Android distribution
- **P2**: Mobile app API wiring for Lovable features (React Native in /app/mobile)

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
