import {test,expect} from '@playwright/test';
import {actors,dispose,type Actors} from '../support/access-history';
import {salaryLeague,settings,execute} from '../support/salary';
import {result} from '../support/h2h';
import {SalaryPage} from '../pages/salary/salary.page';
let a:Actors;test.beforeAll(async()=>{a=await actors();});test.afterAll(async()=>{if(a)await dispose(a);});
test('P01 C01 browser saves salary cap and future values',async({page})=>{
 const l=await salaryLeague(a);await page.context().addCookies((await a.commissioner.api.storageState()).cookies);const p=new SalaryPage(page);await p.goto(l.id);
 await expect(p.selectors.amount(page)).toHaveValue('100,000,000');await p.selectors.amount(page).fill('99000000');await p.selectors.next(page).fill('104000000');
 const save=page.waitForResponse(r=>r.request().method()==='PUT'&&r.url().endsWith('/admin/cap-settings'));await p.selectors.saveCap(page).click();expect((await save).ok()).toBe(true);
 await page.reload();await p.selectors.tab(page).click();await expect(p.selectors.amount(page)).toHaveValue('99,000,000');await expect(p.selectors.next(page)).toHaveValue('104,000,000');
});
test('P01 C06 browser saves retention slots and maximum',async({page})=>{
 const l=await salaryLeague(a);await page.context().addCookies((await a.commissioner.api.storageState()).cookies);const p=new SalaryPage(page);await p.goto(l.id);
 await p.selectors.slots(page).fill('2');await p.selectors.maxPct(page).fill('40');const saving=page.waitForResponse(r=>r.request().method()==='PUT'&&new URL(r.url()).pathname===`/api/leagues/${l.id}`);await p.selectors.saveRetention(page).click();expect((await saving).ok()).toBe(true);
 await page.reload();await p.selectors.tab(page).click();await expect(p.selectors.slots(page)).toHaveValue('2');await expect(p.selectors.maxPct(page)).toHaveValue('40');
});
for(const role of ['manager','outsider'] as const)test(`P02 ${role} salary administration controls hidden`,async({page})=>{
 const l=await salaryLeague(a);await page.context().addCookies((await a[role].api.storageState()).cookies);const p=new SalaryPage(page);
 await page.addInitScript(id=>localStorage.setItem('dd_active_league_id',id),l.id);await page.goto('/commissioner/settings');await expect(p.selectors.denied(page)).toBeVisible();await expect(p.selectors.cap(page)).toBeHidden();await expect(p.selectors.retention(page)).toBeHidden();
});
test('A07 browser preserves permitted zero rookie charge after reload',async({page})=>{
 const l=await salaryLeague(a);await page.context().addCookies((await a.commissioner.api.storageState()).cookies);const p=new SalaryPage(page);await p.goto(l.id);await p.selectors.rookie(page).fill('0');
 const saving=page.waitForResponse(r=>r.request().method()==='PUT'&&r.url().endsWith('/admin/cap-settings'));await p.selectors.saveCap(page).click();expect((await saving).ok()).toBe(true);
 await page.reload();await p.selectors.tab(page).click();await expect(p.selectors.rookie(page)).toHaveValue('0');
});
test('U02 failed salary save displays error and supports retry',async({page})=>{
 const l=await salaryLeague(a);await page.context().addCookies((await a.commissioner.api.storageState()).cookies);const p=new SalaryPage(page);await p.goto(l.id);await p.selectors.amount(page).fill('99000000');
 await page.route('**/admin/cap-settings',route=>route.fulfill({status:503,json:{detail:'Salary save unavailable'}}));await p.selectors.saveCap(page).click();await expect(p.selectors.error(page)).toBeVisible();await expect(p.selectors.amount(page)).toHaveValue('99,000,000');
 expect((await result(await a.commissioner.api.get(`/api/leagues/${l.id}`))).salary_cap).toBe(100000000);
 await page.unroute('**/admin/cap-settings');await p.selectors.saveCap(page).click();await expect.poll(async()=>(await result(await a.commissioner.api.get(`/api/leagues/${l.id}`))).salary_cap).toBe(99000000);
});
test('U04 narrow viewport keeps financial settings usable',async({page})=>{
 const l=await salaryLeague(a);await page.context().addCookies((await a.commissioner.api.storageState()).cookies);const p=new SalaryPage(page);await p.goto(l.id);await page.setViewportSize({width:390,height:844});
 for(const control of [p.selectors.amount(page),p.selectors.slots(page),p.selectors.maxPct(page),p.selectors.saveCap(page),p.selectors.saveRetention(page)]){
  await control.scrollIntoViewIfNeeded();await expect(control).toBeVisible();const rect=await control.boundingBox();expect(rect!.x).toBeGreaterThanOrEqual(0);expect(rect!.x+rect!.width).toBeLessThanOrEqual(390);
 }
});

test('U01 real trade builder uses configured 40 percent maximum',async({page})=>{
 const l=await salaryLeague(a);await settings(l,{salary_retention_max_pct:40,salary_retention_slots:2});await page.context().addCookies((await a.manager.api.storageState()).cookies);
 const p=new SalaryPage(page);await page.addInitScript(id=>localStorage.setItem('dd_active_league_id',id),l.id);await page.goto('/team');await p.selectors.trade(page,l.teams[0].players[0]).click();
 await p.selectors.retain(page,l.teams[0].players[0]).check();await expect(p.selectors.percentage(page,l.teams[0].players[0])).toHaveAttribute('aria-valuemax','40');
});
test('U01 disabled retention cannot be enabled in real trade builder',async({page})=>{
 const l=await salaryLeague(a);await settings(l,{salary_retention_enabled:false,salary_retention_slots:0});await page.context().addCookies((await a.manager.api.storageState()).cookies);
 const p=new SalaryPage(page);await page.addInitScript(id=>localStorage.setItem('dd_active_league_id',id),l.id);await page.goto('/team');await p.selectors.trade(page,l.teams[0].players[0]).click();await expect(p.selectors.asset(page,l.teams[0].players[0])).toBeVisible();
 const control=p.selectors.retain(page,l.teams[0].players[0]);if(await control.count())await expect(control).toBeDisabled();else await expect(control).toBeHidden();
});
test('U03 salary cap screen displays retained obligation after real trade',async({page},info)=>{
 const l=await salaryLeague(a);await execute(a,l,40,info);await page.context().addCookies((await a.manager.api.storageState()).cookies);const p=new SalaryPage(page);
 await page.addInitScript(id=>localStorage.setItem('dd_active_league_id',id),l.id);await page.goto('/salary-cap');await expect(p.selectors.capHit(page)).toContainText('$74.0M');await expect(p.selectors.dead(page)).toContainText('$4.0M');
});

test('L04 browser releases current retention while preserving history after renewal',async({page},info)=>{
 const l=await salaryLeague(a);const year=new Date().getUTCFullYear();
 await settings(l,{current_season_year:year,current_season_status:'in_progress',season_end_date:`${year}-12-31`});
 await execute(a,l,40,info);await page.context().addCookies((await a.manager.api.storageState()).cookies);
 await page.addInitScript(id=>localStorage.setItem('dd_active_league_id',id),l.id);const p=new SalaryPage(page);
 await page.goto('/salary-cap');await expect(p.selectors.capHit(page)).toContainText('$74.0M');
 await result(await a.commissioner.api.post(`/api/leagues/${l.id}/complete-season`,{data:{season_year:year}}),info);
 await result(await a.commissioner.api.post(`/api/leagues/${l.id}/renew-season`,{data:{new_season_year:year+1}}),info);
 await page.reload();await expect(p.selectors.capHit(page)).toContainText('$70.0M');await expect(p.selectors.dead(page)).toContainText('$0.0M');
 const schedule=await result(await a.manager.api.get(`/api/teams/${l.teams[0].id}/dead-cap-schedule`),info);
 expect(schedule.schedule).toHaveLength(1);expect(schedule.schedule[0].year).toBe(year);expect(schedule.schedule[0].total).toBe(4000000);
});

for(const policy of ['receiver_pays','league_waives'])test(`F03 administration saves and reloads forgiveness ${policy}`,async({page})=>{
 const l=await salaryLeague(a);await page.context().addCookies((await a.commissioner.api.storageState()).cookies);
 const p=new SalaryPage(page);await p.goto(l.id);
 await page.getByTestId('rules-schedule-retention-forgiveness').selectOption(policy);
 const saved=page.waitForResponse(r=>r.request().method()==='PUT'&&r.url().endsWith(`/leagues/${l.id}`));
 await p.selectors.saveRetention(page).click();expect((await saved).ok()).toBe(true);
 await page.reload();await p.selectors.tab(page).click();
 await expect(page.getByTestId('rules-schedule-retention-forgiveness')).toHaveValue(policy);
 expect((await result(await a.commissioner.api.get(`/api/leagues/${l.id}`))).retention_forgiveness_policy).toBe(policy);
});
