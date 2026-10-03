"""Shared roster-rule enforcement helpers.

Centralises the position-limit and minimum-roster checks so the waiver,
trade, draft, and lineup-validation paths all read from the same source of
truth (`db.leagues.position_limits`, `enforce_position_maxes`,
`min_active_players`, `min_games_played`). Each helper returns either
`None` (rule satisfied) or a human-readable error string the caller raises
as a 400.

Why a util module: the same rules are checked from at least 4 entry points,
each of which currently lives in a separate router. Inlining the logic four
times would create a drift hazard.
"""
from __future__ import annotations

from typing import Iterable, Optional


def _position_of(player: dict) -> str:
    """Best-effort extraction of a normalised position code from a player doc.

    Players have evolved schema-wise: `position`, `primary_position`, or
    `eligible_positions[0]` may carry the value. Normalise to upper-case.
    Goalies are mapped to "G". Returns "" when nothing usable is present.
    """
    raw = (
        player.get("position")
        or player.get("primary_position")
        or (player.get("eligible_positions") or [None])[0]
        or player.get("player_type")
        or ""
    )
    s = str(raw).strip().upper()
    if s in ("GOALIE", "GOALTENDER"):
        return "G"
    if s in ("LW", "RW", "C", "D", "G"):
        return s
    # Some seeds use "LD"/"RD"; collapse to "D"
    if s in ("LD", "RD"):
        return "D"
    return s


def check_position_limits(
    league: dict,
    current_roster_players: Iterable[dict],
    candidate_player: dict,
) -> Optional[str]:
    """Return an error string if adding `candidate_player` to the roster
    would exceed any configured position limit, else None.

    No-op when `enforce_position_maxes` is False or no caps are
    configured — preserves legacy behaviour for leagues that haven't
    set up Position Breakdown.

    Iter 176 — Reads the new canonical `position_breakdown.active`
    field first, with legacy fallback to the old single-row
    `position_limits` dict so unmigrated leagues keep working.
    Also expands two categorical bucket caps:

      • "S" (Skater) — applies to any non-goalie
      • "W" (Wing) — applies to LW or RW
    """
    if not league.get("enforce_position_maxes"):
        return None
    # Iter 176 — new canonical source: position_breakdown.active.
    # Falls back to the legacy `position_limits` dict.
    breakdown = league.get("position_breakdown") or {}
    active_limits = breakdown.get("active") if isinstance(breakdown, dict) else None
    limits = active_limits if active_limits else (league.get("position_limits") or {})
    if not limits:
        return None

    pos = _position_of(candidate_player)
    if not pos:
        return None

    # Build the list of bucket keys this candidate touches so we can
    # check categorical caps in one pass. A C player triggers "C" and
    # "S" (skater); an LW player triggers "LW", "W" (wing) and "S".
    triggered_buckets = {pos}
    if pos in ("C", "LW", "RW", "D"):
        triggered_buckets.add("S")
    if pos in ("LW", "RW"):
        triggered_buckets.add("W")

    name = candidate_player.get("name") or candidate_player.get("display_name") or "player"
    for bucket in triggered_buckets:
        raw_max = limits.get(bucket)
        if raw_max is None:
            continue
        try:
            max_at_pos = int(raw_max)
        except (TypeError, ValueError):
            continue
        if max_at_pos < 0:
            continue
        # Count current roster members that fall under this bucket so
        # the cap behaves consistently regardless of how the
        # commissioner phrased it.
        def _matches_bucket(p: dict) -> bool:
            existing = _position_of(p)
            if bucket == "S":
                return existing != "G" and existing != ""
            if bucket == "W":
                return existing in ("LW", "RW")
            return existing == bucket
        current_at_pos = sum(1 for p in current_roster_players if _matches_bucket(p))
        if current_at_pos + 1 > max_at_pos:
            return (
                f"Position limit reached for {bucket}: roster already has "
                f"{current_at_pos}/{max_at_pos}. Adding {name} would exceed the "
                f"league's configured {bucket} cap."
            )
    return None


def check_min_active_players(
    league: dict,
    starting_lineup_count: int,
) -> Optional[str]:
    """Return an error string when a lineup save would drop below the
    league's `min_active_players` requirement (i.e. starting players that
    will actually score). 0 / unset = no requirement (legacy behaviour)."""
    minimum = int(league.get("min_active_players") or 0)
    if minimum <= 0:
        return None
    if starting_lineup_count < minimum:
        return (
            f"Lineup has {starting_lineup_count} active player"
            f"{'s' if starting_lineup_count != 1 else ''}; league requires "
            f"at least {minimum}."
        )
    return None


def check_min_games_played(
    league: dict,
    player: dict,
) -> Optional[str]:
    """Return a warning string when a player's season `games_played` count
    is below the league's `min_games_played` requirement. This is the
    NHL-style "play 50 of 82" gate used by some leagues to ensure rostered
    skaters actually contribute. Returns None (no rule) when threshold = 0."""
    threshold = int(league.get("min_games_played") or 0)
    if threshold <= 0:
        return None
    gp = int(player.get("games_played") or 0)
    if gp < threshold:
        name = player.get("name") or "player"
        return (
            f"{name} has {gp} games played; league min is {threshold}. "
            "Player may not count toward roster minimums until eligible."
        )
    return None


def compute_minor_eligible(player: dict, league: Optional[dict] = None) -> bool:
    """Iter 181 — Shared helper for the "is this player eligible to be
    rostered in a Minors slot?" question. Centralises the rule that was
    previously duplicated across `roster.py`, `drafts.py`, and now the
    waivers / players directory.

    A player is minor-eligible when ANY of the following holds:
      • They are explicitly seeded as a prospect (`player_type ==
        "prospect"` or the legacy `minor_eligible: True` flag).
      • Both their age AND career games played fall under the league's
        configured thresholds (defaults: ≤22 years old, ≤25 career
        NHL games). Unknown values count as "eligible" so a freshly
        signed prospect without backfilled NHL stats still qualifies.
    """
    league = league or {}
    player_type = (player.get("player_type") or "").lower()
    if player_type == "prospect" or bool(player.get("minor_eligible")):
        return True
    try:
        max_age = int(league.get("minors_max_age") or 22)
    except (TypeError, ValueError):
        max_age = 22
    try:
        max_career_gp = int(league.get("minors_max_career_games") or 25)
    except (TypeError, ValueError):
        max_career_gp = 25
    age_val = player.get("age")
    gp_val = player.get("career_games_played")
    try:
        age_int = int(age_val) if age_val is not None else None
    except (TypeError, ValueError):
        age_int = None
    try:
        gp_int = int(gp_val) if gp_val is not None else None
    except (TypeError, ValueError):
        gp_int = None
    age_ok = age_int is None or age_int <= max_age
    gp_ok = gp_int is None or gp_int <= max_career_gp
    return age_ok and gp_ok


def check_position_breakdown_within_caps(
    position_breakdown: Optional[dict],
    roster_spots: Optional[int],
    bench_spots: Optional[int],
    minors_spots: Optional[int],
) -> Optional[str]:
    """Iter 181 — Reject `PUT /api/leagues/{id}` when the per-position
    caps on any row would sum to more than the section's overall cap.

    The Position Breakdown matrix lets commissioners set per-position
    caps for Active Roster, Bench, and Minors. The sum of those caps
    on each row MUST be ≤ the corresponding section's total size,
    otherwise the league becomes mathematically impossible to fill:
    e.g. caps summing to 21 with `roster_spots = 19` would force 2
    players into thin air.

    Returns a single human-readable error string (callers raise it as
    a 400). Returns None when every row is within its cap, OR when the
    breakdown is empty / the row's section cap is unset (no constraint
    to enforce). User-friendly note: tells the commissioner WHICH
    section overflowed and BY how much, plus the fix ("increase the
    section size first").
    """
    if not position_breakdown or not isinstance(position_breakdown, dict):
        return None

    def _row_sum(row_key: str) -> int:
        row = position_breakdown.get(row_key) or {}
        if not isinstance(row, dict):
            return 0
        total = 0
        for v in row.values():
            if v is None or v == "":
                continue
            try:
                total += int(v)
            except (TypeError, ValueError):
                continue
        return total

    sections = [
        ("active", "Active Roster", roster_spots),
        ("bench",  "Bench",         bench_spots),
        ("minors", "Minors",        minors_spots),
    ]
    for row_key, label, cap in sections:
        if cap is None:
            continue
        try:
            cap_int = int(cap)
        except (TypeError, ValueError):
            continue
        if cap_int <= 0:
            continue
        s = _row_sum(row_key)
        if s > cap_int:
            return (
                f"{label} per-position caps sum to {s} but {label} size "
                f"is only {cap_int}. Increase {label} size first, or "
                f"lower the per-position caps on the {label} row."
            )
    return None
