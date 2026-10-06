import {test,expect} from '@playwright/test';
import {actors,dispose,league,seedStats,seedGap,trade,propose,lineup,allocation,evidence,type Actors} from '../support/access-history';
import {result,database,generate} from '../support/h2h';
import {ObjectId} from 'mongodb';
let a:Actors;
test.beforeAll(async()=>{a=await actors();});test.afterAll(async()=>{if(a)await dispose(a);});
for(const format of ['h2h-points','h2h-categories','rotisserie']){
  test(`R00 ${format} fixed roster control`,async({},info)=>{
    const l=await league(a,format);await seedStats(l,10,0);expect(await allocation(a,l,format,info)).toEqual([10,0,0]);
  });
  test(`R01 ${format} trade retains past and allocates subsequent stats`,async({},info)=>{
    const l=await league(a,format);await seedStats(l);expect(await allocation(a,l,format,info,'before')).toEqual([10,0,0]);
    await trade(a,l,info);await seedStats(l,10,6);expect(await allocation(a,l,format,info,'after')).toEqual([10,6,0]);
  });
  test(`R03 ${format} late imported historical stats use former owner`,async({},info)=>{
    const l=await league(a,format);await trade(a,l,info);await seedStats(l,10,6);expect(await allocation(a,l,format,info)).toEqual([10,6,0]);
  });
  test(`R06 ${format} drop preserves earned stats and excludes unowned interval`,async({},info)=>{
    const l=await league(a,format);await seedStats(l);await allocation(a,l,format,info,'before');
    await result(await a.manager.api.post(`/api/roster/${l.teams[0].id}/drop`,{data:{player_id:l.teams[0].players[0]}}),info,'drop');
    await seedStats(l,10,6);expect(await allocation(a,l,format,info)).toEqual([10,0,0]);
  });
  test(`R06 ${format} pickup cannot acquire earlier owner or unowned stats`,async({},info)=>{
    const l=await league(a,format);await seedStats(l);
    await result(await a.manager.api.post(`/api/roster/${l.teams[0].id}/drop`,{data:{player_id:l.teams[0].players[0]}}));
    await result(await a.manager2.api.post(`/api/roster/${l.teams[1].id}/add`,{data:{player_id:l.teams[0].players[0]}}),info,'pickup');
    await lineup(a,l,1,'forward');await seedStats(l,10,6);expect(await allocation(a,l,format,info)).toEqual([10,6,0]);
  });
  test(`R08 ${format} multiple trades preserve original allocation`,async({},info)=>{
    const l=await league(a,format);await seedStats(l);await trade(a,l,info);await trade(a,l,info,1,2);
    await seedStats(l,10,6);expect(await allocation(a,l,format,info)).toEqual([10,0,6]);
  });
  test(`R09 ${format} drop reacquire excludes stats from unowned gap`,async({},info)=>{
    const l=await league(a,format);await seedStats(l);
    await result(await a.manager.api.post(`/api/roster/${l.teams[0].id}/drop`,{data:{player_id:l.teams[0].players[0]}}));
    // Ingest a distinct event during the real unowned interval.
    await seedGap(l);
    await result(await a.manager.api.post(`/api/roster/${l.teams[0].id}/add`,{data:{player_id:l.teams[0].players[0]}}));
    await lineup(a,l,0,'forward');expect(await allocation(a,l,format,info)).toEqual([10,0,0]);
  });
  test(`R10 ${format} bench change preserves old stats and excludes new stats`,async({},info)=>{
    const l=await league(a,format);await seedStats(l);await lineup(a,l,0,'bench');await seedStats(l,10,6);
    expect(await allocation(a,l,format,info)).toEqual([10,0,0]);
  });
  test(`R11 ${format} activation excludes bench period stats`,async({},info)=>{
    const l=await league(a,format,'bench');
    await seedStats(l);
    await lineup(a,l,0,'forward');await seedStats(l,10,6);expect(await allocation(a,l,format,info)).toEqual([6,0,0]);
  });
  test(`R14 ${format} historical correction follows former team`,async({},info)=>{
    const l=await league(a,format);await seedStats(l);await trade(a,l,info);await seedStats(l,12,6);
    expect(await allocation(a,l,format,info)).toEqual([12,6,0]);
  });
  for(const action of ['reject','cancel'])test(`R15 ${format} ${action} pending trade leaves allocation unchanged`,async({},info)=>{
    const l=await league(a,format);await seedStats(l);const p=await propose(a,l);
    const owner=action==='reject'?a.manager2:a.manager;
    await result(await owner.api.post(`/api/trades/${p.id}/${action}`),info,action);
    expect(await allocation(a,l,format,info)).toEqual([10,0,0]);
  });
  test(`R04 ${format} accepted future-effective trade retains current allocation`,async({},info)=>{
    const l=await league(a,format);await seedStats(l);
    await database(db=>db.collection('leagues').updateOne({_id:new ObjectId(l.id)},{$set:{trade_review_period_days:1}}));
    const p=await propose(a,l);
    await result(await a.manager2.api.post(`/api/trades/${p.id}/respond`,{data:{action:'accept'}}),info,'pending-acceptance');
    const record=await database(db=>db.collection('trades').findOne({_id:new ObjectId(p.id)}));
    await evidence(info,'pending-record',record);expect(record!.status).toBe('pending');expect(new Date(record!.processes_at).getTime()).toBeGreaterThan(Date.now());
    expect(await allocation(a,l,format,info)).toEqual([10,0,0]);
  });
  test(`R07 ${format} waiver claim does not credit stats before processing`,async({},info)=>{
    const l=await league(a,format,'unowned');await seedStats(l);
    // Initial fixture has P unowned throughout the historic event; claim is a real API action.
    await database(db=>db.collection('teams').updateOne({_id:new ObjectId(l.teams[0].id)},{$pull:{roster:l.teams[0].players[0]}} as any));
    await result(await a.manager2.api.post('/api/waivers/claim',{data:{league_id:l.id,player_id:l.teams[0].players[0],bid_amount:0}}),info,'claim');
    expect(await allocation(a,l,format,info,'pending')).toEqual([0,0,0]);
    // Explicit commissioner force-processing is available in this E2E environment (workers disabled).
    await result(await a.commissioner.api.post(`/api/waivers/process?league_id=${l.id}&force=true`),info,'processing');
    const team=await database(db=>db.collection('teams').findOne({_id:new ObjectId(l.teams[1].id)}));
    expect(team!.roster,'Waiver claim must be processed before the historical assertion').toContain(l.teams[0].players[0]);
    await lineup(a,l,1,'forward');await seedStats(l,10,6);expect(await allocation(a,l,format,info,'processed')).toEqual([0,6,0]);
  });
}
test('R02 R17 R18 rotisserie closed-period recompute preserves allocation ranks standings',async({},info)=>{
  const l=await league(a,'rotisserie');await seedStats(l);
  const recompute=async()=>result(await a.commissioner.api.post(`/api/leagues/${l.id}/roto/recompute`,{data:{period:1,close:true}}),info,'recompute');
  await recompute();const before=await result(await a.commissioner.api.get(`/api/leagues/${l.id}/roto/standings`),info,'before-standings');
  await trade(a,l,info);await recompute();const after=await result(await a.commissioner.api.get(`/api/leagues/${l.id}/roto/standings`),info,'after-standings');
  expect(before.totals[l.teams[0].id].total_points).toBe(8);
  expect.soft(after.totals).toEqual(before.totals);
  expect.soft(after.categories).toEqual(before.categories);
  const first=await allocation(a,l,'rotisserie',info,'first-recompute');expect.soft(first).toEqual([10,0,0]);
  await recompute();expect(await allocation(a,l,'rotisserie',info,'second-recompute')).toEqual(first);
});
test('R12 owner lineup lock is enforced without mutation',async({},info)=>{
  const l=await league(a);await database(db=>db.collection('leagues').updateOne({_id:new ObjectId(l.id)},{$set:{roster_lock_type:'daily',lineup_lock_minutes_before:1440,emergency_changes_enabled:false}}));
  const before=await result(await a.manager.api.get(`/api/teams/${l.teams[0].id}/lineup`));
  const r=await a.manager.api.post(`/api/teams/${l.teams[0].id}/lineup`,{data:{lineup:{}}});
  await evidence(info,'locked-change',{status:r.status(),body:await r.text()});expect(r.status()).toBe(400);
  expect(await result(await a.manager.api.get(`/api/teams/${l.teams[0].id}/lineup`))).toEqual(before);
});
test('R19 independent league roster histories isolate the same player',async({},info)=>{
  const l=await league(a,'rotisserie'),other=await league(a,'rotisserie');await seedStats(l);
  await database(db=>db.collection('teams').updateOne({_id:new ObjectId(other.teams[0].id)},{$set:{roster:[l.teams[0].players[0]]}}));
  const before=await allocation(a,other,'rotisserie',info,'other-before');await trade(a,l,info);
  expect(await allocation(a,other,'rotisserie',info,'other-after')).toEqual(before);
});
for(const format of ['h2h-points','h2h-categories'])test(`R02 R17 R18 ${format} finalized stats survive transfer and recalculation`,async({},info)=>{
  const l=await league(a,format);await seedStats(l);await generate(a.commissioner.api,l);
  await result(await a.commissioner.api.post('/api/matchups/simulate-week',{data:{league_id:l.id,week:1}}),info,'finalize-week');
  const read=async()=>result(await a.commissioner.api.get(`/api/leagues/${l.id}/standings`));
  const before=await read();await trade(a,l,info);
  for(let i=0;i<2;i++){
    await result(await a.commissioner.api.post(`/api/leagues/${l.id}/recalculate-stats`,{data:{}}),info,`recalculation-${i}`);
    const after=await read();await evidence(info,`standings-${i}`,after);
    const numeric=(rows:any)=>rows.standings.map((t:any)=>({id:t.team_id||t.id,w:t.wins,l:t.losses,t:t.ties,pf:t.points_for,pa:t.points_against}));
    expect.soft(numeric(after)).toEqual(numeric(before));
  }
  expect(await allocation(a,l,format,info,'historical-breakdown')).toEqual([10,0,0]);
});
for(const format of ['h2h-points','h2h-categories'])test(`R01 R18 ${format} finalization after trade credits correct team totals`,async({},info)=>{
 const l=await league(a,format);await seedStats(l);await trade(a,l,info);await seedStats(l,10,6);await generate(a.commissioner.api,l);
 await result(await a.commissioner.api.post('/api/matchups/simulate-week',{data:{league_id:l.id,week:1}}),info,'finalized-after-trade');
 const teams=await database(db=>db.collection('teams').find({league_id:l.id}).toArray());
 const scores=l.teams.slice(0,3).map(t=>teams.find(row=>String(row._id)===t.id)!.points_for);
 await evidence(info,'points-for',scores);expect(scores).toEqual([10,6,0]);
});
// R05, R13 and R16 are executable cases in history-timing.spec.ts.
