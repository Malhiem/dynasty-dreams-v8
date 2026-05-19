"""Roster / lineup lock evaluation.

Single source of truth for `Is this league's lineup currently locked?` —
consumed by `POST /teams/{id}/lineup` (and any future write-side hook).

Rules (per Iter 100 spec):
* `roster_lock_type` ∈ {"daily", "semi_weekly", "weekly"}
* `roster_lock_day` (and `roster_lock_second_day` for semi-weekly) = day of week
* `lineup_lock_minutes_before` = cushion (0..1440) before the first NHL game
   of the scoring period when individual slots freeze.
* When `playoff_roster_lock_override` is true AND the current week falls
  inside `[playoff_start_week, playoff_end_week]`, the `playoff_*` mirror
  fields replace the regular-season ones.

The check is *advisory* — it tells the caller whether the lineup is locked
RIGHT NOW with a structured payload that the writer can convert into a 400
response. Commissioners override the lock via the existing `is_commish`
branch in `save_team_lineup`.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Optional

_DAY_INDEX = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}


def _resolve_lock_config(league: dict, week: Optional[int]) -> dict:
    """Pick regular-season or playoff lock fields depending on the current week."""
    use_playoff = (
        bool(league.get("playoff_roster_lock_override"))
        and week is not None
        and league.get("playoff_start_week") is not None
        and league.get("playoff_end_week") is not None
        and int(league["playoff_start_week"]) <= int(week) <= int(league["playoff_end_week"])
    )
    prefix = "playoff_" if use_playoff else ""
    return {
        "type": league.get(f"{prefix}roster_lock_type") or league.get("roster_lock_type") or "daily",
        "day": league.get(f"{prefix}roster_lock_day") or league.get("roster_lock_day") or "monday",
        "second_day": (
            league.get(f"{prefix}roster_lock_second_day")
            or league.get("roster_lock_second_day")
        ),
        "minutes_before": int(
            league.get(f"{prefix}lineup_lock_minutes_before")
            if league.get(f"{prefix}lineup_lock_minutes_before") is not None
            else (league.get("lineup_lock_minutes_before") or 0)
        ),
        "scope": "playoff" if use_playoff else "regular",
    }


def evaluate_lineup_lock(
    league: dict,
    *,
    now: Optional[datetime] = None,
    current_week: Optional[int] = None,
) -> dict:
    """Return a dict describing whether the lineup is currently locked.

    Shape:
      {
        "locked": bool,
        "reason": str | None,
        "next_unlock_iso": str | None,   # when does the next lineup window open?
        "scope": "regular" | "playoff",
        "cadence": "daily" | "semi_weekly" | "weekly",
      }
    """
    now = now or datetime.now(timezone.utc)
    cfg = _resolve_lock_config(league, current_week)

    cadence = cfg["type"]
    mins_before = cfg["minutes_before"]
    today_idx = now.weekday()  # Mon=0 .. Sun=6

    def _lock_day_idx(day_name: Optional[str]) -> Optional[int]:
        if not day_name:
            return None
        return _DAY_INDEX.get(str(day_name).strip().lower())

    primary_idx = _lock_day_idx(cfg["day"])
    second_idx = _lock_day_idx(cfg["second_day"]) if cadence == "semi_weekly" else None

    # Compute most-recent lock moment (start of current locked window).
    # `lineup_lock_minutes_before` is a cushion BEFORE the configured lock day's
    # 00:00 — i.e. lineups freeze N minutes before the day rolls over.
    def _lock_moment_for(day_idx: int) -> datetime:
        """Most-recent occurrence of `day_idx` at 00:00 UTC."""
        delta = (today_idx - day_idx) % 7
        d = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=delta)
        return d - timedelta(minutes=mins_before)

    if cadence == "daily":
        # Daily lock — lineups freeze each day at 00:00 minus cushion, unlock
        # again the next morning. For UI/API simplicity, "locked" means we are
        # within the first `mins_before` minutes after midnight of TODAY.
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
        lock_start = midnight - timedelta(minutes=mins_before)
        # Period: [lock_start, midnight + 24h - mins_before) is unlocked
        # actually: simpler — locked between cushion-before-tomorrow and tomorrow
        next_lock = (midnight + timedelta(days=1)) - timedelta(minutes=mins_before)
        # Lineups are unlocked all day until cushion before tomorrow.
        if mins_before > 0 and now >= next_lock:
            return {
                "locked": True,
                "reason": (
                    f"Daily lock active — lineups freeze {mins_before} minute(s) "
                    "before each day starts. Try again after midnight."
                ),
                "next_unlock_iso": (midnight + timedelta(days=1)).isoformat(),
                "scope": cfg["scope"],
                "cadence": cadence,
            }
        return {
            "locked": False,
            "reason": None,
            "next_unlock_iso": None,
            "scope": cfg["scope"],
            "cadence": cadence,
        }

    # Weekly / semi-weekly: locked from `lock_moment` for `mins_before` minutes.
    candidate_days = [d for d in [primary_idx, second_idx] if d is not None] or [0]
    soonest_lock_in_window: Optional[datetime] = None
    for d_idx in candidate_days:
        # Next occurrence of this day at 00:00
        days_until = (d_idx - today_idx) % 7
        next_lock_day_midnight = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=days_until)
        if days_until == 0 and now.hour == 0 and now.minute == 0:
            pass  # exactly midnight — keep as-is
        lock_start = next_lock_day_midnight - timedelta(minutes=mins_before)
        # If we're currently inside (lock_start, next_lock_day_midnight), locked.
        if lock_start <= now < next_lock_day_midnight:
            return {
                "locked": True,
                "reason": (
                    f"{'Semi-weekly' if cadence == 'semi_weekly' else 'Weekly'} lock active "
                    f"— lineups freeze {mins_before} minute(s) before lock day. "
                    f"Try again after midnight."
                ),
                "next_unlock_iso": next_lock_day_midnight.isoformat(),
                "scope": cfg["scope"],
                "cadence": cadence,
            }
        if soonest_lock_in_window is None or lock_start < soonest_lock_in_window:
            soonest_lock_in_window = lock_start

    return {
        "locked": False,
        "reason": None,
        "next_unlock_iso": None,
        "scope": cfg["scope"],
        "cadence": cadence,
    }
