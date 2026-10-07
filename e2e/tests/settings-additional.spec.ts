import {test,expect} from '@playwright/test';
import {ObjectId} from 'mongodb';
import {actors,dispose,league,type Actors} from '../support/access-history';
import {database,result} from '../support/h2h';
import {PermissionPage} from '../pages/permission-ui/permission-ui.page';
let a:Actors;test.beforeAll(async()=>{a=await actors();});test.afterAll(async()=>{if(a)await dispose(a);});
test('A01 two different commissioners cannot both save the same scoring revision',async()=>{
 const l=await league(a);await database(db=>db.collection('leagues').updateOne({_id:new ObjectId(l.id)},{$set:{co_commissioners:[a.manager.id]}}));
 const c=await result(await a.commissioner.api.get(`/api/scoring/config?league_id=${l.id}`));
 const payload=(goals:number)=>({league_id:l.id,skater_scoring:{goals},goalie_scoring:{},roto_categories:['goals'],expected_revision:c.revision});
 const responses=await Promise.all([a.commissioner.api.post('/api/scoring/config',{data:payload(3)}),a.manager.api.post('/api/scoring/config',{data:payload(4)})]);
 expect(responses.map(r=>r.status()).sort()).toEqual([200,409]);const saved=await result(await a.commissioner.api.get(`/api/scoring/config?league_id=${l.id}`));expect([3,4]).toContain(saved.skater_scoring.goals);expect(saved.revision).toBe(c.revision+1);
});
test('A02 legacy API save advances revision and prevents stale browser write',async()=>{
 const l=await league(a);const c=await result(await a.commissioner.api.get(`/api/scoring/config?league_id=${l.id}`));
 await result(await a.commissioner.api.post('/api/scoring/config',{data:{league_id:l.id,skater_scoring:{goals:8},goalie_scoring:{},roto_categories:['goals']}}));
 const r=await a.commissioner.api.post('/api/scoring/config',{data:{league_id:l.id,skater_scoring:{goals:9},goalie_scoring:{},expected_revision:c.revision}});expect(r.status()).toBe(409);
 expect((await result(await a.commissioner.api.get(`/api/scoring/config?league_id=${l.id}`))).skater_scoring.goals).toBe(8);
});
test('A03 every player-pool setting saves and reloads; failed save preserves draft',async({page})=>{
 const l=await league(a);await page.context().addCookies((await a.commissioner.api.storageState()).cookies);await page.addInitScript(id=>localStorage.setItem('dd_active_league_id',id),l.id);await page.goto('/commissioner/settings?tab=player-pool');
 const pane=page.getByTestId('commissioner-player-pool-tab');await expect(pane).toBeVisible();
 const lock=pane.getByRole('checkbox',{name:'Lock Player Pool',exact:true});
 await page.getByTestId('pool-select-all').uncheck();await page.getByTestId('pool-team-TBL').check();
 await lock.check();await pane.getByRole('checkbox',{name:'Include Drafted Minor League Players',exact:true}).uncheck();await pane.getByRole('checkbox',{name:'Include Non-Signed Players',exact:true}).check();
 await page.getByTestId('player-pool-duplicate-select').click();await page.getByRole('option',{name:'Across Different Divisions',exact:true}).click();
 await page.route(`**/api/leagues/${l.id}`,r=>r.request().method()==='PUT'?r.fulfill({status:503,json:{detail:'Pool save unavailable'}}):r.continue());await page.getByTestId('player-pool-save').click();await expect(page.getByRole('alert')).toContainText('Pool save unavailable');await expect(lock).toBeChecked();
 await page.unroute(`**/api/leagues/${l.id}`);const response=page.waitForResponse(r=>r.request().method()==='PUT'&&r.url().endsWith(`/leagues/${l.id}`));await page.getByTestId('player-pool-save').click();expect((await response).ok()).toBe(true);
 const config=(await result(await a.commissioner.api.get(`/api/leagues/${l.id}`))).player_pool_config;expect(config).toMatchObject({include_entire_nhl:false,selection_mode:"custom",locked:true,include_minors:false,include_unsigned:true,duplicate_players:'across-divisions'});expect(config.teams).toHaveLength(1);
 await page.reload();await expect(page.getByTestId('pool-select-all')).not.toBeChecked();await expect(lock).toBeChecked();await expect(pane.getByRole('checkbox',{name:'Include Drafted Minor League Players',exact:true})).not.toBeChecked();await expect(pane.getByRole('checkbox',{name:'Include Non-Signed Players',exact:true})).toBeChecked();await expect(page.getByTestId('player-pool-duplicate-select')).toContainText('Across Different Divisions');
});
test('A04 explicit zero weight saves and disabled blank category does not block',async({page})=>{
 const l=await league(a);await page.context().addCookies((await a.commissioner.api.storageState()).cookies);const p=new PermissionPage(page);await p.goto(l.id);await expect(p.selectors.goals(page)).toHaveValue('1');await p.saveGoals('0');
 await expect.poll(async()=>(await result(await a.commissioner.api.get(`/api/scoring/config?league_id=${l.id}`))).skater_scoring.goals).toBe(0);await page.reload();await expect(p.selectors.goals(page)).toHaveValue('0');
 await p.selectors.goals(page).fill('');await p.selectors.category(page,'goals').uncheck();await p.selectors.save(page).click();await expect.poll(async()=>Object.hasOwn((await result(await a.commissioner.api.get(`/api/scoring/config?league_id=${l.id}`))).skater_scoring,'goals')).toBe(false);
});
for(const period of ['season','week'])test(`A05 all ${period} claim limits enforce bounds atomically`,async()=>{
 const l=await league(a);const maximum=period==='week'?100:600;
 for(const field of ['total','fa','waivers']){
  await result(await a.commissioner.api.put(`/api/leagues/${l.id}/transactions-config`,{data:{claim_limits:{[period]:{[field]:maximum}}}}));const before=await result(await a.commissioner.api.get(`/api/leagues/${l.id}/transactions-config`));
  const invalid=await a.commissioner.api.put(`/api/leagues/${l.id}/transactions-config`,{data:{claim_limits:{[period]:{[field]:maximum+1}},claim_rules:{prevent_minors:true}}});expect([400,422]).toContain(invalid.status());expect(await result(await a.commissioner.api.get(`/api/leagues/${l.id}/transactions-config`))).toEqual(before);
 }
 await result(await a.commissioner.api.put(`/api/leagues/${l.id}/transactions-config`,{data:{claim_limits:{[period]:{total:0,fa:null,waivers:null}}}}));const saved=await result(await a.commissioner.api.get(`/api/leagues/${l.id}/transactions-config`));expect(saved.claim_limits[period]).toEqual({total:0,fa:null,waivers:null});
});
test('A06 invalid prospect settings reject the whole league update',async()=>{
 const l=await league(a);const before=await database(db=>db.collection('leagues').findOne({_id:new ObjectId(l.id)}));for(const data of [{prospect_max_age:31,name:'Invalid age'},{prospect_max_career_games:501,name:'Invalid games'}]){const r=await a.commissioner.api.put(`/api/leagues/${l.id}`,{data});expect(r.status()).toBe(422);expect(await database(db=>db.collection('leagues').findOne({_id:new ObjectId(l.id)}))).toEqual(before);}
});
