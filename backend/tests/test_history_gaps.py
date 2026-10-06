"""History privacy and season-frozen award scoring regressions."""
import pytest
from bson import ObjectId
from fastapi import HTTPException
from routes import seasons
from services.fantasy_scoring import calculate_fantasy_points
from tests.router_test_utils import isolated_router_app, seed_league, seed_team
from tests.test_history_access import seed


@pytest.mark.asyncio
async def test_career_auth_before_lookup():
    async with isolated_router_app(seasons) as ctx:
        async def deny(_request):
            raise HTTPException(status_code=401, detail="Not authenticated")
        seasons._deps['get_current_user'] = deny
        for pid in (str(ObjectId()), 'not-an-id'):
            assert (await ctx.client.get(f'/api/players/{pid}/dynasty-career')).status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize('role', ['commissioner','co_commissioner','league_owner','league_admin','team_owner','team_co_owner','platform_admin','outsider'])
async def test_career_filters_private_leagues_and_totals(role):
    user = {'_id':str(ObjectId()),'roles':['admin'] if role == 'platform_admin' else ['user']}
    async with isolated_router_app(seasons,user=user) as ctx:
        own, tid = await seed(ctx.db,user,role)
        hidden, other_tid = await seed(ctx.db,{'_id':str(ObjectId())},'commissioner')
        pid = str(ObjectId())
        for lid, team in [(own,tid),(hidden,other_tid)]:
            await ctx.db.league_seasons.update_one({'league_id':lid}, {'$set':{
                'players':[{'player_id':pid,'name':'Private player','position':'C','season_stats':{'points':50}}],
                'teams':[{'team_id':team,'team_name':'Private franchise','roster':[pid],'points_for':100}],
                'champion_team_name':'Private franchise'}})
        response = await ctx.client.get(f'/api/players/{pid}/dynasty-career')
        assert response.status_code == 200
        body = response.json()
        allowed = [own,hidden] if role == 'platform_admin' else [] if role == 'outsider' else [own]
        assert {h['league_id'] for h in body['history']} == set(allowed)
        assert body['totals'] == {'seasons':len(allowed),'leagues':len(allowed),'awards':len(allowed),'championships':len(allowed)}


@pytest.mark.asyncio
@pytest.mark.parametrize('format', ['h2h-points','h2h-categories','rotisserie'])
@pytest.mark.parametrize('automatic', [False,True])
async def test_snapshot_freezes_configured_awards_across_all_views(format, automatic):
    async with isolated_router_app(seasons) as ctx:
        lid = await seed_league(ctx.db)
        tid = await seed_team(ctx.db,league_id=lid)
        await ctx.db.leagues.update_one({'_id':ObjectId(lid)}, {'$set':{'scoring_format':format,'current_season_year':2026}})
        config = {'skater_scoring':{'goals':1,'shots':3},'goalie_scoring':{'wins':1,'saves':2}}
        await ctx.db.scoring_configs.insert_one({'league_id':lid,**config})
        rows=[('C',{'goals':2,'shots':0,'points':100}),('C',{'goals':0,'shots':10,'points':50}),('D',{'goals':1,'shots':9,'points':25}),('G',{'wins':10,'saves':0}),('G',{'wins':0,'saves':100})]
        ids=[]
        for i,(position,stats) in enumerate(rows):
            oid=ObjectId();ids.append(str(oid))
            await ctx.db.players.insert_one({'_id':oid,'name':f'Award player {i}','position':position,'salary':1000000,'season_stats':stats})
        await ctx.db.teams.update_one({'_id':ObjectId(tid)},{'$set':{'roster':ids,'championship_won_at':'2026-01-01','points_for':100}})
        if automatic:
            await ctx.db.matchups.insert_one({'league_id':lid,'is_playoff':True,'week':1,'status':'completed'})
            assert await seasons._maybe_auto_snapshot_season(lid)
        else:
            response=await ctx.client.post(f'/api/leagues/{lid}/complete-season',json={'season_year':2026})
            assert response.status_code==200,response.text
        snap=await ctx.db.league_seasons.find_one({'league_id':lid,'season_year':2026})
        assert snap['scoring_config']==config
        # Later rule/stat changes must not rewrite historical scores or winners.
        await ctx.db.scoring_configs.update_one({'league_id':lid},{'$set':{'skater_scoring':{'goals':100},'goalie_scoring':{'wins':100}}})
        await ctx.db.players.update_many({}, {'$set':{'season_stats':{'goals':999}}})
        league=(await ctx.client.get(f'/api/leagues/{lid}/trophy-room')).json()['seasons'][0]
        for key,index,score in [('season_mvp',1,30),('best_defenseman',2,28),('best_goalie',4,200)]:
            assert league[key]['player_id']==ids[index]
            assert league[key]['points']==score
            assert league[key]['scoring_basis']=='season_weights'
        team=(await ctx.client.get(f'/api/teams/{tid}/trophy-room')).json()
        assert {a['player_id'] for a in team['individual_awards']}=={ids[1],ids[2],ids[4]}
        career=(await ctx.client.get(f'/api/players/{ids[1]}/dynasty-career')).json()['history'][0]
        assert career['fantasy_points']==30 and career['scoring_basis']=='season_weights'


def test_legacy_snapshot_estimate_remains_identifiable():
    card=seasons._build_season_trophies({'players':[{'player_id':'p','name':'Legacy','position':'C','season_stats':{'points':50,'plus_minus':10}}]})['season_mvp']
    assert card['points']==51 and card['scoring_basis']=='legacy_estimate'


def test_canonical_default_scoring_unchanged():
    assert calculate_fantasy_points({'position':'C','goals':2,'assists':3,'shots':4})==14
    assert calculate_fantasy_points({'position':'G','wins':2,'losses':1,'saves':20,'goals_against':3,'shutouts':1})==12
