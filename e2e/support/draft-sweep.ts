import type { APIRequestContext } from '@playwright/test';
import {MongoClient,ObjectId} from 'mongodb';
export async function sweepDraft(api:APIRequestContext,snake:boolean,bonus=false){
 if(process.env.E2E_BASE_URL!=='http://web'||process.env.DRAFT_TEST_ISOLATED!=='1')throw Error('Disposable Compose required');
 const read=async(response:any)=>{if(!response.ok())throw Error(await response.text());return response.json();};
 const league=await read(await api.post('/api/leagues',{data:{name:`Sweep ${crypto.randomUUID()}`,sport:'nhl',format:'dynasty',scoring_format:'head_to_head',max_teams:4,roster_spots:20}}));
 const client=new MongoClient('mongodb://mongo:27017'),db=client.db('dynasty_dreams_e2e');
 const teams=['ALP','BET','GAM','DEL'].map(abbr=>({_id:new ObjectId(),league_id:league.id,owner_id:league.commissioner_id,name:`Sweep ${abbr}`,logo_abbr_override:abbr,roster:[],lineup:{}}));
 const players=Array.from({length:21},(_,i)=>({_id:new ObjectId(),name:`Sweep Player ${i} ${crypto.randomUUID()}`,position:'C',salary:2000000}));
 try{
  await db.collection('teams').deleteMany({league_id:league.id});await db.collection('teams').insertMany(teams);await db.collection('players').insertMany(players);
  await db.collection('leagues').updateOne({_id:new ObjectId(league.id)},{$set:{current_teams:4,setup_wizard_complete:true,salary_cap_enabled:false,cap_floor_enabled:false,position_breakdown:{active:{ACT:20}},draft_roster_target:20,roster_spots:20,bench_spots:0,minors_spots:0,ir_slots:0}});
  const draft=await read(await api.post('/api/drafts',{data:{league_id:league.id,name:'Complete sweep',total_rounds:5,time_per_pick:3600,draft_type:snake?'snake':'linear',snake_draft:snake,pick_trading_enabled:true,trading_window_opens:'immediately',player_criteria:['all']}}));draft.id=draft.id||draft._id;
  if(bonus)await read(await api.post(`/api/drafts/${draft.id}/bonus-picks`,{data:{team_id:String(teams[0]._id),bonus_kind:'compensation',position_mode:'overall',overall_position:3,tradeable:false}}));
  await read(await api.post(`/api/drafts/${draft.id}/start`,{data:{early_start:true}}));
  return {league,draft,teams,players,async snapshot(){return {draft:await db.collection('drafts').findOne({_id:new ObjectId(draft.id)}),teams:await db.collection('teams').find({league_id:league.id}).toArray()};},async cleanup(){await db.collection('players').deleteMany({_id:{$in:players.map(p=>p._id)}});await client.close();}};
 }catch(e){await db.collection('players').deleteMany({_id:{$in:players.map(p=>p._id)}});await client.close();throw e;}
}
