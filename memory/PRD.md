# Dynasty Dreams - PRD

## Platform Summary
NHL Dynasty Fantasy Sports Platform — 9 phases, 65+ API endpoints, 20 web pages, 15 mobile screens, 1,038 real NHL players.

## Implementation (9 Phases, April 2026)

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

## Key Stats
- **65+ REST API endpoints**
- **20 web pages** (React/CRA + sidebar layout)
- **15 mobile screens** (React Native + Expo, all with real API calls)
- **17 MongoDB collections**
- **4 sports configured** (NHL active, NFL/NBA/MLB ready)
- **League invite system** with shareable links, QR codes, email invites

## MOCKED: Email invite sending (records stored, actual emails not sent — needs SendGrid/SES)

## Backlog
- P0: NFL player data seeding (data source needed)
- P1: Trade value analyzer, Player projections
- P2: EAS Build for iOS/Android distribution
