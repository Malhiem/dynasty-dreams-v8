import { expect, type APIRequestContext, type APIResponse, type TestInfo } from "@playwright/test";
import { MongoClient, ObjectId, type Db } from "mongodb";

export type Format = "h2h-points" | "h2h-categories";
export type Stats = { goals: number; assists: number; shots: number; penalty_minutes: number };
export interface Team { id: string; name: string; players: string[]; stats: Stats; points: number }
export interface League { id: string; format: Format; teams: Team[] }
export const weights = { goals: 3.5, assists: 1.2, shots: 0.5, penalty_minutes: -0.2 };
export const categories = ["goals", "assists", "shots"];
export const zero: Stats = { goals: 0, assists: 0, shots: 0, penalty_minutes: 0 };
export const gameId = (l: Pick<League, "teams">, week: number) => Number.parseInt(l.teams[0].players[0].slice(-12),16)*8+week;
export const liveStats = (l: Pick<League, "teams">, stats: any) => Object.fromEntries(Array.from({length:7},(_,i)=>[gameId(l,i+1),{...stats,updated_at:new Date(Date.UTC(2026,9,8+i*7,12)).toISOString()}]));
export const points = (s: Stats) => Math.round((s.goals*3.5+s.assists*1.2+s.shots*0.5-s.penalty_minutes*0.2)*10)/10;

export async function database<T>(fn: (db: Db) => Promise<T>): Promise<T> {
  if (process.env.E2E_BASE_URL !== "http://web" || process.env.H2H_ISOLATED !== "1") throw new Error("H2H fixtures require the dedicated Compose environment");
  const client = new MongoClient("mongodb://mongo:27017");
  try { return await fn(client.db("dynasty_dreams_e2e")); } finally { await client.close(); }
}
export async function result(response: APIResponse, info?: TestInfo, label = "response"): Promise<any> {
  const body = await response.text();
  if (info) await info.attach(label, { body: JSON.stringify({url: response.url(), status: response.status(), body: (()=>{try{return JSON.parse(body);}catch{return body;}})()}, null, 2), contentType: "application/json" });
  expect(response.ok(), `${response.status()} ${response.url()}: ${body.slice(0,500)}`).toBeTruthy();
  return JSON.parse(body);
}
export async function login(request: APIRequestContext) {
  await result(await request.post("/api/auth/login", { data: { email: process.env.E2E_ADMIN_EMAIL, password: process.env.E2E_ADMIN_PASSWORD } }));
}
export async function fixture(request: APIRequestContext, format: Format, playoffs = false, count = 8): Promise<League> {
  const created = await result(await request.post("/api/leagues", { data: {
    // Creation uses the legacy enum; League Setup's update API persists the UI's H2H variants.
    name: `H2H acceptance ${format} ${crypto.randomUUID()}`, sport: "nhl", format: "dynasty", scoring_format: "head_to_head", max_teams: count, is_private: true,
  } }));
  const teams: Team[] = [];
  await database(async db => {
    await db.collection("teams").deleteMany({league_id: created.id});
    for (let i=0;i<count;i++) {
      const teamId = new ObjectId(), ids = [new ObjectId(),new ObjectId(),new ObjectId()];
      const stats: Stats = {goals: 8-i, assists:8-i, shots:2*(8-i), penalty_minutes:i};
      const second = {goals:1,assists:1,shots:2,penalty_minutes:0};
      await db.collection("players").insertMany(ids.map((id,j) => {
        const s = j===0 ? stats : j===1 ? second : zero;
        return {_id:id,name:`H2H ${i+1} player ${j+1}`, position:"C", player_type:"skater", team:"TOR", ...s,
          season_stats:s, period_stats:{"1":s,"2":s,"3":s,"4":s,"5":s,"6":s,"7":s},
          live_stats:{"e2e-week-1":{...s,updated_at:"2026-10-08T12:00:00Z"},"e2e-week-2":{...s,updated_at:"2026-10-15T12:00:00Z"}}};
      }));
      const name=`H2H Team ${String(i+1).padStart(2,"0")}`;
      await db.collection("teams").insertOne({_id:teamId,league_id:created.id,name,owner_id:created.commissioner_id,owner_name:created.commissioner_name,
        roster:ids.map(String),lineup:Object.fromEntries(ids.map((id,j)=>[String(id),{section:j===2?"bench":"forward",slot:j===2?"BN":"C"}])),
        wins:0,losses:0,ties:0,points_for:0,points_against:0,live_points:0,salary_used:0,is_commissioner_team:i===0,created_at:new Date()});
      const total = {goals:stats.goals+1,assists:stats.assists+1,shots:stats.shots+2,penalty_minutes:stats.penalty_minutes};
      teams.push({id:String(teamId),name,players:ids.map(String),stats:total,points:Math.round((points(stats)+points(second))*10)/10});
    }
    const seeded = {teams};
    for(const team of teams)for(const [j,pid] of team.players.entries()) {
      await db.collection("player_ownership_periods").insertOne({league_id:created.id,team_id:team.id,player_id:pid,acquired_at:new Date("2026-10-07T00:00:00Z"),released_at:null,source:"draft"});
      await db.collection("lineup_status_periods").insertOne({league_id:created.id,team_id:team.id,player_id:pid,started_at:new Date("2026-10-07T00:00:00Z"),ended_at:null,position:j===2?"bench":"forward"});
      const stats=j===0?{goals:8-teams.indexOf(team),assists:8-teams.indexOf(team),shots:2*(8-teams.indexOf(team)),penalty_minutes:teams.indexOf(team)}:j===1?{goals:1,assists:1,shots:2,penalty_minutes:0}:zero;
      await db.collection("players").updateOne({_id:new ObjectId(pid)},{$set:{live_stats:liveStats(seeded,stats)}});
    }
    for(let week=1;week<=7;week++)await db.collection("games").insertOne({nhl_game_id:gameId(seeded,week),start_time:new Date(Date.UTC(2026,9,8+(week-1)*7,12)).toISOString()});
    await db.collection("leagues").updateOne({_id:new ObjectId(created.id)},{$set:{current_teams:count,setup_wizard_complete:true,ownership_backfilled_at:new Date()}});
  });
  await result(await request.put(`/api/leagues/${created.id}`, {data:{scoring_format:format,max_teams:count,
    regular_season_weeks:4,matchup_length_days:7,opponents_per_matchup_period:1,season_start_date:"2026-10-07",season_end_date:"2026-11-24",
    playoffs_enabled:playoffs,playoff_format:playoffs?"playoff_tree":"h2h_matchup",playoff_teams:8,playoff_start_week:5,playoff_end_week:7,playoff_rounds:3,
    playoff_seeding_method:"high_vs_low",consolation_enabled:false,roto_categories:categories}}));
  await result(await request.post("/api/scoring/config",{data:{league_id:created.id,skater_scoring:weights,goalie_scoring:{wins:5,saves:0.2,goals_against:-1},roto_categories:categories}}));
  return {id:created.id,format,teams};
}
export async function generate(request: APIRequestContext,l:League,info?:TestInfo) {
  return result(await request.post("/api/matchups/generate-schedule",{data:{league_id:l.id}}),info,"schedule-generation");
}
export async function matches(request: APIRequestContext,l:League,week?:number,info?:TestInfo) {
  return result(await request.get(`/api/matchups/${l.id}${week?`/results?week=${week}`:""}`),info,`matchups-${week??"all"}`);
}
export async function simulate(request: APIRequestContext,l:League,week:number,info?:TestInfo) {
  return result(await request.post("/api/matchups/simulate-week",{data:{league_id:l.id,week}}),info,`simulate-${week}`);
}
export async function standings(request: APIRequestContext,l:League,info?:TestInfo) {
  return (await result(await request.get(`/api/leagues/${l.id}/standings`),info,"standings")).standings;
}
export async function daily(request: APIRequestContext,l:League,team:Team,week=1,info?:TestInfo) {
  return result(await request.get(`/api/matchups/${l.id}/daily-scoring?team_id=${team.id}&week=${week}`),info,`daily-${team.id}-${week}`);
}
/** Input changes only: never write matchup scores, winners, awards, or final records. */
export async function setStats(l:League,team:Team,stats:Stats,bench:Stats=zero) {
  await database(async db=>{
    for(const [i,id] of team.players.entries()) {
      const s=i===0?stats:i===2?bench:zero;
      await db.collection("players").updateOne({_id:new ObjectId(id)},{$set:{...s,season_stats:s,
        period_stats:Object.fromEntries([1,2,3,4,5,6,7].map(w=>[String(w),s])),
        live_stats:liveStats(l,s)}});
    }
  });
  team.stats=stats;team.points=points(stats);
}
export function categoryOutcome(a:Team,b:Team) {
  let home=0,away=0,ties=0;
  for(const k of categories as (keyof Stats)[]) {if(a.stats[k]>b.stats[k])home++;else if(a.stats[k]<b.stats[k])away++;else ties++;}
  return {home,away,ties,winner:home>away?a.id:away>home?b.id:null};
}

/** Change fixture input for the season, including its dated active-lineup record. */
export async function setSection(l:League,team:Team,pid:string,section:string) {
 await database(async db=>{
  await db.collection('teams').updateOne({_id:new ObjectId(team.id)},{$set:{[`lineup.${pid}`]:{section,slot:section==='goalie'?'G':section==='forward'?'C':section.toUpperCase()}}});
  await db.collection('lineup_status_periods').updateMany({league_id:l.id,team_id:team.id,player_id:pid},{$set:{position:section}});
 });
}
