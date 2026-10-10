"""Account identity changes preserve legitimately earned per-user XP."""
import pytest
from bson import ObjectId
from routes import admin_user_actions, teams_admin
from services.profile_attribution import ownership_update
from services.profile_identity import change_ownership
from tests.router_test_utils import isolated_router_app
from utils.xp import compute_user_xp


def admin():
    return {'_id':str(ObjectId()),'role':'admin','permission_tier':'senior_admin','email':'identity@test.local'}


async def accounts(db):
    source,target,new=[str(ObjectId()) for _ in range(3)]
    await db.users.insert_many([{'_id':ObjectId(uid),'email':f'{uid}@test.local','is_active':True}
                               for uid in (source,target,new)])
    return source,target,new


@pytest.mark.asyncio
async def test_merge_preserves_both_coowners_equal_credit_and_future_rewards_once():
    async with isolated_router_app(admin_user_actions,user=admin()) as ctx:
        source,target,_=await accounts(ctx.db)
        tid=ObjectId()
        await ctx.db.teams.insert_one({'_id':tid,'owner_id':source,'co_owner_ids':[target],
                                      'wins':1,'championship_won_at':'2026-10-08'})
        await ctx.db.trades.insert_one({'status':'executed','xp_user_ids':[source,target]})
        before=await compute_user_xp(ctx.db,source)+await compute_user_xp(ctx.db,target)
        assert before==1190
        route=f'/api/admin/platform/users/{target}/merge-accounts'
        response=await ctx.client.post(route,json={'source_user_id':source,'reason':'Same person'})
        assert response.status_code==200,response.text
        assert await compute_user_xp(ctx.db,target)==before
        team=await ctx.db.teams.find_one({'_id':tid})
        assert team['owner_id']==target and team['co_owner_ids']==[]
        assert team['ownership_history'][-1]['before']==sorted([source,target])
        assert (await ctx.client.post(route,json={'source_user_id':source,'reason':'Retry'})).json()['already_merged']
        assert await compute_user_xp(ctx.db,target)==before
        await ctx.db.teams.update_one({'_id':tid},{'$inc':{'wins':1}})
        assert await compute_user_xp(ctx.db,target)==before+20


@pytest.mark.asyncio
async def test_source_only_team_merge_has_no_management_bonus_and_nested_merge_keeps_credit():
    async with isolated_router_app(admin_user_actions,user=admin()) as ctx:
        source,target,new=await accounts(ctx.db)
        tid=ObjectId()
        await ctx.db.teams.insert_one({'_id':tid,'owner_id':source,'wins':2,'xp_win_adjustment':-20})
        await ctx.db.drafts.insert_one({'status':'completed','xp_user_ids':[source]})
        assert await compute_user_xp(ctx.db,source)==110
        for src,dest in [(source,target),(target,new)]:
            response=await ctx.client.post(f'/api/admin/platform/users/{dest}/merge-accounts',json={'source_user_id':src})
            assert response.status_code==200,response.text
            assert await compute_user_xp(ctx.db,dest)==110
        await ctx.db.teams.update_one({'_id':tid},{'$inc':{'wins':1,'xp_win_adjustment':-10}})
        assert await compute_user_xp(ctx.db,new)==120


@pytest.mark.asyncio
async def test_manual_edit_old_owner_keeps_win_new_owner_gets_later_division():
    async with isolated_router_app(teams_admin,user=admin()) as ctx:
        old,new,co=await accounts(ctx.db)
        tid=ObjectId()
        await ctx.db.teams.insert_one({'_id':tid,'owner_id':old,'wins':1})
        response=await ctx.client.post(f'/api/admin/teams/{tid}/ownership',json={
            'owner_id':new,'co_owner_ids':[co,new,co],'reason':'Ownership transfer'})
        assert response.status_code==200,response.text
        assert await compute_user_xp(ctx.db,old)==70
        assert await compute_user_xp(ctx.db,new)==50
        assert await compute_user_xp(ctx.db,co)==50
        await ctx.db.teams.update_one({'_id':tid},{'$set':{'division_winner_at':'2026-10-09'}})
        assert await compute_user_xp(ctx.db,old)==70
        assert await compute_user_xp(ctx.db,new)==200
        assert await compute_user_xp(ctx.db,co)==200
        assert await ctx.db.admin_user_actions.count_documents({'action':'edit_team_ownership'})==1


@pytest.mark.asyncio
async def test_manual_edit_requires_admin_and_valid_active_users():
    async with isolated_router_app(teams_admin,user={'_id':str(ObjectId()),'role':'user','email':'user@test.local'}) as ctx:
        assert (await ctx.client.post(f'/api/admin/teams/{ObjectId()}/ownership',json={
            'owner_id':str(ObjectId()),'reason':'Attempt'})).status_code==403
    async with isolated_router_app(teams_admin,user=admin()) as ctx:
        old,new,_=await accounts(ctx.db)
        tid=ObjectId()
        await ctx.db.teams.insert_one({'_id':tid,'owner_id':old})
        await ctx.db.users.update_one({'_id':ObjectId(new)},{'$set':{'is_active':False}})
        assert (await ctx.client.post(f'/api/admin/teams/{tid}/ownership',json={
            'owner_id':new,'reason':'Attempt'})).status_code==400
        assert (await ctx.db.teams.find_one({'_id':tid}))['owner_id']==old


@pytest.mark.asyncio
async def test_ownership_guard_retries_concurrent_scoring(monkeypatch):
    async with isolated_router_app(teams_admin,user=admin()) as ctx:
        old,new,_=await accounts(ctx.db)
        tid=ObjectId()
        await ctx.db.teams.insert_one({'_id':tid,'owner_id':old,'wins':0})
        collection_type=type(ctx.db.teams)
        original=collection_type.update_one
        raced=False
        async def racing(collection,query,update,*args,**kwargs):
            nonlocal raced
            if not raced and 'wins' in query:
                raced=True
                await original(collection,{'_id':tid},{'$inc':{'wins':1}})
            return await original(collection,query,update,*args,**kwargs)
        monkeypatch.setattr(collection_type,'update_one',racing)
        await change_ownership(ctx.db,tid,{'owner_id':new},reason='Transfer',actor_id='admin')
        assert await compute_user_xp(ctx.db,old)==70
        assert await compute_user_xp(ctx.db,new)==50


@pytest.mark.asyncio
async def test_merged_trophies_honor_later_league_privacy():
    async with isolated_router_app(admin_user_actions,user=admin()) as ctx:
        source,target,_=await accounts(ctx.db)
        lid,tid=ObjectId(),ObjectId()
        await ctx.db.leagues.insert_one({'_id':lid,'name':'Sensitive name','is_private':False})
        await ctx.db.teams.insert_one({'_id':tid,'league_id':str(lid),'owner_id':source,
            'championship_won_at':'2026-10-08'})
        response=await ctx.client.post(f'/api/admin/platform/users/{target}/merge-accounts',json={'source_user_id':source})
        assert response.status_code==200
        await ctx.db.leagues.update_one({'_id':lid},{'$set':{'is_private':True}})
        from services.profile_career import career_summary
        summary=await career_summary(ctx.db,target)
        assert summary['trophies']
        assert all(t['league_id'] is None and t['league_name']=='Private League' for t in summary['trophies'])
