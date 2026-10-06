"""Cached puck-drop ownership and lineup eligibility for live recomputation."""
from utils.game_allocation import _parse_game_date, _build_game_date_map
from utils.scoring_roster import ACTIVE_SECTIONS


async def allocation_context(db, game_ids):
    times = await _build_game_date_map(db, game_ids)
    ownership, eligibility, historical_players = {}, {}, {}
    async for row in db.player_ownership_periods.find({}):
        pid, lid, tid = row["player_id"], row["league_id"], row["team_id"]
        ownership.setdefault((pid, lid), []).append((tid, _parse_game_date(row["acquired_at"]), _parse_game_date(row.get("released_at"))))
        historical_players.setdefault((tid, lid), set()).add(pid)
    async for row in db.lineup_status_periods.find({}):
        eligibility.setdefault((row["player_id"], row["team_id"], row["league_id"]), []).append(
            (_parse_game_date(row["started_at"]), _parse_game_date(row.get("ended_at")), row.get("position") in ACTIVE_SECTIONS))
    return times, ownership, eligibility, historical_players


def qualifies(pid, tid, lid, game_id, current_roster, current_lineup, context):
    times, ownership, eligibility, _ = context
    try:
        at = times.get(int(game_id))
    except (ValueError, TypeError):
        at = None
    spans = ownership.get((pid, lid))
    if spans:
        if at is None or not any(owner == tid and start and start <= at and (end is None or at < end) for owner, start, end in spans):
            return False
    elif pid not in current_roster:
        return False
    periods = eligibility.get((pid, tid, lid))
    if periods:
        return at is not None and any(active and start and start <= at and (end is None or at < end) for start, end, active in periods)
    assignment = current_lineup.get(pid)
    return assignment is None or assignment.get("section") in ACTIVE_SECTIONS
