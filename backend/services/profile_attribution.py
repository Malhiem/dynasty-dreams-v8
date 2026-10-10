"""Attribute season records to owners without granting new owners past activity."""
from datetime import datetime, timezone

AWARDS = {
    'championship_won_at': ('championships_won', 'championship', 'Playoff Champion', 500),
    'conference_winner_at': ('conference_titles', 'conference', 'Conference Champion', 250),
    'division_winner_at': ('division_titles', 'division', 'Division Champion', 150),
    'consolation_won_at': ('consolations_won', 'consolation', 'Consolation Winner', 100),
    'playoffs_reached_at': ('playoff_appearances', None, None, 75),
    'playoff_runner_up_at': ('runner_ups', 'runner_up', 'Playoff Runner-Up', 0),
}


def owners(team):
    return sorted({str(uid) for uid in [team.get('owner_id'), *(team.get('co_owner_ids') or [])] if uid})


def records(team):
    return {
        'wins': int(team.get('wins') or 0),
        'losses': int(team.get('losses') or 0),
        'ties': int(team.get('ties') or 0),
        'points': float(team.get('points_for') or 0) + float(team.get('live_points') or 0),
        'competitive_xp_adjustment': int(team.get('xp_win_adjustment') or 0) + sum(
            int(value) for field, value in (team.get('xp_award_adjustments') or {}).items()
            if team.get(field) or (team.get('awards') or {}).get(field)),
        **{key: (team.get('awards') or {}).get(key) or team.get(key) for key in AWARDS},
    }


def contributions(team):
    """Current season credit, including users who left during the season."""
    current = records(team)
    state = team.get('profile_attribution')
    if state is None:
        return {uid: dict(current) for uid in owners(team)}
    out = {}
    for uid, entry in state.items():
        earned = dict(entry.get('earned') or {})
        if uid in owners(team):
            baseline = entry.get('baseline') or {}
            for key in ('wins', 'losses', 'ties', 'points', 'competitive_xp_adjustment'):
                earned[key] = earned.get(key, 0) + current[key] - baseline.get(key, 0)
            for key in AWARDS:
                if current.get(key) and not baseline.get(key):
                    earned[key] = current[key]
        out[uid] = earned
    return out


def ownership_update(team, update):
    """Include this in the same Mongo write as an ownership change."""
    earned = contributions(team)
    next_team = {**team, **update}
    baseline = records(team)
    recipients = set(earned) | set(owners(next_team))
    return {
        **update,
        'profile_attribution': {
            uid: {'earned': earned.get(uid, {}), 'baseline': baseline}
            for uid in sorted(recipients)
        },
        'career_user_ids': sorted(set(team.get('career_user_ids') or []) | recipients),
        # Legacy drafts/claims must not inherit a subsequently added co-owner.
        'profile_legacy_user_ids': team.get('profile_legacy_user_ids', owners(team)),
    }


def next_season_attribution(team, reset):
    baseline = {} if reset else records(team)
    return {uid: {'earned': {}, 'baseline': baseline} for uid in owners(team)}


def trophy_sort_key(trophy):
    raw = trophy.get('earned_at')
    stamp = None
    try:
        stamp = raw if isinstance(raw, datetime) else datetime.fromisoformat(str(raw).replace('Z', '+00:00'))
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        stamp = stamp.astimezone(timezone.utc)
    except (ValueError, TypeError):
        pass
    try:
        year = int(trophy.get('season_year') or (stamp.year if stamp else 0))
    except (ValueError, TypeError):
        year = stamp.year if stamp else 0
    return (-year, -(stamp.timestamp() if stamp else 0), str(trophy.get('type') or ''),
            str(trophy.get('league_id') or ''), str(trophy.get('team_id') or ''))
