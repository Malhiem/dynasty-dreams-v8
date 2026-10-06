import { expect } from "@playwright/test";
import { test } from "../support/h2h-cases";
import { fixture, generate, matches, simulate, standings, result, setStats, categoryOutcome, zero, weights, type Format, type League } from "../support/h2h";
import type { APIRequestContext, TestInfo } from "@playwright/test";
const formats:Format[]=["h2h-points","h2h-categories"];
async function bracketRun(api:APIRequestContext,l:League,info:TestInfo) {
 let previous:string[]=[];
 for(const [week,count] of [[5,4],[6,2],[7,1]]) {
  const rows=(await matches(api,l,week,info)).filter((m:any)=>m.is_playoff);expect(rows).toHaveLength(count);
  if(previous.length)expect(rows.flatMap((m:any)=>[m.home_team_id,m.away_team_id]).sort()).toEqual([...previous].sort());
  const expected=rows.map((m:any)=>{const a=l.teams.find(t=>t.id===m.home_team_id)!,b=l.teams.find(t=>t.id===m.away_team_id)!;
   return l.format==="h2h-categories"?categoryOutcome(a,b).winner:a.points>b.points?a.id:b.id;});
  await simulate(api,l,week,info);const after=await matches(api,l,week,info);
  for(const [i,m] of after.entries())expect.soft(m.winner,`week ${week} independent format-specific winner`).toBe(expected[i]);
  previous=after.map((m:any)=>m.winner);expect(new Set(previous).size).toBe(count);expect(previous).not.toContain(null);
  const r=await api.post("/api/matchups/simulate-week",{data:{league_id:l.id,week}});expect(r.status()).toBe(400);
  expect(await matches(api,l,week)).toEqual(after);
 }
 return previous[0];
}
for(const format of formats) {
 test(`H2H-24 ${format} disabled playoffs suppress saved tree`,async({api},info)=>{
  const l=await fixture(api,format,true);await result(await api.put(`/api/leagues/${l.id}`,{data:{playoffs_enabled:false}}));await generate(api,l,info);
  const rows=await matches(api,l,undefined,info);expect.soft(rows.filter((m:any)=>!m.is_playoff)).toHaveLength(16);expect.soft(rows.filter((m:any)=>m.is_playoff)).toHaveLength(0);
  const b=await result(await api.get(`/api/leagues/${l.id}/playoff-bracket`),info,"disabled-bracket");expect(b.rounds).toHaveLength(0);
 });
 test(`H2H-24 ${format} no-playoff completion current behavior`,async({api},info)=>{
  const l=await fixture(api,format);await generate(api,l);for(const w of [1,2,3,4])await simulate(api,l,w);
  const c=await result(await api.post(`/api/leagues/${l.id}/complete-season`,{data:{season_year:2026}}),info,"no-playoff-completion");expect(c.champion).toBeNull();
  const snapshot=await result(await api.get(`/api/leagues/${l.id}/seasons/2026`),info,"no-playoff-snapshot");
  expect(snapshot.champion_team_name).toBeNull();expect(snapshot.teams).toHaveLength(8);
  info.annotations.push({type:"ambiguity",description:"Current H2H behavior is completion with no champion unless an award already exists. No documented intended no-playoff champion rule found; this observation is not policy approval."});
 });
 test(`H2H-25 ${format} qualification follows final regular standings`,async({api},info)=>{
  const l=await fixture(api,format,true,10);await generate(api,l);
  // Reverse the initial 0-0/ID ranking through actual scores, forcing the qualification boundary to move.
  for(const [i,t] of l.teams.entries())await setStats(l,t,{...zero,goals:i+1,assists:i+1,shots:i+1});
  for(const w of [1,2,3,4])await simulate(api,l,w,info);
  const ranked=(await standings(api,l,info)).sort((a:any,b:any)=>a.rank-b.rank);const qf=(await matches(api,l,5,info)).filter((m:any)=>m.is_playoff);
  expect.soft(qf.flatMap((m:any)=>[m.home_team_id,m.away_team_id]).sort()).toEqual(ranked.slice(0,8).map((s:any)=>s.team_id).sort());
  for(const [i,m] of qf.entries())expect.soft([m.home_team_id,m.away_team_id]).toEqual([ranked[i].team_id,ranked[7-i].team_id]);
  const b=await result(await api.get(`/api/leagues/${l.id}/playoff-bracket`),info,"qualified-bracket");
  for(const m of b.rounds[0].matchups)for(const slot of [m.high_seed,m.low_seed])if(slot)expect.soft(slot.seed).toBe(ranked.findIndex((s:any)=>s.team_id===slot.team_id)+1);
 });
 test(`H2H-26 ${format} persisted 4-2-1 bracket`,async({api},info)=>{
  const l=await fixture(api,format,true);await generate(api,l,info);const all=await matches(api,l,undefined,info);
  for(const [week,count] of [[5,4],[6,2],[7,1]]){const rows=all.filter((m:any)=>m.is_playoff&&m.week===week);expect(rows).toHaveLength(count);
   if(week===5)for(const [i,m] of rows.entries())expect([m.home_team_id,m.away_team_id]).toEqual([l.teams[i].id,l.teams[7-i].id]);
   else for(const m of rows)expect(m).toMatchObject({home_team_id:null,away_team_id:null,home_team_tbd:true,away_team_tbd:true});
  }
 });
 test(`H2H-29 ${format} scored elimination progression`,async({api},info)=>{
  const l=await fixture(api,format,true);await generate(api,l);await bracketRun(api,l,info);
 });
 test(`H2H-30 ${format} championship history trophy consistency`,async({api},info)=>{
  const l=await fixture(api,format,true);await generate(api,l);const winner=await bracketRun(api,l,info);
  const team=await result(await api.get(`/api/teams/${winner}`),info,"awarded-team");expect(team.championship_won_at).toBeTruthy();
  const c=await result(await api.post(`/api/leagues/${l.id}/complete-season`,{data:{season_year:2026}}),info,"complete-season");const name=l.teams.find(t=>t.id===winner)!.name;expect(c.champion).toBe(name);
  const h=await result(await api.get(`/api/leagues/${l.id}/seasons/2026`),info,"history");expect(h.champion_team_name).toBe(name);
  const trophy=await result(await api.get(`/api/leagues/${l.id}/trophy-room`),info,"trophy-room");expect(JSON.stringify(trophy)).toContain(name);expect(JSON.stringify(trophy)).toContain("championship");
 });
 test(`H2H-31 ${format} renewal preserves historical records`,async({api},info)=>{
  const l=await fixture(api,format,true);await generate(api,l);for(const w of [1,2,3,4,5,6,7])await simulate(api,l,w);
  await result(await api.post(`/api/leagues/${l.id}/complete-season`,{data:{season_year:2026}}));const before=await result(await api.get(`/api/leagues/${l.id}/seasons/2026`),info,"snapshot-before");
  expect(before.champion_team_name).toBeTruthy();expect(before.teams.some((t:any)=>t.wins>0)).toBeTruthy();
  await result(await api.post(`/api/leagues/${l.id}/renew-season`,{data:{new_season_year:2027,reset_records:true,carry_over_settings:true}}),info,"renewed");
  await setStats(l,l.teams[0],{...zero,goals:999});const after=await result(await api.get(`/api/leagues/${l.id}/seasons/2026`),info,"snapshot-after");expect(after).toEqual(before);
  for(const s of await standings(api,l,info))expect(s).toMatchObject({wins:0,losses:0,ties:0,points_for:0,points_against:0});expect(await matches(api,l)).toHaveLength(0);
 });
}
test("H2H-27 h2h-points playoff math and advancement",async({api},info)=>{
 const l=await fixture(api,"h2h-points",true);await generate(api,l);await simulate(api,l,5,info);const qf=await matches(api,l,5,info);
 for(const m of qf){const a=l.teams.find(t=>t.id===m.home_team_id)!,b=l.teams.find(t=>t.id===m.away_team_id)!;expect(m.home_score).toBeCloseTo(a.points,1);expect(m.away_score).toBeCloseTo(b.points,1);expect(m.winner).toBe(a.points>b.points?a.id:b.id);}
 expect((await matches(api,l,6,info)).flatMap((m:any)=>[m.home_team_id,m.away_team_id]).sort()).toEqual(qf.map((m:any)=>m.winner).sort());
});
test("H2H-28 h2h-categories playoff winner uses categories",async({api},info)=>{
 const l=await fixture(api,"h2h-categories",true);await generate(api,l);const m=(await matches(api,l,5))[0],a=l.teams.find(t=>t.id===m.home_team_id)!,b=l.teams.find(t=>t.id===m.away_team_id)!;
 await setStats(l,a,{...zero,goals:2});await setStats(l,b,{...zero,goals:1,assists:2,shots:2});await simulate(api,l,5,info);
 expect.soft((await matches(api,l,5,info)).find((r:any)=>r._id===m._id).winner).toBe(b.id);
 const next=(await matches(api,l,6,info)).flatMap((m:any)=>[m.home_team_id,m.away_team_id]);expect.soft(next).toContain(b.id);expect(next).not.toContain(a.id);
});
test("H2H-32 cross-format evaluation and config isolation",async({api},info)=>{
 const leagues=[];for(const f of formats){const l=await fixture(api,f);await generate(api,l);const m=(await matches(api,l,1))[0],a=l.teams.find(t=>t.id===m.home_team_id)!,b=l.teams.find(t=>t.id===m.away_team_id)!;
  await setStats(l,a,{...zero,goals:2});await setStats(l,b,{...zero,goals:1,assists:2,shots:2});await simulate(api,l,1,info);const r=(await matches(api,l,1,info)).find((r:any)=>r._id===m._id);
  expect.soft(r.winner,`${f} independent expected winner`).toBe(f==="h2h-points"?a.id:b.id);leagues.push(l);
 }
 const saved=await matches(api,leagues[1],1);await result(await api.post("/api/scoring/config",{data:{league_id:leagues[0].id,skater_scoring:{goals:999},goalie_scoring:{},roto_categories:[]}}));
 const c=await result(await api.get(`/api/scoring/config?league_id=${leagues[1].id}`),info,"isolated-category-config");expect(c.skater_scoring).toEqual(weights);expect(await matches(api,leagues[1],1)).toEqual(saved);
});
test("H2H-33 h2h-categories tied playoff current behavior",async({api},info)=>{
 const l=await fixture(api,"h2h-categories",true);for(const t of l.teams)await setStats(l,t,{...zero,goals:2});await generate(api,l);await simulate(api,l,5,info);
 for(const m of await matches(api,l,5,info))expect(m).toMatchObject({winner:null,status:"completed"});for(const m of await matches(api,l,6,info))expect(m).toMatchObject({home_team_id:null,away_team_id:null});
 test.skip(true,"BLOCKED product ambiguity: tied completed playoff leaves next round TBD; no documented category-tie advancement policy. Observed behavior attached; do not invent higher-seed or random advancement.");
});
