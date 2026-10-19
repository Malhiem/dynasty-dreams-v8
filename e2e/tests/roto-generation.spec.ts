import {test,expect} from '@playwright/test';
import {ObjectId} from 'mongodb';
import {actors,dispose} from '../support/access-history';
import {database,result} from '../support/h2h';
import {generatedFixture} from '../support/roto-generation';
test('Rotisserie calendar has dates without regular opponents and generates idempotently',async()=>{
 const a=await actors();try{
  const l=await generatedFixture(a.commissioner.api,false);const url=`/api/leagues/${l.id}/roto/generate`;
  for(const actor of [a.anonymous,a.expired])expect((await actor.api.post(url)).status()).toBe(401);
  expect((await a.outsider.api.post(url)).status()).toBe(403);
  const first=await result(await a.commissioner.api.post(url));expect(first.periods).toEqual([{id:1,startDate:'2025-01-01',endDate:'2025-01-07',type:'regular'}]);expect(first.playoff_matchups).toBe(0);
  const retry=await Promise.all([a.commissioner.api.post(url),a.commissioner.api.post(url)]);for(const r of retry)expect((await result(r)).reused).toBe(true);
  await database(async db=>{expect(await db.collection('matchups').countDocuments({league_id:l.id})).toBe(0);expect(await db.collection('audit_log').countDocuments({league_id:l.id,action:'roto_schedule_generated'})).toBe(1);});
  const close=await result(await a.commissioner.api.post(`/api/leagues/${l.id}/roto/recompute`,{data:{period:1,close:true}}));expect(close.closed).toBe(true);
  const standings=await result(await a.commissioner.api.get(`/api/leagues/${l.id}/roto/standings`));expect(standings.totals[l.teams[0].id].total_points).toBe(16);expect(standings.totals[l.teams[7].id].total_points).toBe(2);
 }finally{await dispose(a);}
});
test('Rotisserie real category scores advance eight teams to a champion and survive retries',async({},info)=>{
 const a=await actors();try{
  const l=await generatedFixture(a.commissioner.api);await result(await a.commissioner.api.post(`/api/leagues/${l.id}/roto/generate`));
  const close=(period:number)=>a.commissioner.api.post(`/api/leagues/${l.id}/roto/recompute`,{data:{period,close:true}});
  expect((await close(2)).status()).toBe(409);await result(await close(1));
  const stages=[];let previous:string[]=[];
  for(const [index,period] of [2,3,4].entries()){
   const retries=await Promise.all([close(period),close(period)]);for(const r of retries)await result(r);
   const rows=await result(await a.commissioner.api.get(`/api/matchups/${l.id}/results?week=${period}`));expect(rows).toHaveLength([4,2,1][index]);
   const participants=rows.flatMap((g:any)=>[g.home_team_id,g.away_team_id]);if(previous.length)expect(participants.sort()).toEqual(previous.sort());
   previous=rows.map((g:any)=>{expect(g.status).toBe('completed');const hi=l.teams.findIndex(t=>t.id===g.home_team_id),ai=l.teams.findIndex(t=>t.id===g.away_team_id);expect(g.home_score).toBe((hi+1)*2);expect(g.away_score).toBe((ai+1)*2);expect(g.winner).toBe(hi>ai?g.home_team_id:g.away_team_id);return g.winner;});stages.push(rows);
  }
  expect(previous).toEqual([l.teams[7].id]);
  const snapshot=await result(await a.commissioner.api.post(`/api/leagues/${l.id}/complete-season`,{data:{season_year:2025}}));expect(snapshot.champion).toBe(l.teams[7].name);
  await database(async db=>{expect(await db.collection('matchups').countDocuments({league_id:l.id})).toBe(7);expect(await db.collection('activity_feed').countDocuments({league_id:l.id,event_type:'championship_awarded'})).toBe(1);});
  await result(await a.commissioner.api.post(`/api/leagues/${l.id}/renew-season`,{data:{new_season_year:2026,carry_over_settings:true,reset_records:true}}));
  await database(async db=>{expect(await db.collection('matchups').countDocuments({league_id:l.id,season:'2025-26'})).toBe(7);expect(await db.collection('roto_period_results').countDocuments({league_id:l.id,season:'2025-26',closed:true})).toBe(4);const renewed=await db.collection('leagues').findOne({_id:new ObjectId(l.id)});expect(renewed!.roto_scoring_periods).toEqual([]);expect(renewed!.season).toBe('2026-27');});
  const renewedStandings=await result(await a.commissioner.api.get(`/api/leagues/${l.id}/roto/standings`));expect(renewedStandings.awaiting_generation).toBe(true);for(const t of Object.values(renewedStandings.totals) as any[])expect(t.total_points).toBe(0);
  await info.attach('actual-roto-progression',{body:JSON.stringify(stages,null,2),contentType:'application/json'});
 }finally{await dispose(a);}
});
test('Rotisserie finalized calendar cannot be replaced and future periods cannot close',async()=>{
 const a=await actors();try{
  const l=await generatedFixture(a.commissioner.api);await result(await a.commissioner.api.post(`/api/leagues/${l.id}/roto/generate`));await result(await a.commissioner.api.post(`/api/leagues/${l.id}/roto/recompute`,{data:{period:1,close:true}}));
  await database(async db=>{await db.collection('leagues').updateOne({_id:new ObjectId(l.id)},{$set:{'scheduler_calendars.2025.regularPeriods.0.startDate':'2025-01-02'}});});
  expect((await a.commissioner.api.post(`/api/leagues/${l.id}/roto/generate`)).status()).toBe(409);
  await database(async db=>{await db.collection('leagues').updateOne({_id:new ObjectId(l.id)},{$set:{'roto_scoring_periods.1.endDate':'2099-01-01'}});});
  expect((await a.commissioner.api.post(`/api/leagues/${l.id}/roto/recompute`,{data:{period:2,close:true}})).status()).toBe(409);
 }finally{await dispose(a);}
});

test('Rotisserie elimination exact ties advance the higher original regular seed',async()=>{
 const a=await actors();try{
  const l=await generatedFixture(a.commissioner.api);await database(async db=>{await db.collection('player_game_logs').updateMany({player_id:{$in:await db.collection('teams').find({league_id:l.id}).toArray().then(rows=>rows.flatMap(t=>t.roster))},date:{$gte:'2025-01-08'}},{$set:{goals:0,assists:0}});});
  await result(await a.commissioner.api.post(`/api/leagues/${l.id}/roto/generate`));
  for(const period of [1,2])await result(await a.commissioner.api.post(`/api/leagues/${l.id}/roto/recompute`,{data:{period,close:true}}));
  const games=await result(await a.commissioner.api.get(`/api/matchups/${l.id}/results?week=2`));for(const g of games){expect(g.home_score).toBe(g.away_score);expect(g.winner).toBe(g.home_team_id);expect(g.tie_break).toBe('higher_regular_seed');}
 }finally{await dispose(a);}
});
test('generated condensed Rotisserie uses playoff category totals without opponent games',async()=>{
 const a=await actors();try{
  const l=await generatedFixture(a.commissioner.api);await database(async db=>{await db.collection('leagues').updateOne({_id:new ObjectId(l.id)},{$set:{playoff_format:'condensed_roto',playoff_roto_fresh_totals:true,playoff_roto_seed_bonuses:{}}});});
  await result(await a.commissioner.api.post(`/api/leagues/${l.id}/roto/generate`));
  for(const period of [1,2,3,4,4])await result(await a.commissioner.api.post(`/api/leagues/${l.id}/roto/recompute`,{data:{period,close:true}}));
  const standings=await result(await a.commissioner.api.get(`/api/leagues/${l.id}/roto/standings`));expect(standings.totals[l.teams[7].id].total_points).toBe(16);expect(standings.totals[l.teams[0].id].total_points).toBe(2);
  const snapshot=await result(await a.commissioner.api.post(`/api/leagues/${l.id}/complete-season`,{data:{season_year:2025}}));expect(snapshot.champion).toBe(l.teams[7].name);
  await database(async db=>expect(await db.collection('matchups').countDocuments({league_id:l.id})).toBe(0));
 }finally{await dispose(a);}
});
