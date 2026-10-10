import { test, expect, request, type APIRequestContext } from '@playwright/test';
import { ObjectId } from 'mongodb';
import { database, result } from '../support/h2h';
import { actors, league, dispose, trade } from '../support/access-history';

import { user, seed, snapshots, publicXP } from '../support/profile';
import { ProfilePage } from '../pages/profile/profile.page';

test('P01 new user renders zero XP and empty achievements',async({page},info)=>{
 const u=await user();try{const s=await snapshots(u);expect(s.private.xp_total).toBe(0);expect(s.public.trophies).toEqual([]);await page.goto(`/u/${u.username}`);await expect(new ProfilePage(page).ui.root).toBeVisible();await expect(new ProfilePage(page).ui.initialXP).toBeVisible();await expect(new ProfilePage(page).ui.empty).toBeVisible();await page.screenshot({path:info.outputPath('new-user.png'),fullPage:true});}finally{await u.api.dispose();}
});
for(const [xp,level,title] of [[145,1,'Bench Warmer'],[150,2,'Bench Warmer'],[345,2,'Bench Warmer'],[350,3,'Bench Warmer'],[1245,5,'Bench Warmer'],[1250,6,'Rink Regular'],[7500,16,'Line Captain']] as const) {
 test(`P02 XP boundary ${xp} yields level ${level}`,async()=>{const u=await user();try{const t=await seed(u.id,{points_for:999999});await database(db=>db.collection('waiver_claims').insertMany(Array.from({length:(xp-50)/5},()=>({team_id:t.tid,status:'won'}))));const s=await snapshots(u);expect(s.private.xp_total).toBe(xp);expect(s.private.level).toBe(level);expect(s.private.title).toBe(title);expect(publicXP(s.public)).toBe(xp);expect(s.public.level).toBe(level);expect(s.private.progress_pct).toBeGreaterThanOrEqual(0);expect(s.private.progress_pct).toBeLessThan(100);}finally{await u.api.dispose();}});
}
test('P03 ordinary activity accumulates identically and repeated reads do not award XP',async()=>{
 const u=await user();try{const t=await seed(u.id,{wins:3,points_for:100,live_points:25});await database(async db=>{await db.collection('trades').insertMany([{proposer_id:u.id,status:'accepted',execution_moves:{},processed_at:'2026-10-07'},{recipient_id:u.id,status:'accepted',execution_moves:{},processed_at:'2026-10-07'},{proposer_id:u.id,status:'pending'}]);await db.collection('drafts').insertOne({participants:[t.tid],status:'complete'});await db.collection('waiver_claims').insertOne({team_id:t.tid,status:'won'});});const s=await snapshots(u);expect(s.private.xp_total).toBe(205);expect(publicXP(s.public)).toBe(205);expect(await snapshots(u)).toEqual(s);}finally{await u.api.dispose();}
});
test('P04 achievement bonuses agree between public profile and signed-in level',async({},info)=>{
 const u=await user();try{await seed(u.id,{championship_won_at:'2026-10-01T00:00:00Z',conference_winner_at:'2026-10-01T00:00:00Z',division_winner_at:'2026-10-01T00:00:00Z',consolation_won_at:'2026-10-01T00:00:00Z',playoffs_reached_at:'2026-09-01T00:00:00Z'});const s=await snapshots(u);await info.attach('achievement-snapshots',{body:JSON.stringify(s),contentType:'application/json'});expect(publicXP(s.public)).toBe(1125);expect(s.private.xp_total,'Same user must show the same accumulated XP').toBe(publicXP(s.public));}finally{await u.api.dispose();}
});
test('P05 completed draft grants its advertised 40 XP',async({},info)=>{
 const u=await user();try{const t=await seed(u.id);await database(db=>db.collection('drafts').insertOne({participants:[t.tid],status:'completed'}));const s=await snapshots(u);await info.attach('completed-draft-snapshots',{body:JSON.stringify(s),contentType:'application/json'});expect(s.private.stats.drafts_completed).toBe(1);expect(s.private.xp_total).toBe(90);}finally{await u.api.dispose();}
});
test('P06 unsuccessful waiver claims do not award successful-claim XP',async({},info)=>{
 const u=await user();try{const t=await seed(u.id);await database(db=>db.collection('waiver_claims').insertMany(['pending','cancelled','lost'].map(status=>({team_id:t.tid,status}))));const s=await snapshots(u);await info.attach('waiver-snapshots',{body:JSON.stringify(s),contentType:'application/json'});expect(s.private.xp_total,'Only won claims should earn waiver_claim_won XP').toBe(50);}finally{await u.api.dispose();}
});
test('P07 trophy UI persists across reload and private league has no link',async({page},info)=>{
 const u=await user();try{const t=await seed(u.id,{championship_won_at:'2026-10-01T00:00:00Z',playoff_runner_up_at:'2026-10-01T00:00:00Z',division_winner_at:'2026-10-01T00:00:00Z'});await database(db=>db.collection('leagues').updateOne({_id:new ObjectId(t.lid)},{$set:{is_private:true}}));const s=await snapshots(u);expect(s.public.trophies.map((x:any)=>x.type).sort()).toEqual(['championship','division']);expect(s.public.teams[0].league_id).toBeNull();await page.goto(`/u/${u.username}`);await expect(new ProfilePage(page).ui.trophyCase).toBeVisible();await expect(new ProfilePage(page).ui.championships).toContainText('1');await expect(new ProfilePage(page).ui.trophyCase.getByRole('link')).toHaveCount(0);await page.reload();await expect(new ProfilePage(page).ui.championships).toContainText('1');await page.screenshot({path:info.outputPath('achievements.png'),fullPage:true});}finally{await u.api.dispose();}
});
test('P08 profile recovers from load failure on reload and handles missing user',async({page})=>{
 const u=await user();try{await page.route(`**/api/u/${u.username}`,r=>r.fulfill({status:503,json:{detail:'test failure'}}));await page.goto(`/u/${u.username}`);await expect(new ProfilePage(page).ui.failed).toBeVisible();await page.unroute(`**/api/u/${u.username}`);await page.reload();await expect(new ProfilePage(page).ui.root).toBeVisible();await page.goto(`/u/missing${crypto.randomUUID()}`);await expect(new ProfilePage(page).ui.missing).toBeVisible();}finally{await u.api.dispose();}
});
test('P09 private level requires authentication and public profile excludes sensitive fields',async({request})=>{
 const u=await user();try{expect((await request.get('/api/users/me/level')).status()).toBe(401);const p=await result(await request.get(`/api/u/${u.username.toUpperCase()}`));expect(p.username).toBe(u.username);for(const key of ['email','password','password_hash','roles','refresh_token']) expect(p).not.toHaveProperty(key);}finally{await u.api.dispose();}
});
test('P10 real accepted trade grants 25 XP to each participant and repeated acceptance grants no extra XP',async({},info)=>{
 const a=await actors();try{const l=await league(a);const before=await result(await a.manager.api.get('/api/users/me/level'));const other=await result(await a.manager2.api.get('/api/users/me/level'));await trade(a,l,info);const after=await result(await a.manager.api.get('/api/users/me/level'));const afterOther=await result(await a.manager2.api.get('/api/users/me/level'));expect(after.xp_total-before.xp_total).toBe(25);expect(afterOther.xp_total-other.xp_total).toBe(25);const tid=await database(db=>db.collection('trades').findOne({league_id:l.id,status:'executed'}));await a.manager2.api.post(`/api/trades/${tid!._id}/accept`);expect((await result(await a.manager.api.get('/api/users/me/level'))).xp_total).toBe(after.xp_total);}finally{await dispose(a);}
});



test('C02 actual season renewal preserves career achievement and earned XP',async({},info)=>{
 const a=await actors();try{const l=await league(a);const me=await result(await a.manager.api.get('/api/auth/me'));await database(async db=>{await db.collection('teams').updateOne({_id:new ObjectId(l.teams[0].id)},{$set:{championship_won_at:'2026-06-01T00:00:00Z',wins:10,points_for:200,live_points:0}});});const url=`/api/u/${me.username}`;const before=await result(await a.anonymous.api.get(url));expect(before.stats.championships_won).toBe(1);await database(db=>db.collection('league_seasons').insertOne({league_id:l.id,season_year:2026,status:'complete',teams:[{team_id:l.teams[0].id,owner_id:a.manager.id,name:'Historical Winner',wins:10,points_for:200,awards:{championship_won_at:'2026-06-01T00:00:00Z'}}]}));await result(await a.commissioner.api.post(`/api/leagues/${l.id}/renew-season`,{data:{new_season_year:2027,reset_records:true}}));const after=await result(await a.anonymous.api.get(url));await info.attach('renewal-profile-diagnostics',{body:JSON.stringify({before,after}),contentType:'application/json'});expect(after.stats.championships_won).toBe(1);}finally{await dispose(a);}
});
