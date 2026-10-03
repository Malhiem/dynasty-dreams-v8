import type { APIRequestContext } from "@playwright/test";
import { MongoClient, ObjectId } from "mongodb";

export async function salaryFixture(request: APIRequestContext, ir = false) {
  if (process.env.E2E_BASE_URL !== "http://web") throw new Error("Disposable Compose only");
  const response = await request.post("/api/leagues", {data: {name:`Salary draft ${crypto.randomUUID()}`, sport:"nhl", format:"dynasty", scoring_format:"head_to_head", max_teams:4, roster_spots: 20}});
  if (!response.ok()) throw new Error(await response.text());
  const league = await response.json();
  const client = new MongoClient("mongodb://mongo:27017");
  const db = client.db("dynasty_dreams_e2e");
  const existing = {_id:new ObjectId(), name:"Existing salary", position:"RW", salary: ir ? 58_000_000 : 46_000_000};
  const candidates = (ir ? [1,4] : [2,4,6,8,10,19]).map(n => ({_id:new ObjectId(),name:`Candidate ${n}M`, position:"RW",salary:n*1_000_000,status: ir && n===4 ? "IR" : "healthy"}));
  const teams = ["ALP","BET","GAM","DEL"].map((abbr,i) => ({_id:new ObjectId(),league_id:league.id,name:`Salary ${abbr}`,logo_abbr_override:abbr,owner_id:league.commissioner_id,roster:i===0?[String(existing._id)]:[],lineup:i===0?{[String(existing._id)]:{section:"forward",slot:"ACT"}}:{}}));
  try {
    await db.collection("teams").deleteMany({league_id:league.id}); await db.collection("teams").insertMany(teams);
    await db.collection("players").insertMany([existing,...candidates]);
    await db.collection("leagues").updateOne({_id:new ObjectId(league.id)},{$set:{current_teams:4,setup_wizard_complete:true,roster_spots:ir?2:3,bench_spots:0,minors_spots:0,ir_slots:1}});
    const settings = await request.put(`/api/leagues/${league.id}/admin/cap-settings`,{data:{salary_cap_enabled:true,salary_cap:ir?60_000_000:64_000_000,cap_floor_enabled:!ir,cap_floor:ir?0:60_000_000,salary_adherence_mode:"strict",draft_roster_target:ir?2:3,ir_salary_charge_pct:0}});
    if (!settings.ok()) throw new Error(await settings.text());
    const created = await request.post("/api/drafts",{data:{league_id:league.id,name:"Salary feasibility",total_rounds:5,time_per_pick:3600,pick_trading_enabled:true,trading_window_opens:"immediately",player_criteria:["all"]}});
    if(!created.ok()) throw new Error(await created.text());
    const draft = await created.json(); draft.id=draft.id||draft._id;
    const start = await request.post(`/api/drafts/${draft.id}/start`,{data:{early_start:true}});
    if(!start.ok()) throw new Error(await start.text());
    return {league,draft,teams,candidates,existing, async restrictToMinorEligible(){await db.collection("players").updateMany({_id:{$in:candidates.map(p=>p._id)}},{$set:{minor_eligible:true}});await db.collection("drafts").updateOne({_id:new ObjectId(draft.id)},{$set:{minors_eligibility_required:true}});}, async assignMember(userId:string){await db.collection("teams").updateOne({_id:teams[1]._id},{$set:{owner_id:userId}});}, async notificationCount(){return db.collection("notifications").countDocuments({league_id:league.id,type:"draft_salary"});}, async setQueue(ids:string[]){await db.collection("teams").updateOne({_id:teams[0]._id},{$set:{draft_queue:ids}});}, async cleanup(){await db.collection("players").deleteMany({_id:{$in:[existing._id,...candidates.map(p=>p._id)]}});await client.close();}};
  } catch(e){await db.collection("players").deleteMany({_id:{$in:[existing._id,...candidates.map(p=>p._id)]}});await client.close();throw e;}
}
