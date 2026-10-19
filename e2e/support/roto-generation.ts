import {ObjectId} from 'mongodb';
import {database,result} from './h2h';
import {createCondensedFixture} from './rotisserie';
import type {APIRequestContext} from '@playwright/test';
export async function generatedFixture(api:APIRequestContext,playoffs=true){
 const l=await createCondensedFixture(api);
 const dates=['2025-01-01','2025-01-08','2025-01-15','2025-01-22'];
 const periods=dates.map((startDate,i)=>({id:i+1,startDate,endDate:`2025-01-${String(7*(i+1)).padStart(2,'0')}`,type:i?'playoff':'regular'}));
 await database(async db=>{
  await db.collection('leagues').updateOne({_id:new ObjectId(l.id)},{$set:{season:'2025-26',current_season_year:2025,season_start_date:'2025-01-01',season_end_date:'2025-01-28',regular_season_weeks:1,matchup_length_days:7,playoff_start_week:2,playoff_end_week:4,playoff_rounds:3,playoff_format:'playoff_tree',playoff_teams:8,playoff_seeding_method:'high_vs_low',playoffs_enabled:playoffs,roto_playoffs_enabled:playoffs,playoff_roto_fresh_totals:false,playoff_roto_seed_bonuses:{},ownership_backfilled_at:new Date()}});
  for(const [i,t] of l.teams.entries()){
   const team=await db.collection('teams').findOne({_id:new ObjectId(t.id)});
   for(const pid of team!.roster){
    await db.collection('player_ownership_periods').insertOne({league_id:l.id,team_id:t.id,player_id:pid,acquired_at:new Date('2024-12-01'),released_at:null});
    await db.collection('lineup_status_periods').insertOne({league_id:l.id,team_id:t.id,player_id:pid,position:'forward',started_at:new Date('2024-12-01'),ended_at:null});
    await db.collection('players').updateOne({_id:new ObjectId(pid)},{$set:{live_stats:{},player_type:'skater'}});
    for(const [j,date] of dates.entries())await db.collection('player_game_logs').insertOne({player_id:pid,date,goals:j?i+1:8-i,assists:j?i+1:8-i});
   }
  }
 });
 await result(await api.put(`/api/leagues/${l.id}/scheduler/2025`,{data:{seasonStart:'2025-01-01',seasonEnd:'2025-01-07',scoringInterval:'weekly',startDay:3,mergeWeeks:1,matchupsPerPeriod:1,playoffStart:'2025-01-08',playoffEnd:'2025-01-28',playoffInterval:'weekly',regularPeriods:[periods[0]],playoffPeriods:periods.slice(1).map((p,i)=>({...p,id:i+1})),brackets:[{id:'main',name:'Championship',teams:8,rounds:3}]}}));
 return l;
}
