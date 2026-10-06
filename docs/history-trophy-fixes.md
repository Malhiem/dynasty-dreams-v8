# Acceptance criteria — League History and Trophy Room fixes

Scope: League Hub → League History; League Hub → Trophy Room; Roster → Visit Trophy Room and embedded Franchise Trophy Room. Includes the season snapshot API used by those views.

## Implemented behavior

“Last 3 Seasons” means the three newest recorded season years in the selected league, ordered newest first. Recorded years come from season snapshots and banner history; gaps between calendar years do not reduce the selection. A specific-year selection intersects this scope. League banners, league individual trophies, franchise banners, and franchise individual honors share these rules. Hall of Fame, draft awards, and team-card all-time counts retain their existing lifetime scope.

Lifetime standings include completed snapshots plus a distinct active season with gameplay, but never add live totals again when that same year is already snapshotted.

## Acceptance criteria

| ID | Priority | Steps / fixture | Required result | Automated coverage |
|---|---|---|---|---|
| AC-01 | P1 | Request season list, full season snapshot, league trophy room, and franchise trophy room without authentication; include malformed and nonexistent resource IDs. | HTTP 401 before resource lookup; no history payload or ID-existence disclosure. | SH-07 anonymous; `test_anonymous_auth_precedes_resource_lookup` |
| AC-02 | P1 | Sign in as an ordinary user without membership in a private league; request all four history endpoints. | HTTP 403; no private season, team, player, or award history returned. | SH-07 outsider; `test_outsider_cannot_read_any_history_view` |
| AC-03 | P1 | Request all four endpoints as commissioner, co-commissioner, league owner, league administrator, team owner, team co-owner, and platform administrator. | Legitimate members retain HTTP 200 access to league-wide history, including other franchises in their league. | Seven parameterized `test_member_roles_can_read_history` cases |
| AC-04 | P1 | Authenticate as an administrator; request malformed IDs and valid IDs for missing resources. | Malformed IDs return 400; missing resources return 404. Authentication takes precedence for anonymous callers. | `test_authenticated_invalid_and_missing_resources`; legacy trophy ID cases |
| AC-05 | P1 | Four snapshots total 32 W, 8 L, 8 T, and 4,060 PF; the live team retains the current year's 8 W, 2 L, 2 T, and 1,000 PF. | Display 4 seasons, 32 W, 8 L, .750 win percentage, and 4,060 PF. | LH-04 snapshot overlap |
| AC-06 | P1 | Move active year to 2027 without a 2027 snapshot; use the same four historical snapshots and 1,000 active PF. | Display 5 seasons, 40 W, 10 L, .750 win percentage, and 5,060 PF. Distinct active-season values remain included exactly once. | LH-04 distinct active season |
| AC-07 | P2 | League has records for 2026, 2024, 2020, and 2019; select Last 3 Seasons. | Banners and individual trophies include exactly 2026, 2024, and 2020; neither includes 2019. Behavior is independent of the machine's calendar year. | TR-04 exact recent-year sets |
| AC-08 | P2 | In the awarded franchise room, choose 2020. | Both team banners and individual honors show only 2020. Selecting All years restores every recorded year. | FT-06; TR-07/FT-06 reset checks |
| AC-09 | P2 | In the same franchise room, select Last 3 Seasons. | Team banners and individual honors use the same three recorded years as the league room; 2019 is excluded. | FT-07 and shared filter implementation |
| AC-10 | P2 | Combine Last 3 Seasons with year 2019, then switch to All Time, then All years; repeat in league and franchise rooms. | Intersection initially yields no banners or individual honors; All Time reveals 2019; All years restores full history. Controls and sections remain consistent. | TR-07/FT-06 combined filters |
| AC-11 | P1 | Open a franchise from Roster's link and embedded tab; change the selected team and compare identity/awards. | Both entry points show the selected team; legitimate users retain access after auth changes; award-free teams show their own empty states. | FT-01, FT-02, FT-03/FT-04, FT-09 |
| AC-12 | P1 | Complete and renew a season through the application in Points and Categories fixtures. | Championship team matches trophy and season history; renewal preserves the completed snapshot and resets only active-season records according to existing renewal behavior. | H2H-30 and H2H-31, both formats |

## Fix mapping

- Access controls: shared `require_league_member` guard, with authentication before lookup; league-owner compatibility added to the existing guard. Protected routes: `/leagues/:id/seasons`, `/leagues/:id/seasons/:year`, `/leagues/:id/trophy-room`, `/teams/:id/trophy-room`.
- Lifetime totals: compare normalized snapshot years with the actual active league year instead of a sentinel value.
- Trophy filters: one recorded-year selection shared by banners and individual honors in league and franchise rooms. Remove calendar-based banner filtering and the nine-trophy truncation.

These criteria address the six failed test scenarios. Additional findings from the earlier source review, such as request races, error-state presentation, and award-scoring policy, are outside this fix set.

## Verification result

All 12 criteria have automated coverage in the final isolated codebase run: 63 backend tests and 29 browser/API tests passed; 4 legacy tests skipped because their fixture prerequisites were absent. All six original failed scenarios now pass. Frontend production build, changed-file lint, and e2e TypeScript checks passed. No deployment was performed.
