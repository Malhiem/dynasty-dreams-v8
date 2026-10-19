import {test,expect,type Page} from '@playwright/test';
import {LoginPage} from '../pages/login/login.page';
import {DraftSalaryPage} from '../pages/draft-salary/draft-salary.page';
import {salaryFixture} from '../support/draft-salary';
import {draftListCandidates} from '../support/draft-list';
async function verifyPaging(page:Page){
 const login=new LoginPage(page);await login.goto();await login.logIn({email:'admin@e2e.dynastydreams.com',password:'e2e-admin-password'});
 await expect(page).toHaveURL(/dashboard/);const pool=await draftListCandidates(10_000_000);const f=await salaryFixture(page.request);
 try{
  const pagedIds:string[]=[];
  for(let number=1;number<=3;number++){
   const response=await page.request.get(`/api/drafts/${f.draft.id}/eligible-players?limit=50&page=${number}&search=${encodeURIComponent(pool.prefix)}`);
   expect(response.ok(),await response.text()).toBeTruthy();const data=await response.json();
   pagedIds.push(...data.players.map((p:any)=>p.id));
  }
  expect(pagedIds).toEqual(pool.players.map(p=>String(p._id)));
  const target=pool.players[119];const invalid=pool.players[0];
  const eligibilityResponse=await page.request.post(`/api/drafts/${f.draft.id}/salary-eligibility`,{data:{player_ids:[String(target._id),String(invalid._id)]}});
  expect(eligibilityResponse.ok(),await eligibilityResponse.text()).toBeTruthy();const eligibility=await eligibilityResponse.json();
  expect(eligibility.players[String(target._id)]).toMatchObject({allowed:true,feasible:true,projected_payroll:56_000_000,remaining_slots:1});
  expect(eligibility.players[String(invalid._id)]).toMatchObject({allowed:false,reason:'salary_completion_infeasible'});
  const before=await(await page.request.get(`/api/drafts/${f.draft.id}`)).json();
  const rejected=await page.request.post(`/api/drafts/${f.draft.id}/pick`,{data:{player_id:String(invalid._id),destination:'ACT',expected_pick:1}});
  expect(rejected.status()).toBe(409);
  const unchanged=await(await page.request.get(`/api/drafts/${f.draft.id}`)).json();
  expect(unchanged.picks).toEqual(before.picks);expect(unchanged.current_pick).toBe(before.current_pick);
  const room=new DraftSalaryPage(page);await room.open(f.league.id);await room.search(pool.prefix);
  await expect(room.rows()).toHaveCount(50);await room.loadMore();await expect(room.rows()).toHaveCount(100);
  await room.loadMore();await expect(room.rows()).toHaveCount(120);
  await room.search(target.name);await expect(room.rows()).toHaveCount(1);
  await expect(room.candidate(String(target._id))).toContainText(target.name);
  await room.preview(String(target._id),target.name);
  await expect(room.draftButton()).toBeEnabled();await room.draftButton().scrollIntoViewIfNeeded();
  const button=await room.draftButton().boundingBox();expect(button).not.toBeNull();
  expect(button!.width).toBeGreaterThanOrEqual(44);expect(button!.height).toBeGreaterThanOrEqual(44);
  expect(button!.x).toBeGreaterThanOrEqual(0);expect(button!.x+button!.width).toBeLessThanOrEqual(page.viewportSize()!.width);
  await room.draftButton().click();await expect(room.destination()).toBeVisible();
  await room.destination().selectOption('ACT');await expect(room.confirm()).toBeEnabled();await room.confirm().click();
  await expect(room.payroll()).toContainText('$56,000,000');await expect(room.positions()).toContainText('Active 2/3');
  const after=await(await page.request.get(`/api/drafts/${f.draft.id}`)).json();
  expect(after.picks).toHaveLength(before.picks.length+1);expect(after.current_pick).toBe(before.current_pick+1);
  expect(after.picks.filter((pick:any)=>pick.player_id===String(target._id))).toHaveLength(1);
  await page.reload();await expect(room.payroll()).toContainText('$56,000,000');await expect(room.positions()).toContainText('Active 2/3');
 }finally{await pool.cleanup();await f.cleanup();}
}
test('large draft list pages results and search still selects a candidate beyond the initial page',async({page})=>verifyPaging(page));
for(const viewport of [{width:320,height:700},{width:430,height:932},{width:844,height:390}]){
 test(`eligible draft candidate remains tappable at ${viewport.width}x${viewport.height}`,async({page})=>{
  await page.setViewportSize(viewport);await verifyPaging(page);
 });
}
