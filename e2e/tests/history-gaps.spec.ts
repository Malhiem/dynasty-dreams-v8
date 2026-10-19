import { expect } from '@playwright/test';
import { ObjectId } from 'mongodb';
import { test } from '../support/h2h-cases';
import { database } from '../support/h2h';
import { historyFixture } from '../support/history-trophy-fixture';
import { HistoryTrophyPage } from '../pages/history-trophy/history-trophy.page';
test.setTimeout(45000);

for(const view of ['league-history','trophy-room','franchise'] as const) {
  for(const [status,message] of [[401,'Sign in'],[403,'do not have access'],[404,'could not be found'],[500,'could not be loaded']] as const) {
    test(`GAP error ${status} is visible and retry recovers ${view}`,async({page,api})=>{
      const l=await historyFixture(api),p=new HistoryTrophyPage(page);
      const endpoint=view==='franchise'?`**/api/teams/${l.teams[0].id}/trophy-room`:`**/api/leagues/${l.id}/trophy-room`;
      await page.route(endpoint, route=>route.fulfill({status,json:{detail:'Injected failure'}}));
      await p.open(l.id,view==='franchise'?`/trophy-room/team/${l.teams[0].id}`:`/${view}`);
      await expect(p.ui.alert()).toContainText(message);
      await expect(p.ui.banner('championship',2026)).toHaveCount(0);
      await page.unroute(endpoint);await p.ui.retry().click();
      if(view==='league-history')await expect(p.ui.historyTeamRow(l.teams[0].name)).toBeVisible();
      else await expect(p.ui.banner('championship',2026)).toBeVisible();
      await expect(p.ui.alert()).toHaveCount(0);
    });
  }
}

test('GAP draft awards failure stays distinct from empty draft history',async({page,api})=>{
  const l=await historyFixture(api),p=new HistoryTrophyPage(page),url=`**/api/leagues/${l.id}/draft-hall-of-awards`;
  await page.route(url,r=>r.fulfill({status:500,json:{detail:'Failure'}}));
  await p.open(l.id,'/trophy-room');await expect(p.ui.banner('championship',2026)).toBeVisible();await expect(p.ui.alert()).toContainText('could not be loaded');
  await page.unroute(url);await p.ui.retry().click();await expect(p.ui.alert()).toHaveCount(0);
  await expect(p.ui.room()).toContainText('Complete a draft');
});

for(const franchise of [false,true]) {
  test(`GAP filtered empty state resets ${franchise?'franchise':'league'} awards`,async({page,api})=>{
    const l=await historyFixture(api),p=new HistoryTrophyPage(page);
    await p.open(l.id,franchise?`/trophy-room/team/${l.teams[0].id}`:'/trophy-room');await expect(p.ui.banner('championship',2026)).toBeVisible();
    await p.ui.recent().click();await p.year(2019);
    const rafters=franchise?p.ui.teamRafters():p.ui.leagueRafters();await expect(rafters).toContainText('No awards match these filters');
    await rafters.getByRole('button',{name:'Reset filters',exact:true}).click();await expect(p.ui.banner('championship',2019)).toBeVisible();await expect(p.ui.trophy('season-mvp',2019)).toBeVisible();
  });
}

for(const tied of [false,true]) {
  test(`GAP championship records show ${tied?'all tied holders':'no winner at zero'}`,async({page,api})=>{
    const l=await historyFixture(api),p=new HistoryTrophyPage(page);
    await database(async db=>{
      const snaps=await db.collection('league_seasons').find({league_id:l.id}).sort({season_year:-1}).toArray();
      for(const [i,snap] of snaps.entries()) await db.collection('league_seasons').updateOne({_id:snap._id},{$set:{champion_team_name:tied?l.teams[i<2?0:1].name:null}});
    });
    await p.open(l.id,'/league-history');await expect(p.ui.historyTeamRow(l.teams[0].name)).toBeVisible();await p.ui.tab('League Records').click();
    if(tied){await expect(p.ui.championshipRecord()).toContainText(l.teams[0].name);await expect(p.ui.championshipRecord()).toContainText(l.teams[1].name);}
    else {await expect(p.ui.championshipRecord()).toContainText('No championships yet');await expect(p.ui.championshipRecord()).not.toContainText(l.teams[0].name);}
  });
}

for(const route of ['/league-history','/trophy-room']) {
  test(`GAP delayed league response cannot overwrite new selection ${route}`,async({page,api})=>{
    const a=await historyFixture(api),b=await historyFixture(api),p=new HistoryTrophyPage(page);
    let release!:()=>void,started!:()=>void,finished!:()=>void;
    const gate=new Promise<void>(r=>release=r),entered=new Promise<void>(r=>started=r),done=new Promise<void>(r=>finished=r);
    await page.route(`**/api/leagues/${a.id}/trophy-room`,async r=>{const response=await r.fetch();started();await gate;try{await r.fulfill({response});}catch{}finally{finished();}});
    await p.open(a.id,route);await entered;
    const menu=page.getByRole('button',{name:'Toggle navigation menu',exact:true});if(await menu.isVisible())await menu.click();await p.ui.leaguePicker().click();await p.ui.leagueOption(b.id).click();await page.keyboard.press('Escape');await page.keyboard.press('Escape');
    if(route==='/league-history')await expect(p.ui.historyRow(b.teams[0].id)).toBeVisible();
    else await expect(p.ui.teamCard(b.teams[0].id)).toBeVisible();
    release();await done;
    if(route==='/league-history'){await expect(p.ui.historyRow(b.teams[0].id)).toBeVisible();await expect(p.ui.historyRow(a.teams[0].id)).toHaveCount(0);}
    else {await expect(p.ui.teamCard(b.teams[0].id)).toBeVisible();await expect(p.ui.teamCard(a.teams[0].id)).toHaveCount(0);}
  });
}

test('GAP franchise loading and delayed response follow selected roster team',async({page,api})=>{
  const l=await historyFixture(api),p=new HistoryTrophyPage(page);
  let release!:()=>void,started!:()=>void,finished!:()=>void;
  const gate=new Promise<void>(r=>release=r),entered=new Promise<void>(r=>started=r),done=new Promise<void>(r=>finished=r);
  await page.route(`**/api/teams/${l.teams[0].id}/trophy-room`,async r=>{const response=await r.fetch();started();await gate;try{await r.fulfill({response});}catch{}finally{finished();}});
  await p.open(l.id,`/roster?team=${l.teams[0].id}`);await p.ui.rosterTab().click();await entered;await expect(p.ui.status()).toBeVisible();await expect(p.ui.leagueRafters()).toHaveCount(0);
  await p.selectTeam(l.teams[0].name,l.teams[1].name);await expect(p.ui.embedded()).toContainText(`${l.teams[1].name} — Trophy Room`);
  release();await done;await expect(p.ui.embedded()).toContainText(`${l.teams[1].name} — Trophy Room`);await expect(p.ui.banner('championship',2026)).toHaveCount(0);
});
