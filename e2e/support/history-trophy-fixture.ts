import { ObjectId } from 'mongodb';
import type { APIRequestContext } from '@playwright/test';
import { fixture, database, result } from './h2h';
export const years = [2026, 2024, 2020, 2019];
export async function historyFixture(api: APIRequestContext, format: 'h2h-points' | 'h2h-categories' | 'rotisserie' = 'h2h-points') {
  const league = await fixture(api, format === 'rotisserie' ? 'h2h-points' : format, false);
  if (format === 'rotisserie') await result(await api.put(`/api/leagues/${league.id}`, {data:{scoring_format:'rotisserie'}}));
  await database(async db => {
    await db.collection('leagues').updateOne({_id:new ObjectId(league.id)}, {$set:{current_season_year:2026}});
    const players = league.teams.flatMap((team, i) => team.players.map((id, j) => ({
      player_id:id, name:`History ${i+1} ${['Skater','Defense','Goalie'][j]}`, position:['C','D','G'][j], team:'TOR',
      season_stats: j === 2 ? {wins:10-i, saves:100, goals_against:10, shutouts:0} : {points:100-i*5-j*10, plus_minus:0},
    })));
    for (const player of players) await db.collection('players').updateOne({_id:new ObjectId(player.player_id)},{$set:{name:player.name,position:player.position,season_stats:player.season_stats}});
    await db.collection('league_seasons').insertMany(years.map((year, index) => ({
      league_id:league.id, season_year:year, status:'completed', snapshot_at:new Date().toISOString(),
      champion_team_name:league.teams[0].name,
      teams:league.teams.map((team,i)=>({team_id:team.id,team_name:team.name,roster:team.players,
        wins:i===0?8:3,losses:i===0?2:9,ties:i===0?2:0,points_for:1000-i*50+index*10,points_against:500,
        division:'North',conference:'East',awards:i===0?{championship_won_at:`${year}-05-01`,division_winner_at:`${year}-05-01`,conference_winner_at:`${year}-05-01`}:{}
      })), players,
    })));
  });
  return league;
}
