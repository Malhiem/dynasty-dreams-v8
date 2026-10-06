import {expect,type Page} from "@playwright/test";
import {MongoClient,ObjectId} from "mongodb";
import {positionFixture} from "./dynamic-positions";
import {LoginPage} from "../pages/login/login.page";
export async function rosterFixture(page:Page){
 const email=`roster-${crypto.randomUUID()}@e2e.dynastydreams.com`,password="Roster-e2e-2026!";
 const reg=await page.request.post("/api/auth/register",{data:{email,password,username:`r${crypto.randomUUID().replaceAll("-","").slice(0,18)}`}});expect(reg.ok(),await reg.text()).toBeTruthy();
 const login=new LoginPage(page);await login.goto();await login.logIn({email,password});await expect(page).toHaveURL(/dashboard|team/);
 const f=await positionFixture(page.request);await f.outsideDraft();
 const client=new MongoClient("mongodb://mongo:27017"),db=client.db("dynasty_dreams_e2e");
 await db.collection("leagues").updateOne({_id:new ObjectId(f.league.id)},{$set:{allow_illegal_rosters:true,roster_lock_type:"daily",lineup_lock_minutes_before:0,waivers_enabled:false,commissioner_id:new ObjectId().toString(),owner_id:new ObjectId().toString(),admin_ids:[]}});
 return {...f,email,password,db,async config(fields:any){await db.collection("leagues").updateOne({_id:new ObjectId(f.league.id)},{$set:fields});},async updateTeam(fields:any){await db.collection("teams").updateOne({_id:f.team._id},{$set:fields});},async cleanup(){await f.cleanup();await client.close();}};
}
export async function actor(page:Page,email:string,password:string){const login=new LoginPage(page);await login.goto();await login.logIn({email,password});await expect(page).toHaveURL(/dashboard|team/);}
export async function register(page:Page){const email=`roster-other-${crypto.randomUUID()}@e2e.dynastydreams.com`,password="Roster-e2e-2026!";const r=await page.request.post("/api/auth/register",{data:{email,password,username:`r${crypto.randomUUID().replaceAll("-","").slice(0,18)}`}});expect(r.ok(),await r.text()).toBeTruthy();const me=await(await page.request.get("/api/auth/me")).json();return {email,password,id:me.id};}
