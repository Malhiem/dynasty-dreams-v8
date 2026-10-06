import { request as playwrightRequest, expect, type APIRequestContext, type TestInfo } from '@playwright/test';
import { ObjectId } from 'mongodb';
import { database, fixture, result, zero, type League } from './h2h';

export type Actor = { id: string; api: APIRequestContext; email: string };
export type Actors = { commissioner: Actor; manager: Actor; manager2: Actor; outsider: Actor; anonymous: Actor; expired: Actor };
export async function actors(): Promise<Actors> {
  const out: any = {};
  for (const name of ['commissioner','manager','manager2','outsider']) {
    const api = await playwrightRequest.newContext({baseURL:'http://web'});
    const email = `history-${name}-${crypto.randomUUID()}@e2e.dynastydreams.com`;
    const username = `qa${crypto.randomUUID().replaceAll('-','').slice(0,16)}`;
    await result(await api.post('/api/auth/register',{data:{email,username,password:'E2e-history-test-2026!'}}));
    const me = await result(await api.get('/api/auth/me'));
    expect(me.role).not.toMatch(/admin/);
    out[name] = {id:me.id,api,email};
  }
  out.anonymous = {id:'anonymous',email:'',api:await playwrightRequest.newContext({baseURL:'http://web'})};
  // Expired test token is signed with the isolated Compose JWT key only.
  const { createHmac } = await import('node:crypto');
  const enc = (x: any) => Buffer.from(JSON.stringify(x)).toString('base64url');
  const input = `${enc({alg:'HS256',typ:'JWT'})}.${enc({sub:out.manager.id,email:out.manager.email,type:'access',iat:1,exp:2})}`;
  const token = `${input}.${createHmac('sha256','e2e-only-jwt-secret').update(input).digest('base64url')}`;
  out.expired = {id:'expired',email:'',api:await playwrightRequest.newContext({baseURL:'http://web',extraHTTPHeaders:{Authorization:`Bearer ${token}`}})};
  return out;
}
export async function dispose(a: Actors) { for(const x of Object.values(a)) await x.api.dispose(); }
export async function league(a: Actors, format='h2h-points', initial='forward'): Promise<League> {
  const l = await fixture(a.commissioner.api,'h2h-points',false,8);
  await result(await a.commissioner.api.put(`/api/leagues/${l.id}`,{data:{scoring_format:format,roto_categories:['goals']}}));
  await result(await a.commissioner.api.post('/api/scoring/config',{data:{league_id:l.id,skater_scoring:{goals:1},goalie_scoring:{},roto_categories:['goals']}}));
  await database(async db=>{
    await db.collection("player_ownership_periods").deleteMany({league_id:l.id});
    await db.collection("lineup_status_periods").deleteMany({league_id:l.id});
    const start = new Date(Date.now()-7*86400000);
    for(const [i,t] of l.teams.entries()) {
      const owner = i===0?a.manager:i===1?a.manager2:a.commissioner;
      for (const [j,pid] of t.players.entries()) {
        const position = i===0 && j===0 ? initial : j===2 ? 'bench' : 'forward';
        if(position==='unowned') {
          await db.collection('teams').updateOne({_id:new ObjectId(t.id)},{$pull:{roster:pid},$unset:{[`lineup.${pid}`]:''}} as any);
          continue;
        }
        await db.collection('player_ownership_periods').insertOne({player_id:pid,team_id:t.id,league_id:l.id,acquired_at:start,released_at:null,source:'draft'});
        await db.collection('lineup_status_periods').insertOne({player_id:pid,team_id:t.id,league_id:l.id,position,started_at:start,ended_at:null});
        await db.collection('teams').updateOne({_id:new ObjectId(t.id)},{$set:{[`lineup.${pid}`]:{section:position,slot:position==='bench'?'BN':'C'}}});
      }
      await db.collection('teams').updateOne({_id:new ObjectId(t.id)},{$set:{owner_id:owner.id,owner_name:owner.email}});
      await db.collection('players').updateMany({_id:{$in:t.players.map(p=>new ObjectId(p))}},{$set:{...zero,season_stats:zero,period_stats:{'1':zero,'2':zero},live_stats:{}}});
    }
    await db.collection('leagues').updateOne({_id:new ObjectId(l.id)},{$set:{
      season_start_date:start.toISOString().slice(0,10),season_end_date:new Date(Date.now()+180*86400000).toISOString().slice(0,10),matchup_length_days:35,
      roster_lock_type:'daily',lineup_lock_minutes_before:0,trade_review_period_days:0,trade_review_period_hours:0,
      salary_cap_enabled:false,allow_illegal_rosters:true,transactions_config:{},current_season_year:2026,
      playoff_roto_seed_bonuses:{'1':4},
    }});
  });
  return l;
}
export async function state(l: League) {
  return database(async db=>{
    const all: any = {};
    for(const c of await db.listCollections().toArray()) {
      // League-scoped persistent state, including notifications, activity and queued jobs.
      const query: any = c.name==='leagues'?{_id:new ObjectId(l.id)}:{league_id:l.id};
      const rows = await db.collection(c.name).find(query).sort({_id:1}).toArray();
      if(rows.length) all[c.name]=rows;
    }
    return JSON.parse(JSON.stringify(all));
  });
}
export async function evidence(info: TestInfo, name: string, value: any) {
  await info.attach(name,{body:JSON.stringify(value,null,2),contentType:'application/json'});
}
const historyGames = new Map<string, {before:number;after:number;beforeTime:string;afterTime:string}>();
function games(l:League) {
  let g=historyGames.get(l.id);
  if(!g) {
    const base=Number.parseInt(l.teams[0].players[0].slice(-12),16)*4;
    g={before:base,after:base+1,beforeTime:new Date(Date.now()-2*86400000).toISOString(),afterTime:new Date(Date.now()+86400000).toISOString()};
    historyGames.set(l.id,g);
  }
  return g;
}
export async function seedStats(l: League, old=10, later=0) {
  const g=games(l);
  await database(async db=>{
    for(const [id,time] of [[g.before,g.beforeTime],[g.after,g.afterTime]] as const) {
      await db.collection('games').updateOne({nhl_game_id:id},{$set:{date:time.slice(0,10),start_time:time,puck_drop:time}},{upsert:true});
    }
    await db.collection('players').updateOne({_id:new ObjectId(l.teams[0].players[0])},{$set:{
      goals:old+later,season_stats:{...zero,goals:old+later},period_stats:{'1':{...zero,goals:old+later},'2':zero},
      live_stats:{[g.before]:{...zero,goals:old,updated_at:g.beforeTime},[g.after]:{...zero,goals:later,updated_at:g.afterTime}}
    }});
  });
}
export async function seedGap(l:League) {
  const id=games(l).after+1,time=new Date().toISOString();
  await database(async db=>{
    await db.collection('games').insertOne({nhl_game_id:id,date:time.slice(0,10),start_time:time,puck_drop:time});
    await db.collection('players').updateOne({_id:new ObjectId(l.teams[0].players[0])},{$set:{[`live_stats.${id}`]:{...zero,goals:4,updated_at:time},'period_stats.1.goals':14,'season_stats.goals':14,goals:14}});
  });
}
export async function propose(a: Actors,l: League,from=0,to=1) {
  const owner = from===0?a.manager:from===1?a.manager2:a.commissioner;
  const response=await result(await owner.api.post('/api/trades',{data:{league_id:l.id,target_team_id:l.teams[to].id,
    assets_offered:[{asset_type:'player',player_id:l.teams[0].players[0],player_name:'History player'}],assets_requested:[]}}));
  return {...response,id:response._id};
}
export async function trade(a: Actors,l: League,info: TestInfo,from=0,to=1) {
  const p = await propose(a,l,from,to);
  await evidence(info,'trade-proposal',p);
  const owner = to===0?a.manager:to===1?a.manager2:a.commissioner;
  const accepted = await result(await owner.api.post(`/api/trades/${p.id}/accept`),info,'trade-accepted');
  expect(accepted.executed,'Trade must actually execute before allocation is tested').toBe(true);
  await database(async db=>{
    const target=await db.collection('teams').findOne({_id:new ObjectId(l.teams[to].id)});
    const source=await db.collection('teams').findOne({_id:new ObjectId(l.teams[from].id)});
    expect(target!.roster).toContain(l.teams[0].players[0]);
    expect(source!.roster).not.toContain(l.teams[0].players[0]);
  });
  await lineup(a,l,to,'forward');
}
export async function lineup(a: Actors,l: League,index:number,section:string) {
  const owner=index===0?a.manager:index===1?a.manager2:a.commissioner;
  const t=await database(db=>db.collection('teams').findOne({_id:new ObjectId(l.teams[index].id)}));
  const mapping={...(t!.lineup||{}),[l.teams[0].players[0]]:{section,slot:section==='bench'?'BN':'C'}};
  return result(await owner.api.post(`/api/teams/${l.teams[index].id}/lineup`,{data:{lineup:mapping}}));
}
export async function allocation(a: Actors,l: League,format:string,info:TestInfo,label='allocation') {
  let totals: number[]=[];
  if(format==='rotisserie') {
    const body=await result(await a.commissioner.api.get(`/api/leagues/${l.id}/roto/matchup?period=1`),info,label);
    const goals=body.categories.find((c:any)=>c.key==='goals').team_stats;
    totals=l.teams.map(t=>goals[t.id]||0);
  } else {
    for(const t of l.teams.slice(0,3)) {
      const body=await result(await a.commissioner.api.get(`/api/matchups/${l.id}/daily-scoring?team_id=${t.id}&week=1`),info,`${label}-${t.id}`);
      totals.push(body.players.reduce((sum:number,p:any)=>sum+Object.values(p.daily).reduce((n:number,d:any)=>n+d.goals,0),0));
    }
  }
  await evidence(info,label+'-goals',totals);
  return totals.slice(0,3);
}
