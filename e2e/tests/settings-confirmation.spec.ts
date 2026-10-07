import {test,expect,type Page} from '@playwright/test';
import {ObjectId} from 'mongodb';
import {actors,dispose,league,type Actors} from '../support/access-history';
import {database,result} from '../support/h2h';
let a:Actors;test.beforeAll(async()=>{a=await actors();});test.afterAll(async()=>{if(a)await dispose(a);});
async function open(p:Page,id:string,tab:string){await p.context().addCookies((await a.commissioner.api.storageState()).cookies);await p.addInitScript(id=>localStorage.setItem('dd_active_league_id',id),id);await p.goto(`/commissioner/settings?tab=${tab}`);}
for(const [id,key,value] of [['prospect-max-age','prospect_max_age',23],['prospect-max-games','prospect_max_career_games',80]] as const)test(`C01 ${key} really persists in database after browser save`,async({page},info)=>{
 const l=await league(a);await open(page,l.id,'rosters');await page.getByTestId(`rosters-${id}`).fill(String(value));
 const saving=page.waitForResponse(r=>r.request().method()==='PUT'&&new URL(r.url()).pathname===`/api/leagues/${l.id}`);await page.getByTestId('rosters-save-btn').click();const r=await saving;
 const doc=await database(db=>db.collection('leagues').findOne({_id:new ObjectId(l.id)}));
 await info.attach('save-result',{body:JSON.stringify({status:r.status(),request:r.request().postDataJSON(),body:await r.json(),stored:doc?.[key]??null}),contentType:'application/json'});
 expect(r.ok()).toBe(true);expect(doc?.[key],`${key} sent by browser must be stored`).toBe(value);
});
test('C02 failed Transactions load must not replace configured values on save',async({page},info)=>{
 const l=await league(a);await result(await a.commissioner.api.put(`/api/leagues/${l.id}/transactions-config`,{data:{claim_limits:{season:{total:12,fa:10,waivers:2},week:{total:3,fa:2,waivers:1}}}}));
 await page.route(`**/api/leagues/${l.id}/transactions-config`,r=>r.request().method()==='GET'?r.fulfill({status:503,json:{detail:'Transactions load unavailable'}}):r.continue());await open(page,l.id,'rules-schedule');
 const save=page.getByTestId('transactions-save-btn');await expect(page.getByRole('alert')).toContainText('Transactions load unavailable');
 if(await save.count() && await save.isEnabled()){const response=page.waitForResponse(r=>r.request().method()==='PUT'&&r.url().endsWith('/transactions-config'));await save.click();await response;}
 const after=await result(await a.commissioner.api.get(`/api/leagues/${l.id}/transactions-config`));await info.attach('after-failed-load-save',{body:JSON.stringify(after),contentType:'application/json'});expect(after.claim_limits.season.total).toBe(12);
});
test('C03 claim input clamps above maximum and API rejects invalid payload atomically',async({page})=>{
 const l=await league(a);await open(page,l.id,'rules-schedule');await page.getByTestId('claims-week-total-toggle').check();await page.getByTestId('claims-week-total-input').fill('101');await expect(page.getByTestId('claims-week-total-input')).toHaveValue('100');
 const response=page.waitForResponse(r=>r.request().method()==='PUT'&&r.url().endsWith('/transactions-config'));await page.getByTestId('transactions-save-btn').click();expect((await response).ok()).toBe(true);
 const before=await result(await a.commissioner.api.get(`/api/leagues/${l.id}/transactions-config`));expect(before.claim_limits.week.total).toBe(100);
 const invalid=await a.commissioner.api.put(`/api/leagues/${l.id}/transactions-config`,{data:{claim_limits:{season:{total:12},week:{total:101}}}});expect([400,422]).toContain(invalid.status());
 expect((await result(await a.commissioner.api.get(`/api/leagues/${l.id}/transactions-config`))).claim_limits).toEqual(before.claim_limits);
});
for(const role of ['manager','outsider'] as const)test(`C04 ${role} cannot update league or generate schedules using explicit fixtures`,async()=>{
 const l=await league(a);const before=await database(db=>db.collection('leagues').findOne({_id:new ObjectId(l.id)}));
 for(const data of [{roster_spots:30},{trade_veto_threshold_pct:99}]){const r=await a[role].api.put(`/api/leagues/${l.id}`,{data});expect(r.status()).toBe(403);expect((await r.json()).detail.toLowerCase()).toContain('commissioner');}
 const r=await a[role].api.post('/api/matchups/generate-schedule',{data:{league_id:l.id,num_weeks:18}});expect(r.status()).toBe(403);expect((await r.json()).detail.toLowerCase()).toContain('commissioner');
 const after=await database(db=>db.collection('leagues').findOne({_id:new ObjectId(l.id)}));expect(after).toEqual(before);
 expect(await database(db=>db.collection('matchups').countDocuments({league_id:l.id}))).toBe(0);
});
