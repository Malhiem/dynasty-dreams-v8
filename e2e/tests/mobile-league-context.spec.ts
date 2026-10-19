import {test,expect} from '@playwright/test';
import {actors,dispose,league} from '../support/access-history';
import {database,result} from '../support/h2h';
import {ObjectId} from 'mongodb';
import {LeagueStructurePage} from '../pages/league-structure/league-structure.page';
import {leagueStructureSelectors} from '../pages/league-structure/league-structure.selectors';
test('selected league absent from list remains the only settings write target',async({page,context})=>{
 const a=await actors();try{
  const first=await league(a),selected=await league(a);
  await result(await a.commissioner.api.put(`/api/leagues/${selected.id}`,{data:{matchup_length_days:7}}));
  const firstBefore=await result(await a.commissioner.api.get(`/api/leagues/${first.id}`));
  await context.addCookies((await a.commissioner.api.storageState()).cookies);
  await page.route('**/api/leagues?my_leagues=true&exclude_archived=true&exclude_test=true',route=>route.fulfill({json:[firstBefore]}));
  await new LeagueStructurePage(page).goto(selected.id);
  const later=page.getByRole('button',{name:'Set Up Later',exact:true});if(await later.isVisible())await later.click();
  await page.getByTestId(leagueStructureSelectors.regularSeasonWeeks).fill('14');
  const saved=page.waitForResponse(r=>r.request().method()==='PUT'&&/^\/api\/leagues\/[^/]+$/.test(new URL(r.url()).pathname));
  await page.getByTestId(leagueStructureSelectors.regularSeasonSave).click();
  const response=await saved;expect(new URL(response.url()).pathname).toBe(`/api/leagues/${selected.id}`);expect(response.ok(),await response.text()).toBeTruthy();
  expect((await result(await a.commissioner.api.get(`/api/leagues/${selected.id}`))).regular_season_weeks).toBe(14);
  expect((await result(await a.commissioner.api.get(`/api/leagues/${first.id}`))).regular_season_weeks).toBe(firstBefore.regular_season_weeks);
  expect(await page.evaluate(()=>localStorage.getItem('dd_active_league_id'))).toBe(selected.id);
  await page.reload();await expect(page.getByTestId(leagueStructureSelectors.regularSeasonWeeks)).toHaveValue('14');
 }finally{await dispose(a);}
});

test('newly created league remains discoverable when the membership list is capped',async()=>{
 const a=await actors();const fillerIds=Array.from({length:201},()=>new ObjectId());
 try{
  const first=await league(a);const template=await database(db=>db.collection('leagues').findOne({_id:new ObjectId(first.id)}));
  await database(db=>db.collection('leagues').insertMany(fillerIds.map((_id,i)=>({...template,_id,name:`Capped list fixture ${i}`,created_at:new Date('2000-01-01')}))));
  const selected=await league(a);const list=await result(await a.commissioner.api.get('/api/leagues?my_leagues=true&exclude_archived=true&exclude_test=true'));
  expect(list).toHaveLength(200);expect(list.some((l:any)=>l.id===selected.id)).toBe(true);
 }finally{await database(db=>db.collection('leagues').deleteMany({_id:{$in:fillerIds}}));await dispose(a);}
});
