"""Iter 192 — Create a new 32-team head-to-head league cloned from
`Ice Kings Head-to-Head`.

Requirements (user):
  - 32 teams
  - Identical settings to Ice Kings Head-to-Head
  - No rosters filled out — teams will conduct an entry draft set up
    by the League Admin
  - 45 rounds entry draft, reverse-serpentine order

Idempotent: if a league named `Ice Kings 32 Entry Draft` already
exists we skip (or you can pass `--reset` to delete and recreate).

Usage:
    cd /app/backend && python -m scripts.iter192_create_32_team_league
    cd /app/backend && python -m scripts.iter192_create_32_team_league --reset
"""
import asyncio
import os
import sys
from copy import deepcopy
from datetime import datetime, timezone

from bson import ObjectId
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")

SOURCE_LEAGUE = "Ice Kings Head-to-Head"
NEW_LEAGUE = "Ice Kings 32 Entry Draft"
TEAM_COUNT = 32
DRAFT_ROUNDS = 45

# 32 distinct team identities — name + 3-letter abbreviation. The
# Entry-Draft commissioner is free to rename these via the UI; we
# just need defaults that don't collide.
TEAM_SEEDS = [
    ("Arctic Wolves", "AWV"),
    ("Boreal Blizzards", "BBZ"),
    ("Capital Crashers", "CCR"),
    ("Diamond Dusters", "DDS"),
    ("Edge Enforcers", "EEN"),
    ("Frost Falcons", "FFC"),
    ("Glacier Grizzlies", "GGZ"),
    ("Hammer Hawks", "HHK"),
    ("Ice Vipers", "IVP"),
    ("Jet Jaguars", "JJG"),
    ("Krakens Krew", "KRK"),
    ("Lightning Lynx", "LLX"),
    ("Mountain Mavericks", "MMV"),
    ("Northern Nighthawks", "NNH"),
    ("Ozone Outlaws", "OOZ"),
    ("Polar Pirates", "PPI"),
    ("Quartz Quakes", "QQK"),
    ("Rapid Rebels", "RRB"),
    ("Stellar Sabres", "SSB"),
    ("Titan Thunder", "TTH"),
    ("Ultra Unicorns", "UUN"),
    ("Volt Vultures", "VVL"),
    ("Wild Whalers", "WWH"),
    ("Xenon Xtreme", "XXT"),
    ("Yukon Yetis", "YYT"),
    ("Zenith Zealots", "ZZL"),
    ("Aurora Archers", "AAR"),
    ("Blitz Bulldogs", "BBD"),
    ("Cobra Captains", "CCP"),
    ("Drift Demons", "DDM"),
    ("Echo Eagles", "EEG"),
    ("Frost Fury", "FFR"),
]

# Keys we DROP when cloning so they don't carry over identifiers / state.
KEYS_TO_DROP = {
    "_id",
    "name",
    "invite_code",
    "created_at",
    "current_season_status",
    "current_week",
    "season_renewed_at",
    "season_completed_at",
    "setup_wizard_complete",
    "setup_wizard_completed_at",
    "setup_wizard_completed_by",
    "first_draft_completed",
    "trade_deadline_at",  # admin will set a fresh one
    "audit_log",
    "constitution",
    "constitution_updated_at",
    "constitution_updated_by",
}


async def main(reset: bool = False) -> None:
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]

    source = await db.leagues.find_one({"name": SOURCE_LEAGUE})
    if not source:
        print(f"Source league '{SOURCE_LEAGUE}' not found — abort.")
        return

    existing = await db.leagues.find_one({"name": NEW_LEAGUE})
    if existing:
        if not reset:
            print(f"League '{NEW_LEAGUE}' already exists ({existing['_id']}) — re-run with --reset to wipe & recreate.")
            return
        eid = str(existing["_id"])
        print(f"--reset → wiping existing league {eid} and its child docs…")
        await db.leagues.delete_one({"_id": existing["_id"]})
        for coll in ("teams", "draft_picks", "rosters", "matchups", "activity_feed",
                     "waiver_claims", "trades", "draft_orders"):
            try:
                r = await db[coll].delete_many({"league_id": eid})
                print(f"  cleared {coll}: {r.deleted_count}")
            except Exception:
                pass

    # ── 1. Clone league doc ─────────────────────────────
    payload = {k: deepcopy(v) for k, v in source.items() if k not in KEYS_TO_DROP}
    now = datetime.now(timezone.utc)
    payload.update({
        "name": NEW_LEAGUE,
        "max_teams": TEAM_COUNT,
        "current_teams": TEAM_COUNT,
        "invite_code": f"IK32-{now.strftime('%Y%m%d-%H%M')}"[:24],
        "created_at": now,
        "status": "active",
        "current_season_status": "pre_draft",
        "current_week": 0,
        "first_draft_completed": False,
        "setup_wizard_complete": True,  # cloned from a complete league
        "constitution": "Cloned from Ice Kings Head-to-Head. Entry draft pending — commissioner to schedule.",
        "constitution_updated_at": now,
        "constitution_updated_by": source.get("commissioner_id"),
        # Iter 191/192 — Apply the user's preferred Draft Format defaults
        "next_draft_type": "snake",
        "draft_order_method": "reverse_standings",
        "draft_trade_review_minutes": 30,
        "draft_trade_post_delay_action": "auto_execute",
    })
    res = await db.leagues.insert_one(payload)
    new_lid = str(res.inserted_id)
    print(f"Created league '{NEW_LEAGUE}' → {new_lid}")

    # ── 2. Generate 32 teams (no rosters) ───────────────
    team_ids = []
    for idx, (name, abbr) in enumerate(TEAM_SEEDS):
        team_doc = {
            "league_id": new_lid,
            "name": name,
            "abbreviation": abbr,
            "owner_id": None,  # commissioner invites owners later
            "owner_name": None,
            "logo_url": None,
            "primary_color": "#1e293b",
            "secondary_color": "#94a3b8",
            "wins": 0,
            "losses": 0,
            "ties": 0,
            "points_for": 0,
            "points_against": 0,
            "salary_used": 0,
            "salary_committed": 0,
            "roster_players": [],  # empty — entry draft will populate
            "lineup": {},
            "draft_position": idx + 1,  # initial 1..32; admin can reshuffle
            "created_at": now,
            "is_pending": True,  # marks the team as awaiting owner assignment
            "sport": payload.get("sport", "nhl"),
        }
        ins = await db.teams.insert_one(team_doc)
        team_ids.append(str(ins.inserted_id))
    print(f"Created {len(team_ids)} teams (no rosters, no owners).")

    # ── 3. Reverse-serpentine 45-round draft order ──────
    # Reverse standings == team 1 picks 1.1, team 32 picks 1.32; then
    # round 2 reverses (team 32 picks 2.1, team 1 picks 2.32); and so on.
    picks = []
    for round_num in range(1, DRAFT_ROUNDS + 1):
        round_order = list(team_ids) if round_num % 2 == 1 else list(reversed(team_ids))
        for pick_in_round, team_id in enumerate(round_order, start=1):
            overall = (round_num - 1) * TEAM_COUNT + pick_in_round
            picks.append({
                "league_id": new_lid,
                "round": round_num,
                "pick_number": pick_in_round,
                "overall": overall,
                "original_team_id": team_id,
                "current_team_id": team_id,
                "original_team_name": next(s[0] for s in TEAM_SEEDS if str(team_ids[TEAM_SEEDS.index(next(t for t in TEAM_SEEDS if t[0] == s[0]))]) == team_id) if False else None,  # filled below
                "trade_history": [],
                "is_made": False,
                "player_id": None,
                "pending_protections": [],
            })
    # Now backfill original_team_name in one pass (the above generator
    # comprehension was a placeholder kept verbose-out).
    abbr_by_id = {tid: TEAM_SEEDS[i] for i, tid in enumerate(team_ids)}
    for p in picks:
        name, abbr = abbr_by_id[p["original_team_id"]]
        p["original_team_name"] = name
        p["original_team_abbr"] = abbr
        p["current_team_name"] = name
        p["current_team_abbr"] = abbr

    if picks:
        await db.draft_picks.insert_many(picks)
    print(f"Created {len(picks)} draft picks ({DRAFT_ROUNDS} rounds × {TEAM_COUNT} teams, reverse-serpentine).")

    print("Done.")


if __name__ == "__main__":
    reset = "--reset" in sys.argv
    asyncio.run(main(reset=reset))
