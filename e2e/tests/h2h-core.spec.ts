import { expect } from "@playwright/test";
import { ObjectId } from "mongodb";
import { test } from "../support/h2h-cases";
import { fixture, generate, matches, simulate, standings, daily, result, setStats, database, categoryOutcome, zero, weights, setSection, type Format } from "../support/h2h";
const formats:Format[]=["h2h-points","h2h-categories"];
for(const format of formats) {
 test(`H2H-02 ${format} schedule integrity`,async({api},info)=>{
  const l=await fixture(api,format);await generate(api,l,info);const all=await matches(api,l,undefined,info);
  const regular=all.filter((m:any)=>!m.is_playoff);expect(regular).toHaveLength(16);
  for(const week of [1,2,3,4]) {const rows=regular.filter((m:any)=>m.week===week);expect(rows).toHaveLength(4);
   expect(rows.flatMap((m:any)=>[m.home_team_id,m.away_team_id]).sort()).toEqual(l.teams.map(t=>t.id).sort());
   for(const m of rows) expect(m.home_team_id).not.toBe(m.away_team_id);
  }
 });
 test(`H2H-04 ${format} active period stats reach weekly score`,async({api},info)=>{
  const l=await fixture(api,format);await generate(api,l);const t=l.teams[0];
  await setStats(l,t,{...zero,goals:2},{...zero,goals:100});
  await database(async db=>{await db.collection("players").updateOne({_id:new ObjectId(t.players[0])},{$set:{"live_stats.outside":{goals:999,updated_at:"2026-09-01T12:00:00Z"}}});});
  const d=await daily(api,l,t,1,info);expect.soft(d.period_start).toBe("2026-10-07");expect.soft(d.period_end).toBe("2026-10-13");
  expect.soft(d.period_total_fpts,"Only 2 active goals at configured 3.5; bench and outside-period stats excluded").toBe(7);
  const rows=await matches(api,l,1,info), m=rows.find((m:any)=>[m.home_team_id,m.away_team_id].includes(t.id));
  expect(m.home_team_id===t.id?m.home_score:m.away_score,"Live matchup total reflects active dated stats").toBe(7);
 });
 test(`H2H-05 ${format} bench IR minors exclusion`,async({api},info)=>{
  const l=await fixture(api,format);const t=l.teams[0];await setStats(l,t,{...zero,goals:2});
  const before=await daily(api,l,t,1,info);
  await setStats(l,t,{...zero,goals:2},{...zero,goals:100,assists:100,shots:100});
  for(const section of ["bench","ir","minors"]) {
   await setSection(l,t,t.players[2],section);
   const after=await daily(api,l,t,1,info);expect.soft(after.period_total_fpts,`${section} stats excluded`).toBe(before.period_total_fpts);
  }
 });
 test(`H2H-15 ${format} open stat replacement and matchup propagation`,async({api},info)=>{
  const l=await fixture(api,format);await generate(api,l);const t=l.teams[0];await setStats(l,t,{...zero,goals:2});
  await daily(api,l,t,1,info);await setStats(l,t,{...zero,goals:3});
  const a=await daily(api,l,t,1,info),b=await daily(api,l,t,1,info);expect.soft(b).toEqual(a);
  expect.soft(a.period_total_fpts,"3 goals at configured 3.5").toBe(10.5);
  const rows=await matches(api,l,1,info),m=rows.find((m:any)=>[m.home_team_id,m.away_team_id].includes(t.id));
  expect.soft(m.home_team_id===t.id?m.home_score:m.away_score).toBe(10.5);
  for(const row of await standings(api,l,info))expect(row.wins+row.losses+row.ties).toBe(0);
 });
 test(`H2H-16 ${format} open scoring leaves finalized records untouched`,async({api},info)=>{
  const l=await fixture(api,format);await generate(api,l);expect((await daily(api,l,l.teams[0],1,info)).period_total_fpts).toBeGreaterThan(0);
  for(const s of await standings(api,l,info))expect(s).toMatchObject({wins:0,losses:0,ties:0,points_for:0,points_against:0});
  for(const m of await matches(api,l,1,info))expect(m).toMatchObject({status:"scheduled",winner:null});
 });
 test(`H2H-17 ${format} commissioner finalization writes one result`,async({api},info)=>{
  const l=await fixture(api,format);await generate(api,l);await simulate(api,l,1,info);
  for(const m of await matches(api,l,1,info))expect(m.status).toBe("completed");
  for(const s of await standings(api,l,info))expect(s.wins+s.losses+s.ties).toBe(1);
 });
 test(`H2H-17 ${format} automatic period boundary`,async()=>{test.skip(true,"BLOCKED: existing E2E_MODE disables workers; no H2H close/clock-control endpoint found. Simulation does not verify real period-boundary finalization.");});
 test(`H2H-18 ${format} duplicate simulation is mutation-free`,async({api},info)=>{
  const l=await fixture(api,format);await generate(api,l);await simulate(api,l,1);const before=await standings(api,l,info),ms=await matches(api,l,1,info);
  for(let i=0;i<3;i++){const r=await api.post("/api/matchups/simulate-week",{data:{league_id:l.id,week:1}});await info.attach(`repeat-${i}`,{body:await r.text(),contentType:"text/plain"});expect(r.status()).toBe(400);}
  expect(await standings(api,l,info)).toEqual(before);expect(await matches(api,l,1,info)).toEqual(ms);
 });
 test(`H2H-18 ${format} closed-period recompute`,async()=>{test.skip(true,"NOT IMPLEMENTED: no H2H recompute route or worker found. Duplicate simulation rejection is covered separately; Rotisserie recompute cannot validate H2H.");});
 test(`H2H-19 ${format} two-week record accumulation`,async({api},info)=>{
  const l=await fixture(api,format);await generate(api,l);
  const expected=Object.fromEntries(l.teams.map(t=>[t.id,{wins:0,losses:0,ties:0}]));
  for(const w of [1,2]) {const rows=await matches(api,l,w);for(const m of rows){const a=l.teams.find(t=>t.id===m.home_team_id)!,b=l.teams.find(t=>t.id===m.away_team_id)!;
   const winner=format==="h2h-categories"?categoryOutcome(a,b).winner:a.points>b.points?a.id:b.points>a.points?b.id:null;
   for(const t of [a,b])expected[t.id][winner===null?"ties":winner===t.id?"wins":"losses"]++;
  }await simulate(api,l,w,info);}
  for(const s of await standings(api,l,info))expect.soft(s).toMatchObject(expected[s.team_id]);
 });
 test(`H2H-22 ${format} all current ranking keys`,async({api},info)=>{
  const l=await fixture(api,format);
  const values=[[3,0,0],[2,10,0],[2,5,10],[2,5,0],[2,5,0],[1,999,0],[0,0,0],[0,0,0]];
  await database(async db=>{for(const [i,t] of l.teams.entries())await db.collection("teams").updateOne({_id:new ObjectId(t.id)},{$set:{wins:values[i][0],points_for:values[i][1],live_points:values[i][2]}});});
  const s=await standings(api,l,info);expect([...s].sort((a:any,b:any)=>a.rank-b.rank).map((s:any)=>s.team_id)).toEqual([0,2,1,3,4,5,6,7].map(i=>l.teams[i].id));
 });
 test(`H2H-23 ${format} future weeks excluded from final records`,async({api},info)=>{
  const l=await fixture(api,format);await generate(api,l);await simulate(api,l,1);const before=await standings(api,l,info);
  await database(async db=>{for(const t of l.teams)await db.collection("players").updateOne({_id:new ObjectId(t.players[0])},{$set:{"period_stats.3":{goals:999},"live_stats.future":{goals:999,updated_at:"2026-10-22T12:00:00Z"}}});});
  expect(await standings(api,l,info)).toEqual(before);for(const m of await matches(api,l,3,info))expect(m).toMatchObject({status:"scheduled",winner:null,home_score:0,away_score:0});
 });
}
test("H2H-06 h2h-points skater goalie configured math",async({api},info)=>{
 const l=await fixture(api,"h2h-points");const t=l.teams[0];
 await database(async db=>{await db.collection("players").updateOne({_id:new ObjectId(t.players[2])},{$set:{position:"G",player_type:"goalie",wins:1,saves:10,goals_against:2}});await db.collection("teams").updateOne({_id:new ObjectId(t.id)},{$set:{[`lineup.${t.players[2]}`]:{section:"goalie",slot:"G"}}});});
 await setSection(l,t,t.players[2],"goalie");
 await database(async db=>{const p=await db.collection("players").findOne({_id:new ObjectId(t.players[2])});await db.collection("players").updateOne({_id:p!._id},{$set:{live_stats:Object.fromEntries(Object.entries(p!.live_stats).map(([gid,stats]:any)=>[gid,{...stats,wins:1,saves:10,goals_against:2}]))}});});
 const calculated=await result(await api.get(`/api/scoring/calculate/${l.id}`),info,"calculated");expect(calculated.find((s:any)=>s.team_id===t.id).total_fantasy_points).toBeCloseTo(t.points+5,1);
 const roster=await result(await api.get(`/api/roster/${t.id}`),info,"per-player-points");
 for(const [i,expected] of [t.points-5.7,5.7,5].entries())expect(roster.players.find((p:any)=>p.player_id===t.players[i]).fantasy_points).toBeCloseTo(expected,1);
 await generate(api,l);await simulate(api,l,1,info);const m=(await matches(api,l,1,info)).find((m:any)=>[m.home_team_id,m.away_team_id].includes(t.id));expect(m.home_team_id===t.id?m.home_score:m.away_score).toBeCloseTo(t.points+5,1);
});
test("H2H-04 h2h-points finalized score excludes season/outside-period totals",async({api},info)=>{
 const l=await fixture(api,"h2h-points");const t=l.teams[0];await setStats(l,t,{...zero,goals:2});
 await database(async db=>{await db.collection("players").updateOne({_id:new ObjectId(t.players[0])},{$set:{goals:999,"season_stats.goals":999}});});
 await generate(api,l);await simulate(api,l,1,info);const m=(await matches(api,l,1,info)).find((m:any)=>[m.home_team_id,m.away_team_id].includes(t.id));
 expect(m.home_team_id===t.id?m.home_score:m.away_score,"2 goals in week 1 at 3.5, not 999 season goals").toBe(7);
});
test("H2H-07 h2h-points positive negative fractional scoring",async({api},info)=>{
 const l=await fixture(api,"h2h-points");await setStats(l,l.teams[0],{goals:2,assists:3,shots:4,penalty_minutes:3});await setStats(l,l.teams[1],{...zero,penalty_minutes:3});
 const c=await result(await api.get(`/api/scoring/calculate/${l.id}`),info,"calculated");expect(c.find((s:any)=>s.team_id===l.teams[0].id).total_fantasy_points).toBe(12);expect(c.find((s:any)=>s.team_id===l.teams[1].id).total_fantasy_points).toBe(-0.6);
 await generate(api,l);await simulate(api,l,1,info);for(const m of await matches(api,l,1,info))for(const side of ["home","away"]) {const t=l.teams.find(t=>t.id===m[`${side}_team_id`])!;expect(m[`${side}_score`]).toBeCloseTo(t.points,1);}
});
for(const id of ["08","09"])test(`H2H-${id} h2h-points final winner and tie records`,async({api},info)=>{
 const l=await fixture(api,"h2h-points");if(id==="09")for(const t of l.teams)await setStats(l,t,{...zero,goals:2});await generate(api,l);await simulate(api,l,1,info);const s=await standings(api,l,info);
 for(const m of await matches(api,l,1,info)){const a=l.teams.find(t=>t.id===m.home_team_id)!,b=l.teams.find(t=>t.id===m.away_team_id)!;const winner=a.points>b.points?a.id:b.points>a.points?b.id:null;expect(m.winner).toBe(winner);
  for(const t of [a,b])expect(s.find((s:any)=>s.team_id===t.id)).toMatchObject({wins:winner===t.id?1:0,losses:winner&&winner!==t.id?1:0,ties:winner===null?1:0});
 }
});
for(const id of ["10","11","12","21"])test(`H2H-${id} h2h-categories category-level results unavailable`,async({api},info)=>{
 const l=await fixture(api,"h2h-categories");await generate(api,l);await simulate(api,l,1,info);await matches(api,l,1,info);await standings(api,l,info);
 test.skip(true,"NOT IMPLEMENTED: matchups/simulate-week evaluates scalar fantasy points for every format; no category-level result persistence/API or category standings fields exist. Probe responses attached; no assumed field contract.");
});
for(const id of ["13","14"])test(`H2H-${id} h2h-categories majority must determine result`,async({api},info)=>{
 const l=await fixture(api,"h2h-categories");await generate(api,l);const m=(await matches(api,l,1))[0],a=l.teams.find(t=>t.id===m.home_team_id)!,b=l.teams.find(t=>t.id===m.away_team_id)!;
 await setStats(l,a,{...zero,goals:2});await setStats(l,b,{...zero,goals:1,assists:2,shots:id==="13"?2:0});
 const expected=categoryOutcome(a,b);await info.attach("independent-category-oracle",{body:JSON.stringify(expected),contentType:"application/json"});await simulate(api,l,1,info);
 const after=(await matches(api,l,1,info)).find((r:any)=>r._id===m._id);expect.soft(after.winner).toBe(expected.winner);
 for(const s of await standings(api,l,info))if([a.id,b.id].includes(s.team_id))expect.soft(s).toMatchObject({wins:expected.winner===s.team_id?1:0,losses:expected.winner&&expected.winner!==s.team_id?1:0,ties:expected.winner===null?1:0});
});
test("H2H-20 h2h-points PF PA closed-week sums",async({api},info)=>{
 const l=await fixture(api,"h2h-points");await generate(api,l);const sums=Object.fromEntries(l.teams.map(t=>[t.id,{points_for:0,points_against:0}]));
 for(const w of [1,2]){for(const m of await matches(api,l,w)){const a=l.teams.find(t=>t.id===m.home_team_id)!,b=l.teams.find(t=>t.id===m.away_team_id)!;sums[a.id].points_for+=a.points;sums[a.id].points_against+=b.points;sums[b.id].points_for+=b.points;sums[b.id].points_against+=a.points;}await simulate(api,l,w,info);}
 for(const s of await standings(api,l,info)){expect(s.points_for).toBeCloseTo(sums[s.team_id].points_for,1);expect(s.points_against).toBeCloseTo(sums[s.team_id].points_against,1);}
});
