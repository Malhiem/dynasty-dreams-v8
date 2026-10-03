import {test,expect} from '@playwright/test';
import {ObjectId} from 'mongodb';
import {actors,dispose,type Actors,evidence} from '../support/access-history';
import {database,result} from '../support/h2h';
import {salaryLeague,settings,price,financial,execute,proposal,denied} from '../support/salary';
let a:Actors;test.beforeAll(async()=>{a=await actors();});test.afterAll(async()=>{if(a)await dispose(a);});
const year=new Date().getUTCFullYear();
const paths=['salary-retention-slots','admin/cap-settings',''] as const;
for(const path of paths)for(const slots of [0,1,2,3,4,10,-1,2.5])test(`C06 ${path||'general'} slots=${slots}`,async({},info)=>{
 const l=await salaryLeague(a);const r=await a.commissioner.api.put(`/api/leagues/${l.id}${path?'/'+path:''}`,{data:{salary_retention_slots:slots}});
 if(Number.isInteger(slots)&&slots>=0&&slots<=3)await result(r,info);else await denied(r,info,/slot|3|maximum|less|between/i);
 const saved=await result(await a.commissioner.api.get(`/api/leagues/${l.id}`),info);expect(saved.salary_retention_slots).toBe(Number.isInteger(slots)&&slots>=0&&slots<=3?slots:3);
});
for(const slots of [0,1,2,3])test(`R05 actual executed retentions stop at configured ${slots} slots`,async({},info)=>{
 const l=await salaryLeague(a);await settings(l,{salary_retention_slots:slots});
 const ids=[...l.teams[0].players,l.teams[7].players[2]];for(const id of ids)await price(id,1000000);
 await database(db=>db.collection('teams').updateOne({_id:new ObjectId(l.teams[0].id)},{$set:{roster:ids,salary_used:4000000,lineup:Object.fromEntries(ids.map(id=>[id,{section:'forward',slot:'C'}]))}}));
 for(let i=0;i<slots;i++)await execute(a,l,50,info,0,1,ids[i]);
 const c=await result(await a.manager.api.get(`/api/teams/${l.teams[0].id}/compliance`),info);
 expect.soft(c.salary_retention_slots_used).toBe(slots);expect.soft(c.salary_retention_slots_total).toBe(slots);expect.soft(c.salary_retention_slots_remaining).toBe(0);
 const before=await financial(l);let r=await proposal(a,l,50,0,1,ids[slots]);if(r.ok()){const p=await r.json();r=await a.manager2.api.post(`/api/trades/${p._id||p.id}/accept`);}
 await denied(r,info,/slot|retention|retained/i);expect(await financial(l)).toEqual(before);
});
for(const format of ['h2h-points','h2h-categories','rotisserie']){
 test(`L02 ${format} double retention splits 10M into 5M 2.5M 2.5M`,async({},info)=>{
  const l=await salaryLeague(a,format);await execute(a,l,50,info);await execute(a,l,50,info,1,2);
  const f=await financial(l);await evidence(info,'chain-state',f);
  for(const [i,amount] of [5000000,2500000].entries())expect.soft(f.retained.find((r:any)=>r.retainer_team_id===l.teams[i].id)?.amount).toBe(amount);
  const overview=await result(await a.commissioner.api.get(`/api/salary-cap/${l.id}`),info);
  for(const [i,amount] of [75000000,92500000,22500000].entries()){
   expect.soft(overview.teams.find((t:any)=>t.team_id===l.teams[i].id).cap_used).toBe(amount);
   const c=await result(await a.commissioner.api.get(`/api/teams/${l.teams[i].id}/compliance`),info);
   expect.soft(c.salary_used).toBe(amount);expect.soft(c.salary_retention_slots_used).toBe(i<2?1:0);
  }
 });
 for(const offseason of [false,true])test(`L04 ${format} real ${offseason?'offseason':'in-season'} trade has one applicable season`,async({},info)=>{
  const l=await salaryLeague(a,format),target=year+(offseason?1:0);
  await settings(l,{current_season_year:year,current_season_status:offseason?'complete':'in_progress',season_start_date:`${year}-01-01`,season_end_date:`${year}-12-31`});
  await execute(a,l,50,info);
  const schedule=await result(await a.commissioner.api.get(`/api/teams/${l.teams[0].id}/dead-cap-schedule`),info);
  expect.soft(schedule.schedule.map((r:any)=>({year:r.year,total:r.total}))).toEqual([{year:target,total:5000000}]);
  if(offseason)await result(await a.commissioner.api.post(`/api/leagues/${l.id}/renew-season`,{data:{new_season_year:target}}),info);
  const active=await result(await a.manager.api.get(`/api/teams/${l.teams[0].id}/compliance`),info);
  expect.soft(active.retained_salary_total).toBe(5000000);expect.soft(active.salary_retention_slots_used).toBe(1);
  await result(await a.commissioner.api.post(`/api/leagues/${l.id}/complete-season`,{data:{season_year:target}}),info);
  const ended=await result(await a.manager.api.get(`/api/teams/${l.teams[0].id}/compliance`),info);
  expect.soft(ended.retained_salary_total).toBe(0);expect.soft(ended.salary_retention_slots_used).toBe(0);
  await result(await a.commissioner.api.post(`/api/leagues/${l.id}/renew-season`,{data:{new_season_year:target+1}}),info);
  const renewed=await result(await a.manager.api.get(`/api/teams/${l.teams[0].id}/compliance`),info);
  expect.soft(renewed.retained_salary_total).toBe(0);expect.soft(renewed.salary_retention_slots_used).toBe(0);
 });
 test(`L04 ${format} existing monetary obligation expires on season completion`,async({},info)=>{
  const l=await salaryLeague(a,format),pid=l.teams[0].players[0],tid=l.teams[0].id;
  await settings(l,{current_season_year:year,current_season_status:'in_progress'});
  // Pre-existing obligation fixture isolates expiry from the known trade-creation defect.
  await database(async db=>{
   await db.collection('salary_retentions').insertOne({league_id:l.id,retainer_team_id:tid,player_id:pid,amount:5000000,pct:50,created_at:new Date(),season_year:year});
   await db.collection('teams').updateOne({_id:new ObjectId(tid)},{$set:{roster:[l.teams[0].players[1]],salary_retentions:[{player_id:pid,amount:5000000,season_year:year}],dead_cap_schedule:[{year,amount:5000000,source:'retention',player_id:pid}]}});
  });
  const before=await result(await a.manager.api.get(`/api/teams/${tid}/compliance`),info);expect(before.retained_salary_total).toBe(5000000);expect(before.salary_retention_slots_used).toBe(1);
  await result(await a.commissioner.api.post(`/api/leagues/${l.id}/complete-season`,{data:{season_year:year}}),info);
  for(const phase of ['completed','renewed']){
   if(phase==='renewed')await result(await a.commissioner.api.post(`/api/leagues/${l.id}/renew-season`,{data:{new_season_year:year+1}}),info);
   const c=await result(await a.manager.api.get(`/api/teams/${tid}/compliance`),info,phase);expect.soft(c.retained_salary_total).toBe(0);expect.soft(c.salary_retention_slots_used).toBe(0);expect.soft(c.salary_used).toBe(70000000);
  }
 });
}

test('E06 competing retained trades can consume the last slot only once',async({},info)=>{
 const l=await salaryLeague(a);await settings(l,{salary_retention_slots:1});
 for(const pid of l.teams[0].players.slice(0,2))await price(pid,1000000);
 const proposals=[];for(const pid of l.teams[0].players.slice(0,2))proposals.push(await result(await proposal(a,l,50,0,1,pid),info));
 const responses=await Promise.all(proposals.map(p=>a.manager2.api.post(`/api/trades/${p._id||p.id}/accept`)));
 expect(responses.map(r=>r.status()).sort()).toEqual([200,400]);
 const state=await financial(l);expect(state.retained).toHaveLength(1);expect(state.retained[0].amount).toBe(500000);
 const c=await result(await a.manager.api.get(`/api/teams/${l.teams[0].id}/compliance`),info);
 expect(c.salary_retention_slots_used).toBe(1);expect(c.salary_used).toBe(1500000);
});
test('L04 season snapshot preserves retention and renewed receiver pays full salary',async({},info)=>{
 const l=await salaryLeague(a);await settings(l,{current_season_year:year,current_season_status:'in_progress',season_end_date:`${year}-12-31`});
 await execute(a,l,50,info);
 await result(await a.commissioner.api.post(`/api/leagues/${l.id}/complete-season`,{data:{season_year:year}}),info);
 const snapshot=await result(await a.commissioner.api.get(`/api/leagues/${l.id}/seasons/${year}`),info);
 const old=snapshot.teams.find((t:any)=>t.team_id===l.teams[0].id);
 expect(old.salary_used).toBe(75000000);expect(old.retention_history[0].amount).toBe(5000000);
 await result(await a.commissioner.api.post(`/api/leagues/${l.id}/complete-season`,{data:{season_year:year}}),info);
 const recomputed=await result(await a.commissioner.api.get(`/api/leagues/${l.id}/seasons/${year}`),info);
 expect(recomputed.teams.find((t:any)=>t.team_id===l.teams[0].id).salary_used).toBe(75000000);

 await result(await a.commissioner.api.post(`/api/leagues/${l.id}/renew-season`,{data:{new_season_year:year+1}}),info);
 const receiver=await result(await a.manager2.api.get(`/api/teams/${l.teams[1].id}/compliance`),info);
 expect(receiver.salary_used).toBe(100000000);
 const reread=await result(await a.commissioner.api.get(`/api/leagues/${l.id}/seasons/${year}`),info);expect(reread.teams).toEqual(snapshot.teams);
 const schedule=await result(await a.manager.api.get(`/api/teams/${l.teams[0].id}/dead-cap-schedule`),info);
 expect(schedule.schedule.map((r:any)=>({year:r.year,total:r.total}))).toEqual([{year,total:5000000}]);
});
