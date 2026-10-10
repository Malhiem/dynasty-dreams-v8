"""Competition awards use frozen owner XP, never fantasy points."""
import os
import pytest
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient
from services.profile_competition import assessment, award, capture_week, award_fields
from services.profile_attribution import AWARDS, ownership_update, contributions
from utils.xp import compute_user_xp


@pytest.fixture
async def db():
    client = AsyncIOMotorClient(os.environ['MONGO_URL'])
    database = client[os.environ['DB_NAME'] + '_competition']
    await client.drop_database(database.name)
    yield database
    await client.drop_database(database.name)
    client.close()


@pytest.mark.parametrize('gap,multiplier', [(0,1), (199,1), (200,.75), (399,.75), (400,.5)])
def test_thresholds(gap, multiplier):
    assert assessment([50,50,50+gap])['multiplier'] == multiplier


def test_missing_evidence_and_rounding():
    assert assessment([None,900])['multiplier'] == 1
    assert assessment([900])['multiplier'] == 1
    assert award(75, {'multiplier':.75})['awarded_xp'] == 56


async def seed(db):
    lid, a, b, co = [str(ObjectId()) for _ in range(4)]
    await db.leagues.insert_one({'_id':ObjectId(lid),'current_season_year':2026})
    teams = [{'_id':ObjectId(),'league_id':lid,'owner_id':a,'co_owner_ids':[co]},
             {'_id':ObjectId(),'league_id':lid,'owner_id':b},
             {'_id':ObjectId(),'league_id':lid,'owner_id':str(ObjectId())}]
    await db.teams.insert_many(teams)
    await db.trades.insert_many([{'status':'executed','xp_user_ids':[co]} for _ in range(16)])
    matchup={'_id':ObjectId(),'league_id':lid,'week':1,'status':'scheduled',
             'home_team_id':str(teams[0]['_id']),'away_team_id':str(teams[1]['_id'])}
    await db.matchups.insert_one(matchup)
    return lid,a,b,co,teams,matchup


@pytest.mark.asyncio
async def test_capture_uses_highest_coowner_and_is_immutable(db):
    lid,a,b,co,teams,m = await seed(db)
    await capture_week(db,lid,[m])
    policy=m['xp_competition']
    assert policy['team_scores'][str(teams[0]['_id'])] == 450
    assert policy['multiplier'] == .5
    await db.trades.insert_many([{'status':'executed','xp_user_ids':[b]} for _ in range(30)])
    del m['xp_competition']
    await capture_week(db,lid,[m])
    assert m['xp_competition'] == policy


@pytest.mark.asyncio
async def test_adjusted_win_and_titles_survive_transfer_and_snapshot(db):
    lid,a,b,co,teams,m = await seed(db)
    await capture_week(db,lid,[m])
    tid=teams[0]['_id']
    await db.teams.update_one({'_id':tid},{'$inc':{'wins':1,'xp_win_adjustment':-10}})
    assert await compute_user_xp(db,a) == 60
    current=await db.teams.find_one({'_id':tid})
    new=str(ObjectId())
    await db.teams.update_one({'_id':tid},{'$set':ownership_update(current,{'owner_id':new,'co_owner_ids':[]})})
    fields=await award_fields(db,tid,{'division_winner_at':'2026-10-08'})
    await db.teams.update_one({'_id':tid},{'$set':fields})
    assert await compute_user_xp(db,a) == 60
    assert await compute_user_xp(db,new) == 125
    assert await compute_user_xp(db,co) == 460
    # Editing XP inputs later cannot recalculate an already earned title.
    await db.teams.update_one({'_id':tid},{'$set':{'xp_last_competition':{'multiplier':1},'points_for':999999}})
    repeated=await award_fields(db,tid,{'division_winner_at':'2026-10-09'})
    assert 'xp_award_adjustments.division_winner_at' not in repeated
    current=await db.teams.find_one({'_id':tid})
    await db.league_seasons.insert_one({'league_id':lid,'season_year':2026,'status':'complete',
        'teams':[{**current,'team_id':str(tid),'profile_contributions':contributions(current)}]})
    assert await compute_user_xp(db,new) == 125
    assert await compute_user_xp(db,a) == 60


@pytest.mark.asyncio
@pytest.mark.parametrize('field', list(AWARDS)[:5])
async def test_every_competitive_achievement_adjusted_once(db,field):
    lid,a,b,co,teams,m = await seed(db)
    await capture_week(db,lid,[m])
    tid=teams[0]['_id']
    fields=await award_fields(db,tid,{field:'2026-10-08'})
    await db.teams.update_one({'_id':tid},{'$set':fields})
    base=AWARDS[field][3]
    assert await compute_user_xp(db,a) == 50+int(base*.5)
    assert await compute_user_xp(db,co) == 450+int(base*.5)
    assert await award_fields(db,tid,{field:'2026-10-08'}) == {field:'2026-10-08'}


@pytest.mark.asyncio
async def test_participation_xp_unchanged_and_points_zero(db):
    lid,a,b,co,teams,m = await seed(db)
    await capture_week(db,lid,[m])
    tid=teams[0]['_id']
    await db.teams.update_one({'_id':tid},{'$set':{'points_for':1e9,'live_points':1e9}})
    await db.trades.insert_one({'status':'executed','xp_user_ids':[a,co]})
    await db.drafts.insert_one({'status':'completed','xp_user_ids':[a,co]})
    await db.waiver_claims.insert_one({'status':'won','xp_committed':True,'xp_user_ids':[a,co]})
    assert await compute_user_xp(db,a) == 120
    assert await compute_user_xp(db,co) == 520
