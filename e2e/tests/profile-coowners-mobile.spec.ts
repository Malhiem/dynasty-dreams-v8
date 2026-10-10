import {test,expect} from '@playwright/test';
import {actors,league,dispose,trade} from '../support/access-history';
import {database,result} from '../support/h2h';
import {user} from '../support/profile';
import {ProfilePage} from '../pages/profile/profile.page';

test('co-owner invitation grants equal future trade XP without retroactive rewards',async({},info)=>{
 const a=await actors();try{
  const l=await league(a);await trade(a,l,info);
  const invitation=await result(await a.commissioner.api.post(`/api/leagues/${l.id}/teams/${l.teams[0].id}/invites`,{data:{role:'co_owner',email:a.outsider.email}}));
  await result(await a.outsider.api.post(`/api/team-invites/${invitation.token}/accept`));
  const get=async(api:any)=>result(await api.get('/api/users/me/level'));
  expect((await get(a.outsider.api)).xp_total).toBe(50);
  expect((await get(a.manager.api)).xp_total).toBe(75);
  await trade(a,l,info,1,0);
  expect((await get(a.outsider.api)).xp_total).toBe(75);
  expect((await get(a.manager.api)).xp_total).toBe(100);
  const doc=await database(db=>db.collection('trades').findOne({league_id:l.id,status:'executed',proposer_id:a.manager2.id}));
  expect(doc!.xp_user_ids).toContain(a.outsider.id);
  expect(doc!.xp_user_ids.filter((id:string)=>id===a.outsider.id)).toHaveLength(1);
 }finally{await dispose(a);}
});

for(const width of [320,390,430]) test(`maximum username fits ${width}px and persists in a fresh session`,async({browser},info)=>{
 const u=await user();let context=await browser.newContext({viewport:{width,height:844}});try{
  const username='qa'+crypto.randomUUID().replaceAll('-','').slice(0,30);
  await result(await u.api.put('/api/users/me/profile',{data:{username}}));
  let page=await context.newPage(),profile=new ProfilePage(page);
  await profile.actions.open(username);await expect(profile.ui.root).toBeVisible();
  const layout=await page.evaluate(()=>({width:innerWidth,client:document.documentElement.clientWidth,scroll:document.documentElement.scrollWidth}));
  expect(layout.width).toBe(width);expect(layout.scroll).toBeLessThanOrEqual(layout.client);
  await page.screenshot({path:info.outputPath(`profile-${width}.png`),fullPage:true});
  await context.close();context=await browser.newContext({viewport:{width,height:844}});
  page=await context.newPage();profile=new ProfilePage(page);await profile.actions.open(username);
  await expect(profile.ui.initialXP).toBeVisible();
 }finally{await context.close();await u.api.dispose();}
});
