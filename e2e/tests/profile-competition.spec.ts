import { test, expect } from '@playwright/test';
import { ObjectId } from 'mongodb';
import { database, fixture, generate, simulate, result } from '../support/h2h';
import { user, snapshots } from '../support/profile';
import { ProfilePage } from '../pages/profile/profile.page';

test('pre-match highest co-owner XP reduces actual win and championship equally', async({page},info)=>{
 const people=await Promise.all(Array.from({length:5},()=>user()));
 const [owner,co,...others]=people;
 try {
  const l=await fixture(owner.api,'h2h-points',false,4);
  await database(async db=>{
   for(const [i,t] of l.teams.entries()) await db.collection('teams').updateOne({_id:new ObjectId(t.id)},{$set:{owner_id:i===0?owner.id:others[i-1].id,co_owner_ids:i===0?[co.id]:[]}});
   await db.collection('trades').insertMany(Array.from({length:16},()=>({status:'executed',xp_user_ids:[co.id]})));
  });
  await generate(owner.api,l,info);
  await database(async db=>{
   const m=await db.collection('matchups').findOne({league_id:l.id,week:1,$or:[{home_team_id:l.teams[0].id},{away_team_id:l.teams[0].id}]});
   await db.collection('matchups').updateOne({_id:m!._id},{$set:{is_final:true,is_playoff:true,bracket:'championship'}});
  });
  const before=await snapshots(owner),coBefore=await snapshots(co);
  await simulate(owner.api,l,1,info);
  const after=await snapshots(owner),coAfter=await snapshots(co);
  expect(after.private.xp_total-before.private.xp_total).toBe(260);
  expect(coAfter.private.xp_total-coBefore.private.xp_total).toBe(260);
  expect(after.public.xp_total).toBe(after.private.xp_total);
  const trophy=after.public.trophies.find((t:any)=>t.type==='championship');
  expect(trophy.xp_award).toMatchObject({base_xp:500,multiplier:.5,awarded_xp:250,reason:'League XP imbalance'});
  const m=await database(db=>db.collection('matchups').findOne({league_id:l.id,week:1,is_final:true}));
  expect(m!.xp_competition.team_scores[l.teams[0].id]).toBe(450);
  expect(m!.xp_win_award).toMatchObject({base_xp:20,multiplier:.5,awarded_xp:10});
  await page.goto(`/u/${owner.username}`);
  await expect(new ProfilePage(page).ui.root).toBeVisible();
  await expect(new ProfilePage(page).ui.championshipXp).toBeVisible();
  const retry=await owner.api.post('/api/matchups/simulate-week',{data:{league_id:l.id,week:1}});
  expect(retry.status()).toBe(400);
  expect((await snapshots(owner)).private.xp_total).toBe(after.private.xp_total);
  await result(await owner.api.get('/api/users/me/level'));
 } finally {await Promise.all(people.map(p=>p.api.dispose()));}
});
