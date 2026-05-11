# League Settings — Source-of-Truth Audit & Gap List

**As of:** Iter 77 (May 11, 2026)

## TL;DR

League configuration is now consistently sourced from `db.leagues.{field}`.
The Setup Wizard and Commissioner Settings UI write to a single
`PUT /api/leagues/{id}` endpoint that accepts every key the wizard tries to
write. Reads happen lazily at the call-site (no caching layer to invalidate).

The **fixed** gaps this iteration:

| Setting | Was | Now |
|--|--|--|
| `roster_spots`, `bench_spots`, `minors_spots` | Wizard payload silently dropped | `PUT /leagues/{id}` accepts them, persisted in `db.leagues` |
| `scoring_format`, `max_teams`, `keepers_allowed`, `entry_fee` | Read-only after league creation | `PUT /leagues/{id}` accepts them |
| `playoff_teams`, `playoff_start_week`, `playoff_rounds`, `regular_season_weeks` | Read-only after league creation | `PUT /leagues/{id}` accepts them |
| `trade_review_period_hours` | Hardcoded `72` in 2 places in `routes/trades.py` | Reads from `league.trade_review_period_hours` (defaults 72) |
| `trade_veto_threshold_pct` | Hardcoded `total_teams // 2` (=50%) in `routes/trades.py` | Reads from `league.trade_veto_threshold_pct` (default 50; 0 disables) |
| `trade_deadline_week` | No field existed | `PUT /leagues/{id}` accepts it; UI can wire it |
| `waiver_faab_budget` | Hardcoded `100` on first claim in 2 places (`routes/waivers.py`) | Reads from `league.waiver_faab_budget` (default 100) |
| `waiver_period_days` | No field existed | `PUT /leagues/{id}` accepts it |
| **League Structure** (divisions + conferences) | Saved but didn't enforce completeness | `PUT /leagues/{id}/divisions` now 400s when any team is missing div or conf |
| **Setup Wizard** roster shape inputs | UI present but PUT dropped values | Same PUT now writes; wizard now persists |
| **Premium feature trial timer** | Didn't exist | 14-day clock via `/leagues/{id}/admin/cap-settings` + `/leagues/{id}/premium-status` |

All of the above are persisted in `db.leagues` (single source of truth) and the
audit log captures every change with actor + diff.

## Architecture: where settings live and are read

```
┌─────────────────────────────────────────────────────────────────────────┐
│  WRITE PATH                                                              │
│                                                                          │
│  Setup Wizard (commissioner/SetupWizard.jsx)  ──┐                       │
│  Commissioner Settings (CommissionerSettings)  ─┼──► PUT /leagues/{id}  │
│  League Structure tab                            ┘    (server.py 769)   │
│                                                                          │
│  Special-case writes (still single source of truth):                    │
│   • Divisions/Conferences → PUT /leagues/{id}/divisions                 │
│   • Salary cap + minors  → PUT /leagues/{id}/admin/cap-settings        │
│   • Scoring config       → POST /scoring/config (in db.scoring_configs)│
└─────────────────────────────────────────────────────────────────────────┘
                                  ▼
              ┌──────────────────────────────────────┐
              │  db.leagues  ←  single source of truth │
              └──────────────────────────────────────┘
                                  ▲
┌─────────────────────────────────────────────────────────────────────────┐
│  READ PATH (lazy per-request)                                            │
│                                                                          │
│  routes/matchups.py        league.get("roster_spots", 20)                │
│  routes/trades.py          league.get("trade_review_period_hours", 72)   │
│                            league.get("trade_veto_threshold_pct", 50)    │
│  routes/waivers.py         league.get("waiver_faab_budget", 100)         │
│  routes/seasons.py         league.get("conferences"), team.division      │
│  routes/leagues.py         _premium_status(league) → 14-day countdown    │
│  routes/ratings.py         (no league config — ELO uses constants)       │
│  db.scoring_configs        per-position rule sets (separate collection)  │
└─────────────────────────────────────────────────────────────────────────┘
```

## Remaining gaps to cover (prioritized)

### P0 — Functionally wrong / inconsistent

(none — all P0 gaps were closed in iter 77)

### P1 — Surfaces exist but currently no UI to edit (the API is ready)

1. **Trade Settings tab** in Commissioner Settings → editor for the new
   `trade_review_period_hours`, `trade_veto_threshold_pct`, `trade_deadline_week`
   fields. Backend accepts them via `PUT /leagues/{id}` already.
2. **Waiver Settings tab** in Commissioner Settings → editor for
   `waiver_faab_budget` + `waiver_period_days`. Same `PUT /leagues/{id}` path.
3. **Playoff Settings tab** → editor for `playoff_teams`, `playoff_start_week`,
   `playoff_rounds`, `regular_season_weeks`.
4. **Roster Shape editor** in CommissionerSettings → already in the Setup
   Wizard Basics step; mirror the same inputs into a permanent settings tab
   so commissioners can resize the roster post-setup.
5. **Setup Wizard "Trades" step** — currently the wizard skips trade settings.
   Add a step after Schedule Mix with trade review period + veto threshold +
   deadline week, all writing to the same `PUT /leagues/{id}`.

### P2 — Doesn't exist yet (settings not in the model)

1. **Lineup deadline / lock time** — what time of day rosters lock each game day.
   Currently lineups lock at game start of each matchup; no league-wide override.
2. **Bench points policy** — does the league earn points from benched players?
   Currently always `false`; add `count_bench_points: bool`.
3. **Tie-breaker rules for standings** — currently fixed (PF, then H2H). Add
   `tiebreakers: ["points_for", "head_to_head", "division_record", "coin_flip"]`.
4. **Trade-block visibility** — `trade_block_visible_to: ["league", "commissioner_only"]`.
5. **Schedule mix overrides per-pair** — current model is one global mix.
   Some leagues want unbalanced schedules (e.g. "I play my rival 4 times").
6. **Custom positions** / positional eligibility — currently fixed to C/LW/RW/D/G.
   Some leagues collapse to F/D/G.
7. **Lineup positions slots** — number of C, LW, RW, D, G slots; currently
   inferred from `roster_spots`. Should be explicit per league.
8. **Streaming limit** — max waiver pickups per week. (Currently unlimited.)
9. **IR slot count** — separate from bench, with eligibility rules.
10. **Draft type** — `snake | linear | auction | salary_cap_auction`. Currently
    `format` mixes this with scoring (head_to_head vs roto). Split the concerns.
11. **Draft order method** — `manual | last_year_inverted | random | weighted_lottery`.
12. **Trade deadline → matchup-week lock** — when `trade_deadline_week` passes,
    automatically reject all new trade proposals.
13. **Inactive league mode** — `frozen | offseason | preseason | active | playoffs | complete`
    drives which UI tabs are reachable.

### P3 — Already in `db.leagues` but no validation

1. `format` (dynasty/keeper/redraft/bestball) — accepted by `PUT /leagues/{id}`
   via `scoring_format` field, but no enum validator. Free text today.
2. `sport` — defaults to "nhl" but no validation prevents nonsense.
3. `current_season_status` — string-typed, no enum.
4. `current_week` — integer, no upper bound check against `regular_season_weeks`.

### Code-quality notes (not gaps but worth tracking)

1. **`server.py` is still ~5060 LOC.** The new `PUT /leagues/{id}` handler should
   be moved to `routes/leagues.py` (alongside `divisions` and `cap-settings`).
2. **`routes/users.py` lints with 7 pre-existing E701/E741** — not introduced this
   session; cosmetic only.
3. **No backend tests cover the new `LeagueUpdate` model** — only the live curl
   verification we just ran. A pytest in `tests/test_iter76_features.py` style
   should be added to cover sparse updates + 403 from non-commissioners.

## How a new setting should be added going forward

1. Append the field to `class LeagueUpdate(BaseModel)` in `server.py`.
2. Add it to `_LEAGUE_UPDATE_ALLOWED` set.
3. Read it at the consuming call-site via `league.get("your_field", default)`.
4. Surface a UI control in either the Setup Wizard step OR the
   Commissioner Settings tab — both POST/PUT to `PUT /leagues/{id}` with the
   sparse payload.
5. Add a pytest verifying the round-trip + the consuming behaviour.
6. Audit log captures the diff automatically.
