"""Fetch real NHL news from ESPN's public RSS feed and persist into the
`player_news` collection. Headlines are matched to existing players by exact
last-name + first-name substring presence in the headline.

Idempotent — re-running upserts based on `(player_id, source_url)`.

Why ESPN RSS? It's free, public, no API key needed, and updated frequently.
We only persist news where we can confidently link a player_id; everything else
is dropped. Use a CRON or just re-run after a roster change.

Usage:
    python /app/backend/fetch_nhl_news.py
"""
import asyncio
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import requests
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import dotenv_values


RSS_FEEDS = [
    # Free public NHL news feeds (ESPN blocks with CloudFront WAF; skip it)
    ("https://sports.yahoo.com/nhl/rss.xml",                   "Yahoo Sports"),
    ("https://www.cbssports.com/rss/headlines/nhl/",           "CBS Sports"),
    ("https://www.sportingnews.com/us/rss/nhl",                "Sporting News"),
    ("https://thehockeywriters.com/feed/",                     "The Hockey Writers"),
]


USER_AGENT = "Mozilla/5.0 (DynastyDreamsBot/1.0)"


def _parse_pub_date(s: str) -> datetime | None:
    try:
        dt = parsedate_to_datetime(s)
        if dt and dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


async def main() -> None:
    env = dotenv_values("/app/backend/.env")
    client = AsyncIOMotorClient(env["MONGO_URL"])
    db = client[env["DB_NAME"]]

    # Build a name -> player_id index. Match in headline order: last name first
    # (more discriminating), then full name, then "F. Last".
    by_last: dict[str, list[dict]] = {}
    async for p in db.players.find({}, {"name": 1, "team": 1, "position": 1}):
        name = (p.get("name") or "").strip()
        if not name:
            continue
        parts = name.split()
        last = parts[-1].lower() if parts else ""
        if last:
            by_last.setdefault(last, []).append({
                "player_id": str(p["_id"]),
                "name": name,
                "team": p.get("team"),
            })

    print(f"Indexed {sum(len(v) for v in by_last.values())} players")

    inserted = 0
    skipped = 0
    for feed_url, feed_source in RSS_FEEDS:
        try:
            resp = requests.get(feed_url, timeout=10, headers={"User-Agent": USER_AGENT})
            resp.raise_for_status()
        except Exception as e:
            print(f"Feed {feed_url} fetch failed: {e}")
            continue
        try:
            root = ET.fromstring(resp.content)
        except Exception as e:
            print(f"Feed {feed_url} parse failed: {e}")
            continue

        items = list(root.iter("item"))
        if not items:
            # Atom fallback
            ns = {"a": "http://www.w3.org/2005/Atom"}
            items = list(root.iter("{http://www.w3.org/2005/Atom}entry"))

        feed_inserted = 0
        for item in items:
            def _get(t):
                el = item.find(t)
                if el is None:
                    el = item.find(f"{{http://www.w3.org/2005/Atom}}{t}")
                return (el.text or "").strip() if el is not None and el.text else ""

            title = _get("title")
            link = _get("link")
            if not link:
                # Atom <link href="...">
                el = item.find("{http://www.w3.org/2005/Atom}link")
                if el is not None:
                    link = (el.attrib.get("href") or "").strip()
            pub = _get("pubDate") or _get("published") or _get("updated")
            description = _get("description") or _get("summary")
            published_at = _parse_pub_date(pub) or datetime.now(timezone.utc)

            haystack = f"{title} {description}".lower()

            # Find every player whose last name appears as a whole word in the headline
            matched: list[dict] = []
            seen_pids = set()
            for last_name, candidates in by_last.items():
                if len(last_name) < 4:
                    continue  # skip ambiguous short surnames
                if not re.search(rf"\b{re.escape(last_name)}\b", haystack):
                    continue
                for c in candidates:
                    if c["player_id"] in seen_pids:
                        continue
                    # Disambiguate when multiple players share a surname by
                    # requiring the first name (or initial) to also appear.
                    parts = c["name"].split()
                    first = parts[0].lower() if len(parts) > 1 else ""
                    if len(candidates) > 1:
                        if not first or first not in haystack:
                            continue
                    matched.append(c)
                    seen_pids.add(c["player_id"])

            if not matched:
                skipped += 1
                continue

            for m in matched:
                # Upsert keyed on (player_id, url) so a repeated feed pull is no-op
                await db.player_news.update_one(
                    {"player_id": m["player_id"], "url": link},
                    {"$set": {
                        "player_id": m["player_id"],
                        "headline": title,
                        "summary": description,
                        "url": link,
                        "source": feed_source,
                        "published_at": published_at,
                        "ingested_at": datetime.now(timezone.utc),
                    }},
                    upsert=True,
                )
                inserted += 1
                feed_inserted += 1
        print(f"  {feed_source}: {feed_inserted} matches")

    print(f"News upserts: {inserted} · headlines skipped (no matches): {skipped}")


if __name__ == "__main__":
    asyncio.run(main())
