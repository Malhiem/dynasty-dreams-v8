import {actors,dispose} from '../support/access-history';
import {salaryLeague,settings,execute,freePlayer} from '../support/salary';
import {database,result} from '../support/h2h';
import {test,expect} from '@playwright/test';
import {LoginPage} from '../pages/login/login.page';
import {DraftSalaryPage} from '../pages/draft-salary/draft-salary.page';
import {sweepDraft} from '../support/draft-sweep';
for(const mode of ['snake','linear','snake bonus'] as const)test(`${mode}: all rounds complete with exact ownership and restored room totals`,async({page},info)=>{
 test.setTimeout(120000);
 const login=new LoginPage(page);await login.goto();await login.logIn({email:'admin@e2e.dynastydreams.com',password:'e2e-admin-password'});await expect(page).toHaveURL(/\/dashboard/);
 const bonus=mode==='snake bonus',f=await sweepDraft(page.request,mode!=='linear',bonus);
 try{
  const before=await f.snapshot(),abbrs=before.draft!.team_abbrs as string[];
  const expected=Array.from({length:5},(_,round)=>mode!=='linear'&&round%2?[...abbrs].reverse():abbrs).flat();
  if(bonus)expected.splice(2,0,Object.entries(before.draft!.team_map).find(([,v]:any)=>v.id===String(f.teams[0]._id))![0]);
  for(const [index,abbr] of expected.entries()){
   const response=await page.request.post(`/api/drafts/${f.draft.id}/pick`,{data:{player_id:String(f.players[index]._id),destination:'ACT',expected_pick:index+1}});
   expect(response.ok(),await response.text()).toBe(true);
   const state=await f.snapshot(),pick=state.draft!.picks[index];
   expect(pick.overall).toBe(index+1);expect(pick.team_id).toBe(before.draft!.team_map[abbr].id);
   expect(state.draft!.current_pick).toBe(index+2);expect(state.draft!.status).toBe(index===expected.length-1?'completed':'active');
  }
  const after=await f.snapshot();expect(after.draft!.picks).toHaveLength(bonus?21:20);
  for(const team of after.teams){expect(team.roster).toHaveLength(bonus&&String(team._id)===String(f.teams[0]._id)?6:5);expect(new Set(team.roster).size).toBe(team.roster.length);}
  const extra=await page.request.post(`/api/drafts/${f.draft.id}/pick`,{data:{player_id:String(f.players[20]._id),destination:'ACT',expected_pick:expected.length+1}});expect(extra.status()).toBe(400);expect(await f.snapshot()).toEqual(after);
  const room=new DraftSalaryPage(page);await room.open(f.league.id);await room.teamSelect().selectOption(String(f.teams[0]._id));
  await expect(room.positions()).toContainText(`Active ${bonus?6:5}/20`);await expect(room.payroll()).toContainText(bonus?'$12,000,000':'$10,000,000');
  await page.reload();await expect(room.positions()).toContainText(`Active ${bonus?6:5}/20`);
  await info.attach('complete-draft',{body:JSON.stringify(after,null,2),contentType:'application/json'});
 }finally{await f.cleanup();}
});

test('active draft trade updates two managers rooms and survives reconnect',async({browser},info)=>{
 test.setTimeout(90000);
 const {ObjectId}=await import('mongodb');
 const a=await actors();let contexts:Awaited<ReturnType<typeof browser.newContext>>[]=[];
 try{
  const l=await salaryLeague(a);await settings(l,{salary_cap_enabled:false,cap_floor_enabled:false,salary_adherence_mode:'informal',position_breakdown:{active:{ACT:25}},draft_roster_target:25,roster_spots:25});
  const created=await result(await a.commissioner.api.post('/api/drafts',{data:{league_id:l.id,name:'Live trade sweep',total_rounds:5,time_per_pick:3600,pick_trading_enabled:true,trading_window_opens:'immediately',player_criteria:['all']}}));const id=created.id||created._id;
  await result(await a.commissioner.api.post(`/api/drafts/${id}/start`,{data:{early_start:true}}));
  const free=await freePlayer(l,1000000);await result(await a.commissioner.api.post(`/api/drafts/${id}/pick`,{data:{player_id:free,destination:'ACT',expected_pick:1}}));
  const draftBefore=await result(await a.commissioner.api.get(`/api/drafts/${id}`));
  const summary=await result(await a.commissioner.api.get(`/api/drafts/${id}/roster-status`));
  const current=summary.teams.find((t:any)=>t.team_id===l.teams[0].id);expect(current).toBeTruthy();
  const before=current.salary_used;const money=(n:number)=>'$'+n.toLocaleString('en-US');
  const pages=[];
  for(const actor of [a.manager,a.manager2]){const context=await browser.newContext({storageState:await actor.api.storageState()});contexts.push(context);const page=await context.newPage();const room=new DraftSalaryPage(page);await room.open(l.id);await room.teamSelect().selectOption(l.teams[0].id);await expect(room.payroll()).toContainText(money(before));pages.push({page,room});}
  await execute(a,l,0,info);
  const changed=await result(await a.commissioner.api.get(`/api/drafts/${id}/roster-status`));expect(changed.teams.find((t:any)=>t.team_id===l.teams[0].id).salary_used).toBe(before-10000000);
  for(const {room} of pages)await expect(room.payroll()).toContainText(money(before-10000000),{timeout:15000});
  await pages[1].page.reload();await pages[1].room.teamSelect().selectOption(l.teams[0].id);await expect(pages[1].room.payroll()).toContainText(money(before-10000000));
  const draftAfter=await result(await a.commissioner.api.get(`/api/drafts/${id}`));expect(draftAfter.picks).toEqual(draftBefore.picks);expect(draftAfter.current_pick).toBe(draftBefore.current_pick);
  const teams=await database(db=>db.collection('teams').find({_id:{$in:l.teams.slice(0,2).map(t=>new ObjectId(t.id))}}).toArray());
  expect(teams.find((t:any)=>String(t._id)===l.teams[0].id)!.roster).not.toContain(l.teams[0].players[0]);expect(teams.find((t:any)=>String(t._id)===l.teams[1].id)!.roster).toContain(l.teams[0].players[0]);
 }finally{for(const context of contexts)await context.close();await dispose(a);}
});
