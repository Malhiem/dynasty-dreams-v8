# Player Pool implementation contract

- Team selection supports all 32 NHL clubs, conference presets, or a custom set. Empty custom selection permits no acquisitions.
- Drafted minor-league players use current NHL rights (`nhl_rights_team`, then `rights_team`). Existing records fall back to NHL `team`, otherwise `drafted_by_team`. A historical drafting club can be stale after a rights trade; importers must supply current rights to avoid that ambiguity.
- Minor status uses `player_type=prospect`, amateur/minor player status, or a non-NHL amateur league. Draft evidence is a positive draft year/pick or a drafting club. Minor eligibility alone is not draft evidence.
- Unsigned status uses `is_unsigned=true`, unsigned/non-signed contract status, or unsigned player status. Missing contract metadata is not inferred from missing salary. Feed completeness remains a separate release check.
- Locking materializes player IDs. Metadata updates and new imports cannot change eligibility until unlocked. Eligible players may still be added, dropped and traded. Existing roster players are not automatically removed by a restriction change.
- A locked pool must be unlocked before its restrictions change. Unlocking uses current metadata; relocking creates a new snapshot. Legacy locked pools without snapshots return no eligible players until re-finalized.
- Player searches and acquisition validation share one predicate. Roster adds, waiver claim/award, manual draft picks, autopicks, replacement picks and auction nomination/resolution enforce it. League mutation locks serialize acquisitions with Settings changes.
- Paywalls remain disabled. Unsigned-player inclusion is recorded in the future paywall feature list.
- Duplicate-player mode is retained as existing configuration; it is a separate ownership/scoring contract.

## Acceptance evidence

The dedicated suite covers club/current-rights filtering, unsigned and drafted-only minor inclusion, lock/unlock and roster moves, rejected add/claim/pick state integrity, the 32-club UI, queued autopicks, replacement picks, queued waiver denial, and stale auction resolution. Run with no retries in isolated Compose stacks. A full Chromium sweep and final cross-browser results are recorded separately.
