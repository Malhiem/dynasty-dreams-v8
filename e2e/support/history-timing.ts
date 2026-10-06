import {ObjectId} from 'mongodb';
import {database,result,zero,type League} from './h2h';
import {type Actors} from './access-history';
import type {TestInfo} from '@playwright/test';

export type Game={start:string;goals:number;updated?:string};
// Seed input history only; never write calculated scores or standings.
export async function timingFixture(l:League,season:string,transfer:string|null,games:Game[],lineupChange?:'bench'|'forward') {
 await database(async db=>{
  const pid=l.teams[0].players[0],a=l.teams[0].id,b=l.teams[1].id;
  const initial=new Date(new Date(season+'T00:00:00Z').getTime()-86400000);
  const at=new Date(transfer||season+'T12:00:00Z');
  await db.collection('leagues').updateOne({_id:new ObjectId(l.id)},{$set:{season_start_date:season,matchup_length_days:1,current_week:1,ownership_backfilled_at:new Date()}});
  await db.collection('player_ownership_periods').deleteMany({league_id:l.id,player_id:pid});
  await db.collection('lineup_status_periods').deleteMany({league_id:l.id,player_id:pid});
  const spans=transfer&&!lineupChange?[{team_id:a,acquired_at:initial,released_at:at},{team_id:b,acquired_at:at,released_at:null}]:[{team_id:a,acquired_at:initial,released_at:null}];
  await db.collection('player_ownership_periods').insertMany(spans.map(s=>({...s,league_id:l.id,player_id:pid,source:'timing_fixture'})));
  const lineups=lineupChange?[
    {team_id:a,started_at:initial,ended_at:at,position:lineupChange==='bench'?'forward':'bench'},
    {team_id:a,started_at:at,ended_at:null,position:lineupChange},
  ]:spans.map(s=>({team_id:s.team_id,started_at:s.acquired_at,ended_at:s.released_at,position:'forward'}));
  await db.collection('lineup_status_periods').insertMany(lineups.map(s=>({...s,league_id:l.id,player_id:pid})));
  if(transfer&&!lineupChange){
   await db.collection('teams').updateOne({_id:new ObjectId(a)},{$pull:{roster:pid},$unset:{[`lineup.${pid}`]:''}} as any);
   await db.collection('teams').updateOne({_id:new ObjectId(b)},{$addToSet:{roster:pid},$set:{[`lineup.${pid}`]:{section:'forward',slot:'C'}}});
  }
  const base=Number.parseInt(pid.slice(-11),16)*16;
  const live:any={};
  for(const [i,g] of games.entries()){
   const id=base+i;
   await db.collection('games').updateOne({nhl_game_id:id},{$set:{date:new Date(g.start).toISOString().slice(0,10),start_time:g.start,puck_drop:g.start}},{upsert:true});
   live[String(id)]={...zero,goals:g.goals,updated_at:g.updated||g.start};
  }
  await db.collection('players').updateOne({_id:new ObjectId(pid)},{$set:{live_stats:live}});
 });
}

export async function timingTotals(a:Actors,l:League,format:string,week:number,info:TestInfo){
 const totals:number[]=[];
 for(const t of l.teams.slice(0,2)){
  const body=await result(await a.commissioner.api.get(`/api/matchups/${l.id}/daily-scoring?team_id=${t.id}&week=${week}`),info,`daily-${week}-${t.id}`);
  totals.push(body.players.reduce((n:number,p:any)=>n+Object.values(p.daily).reduce((s:number,d:any)=>s+d.goals,0),0));
 }
 const scores=await result(await a.commissioner.api.get(`/api/scoring/calculate/${l.id}?week=${week}`),info,`calculated-${week}`);
 const calculated=l.teams.slice(0,2).map(t=>scores.find((s:any)=>s.team_id===t.id).total_fantasy_points);
 let roto:number[]|undefined;
 if(format==='rotisserie'){
  const body=await result(await a.commissioner.api.get(`/api/leagues/${l.id}/roto/matchup?period=${week}`),info,`roto-${week}`);
  const goals=body.categories.find((c:any)=>c.key==='goals').team_stats;
  roto=l.teams.slice(0,2).map(t=>goals[t.id]||0);
 }
 return {daily:totals,calculated,...(roto?{roto}: {})};
}
