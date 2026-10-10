# Profile experience and career history

The public profile, signed-in level endpoint and XP notifications use
`services.profile_career.career_summary`. Reads do not create rewards. The
public response now includes `xp_total` alongside the existing level fields.

## Rules

| Activity | XP |
|---|---:|
| Distinct team managed | 50 per user/team |
| Matchup win | 20 |
| Committed trade execution | 25 per distinct participant |
| Completed draft | 40 per distinct participant/draft |
| Successful waiver acquisition | 5 |
| Career fantasy points | No XP; displayed as a statistic only |
| Championship | 500 per season |
| Conference title | 250 per season |
| Division title | 150 per season |
| Consolation win | 100 per season |
| Playoff appearance | 75 per season |

Owners and co-owners receive the same full amount. A user appearing on multiple
participating teams receives one trade/draft credit for the same activity.
Adding a co-owner does not grant past activity rewards. Direct free-agent adds,
pending/lost/cancelled/denied waiver claims, failed executions and queued trade
acceptances earn no XP. Dropping a player later does not revoke an earned waiver
credit. Correcting the claim to a non-success status removes that credit.

Runner-up and regular-season top-three trophies have no separate XP multiplier.
The speed-champion +50 notification remains non-cumulative. Level L costs
`100 + 50 * L` XP to advance. Notifications carry a cumulative snapshot after
the action commits; personal-room authorization is unchanged.

## Attribution and history

- Trades and completed drafts store `xp_user_ids` in the successful status write.
  Waiver claims also store `xp_committed`; fallback processing keeps it false
  until all roster/budget writes have succeeded. Failed finalization rolls back
  the claim and roster writes.
- `profile_attribution` on a team records per-user current-season earned amounts
  and the record baseline at ownership changes. Departing owners retain their
  contribution; new owners start at the current baseline. `career_user_ids`
  preserves distinct-team participation. Invitation acceptance and owner removal
  write attribution with their ownership update.
- Both season-finalization paths save `co_owner_ids` and `profile_contributions`
  in team snapshots, including earned runner-up flags. Renewal starts a fresh
  attribution baseline. When records are carried over instead of reset, that
  baseline prevents carrying the same records into XP twice.
- Completed snapshots are authoritative for a league/team/season; live records
  contribute when that season has no snapshot for the user. Integer/string
  season years share the same identity. Distinct seasons remain separate.
- Trophy ordering uses a consistently typed UTC key: newer year first, then known
  dates, then stable type/league/team ties. Undated entries follow dated entries
  within a year. Invalid legacy dates do not crash the profile. Historical private
  leagues retain name/ID/link masking.
- `xp_notifications` uses its unique `_id` to deduplicate user/source/activity
  notifications. Broadcast failure releases that key for an explicit retry.
  Cumulative XP is derived from successful source records, not notification rows.

Existing records without completion-time recipient metadata retain compatible
reads from stored trade participant IDs or the legacy team participants. An
ownership change freezes `profile_legacy_user_ids` so a later co-owner cannot
inherit those rows. Data predating tracking may lack enough evidence to recover
former owners or historical co-owners. The audit reports those gaps; it cannot
reconstruct missing history. Account merges freeze each source account’s full earned summary and transfer active
ownership through the baseline service. Legitimate equal awards earned by both
accounts are preserved. Raw Mongo ownership writes remain unsupported; use the
administrative ownership endpoint described below.

## Legacy audit/backfill

From `backend/`, with explicit `MONGO_URL` and `DB_NAME`:

```sh
python -m scripts.backfill_profile_progression
python -m scripts.backfill_profile_progression --apply
```

The default is a dry run. Apply mode freezes only evidence-backed snapshot
contributions and successful legacy trade recipients. It uses compare guards and
does not infer old co-owners from current ownership. Repeated apply runs leave
totals unchanged. Accepted trades without execution evidence, drafts/claims
without completion-time attribution and incomplete ownership history are reported.
Review the report before applying it to real data. No real-data backfill is part
of the profile fix validation.

## Validation

Use the isolated Compose workflow in `e2e/README.md`. The repository currently has
`docker-compose.h2h.yml` as its retained test stack definition. Never use backend
pytest against ambient/shared Mongo settings.

```sh
python -m pytest tests/test_profile_progression.py tests/test_users_router.py \
  tests/test_iter232N24_xp_helper.py tests/test_seasons_router.py \
  tests/test_iter232N27_draft_leaderboard.py -q
npm --prefix e2e run typecheck
npx playwright test --config=e2e/profile.config.ts
```

The browser suite includes real co-owner invitation/acceptance, executed trades,
season renewal, XP thresholds, public/private consistency, trophy persistence,
failed-load recovery and maximum 32-character usernames at 320/390/430px across
Chromium, Firefox and WebKit. Backend tests exercise the last-pick commit, successful
waiver finalization, ownership changes, notification idempotency and legacy audit.

## Competition modifier (owner-xp-v1)

Before the first scoring of each matchup, capture every league team's highest
owner/co-owner career XP. Compare the highest team score with the league median:
under 200 XP gap earns 100%, 200–399 earns 75%, and 400+ earns 50%. All teams use
the same league multiplier. Missing ownership/history yields 100%. Floor each
adjusted award to a whole XP. Stored assessments never change on profile reads.

The modifier applies only to matchup wins, championships, conference/division
titles, consolation wins and playoff appearances. Separately awarded titles use
the team's most recent pre-match assessment. Legacy awards without recorded
assessments retain full XP. Fantasy points never award XP. Team management,
executed trades, draft completion and successful waiver acquisitions are unchanged.
Ownership transfer and season snapshots preserve earned adjustments. Trophy API
entries include base XP, multiplier and awarded XP; matchup XP notifications also
include this breakdown. No commissioner can select or override the multiplier.

## Account merges and administrative ownership changes

Account merges preserve the sum of both accounts' previously earned XP, even if
+both legitimately earned equal credit for the same team event. Source summaries
+are captured once and stored under their source account ID; rerunning a completed
+merge adds nothing. Transferred team membership earns no extra management XP.
+Historical event IDs remain intact, preserving provenance and avoiding new reward
+notifications. Future rewards belong to the surviving account. Nested merges
+include prior source credit once.

Platform admins can POST `/api/admin/teams/{team_id}/ownership` with `owner_id`,
+`co_owner_ids` and a required `reason`. The operation automatically freezes earned
+credit, applies incoming baselines and records ownership history. Record comparison
+guards retry concurrent scoring. It exposes no XP allocation or multiplier input.
+Direct database edits cannot be intercepted by application code and must be replaced
+with this endpoint. Historical raw edits still require evidence-based reconciliation.
