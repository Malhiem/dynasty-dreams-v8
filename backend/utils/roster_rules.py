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

    No-op when `enforce_position_maxes` is False or `position_limits` is
    empty/missing — preserves legacy behaviour for leagues that haven't
    configured the rule.
    """
    if not league.get("enforce_position_maxes"):
        return None
    limits = league.get("position_limits") or {}
    if not limits:
        return None
    pos = _position_of(candidate_player)
    if not pos or pos not in limits:
        return None
    # An explicit `0` means "zero players allowed at this position" — block
    # the add. A missing key is treated as "no limit" via the membership
    # check above. Negative values fall through as no-limit (defensive).
    raw_max = limits[pos]
    if raw_max is None:
        return None
    max_at_pos = int(raw_max)
    if max_at_pos < 0:
        return None
    current_at_pos = sum(1 for p in current_roster_players if _position_of(p) == pos)
    if current_at_pos + 1 > max_at_pos:
        name = candidate_player.get("name") or candidate_player.get("display_name") or "player"
        return (
            f"Position limit reached for {pos}: roster already has "
            f"{current_at_pos}/{max_at_pos}. Adding {name} would exceed the "
            f"league's configured {pos} cap."
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
