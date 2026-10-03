"""
Read-only verification that the TFHL data-heal performed by the main agent persisted.

Expected state (per review_request):
- League: TFHL
- Inaugural draft: total_rounds=55, picks rounds 1-55
- Summer Entry: total_rounds=4, picks rounds 1-4 only (was 29; healed down to 4)
- Winter: total_rounds=2, picks rounds 1-2

Note: TFHL stores ids via Mongo `_id` (ObjectId); foreign refs use stringified
ObjectId. Test only does reads.
"""
import os
import pytest
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv('/app/backend/.env')

MONGO_URL = os.environ['MONGO_URL']
DB_NAME = os.environ['DB_NAME']


@pytest.fixture
async def db():
    client = AsyncIOMotorClient(MONGO_URL)
    database = client[DB_NAME]
    if not await database.leagues.find_one({"name": "TFHL"}):
        client.close()
        pytest.skip("Historical TFHL repair verification requires an explicit TFHL snapshot; the disposable application suite has none")
    yield database
    client.close()


def _did(d):
    return d.get('id') or str(d.get('_id'))


@pytest.mark.asyncio
async def test_tfhl_league_exists(db):
    league = await db.leagues.find_one({"name": "TFHL"})
    assert league is not None, "TFHL league must exist"


@pytest.mark.asyncio
async def test_tfhl_target_drafts_total_rounds(db):
    league = await db.leagues.find_one({"name": "TFHL"})
    lid = league.get('id') or str(league['_id'])

    drafts = await db.drafts.find({"league_id": lid}).to_list(length=50)
    by_name = {d.get('name'): d for d in drafts if d.get('name')}

    assert 'TFHL Inaugural Draft' in by_name
    assert 'TFHL Summer Entry Draft' in by_name
    assert 'TFHL Winter Draft' in by_name

    assert by_name['TFHL Inaugural Draft'].get('total_rounds') == 55
    assert by_name['TFHL Summer Entry Draft'].get('total_rounds') == 4
    assert by_name['TFHL Winter Draft'].get('total_rounds') == 2, (
        f"Winter total_rounds expected 2 (was 55 pre-heal) got "
        f"{by_name['TFHL Winter Draft'].get('total_rounds')}"
    )


@pytest.mark.asyncio
async def test_tfhl_pick_counts_and_round_bounds(db):
    league = await db.leagues.find_one({"name": "TFHL"})
    lid = league.get('id') or str(league['_id'])
    n_teams = await db.teams.count_documents({"league_id": lid})
    assert n_teams >= 1, f"TFHL teams count={n_teams}"

    drafts = await db.drafts.find({"league_id": lid}).to_list(length=50)
    by_name = {d.get('name'): d for d in drafts if d.get('name')}

    targets = {
        'TFHL Inaugural Draft': (55, list(range(1, 56))),
        'TFHL Summer Entry Draft': (4, [1, 2, 3, 4]),
        'TFHL Winter Draft': (2, [1, 2]),
    }
    for name, (rounds_expected, round_list) in targets.items():
        d = by_name[name]
        did = _did(d)
        cnt = await db.draft_picks.count_documents({"league_id": lid, "draft_id": did})
        assert cnt == rounds_expected * n_teams, (
            f"{name}: picks expected {rounds_expected * n_teams} got {cnt}"
        )
        rounds_seen = sorted(
            r for r in await db.draft_picks.distinct(
                "round", {"league_id": lid, "draft_id": did}
            ) if r is not None
        )
        assert rounds_seen == round_list, (
            f"{name}: rounds expected {round_list} got {rounds_seen}"
        )


@pytest.mark.asyncio
async def test_tfhl_summer_no_high_round_orphans(db):
    """The user-reported bug: Summer Entry showed 29 picks (rounds extending beyond 4).
    Post-heal there must be ZERO picks for the Summer Entry draft with round > 4."""
    league = await db.leagues.find_one({"name": "TFHL"})
    lid = league.get('id') or str(league['_id'])
    d = await db.drafts.find_one({"league_id": lid, "name": "TFHL Summer Entry Draft"})
    did = _did(d)
    high = await db.draft_picks.count_documents({
        "league_id": lid, "draft_id": did, "round": {"$gt": 4}
    })
    assert high == 0, f"Summer Entry must have NO picks with round>4, found {high}"


@pytest.mark.asyncio
async def test_tfhl_winter_no_high_round_orphans(db):
    """Winter total_rounds was healed to 2 — no picks should have round > 2."""
    league = await db.leagues.find_one({"name": "TFHL"})
    lid = league.get('id') or str(league['_id'])
    d = await db.drafts.find_one({"league_id": lid, "name": "TFHL Winter Draft"})
    did = _did(d)
    high = await db.draft_picks.count_documents({
        "league_id": lid, "draft_id": did, "round": {"$gt": 2}
    })
    assert high == 0, f"Winter must have NO picks with round>2, found {high}"
