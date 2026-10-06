"""Incomplete snapshots, champion IDs, shared awards, archived franchises and ranks."""
import pytest
from bson import ObjectId
from fastapi import HTTPException
from routes import seasons
from services import season_history
from tests.router_test_utils import isolated_router_app, seed_league, seed_team


async def finish(ctx,lid,automatic):
    if automatic:
        await ctx.db.matchups.insert_one({'league_id':lid,'week':1,'is_playoff':True,'status':'completed'})
        return await seasons._maybe_auto_snapshot_season(lid)
    response=await ctx.client.post(f'/api/leagues/{lid}/complete-season',json={'season_year':2026})
    assert response.status_code==200,response.text
    return response.json()


@pytest.mark.asyncio
@pytest.mark.parametrize('automatic',[False,True])
@pytest.mark.parametrize('fault',['missing','malformed','read_failure'])
async def test_invalid_player_capture_preserves_prior_snapshot_and_status(automatic,fault,monkeypatch):
    async with isolated_router_app(seasons) as ctx:
        lid=await seed_league(ctx.db);tid=await seed_team(ctx.db,league_id=lid)
        await ctx.db.leagues.update_one({'_id':ObjectId(lid)},{'$set':{'current_season_year':2026,'current_season_status':'in_progress'}})
        await ctx.db.teams.update_one({'_id':ObjectId(tid)},{'$set':{'roster':['malformed' if fault=='malformed' else str(ObjectId())]}})
        await ctx.db.league_seasons.insert_one({'league_id':lid,'season_year':2026,'status':'complete','sentinel':'preserve'})
        if fault=='read_failure':
            collection_type=type(ctx.db.players);original=collection_type.find
            def fail(collection,*args,**kwargs):
                if collection.name=='players':raise RuntimeError('Transient player database failure')
                return original(collection,*args,**kwargs)
            monkeypatch.setattr(collection_type,'find',fail)
        if automatic:
            await ctx.db.matchups.insert_one({'league_id':lid,'week':1,'is_playoff':True,'status':'completed'})
            with pytest.raises(HTTPException) as exc:await seasons._maybe_auto_snapshot_season(lid)
            status=exc.value.status_code
        else:
            status=(await ctx.client.post(f'/api/leagues/{lid}/complete-season',json={'season_year':2026})).status_code
        assert status==(503 if fault=='read_failure' else 409)
        snap=await ctx.db.league_seasons.find_one({'league_id':lid})
        assert snap['sentinel']=='preserve' and 'players' not in snap
        league=await ctx.db.leagues.find_one({'_id':ObjectId(lid)})
        assert league['current_season_status']=='in_progress'
        assert 'season_completed_at' not in league
        assert not (await ctx.db.teams.find_one({'_id':ObjectId(tid)})).get('championship_won_at')


@pytest.mark.asyncio
@pytest.mark.parametrize('automatic',[False,True])
async def test_champion_id_survives_duplicate_names_and_inconsistent_flags(automatic):
    async with isolated_router_app(seasons) as ctx:
        lid=await seed_league(ctx.db)
        a=await seed_team(ctx.db,league_id=lid,name='Same franchise name');b=await seed_team(ctx.db,league_id=lid,name='Same franchise name')
        await ctx.db.leagues.update_one({'_id':ObjectId(lid)},{'$set':{'current_season_year':2026}})
        pid=str((await ctx.db.players.insert_one({'name':'Owned player','position':'C','salary':1000000,'season_stats':{'goals':1}})).inserted_id)
        await ctx.db.teams.update_one({'_id':ObjectId(b)},{'$set':{'championship_won_at':'2026-01-01','roster':[pid]}})
        await finish(ctx,lid,automatic)
        snap=await ctx.db.league_seasons.find_one({'league_id':lid});assert snap['champion_team_id']==b
        assert (await ctx.db.teams.find_one({'_id':ObjectId(b)}))['championship_won_at']=='2026-01-01'
        # ID remains authoritative even when legacy flags/name disagree after import.
        saved=snap['teams'];saved[0]['awards']['championship_won_at']='2026-01-01';saved[1]['awards']['championship_won_at']=None
        await ctx.db.league_seasons.update_one({'_id':snap['_id']},{'$set':{'teams':saved,'champion_team_name':'Wrong name'}})
        league=(await ctx.client.get(f'/api/leagues/{lid}/trophy-room')).json();assert league['seasons'][0]['champion']['team_id']==b
        for tid,expected in [(a,False),(b,True)]:
            body=(await ctx.client.get(f'/api/teams/{tid}/trophy-room')).json()
            assert any(x['type']=='championship' for x in body['banners'])==expected
        career=(await ctx.client.get(f'/api/players/{pid}/dynasty-career')).json()
        assert career['history'][0]['champion'] is True


def test_legacy_duplicate_champion_names_never_pick_arbitrarily():
    snap={'champion_team_name':'Same','teams':[{'team_id':'a','team_name':'Same'},{'team_id':'b','team_name':'Same'}]}
    card=seasons._build_season_trophies(snap);assert card['champion'] is None and card['champion_status']=='ambiguous'
    snap['teams'][1]['awards']={'championship_won_at':'2026-01-01'}
    assert seasons._build_season_trophies(snap)['champion']['team_id']=='b'


@pytest.mark.asyncio
async def test_shared_awards_agree_in_league_franchise_hall_and_career():
    async with isolated_router_app(seasons) as ctx:
        lid=await seed_league(ctx.db);a=await seed_team(ctx.db,league_id=lid);b=await seed_team(ctx.db,league_id=lid,name='Other')
        players=[{'player_id':str(ObjectId()),'name':'Same player name','position':pos,'season_stats':stats} for pos,stats in [('D',{'points':50}),('D',{'points':50}),('G',{'wins':1}),('G',{'wins':1})]]
        teams=[{'team_id':tid,'team_name':name,'points_for':100,'roster':[players[i]['player_id'],players[i+2]['player_id']]} for i,(tid,name) in enumerate([(a,'Test Team'),(b,'Other')])]
        await ctx.db.league_seasons.insert_one({'league_id':lid,'season_year':2026,'teams':teams,'players':players})
        body=(await ctx.client.get(f'/api/leagues/{lid}/trophy-room')).json();card=body['seasons'][0]
        assert len(card['presidents_trophies'])==2 and len(card['player_awards'])==6
        assert len(body['hall_of_fame'])==4
        for tid in [a,b]:
            franchise=(await ctx.client.get(f'/api/teams/{tid}/trophy-room')).json()
            assert len(franchise['individual_awards'])==3
            assert any(x['type']=='presidents_trophy' for x in franchise['banners'])
        for player in players[:2]:
            career=(await ctx.client.get(f"/api/players/{player['player_id']}/dynasty-career")).json()
            assert career['totals']['awards']==2


@pytest.mark.asyncio
async def test_archived_franchise_history_keeps_member_checks_and_saved_name():
    async with isolated_router_app(seasons) as ctx:
        lid=await seed_league(ctx.db);tid=str(ObjectId())
        await ctx.db.league_seasons.insert_one({'league_id':lid,'season_year':2026,'champion_team_id':tid,'teams':[{'team_id':tid,'team_name':'Archived franchise','wins':8,'points_for':10}], 'players':[]})
        url=f'/api/teams/{tid}/trophy-room';r=await ctx.client.get(url);assert r.status_code==200
        body=r.json();assert body['historical_franchise'] is True and body['team_name']=='Archived franchise'
        assert body['seasons_played'][0]['rank']==1
        async def outsider(_request):return {'_id':'outsider'}
        seasons._deps['get_current_user']=outsider;assert (await ctx.client.get(url)).status_code==403
        async def anon(_request):raise HTTPException(401,'Not authenticated')
        seasons._deps['get_current_user']=anon;assert (await ctx.client.get(url)).status_code==401


@pytest.mark.asyncio
@pytest.mark.parametrize('format',['h2h-points','h2h-categories','rotisserie'])
async def test_snapshot_ranks_are_format_correct_and_frozen(format,monkeypatch):
    async with isolated_router_app(seasons) as ctx:
        lid=await seed_league(ctx.db);ids=[await seed_team(ctx.db,league_id=lid,name=str(i)) for i in range(3)]
        await ctx.db.leagues.update_one({'_id':ObjectId(lid)},{'$set':{'scoring_format':format,'current_season_year':2026}})
        for i,tid in enumerate(ids):await ctx.db.teams.update_one({'_id':ObjectId(tid)},{'$set':{'wins':[2,3,3][i],'points_for':[100,10,20][i]}})
        if format=='rotisserie':
            from routes import roto
            async def totals(*args):return {'totals':{tid:{'total_points':[5,10,10][i]} for i,tid in enumerate(ids)}}
            monkeypatch.setattr(roto,'compute_season',totals)
        await finish(ctx,lid,False)
        if format=='rotisserie':
            await finish(ctx,lid,False)  # Shared Roto championships remain replay-safe.
        await ctx.db.teams.update_many({'league_id':lid},{'$set':{'wins':99,'points_for':999}})
        await ctx.db.leagues.update_one({'_id':ObjectId(lid)},{'$set':{'scoring_format':'changed'}})
        ranks=[]
        for tid in ids:ranks.append((await ctx.client.get(f'/api/teams/{tid}/trophy-room')).json()['seasons_played'][0]['rank'])
        assert ranks==([3,1,1] if format=='rotisserie' else [3,2,1])


def test_legacy_roto_rank_explicitly_unavailable_without_saved_totals():
    snap={'scoring_format':'rotisserie','teams':[{'team_id':'a','points_for':100}]}
    assert season_history.historical_rank(snap,snap['teams'][0])==(None,'legacy_roto_totals_unavailable')


@pytest.mark.asyncio
@pytest.mark.parametrize('automatic',[False,True])
async def test_multiple_championship_flags_cannot_complete(automatic):
    async with isolated_router_app(seasons) as ctx:
        lid=await seed_league(ctx.db)
        for name in ['A','B']:
            tid=await seed_team(ctx.db,league_id=lid,name=name)
            await ctx.db.teams.update_one({'_id':ObjectId(tid)},{'$set':{'championship_won_at':'2026-01-01'}})
        if automatic:
            await ctx.db.matchups.insert_one({'league_id':lid,'week':1,'is_playoff':True,'status':'completed'})
            with pytest.raises(HTTPException) as exc:await seasons._maybe_auto_snapshot_season(lid)
            assert exc.value.status_code==409
        else:assert (await ctx.client.post(f'/api/leagues/{lid}/complete-season',json={'season_year':2026})).status_code==409
        assert await ctx.db.league_seasons.count_documents({'league_id':lid})==0
