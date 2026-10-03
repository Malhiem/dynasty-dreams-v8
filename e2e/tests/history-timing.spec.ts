import {test,expect} from '@playwright/test';
import {actors,dispose,league,type Actors} from '../support/access-history';
import {timingFixture,timingTotals} from '../support/history-timing';
let a:Actors;
test.beforeAll(async()=>{a=await actors();});
test.afterAll(async()=>{if(a)await dispose(a);});
const expected=(format:string,values:number[])=>({daily:values,calculated:values,...(format==='rotisserie'?{roto:values}:{})});
for(const format of ['h2h-points','h2h-categories','rotisserie']){
 test(`R05 ${format} exact ownership boundary credits the incoming owner only`,async({},info)=>{
  const l=await league(a,format);
  await timingFixture(l,'2026-11-01','2026-11-01T12:00:00Z',[
   {start:'2026-11-01T11:59:59.999Z',goals:2},
   {start:'2026-11-01T12:00:00Z',goals:3},
   {start:'2026-11-01T12:00:00.001Z',goals:5},
  ]);
  expect(await timingTotals(a,l,format,1,info)).toEqual(expected(format,[2,8]));
 });
 for(const position of ['bench','forward'] as const)test(`R05 ${format} exact lineup boundary applies new ${position} status`,async({},info)=>{
  const l=await league(a,format);
  await timingFixture(l,'2026-11-01','2026-11-01T12:00:00Z',[
   {start:'2026-11-01T11:59:59.999Z',goals:2},
   {start:'2026-11-01T12:00:00Z',goals:3},
   {start:'2026-11-01T12:00:00.001Z',goals:5},
  ],position);
  expect(await timingTotals(a,l,format,1,info)).toEqual(expected(format,[position==='bench'?2:8,0]));
 });
 test(`R13 ${format} midgame transfer and later correction retain puck-drop owner`,async({},info)=>{
  const l=await league(a,format);
  const before={start:'2026-11-01T11:00:00Z',goals:2,updated:'2026-11-01T13:00:00Z'};
  await timingFixture(l,'2026-11-01','2026-11-01T12:00:00Z',[before]);
  expect(await timingTotals(a,l,format,1,info)).toEqual(expected(format,[2,0]));
  await timingFixture(l,'2026-11-01','2026-11-01T12:00:00Z',[
   {...before,goals:5,updated:'2026-11-02T15:00:00Z'},
   {start:'2026-11-01T16:00:00Z',goals:7,updated:'2026-11-02T17:00:00Z'},
  ]);
  for(let i=0;i<2;i++)expect(await timingTotals(a,l,format,1,info)).toEqual(expected(format,[5,7]));
 });
 for(const scenario of [
  {name:'spring-forward',day:'2026-03-08',next:'2026-03-09',transfer:'2026-03-08T07:00:00Z',first:'2026-03-08T01:30:00-05:00',second:'2026-03-08T03:30:00-04:00'},
  {name:'fall-back repeated hour',day:'2026-11-01',next:'2026-11-02',transfer:'2026-11-01T06:00:00Z',first:'2026-11-01T01:30:00-04:00',second:'2026-11-01T01:30:00-05:00'},
 ])test(`R16 ${format} ${scenario.name} respects absolute time and UTC period boundaries`,async({},info)=>{
  const l=await league(a,format),start=new Date(scenario.day+'T00:00:00Z').getTime();
  await timingFixture(l,scenario.day,scenario.transfer,[
   {start:new Date(start-1).toISOString(),goals:16},
   {start:scenario.day+'T00:00:00Z',goals:1},
   {start:scenario.first,goals:2,updated:scenario.next+'T12:00:00Z'},
   {start:scenario.second,goals:4,updated:scenario.next+'T12:00:00Z'},
   {start:scenario.day+'T23:59:59.999Z',goals:8},
   {start:scenario.next+'T00:00:00Z',goals:32},
  ]);
  expect(await timingTotals(a,l,format,1,info)).toEqual(expected(format,[3,12]));
  expect(await timingTotals(a,l,format,2,info)).toEqual(expected(format,[0,32]));
 });
}
