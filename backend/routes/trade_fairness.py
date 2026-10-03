"""
Iter 201b — Trade Fairness Scoring.

Computes a per-trade fairness score (0-100, 100 = perfectly balanced) based
on five signals applied to each side of the trade:

  1. Salary delta            — annual cap dollars × 0.0001
  2. YTD fantasy-points       — cumulative `points` per player × 0.4
  3. Position scarcity        — Goalie 1.5× · Defense 1.2× · Forward 1.0×
  4. Pick equity              — round/year-discounted draft-pick value table
  5. Age differential         — bonus for youth (30 - age) × 5, dynasty-aware
                                 (per user requirement on top of base signals)

The two side totals are reduced to a single fairness percentage:

    fairness = 100 × min(side_a_value, side_b_value)
                     / max(side_a_value, side_b_value)

Trades scoring < ALERT_THRESHOLD (default 50) are flagged ALERT for the
platform admin. Self-contained — no DB writes, callable as a pure
function on a hydrated trade dict (assets + side player lookup).
"""
from __future__ import annotations

from typing import Iterable

ALERT_THRESHOLD = 50

# Per-position scarcity multiplier (fantasy hockey defaults)
POSITION_SCARCITY = {
    "G": 1.5, "D": 1.2,
    "C": 1.0, "LW": 1.0, "RW": 1.0, "F": 1.0,
}

# Base draft-pick value table by round (1-based). Linear discount with year offset.
PICK_VALUE_TABLE = {1: 100, 2: 60, 3: 35, 4: 20, 5: 12, 6: 6, 7: 3}
PICK_FUTURE_YEAR_DISCOUNT = 0.7  # value of round R in (current_year + N) = PICK_VALUE_TABLE[R] * 0.7**N


def _player_value(player: dict | None, asset: dict, current_year: int | None = None) -> dict:
    """Return per-signal contributions for a single player asset.
    Falls back to asset-embedded `points`/`position` when the player doc
    is missing (e.g., player deleted post-trade)."""
    pts = (player or {}).get("points") or asset.get("points") or 0
    salary = (player or {}).get("salary") or asset.get("salary") or 0
    age = (player or {}).get("age")
    pos = (player or {}).get("position") or asset.get("position") or "F"
    scarcity = POSITION_SCARCITY.get(pos, 1.0)

    pts_signal = float(pts) * 0.4
    salary_signal = float(salary) * 0.0001
    age_signal = max(0.0, (30 - float(age))) * 5.0 if isinstance(age, (int, float)) else 0.0
    base = pts_signal + salary_signal + age_signal
    return {
        "value": base * scarcity,
        "points_signal": pts_signal,
        "salary_signal": salary_signal,
        "age_signal": age_signal,
        "scarcity_mult": scarcity,
        "position": pos,
        "age": age,
    }


def _pick_value(asset: dict, current_year: int | None = None) -> dict:
    try:
        rd = int(asset.get("pick_round") or 0)
    except (TypeError, ValueError):
        rd = 0
    if rd <= 0:
        return {"value": 0, "round": rd, "year": asset.get("pick_year")}
    base = PICK_VALUE_TABLE.get(rd, 1)
    py = asset.get("pick_year")
    discount = 1.0
    if isinstance(py, (int, float)) and isinstance(current_year, (int, float)):
        offset = max(0, int(py) - int(current_year))
        discount = PICK_FUTURE_YEAR_DISCOUNT ** offset
    return {"value": base * discount, "round": rd, "year": py, "discount": discount}


def compute_side_value(
    assets: Iterable[dict],
    player_lookup: dict,
    current_year: int | None = None,
) -> dict:
    """Aggregate the value of one side of a trade.

    Args
    ----
    assets : list of asset dicts (asset_type ∈ {'player', 'pick'})
    player_lookup : map of player_id (str) → player document
    current_year : optional — used to discount future picks
    """
    player_total = 0.0
    pick_total = 0.0
    breakdown = {"players": [], "picks": []}
    ages: list[float] = []
    for a in assets:
        if a.get("asset_type") == "player":
            pid = str(a.get("player_id") or "")
            p = player_lookup.get(pid)
            v = _player_value(p, a, current_year=current_year)
            player_total += v["value"]
            breakdown["players"].append({"player_id": pid, **v})
            if isinstance(v.get("age"), (int, float)):
                ages.append(float(v["age"]))
        elif a.get("asset_type") == "pick":
            v = _pick_value(a, current_year=current_year)
            pick_total += v["value"]
            breakdown["picks"].append(v)
    avg_age = sum(ages) / len(ages) if ages else None
    return {
        "total": player_total + pick_total,
        "player_value": player_total,
        "pick_value": pick_total,
        "avg_age": avg_age,
        "asset_count": len(breakdown["players"]) + len(breakdown["picks"]),
        "breakdown": breakdown,
    }


def compute_fairness(trade: dict, player_lookup: dict, current_year: int | None = None) -> dict:
    """Top-level fairness computation. Returns a dict with:
      - score: 0-100 (100=perfectly fair, threshold=ALERT_THRESHOLD)
      - alert: bool
      - favored_side: 'offered' | 'requested' | 'even'
      - side_a / side_b: the per-side value breakdowns
      - age_differential: requested_avg_age - offered_avg_age (positive ⇒
        the offered side is younger ⇒ proposer is giving up youth)
    """
    side_a = compute_side_value(trade.get("assets_offered") or [], player_lookup, current_year)
    side_b = compute_side_value(trade.get("assets_requested") or [], player_lookup, current_year)
    a, b = side_a["total"], side_b["total"]
    if max(a, b) == 0:
        score = 100  # both sides empty → vacuously even
    else:
        score = round(100.0 * min(a, b) / max(a, b), 1)
    favored = "even"
    if a > b * 1.05:
        favored = "requested"  # the receiver of side_a got more
    elif b > a * 1.05:
        favored = "offered"
    age_diff = None
    if side_a["avg_age"] is not None and side_b["avg_age"] is not None:
        age_diff = round(side_b["avg_age"] - side_a["avg_age"], 1)
    return {
        "score": score,
        "alert": score < ALERT_THRESHOLD,
        "favored_side": favored,
        "side_a": side_a,  # assets_offered
        "side_b": side_b,  # assets_requested
        "age_differential": age_diff,
    }
