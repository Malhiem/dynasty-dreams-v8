import {test,expect} from '@playwright/test';
import {actors,dispose,league,state,evidence,type Actors} from '../support/access-history';
import {database,result,generate,type League} from '../support/h2h';
import {ObjectId} from 'mongodb';
let a:Actors,l:League,other:League;
test.beforeAll(async()=>{a=await actors();l=await league(a);other=await league(a);await generate(a.commissioner.api,l);});
test.afterAll(async()=>{if(a)await dispose(a);});
const writes = [
  {id:'P01',name:'scoring rules',method:'POST',url:(l:League)=>'/api/scoring/config',data:(l:League)=>({league_id:l.id,skater_scoring:{goals:9},goalie_scoring:{},roto_categories:['goals']})},
  {id:'P02',name:'bonus create',method:'PUT',url:(l:League)=>`/api/leagues/${l.id}`,data:()=>({playoff_roto_seed_bonuses:{'2':10}})},
  {id:'P02',name:'bonus edit',method:'PUT',url:(l:League)=>`/api/leagues/${l.id}`,data:()=>({playoff_roto_seed_bonuses:{'1':20}})},
  {id:'P02',name:'bonus remove',method:'PUT',url:(l:League)=>`/api/leagues/${l.id}`,data:()=>({playoff_roto_seed_bonuses:{}})},
  {id:'P03',name:'season finalization',method:'POST',url:(l:League)=>`/api/leagues/${l.id}/complete-season`,data:()=>({season_year:2026})},
  {id:'P12',name:'period close recompute',method:'POST',url:(l:League)=>`/api/leagues/${l.id}/roto/recompute`,data:()=>({period:1,close:true})},
  {id:'P12',name:'H2H week finalization',method:'POST',url:()=>'/api/matchups/simulate-week',data:(l:League)=>({league_id:l.id,week:1})},
  {id:'P12',name:'standings recalculation',method:'POST',url:(l:League)=>`/api/leagues/${l.id}/recalculate-stats`,data:()=>({})},
];
for(const w of writes) {
  test(`${w.id} commissioner can ${w.name}`,async({},info)=>{
    const fresh=await league(a);if(w.name==='H2H week finalization')await generate(a.commissioner.api,fresh);
    const body=await result(await a.commissioner.api.fetch(w.url(fresh),{method:w.method,data:w.data(fresh)}),info,'authorized-response');
    const after=await state(fresh);await evidence(info,'persisted-state',after);
    if(w.id==='P01')expect(after.scoring_configs[0].skater_scoring.goals).toBe(9);
    if(w.id==='P02')expect(after.leagues[0].playoff_roto_seed_bonuses).toEqual((w.data(fresh) as any).playoff_roto_seed_bonuses);
    if(w.id==='P03')expect(after.league_seasons).toHaveLength(1);
    if(w.name==='period close recompute')expect(after.roto_period_results[0].closed).toBe(true);
    if(w.name==='H2H week finalization')expect(after.matchups.filter((m:any)=>m.week===1).every((m:any)=>m.status==='completed')).toBe(true);
  });
  for(const role of ['manager','manager2','outsider','anonymous','expired'] as const) {
    test(`${role.startsWith('manager')?'P04':role==='outsider'?'P07':'P08'} ${role} denied ${w.name}`,async({},info)=>{
      const before=await state(l),r=await a[role].api.fetch(w.url(l),{method:w.method,data:w.data(l)});
      await evidence(info,'denied-response',{status:r.status(),body:await r.text()});
      const after=await state(l);await evidence(info,'mutation-check',{unchanged:JSON.stringify(before)===JSON.stringify(after)});
      expect.soft(after,'Denied requests must not mutate league-scoped data').toEqual(before);
      expect(role==='anonymous'||role==='expired'?[401]:[403,404]).toContain(r.status());
    });
  }
}
const reads=[
  ['league details',(l:League)=>`/api/leagues/${l.id}`],
  ['scoring configuration',(l:League)=>`/api/scoring/config?league_id=${l.id}`],
  ['team',(l:League)=>`/api/teams/${l.teams[0].id}`],
  ['roster',(l:League)=>`/api/roster/${l.teams[0].id}`],
  ['roster detail',(l:League)=>`/api/roster/${l.teams[0].id}/detail`],
  ['lineup',(l:League)=>`/api/teams/${l.teams[0].id}/lineup`],
  ['league standings',(l:League)=>`/api/leagues/${l.id}/standings`],
  ['roto standings',(l:League)=>`/api/leagues/${l.id}/roto/standings`],
  ['roto matchup',(l:League)=>`/api/leagues/${l.id}/roto/matchup?period=1`],
  ['matchups',(l:League)=>`/api/matchups/${l.id}`],
  ['matchup results',(l:League)=>`/api/matchups/${l.id}/results?week=1`],
  ['daily scoring',(l:League)=>`/api/matchups/${l.id}/daily-scoring?team_id=${l.teams[0].id}&week=1`],
  ['legacy scoring',(l:League)=>`/api/scoring/calculate/${l.id}`],
  ['legacy roto',(l:League)=>`/api/scoring/roto/${l.id}`],
] as const;
for(const [name,url] of reads)for(const role of ['manager','outsider','anonymous','expired'] as const){
  test(`${role==='manager'?'P00':role==='outsider'?'P06':'P08'} ${role} read ${name}`,async({},info)=>{
    const r=await a[role].api.get(url(l));await evidence(info,'read-response',{url:r.url(),status:r.status(),body:await r.text()});
    if(role==='manager')expect(r.status()).toBe(200);else expect(role==='outsider'?[403,404]:[401]).toContain(r.status());
  });
}
test('P09 mixed league and team identifiers rejected',async({},info)=>{
  // Manager is explicitly removed from other league before substituting its team ID.
  await database(db=>db.collection('teams').updateMany({league_id:other.id},{$set:{owner_id:a.commissioner.id}}));
  const r=await a.manager.api.get(`/api/matchups/${l.id}/daily-scoring?team_id=${other.teams[0].id}&week=1`);
  await evidence(info,'cross-league-response',{status:r.status(),body:await r.text()});expect([403,404]).toContain(r.status());
});
test('P09 commissioner of another league has no authority here',async({},info)=>{
  await database(db=>db.collection('leagues').updateOne({_id:new ObjectId(other.id)},{$set:{commissioner_id:a.outsider.id}}));
  const before=await state(l),r=await a.outsider.api.put(`/api/leagues/${l.id}`,{data:{playoff_roto_seed_bonuses:{'1':99}}});
  await evidence(info,'cross-league-mutation',{status:r.status(),body:await r.text()});expect(await state(l)).toEqual(before);expect([403,404]).toContain(r.status());
});
test('P10 client supplied commissioner identity cannot grant scoring privilege',async({},info)=>{
  const before=await state(l),r=await a.manager.api.post('/api/scoring/config',{data:{...writes[0].data(l),role:'commissioner',user_id:a.commissioner.id,commissioner_id:a.manager.id,is_admin:true}});
  await evidence(info,'escalation-response',{status:r.status(),body:await r.text()});expect(await state(l)).toEqual(before);expect([403,404]).toContain(r.status());
});
test('P11 revoked commissioner token loses mutation authority immediately',async({},info)=>{
  const fresh=await league(a);await database(db=>db.collection('leagues').updateOne({_id:new ObjectId(fresh.id)},{$set:{commissioner_id:a.manager2.id}}));
  const before=await state(fresh),r=await a.commissioner.api.post('/api/scoring/config',{data:writes[0].data(fresh)});
  await evidence(info,'revoked-commissioner-response',{status:r.status(),body:await r.text()});expect(await state(fresh)).toEqual(before);expect([403,404]).toContain(r.status());
});
for(const [name,url] of reads)test(`P11 removed member denied ${name}`,async({},info)=>{
  const fresh=await league(a);await database(db=>db.collection('teams').updateMany({league_id:fresh.id,owner_id:a.manager.id},{$set:{owner_id:a.commissioner.id}}));
  const r=await a.manager.api.get(url(fresh));await evidence(info,'revoked-member-response',{status:r.status(),body:await r.text()});expect([403,404]).toContain(r.status());
});
