"""Deterministic baseline for the disposable Compose HTTP test suite only."""
import os
from functools import lru_cache
from datetime import datetime, timezone
from urllib.parse import urlparse
import bcrypt
from bson import ObjectId
from pymongo import MongoClient


@lru_cache(maxsize=4)
def _password_hash(password):
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def seed_disposable_suite(*, reset=False):
    if os.environ.get("TEST_SUITE_ISOLATED") != "1":
        return
    url = os.environ["MONGO_URL"]
    name = os.environ["DB_NAME"]
    if urlparse(url).hostname != "mongo" or name != "dynasty_dreams_e2e" or os.environ.get("REACT_APP_BACKEND_URL") != "http://web":
        raise RuntimeError("Suite baseline requires the dedicated disposable Compose network")
    client = MongoClient(url, serverSelectionTimeoutMS=5000)
    db = client[name]
    if reset:
        lids = [str(row["_id"]) for row in db.leagues.find({"_suite_baseline": True}, {"_id": 1})]
        for collection in ("teams", "matchups", "drafts", "draft_picks", "week_summaries", "team_contracts", "contracts", "retained_salaries", "salary_retentions", "buyout_schedules", "league_seasons", "waiver_claims", "scoring_configs", "player_ownership_periods", "lineup_status_periods"):
            db[collection].delete_many({"league_id": {"$in": lids}})
        db.leagues.delete_many({"_suite_baseline": True})
        db.players.delete_many({"_suite_baseline": {"$ne": True}})
        db.players.update_many({"_suite_baseline": True}, {"$set": {"goals": 20, "assists": 30, "points": 50, "shots": 120,
            "games_played": 60, "season_stats": {"goals": 20, "assists": 30, "shots": 120}, "period_stats": {}, "live_stats": {}}})
    now = datetime.now(timezone.utc)
    member_hash = _password_hash("e2e-member-password")
    owner_id = ObjectId()
    owner_email = os.environ.get("TEST_OWNER_EMAIL", "test-owner@e2e.dynastydreams.com")
    password = os.environ.get("TEST_OWNER_PASSWORD", "e2e-owner-password")
    db.users.update_one({"email": owner_email}, {"$setOnInsert": {"_id": owner_id}, "$set": {
        "username": "suite_owner", "name": "Fixture Owner", "role": "commissioner", "roles": ["commissioner"],
        "password_hash": _password_hash(password), "created_at": now,
        "_test_seed": False, "is_test_account": True}}, upsert=True)
    owner = db.users.find_one({"email": owner_email})
    admin = db.users.find_one({"email": os.environ["ADMIN_EMAIL"]})
    if not admin:
        raise RuntimeError("Start the isolated API before seeding suite fixtures")
    # These are explicitly synthetic test stats, never a copy of a user's database.
    if db.players.count_documents({"_suite_baseline": True}) == 0:
        players = []
        for i in range(1038):
            pos = ["C", "LW", "RW", "D", "G"][i % 5]
            players.append({"_id": ObjectId("69e43d98b80cbdcecf495275") if i == 0 else ObjectId(), "sport": "nhl", "season": "2025-2026", "name": ["Connor McDavid", "Alex Ovechkin", "Leon Draisaitl"][i] if i < 3 else f"Fixture Player {i:04d}",
                "nhl_id": [8478402,8471214,8477934][i] if i < 3 else 9000000+i, "position": pos, "player_type": "goalie" if pos == "G" else "skater", "team": ["EDM", "WSH", "TOR", "BOS"][i%4],
                "height_inches": 73, "weight_pounds": 200, "birth_date": "1997-01-13", "birth_country": "CAN", "nhl_seasons": 8, "draft_year": 2015, "draft_round": 1, "draft_overall": 1, "draft_team_abbr": "EDM",
                "age": 25, "goals": 20, "assists": 30, "points": 50, "shots": 120, "games_played": 60,
                "saves": 600 if pos == "G" else 0, "wins": 20 if pos == "G" else 0, "goals_against": 50 if pos == "G" else 0,
                "plus_minus": 0, "power_play_goals": 0, "power_play_points": 0, "shooting_pct": 0.0, "fantasy_points": 100, "season_stats": {"goals": 20, "assists": 30, "shots": 120},
                "contract": {"aav": 1000000, "salary": 1000000, "yearsRemaining": 3},
                "_test_seed": False, "_suite_baseline": True})
        # Six explicit draft classes support prospect filtering/watchlist tests.
        for i, year in enumerate(range(2020, 2026)):
            players[-1-i].update({"name": "Gavin McKenna" if i == 0 else f"Fixture Prospect {year}", "player_type": "prospect", "is_prospect": True,
                "drafted_by_team": ["EDM", "WSH", "TOR", "BOS", "NYR", "COL"][i], "draft_year": year, "draft_pick_overall": i+1, "position": "C", "age": 19, "career_games_played": 0, "minor_eligible": True})
        db.players.insert_many(players)
    pids = [str(p["_id"]) for p in db.players.find({"_suite_baseline": True})]
    from seed_demo_leagues import DEMO_LEAGUES
    fixed = {"Ice Kings Head-to-Head": "69e46af167999bfb85c39628", "Perennial Keepers": "69e46af167999bfb85c3962b", "Set-and-Forget Best Ball": "69e46af167999bfb85c3962c", "Stat Chasers Roto": "69e46af167999bfb85c39629", "Frozen Dynasty": "69e46af167999bfb85c3962a"}
    for index, template in enumerate(DEMO_LEAGUES):
        lid = ObjectId(fixed[template["name"]]) if template["name"] in fixed else ObjectId()
        count = template["max_teams"]
        db.leagues.update_one({"name": template["name"]}, {"$setOnInsert": {"_id": lid}, "$set": {
            **template, "current_teams": count, "commissioner_id": str(owner["_id"] if index == 0 else admin["_id"]), "commissioner_name": "Fixture Admin",
            "admin_ids": [str(owner["_id"])], "co_commissioners": [str(owner["_id"]), str(admin["_id"])], "invite_code": f"fixture-{index}", "status": "active", "created_at": now,
            "current_season_year": 2026, "regular_season_weeks": 18, "playoffs_enabled": True,
            "playoff_format": "playoff_tree", "playoff_start_week": 19, "playoff_end_week": 21, "playoff_rounds": 3, "playoff_teams": 8,
            "division_conference_map": {"North": "Test", "South": "Test"} if count == 14 else {},
            "_test_seed": False, "_suite_baseline": True}}, upsert=True)
        league = db.leagues.find_one({"name": template["name"]});lid=league["_id"]
        if db.teams.count_documents({"league_id": str(lid)}):
            continue
        for i in range(count):
            uid = owner["_id"] if i == 0 else admin["_id"] if i == 1 else ObjectId()
            if i > 1:
                existing_member = db.users.find_one({"email": f"fixture-{index}-{i}@e2e.dynastydreams.com"})
                if existing_member:
                    uid = existing_member["_id"]
                else:
                    db.users.insert_one({"_id": uid, "email": f"fixture-{index}-{i}@e2e.dynastydreams.com", "username": f"fixture_{index}_{i}", "name": f"Fixture Manager {i}", "password_hash": member_hash, "role": "user", "created_at": now, "_test_seed": False})
            division = ["North", "South"][i // 7] if count == 14 else ["Atlantic", "Metropolitan", "Central", "Pacific"][i // 4] if count == 16 else None
            conference = "Test" if count == 14 else ("Eastern" if i < 8 else "Western") if count == 16 else None
            tid = ObjectId("69e59b30cbd3fea02a914c61") if index == 0 and i == 0 else ObjectId("69e59b33cbd3fea02a914c79") if index == 1 and i == 0 else ObjectId("69e59b33cbd3fea02a914c7b") if index == 1 and i == 1 else ObjectId()
            db.teams.insert_one({"_id": tid, "league_id": str(lid), "owner_id": str(uid), "owner_name": "Fixture Owner" if i == 0 else f"Fixture Manager {i}",
                "name": "Ice Breakers" if index == 1 and i == 1 else f"Fixture {index} Team {i+1:02d}", "logo_abbr": f"F{i+1}", "abbreviation": f"F{i+1}", "draft_position": i+1,
                "division": division, "conference": conference, "roster": pids[i*20:(i+1)*20], "lineup": {}, "salary_used": 20000000,
                "wins": 0, "losses": 0, "ties": 0, "points_for": 0, "points_against": 0, "live_points": 0,
                "is_commissioner_team": i == 1, "created_at": now, "_test_seed": False})
    # Explicit five-round draft assets used by trade and pick-ownership tests.
    for league in db.leagues.find({"_suite_baseline": True}):
        lid = str(league["_id"])
        if db.draft_picks.count_documents({"league_id": lid}):
            continue
        picks = []
        for team in db.teams.find({"league_id": lid}):
            for year in (2026, 2027):
                for round_no in range(1, 6):
                    picks.append({"league_id": lid, "year": year, "round": round_no,
                        "original_team_id": str(team["_id"]), "original_team_name": team["name"],
                        "current_team_id": str(team["_id"]), "current_team_name": team["name"],
                        "trade_history": [], "_suite_baseline": True})
        if picks:
            db.draft_picks.insert_many(picks)
    client.close()
