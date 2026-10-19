import {test,expect} from '@playwright/test';
import {actors,dispose,league} from '../support/access-history';
import {database,result} from '../support/h2h';
import {LeagueExitPage} from '../pages/league-exit/league-exit.page';
test('mobile exit cancellation preserves membership and a lost committed response exits once',async({page,context})=>{
 const a=await actors();try{
  const l=await league(a);await context.addCookies((await a.commissioner.api.storageState()).cookies);await page.goto('/dashboard');
  const ui=new LeagueExitPage(page,l.id);await ui.open();await expect(ui.controls.dialog()).toContainText('without approval');await ui.cancel();await expect(ui.controls.dialog()).toBeHidden();expect((await a.commissioner.api.get(`/api/leagues/${l.id}`)).status()).toBe(200);
  let attempts=0;await page.route(`**/api/leagues/${l.id}/leave`,async route=>{attempts++;if(attempts===1){const committed=await route.fetch();expect(committed.ok()).toBe(true);await route.abort('failed');}else await route.continue();});
  await ui.open();await ui.confirm();await expect(ui.controls.row()).toBeHidden();await expect.poll(()=>page.url()).toMatch(/dashboard/);expect(attempts).toBe(2);
  expect((await a.commissioner.api.get(`/api/leagues/${l.id}`)).status()).toBe(403);await database(async db=>expect(await db.collection('league_membership_events').countDocuments({league_id:l.id,user_id:a.commissioner.id})).toBe(1));
 }finally{await dispose(a);}
});
