"""Iter 174 — Roster compliance cleanup.

Audits every team's lineup, finds players assigned to the "minors"
section who are NOT actually minor-eligible per the league rules, and
moves them to "bench". Defensive and idempotent — re-running is a no-op.

Eligibility per Iter 173 is BINARY: a player is minor-eligible if and
only if `player_type == "prospect"` (or the explicit `minor_eligible`
flag is true). Veteran NHL skaters/goalies — regardless of how few
season games they've played — do not belong in minors slots.

This matches the user-visible Minor-eligible badge surfaced by the
Player Card + Draft Room (Iter 173). The legacy gp/age heuristic in
`routes/lineup.py::get_team_compliance` is left untouched for now so
existing pytest suites don't regress; this script is the authoritative
cleanup pass.

Why bench? Bench has no eligibility predicate, fits any veteran, and
preserves the team's roster ordering. If bench is already at cap the
script logs a warning and leaves the player in minors so the manager
sees the compliance issue and can rebalance manually.

Usage:
    python -m scripts.iter174_compliance_cleanup --dry-run
    python -m scripts.iter174_compliance_cleanup
    python -m scripts.iter174_compliance_cleanup --league <league_id>
"""
import argparse
import asyncio
import os
from datetime import datetime, timezone

from bson import ObjectId
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")


def _age_of(player: dict):
    bd = player.get("birth_date")
    if not bd:
        return None
    try:
        bd_dt = datetime.fromisoformat(bd.split("T")[0]) if isinstance(bd, str) else bd
        return (datetime.now(timezone.utc).replace(tzinfo=None) - bd_dt).days // 365
    except Exception:
        return None


async def _process_team(db, team, league, dry_run: bool, summary: dict) -> int:
    lineup = team.get("lineup") or {}
    if not lineup:
        return 0
    minors_pids = [pid for pid, info in lineup.items()
                   if isinstance(info, dict)
                   and (info.get("section") or "").lower() == "minors"]
    if not minors_pids:
        return 0

    max_age = int(league.get("minors_max_age") or 22)
    max_games = int(league.get("minors_max_career_games") or 25)
    bench_cap = int(league.get("bench_spots") or 0)

    try:
        obj_ids = [ObjectId(pid) for pid in minors_pids]
    except Exception:
        return 0
    players = {str(p["_id"]): p for p in
               await db.players.find({"_id": {"$in": obj_ids}}).to_list(None)}

    moved = 0
    bench_used = sum(
        1 for pid, info in lineup.items()
        if isinstance(info, dict) and (info.get("section") or "").lower() == "bench"
    )
    for pid in minors_pids:
        p = players.get(pid)
        if not p:
            continue
        gp = int(p.get("games_played") or 0)
        age = _age_of(p) if p.get("birth_date") else p.get("age")
        # Iter 173 binary eligibility: minors slot is for prospects ONLY.
        # Anything else (skater, goalie, NHL veteran) gets bumped to bench.
        player_type = (p.get("player_type") or "skater").lower()
        is_prospect = player_type == "prospect" or bool(p.get("minor_eligible"))
        if is_prospect:
            continue
        # Bench cap guard. 0 = unbounded.
        if bench_cap > 0 and bench_used >= bench_cap:
            summary["bench_full"].append({
                "team_id": str(team["_id"]),
                "team_name": team.get("name"),
                "player_id": pid,
                "player_name": p.get("name"),
            })
            continue
        # Move to bench.
        lineup[pid] = {"section": "bench", "slot": "BN"}
        bench_used += 1
        moved += 1
        summary["moves"].append({
            "team_id": str(team["_id"]),
            "team_name": team.get("name"),
            "player_id": pid,
            "player_name": p.get("name") or p.get("full_name"),
            "position": p.get("position"),
            "games_played": gp,
            "age": age,
            "player_type": player_type,
            "from": "minors",
            "to": "bench",
        })

    if moved and not dry_run:
        await db.teams.update_one(
            {"_id": team["_id"]},
            {"$set": {"lineup": lineup, "lineup_updated_at": datetime.now(timezone.utc)}},
        )
    return moved


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--league", default=None, help="Restrict to a single league_id")
    parser.add_argument("--dry-run", action="store_true", help="Audit only — do not write")
    args = parser.parse_args()

    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]

    leagues_query = {"_id": ObjectId(args.league)} if args.league else {}
    leagues = await db.leagues.find(leagues_query).to_list(None)
    print(f"Auditing {len(leagues)} league(s)…")

    summary = {"moves": [], "bench_full": []}
    total_moved = 0
    for league in leagues:
        league_id = str(league["_id"])
        teams = await db.teams.find({"league_id": league_id}).to_list(None)
        for team in teams:
            moved = await _process_team(db, team, league, args.dry_run, summary)
            total_moved += moved
            if moved:
                print(
                    f"  [{league.get('name')}] {team.get('name')}: "
                    f"{moved} ineligible player(s) bumped from minors → bench"
                )

    print()
    print(f"== Iter 174 cleanup complete{' (DRY RUN)' if args.dry_run else ''} ==")
    print(f"Total moves: {total_moved}")
    if summary["bench_full"]:
        print(
            f"\n⚠️  {len(summary['bench_full'])} player(s) could not be moved because "
            f"bench was already at cap:"
        )
        for x in summary["bench_full"]:
            print(f"  - {x['team_name']:30s} · {x['player_name']:25s} (manager must rebalance)")
    if total_moved == 0 and not summary["bench_full"]:
        print("✓ All rosters already compliant.")


if __name__ == "__main__":
    asyncio.run(main())
