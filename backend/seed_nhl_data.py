"""
NHL Player Data Seeder
Fetches real NHL player stats from the official NHL API via nhlpy
and seeds them into MongoDB for the Dynasty Dreams platform.
"""
import asyncio
import os
import sys
import logging
from pathlib import Path
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime, timezone

# Load env
ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# NHL team abbreviation mapping
NHL_TEAMS = {
    "ANA": "Anaheim Ducks", "ARI": "Arizona Coyotes", "BOS": "Boston Bruins",
    "BUF": "Buffalo Sabres", "CGY": "Calgary Flames", "CAR": "Carolina Hurricanes",
    "CHI": "Chicago Blackhawks", "COL": "Colorado Avalanche", "CBJ": "Columbus Blue Jackets",
    "DAL": "Dallas Stars", "DET": "Detroit Red Wings", "EDM": "Edmonton Oilers",
    "FLA": "Florida Panthers", "LAK": "Los Angeles Kings", "MIN": "Minnesota Wild",
    "MTL": "Montreal Canadiens", "NSH": "Nashville Predators", "NJD": "New Jersey Devils",
    "NYI": "New York Islanders", "NYR": "New York Rangers", "OTT": "Ottawa Senators",
    "PHI": "Philadelphia Flyers", "PIT": "Pittsburgh Penguins", "SJS": "San Jose Sharks",
    "SEA": "Seattle Kraken", "STL": "St. Louis Blues", "TBL": "Tampa Bay Lightning",
    "TOR": "Toronto Maple Leafs", "UTA": "Utah Hockey Club", "VAN": "Vancouver Canucks",
    "VGK": "Vegas Golden Knights", "WPG": "Winnipeg Jets", "WSH": "Washington Capitals",
}

POSITION_MAP = {
    "C": "C", "L": "LW", "R": "RW", "D": "D", "G": "G"
}


def fetch_skaters(client, season="20252026", batch_size=100):
    """Fetch all skater stats from NHL API with pagination."""
    from nhlpy.api.query.builder import QueryBuilder, QueryContext
    from nhlpy.api.query.filters.season import SeasonQuery
    from nhlpy.api.query.filters.game_type import GameTypeQuery

    filters = [
        SeasonQuery(season_start=season, season_end=season),
        GameTypeQuery(game_type="2"),
    ]
    query_builder = QueryBuilder()
    query_context = query_builder.build(filters=filters)

    all_skaters = []
    start = 0

    while True:
        result = client.stats.skater_stats_with_query_context(
            report_type='summary',
            query_context=query_context,
            aggregate=True,
            start=start,
            limit=batch_size
        )

        data = result.get("data", [])
        total = result.get("total", 0)

        if not data:
            break

        all_skaters.extend(data)
        start += batch_size
        logger.info(f"Fetched {len(all_skaters)}/{total} skaters...")

        if len(all_skaters) >= total:
            break

    return all_skaters


def fetch_goalies(client, season="20252026", batch_size=100):
    """Fetch all goalie stats from NHL API with pagination."""
    all_goalies = []
    start = 0

    while True:
        data = client.stats.goalie_stats_summary(
            start_season=season,
            end_season=season,
            aggregate=True,
            start=start,
            limit=batch_size
        )

        if not data:
            break

        all_goalies.extend(data)
        logger.info(f"Fetched {len(all_goalies)} goalies so far...")
        start += batch_size

        if len(data) < batch_size:
            break

    return all_goalies


def fetch_team_rosters(client):
    """Fetch team abbreviations for each player using team rosters."""
    team_map = {}  # playerId -> team abbreviation

    try:
        teams_list = client.teams.teams()
        logger.info(f"Found {len(teams_list)} NHL teams")

        for team in teams_list:
            abbr = team.get("abbr", "")
            if not abbr:
                continue
            try:
                roster = client.teams.team_roster(team_abbr=abbr, season="20252026")
                for pos_group in ["forwards", "defensemen", "goalies"]:
                    for player in roster.get(pos_group, []):
                        pid = player.get("id")
                        if pid:
                            team_map[pid] = abbr
            except Exception as e:
                logger.warning(f"Failed to get roster for {abbr}: {e}")
    except Exception as e:
        logger.warning(f"Failed to fetch teams: {e}")

    return team_map


def transform_skater(raw, team_map):
    """Transform NHL API skater data to our player model."""
    player_id = raw.get("playerId")
    pos_code = raw.get("positionCode", "C")

    return {
        "nhl_id": player_id,
        "name": raw.get("skaterFullName", raw.get("lastName", "Unknown")),
        "team": team_map.get(player_id, ""),
        "team_name": NHL_TEAMS.get(team_map.get(player_id, ""), ""),
        "position": POSITION_MAP.get(pos_code, pos_code),
        "player_type": "skater",
        "shoots": raw.get("shootsCatches", ""),
        "games_played": raw.get("gamesPlayed", 0),
        "goals": raw.get("goals", 0),
        "assists": raw.get("assists", 0),
        "points": raw.get("points", 0),
        "plus_minus": raw.get("plusMinus", 0),
        "penalty_minutes": raw.get("penaltyMinutes", 0),
        "power_play_goals": raw.get("ppGoals", 0),
        "power_play_points": raw.get("ppPoints", 0),
        "short_handed_goals": raw.get("shGoals", 0),
        "short_handed_points": raw.get("shPoints", 0),
        "game_winning_goals": raw.get("gameWinningGoals", 0),
        "overtime_goals": raw.get("otGoals", 0),
        "shots": raw.get("shots", 0),
        "shooting_pct": round(raw.get("shootingPct", 0) * 100, 1) if raw.get("shootingPct") else 0,
        "even_strength_goals": raw.get("evGoals", 0),
        "even_strength_points": raw.get("evPoints", 0),
        "points_per_game": round(raw.get("pointsPerGame", 0), 2),
        "toi_per_game": round(raw.get("timeOnIcePerGame", 0) / 60, 1) if raw.get("timeOnIcePerGame") else 0,
        "faceoff_win_pct": round(raw.get("faceoffWinPct", 0) * 100, 1) if raw.get("faceoffWinPct") else 0,
        "season": "2025-2026",
        "seeded_at": datetime.now(timezone.utc),
    }


def transform_goalie(raw, team_map):
    """Transform NHL API goalie data to our player model."""
    player_id = raw.get("playerId")

    return {
        "nhl_id": player_id,
        "name": raw.get("goalieFullName", raw.get("lastName", "Unknown")),
        "team": team_map.get(player_id, ""),
        "team_name": NHL_TEAMS.get(team_map.get(player_id, ""), ""),
        "position": "G",
        "player_type": "goalie",
        "shoots": raw.get("shootsCatches", ""),
        "games_played": raw.get("gamesPlayed", 0),
        "games_started": raw.get("gamesStarted", 0),
        "goals": raw.get("goals", 0),
        "assists": raw.get("assists", 0),
        "points": raw.get("points", 0),
        "plus_minus": 0,
        "penalty_minutes": raw.get("penaltyMinutes", 0),
        "wins": raw.get("wins", 0),
        "losses": raw.get("losses", 0),
        "ot_losses": raw.get("otLosses", 0),
        "saves": raw.get("saves", 0),
        "save_pct": round(raw.get("savePct", 0) * 100, 1) if raw.get("savePct") else 0,
        "goals_against_avg": round(raw.get("goalsAgainstAverage", 0), 2),
        "goals_against": raw.get("goalsAgainst", 0),
        "shots_against": raw.get("shotsAgainst", 0),
        "shutouts": raw.get("shutouts", 0),
        "toi_total": round(raw.get("timeOnIce", 0) / 60, 1) if raw.get("timeOnIce") else 0,
        "shots": 0,
        "shooting_pct": 0,
        "power_play_goals": 0,
        "power_play_points": 0,
        "short_handed_goals": 0,
        "short_handed_points": 0,
        "game_winning_goals": 0,
        "overtime_goals": 0,
        "even_strength_goals": 0,
        "even_strength_points": 0,
        "points_per_game": 0,
        "toi_per_game": 0,
        "faceoff_win_pct": 0,
        "season": "2025-2026",
        "seeded_at": datetime.now(timezone.utc),
    }


async def seed_players():
    """Main seeding function."""
    from nhlpy.nhl_client import NHLClient

    mongo_url = os.environ['MONGO_URL']
    db_name = os.environ['DB_NAME']
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    nhl_client = NHLClient()

    # Step 1: Fetch team rosters for team mapping
    logger.info("Fetching team rosters for player-team mapping...")
    team_map = fetch_team_rosters(nhl_client)
    logger.info(f"Mapped {len(team_map)} players to teams")

    # Step 2: Fetch all skaters
    logger.info("Fetching skater stats from NHL API...")
    raw_skaters = fetch_skaters(nhl_client)
    logger.info(f"Fetched {len(raw_skaters)} skaters")

    # Step 3: Fetch all goalies
    logger.info("Fetching goalie stats from NHL API...")
    raw_goalies = fetch_goalies(nhl_client)
    logger.info(f"Fetched {len(raw_goalies)} goalies")

    # Step 4: Transform data
    players = []
    for raw in raw_skaters:
        players.append(transform_skater(raw, team_map))
    for raw in raw_goalies:
        players.append(transform_goalie(raw, team_map))

    logger.info(f"Total players to seed: {len(players)}")

    # Step 5: Clear existing and insert
    existing_count = await db.players.count_documents({})
    if existing_count > 0:
        logger.info(f"Clearing {existing_count} existing players...")
        await db.players.delete_many({})

    if players:
        await db.players.insert_many(players)
        logger.info(f"Seeded {len(players)} NHL players into database")

    # Step 6: Create indexes
    await db.players.create_index("name")
    await db.players.create_index("team")
    await db.players.create_index("position")
    await db.players.create_index("nhl_id", unique=True)
    await db.players.create_index("points")

    # Step 7: Print summary
    skater_count = sum(1 for p in players if p["player_type"] == "skater")
    goalie_count = sum(1 for p in players if p["player_type"] == "goalie")
    teams_found = len(set(p["team"] for p in players if p["team"]))

    logger.info(f"\n{'='*50}")
    logger.info(f"SEED COMPLETE")
    logger.info(f"  Skaters: {skater_count}")
    logger.info(f"  Goalies: {goalie_count}")
    logger.info(f"  Teams represented: {teams_found}")
    logger.info(f"  Season: 2025-2026")
    logger.info(f"{'='*50}")

    # Top 10 scorers
    top_scorers = sorted([p for p in players if p["player_type"] == "skater"], key=lambda x: x["points"], reverse=True)[:10]
    logger.info("\nTop 10 Scorers:")
    for i, p in enumerate(top_scorers, 1):
        logger.info(f"  {i}. {p['name']} ({p['team']}) - {p['points']} pts ({p['goals']}G {p['assists']}A)")

    client.close()


if __name__ == "__main__":
    asyncio.run(seed_players())
