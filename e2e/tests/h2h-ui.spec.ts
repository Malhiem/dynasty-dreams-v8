import { expect } from "@playwright/test";
import { test } from "../support/h2h-cases";
import { fixture,generate,matches,result,weights,categories,type Format } from "../support/h2h";
import { LeagueScoringPage } from "../pages/league-scoring/league-scoring.page";
import { H2HMatchupPage } from "../pages/h2h-matchup/h2h-matchup.page";
for(const [format,label] of [["h2h-points","Head-to-Head Points"],["h2h-categories","Head-to-Head Most Categories"]] as const){
 test(`H2H-01 ${format} setup persistence`,async({page,api},info)=>{
  const l=await fixture(api,format);await result(await api.put(`/api/leagues/${l.id}`,{data:{scoring_format:"rotisserie"}}));const p=new LeagueScoringPage(page);await p.goto(l.id);await p.select(label);
  await expect.configure({soft:true}).poll(async()=> (await result(await api.get(`/api/leagues/${l.id}`))).scoring_format).toBe(format);
  await page.reload();await expect.soft(p.selectors.h2hRequired(page)).toBeHidden();
  expect.soft((await result(await api.get(`/api/leagues/${l.id}`),info,"reloaded-config")).scoring_format).toBe(format);
  const c=await result(await api.get(`/api/scoring/config?league_id=${l.id}`),info,"scoring-settings");expect(c.skater_scoring).toEqual(weights);expect(c.roto_categories).toEqual(categories);
 });
 test(`H2H-03 ${format} browser week navigation`,async({page,api},info)=>{
  const l=await fixture(api,format as Format);await generate(api,l);const p=new H2HMatchupPage(page);await p.goto(l.id);await expect(p.selectors.week(page)).toBeVisible();
  for(const w of [1,2,1]){
   await p.selectWeek(w);await expect(p.selectors.week(page)).toContainText(`Week ${w}`);
   await expect(page.getByText(w===1?"2026-10-07 – 2026-10-13":"2026-10-14 – 2026-10-20",{exact:true})).toBeVisible();
   const rows=await matches(api,l,w,info),m=rows.find((m:any)=>[m.home_team_id,m.away_team_id].includes(l.teams[0].id));const opponent=m.home_team_id===l.teams[0].id?m.away_team_name:m.home_team_name;
   // The matchup heading must change with the week, not only its daily date strip.
   await expect.soft(page.getByRole("heading",{name:opponent,exact:true})).toBeVisible();
   await info.attach(`week-${w}-screen`,{body:await page.screenshot(),contentType:"image/png"});
  }
 });
}
