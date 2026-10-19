import {test,expect} from '@playwright/test';
import {actors,dispose} from '../support/access-history';
import {fixture} from '../support/h2h';
import {controlledWorker,legacyPrivateCache,readFromPage,purgePrivateCache,privateCacheNames,staleHtml} from '../support/mobile-worker';

test.skip(process.env.MOBILE_WORKER_BROWSER_ISOLATED!=='1','Requires the isolated secure-origin Chromium worker harness');

test('controlled service worker never returns a previous account private cache',async({page,context},info)=>{
 const a=await actors();
 try{
  const league=await fixture(a.commissioner.api,'h2h-points');await context.addCookies((await a.commissioner.api.storageState()).cookies.map(cookie=>({...cookie,domain:"localhost"})));
  await page.goto('/dashboard');expect(await controlledWorker(page)).toBe(true);
  const path=`/api/teams/${league.teams[0].id}`;const authorized=await readFromPage(page,path);expect(authorized.status).toBe(200);
  await legacyPrivateCache(page,path);
  await context.clearCookies();await context.addCookies((await a.outsider.api.storageState()).cookies.map(cookie=>({...cookie,domain:"localhost"})));
  const denied=await readFromPage(page,path);expect(denied.status).toBe(403);expect(denied.body).not.toContain('previous-account-data');
  await purgePrivateCache(page);await expect.poll(()=>privateCacheNames(page)).toEqual([]);
  await info.attach('worker-account-boundary',{body:JSON.stringify({authorized:authorized.status,outsider:denied.status,legacy_private_caches:await privateCacheNames(page)}),contentType:'application/json'});
 }finally{await dispose(a);}
});

test('controlled service worker refreshes HTML and never substitutes it for missing offline JavaScript',async({page,context},info)=>{
 const a=await actors();
 try{
  await context.addCookies((await a.commissioner.api.storageState()).cookies.map(cookie=>({...cookie,domain:"localhost"})));await page.goto('/dashboard');expect(await controlledWorker(page)).toBe(true);
  const title=await page.title();await staleHtml(page);await page.goto('/');await expect(page).toHaveTitle(title);expect(await page.title()).not.toBe('stale cached build');
  await context.setOffline(true);
  const missing=await readFromPage(page,`/static/js/not-a-build-chunk-${crypto.randomUUID()}.js`);expect(missing.status).toBe(504);expect(missing.type).not.toContain('html');expect(missing.body).not.toContain('<html');
  await context.setOffline(false);await page.reload();await expect(page).toHaveTitle(title);
  await info.attach('worker-version-recovery',{body:JSON.stringify({fresh_title:title,missing_asset_status:missing.status,missing_asset_type:missing.type}),contentType:'application/json'});
 }finally{await context.setOffline(false);await dispose(a);}
});
