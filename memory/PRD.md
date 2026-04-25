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
| 19 | **Audit log wired** to `/api/leagues/{id}/audit-log` in CommissionerSettings. **Draft-pick ownership persisted** (db.draft_picks, 1290 seeded across 5 leagues, `/api/drafts/{id}/picks` endpoint) + DraftBoard rendering live ownership with real team abbrs. **League Home sidebar link**. **Full trade execution** (players, picks, salary retention) + **conditional trades** (fantasy_points, nhl_points, nhl_goals/assists/wins, games_played, live_fantasy_points with gte/lte/eq operators). New `TradeConditionsEditor` UI in TradeBuilder. test_trade_flow.py: all assertions PASSED | 5/5 backend pytest + frontend regression, 2 minor UX notes fixed |
| 20 | **Pick trade_history persisted** (every execution $push's {trade_id, from/to team, traded_at} onto the draft_picks doc; DraftBoard popover renders the full chain). **Trade proposal wiring** — Team.tsx `handleSendProposal` now POSTs to `/api/trades` with assets + conditions (pulled from `window.__getTradeConditions`). **Team-level trade conditions** — new metrics `won_championship`, `won_division`, `made_playoffs`, `team_rank`, `team_wins`, `team_losses`, `team_points_for`. UI toggle between Player / Team condition rows. Evaluator resolves team_id from trade side when not set. test_trade_flow.py: 5 test blocks including championship condition + 2-step trade history | All passing end-to-end |
| 21 | **HEAD TO HEAD fix** (regex /_/g replace across 6 files). **Opponent score in My Week at a Glance** for H2H leagues via updated `/api/users/me/week-at-a-glance` endpoint. **Drag-drop MyLeaguesOrderedList** replacing RecommendedForYou on Dashboard (native HTML5 DnD, localStorage persisted). **Season Awards admin UI** — Commissioner/co-comm mark championship/division/playoffs per team via new `PUT /api/leagues/{id}/teams/{id}/awards` endpoint; TeamResponse exposes award datetimes; toggling awards auto-evaluates pending conditional trades and returns `unlocked_trades` count. **Recharts -1 warnings** fixed by wrapping ResponsiveContainers with min-height divs. Audit log entries for award toggles. Improved exception logging on conditional re-eval. | 5/5 pytest + 8/8 frontend items, 0 critical issues |
| 22 (Apr 23, 2026) | **Auto-Crown Championships + Consolation Prize**. `POST /api/matchups/simulate-week` now auto-crowns champions on `is_final` playoff matchups (sets `championship_won_at`, activity_feed, audit_log, re-evaluates conditional trades, emits `championship_crowned` Socket.IO event) and auto-awards consolation winners (sets `consolation_won_at`, inserts `team_rewards` with team_name, calls `_apply_consolation_prize` for lottery boost / compensation pick, emits `consolation_crowned`). New commissioner endpoints: `PUT /api/leagues/{id}/consolation-prize`, `GET /api/leagues/{id}/consolation-prize`, `GET /api/leagues/{id}/team-rewards`. **SeasonAwardsTab rebuilt** with 3 sub-tabs: Team Awards · Consolation Prize (editor for draft_lottery_boost / compensation_pick / custom) · Awarded Prizes history. **DraftLottery.tsx** adds live "Consolation Winners & Applied Prizes" card showing boosted R1 picks + compensation picks, with Socket.IO live-refresh on new crownings. **LeagueHistory.tsx** adds "Recent Crowns" card wired to live champion + consolation data. **AppLayout.jsx** now listens app-wide to `championship_crowned` + `consolation_crowned` socket events and shows toasts. **Toaster mounted** in App.js (was missing — caused silent toast failures). `test_crown_flow.py` passes end-to-end. | 10/10 pytest + 100% frontend acceptance (iter 19); 2 LOW fixes applied (hydration + toaster) |
| 23 (Apr 23, 2026) | **Championship roll-up into user's profile card**. New fields `conference_winner_at`, `consolation_won_at` on Team model. Awards endpoint `PUT /api/leagues/{id}/teams/{id}/awards` now accepts `conference_winner`, `consolation_won`. `simulate-week` auto-crowns `conference_final` + `division_final` brackets (parallel Socket.IO events `conference_crowned`, `division_crowned`). `/api/u/{username}` rolls up championships / conference titles / division titles / consolations / playoff appearances into `stats` + appends permanent career trophies (with `earned_at`) to `trophies[]`. XP formula bumped: +500/championship, +250/conf, +150/division, +100/consolation, +75/playoff. **SeasonAwardsTab** gains Conference + Consolation toggles. **ProfilePage.jsx** adds a 5-tile career championships row + colored trophy palettes per type with earned date. Conditional trade evaluator supports new `won_conference` + `won_consolation` metrics. Self-tested via curl — `chriszarek` went from level 11 → 12 with 1 championship trophy rendered. | Backend verified via curl + test_crown_flow.py pass; frontend verified via screenshot — all 3 testids present |
| 24 (Apr 25, 2026) | **Backend refactor (Task B)** — extracted awards, drafts, matchups into `/app/backend/routes/` using a `setup(deps)` injection pattern. server.py shrank from 4,975 → 4,406 lines (-580 LOC). New modules: `routes/awards.py` (244 loc: team-awards, consolation prize, team rewards, apply_consolation_prize helper), `routes/drafts.py` (23 loc: draft picks), `routes/matchups.py` (387 loc: schedule gen, current-week, simulate-week w/ all 4 auto-crown branches). **Mobile app wiring (Task C)** — `/app/mobile/.env` with `EXPO_PUBLIC_BACKEND_URL`; `api.js` + `useSocket.js` now env-driven. Added `useGlobalSocketEvent` RN hook. Auth endpoints now return `access_token` + `refresh_token` in the JSON body (in addition to cookies) so mobile Bearer auth works end-to-end. `/auth/refresh` now accepts refresh token via `Authorization: Bearer` header. Two new screens: **ProfileScreen** (full championship roll-up, live-refresh on crown events) and **MatchupScreen** (current-week matchups w/ bracket badges). **DashboardScreen** gains Alert toasts for 4 crown events + tappable name → Profile. `useLeagueSocket` exposes onChampionshipCrowned/onConsolationCrowned/onConferenceCrowned/onDivisionCrowned. `test_trade_flow.py` made idempotent (auto-clears award timestamps at startup). | Iter 20: 15/15 pytest + test_crown_flow.py + test_trade_flow.py all green; 0 critical, 0 minor (pre-existing contract note) |
| 25 (Apr 25, 2026) | **Historical weekly analytics rollup (P1)**. New `routes/analytics.py` exposes `GET /leagues/{id}/weekly-analytics?team_id=...&season=...` returning `{weeks, season_summary, year_over_year}` and `POST /leagues/{id}/backfill-week-summaries` (idempotent, returns `{rows_upserted, rows_inserted, rows_updated}`). `simulate_week` now upserts per-team `week_summaries` rows on every matchup. New `seed_analytics.py` synthesizes 9,804 rows across 5 leagues (current season W1..W10 + 4 prior seasons × 26 weeks). `_current_season()` uses NHL convention (Oct-cutover). Wired `Analytics.tsx` to live data with LIVE/DEMO testid badges and graceful fallback. Fixed `vs League Avg` card to show conditional sign (+/-). | Iter 22: 8/8 pytest + crown_flow + trade_flow all green; 0 critical, 0 minor; LIVE badge + W1..W10 chart verified for chriszarek |
| 26 (Apr 25, 2026) | **League Search + Privacy toggle**. Sidebar "League Settings" replaced by "League Search" (testID `sidebar-league-search-link`). New `/league-search` page (`LeagueSearch.tsx`) lists public leagues with q/format filters, open-spots / FULL / Member badges, and a Join dialog that posts `POST /leagues/{id}/join-public`. Backend additions: `GET /api/public-leagues` (anonymous OK), `PUT /api/leagues/{id}` (commissioner-only is_private toggle + audit_log), `POST /api/leagues/{id}/join-public` (rejects on private/full/already-member). CommissionerSettings → League Setup tab gains a Privacy card with a Switch (testID `league-privacy-toggle`) showing 🔒 PRIVATE / 🌐 PUBLIC. Post-join navigates to `/dashboard` and stores active_league_id in localStorage. | Iter 23: 11/11 pytest + crown_flow + trade_flow all green; 0 critical, 0 frontend minor; nav UX fix applied |
| 27 (Apr 25, 2026) | **PF reconciliation + H2H matchups on League Detail page**. Bug: Ice Kings H2H showed PF=56,418 vs actual matchup sum 4,584 — historical inflation. Added `POST /api/leagues/{id}/recalculate-stats` (commissioner-only) that re-derives wins/losses/ties/PF/PA from completed matchups and writes audit_log; ran it on Ice Kings → Zarek's Frozen back to 4,584.1 PF. CommissionerSettings → League Setup tab gains a "Recalculate Stats" button (testID `league-recalc-stats`) under the Privacy card. New "MATCHUPS — WEEK X" section on `/leagues/{id}` rendered ONLY for H2H scoring formats, with cyan-highlighted winners, FINAL/SCHEDULED status badge, and stable testIDs (`league-matchups-section`, `league-matchup-card-{id}`, `matchup-home-name-{id}`, `matchup-home-record-{id}`, `matchup-home-score-{id}` + away counterparts). | Iter 24: 40/40 pytest (11 new + 29 regression) + frontend acceptance 100%; 0 critical, 0 minor |
| 28 (Apr 26, 2026) | **Pending Trades + Recent Transactions on League Page**. New backend endpoints: `GET /api/leagues/{id}/transactions?limit=N` (normalized roster_add / roster_drop / waiver_won / trade_executed), `GET /api/leagues/{id}/pending-trades` (status in pending/voting/conditional). Existing `/api/activity/{id}` now accepts comma-separated event_type. **Bug fix**: `process_waivers` now actually adds the won player to the team's roster (`$addToSet`) AND emits a `waiver_won` activity event — previously the player wasn't moved at all. Enriched roster_add/drop activity metadata with team/player IDs+names. **Frontend**: LeagueDetailPage (`/leagues/{id}`) gains two stacked cards above Standings — "PENDING TRADES" (only shows when count>0; amber pulse dot, asset summary, expiry countdown, Review link) with testIDs `league-pending-trades-section`/`pending-trade-card-{id}`; and "RECENT TRANSACTIONS" with testIDs `league-transactions-section`/`league-transaction-{id}` and color-coded ADD (emerald) / DROP (rose) / WAIVER (violet) / TRADE (cyan) icons + FAAB bid display + empty state (`league-transactions-empty`). | Iter 25: 17/17 new pytest + crown_flow + trade_flow regression; frontend 100%; 0 critical, 0 minor |

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
- **P1**: Continue `server.py` split (still ~4,406 lines) — extract `/trades`, `/players`, `/auth`, `/users`, `/waivers`, `/live_scoring` routers next
- **P1**: Mobile EAS Build pipeline (iOS + Android distribution)
- **P1**: Expo push notifications for championship/consolation crown events
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
