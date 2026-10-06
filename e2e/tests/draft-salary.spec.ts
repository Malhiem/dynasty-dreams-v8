import { expect,test } from "@playwright/test";
import { LoginPage } from "../pages/login/login.page";
import { DraftSalaryPage } from "../pages/draft-salary/draft-salary.page";
import { salaryFixture } from "../support/draft-salary";

test.beforeEach(async({page})=>{
  await new LoginPage(page).goto();await new LoginPage(page).logIn({email:"admin@e2e.dynastydreams.com",password:"e2e-admin-password"});
  await expect(page).toHaveURL(/\/dashboard/);
});

test("strict salary feasibility rejects illegal API picks without mutation and shows team totals",async({page},info)=>{
  const f=await salaryFixture(page.request);
  try {
    const ids=f.candidates.map(p=>String(p._id));
    const eligibility=await page.request.post(`/api/drafts/${f.draft.id}/salary-eligibility`,{data:{player_ids:ids}});
    expect(eligibility.ok(),await eligibility.text()).toBeTruthy();
    const data=await eligibility.json();expect(ids.map(id=>data.players[id].allowed)).toEqual([false,true,true,true,true,false]);
    const before=await(await page.request.get(`/api/drafts/${f.draft.id}`)).json();
    const rejected=await page.request.post(`/api/drafts/${f.draft.id}/pick`,{data:{player_id:ids[0],destination:"ACT",expected_pick:1}});
    expect(rejected.status()).toBe(409);
    const after=await(await page.request.get(`/api/drafts/${f.draft.id}`)).json();
    expect(after.picks).toEqual(before.picks);expect(after.current_pick).toBe(before.current_pick);expect(after.current_pick_started_at).toBe(before.current_pick_started_at);
    const room=new DraftSalaryPage(page);await room.open(f.league.id);
    await expect(room.payroll()).toContainText("$46,000,000");await expect(room.positions()).toContainText("Active 1/3");
    await expect(room.candidate(ids[0])).toHaveAttribute("data-salary-blocked","true");
    await room.teamSelect().selectOption(String(f.teams[1]._id));await expect(room.positions()).toContainText("Active 0/3");
    await info.attach("salary-api-evidence",{body:JSON.stringify(data,null,2),contentType:"application/json"});
    await page.screenshot({path:info.outputPath("salary-totals.png"),fullPage:true});
  } finally{await f.cleanup();}
});

test("informal mode permits an over-cap pick with a warning and persisted notification",async({page},info)=>{
  const f=await salaryFixture(page.request);
  try{
    const settings=await page.request.put(`/api/leagues/${f.league.id}/admin/cap-settings`,{data:{salary_adherence_mode:"informal"}});expect(settings.ok()).toBeTruthy();
    const result=await page.request.post(`/api/drafts/${f.draft.id}/pick`,{data:{player_id:String(f.candidates[5]._id),expected_pick:1}});
    expect(result.ok(),await result.text()).toBeTruthy();const body=await result.json();expect(body.salary_validation.feasible).toBe(false);expect(await f.notificationCount()).toBe(1);
    const room=new DraftSalaryPage(page);await room.open(f.league.id);await expect(room.payroll()).toContainText("$65,000,000");await expect(room.overview()).toContainText("Over cap");
    await info.attach("informal-pick",{body:JSON.stringify(body),contentType:"application/json"});
  }finally{await f.cleanup();}
});

test("direct IR drafting is salary exempt and activation is blocked in Strict mode",async({page},info)=>{
  const f=await salaryFixture(page.request,true);
  try{
    const playerId=String(f.candidates[1]._id);
    const active=await page.request.post(`/api/drafts/${f.draft.id}/pick`,{data:{player_id:playerId,destination:"ACT",expected_pick:1}});expect(active.status()).toBe(409);
    const room=new DraftSalaryPage(page);await room.open(f.league.id);
    await room.choose(playerId);await room.destination().selectOption("IR");await expect(room.confirm()).toBeEnabled();await room.confirm().click();
    await expect(room.payroll()).toContainText("$58,000,000");await expect(room.positions()).toContainText("IR 1/1");
    const picked=await(await page.request.get(`/api/drafts/${f.draft.id}`)).json();expect(picked.picks[0].destination).toBe("IR");
    const move=await page.request.post(`/api/drafts/${f.draft.id}/roster-move`,{data:{team_id:String(f.teams[0]._id),player_id:playerId,destination:"ACT"}});expect(move.status()).toBe(409);
    await expect(room.payroll()).toContainText("$58,000,000");await expect(room.positions()).toContainText("IR 1/1");await expect(room.positions()).toContainText("Active 1/2");
    await info.attach("ir-pick",{body:JSON.stringify(picked),contentType:"application/json"});
    await page.screenshot({path:info.outputPath("ir-roster.png"),fullPage:true});
    const informal=await page.request.put(`/api/leagues/${f.league.id}/admin/cap-settings`,{data:{salary_adherence_mode:"informal"}});expect(informal.ok()).toBeTruthy();
    await room.move(f.candidates[1].name,"ACT");await expect(room.payroll()).toContainText("$62,000,000");await expect(room.positions()).toContainText("Active 2/2");await expect(room.positions()).toContainText("IR 0/1");
  }finally{await f.cleanup();}
});


test("autopick skips an infeasible queued player and commits a legal replacement",async({page},info)=>{
  const f=await salaryFixture(page.request);
  try{
    await f.setQueue([String(f.candidates[0]._id),String(f.candidates[1]._id)]);
    const picked=await page.request.post(`/api/drafts/${f.draft.id}/auto-pick`);
    expect(picked.ok(),await picked.text()).toBeTruthy();
    const draft=await(await page.request.get(`/api/drafts/${f.draft.id}`)).json();
    expect(draft.picks).toHaveLength(1);expect(draft.picks[0].player_id).toBe(String(f.candidates[1]._id));expect(draft.picks[0].salary_validation.feasible).toBe(true);
    await info.attach("autopick-result",{body:JSON.stringify(draft),contentType:"application/json"});
  }finally{await f.cleanup();}
});

test("simultaneous picks for the same expected turn commit exactly one player",async({page},info)=>{
  const f=await salaryFixture(page.request);
  try{
    const results=await Promise.all([1,2].map(i=>page.request.post(`/api/drafts/${f.draft.id}/pick`,{data:{player_id:String(f.candidates[i]._id),expected_pick:1}})));
    expect(results.map(r=>r.status()).sort()).toEqual([200,409]);
    const draft=await(await page.request.get(`/api/drafts/${f.draft.id}`)).json();expect(draft.picks).toHaveLength(1);expect(draft.current_pick).toBe(2);
    const totals=await(await page.request.get(`/api/drafts/${f.draft.id}/roster-status`)).json();expect(totals.teams.find((t:{team_id:string,positions:{ACT:{filled:number}}})=>t.team_id===String(f.teams[0]._id)).positions.ACT.filled).toBe(2);
    await info.attach("concurrency-result",{body:JSON.stringify(draft),contentType:"application/json"});
  }finally{await f.cleanup();}
});


test("salary totals require membership and roster edits require ownership",async({page,request},info)=>{
  const f=await salaryFixture(page.request);
  try{
    expect((await request.get(`/api/drafts/${f.draft.id}/roster-status`)).status()).toBe(401);
    const username=`draft_member_${crypto.randomUUID().replaceAll("-","").slice(0,10)}`;
    const registered=await request.post("/api/auth/register",{data:{username,email:`${username}@example.com`,password:"DraftFixture2026!"}});
    expect(registered.ok(),await registered.text()).toBeTruthy();const user=await registered.json();const headers={Authorization:`Bearer ${user.access_token}`};
    expect((await request.get(`/api/drafts/${f.draft.id}/roster-status`,{headers})).status()).toBe(403);
    await f.assignMember(user.id);
    const totals=await request.get(`/api/drafts/${f.draft.id}/roster-status`,{headers});expect(totals.ok()).toBeTruthy();
    const denied=await request.post(`/api/drafts/${f.draft.id}/roster-move`,{headers,data:{team_id:String(f.teams[0]._id),player_id:String(f.existing._id),destination:"IR"}});expect(denied.status()).toBe(403);
    await info.attach("member-totals",{body:await totals.text(),contentType:"application/json"});
  }finally{await f.cleanup();}
});

test("no legal autopick preserves the turn and resumes after Informal mode is selected",async({page},info)=>{
  const f=await salaryFixture(page.request);
  try{
    await f.setQueue([String(f.candidates[0]._id)]);
    const settings=await page.request.put(`/api/leagues/${f.league.id}/admin/cap-settings`,{data:{salary_cap:1,cap_floor_enabled:false}});expect(settings.ok(),await settings.text()).toBeTruthy();
    const rejected=await page.request.post(`/api/drafts/${f.draft.id}/auto-pick`);expect(rejected.status()).toBe(409);
    const blocked=await(await page.request.get(`/api/drafts/${f.draft.id}`)).json();expect(blocked.current_pick).toBe(1);expect(blocked.picks).toHaveLength(0);expect(blocked.salary_blocked).toBe(true);
    const changed=await page.request.put(`/api/leagues/${f.league.id}/admin/cap-settings`,{data:{salary_adherence_mode:"informal"}});expect(changed.ok()).toBeTruthy();
    const resumed=await page.request.post(`/api/drafts/${f.draft.id}/auto-pick`);expect(resumed.ok(),await resumed.text()).toBeTruthy();
    const draft=await(await page.request.get(`/api/drafts/${f.draft.id}`)).json();expect(draft.current_pick).toBe(2);expect(draft.salary_blocked).toBe(false);
    await info.attach("blocked-autopick",{body:JSON.stringify(blocked),contentType:"application/json"});
  }finally{await f.cleanup();}
});


test("floor-only configuration applies its minimum without a salary ceiling",async({page},info)=>{
  const f=await salaryFixture(page.request);
  try{
    await f.restrictToMinorEligible();
    const settings=await page.request.put(`/api/leagues/${f.league.id}/admin/cap-settings`,{data:{salary_cap_enabled:false,cap_floor_enabled:true,cap_floor:70_000_000}});
    expect(settings.ok(),await settings.text()).toBeTruthy();const saved=await settings.json();expect(saved.salary_cap_enabled).toBe(false);expect(saved.cap_floor_enabled).toBe(true);
    const ids=f.candidates.map(p=>String(p._id));const result=await page.request.post(`/api/drafts/${f.draft.id}/salary-eligibility`,{data:{player_ids:ids}});expect(result.ok()).toBeTruthy();const data=await result.json();
    expect(ids.map(id=>data.players[id].allowed)).toEqual([false,false,true,true,true,true]);
    const room=new DraftSalaryPage(page);await room.open(f.league.id);await expect(room.payroll()).toContainText("Cap Disabled");await expect(room.payroll()).toContainText("Floor $70,000,000");
    await info.attach("floor-only-eligibility",{body:JSON.stringify(data),contentType:"application/json"});
  }finally{await f.cleanup();}
});
