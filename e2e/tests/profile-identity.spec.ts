import { test, expect } from '@playwright/test';
import { ObjectId } from 'mongodb';
import { login, database, result } from '../support/h2h';
import { user, seed, snapshots } from '../support/profile';
import { ProfilePage } from '../pages/profile/profile.page';

test('real administrative merge preserves both earned awards and manual transfer credits future owners',async({request,page})=>{
 await login(request);
 const [a,b,c]=await Promise.all([user(),user(),user()]);
 try {
  const t=await seed(a.id,{co_owner_ids:[b.id],wins:1,championship_won_at:'2026-10-08'});
  const before=(await snapshots(a)).private.xp_total+(await snapshots(b)).private.xp_total;
  await result(await request.post(`/api/admin/platform/users/${b.id}/merge-accounts`,{data:{source_user_id:a.id,reason:'Identity acceptance'}}));
  const merged=await snapshots(b);
  expect(merged.private.xp_total).toBe(before);
  expect(merged.public.xp_total).toBe(before);
  await page.goto(`/u/${b.username}`);
  await expect(new ProfilePage(page).ui.root).toBeVisible();
  await expect(new ProfilePage(page).ui.earnedChampionships).toHaveCount(2);
  await result(await request.post(`/api/admin/teams/${t.tid}/ownership`,{data:{owner_id:c.id,co_owner_ids:[],reason:'Identity transfer acceptance'}}));
  await database(db=>db.collection('teams').updateOne({_id:new ObjectId(t.tid)},{$set:{division_winner_at:'2026-10-09'}}));
  expect((await snapshots(b)).private.xp_total).toBe(before);
  expect((await snapshots(c)).private.xp_total).toBe(200);
  const repeated=await result(await request.post(`/api/admin/platform/users/${b.id}/merge-accounts`,{data:{source_user_id:a.id}}));
  expect(repeated.already_merged).toBe(true);
  expect((await snapshots(b)).private.xp_total).toBe(before);
 } finally {await Promise.all([a,b,c].map(p=>p.api.dispose()));}
});
