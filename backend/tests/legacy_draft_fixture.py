import os
import pytest
from bson import ObjectId
from pymongo import MongoClient

@pytest.fixture(scope="module", autouse=True)
def legacy_draft_inputs(_global_pollution_sweep):
    assert os.environ.get("TEST_SUITE_ISOLATED") == "1"
    with MongoClient(os.environ["MONGO_URL"]) as client:
        db = client[os.environ["DB_NAME"]]
        lid = "69e46af167999bfb85c39629"
        teams = list(db.teams.find({"league_id": lid}).sort("draft_position", 1))
        pids = [str(p["_id"]) for p in db.players.find({"_suite_baseline": True}).limit(10)]
        picks = [{"overall": i+1, "round": 1, "pick_in_round": i+1, "team_id": str(teams[i % len(teams)]["_id"]), "player_id": pid, "player": {"name": f"Fixture Player {i}"}, "auto_picked": True} for i,pid in enumerate(pids)]
        ids = [ObjectId("6a3c00447f735c0f8adc92f8"), ObjectId("6a408dbdd93ed14d3a8fb393")]
        for did in ids:
            db.drafts.insert_one({"_id": did, "league_id": lid, "name": "TEST_LegacyReader", "status": "completed", "total_rounds": 1, "current_pick": 11,
                "team_abbrs": [t["abbreviation"] for t in teams], "team_map": {t["abbreviation"]: {"id": str(t["_id"]), "name": t["name"]} for t in teams}, "picks": picks})
        yield
        db.drafts.delete_many({"_id": {"$in": ids}})
