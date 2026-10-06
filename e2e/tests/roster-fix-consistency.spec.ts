import {test,expect} from "@playwright/test";
import {RosterPage} from "../pages/roster-gaps/roster-gaps.page";
import {rosterFixture} from "../support/roster-gaps";

test("full roster precheck includes reserved players in total capacity",async({page})=>{
  const f=await rosterFixture(page);
  try {
    const pid=String(f.players[0]._id);
    await f.config({ir_slots:1,roster_spots:3});
    await f.updateTeam({lineup:{...f.lineup,[pid]:{section:"ir",slot:"IR"}}});
    const response=await page.request.get(`/api/waivers/precheck?league_id=${f.league.id}&player_id=${pid}`);
    expect(response.ok()).toBeTruthy();
    const precheck=await response.json();
    expect(precheck.roster).toMatchObject({current:3,max:3,has_room:false,ir_count:1});
  } finally {await f.cleanup();}
});

test("rejected locked save preserves emergency budget and lineup",async({page})=>{
  const f=await rosterFixture(page);
  try {
    await f.config({lineup_lock_minutes_before:1440,emergency_changes_enabled:true,emergency_changes_regular:2,emergency_eligibility:["any"]});
    const before=await f.snapshot();
    const response=await page.request.post(`/api/teams/${f.team._id}/lineup`,{data:{lineup:{...f.lineup,"000000000000000000000000":{section:"bench",slot:"BN"}}}});
    expect(response.status()).toBe(409);
    expect(await f.snapshot()).toEqual(before);
  } finally {await f.cleanup();}
});

test("legacy generic active assignments remain visible",async({page})=>{const f=await rosterFixture(page),r=new RosterPage(page);try{await f.config({position_breakdown:{active:{}},position_limits:{}});await f.updateTeam({lineup:Object.fromEntries(f.players.map(p=>[String(p._id),{section:"forward",slot:"ACT"}]))});await r.open(f.league.id,String(f.team._id));for(const p of f.players)await expect(r.ui.row(String(p._id))).toBeVisible();}finally{await f.cleanup();}});

test("in-flight refresh preserves pending edits after remote membership change",async({page})=>{
 const f=await rosterFixture(page),r=new RosterPage(page),a=String(f.players[0]._id),b=String(f.players[1]._id),c=String(f.players[2]._id);
 let release!:()=>void,capture!:()=>void;
 const held=new Promise<void>(resolve=>{release=resolve;}),started=new Promise<void>(resolve=>{capture=resolve;});
 try {
  await r.open(f.league.id,String(f.team._id));await expect(r.ui.row(a)).toBeVisible();
  await page.route(`**/api/roster/${f.team._id}/detail`,async route=>{capture();await held;await route.continue();});
  await started;await r.swap(a,b);
  const drop=await page.request.post(`/api/roster/${f.team._id}/drop`,{data:{player_id:c}});expect(drop.ok()).toBeTruthy();
  const refresh=page.waitForResponse(response=>response.url().includes(`/roster/${f.team._id}/detail`));release();await refresh;
  const saved=page.waitForResponse(response=>response.url().includes(`/teams/${f.team._id}/lineup`)&&response.request().method()==="POST");
  await r.save();expect((await saved).status()).toBe(409);await expect(r.ui.row(a).getByRole("button",{name:"C",exact:true})).toBeVisible();await expect(r.ui.save()).toHaveCount(1);await expect(r.ui.save()).toBeVisible();
 }finally{release();await page.unrouteAll();await f.cleanup();}
});
