# Historical Scoring Allocation — Rules & Conventions

## Timezone & Clock Rules

| Concept | Rule |
|---|---|
| **Transaction time** | The UTC instant when the backend writes the roster change (`datetime.now(timezone.utc)`). This is the boundary: stats before this moment → old owner; stats at or after → new owner. |
| **Game time** | The NHL game's puck-drop time (UTC). A player's stats for a game are attributed to whoever owned the player at game start (puck drop), **not** game end. |
| **Scoring period** | Defined by the league's `season_start_date` and `matchup_length_days`. Week N spans `[season_start + (N-1)*length, season_start + N*length)` in UTC. |
| **Lineup lock** | The lineup position (active/bench/IR) at **game start** (puck drop) determines eligibility for that game. A mid-game lineup change does not retroactively include or exclude stats for an in-progress game. |

## Ownership Rules

| Scenario | Rule |
|---|---|
| **Trade** | At transaction time T, team A's ownership of the player ends (released_at = T). Team B's ownership starts (acquired_at = T). Stats from games starting before T → A. Stats from games starting at or after T → B. |
| **Drop** | At transaction time T, the team's ownership ends. The player enters an "unowned" interval. Stats earned during the unowned interval are not credited to any team. |
| **Direct pickup** | At transaction time T, the new team's ownership starts. Stats from games starting before T remain unassigned (unowned). Stats from games starting at or after T → new owner. |
| **Waiver claim** | Identical to direct pickup — ownership starts at the processed_at timestamp. |
| **Draft pick** | Ownership starts at the timestamp of the pick. |
| **Buyout** | At transaction time T, ownership ends (player removed from roster). If the buyout is later reversed, a new ownership period begins at the reversal time — it does NOT resurrect the old period. |
| **Roster snapshot restore** | At restore time, a diff is computed: players removed get ownership ended; players added get ownership started. Restores are recorded as source="admin". |

## Lineup Eligibility Rules

| Scenario | Rule |
|---|---|
| **Active position** | forward, defense, goalie → stats count. |
| **Inactive position** | bench, ir, ir-plus, taxi, minors → stats do NOT count. |
| **Position change** | At transaction time T, the old position ends and the new one begins. Stats from games starting before T use the old position's eligibility. Stats from games starting at or after T use the new position. |
| **No tracking data** | For players/periods with no `lineup_status_periods` records, assume eligible (backward compatibility). |
| **New roster addition** | When a player is added to a roster, they are assumed to be in "bench" position until explicitly placed in an active slot via lineup set. The initial ownership record is created with source but NO automatic lineup_status_period — lineup is set when the user saves their lineup. |

## Correction Rules

| Scenario | Rule |
|---|---|
| **Stat correction** | A correction to a game played at time G is applied to the team that owned the player at time G, regardless of who currently owns the player. |
| **Delayed stats** | Stats arriving late for a game at time G follow the same rule — ownership at game time G determines the team. |
| **Retroactive trade** | Not supported. All trades take effect at transaction time going forward. |

## Recomputation Rules

| Scenario | Rule |
|---|---|
| **Period recomputation** | When recomputing week N, the system resolves ownership and lineup eligibility for each game in that week's date range. The result is deterministic and does not change regardless of current roster state. |
| **Idempotency** | Running the same recomputation twice produces identical results. |
| **Historical gaps** | For periods before ownership tracking was enabled, the system falls back to scoring_rosters (week-level snapshots) then to the current roster. A warning is logged. Results are best-effort. |

## Collection Schemas

### `player_ownership_periods`
```
{ player_id: str, team_id: str, league_id: str,
  acquired_at: datetime(UTC), released_at: datetime(UTC) | null,
  source: "trade"|"add"|"draft"|"waiver"|"admin",
  release_source: "trade"|"drop"|"release"|"admin"|"buyout" | null }
```

### `lineup_status_periods`
```
{ player_id: str, team_id: str, league_id: str,
  position: "forward"|"defense"|"goalie"|"bench"|"ir"|"ir-plus"|"taxi"|"minors",
  started_at: datetime(UTC), ended_at: datetime(UTC) | null }
```

## All Roster-Changing Paths (must be instrumented)

1. `trades.py` — Trade execution (both 2-party and multi-party)
2. `roster.py` — Direct pickup (add player)
3. `roster.py` — Drop player
4. `services/waiver_engine.py` — Processed waiver claim (add + optional drop)
5. `draft_pick_actions.py` — Manual draft pick
6. `draft_helpers.py` — Auto-pick during draft
7. `draft_pick_actions.py` — Undo picks (remove from roster)
8. `draft_pick_actions.py` — Undo specific picks (remove from roster)
9. `draft_pick_actions.py` — Swap pick player (remove old + add new)
10. `admin_platform.py` — Platform admin trade revert
11. `roster_snapshots.py` — Restore roster snapshot
12. `admin_players.py` — Player merge (pull old ID, add kept ID)
13. `db_hygiene.py` — Delete orphaned players from roster
14. `teams.py` — Buyout (remove from roster)
15. `teams.py` — Reverse buyout (add back to roster)
