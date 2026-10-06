import { expect } from '@playwright/test';
import { test } from '../support/h2h-cases';
import { database } from '../support/h2h';
import { historyFixture } from '../support/history-trophy-fixture';
import { HistoryTrophyPage } from '../pages/history-trophy/history-trophy.page';
test.setTimeout(45000);

for(const format of ['h2h-points','h2h-categories','rotisserie'] as const) {
  for(const view of ['history','league','franchise'] as const) {
    test(`SWEEP mobile ${format} ${view} remains usable at 390px`,async({page,api},info)=>{
      await page.setViewportSize({width:390,height:844});
      const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
      const l=await historyFixture(api,format),p=new HistoryTrophyPage(page);
      await p.open(l.id,view==='history'?'/league-history':view==='league'?'/trophy-room':`/trophy-room/team/${l.teams[0].id}`);
      if(view==='history') {
        await expect(p.ui.historyRow(l.teams[0].id)).toBeVisible();
        for(const name of ['League Records','Player Awards','Transactions','Trophy Room','Lifetime Records']) {
          await p.ui.tab(name).click();await expect(p.ui.tab(name)).toHaveAttribute('aria-selected','true');
        }
      } else {
        await expect(p.ui.banner('championship',2026)).toBeVisible();
        await p.ui.recent().click();await expect(p.ui.banner('championship',2019)).toHaveCount(0);
        await p.ui.all().click();await p.year(2020);await expect(p.ui.trophy('season-mvp',2020)).toBeVisible();
        if(view==='franchise') await expect(p.ui.franchiseRecord(2020)).toBeVisible();
        await p.year('all');await expect(p.ui.banner('championship',2019)).toBeVisible();
      }
      await info.attach('mobile-page',{body:await page.screenshot({fullPage:true}),contentType:'image/png'});
      const dimensions=await page.evaluate(()=>({viewport:document.documentElement.clientWidth,content:document.documentElement.scrollWidth}));
      expect.soft(dimensions.content,'page must not require horizontal scrolling').toBeLessThanOrEqual(dimensions.viewport+1);
      expect(errors,'uncaught browser errors').toEqual([]);
    });
  }
  test(`SWEEP keyboard ${format} history tabs and trophy filters`,async({page,api})=>{
    const l=await historyFixture(api,format),p=new HistoryTrophyPage(page);
    await p.open(l.id,'/league-history');await expect(p.ui.historyRow(l.teams[0].id)).toBeVisible();
    await p.ui.tab('Lifetime Records').focus();await page.keyboard.press('ArrowRight');
    await expect(p.ui.tab('League Records')).toBeFocused();await expect(p.ui.tab('League Records')).toHaveAttribute('aria-selected','true');
    await page.goto('/trophy-room',{waitUntil:'domcontentloaded'});await expect(p.ui.banner('championship',2026)).toBeVisible();
    await p.ui.recent().focus();await page.keyboard.press('Enter');await expect(p.ui.banner('championship',2019)).toHaveCount(0);
    await p.ui.all().focus();await page.keyboard.press('Space');await expect(p.ui.banner('championship',2019)).toBeVisible();
    await expect(p.ui.years()).toHaveAccessibleName('Filter by season year');
    await p.ui.teamCard(l.teams[0].id).focus();await page.keyboard.press('Enter');await expect(p.ui.teamRafters()).toBeVisible();
    await p.ui.exit().focus();await page.keyboard.press('Enter');await expect(p.ui.leagueRafters()).toBeVisible();
  });
  test(`SWEEP direct franchise link ${format} uses its own league seasons`,async({page,api})=>{
    const target=await historyFixture(api,format),other=await historyFixture(api,format),p=new HistoryTrophyPage(page);
    await database(async db=>{
      for(const year of [2026,2024,2020,2019]) await db.collection('league_seasons').updateOne({league_id:target.id,season_year:year},{$set:{season_year:year-8}});
    });
    await p.open(other.id,`/trophy-room/team/${target.teams[0].id}`);
    await expect(p.ui.room()).toContainText(`${target.teams[0].name} — Trophy Room`);
    await expect(p.ui.banner('championship',2018)).toBeVisible();
    await expect(p.ui.years().getByRole('option',{name:'2018',exact:true})).toHaveCount(1);
    await expect.poll(()=>page.evaluate(()=>localStorage.getItem('dd_active_league_id'))).toBe(target.id);
    await expect(p.ui.years()).toHaveValue('all');
    for(const year of [2018,2016,2012,2011]) await expect(p.ui.franchiseRecord(year)).toBeVisible();
    for(const year of [2026,2024,2020,2019]) await expect(p.ui.years().getByRole('option',{name:String(year),exact:true})).toHaveCount(0);
    await p.ui.recent().click();
    for(const year of [2018,2016,2012]) {await expect(p.ui.banner('championship',year)).toBeVisible();await expect(p.ui.franchiseRecord(year)).toBeVisible();}
    await expect(p.ui.banner('championship',2011)).toHaveCount(0);await expect(p.ui.franchiseRecord(2011)).toHaveCount(0);
    await p.year(2011);await expect(p.ui.teamRafters()).toContainText('No awards match these filters');
    await p.ui.teamRafters().getByRole('button',{name:'Reset filters',exact:true}).click();
    await expect(p.ui.franchiseRecord(2011)).toBeVisible();await expect(p.ui.trophy('season-mvp',2011)).toBeVisible();
    await p.year(2018);await expect(p.ui.franchiseRecord(2018)).toBeVisible();
    await expect(p.ui.franchiseRecord(2016)).toHaveCount(0);await expect(p.ui.trophy('season-mvp',2018)).toBeVisible();
    await page.reload({waitUntil:'domcontentloaded'});await expect(p.ui.banner('championship',2018)).toBeVisible();
    await p.ui.exit().click();await expect(p.ui.leagueRafters()).toBeVisible();await expect(p.ui.teamCard(target.teams[0].id)).toBeVisible();
    await expect(p.ui.teamCard(other.teams[0].id)).toHaveCount(0);await expect(p.ui.banner('championship',2018)).toBeVisible();
  });
}

for(const format of ['h2h-points','h2h-categories','rotisserie'] as const) {
  test(`SWEEP direct franchise ${format} works without saved league selection`,async({page,api})=>{
    const target=await historyFixture(api,format),p=new HistoryTrophyPage(page);
    await page.addInitScript(()=>localStorage.removeItem('dd_active_league_id'));
    await page.goto(`/trophy-room/team/${target.teams[0].id}`,{waitUntil:'domcontentloaded'});
    await expect(p.ui.banner('championship',2026)).toBeVisible();await expect(p.ui.franchiseRecord(2026)).toBeVisible();
    await expect.poll(()=>page.evaluate(()=>localStorage.getItem('dd_active_league_id'))).toBe(target.id);
    await p.ui.exit().click();await expect(p.ui.teamCard(target.teams[0].id)).toBeVisible();
  });
  test(`SWEEP direct franchise ${format} ignores failed unrelated league history`,async({page,api})=>{
    const target=await historyFixture(api,format),other=await historyFixture(api,format),p=new HistoryTrophyPage(page);
    let unrelatedRequests=0;
    await page.route(`**/api/leagues/${other.id}/trophy-room`,route=>{unrelatedRequests++;return route.fulfill({status:500,json:{detail:'Unrelated league unavailable'}});});
    await p.open(other.id,`/trophy-room/team/${target.teams[0].id}`);
    await expect(p.ui.banner('championship',2026)).toBeVisible();await expect(p.ui.franchiseRecord(2026)).toBeVisible();
    await expect(p.ui.alert()).toHaveCount(0);expect(unrelatedRequests).toBe(0);
  });
}
