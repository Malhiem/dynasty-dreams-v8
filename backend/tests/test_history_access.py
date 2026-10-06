"""Authenticated league-history reads and member-role compatibility."""
import pytest
from bson import ObjectId
from fastapi import HTTPException
from routes import seasons
from tests.router_test_utils import isolated_router_app


async def seed(db, user, role):
    uid = str(user['_id'])
    league = {'name': 'History access fixture', 'is_private': True, 'commissioner_id': 'another-user'}
    team = {'name': 'Fixture franchise', 'owner_id': 'another-user', 'roster': []}
    if role == 'commissioner': league['commissioner_id'] = uid
    elif role == 'co_commissioner': league['co_commissioners'] = [uid]
    elif role == 'league_owner': league['owner_id'] = uid
    elif role == 'league_admin': league['admin_ids'] = [uid]
    elif role == 'team_owner': team['owner_id'] = uid
    elif role == 'team_co_owner': team['co_owner_ids'] = [uid]
    lid = str((await db.leagues.insert_one(league)).inserted_id)
    team['league_id'] = lid
    tid = str((await db.teams.insert_one(team)).inserted_id)
    await db.league_seasons.insert_one({'league_id':lid,'season_year':2026,'teams':[],'players':[]})
    return lid, tid


def paths(lid, tid):
    return [f'/api/leagues/{lid}/seasons?include_team_stats=true',
            f'/api/leagues/{lid}/seasons/2026',
            f'/api/leagues/{lid}/trophy-room', f'/api/teams/{tid}/trophy-room']


@pytest.mark.asyncio
@pytest.mark.parametrize('role', ['commissioner','co_commissioner','league_owner','league_admin',
                                  'team_owner','team_co_owner','platform_admin'])
async def test_member_roles_can_read_history(role):
    user = {'_id': str(ObjectId()), 'roles': ['admin'] if role == 'platform_admin' else ['user']}
    async with isolated_router_app(seasons, user=user) as ctx:
        lid, tid = await seed(ctx.db, user, role)
        for path in paths(lid, tid):
            response = await ctx.client.get(path)
            assert response.status_code == 200, (path, response.text)


@pytest.mark.asyncio
async def test_outsider_cannot_read_any_history_view():
    user = {'_id': str(ObjectId()), 'roles': ['user']}
    async with isolated_router_app(seasons, user=user) as ctx:
        lid, tid = await seed(ctx.db, user, 'outsider')
        for path in paths(lid, tid):
            assert (await ctx.client.get(path)).status_code == 403, path


@pytest.mark.asyncio
async def test_anonymous_auth_precedes_resource_lookup():
    async with isolated_router_app(seasons) as ctx:
        async def deny(_request):
            raise HTTPException(status_code=401, detail='Not authenticated')
        seasons._deps['get_current_user'] = deny
        for path in paths(str(ObjectId()), str(ObjectId())) + paths('invalid-league','invalid-team'):
            assert (await ctx.client.get(path)).status_code == 401, path


@pytest.mark.asyncio
async def test_authenticated_invalid_and_missing_resources():
    user = {'_id':str(ObjectId()), 'roles':['admin']}
    async with isolated_router_app(seasons, user=user) as ctx:
        for path in paths('invalid-league','invalid-team'):
            assert (await ctx.client.get(path)).status_code == 400, path
        for path in paths(str(ObjectId()),str(ObjectId())):
            assert (await ctx.client.get(path)).status_code == 404, path
