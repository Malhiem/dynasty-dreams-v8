"""Read-only audit for abuse of two draft-route holes that are now closed.

1. POST /drafts/{id}/auto-pick used to need only a login and had no clock
   check, so anyone could make picks for the team on the clock at any time.
2. POST /drafts/{league_id}/propose-pick-trade (and the vote route) used to
   need only a login, so anyone could propose or vote on trades for teams
   they did not own, with no consent from the receiving team.

The old code kept no record of who called either route, so this works from
what was stored: auto-picks carry `time_taken_seconds` and a source tag, and
pick trades carry `created_by` plus the list of voters. Findings are leads to
review, not proof; the web server's request logs for those routes are the
only place a caller IP or account can still be confirmed.

Usage (point MONGO_URL / DB_NAME at a read replica or the live DB; nothing is
written):

    python -m scripts.audit_draft_abuse [--since 2026-01-01] [--json out.json]

Severity: HIGH = strong sign of misuse, REVIEW = unusual, worth a look.
"""
import argparse
import asyncio
import json
import os
import sys
from collections import defaultdict
from datetime import datetime

from bson import ObjectId

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# A timeout pick should land after the full clock. Allow some slack for clock
# skew, the grace period and per-draft clock changes mid-pick.
EARLY_SLACK_SECONDS = 15
# Several auto-picks inside this window is the "rapid-fire" signature of
# someone looping the endpoint.
BURST_WINDOW_SECONDS = 10
BURST_MIN_PICKS = 3
# Sources that are legitimately allowed to fire before the full clock.
EARLY_OK_SOURCES = {"commissioner_skip", "eviction", "personal_timeout"}


def _ts(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def early_and_burst_auto_picks(draft: dict) -> list[dict]:
    """Findings for one draft's auto-picks: fired before the clock could have
    run out, or several in a few seconds."""
    findings = []
    per_pick = draft.get("time_per_pick")
    auto = [p for p in draft.get("picks") or [] if p.get("auto_picked")]
    for p in auto:
        source = p.get("auto_pick_source") or "timeout"  # older picks carry no tag
        taken = p.get("time_taken_seconds")
        if source in EARLY_OK_SOURCES or taken is None or not per_pick:
            continue
        if taken < int(per_pick) - EARLY_SLACK_SECONDS:
            findings.append({
                "severity": "HIGH", "kind": "early_auto_pick", "draft_id": str(draft["_id"]),
                "league_id": draft.get("league_id"), "overall": p.get("overall"), "team_id": p.get("team_id"),
                "detail": f"auto-picked after {taken}s on a {per_pick}s clock (source={source})",
                "timestamp": p.get("timestamp"),
            })
    stamped = sorted(((t, p) for p in auto if (t := _ts(p.get("timestamp")))), key=lambda x: x[0])
    for i in range(len(stamped)):
        j = i
        while j + 1 < len(stamped) and (stamped[j + 1][0] - stamped[i][0]).total_seconds() <= BURST_WINDOW_SECONDS:
            j += 1
        if j - i + 1 >= BURST_MIN_PICKS:
            first, last = stamped[i][1], stamped[j][1]
            findings.append({
                "severity": "REVIEW", "kind": "auto_pick_burst", "draft_id": str(draft["_id"]),
                "league_id": draft.get("league_id"), "overall": first.get("overall"),
                "detail": f"{j - i + 1} auto-picks within {BURST_WINDOW_SECONDS}s (picks {first.get('overall')}-{last.get('overall')})",
                "timestamp": first.get("timestamp"),
            })
            break  # one finding per draft is enough to open it
    return findings


def pick_trade_findings(trade: dict, league: dict | None, teams: dict, admins: set, member_ids: set) -> list[dict]:
    """Findings for one in-draft pick trade. `teams` maps team id -> doc,
    `member_ids` is every user id that belongs to the trade's league."""
    out = []
    base = {"trade_id": str(trade["_id"]), "league_id": trade.get("league_id"),
            "status": trade.get("status"), "timestamp": trade.get("created_at")}
    creator = str(trade.get("created_by") or "")
    prop = teams.get(str(trade.get("proposer_team_id")))
    recv = teams.get(str(trade.get("receiver_team_id")))

    if league is None or not prop or not recv:
        out.append({**base, "severity": "HIGH", "kind": "dangling_reference", "detail": "league or a team no longer exists"})
        return out
    if prop.get("league_id") != trade.get("league_id") or recv.get("league_id") != trade.get("league_id"):
        out.append({**base, "severity": "HIGH", "kind": "cross_league_team",
                    "detail": "a team in the trade belongs to a different league"})

    def acts_for(team):
        return creator and (str(team.get("owner_id")) == creator
                            or creator in {str(c) for c in team.get("co_owner_ids") or []})
    commissioners = {str(league.get("commissioner_id") or "")} | {
        str(x) for x in (league.get("co_commissioners") or []) + (league.get("admin_ids") or [])}
    if creator not in member_ids and creator not in admins:
        out.append({**base, "severity": "HIGH", "kind": "creator_not_in_league",
                    "detail": f"proposed by {creator or 'unknown'}, who is not a member of the league"})
    elif not acts_for(prop) and creator not in commissioners and creator not in admins:
        out.append({**base, "severity": "HIGH", "kind": "creator_not_on_proposing_team",
                    "detail": f"proposed by {creator}, who does not own or co-own the proposing team"})

    voters = {str(v) for v in (trade.get("votes") or {}).get("voters") or []}
    outsiders = sorted(v for v in voters if v not in member_ids and v not in admins)
    if outsiders:
        out.append({**base, "severity": "HIGH", "kind": "votes_from_non_members",
                    "detail": f"{len(outsiders)} vote(s) from non-members: {', '.join(outsiders[:5])}"})

    if trade.get("status") == "executed":
        owners = {str(recv.get("owner_id"))} | {str(c) for c in recv.get("co_owner_ids") or []}
        if creator not in owners and not (owners & voters):
            out.append({**base, "severity": "REVIEW", "kind": "executed_without_receiver_involvement",
                        "detail": "receiving team's owner neither proposed nor voted (consent was not required then)"})
    return out


async def run(db, since: str | None) -> dict:
    findings = []
    draft_q = {"picks.auto_picked": True}
    async for draft in db.drafts.find(draft_q):
        findings += early_and_burst_auto_picks(draft)

    trade_q = {"is_in_draft_pick_trade": True}
    if since:
        trade_q["created_at"] = {"$gte": since}
    admins = {str(u["_id"]) async for u in db.users.find({"$or": [{"role": "admin"}, {"is_admin": True}]}, {"_id": 1})}
    league_cache: dict = {}
    async for trade in db.trades.find(trade_q):
        lid = trade.get("league_id")
        if lid not in league_cache:
            try:
                league = await db.leagues.find_one({"_id": ObjectId(lid)})
            except Exception:
                league = None
            members = set()
            if league:
                members |= {str(league.get("commissioner_id") or "")}
                members |= {str(x) for x in (league.get("co_commissioners") or []) + (league.get("admin_ids") or [])}
                async for t in db.teams.find({"league_id": lid}, {"owner_id": 1, "co_owner_ids": 1}):
                    members.add(str(t.get("owner_id")))
                    members |= {str(c) for c in t.get("co_owner_ids") or []}
            league_cache[lid] = (league, members)
        league, members = league_cache[lid]
        teams = {}
        for key in ("proposer_team_id", "receiver_team_id"):
            try:
                t = await db.teams.find_one({"_id": ObjectId(str(trade.get(key)))})
            except Exception:
                t = None
            if t:
                teams[str(t["_id"])] = t
        findings += pick_trade_findings(trade, league, teams, admins, members)
    by_kind = defaultdict(int)
    for f in findings:
        by_kind[f"{f['severity']} {f['kind']}"] += 1
    return {"summary": dict(sorted(by_kind.items())), "findings": findings}


async def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--since", help="only pick trades created on/after this ISO date")
    parser.add_argument("--json", help="also write the full findings to this file")
    args = parser.parse_args()
    from motor.motor_asyncio import AsyncIOMotorClient
    mongo_url, db_name = os.environ.get("MONGO_URL"), os.environ.get("DB_NAME")
    if not (mongo_url and db_name):
        from dotenv import load_dotenv
        load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
        mongo_url, db_name = os.environ.get("MONGO_URL"), os.environ.get("DB_NAME")
    report = await run(AsyncIOMotorClient(mongo_url)[db_name], args.since)
    print(f"Database: {db_name}")
    if not report["findings"]:
        print("No findings.")
    for k, v in report["summary"].items():
        print(f"  {v:5d}  {k}")
    for f in sorted(report["findings"], key=lambda f: (f["severity"] != "HIGH", str(f.get("timestamp")))):
        ident = f.get("trade_id") or f.get("draft_id")
        print(f"[{f['severity']}] {f['kind']} league={f.get('league_id')} id={ident} {f['detail']}")
    if args.json:
        with open(args.json, "w") as fh:
            json.dump(report, fh, indent=2, default=str)
        print(f"Wrote {args.json}")


if __name__ == "__main__":
    asyncio.run(main())
