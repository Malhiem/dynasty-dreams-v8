"""Freeze automatic competition assessments before a matchup is scored."""
from datetime import datetime, timezone
from statistics import median
from bson import ObjectId
from services.profile_attribution import AWARDS, owners


def assessment(scores):
    if len(scores) < 2 or any(value is None for value in scores):
        return {'multiplier': 1.0, 'reason': 'Insufficient competition history', 'gap': None}
    gap = max(scores) - median(scores)
    multiplier = 0.5 if gap >= 400 else 0.75 if gap >= 200 else 1.0
    return {'multiplier': multiplier, 'gap': gap,
            'reason': 'League XP imbalance' if multiplier < 1 else 'Competitive league'}


def award(base, snapshot=None):
    policy = snapshot or {'multiplier': 1.0, 'reason': 'No recorded pre-match assessment'}
    multiplier = policy.get('multiplier', 1.0)
    return {'base_xp': base, 'multiplier': multiplier, 'awarded_xp': int(base * multiplier),
            'reason': policy.get('reason'), 'assessed_at': policy.get('assessed_at')}


async def capture_week(db, league_id, matchups):
    """Capture all open matchups together, before any result changes career XP."""
    pending = [m for m in matchups if not m.get('xp_competition') and m.get('status') == 'scheduled']
    if not pending:
        return
    from services.profile_career import career_summary
    teams = await db.teams.find({'league_id': str(league_id)}).to_list(None)
    totals, team_scores = {}, {}
    for team in teams:
        participants = owners(team)
        for uid in participants:
            if uid not in totals:
                totals[uid] = (await career_summary(db, uid))['xp_total']
        team_scores[str(team['_id'])] = max((totals[uid] for uid in participants), default=None)
    snapshot = {**assessment(list(team_scores.values())), 'policy': 'owner-xp-v1',
                'assessed_at': datetime.now(timezone.utc).isoformat(), 'team_scores': team_scores}
    for matchup in pending:
        await db.matchups.update_one({'_id': matchup['_id'], 'status': 'scheduled',
                                    'xp_competition': {'$exists': False}}, {'$set': {'xp_competition': snapshot}})
        saved = await db.matchups.find_one({'_id': matchup['_id']})
        matchup['xp_competition'] = saved.get('xp_competition')
    # Keep each team's latest pre-match assessment for separately clinched titles.
    for team in teams:
        relevant = [m for m in pending if str(team['_id']) in (m.get('home_team_id'), m.get('away_team_id'))]
        if relevant:
            await db.teams.update_one({'_id': team['_id']}, {'$set': {
                'xp_last_competition': relevant[-1]['xp_competition']}})


async def award_fields(db, team_id, fields):
    """Attach immutable automatic XP amounts in the same write as a new title."""
    team = await db.teams.find_one({'_id': ObjectId(str(team_id))})
    result = dict(fields)
    if not team:
        return result
    for field, value in fields.items():
        if field not in AWARDS or not value or team.get(field):
            continue
        detail = award(AWARDS[field][3], team.get('xp_last_competition'))
        result[f'xp_award_adjustments.{field}'] = detail['awarded_xp'] - detail['base_xp']
        result[f'xp_award_details.{field}'] = detail
    return result
