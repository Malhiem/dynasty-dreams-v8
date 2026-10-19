"""Snapshot integrity, champion identity, award ties, and historical ranks."""
from bson import ObjectId
from fastapi import HTTPException


def tied_leaders(rows, score, identity):
    if not rows:
        return []
    best = max(score(row) for row in rows)
    return sorted([row for row in rows if score(row) == best], key=lambda row: str(row.get(identity) or ""))


def champions(snapshot):
    teams = snapshot.get('teams') or []
    if 'champion_team_ids' in snapshot:
        ids = set(snapshot['champion_team_ids'] or [])
        return [t for t in teams if t.get('team_id') in ids]
    if 'champion_team_id' in snapshot:
        return [t for t in teams if t.get('team_id') == snapshot['champion_team_id']]
    name = snapshot.get('champion_team_name')
    if not name:
        return []
    matches = [t for t in teams if t.get('team_name') == name]
    if len(matches) == 1:
        return matches
    flagged = [t for t in matches if (t.get('awards') or {}).get('championship_won_at')]
    return flagged if len(flagged) == 1 else []


async def capture_players(db, teams):
    ids = {str(pid) for t in teams for pid in (t.get('roster') or [])}
    if any(not ObjectId.is_valid(pid) for pid in ids):
        raise HTTPException(409, 'Season snapshot has invalid roster player IDs')
    try:
        rows = await db.players.find({'_id':{'$in':[ObjectId(pid) for pid in ids]}},
            {'name':1,'position':1,'team':1,'season_stats':1}).to_list(len(ids) or 1)
    except Exception as exc:
        raise HTTPException(503, 'Player snapshot could not be read; season was not completed') from exc
    if {str(p['_id']) for p in rows} != ids:
        raise HTTPException(409, 'Season snapshot has missing roster players')
    return [{'player_id':str(p['_id']),'name':p.get('name'),'position':p.get('position'),
             'team':p.get('team'),'season_stats':p.get('season_stats')} for p in rows]


async def capture_standings(db, league, teams):
    """Freeze H2H ordering or Roto category totals; never infer Roto from PF."""
    flagged = [t for t in teams if (t.get('awards') or {}).get('championship_won_at')]
    if len(flagged) > 1 and league.get('scoring_format') != 'rotisserie':
        raise HTTPException(409, 'Multiple championship flags; resolve the season champion before completion')
    winner_ids = [t['team_id'] for t in flagged]
    if league.get('scoring_format') == 'rotisserie':
        from routes.roto import compute_season
        if league.get('roto_scoring_periods'):
            from services.schedule_store import season
            expected = {p['id'] for p in league['roto_scoring_periods']}
            closed = await db.roto_period_results.find({'league_id':str(league['_id']), 'season':season(league), 'closed':True}).to_list(366)
            if not expected.issubset({p['period'] for p in closed}):
                raise HTTPException(409, 'Finalize all generated Rotisserie periods before completing the season')
        try:
            result = await compute_season(db, str(league['_id']))
            totals = result.get('totals') or {}
            if any(t['team_id'] not in totals for t in teams):
                raise ValueError('Incomplete Roto standings')
            for t in teams:
                t['roto_total_points'] = float(totals[t['team_id']]['total_points'])
                t['rank'] = 1 + sum(float(v['total_points']) > t['roto_total_points'] for v in totals.values())
                t['rank_basis'] = 'roto_total_points'
            leaders = [t['team_id'] for t in tied_leaders(teams, lambda t:t['roto_total_points'], 'team_id')]
            if len(winner_ids) > 1 and set(winner_ids) != set(leaders):
                raise HTTPException(409, 'Conflicting Roto championship flags; resolve before completion')
            if league.get('roto_scoring_periods') and league.get('playoff_format') == 'playoff_tree' and league.get('playoffs_enabled') and league.get('roto_playoffs_enabled'):
                champion = league.get('roto_champion_team_id')
                if not champion: raise HTTPException(409, 'Finalize the Rotisserie championship before completing the season')
                winner_ids = [champion]
            elif not winner_ids:
                winner_ids = leaders
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(503, 'Standings snapshot could not be read; season was not completed') from exc
    else:
        ordered = sorted(teams, key=lambda t:(-float(t.get('wins') or 0),
            -float(t.get('points_for') or 0)-float(t.get('live_points') or 0), str(t['team_id'])))
        for rank,t in enumerate(ordered,1):
            t['rank'] = rank
            t['rank_basis'] = 'wins_points_team_id'
    return winner_ids


def historical_rank(snapshot, team):
    if team.get('rank') is not None:
        return team['rank'], team.get('rank_basis', 'saved_standings')
    teams = snapshot.get('teams') or []
    if snapshot.get('scoring_format') == 'rotisserie':
        if not teams or any(t.get('roto_total_points') is None for t in teams):
            return None, 'legacy_roto_totals_unavailable'
        return 1 + sum(float(t['roto_total_points']) > float(team['roto_total_points']) for t in teams), 'roto_total_points'
    ordered = sorted(teams, key=lambda t:(-float(t.get('wins') or 0),
        -float(t.get('points_for') or 0)-float(t.get('live_points') or 0), str(t['team_id'])))
    return next(i for i,t in enumerate(ordered,1) if t['team_id'] == team['team_id']), 'wins_points_team_id'
