import type {APIRequestContext} from "@playwright/test";
import {MongoClient,ObjectId} from "mongodb";
export async function positionFixture(request:APIRequestContext){
 if(process.env.E2E_BASE_URL!=="http://web"||process.env.DRAFT_TEST_ISOLATED!=="1")throw new Error("Disposable draft Compose required");
 const response=await request.post("/api/leagues",{data:{name:`Position moves ${crypto.randomUUID()}`,sport:"nhl",format:"dynasty",scoring_format:"head_to_head",max_teams:4,roster_spots:20}});
 if(!response.ok())throw new Error(await response.text());const league=await response.json();
 const client=new MongoClient("mongodb://mongo:27017");const db=client.db("dynasty_dreams_e2e");
 const players=[{_id:new ObjectId(),name:"Dual Left",position:"LW",eligible_positions:["LW","C"],salary:4_000_000},{_id:new ObjectId(),name:"Dual Centre",position:"C",eligible_positions:["LW","C"],salary:4_000_000},{_id:new ObjectId(),name:"Right Only",position:"RW",eligible_positions:["RW"],salary:1_000_000}];
 const lineup=Object.fromEntries(players.map(p=>[String(p._id),{section:"forward",slot:p.position}]));
 const teams=["ALP","BET","GAM","DEL"].map((abbr,i)=>({_id:new ObjectId(),name:`Positions ${abbr}`,logo_abbr_override:abbr,league_id:league.id,owner_id:league.commissioner_id,roster:i===0?players.map(p=>String(p._id)):[],lineup:i===0?lineup:{}}));
 try{
  await db.collection("teams").deleteMany({league_id:league.id});await db.collection("teams").insertMany(teams);await db.collection("players").insertMany(players);
  await db.collection("leagues").updateOne({_id:new ObjectId(league.id)},{$set:{setup_wizard_complete:true,current_teams:4,roster_spots:3,position_breakdown:{active:{C:1,LW:1,RW:1}},bench_spots:2,ir_slots:0,minors_spots:0,salary_adherence_mode:"informal",draft_roster_target:3,salary_cap_enabled:false,cap_floor_enabled:false}});
  const created=await request.post("/api/drafts",{data:{league_id:league.id,name:"Dynamic positions",total_rounds:3,time_per_pick:3600,player_criteria:["all"]}});if(!created.ok())throw new Error(await created.text());const draft=await created.json();draft.id=draft.id||draft._id;
  const started=await request.post(`/api/drafts/${draft.id}/start`,{data:{early_start:true}});if(!started.ok())throw new Error(await started.text());
  return {league,draft,team:teams[0],players,lineup,async outsideDraft(){await db.collection("drafts").updateOne({_id:new ObjectId(draft.id)},{$set:{status:"cancelled"}});},async snapshot(){return db.collection("teams").findOne({_id:teams[0]._id});},async cleanup(){await db.collection("players").deleteMany({_id:{$in:players.map(p=>p._id)}});await client.close();}};
 }catch(e){await db.collection("players").deleteMany({_id:{$in:players.map(p=>p._id)}});await client.close();throw e;}
}
