import {expect,test} from "@playwright/test";
import {DynamicRosterPage} from "../pages/dynamic-roster/dynamic-roster.page";
import {LoginPage} from "../pages/login/login.page";
import {DraftSalaryPage} from "../pages/draft-salary/draft-salary.page";
import {positionFixture} from "../support/dynamic-positions";
test.beforeEach(async({page})=>{const login=new LoginPage(page);await login.goto();await login.logIn({email:"admin@e2e.dynastydreams.com",password:"e2e-admin-password"});await expect(page).toHaveURL(/dashboard/);});
test("draft LW to C updates occupancy, persists on reload and preserves payroll",async({page},info)=>{
 const f=await positionFixture(page.request);try{
  const room=new DraftSalaryPage(page);await room.open(f.league.id);await expect(room.positions()).toContainText("LW 1/1");await expect(room.payroll()).toContainText("$9,000,000");
  const move=(i:number,destination:string)=>page.request.post(`/api/drafts/${f.draft.id}/roster-move`,{data:{team_id:String(f.team._id),player_id:String(f.players[i]._id),destination}});
  const before=await f.snapshot();expect((await move(0,"C")).status()).toBe(400);expect(await f.snapshot()).toEqual(before);
  await room.move("Dual Centre","BN");await expect(room.positions()).toContainText("C 0/1");
  await room.changeDestination("Dual Left","C");await expect(room.positions()).toContainText("C 1/1");await expect(room.positions()).toContainText("LW 0/1");await expect(room.payroll()).toContainText("$9,000,000");
  const moved=await f.snapshot();expect((await move(2,"LW")).status()).toBe(400);expect(await f.snapshot()).toEqual(moved);
  await page.reload();await expect(room.positions()).toContainText("LW 0/1");await expect(room.positions()).toContainText("C 1/1");await expect(room.payroll()).toContainText("$9,000,000");
  expect(moved!.lineup[String(f.players[0]._id)].slot).toBe("C");expect(moved!.roster).toHaveLength(3);
  await info.attach("persisted-draft-assignment",{body:JSON.stringify(moved),contentType:"application/json"});await page.screenshot({path:info.outputPath("draft-positions.png"),fullPage:true});
 }finally{await f.cleanup();}
});
test("regular roster lineup roundtrip honors assigned dual positions and rejects illegal destinations",async({page},info)=>{
 const f=await positionFixture(page.request);try{
  const lineup={...f.lineup,[String(f.players[0]._id)]:{section:"forward",slot:"C"},[String(f.players[1]._id)]:{section:"forward",slot:"LW"}};
  const saved=await page.request.post(`/api/teams/${f.team._id}/lineup`,{data:{lineup}});expect(saved.ok(),await saved.text()).toBeTruthy();
  const roster=await(await page.request.get(`/api/roster/${f.team._id}/detail`)).json();
  const left=roster.players.find((p:{id:string})=>p.id===String(f.players[0]._id));expect(left.eligiblePositions).toEqual(expect.arrayContaining(["LW","C"]));expect(left.rosterSlotId).toBe("C1");expect(left.rosterSection).toBe("starting");expect(roster.salary_used).toBe(9_000_000);
  const before=await f.snapshot();
  for(const illegal of [{...lineup,[String(f.players[1]._id)]:{section:"forward",slot:"C"}},{...lineup,[String(f.players[2]._id)]:{section:"forward",slot:"LW"}}]){
   expect((await page.request.post(`/api/teams/${f.team._id}/lineup`,{data:{lineup:illegal}})).status()).toBe(400);expect(await f.snapshot()).toEqual(before);
  }
  const totals=await(await page.request.get(`/api/drafts/${f.draft.id}/roster-status`)).json();const team=totals.teams.find((t:{team_id:string})=>t.team_id===String(f.team._id));expect(team.positions.C.filled).toBe(1);expect(team.positions.LW.filled).toBe(1);expect(team.salary_used).toBe(9_000_000);
  await info.attach("regular-roster-roundtrip",{body:JSON.stringify(roster),contentType:"application/json"});
 }finally{await f.cleanup();}
});

test("regular roster UI dual-position swap saves selected slots and survives reload",async({page},info)=>{
 const f=await positionFixture(page.request);try{
  const roster=new DynamicRosterPage(page);await roster.open(f.league.id,String(f.team._id));
  const left=String(f.players[0]._id),centre=String(f.players[1]._id),right=String(f.players[2]._id);
  await expect(roster.assigned(left,"LW")).toBeVisible();await expect(roster.assigned(centre,"C")).toBeVisible();
  await roster.position(left,"LW");await roster.position(centre,"C");await expect(roster.assigned(left,"C")).toBeVisible();await expect(roster.assigned(centre,"LW")).toBeVisible();await roster.save();
  await expect.poll(async()=>{const state=await f.snapshot();return state!.lineup[left].slot;}).toBe("C");
  await page.reload();await expect(roster.assigned(left,"C")).toBeVisible();await expect(roster.assigned(centre,"LW")).toBeVisible();
  const before=await f.snapshot();await roster.position(right,"RW");await roster.position(left,"C");await expect(page.getByText("Swap denied",{exact:true})).toBeVisible();expect(await f.snapshot()).toEqual(before);
  const totals=await(await page.request.get(`/api/drafts/${f.draft.id}/roster-status`)).json();const team=totals.teams.find((t:{team_id:string})=>t.team_id===String(f.team._id));expect(team.positions.C.filled).toBe(1);expect(team.positions.LW.filled).toBe(1);expect(team.salary_used).toBe(9_000_000);expect(before!.roster).toHaveLength(3);
  await info.attach("ui-saved-lineup",{body:JSON.stringify(before),contentType:"application/json"});await page.screenshot({path:info.outputPath("roster-swap.png"),fullPage:true});
 }finally{await f.cleanup();}
});

test("regular roster positional rules also apply without an active or historical draft",async({page},info)=>{
 const f=await positionFixture(page.request);try{
  await f.outsideDraft();
  const lineup={...f.lineup,[String(f.players[0]._id)]:{section:"forward",slot:"C"},[String(f.players[1]._id)]:{section:"forward",slot:"LW"}};
  const saved=await page.request.post(`/api/teams/${f.team._id}/lineup`,{data:{lineup}});expect(saved.ok(),await saved.text()).toBeTruthy();const before=await f.snapshot();
  for(const illegal of [{...lineup,[String(f.players[1]._id)]:{section:"forward",slot:"C"}},{...lineup,[String(f.players[2]._id)]:{section:"forward",slot:"LW"}}]){expect((await page.request.post(`/api/teams/${f.team._id}/lineup`,{data:{lineup:illegal}})).status()).toBe(400);expect(await f.snapshot()).toEqual(before);}
  const detail=await(await page.request.get(`/api/roster/${f.team._id}/detail`)).json();expect(detail.players.find((p:{id:string})=>p.id===String(f.players[0]._id)).rosterSlotId).toBe("C1");expect(detail.salary_used).toBe(9_000_000);
  await info.attach("outside-draft-lineup",{body:JSON.stringify(before),contentType:"application/json"});
 }finally{await f.cleanup();}
});
