import {test,expect} from '@playwright/test';
import {LoginPage} from '../pages/login/login.page';
import {DraftSalaryPage} from '../pages/draft-salary/draft-salary.page';
import {salaryFixture} from '../support/draft-salary';
import {draftListCandidates} from '../support/draft-list';
import {database,result} from '../support/h2h';

test('draft search reaches a real candidate beyond 10000 players and ignores a delayed old search',async({page},info)=>{
 const login=new LoginPage(page);await login.goto();await login.logIn({email:'admin@e2e.dynastydreams.com',password:'e2e-admin-password'});await expect(page).toHaveURL(/dashboard/);
 const f=await salaryFixture(page.request);const pool=await draftListCandidates(10_000_000,10005);
 let releaseOld=()=>{};
 try{
  await database(async db=>{await db.collection('players').updateMany({_id:{$in:pool.players.map(p=>p._id)}},{$set:{minor_eligible:true}});await db.collection('players').updateOne({_id:pool.players[10003]._id},{$set:{salary:6_000_000}});});await f.restrictToMinorEligible();
  const target=pool.players[10004],invalid=pool.players[0];
  const last=await result(await page.request.get(`/api/drafts/${f.draft.id}/eligible-players?limit=200&page=51&search=${encodeURIComponent(pool.prefix)}`));expect(last.total).toBe(10005);expect(last.pages).toBe(51);expect(last.players.map((p:any)=>p.id)).toContain(String(target._id));
  expect((await page.request.post(`/api/drafts/${f.draft.id}/pick`,{data:{player_id:String(invalid._id),destination:'ACT',expected_pick:1}})).status()).toBe(409);
  let oldSeen=()=>{};const seen=new Promise<void>(resolve=>{oldSeen=resolve;});const hold=new Promise<void>(resolve=>{releaseOld=resolve;});
  await page.route('**/eligible-players?**',async route=>{if(new URL(route.request().url()).searchParams.get('search')===invalid.name){const response=await route.fetch();oldSeen();await hold;await route.fulfill({response}).catch(()=>{});}else await route.continue();});
  const room=new DraftSalaryPage(page);await room.open(f.league.id);await room.search(invalid.name);await seen;
  const searched=page.waitForResponse(r=>new URL(r.url()).pathname===`/api/drafts/${f.draft.id}/eligible-players`&&new URL(r.url()).searchParams.get('search')===target.name);
  await room.search(target.name);expect((await searched).ok()).toBe(true);await expect(room.candidate(String(target._id))).toBeVisible();releaseOld();
  await expect(room.candidate(String(invalid._id))).toHaveCount(0);await room.choose(String(target._id),target.name);await room.destination().selectOption('ACT');await room.confirm().click();await expect(room.payroll()).toContainText('$56,000,000');
  const saved=await result(await page.request.get(`/api/drafts/${f.draft.id}`));expect(saved.picks).toHaveLength(1);expect(saved.picks[0].player_id).toBe(String(target._id));
  await info.attach('beyond-former-cutoff',{body:JSON.stringify({total:last.total,pages:last.pages,target:String(target._id),persisted_pick:saved.picks[0]}),contentType:'application/json'});
 }finally{releaseOld();await pool.cleanup();await f.cleanup();}
});
