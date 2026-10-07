import {test,expect,type Page} from '@playwright/test';
import {ObjectId} from 'mongodb';
import {actors,dispose,league,type Actors} from '../support/access-history';
import {database,result} from '../support/h2h';
import {PermissionPage} from '../pages/permission-ui/permission-ui.page';
let a:Actors;
test.beforeAll(async()=>{a=await actors();});
test.afterAll(async()=>{if(a)await dispose(a);});
async function open(page:Page,id:string,actor=a.commissioner,tab='scoring'){
 await page.context().addCookies((await actor.api.storageState()).cookies);
 await page.addInitScript(id=>{if(!sessionStorage.getItem('settings-test-init')){localStorage.setItem('dd_active_league_id',id);sessionStorage.setItem('settings-test-init','1');}},id);
 await page.goto(`/commissioner/settings?tab=${tab}`);
 return new PermissionPage(page);
}
async function config(id:string,goals:number,assists=2){
 await result(await a.commissioner.api.post('/api/scoring/config',{data:{league_id:id,skater_scoring:{goals,assists},goalie_scoring:{},roto_categories:['goals']}}));
}
test('G01 scoring league switch discards prior league edits without cross-league writes',async({page})=>{
 const x=await league(a),y=await league(a);await config(x.id,3);await config(y.id,11);
 const p=await open(page,x.id);await expect(p.selectors.goals(page)).toHaveValue('3');await p.selectors.goals(page).fill('9');
 await page.evaluate(id=>localStorage.setItem('dd_active_league_id',id),y.id);
 await page.reload();await expect(p.selectors.goals(page)).toHaveValue('11');await p.saveGoals('12');
 await expect.poll(async()=>(await result(await a.commissioner.api.get(`/api/scoring/config?league_id=${y.id}`))).skater_scoring.goals).toBe(12);
 expect((await result(await a.commissioner.api.get(`/api/scoring/config?league_id=${x.id}`))).skater_scoring.goals).toBe(3);
});
test('G02 commissioner revocation while scoring is open denies save and preserves server rules',async({page})=>{
 const l=await league(a);const p=await open(page,l.id);await expect(p.selectors.goals(page)).toHaveValue('1');
 await database(db=>db.collection('leagues').updateOne({_id:new ObjectId(l.id)},{$set:{commissioner_id:a.manager.id,co_commissioners:[]}}));
 const response=page.waitForResponse(r=>r.request().method()==='POST'&&new URL(r.url()).pathname==='/api/scoring/config');
 await p.saveGoals('9');expect((await response).status()).toBe(403);await expect(page.getByRole('alert')).toBeVisible();
 expect((await result(await a.manager.api.get(`/api/scoring/config?league_id=${l.id}`))).skater_scoring.goals).toBe(1);
 await expect(p.selectors.goals(page)).toHaveValue('9');
});
test('G03 co-commissioner can save scoring via browser',async({page})=>{
 const l=await league(a);await database(db=>db.collection('leagues').updateOne({_id:new ObjectId(l.id)},{$set:{co_commissioners:[a.manager.id]}}));
 const p=await open(page,l.id,a.manager);await expect(p.selectors.goals(page)).toHaveValue('1');await p.saveGoals('4');
 await expect.poll(async()=>(await result(await a.manager.api.get(`/api/scoring/config?league_id=${l.id}`))).skater_scoring.goals).toBe(4);
});
test('G04 stale commissioner save protects another commissioner changes or reports conflict',async({page,context},info)=>{
 const l=await league(a);await config(l.id,1,2);const p=await open(page,l.id);
 const second=await context.newPage();await second.goto('/commissioner/settings?tab=scoring');const q=new PermissionPage(second);
 await expect(p.selectors.goals(page)).toHaveValue('1');await expect(q.selectors.goals(second)).toHaveValue('1');
 await q.selectors.category(second,'assists').check();await q.selectors.points(second,'assists').fill('8');await q.selectors.save(second).click();
 await expect.poll(async()=>(await result(await a.commissioner.api.get(`/api/scoring/config?league_id=${l.id}`))).skater_scoring.assists).toBe(8);
 const conflict=page.waitForResponse(r=>r.request().method()==='POST'&&new URL(r.url()).pathname==='/api/scoring/config');
 await p.saveGoals('7');expect((await conflict).status()).toBe(409);await expect(page.getByRole('alert')).toContainText('Scoring changed');await expect(p.selectors.goals(page)).toHaveValue('7');
 const s=await result(await a.commissioner.api.get(`/api/scoring/config?league_id=${l.id}`));expect(s.skater_scoring).toEqual({goals:1,assists:8});
 await page.getByRole('button',{name:'Reload saved scoring',exact:true}).click();await expect(p.selectors.goals(page)).toHaveValue('1');await p.saveGoals('7');
 await expect.poll(async()=>(await result(await a.commissioner.api.get(`/api/scoring/config?league_id=${l.id}`))).skater_scoring).toEqual({goals:7,assists:8});
});
test('G05 empty enabled scoring weight is rejected without overwriting saved value',async({page})=>{
 const l=await league(a);const p=await open(page,l.id);await expect(p.selectors.goals(page)).toHaveValue('1');
 await p.selectors.goals(page).fill('');await p.selectors.save(page).click();
 await expect(page.getByRole('alert')).toBeVisible();expect((await result(await a.commissioner.api.get(`/api/scoring/config?league_id=${l.id}`))).skater_scoring.goals).toBe(1);
});
test('G06 network failure preserves scoring edits and allows retry',async({page})=>{
 const l=await league(a);const p=await open(page,l.id);await expect(p.selectors.goals(page)).toHaveValue('1');
 await page.route('**/api/scoring/config',r=>r.request().method()==='POST'?r.abort('failed'):r.continue());
 await p.saveGoals('6');await expect(page.getByRole('alert')).toBeVisible();await expect(p.selectors.goals(page)).toHaveValue('6');
 expect((await result(await a.commissioner.api.get(`/api/scoring/config?league_id=${l.id}`))).skater_scoring.goals).toBe(1);
 await page.unroute('**/api/scoring/config');await p.selectors.save(page).click();
 await expect.poll(async()=>(await result(await a.commissioner.api.get(`/api/scoring/config?league_id=${l.id}`))).skater_scoring.goals).toBe(6);
});
test('G07 duplicate submit disabled during in-flight scoring save',async({page})=>{
 const l=await league(a);const p=await open(page,l.id);await expect(p.selectors.goals(page)).toHaveValue('1');
 let release!:()=>void;const gate=new Promise<void>(r=>release=r);let count=0;
 await page.route('**/api/scoring/config',async r=>{if(r.request().method()==='POST'){count++;await gate;}await r.continue();});
 await p.saveGoals('5');await expect(p.selectors.save(page)).toBeDisabled();expect(count).toBe(1);release();
 await expect.poll(async()=>(await result(await a.commissioner.api.get(`/api/scoring/config?league_id=${l.id}`))).skater_scoring.goals).toBe(5);
});
test('G08 player pool team selection survives reload',async({page})=>{
 const l=await league(a);await open(page,l.id,a.commissioner,'player-pool');
 const box=page.getByTestId('player-pool-team-grid').getByRole('checkbox').first();await expect(box).toBeChecked();await box.uncheck();await expect(box).not.toBeChecked();
 const saved=page.waitForResponse(r=>r.request().method()==='PUT'&&r.url().endsWith(`/leagues/${l.id}`));await page.getByTestId('player-pool-save').click();expect((await saved).ok()).toBe(true);await page.reload();await expect(box).not.toBeChecked();
});
test('G09 duplicate-player pool setting survives reload',async({page})=>{
 const l=await league(a);await open(page,l.id,a.commissioner,'player-pool');
 const select=page.getByTestId('player-pool-duplicate-select');await select.click();await page.getByRole('option',{name:'Entire League',exact:true}).click();
 await expect(select).toContainText('Entire League');const saved=page.waitForResponse(r=>r.request().method()==='PUT'&&r.url().endsWith(`/leagues/${l.id}`));await page.getByTestId('player-pool-save').click();expect((await saved).ok()).toBe(true);await page.reload();await expect(select).toContainText('Entire League');
});
const tabs=[['league-setup','League Setup'],['player-pool','Player Pool'],['rosters','Rosters'],['divisions','League Structure'],['rules-schedule','Transactions'],['salary-cap-contracts','Salary Cap & Contracts'],['scoring','Scoring'],['draft','Draft'],['tanking','Tank Monitor'],['roster-monitor','Roster Monitor'],['admin','League Administration'],['audit-log','Audit Log']];
test('G10 all desktop Settings tabs render without uncaught page errors',async({page},info)=>{
 const l=await league(a);const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));await open(page,l.id,a.commissioner,'league-setup');
 for(const [,label] of tabs){await page.getByRole('tab',{name:label,exact:true}).click();await expect(page.getByRole('tabpanel').first()).toBeVisible();await info.attach(label,{body:await page.screenshot(),contentType:'image/png'});}
 expect(errors).toEqual([]);
});
test('G11 mobile selector reaches every Settings tab and scoring saves',async({page},info)=>{
 const l=await league(a);await page.setViewportSize({width:390,height:844});await open(page,l.id,a.commissioner,'league-setup');
 for(const [value] of tabs){await page.getByTestId('commissioner-settings-mobile-tab-select').click();await page.getByTestId(`commissioner-settings-mobile-tab-${value}`).click();await expect(page.getByRole('tabpanel').first()).toBeVisible();}
 await page.getByTestId('commissioner-settings-mobile-tab-select').click();await page.getByTestId('commissioner-settings-mobile-tab-scoring').click();
 const p=new PermissionPage(page);await expect(p.selectors.goals(page)).toHaveValue('1');await p.saveGoals('3');
 await expect.poll(async()=>(await result(await a.commissioner.api.get(`/api/scoring/config?league_id=${l.id}`))).skater_scoring.goals).toBe(3);
 await info.attach('mobile-scoring',{body:await page.screenshot(),contentType:'image/png'});
});
