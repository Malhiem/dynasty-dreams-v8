"""Audit legacy attribution; apply only evidence-backed, idempotent metadata."""
import argparse
import asyncio
import json
import os
from copy import deepcopy
from motor.motor_asyncio import AsyncIOMotorClient
from services.profile_attribution import contributions


async def backfill(db, apply=False):
    report = {'apply': apply, 'eligible': 0, 'updated': 0, 'unresolved': []}
    async for snapshot in db.league_seasons.find({}):
        teams = snapshot.get('teams') or []
        original_teams = deepcopy(teams)
        changed = False
        for team in teams:
            if 'profile_contributions' in team:
                continue
            if not team.get('owner_id'):
                report['unresolved'].append({'collection': 'league_seasons', 'id': str(snapshot['_id']),
                                             'team_id': team.get('team_id'), 'reason': 'missing historical owner'})
                continue
            team['profile_contributions'] = contributions(team)
            changed = True
            report['eligible'] += 1
            if 'co_owner_ids' not in team:
                report['unresolved'].append({'collection': 'league_seasons', 'id': str(snapshot['_id']),
                                             'team_id': team.get('team_id'), 'reason': 'historical co-owners unavailable; primary owner only'})
        if apply and changed:
            result = await db.league_seasons.update_one(
                {'_id': snapshot['_id'], 'teams': original_teams}, {'$set': {'teams': teams}})
            report['updated'] += result.modified_count
    async for trade in db.trades.find({'xp_user_ids': {'$exists': False}}):
        successful = trade.get('status') == 'executed' or (trade.get('status') == 'accepted'
                     and 'execution_moves' in trade and trade.get('processed_at'))
        if not successful:
            if trade.get('status') == 'accepted':
                report['unresolved'].append({'collection': 'trades', 'id': str(trade['_id']), 'reason': 'accepted without execution evidence'})
            continue
        recipients = {str(uid) for uid in [trade.get('proposer_id'), trade.get('target_owner_id'),
                      trade.get('recipient_id'), *[p.get('owner_id') for p in trade.get('parties') or []]] if uid}
        if not recipients:
            report['unresolved'].append({'collection': 'trades', 'id': str(trade['_id']), 'reason': 'missing historical participants'})
            continue
        report['eligible'] += 1
        if apply:
            result = await db.trades.update_one({'_id': trade['_id'], 'xp_user_ids': {'$exists': False}},
                                               {'$set': {'xp_user_ids': sorted(recipients)}})
            report['updated'] += result.modified_count
        report['unresolved'].append({'collection': 'trades', 'id': str(trade['_id']),
                                     'reason': 'legacy co-owner attribution unavailable; stored participants only'})
    for collection, query in [('drafts', {'status': {'$in': ['complete', 'completed']}}),
                              ('waiver_claims', {'status': 'won'})]:
        async for row in db[collection].find({**query, 'xp_user_ids': {'$exists': False}}):
            report['unresolved'].append({'collection': collection, 'id': str(row['_id']),
                                         'reason': 'missing completion-time participants; no current-owner inference applied'})
    async for team in db.teams.find({'owner_history.0': {'$exists': True}, 'profile_attribution': {'$exists': False}}):
        report['unresolved'].append({'collection': 'teams', 'id': str(team['_id']),
                                     'reason': 'legacy ownership changes lack contribution baselines'})
    return report


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='Write only recoverable attribution metadata; default is dry-run')
    args = parser.parse_args()
    if not os.environ.get('MONGO_URL') or not os.environ.get('DB_NAME'):
        parser.error('Explicit MONGO_URL and DB_NAME are required; ambient defaults are not used')
    client = AsyncIOMotorClient(os.environ['MONGO_URL'])
    try:
        print(json.dumps(await backfill(client[os.environ['DB_NAME']], args.apply), indent=2))
    finally:
        client.close()


if __name__ == '__main__':
    asyncio.run(main())
