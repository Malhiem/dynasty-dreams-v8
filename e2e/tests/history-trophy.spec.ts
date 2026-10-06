import { expect, request } from '@playwright/test';
import { ObjectId } from 'mongodb';
import { test } from '../support/h2h-cases';
import { database, result } from '../support/h2h';
import { historyFixture, years } from '../support/history-trophy-fixture';
import { HistoryTrophyPage } from '../pages/history-trophy/history-trophy.page';
test.setTimeout(45000);

for (const format of ['h2h-points','h2h-categories','rotisserie'] as const) {
  test(`LH-01 TR-01 ${format} league menu opens history and trophy room`,async({page,api})=>{
    const l=await historyFixture(api,format), p=new HistoryTrophyPage(page);
    await p.open(l.id,'/league-history'); await expect(p.ui.history()).toBeVisible();
    await expect(p.ui.tab('Lifetime Records')).toHaveAttribute('aria-selected','true');
    for(const name of ['Lifetime Records','League Records','Player Awards','Transactions','Trophy Room']) await expect(p.ui.tab(name)).toBeVisible();
    await page.getByRole('link',{name:'Trophy Room',exact:true}).click(); await expect(p.ui.room()).toContainText('Championship Banners');
    await page.getByRole('link',{name:'League History',exact:true}).click(); await expect(p.ui.history()).toBeVisible();
  });
  test(`LH-03 LH-05 ${format} lifetime records aggregate four completed snapshots`,async({page,api})=>{
    const l=await historyFixture(api,format),p=new HistoryTrophyPage(page); await p.open(l.id,'/league-history');
    const row=p.ui.historyTeamRow(l.teams[0].name); await expect(row).toContainText('.750');
    const cells=await row.getByRole('cell').allTextContents(); expect(cells.slice(2,8).map(s=>s.trim())).toEqual(['4','32','8','.750','4,060','4W']);
  });
  test(`SH-04 ${format} league and franchise championship banners agree`,async({api})=>{
    const l=await historyFixture(api,format);
    const league=await result(await api.get(`/api/leagues/${l.id}/trophy-room`));
    const team=await result(await api.get(`/api/teams/${l.teams[0].id}/trophy-room`));
    expect(league.seasons.map((s:any)=>s.champion.team_id)).toEqual(years.map(()=>l.teams[0].id));
    expect(team.banners.filter((b:any)=>b.type==='championship').map((b:any)=>b.year)).toEqual(years);
    expect(team.individual_awards).toHaveLength(12);
  });
}
test('LH-04 snapshotted active year is never counted twice',async({page,api})=>{
  const l=await historyFixture(api),p=new HistoryTrophyPage(page);
  await database(db=>db.collection('teams').updateOne({_id:new ObjectId(l.teams[0].id)},{$set:{wins:8,losses:2,ties:2,points_for:1000,points_against:500}}));
  await p.open(l.id,'/league-history'); const row=p.ui.historyTeamRow(l.teams[0].name); await expect(row).toBeVisible();
  await expect(row).toContainText('4,060'); expect((await row.getByRole('cell').allTextContents()).slice(2,7).map(s=>s.trim())).toEqual(['4','32','8','.750','4,060']);
});
test('LH-11 LH-13 league records and player award scores match fixture',async({page,api})=>{
  const l=await historyFixture(api),p=new HistoryTrophyPage(page); await p.open(l.id,'/league-history');
  await expect(p.ui.historyTeamRow(l.teams[0].name)).toBeVisible(); await p.ui.tab('League Records').click();
  await expect(p.ui.panel()).toContainText('1,030'); await expect(p.ui.panel()).toContainText('Most Championships');
  await p.ui.tab('Player Awards').click(); await expect(p.ui.panel()).toContainText('History 1 Skater');
  await expect(p.ui.panel()).toContainText('100'); await expect(p.ui.panel()).toContainText('90');
});
test('TR-06 TR-08 league year filter removes unrelated years and resets',async({page,api})=>{
  const l=await historyFixture(api),p=new HistoryTrophyPage(page); await p.open(l.id,'/trophy-room'); await p.year(2020);
  await expect(p.ui.banner('championship',2020)).toBeVisible(); await expect(p.ui.banner('championship',2026)).toHaveCount(0);
  await expect(p.ui.trophy('season-mvp',2020)).toBeVisible(); await expect(p.ui.trophy('season-mvp',2026)).toHaveCount(0);
  await p.year('all'); await expect(p.ui.banner('championship',2026)).toBeVisible(); await expect(p.ui.trophy('season-mvp',2026)).toBeVisible();
});
test('TR-04 recent banners and individual honors use identical years',async({page,api})=>{
  const l=await historyFixture(api),p=new HistoryTrophyPage(page); await p.open(l.id,'/trophy-room'); await expect(p.ui.banner('championship',2026)).toBeVisible();
  await p.ui.recent().click();
  const bannerYears:number[]=[], trophyYears:number[]=[];
  for(const year of years){if(await p.ui.banner('championship',year).count())bannerYears.push(year);if(await p.ui.trophy('season-mvp',year).count())trophyYears.push(year);}
  expect(bannerYears).toEqual(years.slice(0,3)); expect(trophyYears).toEqual(years.slice(0,3));
});
test('TR-10 FT-11 team card opens franchise and returns to league room',async({page,api})=>{
  const l=await historyFixture(api),p=new HistoryTrophyPage(page); await p.open(l.id,'/trophy-room'); await p.ui.teamCard(l.teams[0].id).click();
  await expect(page).toHaveURL(new RegExp(`/trophy-room/team/${l.teams[0].id}$`)); await expect(p.ui.teamRafters()).toContainText(l.teams[0].name);
  await p.ui.exit().click(); await expect(page).toHaveURL(/\/trophy-room$/); await expect(p.ui.leagueRafters()).toBeVisible();
});
test('FT-06 franchise year filter applies to banners and individual honors',async({page,api})=>{
  const l=await historyFixture(api),p=new HistoryTrophyPage(page); await p.open(l.id,`/trophy-room/team/${l.teams[0].id}`); await expect(p.ui.teamRafters()).toBeVisible(); await p.year(2020);
  await expect(p.ui.banner('championship',2020)).toBeVisible(); expect.soft(await p.ui.banner('championship',2026).count()).toBe(0);
  expect(await p.ui.trophy('season-mvp',2026).count()).toBe(0);
  await expect(p.ui.trophy('season-mvp',2020)).toBeVisible();
});
test('FT-07 franchise recent filter changes displayed award years',async({page,api})=>{
  const l=await historyFixture(api),p=new HistoryTrophyPage(page); await p.open(l.id,`/trophy-room/team/${l.teams[0].id}`); await expect(p.ui.teamRafters()).toBeVisible(); await p.ui.recent().click();
  for(const year of years.slice(0,3)) {await expect(p.ui.banner('championship',year)).toBeVisible();await expect(p.ui.trophy('season-mvp',year)).toBeVisible();}
  await expect(p.ui.banner('championship',2019)).toHaveCount(0); await expect(p.ui.trophy('season-mvp',2019)).toHaveCount(0);
});
test('FT-01 roster Visit Trophy Room opens selected franchise',async({page,api})=>{
  const l=await historyFixture(api),p=new HistoryTrophyPage(page); await p.open(l.id,`/roster?team=${l.teams[0].id}`);
  await expect(p.ui.rosterLink()).toHaveAttribute('href',`/trophy-room/team/${l.teams[0].id}`); await p.ui.rosterLink().click(); await expect(p.ui.teamRafters()).toBeVisible();
  await expect(p.ui.room()).toContainText(`${l.teams[0].name} — Trophy Room`);
});
test('FT-02 roster link follows selection of another team',async({page,api})=>{
  const l=await historyFixture(api),p=new HistoryTrophyPage(page); await p.open(l.id,`/roster?team=${l.teams[0].id}`); await expect(p.ui.rosterLink()).toBeVisible();
  await p.selectTeam(l.teams[0].name,l.teams[1].name); await expect(p.ui.rosterLink()).toHaveAttribute('href',`/trophy-room/team/${l.teams[1].id}`);
  await p.ui.rosterLink().click(); await expect(p.ui.room()).toContainText(`${l.teams[1].name} — Trophy Room`);
});
test('FT-03 FT-04 roster embedded trophy tab follows selected team',async({page,api})=>{
  const l=await historyFixture(api),p=new HistoryTrophyPage(page); await p.open(l.id,`/roster?team=${l.teams[0].id}`); await p.ui.rosterTab().click();
  await expect(p.ui.embedded()).toContainText(`${l.teams[0].name} — Trophy Room`); await expect(p.ui.exit()).toHaveCount(0);
  await p.selectTeam(l.teams[0].name,l.teams[1].name); await expect(p.ui.embedded()).toContainText(`${l.teams[1].name} — Trophy Room`);
  await expect(p.ui.banner('championship',2026)).toHaveCount(0);
});
test('FT-09 award-free franchise has team identity and empty states',async({page,api})=>{
  const l=await historyFixture(api),p=new HistoryTrophyPage(page); await p.open(l.id,`/trophy-room/team/${l.teams[1].id}`);
  await expect(p.ui.teamRafters()).toContainText('No banners hung yet'); await expect(p.ui.room()).toContainText('Drafting future MVPs'); await expect(p.ui.leagueRafters()).toHaveCount(0);
});
test('LH-20 history embedded trophy room shows same fixture awards',async({page,api})=>{
  const l=await historyFixture(api),p=new HistoryTrophyPage(page); await p.open(l.id,'/league-history'); await expect(p.ui.historyTeamRow(l.teams[0].name)).toBeVisible(); await p.ui.tab('Trophy Room').click();
  await expect(p.ui.leagueRafters()).toBeVisible(); await expect(p.ui.banner('championship',2026)).toBeVisible(); await expect(p.ui.trophy('season-mvp',2020)).toBeVisible();
});
test('SH-07 anonymous requests cannot read private league history',async({api})=>{
  const l=await historyFixture(api), anon=await request.newContext({baseURL:'http://web'});
  try{for(const path of [`/api/leagues/${l.id}/seasons?include_team_stats=true`,`/api/leagues/${l.id}/seasons/2026`,`/api/leagues/${l.id}/trophy-room`,`/api/teams/${l.teams[0].id}/trophy-room`]){
    const response=await anon.get(path); expect.soft(response.status(),path).toBe(401);
  }}finally{await anon.dispose();}
});
test('SH-07 authenticated outsider cannot read another private league history',async({api})=>{
  const l=await historyFixture(api), outsider=await request.newContext({baseURL:'http://web'});
  try {
    const suffix=crypto.randomUUID().replace(/-/g,''),email=`history-${suffix}@example.com`,password='HistoryFixture123!';
    await result(await outsider.post('/api/auth/register',{data:{email,username:`history_${suffix.slice(0,16)}`,password}}));
    await result(await outsider.post('/api/auth/login',{data:{email,password}}));
    for(const path of [`/api/leagues/${l.id}/seasons?include_team_stats=true`,`/api/leagues/${l.id}/seasons/2026`,`/api/leagues/${l.id}/trophy-room`,`/api/teams/${l.teams[0].id}/trophy-room`]) {
      const response=await outsider.get(path);expect.soft(response.status(),path).toBe(403);
    }
  } finally {await outsider.dispose();}
});



test('TR-07 FT-06 recent and year filters intersect consistently',async({page,api})=>{
  const l=await historyFixture(api),p=new HistoryTrophyPage(page);
  for(const route of ['/trophy-room',`/trophy-room/team/${l.teams[0].id}`]) {
    await p.open(l.id,route); await expect(p.ui.banner('championship',2026)).toBeVisible();
    await p.ui.recent().click(); await p.year(2019);
    for(const year of years) {await expect(p.ui.banner('championship',year)).toHaveCount(0);await expect(p.ui.trophy('season-mvp',year)).toHaveCount(0);}
    await p.ui.all().click(); await expect(p.ui.banner('championship',2019)).toBeVisible(); await expect(p.ui.trophy('season-mvp',2019)).toBeVisible();
    await p.year('all'); await expect(p.ui.banner('championship',2026)).toBeVisible();
  }
});
test('LH-04 a distinct active season is included once',async({page,api})=>{
  const l=await historyFixture(api),p=new HistoryTrophyPage(page);
  await database(async db=>{
    await db.collection('leagues').updateOne({_id:new ObjectId(l.id)},{$set:{current_season_year:2027}});
    await db.collection('teams').updateOne({_id:new ObjectId(l.teams[0].id)},{$set:{wins:8,losses:2,ties:2,points_for:1000,points_against:500}});
  });
  await p.open(l.id,'/league-history');const row=p.ui.historyTeamRow(l.teams[0].name);await expect(row).toContainText('5,060');
  expect((await row.getByRole('cell').allTextContents()).slice(2,7).map(s=>s.trim())).toEqual(['5','40','10','.750','5,060']);
});
