import os
import asyncio
import pytest
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient
from services.profile_attribution import contributions, ownership_update, trophy_sort_key
from services.profile_career import career_summary
from utils.xp import compute_user_xp, emit_xp_gain, award_draft_completion_bonuses


@pytest.fixture
async def db():
    client = AsyncIOMotorClient(os.environ['MONGO_URL'])
    database = client[os.environ['DB_NAME']]
    yield database
    client.close()


async def team(db, **fields):
    uid, co, lid, tid = (str(ObjectId()) for _ in range(4))
    await db.leagues.insert_one({'_id': ObjectId(lid), 'current_season_year': 2026, 'name': 'Profile unit'})
    doc = {'_id': ObjectId(tid), 'owner_id': uid, 'co_owner_ids': [co], 'league_id': lid,
           'name': 'Profile unit team', 'wins': 0, 'points_for': 0, 'live_points': 0, 'roster': [], **fields}
    await db.teams.insert_one(doc)
    return uid, co, lid, tid, doc


@pytest.mark.asyncio
async def test_coowners_receive_equal_full_achievement_credit(db):
    uid, co, _, _, _ = await team(db, championship_won_at='2026-06-01', conference_winner_at='2026-06-01',
        division_winner_at='2026-06-01', consolation_won_at='2026-06-01', playoffs_reached_at='2026-05-01')
    assert await compute_user_xp(db, uid) == 1125
    assert await compute_user_xp(db, co) == 1125


@pytest.mark.asyncio
async def test_snapshot_dedup_and_transfer_preserve_former_owner(db):
    uid, co, lid, tid, doc = await team(db, wins=10, points_for=200, championship_won_at='2026-06-01')
    await db.league_seasons.insert_one({'league_id': lid, 'season_year': 2026, 'status': 'complete', 'teams': [
        {**doc, 'team_id': tid, 'profile_contributions': contributions(doc)}]})
    assert await compute_user_xp(db, uid) == 750
    newcomer = str(ObjectId())
    updates = ownership_update(doc, {'owner_id': newcomer, 'co_owner_ids': []})
    await db.teams.update_one({'_id': ObjectId(tid)}, {'$set': updates})
    assert await compute_user_xp(db, uid) == 750
    assert await compute_user_xp(db, co) == 750
    assert await compute_user_xp(db, newcomer) == 50
    await db.leagues.update_one({'_id': ObjectId(lid)}, {'$set': {'current_season_year': 2027}})
    await db.teams.update_one({'_id': ObjectId(tid)}, {'$set': {'wins': 0, 'points_for': 0,
        'profile_attribution': {newcomer: {'earned': {}, 'baseline': {}}}}, '$unset': {'championship_won_at': ''}})
    assert await compute_user_xp(db, uid) == 750


@pytest.mark.asyncio
async def test_added_coowner_gets_only_future_activity(db):
    uid, _, _, tid, doc = await team(db, wins=2, points_for=50, championship_won_at='2026-06-01')
    newcomer = str(ObjectId())
    updates = ownership_update(doc, {'co_owner_ids': [*doc['co_owner_ids'], newcomer]})
    await db.teams.update_one({'_id': ObjectId(tid)}, {'$set': updates})
    assert await compute_user_xp(db, newcomer) == 50
    await db.teams.update_one({'_id': ObjectId(tid)}, {'$inc': {'wins': 1, 'points_for': 25}})
    assert await compute_user_xp(db, newcomer) == 70
    current = await db.teams.find_one({'_id': ObjectId(tid)})
    await db.teams.update_one({'_id': ObjectId(tid)}, {'$set': ownership_update(current, {'co_owner_ids': doc['co_owner_ids']})})
    await db.teams.update_one({'_id': ObjectId(tid)}, {'$inc': {'wins': 1}})
    assert await compute_user_xp(db, newcomer) == 70


@pytest.mark.asyncio
async def test_activity_statuses_and_distinct_frozen_recipients(db):
    uid, co, _, tid, _ = await team(db)
    await db.trades.insert_many([
        {'status': 'accepted', 'proposer_id': uid},
        {'status': 'executed', 'xp_user_ids': [uid, co, uid]},
        {'status': 'executed', 'target_owner_id': uid},
    ])
    await db.drafts.insert_many([{'status': 'completed', 'team_map': {'ABC': tid}, 'xp_user_ids': [uid, co]},
                                {'status': 'active', 'participants': [tid]},
                                {'status': 'complete', 'participants': [tid]}])
    await db.waiver_claims.insert_many([{'team_id': tid, 'status': status} for status in ['pending', 'lost', 'cancelled', 'denied']]
        + [{'team_id': tid, 'status': 'won', 'xp_committed': False},
           {'team_id': tid, 'status': 'won', 'xp_committed': True, 'xp_user_ids': [uid, co]}])
    summary = await career_summary(db, uid)
    assert summary['xp_total'] == 185
    assert summary['stats']['trades_accepted'] == 2
    assert summary['stats']['drafts_completed'] == 2
    assert summary['stats']['waiver_claims'] == 1
    assert await compute_user_xp(db, co) == 160


def test_mixed_missing_and_malformed_trophy_dates_sort():
    trophies = [{'type': 'championship', 'earned_at': '2026-10-01T00:00:00Z'},
        {'type': 'regular_season_first', 'season_year': 2026},
        {'type': 'division', 'season_year': '2027'},
        {'type': 'conference', 'earned_at': 'bad'}, {'type': 'runner_up'}]
    ordered = sorted(trophies, key=trophy_sort_key)
    assert [t['type'] for t in ordered] == ['division', 'championship', 'regular_season_first', 'conference', 'runner_up']
    assert trophy_sort_key({'season_year': '2026'}) == trophy_sort_key({'season_year': 2026})


@pytest.mark.asyncio
async def test_xp_event_is_idempotent_and_matches_career_after_commit(db):
    uid, co, _, _, _ = await team(db)
    trade_id = str(ObjectId())
    await db.trades.insert_one({'_id': ObjectId(trade_id), 'status': 'executed', 'xp_user_ids': [uid, co]})
    sent = []
    async def broadcast(*args):
        sent.append(args)
    payload = await emit_xp_gain(db, uid, source='trade_accepted', broadcast_fn=broadcast, meta={'trade_id': trade_id})
    assert payload['xp_total'] == 75
    assert payload['delta'] == 25
    assert sent[0][0] == f'user_{uid}'
    assert await emit_xp_gain(db, uid, source='trade_accepted', broadcast_fn=broadcast, meta={'trade_id': trade_id}) is None
    assert len(sent) == 1


@pytest.mark.asyncio
async def test_completion_notifications_even_without_speed_prize_and_no_repeat(db):
    uid, co, lid, tid, _ = await team(db)
    did = ObjectId()
    await db.drafts.insert_one({'_id': did, 'status': 'completed', 'league_id': lid,
                               'team_map': {'ABC': tid}, 'xp_user_ids': [uid, co], 'picks': []})
    sent = []
    async def broadcast(*args):
        sent.append(args)
    await award_draft_completion_bonuses(db, draft_id=str(did), broadcast_fn=broadcast)
    await award_draft_completion_bonuses(db, draft_id=str(did), broadcast_fn=broadcast)
    assert len(sent) == 2
    assert all(event[2]['xp_total'] == 90 and event[2]['delta'] == 40 for event in sent)


@pytest.mark.asyncio
async def test_real_last_draft_pick_records_coowners(db):
    from services.draft_mutation import commit_pick
    uid, co, lid, tid, doc = await team(db, lineup={}, draft_queue=[])
    pid, did = ObjectId(), ObjectId()
    await db.players.insert_one({'_id': pid, 'team': 'TOR', 'name': 'Completion Player', 'position': 'C'})
    draft = {'_id': did, 'league_id': lid, 'status': 'active', 'current_pick': 1, 'team_map': {'ABC': {'id': tid, 'name': 'Team'}}, 'picks': []}
    await db.drafts.insert_one(draft)
    await commit_pick(db, draft, doc, {'overall': 1, 'player_id': str(pid), 'team_id': tid}, {}, 'completed')
    finished = await db.drafts.find_one({'_id': did})
    assert finished['xp_user_ids'] == sorted([uid, co])
    assert await compute_user_xp(db, uid) == 90
    assert await compute_user_xp(db, co) == 90


@pytest.mark.asyncio
async def test_successful_waiver_finalization_credits_only_after_roster_commit(db):
    from services.waiver_engine import _finalize_winner
    uid, co, lid, tid, _ = await team(db)
    pid, cid = ObjectId(), ObjectId()
    await db.players.insert_one({'_id': pid, 'team': 'TOR', 'name': 'Waiver Player', 'position': 'C'})
    winner = {'_id': cid, 'team_id': tid, 'player_id': str(pid), 'league_id': lid, 'status': 'pending'}
    await db.waiver_claims.insert_one(winner)
    assert await compute_user_xp(db, uid) == 50
    assert await _finalize_winner(db, lid, winner, 'rolling', '2026-10-07T00:00:00Z')
    won = await db.waiver_claims.find_one({'_id': cid})
    assert won['xp_committed'] is True
    assert won['xp_user_ids'] == sorted([uid, co])
    assert str(pid) in (await db.teams.find_one({'_id': ObjectId(tid)}))['roster']
    assert await compute_user_xp(db, uid) == 55
    assert await compute_user_xp(db, co) == 55


@pytest.mark.asyncio
async def test_backfill_dry_run_and_apply_are_safe_and_repeatable(db):
    from scripts.backfill_profile_progression import backfill
    uid, _, lid, tid, _ = await team(db)
    snapshot = {'league_id': lid, 'season_year': 2025, 'status': 'complete',
                'teams': [{'team_id': tid, 'owner_id': uid, 'wins': 2, 'points_for': 50}]}
    result = await db.league_seasons.insert_one(snapshot)
    executed = await db.trades.insert_one({'status': 'executed', 'proposer_id': uid})
    ambiguous = await db.trades.insert_one({'status': 'accepted', 'proposer_id': uid})
    dry = await backfill(db)
    assert dry['updated'] == 0
    assert 'profile_contributions' not in (await db.league_seasons.find_one({'_id': result.inserted_id}))['teams'][0]
    assert await db.trades.find_one({'_id': executed.inserted_id, 'xp_user_ids': {'$exists': False}})
    before = await compute_user_xp(db, uid)
    applied = await backfill(db, apply=True)
    assert applied['updated'] >= 2
    assert await compute_user_xp(db, uid) == before
    assert await db.trades.find_one({'_id': ambiguous.inserted_id, 'xp_user_ids': {'$exists': False}})
    assert (await backfill(db, apply=True))['updated'] == 0


@pytest.mark.asyncio
async def test_failed_notification_can_retry_without_altering_xp(db):
    uid, _, _, _, _ = await team(db)
    async def failing(*args):
        raise RuntimeError('socket unavailable')
    meta = {'matchup_id': str(ObjectId())}
    assert await emit_xp_gain(db, uid, source='matchup_won', broadcast_fn=failing, meta=meta) is None
    sent = []
    async def working(*args):
        sent.append(args)
    assert await emit_xp_gain(db, uid, source='matchup_won', broadcast_fn=working, meta=meta)
    assert len(sent) == 1
    assert await compute_user_xp(db, uid) == 50


@pytest.mark.asyncio
async def test_fantasy_points_never_award_xp(db):
    uid, co, _, _, _ = await team(db, points_for=49.999)
    assert await compute_user_xp(db, uid) == 50
    assert await compute_user_xp(db, co) == 50


@pytest.mark.asyncio
async def test_concurrent_notification_attempts_emit_once(db):
    uid, _, _, _, _ = await team(db)
    sent = []
    async def broadcast(*args):
        sent.append(args)
    meta = {'matchup_id': str(ObjectId())}
    await asyncio.gather(*(emit_xp_gain(db, uid, source='matchup_won', broadcast_fn=broadcast, meta=meta) for _ in range(8)))
    assert len(sent) == 1


@pytest.mark.asyncio
async def test_failed_waiver_roster_write_leaves_no_reward(db, monkeypatch):
    from services.waiver_engine import _finalize_winner
    from motor.motor_asyncio import AsyncIOMotorCollection
    uid, co, lid, tid, _ = await team(db)
    pid, cid = ObjectId(), ObjectId()
    await db.players.insert_one({'_id': pid, 'team': 'TOR', 'name': 'Failing Waiver Player', 'position': 'C'})
    winner = {'_id': cid, 'team_id': tid, 'player_id': str(pid), 'league_id': lid, 'status': 'pending'}
    await db.waiver_claims.insert_one(winner)
    original = AsyncIOMotorCollection.update_one
    async def fail_roster(collection, query, update, *args, **kwargs):
        if collection.name == 'teams' and update.get('$addToSet', {}).get('roster') == str(pid):
            raise RuntimeError('injected roster write failure')
        return await original(collection, query, update, *args, **kwargs)
    monkeypatch.setattr(AsyncIOMotorCollection, 'update_one', fail_roster)
    assert not await _finalize_winner(db, lid, winner, 'rolling', '2026-10-07T00:00:00Z')
    assert (await db.waiver_claims.find_one({'_id': cid}))['status'] == 'pending'
    assert await compute_user_xp(db, uid) == 50
    assert await compute_user_xp(db, co) == 50
