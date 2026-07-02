"""Iter 230f — Injury news scraper service.

Wraps the existing `fetch_nhl_news.py` script in an async-callable
service that can be invoked from a background worker (every 15 min) OR
the one-shot CLI. After upserting `player_news` rows, the service runs
each newly-matched headline through `_classify_injury_signal` and, when
the headline indicates an injury-status change, routes the diff through
`services.nhl_sync_dispatcher.apply_player_diff_and_notify` — same code
path the daily NHL roster sync uses.

Idempotency: only headlines published in the last `LOOKBACK_HOURS`
contribute to dispatcher signals, and the per-player-per-week dedup
collection `injury_news_signals` prevents the same headline from firing
notifications more than once.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from typing import Awaitable, Callable, Optional

import httpx

logger = logging.getLogger("injury_news")

RSS_FEEDS = [
    ("https://sports.yahoo.com/nhl/rss.xml",          "Yahoo Sports"),
    ("https://www.cbssports.com/rss/headlines/nhl/",  "CBS Sports"),
    ("https://www.sportingnews.com/us/rss/nhl",       "Sporting News"),
    ("https://thehockeywriters.com/feed/",            "The Hockey Writers"),
]

USER_AGENT = "Mozilla/5.0 (DynastyDreamsBot/1.0)"
LOOKBACK_HOURS = int(os.environ.get("INJURY_NEWS_LOOKBACK_HOURS", "24"))
DEFAULT_INTERVAL_SEC = int(os.environ.get("INJURY_NEWS_INTERVAL", str(15 * 60)))

# ── Keyword classifier ────────────────────────────────────────────────
#
# Each kind maps a (regex, suggested_injury_status) pair. The first
# matching kind wins per headline. Recovery has to win over injury when
# both appear ("returned from IR" beats "IR-listed last week").
INJURY_PATTERNS = [
    ("recovered", [
        re.compile(r"\b(returns?|returning|return\s+from)\b.{0,40}\b(injury|ir|injured\s+reserve|ltir)\b", re.I),
        re.compile(r"\b(activated\s+(off|from))\b.{0,30}\b(ir|injured\s+reserve|ltir)\b", re.I),
        re.compile(r"\b(cleared\s+to\s+play)\b", re.I),
        re.compile(r"\b(back\s+in\s+the\s+lineup)\b", re.I),
        re.compile(r"\b(activated)\b.{0,20}\b(from|off)\b", re.I),
    ], "Healthy"),
    ("injured", [
        re.compile(r"\bplaced\s+on\s+(ir|injured\s+reserve|ltir)\b", re.I),
        re.compile(r"\b(season-?ending|out\s+for\s+(the\s+)?season|out\s+indefinitely)\b", re.I),
        re.compile(r"\b(undergoes?|underwent)\s+(surgery|procedure)\b", re.I),
        re.compile(r"\b(suffer(s|ed)?|sustains?)\s+.{0,40}\b(injury|tear|fracture|break|concussion)\b", re.I),
        re.compile(r"\bout\s+(\d+\s+(weeks?|months?|games?))\b", re.I),
        re.compile(r"\bweek-to-week\b", re.I),
        re.compile(r"\b(injured|injury\s+update)\b", re.I),
    ], "IR"),
    ("injury_status_changed", [
        re.compile(r"\b(day-to-day|game-time\s+decision|questionable|probable|doubtful)\b", re.I),
        re.compile(r"\b(upgrade(d)?|downgrade(d)?)\s+to\b", re.I),
    ], "DTD"),
]


def _classify_injury_signal(haystack: str) -> Optional[tuple]:
    """Returns (change_kind, suggested_status) or None if no signal."""
    for kind, patterns, suggested in INJURY_PATTERNS:
        for p in patterns:
            if p.search(haystack):
                return (kind, suggested)
    return None


def _parse_pub_date(s: str) -> Optional[datetime]:
    try:
        dt = parsedate_to_datetime(s)
        if dt and dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


async def _build_lastname_index(db) -> dict:
    by_last: dict = {}
    async for p in db.players.find({}, {"name": 1}):
        name = (p.get("name") or "").strip()
        if not name:
            continue
        parts = name.split()
        last = parts[-1].lower() if parts else ""
        if last:
            by_last.setdefault(last, []).append({
                "player_id": str(p["_id"]),
                "name": name,
            })
    return by_last


def _match_players(haystack: str, by_last: dict) -> list:
    matched: list = []
    seen: set = set()
    for last_name, candidates in by_last.items():
        if len(last_name) < 4:
            continue
        if not re.search(rf"\b{re.escape(last_name)}\b", haystack):
            continue
        for c in candidates:
            if c["player_id"] in seen:
                continue
            parts = c["name"].split()
            first = parts[0].lower() if len(parts) > 1 else ""
            if len(candidates) > 1:
                if not first or first not in haystack:
                    continue
            matched.append(c)
            seen.add(c["player_id"])
    return matched


async def _fetch_feed(http: httpx.AsyncClient, url: str) -> Optional[list]:
    try:
        r = await http.get(url, timeout=15.0, headers={"User-Agent": USER_AGENT})
        if r.status_code != 200:
            return None
        root = ET.fromstring(r.content)
    except Exception as e:
        logger.debug("Feed %s fetch failed: %s", url, e)
        return None
    items = list(root.iter("item"))
    if not items:
        items = list(root.iter("{http://www.w3.org/2005/Atom}entry"))
    return items


def _atom_get(item, t):
    el = item.find(t)
    if el is None:
        el = item.find(f"{{http://www.w3.org/2005/Atom}}{t}")
    return (el.text or "").strip() if el is not None and el.text else ""


async def scrape_news_and_dispatch(
    db,
    *,
    create_notification: Optional[Callable[..., Awaitable]] = None,
    broadcast_fn: Optional[Callable[..., Awaitable]] = None,
) -> dict:
    """Single pass. Returns counts dict for observability + tests."""
    counts = {
        "headlines_scanned": 0,
        "headlines_matched": 0,
        "injury_signals": 0,
        "dispatched": 0,
        "deduped": 0,
    }
    # Iter 232N.4 — Every player_id we mutate this pass. Used at the
    # end to fan out real-time status-flag toasts.
    touched_pids: set[str] = set()
    by_last = await _build_lastname_index(db)
    if not by_last:
        return counts
    cutoff = datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)

    from services.nhl_sync_dispatcher import apply_player_diff_and_notify

    async with httpx.AsyncClient(headers={"User-Agent": USER_AGENT}) as http:
        for url, source in RSS_FEEDS:
            items = await _fetch_feed(http, url)
            if not items:
                continue
            for item in items:
                counts["headlines_scanned"] += 1
                title = _atom_get(item, "title")
                link = _atom_get(item, "link")
                if not link:
                    el = item.find("{http://www.w3.org/2005/Atom}link")
                    if el is not None:
                        link = (el.attrib.get("href") or "").strip()
                pub = _atom_get(item, "pubDate") or _atom_get(item, "published") or _atom_get(item, "updated")
                description = _atom_get(item, "description") or _atom_get(item, "summary")
                published_at = _parse_pub_date(pub) or datetime.now(timezone.utc)

                # Skip stale headlines.
                if published_at < cutoff:
                    continue

                haystack = f"{title} {description}".lower()

                # 1. Persist player_news (idempotent upsert).
                matched = _match_players(haystack, by_last)
                if not matched:
                    continue
                counts["headlines_matched"] += 1
                for m in matched:
                    await db.player_news.update_one(
                        {"player_id": m["player_id"], "url": link},
                        {"$set": {
                            "player_id": m["player_id"],
                            "headline": title,
                            "summary": description,
                            "url": link,
                            "source": source,
                            "published_at": published_at,
                            "ingested_at": datetime.now(timezone.utc),
                        }},
                        upsert=True,
                    )

                # 2. Classify + dispatch.
                signal = _classify_injury_signal(haystack)
                if not signal:
                    continue
                counts["injury_signals"] += 1
                change_kind, suggested_status = signal

                for m in matched:
                    # Per-player-per-headline dedup (keyed on url so the
                    # same article never fires twice across runs).
                    dedup_key = f"{m['player_id']}:{link}"
                    dedup_doc = await db.injury_news_signals.find_one({"key": dedup_key})
                    if dedup_doc:
                        counts["deduped"] += 1
                        continue
                    await db.injury_news_signals.update_one(
                        {"key": dedup_key},
                        {"$set": {
                            "key": dedup_key,
                            "player_id": m["player_id"],
                            "url": link,
                            "change_kind": change_kind,
                            "fired_at": datetime.now(timezone.utc),
                        }},
                        upsert=True,
                    )

                    # Patch the player's injury_status + fan out via the
                    # shared dispatcher. The dispatcher will only fire a
                    # notification if the status actually transitions.
                    try:
                        summary = await apply_player_diff_and_notify(
                            db,
                            player_id=m["player_id"],
                            new_fields={"injury_status": suggested_status},
                            create_notification=create_notification,
                            source={
                                "kind": "injury_news",
                                "publisher": source,
                                "url": link,
                                "headline": title,
                                "signal_type": change_kind,
                            },
                        )
                        touched_pids.add(str(m["player_id"]))
                        if summary.get("notifications_sent", 0) > 0 or summary.get("updated"):
                            counts["dispatched"] += 1
                    except Exception as e:
                        logger.exception("dispatch failed for %s: %s", m["player_id"], e)
    # Iter 232N.4 — Fan out real-time status-flag toasts for every
    # player whose injury_status we just mutated.
    if touched_pids and broadcast_fn is not None:
        try:
            from services.player_status_change_detector import detect_and_emit_status_changes
            det = await detect_and_emit_status_changes(
                db,
                list(touched_pids),
                broadcast_fn=broadcast_fn,
                create_notification_fn=create_notification,
            )
            counts["status_flag_events"] = len(det.get("events") or [])
        except Exception as e:
            logger.exception("injury_news status-flag detect failed: %s", e)

    logger.info("injury_news_scraper: %s", counts)
    return counts


async def injury_news_loop(
    db,
    create_notification: Callable[..., Awaitable],
    interval_sec: int = DEFAULT_INTERVAL_SEC,
    broadcast_fn: Optional[Callable[..., Awaitable]] = None,
):
    """Long-running asyncio task. Defers first pass by 120s so the rest
    of the app boots cleanly."""
    logger.info("Injury news scraper worker started (interval=%ds)", interval_sec)
    await asyncio.sleep(120)
    while True:
        try:
            await scrape_news_and_dispatch(
                db, create_notification=create_notification, broadcast_fn=broadcast_fn,
            )
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.exception("injury_news loop error: %s", e)
            await asyncio.sleep(300)
            continue
        await asyncio.sleep(interval_sec)
