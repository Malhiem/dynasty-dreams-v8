import {expect,type APIResponse,type TestInfo} from '@playwright/test';
import {ObjectId} from 'mongodb';
import {league,type Actors,evidence} from './access-history';
import {database,result,type League} from './h2h';
export async function salaryLeague(a:Actors,format='h2h-points'){
 const l=await league(a,format);
 await database(async db=>{
  await db.collection('leagues').updateOne({_id:new ObjectId(l.id)},{$set:{salary_cap_enabled:true,salary_cap:100000000,salary_retention_enabled:true,salary_retention_max_pct:50,salary_retention_slots:3,cap_floor_enabled:false,allow_illegal_rosters:false,roster_spots:25,enforce_position_maxes:false,minors_enabled:false,minors_cap_treatment:'full',injury_reserve_compliance_mode:'none'}});
  for(const [i,t] of l.teams.entries()){
   const ids=i===0?t.players.slice(0,2):t.players.slice(0,1);
   const amounts=i===0?[10000000,70000000]:[i===1?90000000:20000000];
   for(const [j,id] of ids.entries())await db.collection('players').updateOne({_id:new ObjectId(id)},{$set:{contract:{aav:amounts[j],salary:amounts[j],yearsRemaining:3},salary:amounts[j],cap_hit:amounts[j],age:28,is_prospect:false}});
   await db.collection('teams').updateOne({_id:new ObjectId(t.id)},{$set:{roster:ids,lineup:Object.fromEntries(ids.map(id=>[id,{section:'forward',slot:'C'}])),salary_used:amounts.reduce((x,y)=>x+y,0),salary_retentions:[],dead_cap_schedule:[]}});
  }
 });return l;
}
export async function settings(l:League,patch:any){await database(db=>db.collection('leagues').updateOne({_id:new ObjectId(l.id)},{$set:patch}));}
export async function price(id:string,value:number){await database(db=>db.collection('players').updateOne({_id:new ObjectId(id)},{$set:{contract:{aav:value,salary:value,yearsRemaining:3},salary:value,cap_hit:value}}));}
export async function freePlayer(l:League,amount:number){const id=l.teams[7].players[2];await price(id,amount);return id;}
export async function financial(l:League){return database(async db=>JSON.parse(JSON.stringify({
 teams:await db.collection('teams').find({league_id:l.id},{projection:{roster:1,salary_used:1,salary_retentions:1,dead_cap_schedule:1}}).sort({_id:1}).toArray(),
 contracts:await db.collection('contracts').find({league_id:l.id}).sort({_id:1}).toArray(),
 retained:await db.collection('salary_retentions').find({league_id:l.id}).sort({_id:1}).toArray(),
})));}
export async function payroll(a:Actors,l:League,info:TestInfo){
 const overview=await result(await a.commissioner.api.get(`/api/salary-cap/${l.id}`),info,'salary-overview');
 const compliance=[];for(const t of l.teams.slice(0,2))compliance.push(await result(await a.commissioner.api.get(`/api/teams/${t.id}/compliance`),info,'compliance'));
 const schedules=[];for(const t of l.teams.slice(0,2))schedules.push(await result(await a.commissioner.api.get(`/api/teams/${t.id}/dead-cap-schedule`),info,'dead-cap'));
 return {overview,compliance,schedules};
}
export async function assertPayroll(a:Actors,l:League,values:number[],info:TestInfo){
 const read=await payroll(a,l,info);
 for(const [i,value] of values.entries()){
  expect.soft(read.overview.teams.find((t:any)=>t.team_id===l.teams[i].id).cap_used,'overview payroll').toBe(value);
  expect.soft(read.compliance[i].salary_used,'compliance payroll').toBe(value);
 }return read;
}
export async function proposal(a:Actors,l:League,pct:any=0,from=0,to=1,pid=l.teams[0].players[0]){
 const actor=from===0?a.manager:from===1?a.manager2:a.commissioner;
 return actor.api.post('/api/trades',{data:{league_id:l.id,target_team_id:l.teams[to].id,assets_offered:[{asset_type:'player',player_id:pid,player_name:'Salary fixture',salary_retained_pct:pct}],assets_requested:[]}});
}
export async function execute(a:Actors,l:League,pct=0,info?:TestInfo,from=0,to=1,pid=l.teams[0].players[0]){
 const p=await result(await proposal(a,l,pct,from,to,pid),info,'proposal');
 const actor=to===0?a.manager:to===1?a.manager2:a.commissioner;
 const x=await result(await actor.api.post(`/api/trades/${p._id||p.id}/accept`),info,'accept');
 expect(x.executed,'Fixture trade must execute').toBe(true);return p._id||p.id;
}
export async function denied(response:APIResponse,info:TestInfo,reason:RegExp){
 const body=await response.text();await evidence(info,'denial',{status:response.status(),body});
 expect.soft([400,422]).toContain(response.status());expect.soft(body).toMatch(reason);
}
export async function deniedTrade(a:Actors,l:League,pct:any,info:TestInfo){
 const before=await financial(l);let response=await proposal(a,l,pct);
 if(response.ok()){const p=await response.json();response=await a.manager2.api.post(`/api/trades/${p._id||p.id}/accept`);}
 await denied(response,info,/cap|retention|retained|salary/i);expect(await financial(l)).toEqual(before);
}
export async function seedRetention(l:League,mirror=false){
 const pid=l.teams[0].players[0],tid=l.teams[0].id,year=new Date().getUTCFullYear();
 await database(async db=>{
  await db.collection('salary_retentions').insertOne({league_id:l.id,retainer_team_id:tid,player_id:pid,amount:4000000,pct:40,created_at:new Date()});
  if(mirror)await db.collection('teams').updateOne({_id:new ObjectId(tid)},{$set:{dead_cap_schedule:[0].map(i=>({year:year+i,amount:4000000,source:'retention',player_id:pid,player_name:'Fixture P'}))}});
 });
}
export const contract=(l:League,team=0)=>({league_id:l.id,team_id:l.teams[team].id,player_id:l.teams[team].players[0],aav:10000000,total_value:30000000,years:3,start_year:2026});
