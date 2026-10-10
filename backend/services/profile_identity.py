"""Preserve earned account credit while changing current ownership."""
from datetime import datetime, timezone
from bson import ObjectId
from services.profile_attribution import AWARDS, owners, ownership_update


async def change_ownership(db, team_id, update, *, reason, actor_id):
    """Compare record baselines in the ownership write; retry concurrent scoring."""
    for _ in range(5):
        team = await db.teams.find_one({'_id': ObjectId(str(team_id))})
        if team is None:
            raise ValueError('Team not found')
        fields = ['owner_id', 'co_owner_ids', 'profile_attribution', 'wins', 'losses',
                  'ties', 'points_for', 'live_points', 'xp_win_adjustment',
                  'xp_award_adjustments', *AWARDS]
        guard = {'_id': team['_id'], **{key: team.get(key) for key in fields}}
        changes = ownership_update(team, update)
        history = {'at': datetime.now(timezone.utc).isoformat(), 'actor_id': str(actor_id),
                   'reason': reason, 'before': owners(team), 'after': owners({**team, **update})}
        result = await db.teams.update_one(guard, {'$set': changes, '$push': {'ownership_history': history}})
        if result.matched_count:
            return changes
    raise RuntimeError('Ownership changed concurrently; retry the operation')


async def reserve_merge(db, source_id, target_id):
    """One source account can only be assigned to one merge destination."""
    key = str(source_id)
    await db.profile_account_merges.update_one({'_id': key}, {'$setOnInsert': {
        'target_id': str(target_id), 'created_at': datetime.now(timezone.utc).isoformat()}}, upsert=True)
    saved = await db.profile_account_merges.find_one({'_id': key})
    if saved['target_id'] != str(target_id):
        raise ValueError('Source account already belongs to another merge')
    return saved


async def prepare_merge_credit(db, source_id, target_id):
    """Freeze after ownership settles so concurrent pre-transfer wins are retained."""
    from services.profile_career import career_summary
    saved = await reserve_merge(db, source_id, target_id)
    if 'credit' in saved:
        return saved['credit']
    credit = await career_summary(db, source_id)
    await db.profile_account_merges.update_one(
        {'_id': str(source_id), 'credit': {'$exists': False}}, {'$set': {'credit': credit}})
    return (await db.profile_account_merges.find_one({'_id': str(source_id)}))['credit']


async def transfer_merge_teams(db, source_id, target_id, *, reason, actor_id):
    """Freeze source credit; receiving membership must not mint management XP."""
    source, target = str(source_id), str(target_id)
    source_variants = [source, ObjectId(source)] if ObjectId.is_valid(source) else [source]
    count = 0
    async for team in db.teams.find({'$or': [{'owner_id': {'$in': source_variants}},
                                           {'co_owner_ids': {'$in': source_variants}}]}):
        active = owners(team)
        coowners = sorted({target if str(uid) == source else str(uid)
                           for uid in team.get('co_owner_ids') or []})
        owner = target if str(team.get('owner_id')) == source else team.get('owner_id')
        update = {'owner_id': owner, 'co_owner_ids': [uid for uid in coowners if uid != str(owner)]}
        if target not in active and target not in team.get('career_user_ids', []):
            update['profile_management_excluded_user_ids'] = sorted(
                set(team.get('profile_management_excluded_user_ids') or []) | {target})
        await change_ownership(db, team['_id'], update, reason=reason, actor_id=actor_id)
        count += 1
    return count
