import {test,expect,request} from '@playwright/test';
import {ObjectId} from 'mongodb';
import {actors,dispose,type Actors,evidence} from '../support/access-history';
import {database,result} from '../support/h2h';
import {salaryLeague,settings,price,freePlayer,financial,payroll,assertPayroll,proposal,execute,denied,deniedTrade,seedRetention,contract} from '../support/salary';
let a:Actors;test.beforeAll(async()=>{a=await actors();});test.afterAll(async()=>{if(a)await dispose(a);});

test('P01 C01 commissioner saves all cap fields and retention rules',async({},info)=>{
 const l=await salaryLeague(a);const data={salary_cap_enabled:true,salary_cap:100000000,salary_cap_year_plus_1:105000000,salary_cap_year_plus_2:110000000,cap_floor_enabled:true,cap_floor:70000000,cap_floor_year_plus_1:75000000,cap_floor_year_plus_2:80000000,salary_cap_year_plus_1_tentative:true,salary_cap_year_plus_2_tentative:false};
 await result(await a.commissioner.api.put(`/api/leagues/${l.id}/admin/cap-settings`,{data}),info);
 await result(await a.commissioner.api.put(`/api/leagues/${l.id}`,{data:{salary_retention_enabled:true,salary_retention_slots:2,salary_retention_max_pct:40}}));
 const saved=await result(await a.commissioner.api.get(`/api/leagues/${l.id}`),info);expect(saved).toMatchObject({...data,salary_retention_slots:2,salary_retention_max_pct:40});
});
for(const path of ['admin/cap-settings','salary-retention-slots','general'])test(`P02 manager denied financial settings ${path}`,async({},info)=>{
 const l=await salaryLeague(a),before=await result(await a.commissioner.api.get(`/api/leagues/${l.id}`));
 const r=await a.manager.api.put(`/api/leagues/${l.id}${path==='general'?'':'/'+path}`,{data:{salary_cap:1,salary_retention_slots:0,salary_retention_enabled:false}});
 await evidence(info,'response',{status:r.status(),body:await r.text()});expect.soft(r.status()).toBe(403);
 expect(await result(await a.commissioner.api.get(`/api/leagues/${l.id}`))).toEqual(before);
});
for(const role of ['anonymous','outsider'] as const)for(const resource of ['overview','expiring','contracts','compliance','roster','dead-cap'])test(`P03 ${role} cannot read private ${resource}`,async({},info)=>{
 const l=await salaryLeague(a);await database(db=>db.collection('contracts').insertOne({...contract(l),status:'active',free_agency_year:2026}));const paths:any={overview:`/api/salary-cap/${l.id}`,expiring:`/api/salary-cap/${l.id}/expiring`,contracts:`/api/contracts?league_id=${l.id}`,compliance:`/api/teams/${l.teams[0].id}/compliance`,roster:`/api/roster/${l.teams[0].id}/detail`,'dead-cap':`/api/teams/${l.teams[0].id}/dead-cap-schedule`};
 const control=await a.commissioner.api.get(paths[resource]);expect(control.ok(),'member positive control').toBe(true);
 const r=await a[role].api.get(paths[resource]);await evidence(info,'protected-read',{status:r.status(),body:await r.text()});expect(r.status()).toBe(role==='anonymous'?401:403);
});
test('P04 contract creation rejects mismatched league and team',async({},info)=>{
 const l=await salaryLeague(a),other=await salaryLeague(a);const before=await financial(l);
 const r=await a.commissioner.api.post('/api/contracts',{data:{...contract(l),team_id:other.teams[0].id}});
 await evidence(info,'cross-league',{status:r.status(),body:await r.text()});expect.soft([400,403,404,422]).toContain(r.status());expect(await financial(l)).toEqual(before);
});
for(const role of ['manager','outsider'] as const)test(`P06 ${role} cannot forgive retention`,async({},info)=>{
 const l=await salaryLeague(a);await seedRetention(l,true);const before=await financial(l);
 const r=await a[role].api.delete(`/api/teams/${l.teams[0].id}/dead-cap/retention/${l.teams[0].players[0]}`);
 await evidence(info,'forgive',{status:r.status(),body:await r.text()});expect.soft(r.status()).toBe(403);expect(await financial(l)).toEqual(before);
});
test('C02 disabling cap overrides conflicting future amounts and flags',async({},info)=>{
 const l=await salaryLeague(a);await result(await a.commissioner.api.put(`/api/leagues/${l.id}/admin/cap-settings`,{data:{salary_cap_enabled:false,salary_cap:100000000,salary_cap_year_plus_1:105000000,salary_cap_year_plus_2:110000000,salary_cap_year_plus_1_tentative:true,cap_floor_enabled:true,cap_floor:70000000}}),info);
 const saved=await result(await a.commissioner.api.get(`/api/leagues/${l.id}`),info);
 expect(saved).toMatchObject({salary_cap_enabled:false,salary_cap:null,salary_cap_year_plus_1:null,salary_cap_year_plus_2:null,salary_cap_year_plus_1_tentative:false,cap_floor_enabled:false});
});
test('C03 cap can be re-enabled with explicit new amounts',async({},info)=>{
 const l=await salaryLeague(a);await result(await a.commissioner.api.put(`/api/leagues/${l.id}/admin/cap-settings`,{data:{salary_cap_enabled:false}}));
 await result(await a.commissioner.api.put(`/api/leagues/${l.id}/admin/cap-settings`,{data:{salary_cap_enabled:true,salary_cap:99000000,salary_cap_year_plus_1:101000000,salary_cap_year_plus_2:102000000}}));
 expect(await result(await a.commissioner.api.get(`/api/leagues/${l.id}`),info)).toMatchObject({salary_cap_enabled:true,salary_cap:99000000,salary_cap_year_plus_1:101000000,salary_cap_year_plus_2:102000000});
});
for(const value of [-1,'invalid'])test(`C04 invalid cap ${value} rejected`,async({},info)=>{
 const l=await salaryLeague(a);const r=await a.commissioner.api.put(`/api/leagues/${l.id}/admin/cap-settings`,{data:{salary_cap_enabled:true,salary_cap:value}});
 await denied(r,info,/cap|integer|number|input/i);expect((await result(await a.commissioner.api.get(`/api/leagues/${l.id}`))).salary_cap).toBe(100000000);
});
test('C05 floor above ceiling rejected including partial ceiling reduction',async({},info)=>{
 const l=await salaryLeague(a);await denied(await a.commissioner.api.put(`/api/leagues/${l.id}/admin/cap-settings`,{data:{cap_floor_enabled:true,cap_floor:100000001}}),info,/floor|ceiling|cap/i);
 await result(await a.commissioner.api.put(`/api/leagues/${l.id}/admin/cap-settings`,{data:{cap_floor_enabled:true,cap_floor:90000000}}));
 await denied(await a.commissioner.api.put(`/api/leagues/${l.id}/admin/cap-settings`,{data:{salary_cap:80000000}}),info,/floor|ceiling|cap/i);
 expect((await result(await a.commissioner.api.get(`/api/leagues/${l.id}`))).salary_cap).toBe(100000000);
});
for(const n of [-1,4,10,2.5])test(`C06 retention slots ${n} rejected without coercion`,async({},info)=>{
 const l=await salaryLeague(a);await denied(await a.commissioner.api.put(`/api/leagues/${l.id}/salary-retention-slots`,{data:{salary_retention_slots:n}}),info,/integer|between|slot/i);
 expect((await result(await a.commissioner.api.get(`/api/leagues/${l.id}`))).salary_retention_slots).toBe(3);
});
test('C07 zero slots displayed as zero and block retention',async({},info)=>{
 const l=await salaryLeague(a);await result(await a.commissioner.api.put(`/api/leagues/${l.id}/salary-retention-slots`,{data:{salary_retention_slots:0}}));
 const c=await result(await a.manager.api.get(`/api/teams/${l.teams[0].id}/compliance`),info);
 expect.soft(c.salary_retention_slots_total).toBe(0);expect.soft(c.salary_retention_slots_remaining).toBe(0);await deniedTrade(a,l,40,info);
});
for(const format of ['h2h-points','h2h-categories','rotisserie']){
 test(`A01 ${format} explicit salary baseline consistent`,async({},info)=>{const l=await salaryLeague(a,format);await assertPayroll(a,l,[80000000,90000000],info);});
 test(`R01 ${format} no-retention trade preserves full obligation`,async({},info)=>{const l=await salaryLeague(a,format);await execute(a,l,0,info);await assertPayroll(a,l,[70000000,100000000],info);expect((await financial(l)).retained).toHaveLength(0);});
 test(`R02 ${format} 40 percent retained trade charges A4M B6M`,async({},info)=>{
  const l=await salaryLeague(a,format);await execute(a,l,40,info);const state=await financial(l);await evidence(info,'financial-state',state);
  expect.soft(state.retained).toHaveLength(1);expect.soft(state.retained[0]?.amount).toBe(4000000);
  const p=await assertPayroll(a,l,[74000000,96000000],info);expect.soft(p.compliance[0].salary_retention_slots_used).toBe(1);expect.soft(p.compliance[0].retained_salary_total).toBe(4000000);
  expect.soft(p.schedules[0].schedule).toHaveLength(1);for(const row of p.schedules[0].schedule)expect.soft(row.total).toBe(4000000);
 });
}
test('A02 partial contract ledger cannot hide remaining payroll',async({},info)=>{
 const l=await salaryLeague(a);await database(db=>db.collection('contracts').insertOne({...contract(l),status:'active'}));await assertPayroll(a,l,[80000000,90000000],info);
});
for(const mode of ['full','default','tiered','none'])test(`A05 minors ${mode} consistent in overview and compliance`,async({},info)=>{
 const l=await salaryLeague(a);await price(l.teams[0].players[0],2000000);await settings(l,{minors_cap_treatment:mode,default_rookie_aav:950000});
 await database(async db=>{await db.collection('players').updateOne({_id:new ObjectId(l.teams[0].players[0])},{$set:{age:23,is_prospect:true}});await db.collection('teams').updateOne({_id:new ObjectId(l.teams[0].id)},{$set:{[`lineup.${l.teams[0].players[0]}`]:{section:'minors',slot:'MIN'}}});});
 const values:any={full:72000000,default:70950000,tiered:71000000,none:70000000};await assertPayroll(a,l,[values[mode],90000000],info);
});
test('A07 valid zero rookie setting must not become 950k',async({},info)=>{
 const l=await salaryLeague(a);await result(await a.commissioner.api.put(`/api/leagues/${l.id}/admin/cap-settings`,{data:{default_rookie_aav:0,minors_cap_treatment:'default'}}));
 await database(db=>db.collection('teams').updateOne({_id:new ObjectId(l.teams[0].id)},{$set:{[`lineup.${l.teams[0].players[0]}`]:{section:'minors',slot:'MIN'}}}));await assertPayroll(a,l,[70000000,90000000],info);
});
for(const amount of [9999999,10000000,10000001])test(`E01 add ${amount} to 90M respects exact ceiling`,async({},info)=>{
 const l=await salaryLeague(a),pid=await freePlayer(l,amount),before=await financial(l);const r=await a.manager2.api.post(`/api/roster/${l.teams[1].id}/add`,{data:{player_id:pid}});
 if(amount>10000000){await denied(r,info,/salary cap/i);expect(await financial(l)).toEqual(before);}else{await result(r,info);await assertPayroll(a,l,[80000000,90000000+amount],info);}
});
test('E02 creating first explicit contract does not double charge existing player',async({},info)=>{
 const l=await salaryLeague(a);await settings(l,{salary_cap:80000000});await result(await a.manager.api.post('/api/contracts',{data:contract(l)}),info);await assertPayroll(a,l,[80000000,90000000],info);
});
test('E03 waiver claim plus drop processes at 99M',async({},info)=>{
 const l=await salaryLeague(a);await price(l.teams[0].players[0],4000000);await price(l.teams[0].players[1],94000000);
 await result(await a.manager.api.get(`/api/teams/${l.teams[0].id}/compliance`));const pid=await freePlayer(l,5000000);
 await result(await a.manager.api.post('/api/waivers/claim',{data:{league_id:l.id,player_id:pid,bid_amount:0,drop_player_id:l.teams[0].players[0]}}),info);
 await result(await a.commissioner.api.post(`/api/waivers/process?league_id=${l.id}&force=true`),info);await assertPayroll(a,l,[99000000,90000000],info);
});
test('A04 waiver rejects over-cap claim despite stale low cache',async({},info)=>{
 const l=await salaryLeague(a),pid=await freePlayer(l,11000000);await database(db=>db.collection('teams').updateOne({_id:new ObjectId(l.teams[1].id)},{$set:{salary_used:0}}));
 await denied(await a.manager2.api.post('/api/waivers/claim',{data:{league_id:l.id,player_id:pid,bid_amount:0}}),info,/cap/i);
});
test('E04 trade execution revalidates cap changed after proposal',async({},info)=>{
 const l=await salaryLeague(a),p=await result(await proposal(a,l,0));await settings(l,{salary_cap:99000000});const before=await financial(l);
 await denied(await a.manager2.api.post(`/api/trades/${p._id||p.id}/accept`),info,/cap/i);expect(await financial(l)).toEqual(before);
});
test('E05 disabled cap permits otherwise-valid over-limit add',async({},info)=>{
 const l=await salaryLeague(a);await settings(l,{salary_cap_enabled:false});const pid=await freePlayer(l,20000000);await result(await a.manager2.api.post(`/api/roster/${l.teams[1].id}/add`,{data:{player_id:pid}}),info);await assertPayroll(a,l,[80000000,110000000],info);
});
test('E06 concurrent adds cannot jointly exceed cap',async({},info)=>{
 const l=await salaryLeague(a);const ids=l.teams[7].players.slice(1);for(const id of ids)await price(id,6000000);
 const rs=await Promise.all(ids.map(id=>a.manager2.api.post(`/api/roster/${l.teams[1].id}/add`,{data:{player_id:id}})));
 await evidence(info,'concurrent-results',await Promise.all(rs.map(async r=>({status:r.status(),body:await r.text()}))));expect.soft(rs.filter(r=>r.ok())).toHaveLength(1);await assertPayroll(a,l,[80000000,96000000],info);
});
test('R03 no retention over cap is rejected',async({},info)=>{const l=await salaryLeague(a);await price(l.teams[1].players[0],95000000);await deniedTrade(a,l,0,info);});
test('R03 50 percent retention permits exact-cap receiving team',async({},info)=>{const l=await salaryLeague(a);await price(l.teams[1].players[0],95000000);await execute(a,l,50,info);await assertPayroll(a,l,[75000000,100000000],info);});
for(const pct of [-1,40.01,101])test(`R04 invalid or over-limit retention ${pct} denied`,async({},info)=>{const l=await salaryLeague(a);await settings(l,{salary_retention_max_pct:40});await deniedTrade(a,l,pct,info);});
test('R04 retention disabled blocks direct API retained trade',async({},info)=>{const l=await salaryLeague(a);await settings(l,{salary_retention_enabled:false});await deniedTrade(a,l,40,info);});
test('R05 occupied last retention slot blocks another retained player',async({},info)=>{
 const l=await salaryLeague(a);await settings(l,{salary_retention_slots:1});await database(db=>db.collection('salary_retentions').insertOne({league_id:l.id,retainer_team_id:l.teams[0].id,player_id:l.teams[6].players[0],amount:1000000,pct:10,created_at:new Date()}));await deniedTrade(a,l,40,info);
});
for(const action of ['reject','cancel'])test(`R06 ${action} pending retained trade has no financial effects`,async({},info)=>{
 const l=await salaryLeague(a),before=await financial(l),p=await result(await proposal(a,l,40));expect(await financial(l)).toEqual(before);
 const owner=action==='reject'?a.manager2:a.manager;await result(await owner.api.post(`/api/trades/${p._id||p.id}/${action}`),info);expect(await financial(l)).toEqual(before);
});
test('R08 repeated execution does not duplicate obligations',async({},info)=>{
 const l=await salaryLeague(a),id=await execute(a,l,40,info),before=await financial(l);const r=await a.commissioner.api.post(`/api/trades/${id}/execute`);await evidence(info,'replay',{status:r.status(),body:await r.text()});expect(r.status()).toBe(400);expect(await financial(l)).toEqual(before);
});
for(const mirror of [false,true])test(`L05 retention cancellation removes ${mirror?'mirrored':'legacy'} charge permanently`,async({},info)=>{
 const l=await salaryLeague(a);await seedRetention(l,mirror);const before=await result(await a.commissioner.api.get(`/api/teams/${l.teams[0].id}/dead-cap-schedule`));expect(before.schedule).toHaveLength(1);
 await result(await a.commissioner.api.delete(`/api/teams/${l.teams[0].id}/dead-cap/retention/${l.teams[0].players[0]}`),info);
 for(let i=0;i<2;i++){const after=await result(await a.commissioner.api.get(`/api/teams/${l.teams[0].id}/dead-cap-schedule`),info);expect.soft(after.schedule).toHaveLength(0);}expect((await financial(l)).retained.filter((row:any)=>row.status!=="cancelled")).toHaveLength(0);
 expect((await financial(l)).retained[0]).toMatchObject({status:"cancelled",forgiveness_policy:"receiver_pays",amount:4000000});
});
test('L06 collection plus mirrored retention schedule counts once',async({},info)=>{
 const l=await salaryLeague(a);await seedRetention(l,true);const s=await result(await a.commissioner.api.get(`/api/teams/${l.teams[0].id}/dead-cap-schedule`),info);expect(s.schedule).toHaveLength(1);for(const row of s.schedule)expect(row.total).toBe(4000000);
});

test('P05 co-commissioner can save cap settings through supported API',async({},info)=>{
 const l=await salaryLeague(a);await settings(l,{co_commissioners:[a.outsider.id]});
 await result(await a.outsider.api.put(`/api/leagues/${l.id}/admin/cap-settings`,{data:{salary_cap:99000000}}),info);
 expect((await result(await a.commissioner.api.get(`/api/leagues/${l.id}`))).salary_cap).toBe(99000000);
});
for(const sandbox of [false,true])test(`P05 platform admin cap settings sandbox=${sandbox}`,async({},info)=>{
 const l=await salaryLeague(a);await settings(l,{is_test_sandbox:sandbox});const api=await request.newContext({baseURL:'http://web'});
 try{await result(await api.post('/api/auth/login',{data:{email:process.env.E2E_ADMIN_EMAIL,password:process.env.E2E_ADMIN_PASSWORD}}));const r=await api.put(`/api/leagues/${l.id}/admin/cap-settings`,{data:{salary_cap:99000000}});await evidence(info,'admin-cap',{status:r.status(),body:await r.text()});expect(r.status()).toBe(sandbox?200:403);}finally{await api.dispose();}
});
test('A08 retained salary and buyout are each charged once',async({},info)=>{
 const l=await salaryLeague(a);await seedRetention(l,true);await database(db=>db.collection('teams').updateOne({_id:new ObjectId(l.teams[0].id)},{$set:{roster:[l.teams[0].players[1]],salary_retentions:[{player_id:l.teams[0].players[0],amount:4000000}]},$push:{dead_cap_schedule:{year:new Date().getUTCFullYear(),amount:2000000,source:'buyout',player_id:l.teams[6].players[0]}}} as any));
 await assertPayroll(a,l,[76000000,90000000],info);
});
test('R07 three-party retained trade applies full monetary obligations',async({},info)=>{
 const l=await salaryLeague(a),p=l.teams[0].players[0],q=l.teams[2].players[0];
 const asset={asset_type:'player',player_id:p,salary_retained_pct:40,to_team_id:l.teams[1].id};
 const other={asset_type:'player',player_id:q,salary_retained_pct:0,to_team_id:l.teams[0].id};
 const trade=await result(await a.manager.api.post('/api/trades/multi',{data:{league_id:l.id,parties:[{team_id:l.teams[0].id,sends:[asset],receives:[other]},{team_id:l.teams[1].id,sends:[],receives:[asset]},{team_id:l.teams[2].id,sends:[other],receives:[]}]}}),info,'multi-proposal');
 const id=trade._id||trade.id;expect(id).toBeTruthy();
 await result(await a.manager2.api.post(`/api/trades/${id}/party-respond`,{data:{action:'accept'}}),info);
 await result(await a.commissioner.api.post(`/api/trades/${id}/party-respond`,{data:{action:'accept'}}),info);
 const record=await database(db=>db.collection('trades').findOne({_id:new ObjectId(id)}));expect(record!.status).toBe('executed');
 await assertPayroll(a,l,[94000000,96000000],info);const state=await financial(l);expect.soft(state.retained[0]?.amount).toBe(4000000);
 const charges=state.teams.find((t:any)=>t._id===l.teams[0].id).dead_cap_schedule;expect.soft(charges).toHaveLength(1);for(const row of charges)expect.soft(row.amount).toBe(4000000);
});
test('L01 onward transfer preserves original retained liability',async({},info)=>{
 const l=await salaryLeague(a);await execute(a,l,40,info);await execute(a,l,0,info,1,2);await assertPayroll(a,l,[74000000,90000000],info);
 const overview=await result(await a.commissioner.api.get(`/api/salary-cap/${l.id}`));expect(overview.teams.find((t:any)=>t.team_id===l.teams[2].id).cap_used).toBe(26000000);
});
test('L06 same NHL player in another league has independent retained charges',async({},info)=>{
 const l=await salaryLeague(a),other=await salaryLeague(a);await seedRetention(l);
 await database(db=>db.collection('teams').updateOne({_id:new ObjectId(other.teams[0].id)},{$set:{roster:[l.teams[0].players[0]]}}));
 const before=await payroll(a,other,info);await a.commissioner.api.delete(`/api/teams/${l.teams[0].id}/dead-cap/retention/${l.teams[0].players[0]}`);
 const after=await payroll(a,other,info);expect(after).toEqual(before);
});
test('U04 retention slot change writes actor and before-after audit',async({},info)=>{
 const l=await salaryLeague(a);await result(await a.commissioner.api.put(`/api/leagues/${l.id}/salary-retention-slots`,{data:{salary_retention_slots:2}}));
 const rows=await database(db=>db.collection('audit_log').find({league_id:l.id,action:'salary_retention_slots_updated'}).toArray());await evidence(info,'audit',rows);expect(rows).toHaveLength(1);expect(rows[0].diff.salary_retention_slots).toEqual({from:3,to:2});
 expect(JSON.stringify(rows[0])).toContain(a.commissioner.id);
});

test('E04 pending waiver revalidates changed cap at actual processing',async({},info)=>{
 const l=await salaryLeague(a),pid=await freePlayer(l,5000000);
 await result(await a.manager2.api.post('/api/waivers/claim',{data:{league_id:l.id,player_id:pid,bid_amount:0}}),info);
 await settings(l,{salary_cap:94000000});const before=await financial(l);
 await result(await a.commissioner.api.post(`/api/waivers/process?league_id=${l.id}&force=true`),info);
 expect(await financial(l)).toEqual(before);
 const claim=await database(db=>db.collection('waiver_claims').findOne({league_id:l.id,player_id:pid}));
 expect(claim!.status).toBe('denied');expect(claim!.denied_reason).toBe('salary_cap_breach');
});

for(const policy of ['receiver_pays','league_waives'])test(`F01 forgiveness ${policy} preserves history and expires with season`,async({},info)=>{
 const l=await salaryLeague(a),year=new Date().getUTCFullYear();
 await settings(l,{current_season_year:year,current_season_status:'in_progress',season_end_date:`${year}-12-31`});
 await result(await a.commissioner.api.put(`/api/leagues/${l.id}`,{data:{retention_forgiveness_policy:policy}}),info);
 expect((await result(await a.commissioner.api.get(`/api/leagues/${l.id}`))).retention_forgiveness_policy).toBe(policy);
 await execute(a,l,40,info);await assertPayroll(a,l,[74000000,96000000],info);
 await result(await a.commissioner.api.delete(`/api/teams/${l.teams[0].id}/dead-cap/retention/${l.teams[0].players[0]}`),info);
 await assertPayroll(a,l,[70000000,policy==='receiver_pays'?100000000:96000000],info);
 const history=(await financial(l)).retained;expect(history).toHaveLength(1);expect(history[0]).toMatchObject({status:'cancelled',amount:4000000,forgiveness_policy:policy});
 expect((await a.commissioner.api.delete(`/api/teams/${l.teams[0].id}/dead-cap/retention/${l.teams[0].players[0]}`)).status()).toBe(404);
 await result(await a.commissioner.api.put(`/api/leagues/${l.id}`,{data:{retention_forgiveness_policy:policy==='receiver_pays'?'league_waives':'receiver_pays'}}));
 await assertPayroll(a,l,[70000000,policy==='receiver_pays'?100000000:96000000],info);
 await result(await a.commissioner.api.post(`/api/leagues/${l.id}/complete-season`,{data:{season_year:year}}),info);
 await result(await a.commissioner.api.post(`/api/leagues/${l.id}/renew-season`,{data:{new_season_year:year+1}}),info);
 await assertPayroll(a,l,[70000000,100000000],info);
});
for(const path of ['', '/admin/cap-settings'])test(`F02 forgiveness settings validation and authorization ${path}`,async({},info)=>{
 const l=await salaryLeague(a);
 const denied=await a.manager.api.put(`/api/leagues/${l.id}${path}`,{data:{retention_forgiveness_policy:'league_waives'}});expect(denied.status()).toBe(403);
 for(const value of ['invalid',null]){const invalid=await a.commissioner.api.put(`/api/leagues/${l.id}${path}`,{data:{retention_forgiveness_policy:value}});expect(invalid.status()).toBe(422);}
 expect((await result(await a.commissioner.api.get(`/api/leagues/${l.id}`))).retention_forgiveness_policy).toBe('receiver_pays');
 await result(await a.commissioner.api.put(`/api/leagues/${l.id}${path}`,{data:{retention_forgiveness_policy:'league_waives'}}),info);
 expect((await result(await a.commissioner.api.get(`/api/leagues/${l.id}`))).retention_forgiveness_policy).toBe('league_waives');
});

test('F04 buyout replaces explicit contract payroll and reversal restores it',async({},info)=>{
 const l=await salaryLeague(a);await settings(l,{contract_buyouts_enabled:true});
 await database(db=>db.collection('contracts').insertOne({...contract(l),status:'active'}));
 await result(await a.manager.api.post(`/api/teams/${l.teams[0].id}/players/${l.teams[0].players[0]}/buyout`,{data:{length_option:'one_year',buyout_rate:0.5,years_span:1}}),info);
 await assertPayroll(a,l,[85000000,90000000],info);
 const row=await database(db=>db.collection('contracts').findOne({league_id:l.id,player_id:l.teams[0].players[0]}));expect(row?.status).toBe('bought_out');
 await result(await a.commissioner.api.delete(`/api/teams/${l.teams[0].id}/buyouts/${l.teams[0].players[0]}`),info);
 await assertPayroll(a,l,[80000000,90000000],info);
});
