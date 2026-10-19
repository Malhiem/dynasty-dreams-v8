import {test,expect} from '@playwright/test';
import {LoginPage} from '../pages/login/login.page';
import {DraftSalaryPage} from '../pages/draft-salary/draft-salary.page';
import {salaryFixture} from '../support/draft-salary';
import {draftListCandidates} from '../support/draft-list';

for(const failure of ['before commit','after commit']){
 test(`draft pick reconciles a lost response ${failure} without duplicate advancement`,async({page},info)=>{
  const login=new LoginPage(page);await login.goto();await login.logIn({email:'admin@e2e.dynastydreams.com',password:'e2e-admin-password'});
  await expect(page).toHaveURL(/dashboard/);
  const pool=await draftListCandidates(10_000_000);const f=await salaryFixture(page.request);let release:()=>void=()=>{};
  try{
   const target=pool.players[119];const room=new DraftSalaryPage(page);await room.open(f.league.id);await room.choose(String(target._id),target.name);
   await room.destination().selectOption('ACT');await expect(room.confirm()).toBeEnabled();
   let posts=0;const gate=new Promise<void>(resolve=>{release=resolve;});
   const pattern=`**/api/drafts/${f.draft.id}/pick`;
   await page.route(pattern,async route=>{
    posts++;
    if(failure==='after commit'){
     const saved=await route.fetch();expect(saved.ok(),await saved.text()).toBeTruthy();
     await gate;
    }
    await route.abort('failed');
   });
   await room.confirm().click();
   if(failure==='after commit'){
    await expect(room.confirm()).toBeDisabled();await expect(room.confirm()).toHaveAttribute('aria-busy','true');release();
   }else{
    await expect(room.pickRejected()).toBeVisible();await expect(room.confirm()).toBeEnabled();
    const untouched=await(await page.request.get(`/api/drafts/${f.draft.id}`)).json();expect(untouched.picks).toHaveLength(0);expect(untouched.current_pick).toBe(1);
    await page.unroute(pattern);await room.confirm().click();
   }
   await expect(room.confirm()).toBeHidden();await expect(room.payroll()).toContainText('$56,000,000');
   expect(posts).toBe(1);
   const saved=await(await page.request.get(`/api/drafts/${f.draft.id}`)).json();
   expect(saved.picks).toHaveLength(1);expect(saved.current_pick).toBe(2);expect(saved.picks[0].player_id).toBe(String(target._id));
   await info.attach('authoritative-draft-after-response-loss',{body:JSON.stringify(saved),contentType:'application/json'});
   await page.reload();await expect(room.payroll()).toContainText('$56,000,000');await expect(room.positions()).toContainText('Active 2/3');
  }finally{release();await pool.cleanup();await f.cleanup();}
 });
}
