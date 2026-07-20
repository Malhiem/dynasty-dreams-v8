"""Iter 232N.65 — Full NHL API sync service.

Upgrades the previous `nhl_api` scaffold (which only pinged
statsapi.web.nhl.com/teams) into a real, concurrent fetch against the
current NHL public API at `api-web.nhle.com`.

Coverage (user pick "c" — full pool for dynasty leagues):
  • NHL active rosters for all 32 team codes
        /v1/roster/{TEAM}/current
  • Signed prospects per team (returns AHL / juniors / NCAA affiliations
    when the NHL publishes them)
        /v1/prospects/{TEAM}

We DO NOT write anything from this module. It only returns a normalized
list of player candidates that the admin route diffs against `db.players`
and then either dry-runs or applies. Keeping fetch + persist separate is
what makes the "Dry Run" flow honest.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timezone
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# 32 NHL team abbreviations (as accepted by api-web.nhle.com).
NHL_TEAM_CODES: list[str] = [
    "ANA", "BOS", "BUF", "CAR", "CBJ", "CGY", "CHI", "COL",
    "DAL", "DET", "EDM", "FLA", "LAK", "MIN", "MTL", "NJD",
    "NSH", "NYI", "NYR", "OTT", "PHI", "PIT", "SEA", "SJS",
    "STL", "TBL", "TOR", "UTA", "VAN", "VGK", "WPG", "WSH",
]

_API = "https://api-web.nhle.com"
_TIMEOUT = 12.0
_CONCURRENCY = 8   # be polite; api-web serves through Cloudflare.


def _compute_age(birth_date: str | None) -> int | None:
    if not birth_date:
        return None
    try:
        d = date.fromisoformat(birth_date[:10])
    except Exception:
        return None
    today = datetime.now(timezone.utc).date()
    years = today.year - d.year - ((today.month, today.day) < (d.month, d.day))
    return years if 15 <= years <= 60 else None


def _localized(field) -> str | None:
    """NHL API returns `{ 'default': 'Name', 'fr': ... }` for names /
    cities. Prefer default, tolerate raw strings."""
    if isinstance(field, dict):
        return field.get("default") or next(iter(field.values()), None)
    if isinstance(field, str):
        return field
    return None


def _parse_player(raw: dict, team_code: str, is_prospect: bool) -> dict | None:
    """Normalize one NHL API player object into our `players` schema.
    Returns None if the row is missing enough data to be useful."""
    nhl_id = raw.get("id")
    if not nhl_id:
        return None
    first = _localized(raw.get("firstName")) or ""
    last = _localized(raw.get("lastName")) or ""
    name = f"{first} {last}".strip()
    if not name:
        return None
    pos = raw.get("positionCode") or None
    # NHL API sometimes returns "L" / "R" for wings; normalize.
    if pos == "L":
        pos = "LW"
    elif pos == "R":
        pos = "RW"

    return {
        "nhl_id": str(nhl_id),
        "name": name,
        "position": pos,
        "team": team_code,
        "league": "NHL" if not is_prospect else "AHL/JUNIOR",
        "age": _compute_age(raw.get("birthDate")),
        "birth_date": raw.get("birthDate"),
        "birth_country": raw.get("birthCountry"),
        "shoots": raw.get("shootsCatches"),
        "is_prospect": bool(is_prospect),
        "headshot_url": raw.get("headshot"),
    }


async def _fetch_json(client: httpx.AsyncClient, path: str) -> dict | None:
    try:
        r = await client.get(f"{_API}{path}", follow_redirects=True)
        if r.status_code != 200:
            logger.info("nhl_sync: %s -> %s", path, r.status_code)
            return None
        return r.json()
    except Exception as e:
        logger.info("nhl_sync fetch failed %s: %s", path, str(e)[-120:])
        return None


async def _fetch_team(client: httpx.AsyncClient, sem: asyncio.Semaphore,
                      team: str) -> list[dict]:
    async with sem:
        roster_task = _fetch_json(client, f"/v1/roster/{team}/current")
        prosp_task = _fetch_json(client, f"/v1/prospects/{team}")
        roster, prosp = await asyncio.gather(roster_task, prosp_task)

    out: list[dict] = []
    for bucket in ("forwards", "defensemen", "goalies"):
        for raw in (roster or {}).get(bucket, []) or []:
            p = _parse_player(raw, team, is_prospect=False)
            if p:
                out.append(p)
        for raw in (prosp or {}).get(bucket, []) or []:
            p = _parse_player(raw, team, is_prospect=True)
            if p:
                out.append(p)
    return out


async def fetch_all_players(
    team_codes: Optional[list[str]] = None,
) -> tuple[list[dict], list[str]]:
    """Fetch every NHL roster + prospect list concurrently.

    Returns `(candidates, errors)` where `candidates` is a list of
    normalized player dicts and `errors` is a list of human-readable
    warnings (unreachable team endpoints, malformed responses).
    """
    codes = team_codes or NHL_TEAM_CODES
    sem = asyncio.Semaphore(_CONCURRENCY)
    errors: list[str] = []

    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        results = await asyncio.gather(
            *[_fetch_team(client, sem, code) for code in codes],
            return_exceptions=True,
        )

    candidates: list[dict] = []
    for code, res in zip(codes, results):
        if isinstance(res, Exception):
            errors.append(f"{code}: {str(res)[-100:]}")
            continue
        if not res:
            errors.append(f"{code}: empty response")
            continue
        candidates.extend(res)

    # Deduplicate on nhl_id (roster+prospect endpoints occasionally
    # double-list a callup); prefer the non-prospect record.
    dedup: dict[str, dict] = {}
    for c in candidates:
        key = c["nhl_id"]
        if key in dedup and not c.get("is_prospect"):
            dedup[key] = c
        elif key not in dedup:
            dedup[key] = c
    return list(dedup.values()), errors


# ─── Diff builder ─────────────────────────────────────────────────

# Fields we consider when computing a "team change" or "age change".
# Kept small on purpose — we don't want cosmetic diffs to spam the UI.
_DIFF_FIELDS = ("team", "position", "age", "is_prospect")


def build_diff(existing: list[dict], candidates: list[dict]) -> dict:
    """Compare candidates against the current `db.players` rows and
    bucket the differences.

    Returned shape:
      {
        "new_players":    [candidate,...],     # not present at all
        "age_changes":    [{old, new, ...}],
        "team_changes":   [{old, new, ...}],
        "position_changes":[{old, new, ...}],
        "prospect_changes":[{old, new, ...}],
        "removed":        [existing,...],      # in DB but not in feed
      }
    """
    by_id: dict[str, dict] = {}
    for e in existing:
        nid = str(e.get("nhl_id") or "")
        if nid:
            by_id[nid] = e

    seen: set[str] = set()
    new_players: list[dict] = []
    age_changes: list[dict] = []
    team_changes: list[dict] = []
    pos_changes: list[dict] = []
    prospect_changes: list[dict] = []

    for c in candidates:
        nid = c["nhl_id"]
        seen.add(nid)
        cur = by_id.get(nid)
        if not cur:
            new_players.append(c)
            continue
        if c.get("age") is not None and c["age"] != cur.get("age"):
            age_changes.append({
                "nhl_id": nid, "name": c["name"],
                "old_age": cur.get("age"), "new_age": c["age"],
                "existing_id": str(cur.get("_id") or cur.get("id") or ""),
            })
        if c.get("team") and c["team"] != cur.get("team"):
            team_changes.append({
                "nhl_id": nid, "name": c["name"],
                "old_team": cur.get("team"), "new_team": c["team"],
                "existing_id": str(cur.get("_id") or cur.get("id") or ""),
            })
        if c.get("position") and c["position"] != cur.get("position"):
            pos_changes.append({
                "nhl_id": nid, "name": c["name"],
                "old_position": cur.get("position"), "new_position": c["position"],
                "existing_id": str(cur.get("_id") or cur.get("id") or ""),
            })
        if bool(c.get("is_prospect")) != bool(cur.get("is_prospect")):
            prospect_changes.append({
                "nhl_id": nid, "name": c["name"],
                "old_is_prospect": bool(cur.get("is_prospect")),
                "new_is_prospect": bool(c.get("is_prospect")),
                "existing_id": str(cur.get("_id") or cur.get("id") or ""),
            })

    # A player is "removed" only if we had an nhl_id-tracked NHL row and
    # the current feed no longer contains it. Admin-added ("admin_*")
    # rows are always kept.
    removed: list[dict] = []
    for nid, e in by_id.items():
        if nid in seen:
            continue
        if nid.startswith("admin_"):
            continue
        removed.append({
            "nhl_id": nid,
            "name": e.get("name"),
            "team": e.get("team"),
            "existing_id": str(e.get("_id") or e.get("id") or ""),
        })

    return {
        "new_players": new_players,
        "age_changes": age_changes,
        "team_changes": team_changes,
        "position_changes": pos_changes,
        "prospect_changes": prospect_changes,
        "removed": removed,
        "counts": {
            "new_players": len(new_players),
            "age_changes": len(age_changes),
            "team_changes": len(team_changes),
            "position_changes": len(pos_changes),
            "prospect_changes": len(prospect_changes),
            "removed": len(removed),
            "existing_total": len(by_id),
            "feed_total": len(candidates),
        },
    }
