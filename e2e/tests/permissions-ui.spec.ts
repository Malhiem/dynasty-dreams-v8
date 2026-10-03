import {test,expect} from '@playwright/test';
import {actors,dispose,league,evidence,type Actors} from '../support/access-history';
import {result} from '../support/h2h';
import {PermissionPage} from '../pages/permission-ui/permission-ui.page';
import {LeagueScoringPage} from '../pages/league-scoring/league-scoring.page';
let a:Actors;
test.beforeAll(async()=>{a=await actors();});test.afterAll(async()=>{if(a)await dispose(a);});
test('P01 commissioner saves scoring rule through browser and reloads',async({page},info)=>{
 const l=await league(a);await page.context().addCookies((await a.commissioner.api.storageState()).cookies);
 const p=new PermissionPage(page);await p.goto(l.id);await expect(p.selectors.scoring(page)).toBeVisible();
 await p.saveGoals('7');
 await expect.poll(async()=> (await result(await a.commissioner.api.get(`/api/scoring/config?league_id=${l.id}`))).skater_scoring.goals).toBe(7);
 await page.reload();await expect(p.selectors.goals(page)).toHaveValue('7');await info.attach('saved-scoring',{body:await page.screenshot(),contentType:'image/png'});
});
test('P02 commissioner creates edits and clears bonus through browser',async({page},info)=>{
 const l=await league(a,'rotisserie');await result(await a.commissioner.api.put(`/api/leagues/${l.id}`,{data:{playoffs_enabled:true,playoff_format:'condensed_roto',playoff_roto_fresh_totals:true,playoff_start_week:5,playoff_end_week:7}}));
 await page.context().addCookies((await a.commissioner.api.storageState()).cookies);const p=new LeagueScoringPage(page);await p.structure(l.id);
 for(const value of ['10','20','0']){
   await expect(p.selectors.seedBonus(page,1)).toBeVisible();await p.selectors.seedBonus(page,1).fill(value);
   const saving=page.waitForResponse(r=>r.request().method()==='PUT'&&new URL(r.url()).pathname===`/api/leagues/${l.id}`);
   await p.selectors.playoffSave(page).click();expect((await saving).ok()).toBe(true);
   const saved=await result(await a.commissioner.api.get(`/api/leagues/${l.id}`),info,`bonus-${value}`);expect(saved.playoff_roto_seed_bonuses['1']||0).toBe(Number(value));
   await page.reload();await expect(p.selectors.seedBonus(page,1)).toHaveValue(value);
 }
});
test('P03 commissioner finalizes season through browser',async({page},info)=>{
 const l=await league(a);await page.context().addCookies((await a.commissioner.api.storageState()).cookies);const p=new PermissionPage(page);await p.goto(l.id);
 await expect(p.selectors.complete(page)).toBeVisible();const completed=page.waitForResponse(r=>r.request().method()==='POST'&&new URL(r.url()).pathname===`/api/leagues/${l.id}/complete-season`);
 await p.selectors.complete(page).click();const r=await completed;await evidence(info,'ui-completion',{status:r.status(),body:await r.text()});expect(r.ok()).toBe(true);await page.reload();await expect(p.selectors.complete(page)).toBeHidden();
 const history=await result(await a.commissioner.api.get(`/api/leagues/${l.id}/seasons`),info,'season-history');expect(history.seasons).toHaveLength(1);
});
for(const role of ['manager','manager2'] as const)test(`P05 ${role} bonus and season completion controls are restricted`,async({page},info)=>{
 const l=await league(a,'rotisserie');await result(await a.commissioner.api.put(`/api/leagues/${l.id}`,{data:{playoffs_enabled:true,playoff_format:'condensed_roto',playoff_roto_fresh_totals:true}}));
 await page.context().addCookies((await a[role].api.storageState()).cookies);const p=new LeagueScoringPage(page),admin=new PermissionPage(page);await p.structure(l.id);
 await expect(admin.selectors.denied(page)).toBeVisible();
 await expect(p.selectors.seedBonus(page,1)).toBeHidden();
 await expect(p.selectors.playoffSave(page)).toBeHidden();
 await expect(admin.selectors.complete(page)).toBeHidden();
 await info.attach('controls',{body:await page.screenshot(),contentType:'image/png'});
});
for(const role of ['manager','manager2','outsider'] as const)test(`P05 ${role} direct administration URL cannot enable scoring edits`,async({page},info)=>{
 const l=await league(a);await page.context().addCookies((await a[role].api.storageState()).cookies);
 const p=new PermissionPage(page);await p.goto(l.id);await expect(p.selectors.heading(page)).toBeVisible();
 await expect(p.selectors.denied(page)).toBeVisible();
 await expect(p.selectors.scoring(page)).toBeHidden();
 await expect(p.selectors.save(page)).toBeHidden();
 await expect(p.selectors.goals(page)).toBeHidden();
 await info.attach('administration-screen',{body:await page.screenshot(),contentType:'image/png'});
});

test('P06 scoring round trip preserves zero negative goalie and unexposed categories',async({page})=>{
 const l=await league(a);
 const skater={goals:1,shots:0.25,short_handed_goals:2,penalty_minutes:-0.5,games_played:1,custom_stat:4};
 const goalie={wins:5,losses:-2,saves:0.2,games_played:3,custom_goalie:7};
 await result(await a.commissioner.api.post('/api/scoring/config',{data:{league_id:l.id,skater_scoring:skater,goalie_scoring:goalie,roto_categories:['goals','saves']}}));
 await page.context().addCookies((await a.commissioner.api.storageState()).cookies);
 const p=new PermissionPage(page);await p.goto(l.id);
 await expect(p.selectors.points(page,'shots_on_goal')).toHaveValue('0.25');
 await expect(p.selectors.points(page,'shorthanded_goals')).toHaveValue('2');
 await expect(p.selectors.points(page,'games_played')).toHaveValue('1');
 await expect(p.selectors.points(page,'goalie_games_played')).toHaveValue('3');
 await p.selectors.points(page,'penalty_minutes').fill('-1.5');
 await p.selectors.points(page,'wins').fill('0');
 await p.selectors.category(page,'shorthanded_goals').uncheck();
 await p.saveGoals('7');
 const expectedSkater={goals:7,shots:0.25,penalty_minutes:-1.5,games_played:1,custom_stat:4};
 await expect.poll(async()=> (await result(await a.commissioner.api.get(`/api/scoring/config?league_id=${l.id}`))).skater_scoring).toEqual(expectedSkater);
 const saved=await result(await a.commissioner.api.get(`/api/scoring/config?league_id=${l.id}`));
 expect(saved.goalie_scoring).toEqual({...goalie,wins:0});expect(saved.roto_categories).toEqual(['goals','saves']);
 await page.reload();
 await expect(p.selectors.points(page,'wins')).toHaveValue('0');
 await expect(p.selectors.category(page,'wins')).toBeChecked();
 await expect(p.selectors.category(page,'shorthanded_goals')).not.toBeChecked();
 await expect(p.selectors.points(page,'penalty_minutes')).toHaveValue('-1.5');
});

test('P07 failed scoring save keeps changes available for retry',async({page})=>{
 const l=await league(a);await page.context().addCookies((await a.commissioner.api.storageState()).cookies);
 const p=new PermissionPage(page);await p.goto(l.id);await expect(p.selectors.goals(page)).toHaveValue('1');
 await page.route('**/api/scoring/config',async route=>{
   if(route.request().method()==='POST')await route.fulfill({status:500,json:{detail:'Scoring save unavailable'}});
   else await route.continue();
 });
 await p.saveGoals('9');await expect(p.selectors.error(page,'Scoring save unavailable')).toBeVisible();
 await expect(p.selectors.goals(page)).toHaveValue('9');await expect(p.selectors.save(page)).toBeEnabled();
 expect((await result(await a.commissioner.api.get(`/api/scoring/config?league_id=${l.id}`))).skater_scoring.goals).toBe(1);
 await page.unroute('**/api/scoring/config');await p.selectors.save(page).click();
 await expect.poll(async()=> (await result(await a.commissioner.api.get(`/api/scoring/config?league_id=${l.id}`))).skater_scoring.goals).toBe(9);
});

test('P08 failed scoring load cannot overwrite persisted rules with defaults',async({page})=>{
 const l=await league(a);await page.context().addCookies((await a.commissioner.api.storageState()).cookies);
 await page.route('**/api/scoring/config?*',route=>route.fulfill({status:503,json:{detail:'Scoring load unavailable'}}));
 const p=new PermissionPage(page);await p.goto(l.id);
 await expect(p.selectors.error(page,'Scoring load unavailable')).toBeVisible();
 await expect(p.selectors.save(page)).toBeHidden();
 await page.unroute('**/api/scoring/config?*');await p.selectors.retry(page).click();
 await expect(p.selectors.goals(page)).toHaveValue('1');
});
