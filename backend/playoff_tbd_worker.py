"""Daily TBD-deadline scanner.

Every 6 hours, iterates every league and asks the existing
`check_playoff_tbd_deadlines` logic to fire notifications for any custom-bracket
week whose start is 0..2 days away and still has TBD slots.

The endpoint version (`POST /leagues/{id}/playoffs/check-tbd-deadlines`) covers
the on-demand case (admin opens settings); this background loop guarantees the
notification even if no admin visits in the deadline window.

Idempotent within 22h via the `tbd_deadline_pings` collection (same row the
endpoint inserts), so worker + endpoint can both run without doubling up.
"""
import asyncio
import logging
from datetime import datetime, date, timedelta, timezone

logger = logging.getLogger(__name__)


async def _scan_league(db, league: dict, *, create_notification) -> int:
    """Best-effort scan for one league. Returns the count of notifications fired."""
    matchup_len = int(league.get("matchup_length_days") or 7)
    season_start_str = league.get("season_start_date")
    if not season_start_str:
        return 0
    try:
        season_start = date.fromisoformat(season_start_str)
    except Exception:
        return 0
    today = date.today()
    recipients = [league["commissioner_id"]] + list(league.get("co_commissioners") or [])
    recipients = list(dict.fromkeys(recipients))
    league_id = str(league["_id"])
    fired = 0

    for bracket_key, label in (
        ("playoff_custom_matchups", "Playoff"),
        ("consolation_custom_matchups", "Consolation"),
    ):
        for entry in (league.get(bracket_key) or []):
            try:
                week = int(entry.get("week", 0))
            except Exception:
                continue
            if week <= 0:
                continue
            has_tbd = any(
                (m.get("home") in (None, "tbd", "")) or (m.get("away") in (None, "tbd", ""))
                for m in (entry.get("matchups") or [])
            )
            if not has_tbd:
                continue
            week_start = season_start + timedelta(days=(week - 1) * matchup_len)
            days_until = (week_start - today).days
            if not (0 <= days_until <= 2):
                continue

            recent = await db.tbd_deadline_pings.find_one({
                "league_id": league_id,
                "bracket": bracket_key,
                "week": week,
                "created_at": {"$gte": datetime.now(timezone.utc) - timedelta(hours=22)},
            })
            if recent:
                continue

            for uid in recipients:
                try:
                    await create_notification(
                        uid,
                        "playoff_tbd_deadline",
                        f"{label} bracket needs matchup setup",
                        (
                            f"Week {week} starts in {days_until} day"
                            f"{'s' if days_until != 1 else ''} and has TBD slots. "
                            "Configure the matchup ladder in Commissioner → League Structure."
                        ),
                        league_id,
                        f"/commissioner/settings?tab=divisions&focus={bracket_key}-week-{week}",
                    )
                    fired += 1
                except Exception as e:
                    logger.debug(f"TBD notify skipped for {uid}: {e}")
            await db.tbd_deadline_pings.insert_one({
                "league_id": league_id,
                "bracket": bracket_key,
                "week": week,
                "created_at": datetime.now(timezone.utc),
            })
    return fired


async def tbd_deadline_loop(db, create_notification, interval_seconds: int = 6 * 3600):
    """Long-running task — sleeps `interval_seconds` between scans."""
    while True:
        try:
            total_fired = 0
            scanned = 0
            async for league in db.leagues.find({"$or": [
                {"playoff_custom_matchups": {"$exists": True, "$ne": []}},
                {"consolation_custom_matchups": {"$exists": True, "$ne": []}},
            ]}):
                scanned += 1
                total_fired += await _scan_league(db, league, create_notification=create_notification)
            if scanned > 0:
                logger.info(f"TBD scanner: {scanned} leagues scanned, {total_fired} notifications fired")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.exception(f"TBD scanner cycle failed: {e}")
        try:
            await asyncio.sleep(interval_seconds)
        except asyncio.CancelledError:
            raise
