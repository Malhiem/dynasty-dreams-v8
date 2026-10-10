"""One read-only career summary for public profiles, levels and XP events."""
from bson import ObjectId
from services.profile_attribution import AWARDS, contributions, owners, trophy_sort_key


def variants(uid):
    return [str(uid), ObjectId(str(uid))] if ObjectId.is_valid(str(uid)) else [str(uid)]


def draft_team_ids(draft):
    mapped = [entry.get('id') or entry.get('team_id') if isinstance(entry, dict) else entry
              for entry in (draft.get('team_map') or {}).values()]
    return sorted({str(tid) for tid in [*(draft.get('participants') or []), *mapped,
                  *[p.get('team_id') for p in draft.get('picks') or []]] if tid})


async def participants_for_teams(db, team_ids):
    ids = [ObjectId(str(tid)) for tid in team_ids if ObjectId.is_valid(str(tid))]
    recipients = set()
    async for team in db.teams.find({'_id': {'$in': ids}}):
        recipients.update(owners(team))
    return sorted(recipients)


async def career_summary(db, user_id):
    uid = str(user_id)
    ids = variants(uid)
    teams = await db.teams.find({'$or': [
        {'owner_id': {'$in': ids}}, {'co_owner_ids': {'$in': ids}},
        {'career_user_ids': uid}, {f'profile_attribution.{uid}': {'$exists': True}},
    ]}).to_list(None)
    historical = await db.league_seasons.find({'$and': [
        {'$or': [{'status': {'$in': ['complete', 'completed']}}, {'status': {'$exists': False}}]},
        {'$or': [{'teams.owner_id': {'$in': ids}}, {'teams.co_owner_ids': {'$in': ids}},
                 {f'teams.profile_contributions.{uid}': {'$exists': True}}]},
    ]}).sort('snapshot_at', 1).to_list(None)
    lids = {str(t.get('league_id')) for t in teams if t.get('league_id')}
    lids.update(str(s['league_id']) for s in historical)
    leagues = {str(l['_id']): l async for l in db.leagues.find(
        {'_id': {'$in': [ObjectId(lid) for lid in lids if ObjectId.is_valid(lid)]}})}
    seasons = {}
    managed = {str(t['_id']) for t in teams if uid in set(owners(t)) | set(t.get('career_user_ids') or [])
               and uid not in (t.get('profile_management_excluded_user_ids') or [])}
    for snap in historical:
        lid, year = str(snap['league_id']), str(snap.get('season_year') or '')
        ranked = sorted(snap.get('teams') or [], key=lambda t: -float(t.get('points_for') or 0))
        for index, team in enumerate(ranked):
            if 'profile_contributions' in team:
                earned = (team.get('profile_contributions') or {}).get(uid)
            else:
                earned = contributions(team).get(uid)
            if earned is None:
                continue
            tid = str(team.get('team_id') or team.get('_id') or '')
            excluded = team.get('profile_management_excluded_user_ids') or []
            current_team = next((t for t in teams if str(t['_id']) == tid), {})
            if uid not in excluded and uid not in (current_team.get('profile_management_excluded_user_ids') or []):
                managed.add(tid)
            seasons[(lid, tid, year)] = (team, earned, index + 1)
    for team in teams:
        earned = contributions(team).get(uid)
        if earned is None:
            continue
        lid = str(team.get('league_id') or '')
        year = str((leagues.get(lid) or {}).get('current_season_year') or '')
        seasons.setdefault((lid, str(team['_id']), year), (team, earned, None))

    stats = {key: 0 for key in ('total_wins', 'total_losses', 'total_ties', 'total_points',
             'championships_won', 'conference_titles', 'division_titles', 'consolations_won',
             'playoff_appearances', 'runner_ups', 'regular_season_top3')}
    trophies = []
    competitive_adjustment = 0
    for (lid, tid, year), (team, earned, rank) in seasons.items():
        for key in ('wins', 'losses', 'ties'):
            stats[f'total_{key}'] += earned.get(key, 0)
        stats['total_points'] += earned.get('points', 0)
        competitive_adjustment += earned.get('competitive_xp_adjustment', 0)
        league = leagues.get(lid) or {}
        private = bool(league.get('is_private'))
        base = {'league_id': None if private else lid or None,
                'league_name': 'Private League' if private else league.get('name', 'Former League'),
                'league_is_private': private, 'team_id': tid,
                'team_name': team.get('team_name') or team.get('name') or 'Former Team',
                'season_year': year or None}
        for field, (counter, kind, label, _) in AWARDS.items():
            if not earned.get(field):
                continue
            stats[counter] += 1
            if kind and not (kind == 'runner_up' and earned.get('championship_won_at')):
                trophies.append({**base, 'type': kind, 'label': label, 'earned_at': earned[field],
                                 'xp_award': (team.get('xp_award_details') or {}).get(field)})
        if rank and rank <= 3:
            stats['regular_season_top3'] += 1
            ordinal = ['1st', '2nd', '3rd'][rank - 1]
            trophies.append({**base, 'type': ['regular_season_first', 'regular_season_second', 'regular_season_third'][rank - 1],
                             'label': f'Regular Season {ordinal} ({year})', 'place': rank})

    legacy_team_ids = [str(t['_id']) for t in teams if uid in
                       [str(v) for v in t.get('profile_legacy_user_ids', owners(t))]]
    counts = {'trades_accepted': 0, 'drafts_completed': 0, 'waiver_claims': 0}
    async for trade in db.trades.find({'$and': [
            {'$or': [{'status': 'executed'}, {'status': 'accepted', 'execution_moves': {'$exists': True}, 'processed_at': {'$ne': None}}]},
            {'$or': [{'xp_user_ids': uid}, {'xp_user_ids': {'$exists': False}, '$or': [
                {'proposer_id': {'$in': ids}}, {'target_owner_id': {'$in': ids}},
                {'recipient_id': {'$in': ids}}, {'parties.owner_id': {'$in': ids}}]}]},
    ]}):
        recipients = trade.get('xp_user_ids')
        if recipients is None:
            recipients = {str(v) for v in [trade.get('proposer_id'), trade.get('target_owner_id'),
                         trade.get('recipient_id'), *[p.get('owner_id') for p in trade.get('parties') or []]] if v}
        if uid in recipients:
            counts['trades_accepted'] += 1
    async for draft in db.drafts.find({'status': {'$in': ['complete', 'completed']}, '$or': [
            {'xp_user_ids': uid}, {'xp_user_ids': {'$exists': False}, '$or': [
                {'participants': {'$in': legacy_team_ids}}, {'picks.team_id': {'$in': legacy_team_ids}},
                # Dynamic abbreviation keys cannot be queried by value without an expression.
                {'team_map': {'$exists': True}},
            ]}]}):
        recipients = draft.get('xp_user_ids')
        if (recipients is not None and uid in recipients) or (recipients is None and set(draft_team_ids(draft)) & set(legacy_team_ids)):
            counts['drafts_completed'] += 1
    async for claim in db.waiver_claims.find({'status': 'won', 'xp_committed': {'$ne': False}, '$or': [
            {'xp_user_ids': uid}, {'xp_user_ids': {'$exists': False}, 'team_id': {'$in': legacy_team_ids}}]}):
        recipients = claim.get('xp_user_ids')
        if (recipients is not None and uid in recipients) or (recipients is None and str(claim.get('team_id')) in legacy_team_ids):
            counts['waiver_claims'] += 1
    stats.update(counts)
    stats['leagues_joined'] = len(managed)
    xp = int(len(managed) * 50 + stats['total_wins'] * 20 + counts['trades_accepted'] * 25
             + counts['drafts_completed'] * 40 + counts['waiver_claims'] * 5
             + sum(stats[counter] * amount for counter, _, _, amount in AWARDS.values()) + competitive_adjustment)
    competitive_base = stats['total_wins'] * 20 + sum(stats[counter] * amount for counter, _, _, amount in AWARDS.values())
    breakdown = {'competitive_base_xp': competitive_base,
                 'competitive_awarded_xp': competitive_base + competitive_adjustment,
                 'participation_xp': xp - competitive_base - competitive_adjustment}
    account = await db.users.find_one({'_id': {'$in': ids}}, {'profile_merged_credits': 1})
    for source_uid, credit in ((account or {}).get('profile_merged_credits') or {}).items():
        xp += credit.get('xp_total', 0)
        for key in stats:
            stats[key] += (credit.get('stats') or {}).get(key, 0)
        for key in breakdown:
            breakdown[key] += (credit.get('xp_breakdown') or {}).get(key, 0)
        inherited = credit.get('trophies') or []
        inherited_ids = {str(t.get('league_id')) for t in inherited if ObjectId.is_valid(str(t.get('league_id')))}
        private_ids = {str(l['_id']) async for l in db.leagues.find({
            '_id': {'$in': [ObjectId(lid) for lid in inherited_ids]}, 'is_private': True})}
        for trophy in inherited:
            item = {**trophy, 'earned_by_user_id': trophy.get('earned_by_user_id', source_uid)}
            if str(item.get('league_id')) in private_ids:
                item.update(league_id=None, league_name='Private League', league_is_private=True)
            trophies.append(item)
    stats['total_points'] = round(stats['total_points'], 2)
    return {'xp_total': max(xp, 0), 'stats': stats, 'xp_breakdown': breakdown, 'trophies': sorted(trophies, key=trophy_sort_key)}
