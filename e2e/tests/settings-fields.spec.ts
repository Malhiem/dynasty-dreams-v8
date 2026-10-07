import {test,expect,type Page} from '@playwright/test';
import {actors,dispose,league,type Actors} from '../support/access-history';
import {result} from '../support/h2h';
let a:Actors;test.beforeAll(async()=>{a=await actors();});test.afterAll(async()=>{if(a)await dispose(a);});
async function open(p:Page,id:string,tab:string){await p.context().addCookies((await a.commissioner.api.storageState()).cookies);await p.addInitScript(id=>localStorage.setItem('dd_active_league_id',id),id);await p.goto(`/commissioner/settings?tab=${tab}`);}
test('F01 roster numeric settings save and reload together',async({page})=>{
 const l=await league(a);await open(page,l.id,'rosters');
 const fields=[['bench-spots',5],['ir-slots',0],['ir-plus-slots',0],['minors-spots',8],['taxi-squad',2],['min-active',0],['min-games',0],['prospect-max-age',24],['prospect-max-games',80]] as const;
 for(const [name,value] of fields){const suffix=name.startsWith('prospect')?'':'-input';await page.getByTestId(`rosters-${name}${suffix}`).fill(String(value));}
 const saved=page.waitForResponse(r=>r.request().method()==='PUT'&&new URL(r.url()).pathname===`/api/leagues/${l.id}`);await page.getByTestId('rosters-save-btn').click();expect((await saved).ok()).toBe(true);
 await page.reload();for(const [name,value] of fields){const suffix=name.startsWith('prospect')?'':'-input';await expect(page.getByTestId(`rosters-${name}${suffix}`)).toHaveValue(String(value));}
 const s=await result(await a.commissioner.api.get(`/api/leagues/${l.id}`));expect(s.ir_slots).toBe(0);expect(s.bench_spots).toBe(5);
});
test('F02 invalid roster count blocks entire save',async({page})=>{
 const l=await league(a);const before=await result(await a.commissioner.api.get(`/api/leagues/${l.id}`));await open(page,l.id,'rosters');
 await page.getByTestId('rosters-bench-spots-input').fill('21');await page.getByTestId('rosters-ir-slots-input').fill('0');await page.getByTestId('rosters-save-btn').click();
 await expect(page.getByText('bench spots must be between 0 and 20',{exact:true})).toBeVisible();const after=await result(await a.commissioner.api.get(`/api/leagues/${l.id}`));expect(after.bench_spots).toBe(before.bench_spots);expect(after.ir_slots).toBe(before.ir_slots);
});
test('F03 failed roster save preserves pending edits for retry',async({page})=>{
 const l=await league(a);await open(page,l.id,'rosters');await page.getByTestId('rosters-bench-spots-input').fill('6');
 await page.route(`**/api/leagues/${l.id}`,r=>r.request().method()==='PUT'?r.fulfill({status:503,json:{detail:'Roster settings unavailable'}}):r.continue());
 await page.getByTestId('rosters-save-btn').click();await expect(page.getByText('Roster settings unavailable',{exact:true})).toBeVisible();await expect(page.getByTestId('rosters-bench-spots-input')).toHaveValue('6');
 await page.unroute(`**/api/leagues/${l.id}`);await page.getByTestId('rosters-save-btn').click();await expect.poll(async()=>(await result(await a.commissioner.api.get(`/api/leagues/${l.id}`))).bench_spots).toBe(6);
});
test('F04 transaction load failure cannot offer default settings for overwrite',async({page},info)=>{
 const l=await league(a);await result(await a.commissioner.api.put(`/api/leagues/${l.id}/transactions-config`,{data:{claim_limits:{season:{total:12,fa:10,waivers:2},week:{total:3,fa:2,waivers:1}}}}));
 await page.route(`**/api/leagues/${l.id}/transactions-config`,r=>r.request().method()==='GET'?r.fulfill({status:503,json:{detail:'Transactions load unavailable'}}):r.continue());
 await open(page,l.id,'rules-schedule');const save=page.getByTestId('transactions-save-btn');await expect(page.getByRole('alert')).toContainText('Transactions load unavailable');
 await info.attach('failed-load-screen',{body:await page.screenshot(),contentType:'image/png'});
 await expect(save).toBeHidden();await page.unroute(`**/api/leagues/${l.id}/transactions-config`);await page.getByRole('button',{name:'Retry loading transactions'}).click();await expect(page.getByTestId('claims-season-total-input')).toHaveValue('12');
});
test('F05 claim-limit settings save reload and retain all six values',async({page})=>{
 const l=await league(a);await open(page,l.id,'rules-schedule');
 const fields=[['season-total',12],['season-fa',10],['season-waivers',2],['week-total',3],['week-fa',2],['week-waivers',1]] as const;
 for(const [name,value] of fields){await page.getByTestId(`claims-${name}-toggle`).check();await page.getByTestId(`claims-${name}-input`).fill(String(value));}
 const response=page.waitForResponse(r=>r.request().method()==='PUT'&&r.url().endsWith('/transactions-config'));await page.getByTestId('transactions-save-btn').click();expect((await response).ok()).toBe(true);
 await page.reload();for(const [name,value] of fields)await expect(page.getByTestId(`claims-${name}-input`)).toHaveValue(String(value));
});
