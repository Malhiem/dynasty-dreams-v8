"""Iter 232N.63 — Salary-cap treatment resolver for minor-league players.

Consulted by every code path that sums a team's cap usage (contracts +
roster synthesis). Implements the 4 modes exposed via
`league.minors_cap_treatment`:

  • ``full``    — Default legacy behaviour. Minor-leaguers count at
                  their full AAV.
  • ``default`` — Every minors player counts at ``default_rookie_aav``
                  (2026 NHL CBA minimum by default).
  • ``tiered``  — Prospects (age < 24 OR ``is_prospect=true``) count
                  at 50%, veterans at 100%.
  • ``none``    — Minor-league contracts are cap-exempt (charge 0).

The resolver is a pure function: given a player, the team's lineup
map, and the league's cap-treatment settings, return the effective
cap hit in dollars. `full` short-circuits without touching the lineup.
"""
from __future__ import annotations

from typing import Optional


def _player_is_in_minors(player: dict, lineup: Optional[dict]) -> bool:
    """A player is 'in minors' if their lineup entry has
    ``section == 'minors'``. Absent-from-lineup players (bench) are
    NOT treated as minors — cap treatment applies only to explicit
    minor-league assignments."""
    if not lineup:
        return False
    pid = str(player.get("_id") or player.get("id") or "")
    if not pid:
        return False
    entry = lineup.get(pid) or {}
    return str(entry.get("section") or "").lower() == "minors"


def _player_is_prospect(player: dict) -> bool:
    """Prospect = explicitly flagged, OR under 24 years old."""
    if player.get("is_prospect"):
        return True
    try:
        age = int(player.get("age") or 0)
    except (ValueError, TypeError):
        age = 0
    return 0 < age < 24


def resolve_full_aav(player: dict, default_rookie_aav: int = 950_000) -> float:
    """Same fallback resolution used by draft-cap-view: contract.aav →
    cap_hit → salary → default_rookie_aav."""
    contract = player.get("contract") or {}
    for candidate in (
        contract.get("aav"),
        player.get("cap_hit"),
        player.get("salary"),
    ):
        try:
            v = float(candidate or 0)
            if v > 0:
                return v
        except (ValueError, TypeError):
            continue
    return float(default_rookie_aav)


def apply_minors_treatment(
    player: dict,
    *,
    base_aav: float,
    is_in_minors: bool,
    treatment: str,
    default_rookie_aav: float = 950_000,
) -> float:
    """Given the player's base AAV + whether they're in the minors,
    apply the league's `minors_cap_treatment` policy."""
    if not is_in_minors:
        return float(base_aav)
    t = (treatment or "full").lower()
    if t == "full":
        return float(base_aav)
    if t == "none":
        return 0.0
    if t == "default":
        return float(default_rookie_aav)
    if t == "tiered":
        # 50% for prospects, 100% for veterans.
        return float(base_aav) * (0.5 if _player_is_prospect(player) else 1.0)
    # Unknown value → conservatively fall back to full.
    return float(base_aav)


def effective_cap_hit(
    player: dict,
    *,
    lineup: Optional[dict],
    league: dict,
) -> float:
    """One-liner used by callers that already have `player` + `team.lineup`
    + `league`. Combines full-AAV resolution + minors treatment."""
    default_rookie_aav = int(league.get("default_rookie_aav", 950_000))
    treatment = league.get("minors_cap_treatment") or "full"
    base = resolve_full_aav(player, default_rookie_aav=default_rookie_aav)
    in_minors = _player_is_in_minors(player, lineup)
    return apply_minors_treatment(
        player,
        base_aav=base,
        is_in_minors=in_minors,
        treatment=treatment,
        default_rookie_aav=default_rookie_aav,
    )
