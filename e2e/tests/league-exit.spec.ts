import {test,expect} from '@playwright/test';
import {ObjectId} from 'mongodb';
import {actors,dispose,league} from '../support/access-history';
import {database,result} from '../support/h2h';
test('last commissioner can leave immediately with vacancies and one audited exit',async()=>{
 const a=await actors();try{
  const l=await league(a),other=await league(a);const url=`/api/leagues/${l.id}/leave`;
  const before=await database(async db=>db.collection('teams').find({league_id:l.id}).sort({_id:1}).toArray());
  await database(async db=>{await db.collection('leagues').updateOne({_id:new ObjectId(l.id)},{$set:{admin_ids:null,co_commissioners:[new ObjectId(a.commissioner.id),a.manager.id],owner_id:a.commissioner.id}});await db.collection('teams').updateOne({_id:new ObjectId(l.teams[0].id)},{$set:{co_owner_ids:[a.commissioner.id,a.manager2.id]}});});
  const data={expected_user_id:a.commissioner.id};
  for(const actor of [a.anonymous,a.expired])expect((await actor.api.post(url,{data})).status()).toBe(401);
  expect((await a.outsider.api.post(url,{data:{expected_user_id:a.outsider.id}})).status()).toBe(403);
  expect((await a.manager.api.post(url,{data})).status()).toBe(409);
  const responses=await Promise.all([a.commissioner.api.post(url,{data}),a.commissioner.api.post(url,{data})]);for(const r of responses)expect((await result(r)).status).toBe('left');
  expect((await a.commissioner.api.get(`/api/leagues/${l.id}`)).status()).toBe(403);expect((await a.commissioner.api.get(`/api/leagues/${other.id}`)).status()).toBe(200);
  await database(async db=>{
   const saved=await db.collection('leagues').findOne({_id:new ObjectId(l.id)});expect(saved!.commissioner_id).toBe('');expect(saved!.co_commissioners).toEqual([a.manager.id]);expect(saved!.admin_ids).toEqual([]);
   const after=await db.collection('teams').find({league_id:l.id}).sort({_id:1}).toArray();for(let i=0;i<after.length;i++){expect(after[i].roster).toEqual(before[i].roster);expect(after[i].lineup).toEqual(before[i].lineup);if(before[i].owner_id===a.commissioner.id)expect(after[i].ownership_vacant).toBe(true);else expect(after[i].owner_id).toBe(before[i].owner_id);expect(after[i].co_owner_ids||[]).not.toContain(a.commissioner.id);}
   expect(await db.collection('league_membership_events').countDocuments({league_id:l.id,user_id:a.commissioner.id,type:'left'})).toBe(1);
  });
 }finally{await dispose(a);}
});
test('co-owner exit removes only their roles and retry cannot leave another account',async()=>{
 const a=await actors();try{
  const l=await league(a);await database(async db=>{await db.collection('teams').updateOne({_id:new ObjectId(l.teams[0].id)},{$set:{co_owner_ids:[a.outsider.id,a.manager2.id]}});});
  const url=`/api/leagues/${l.id}/leave`;await result(await a.outsider.api.post(url,{data:{expected_user_id:a.outsider.id}}));
  expect((await a.manager.api.post(url,{data:{expected_user_id:a.outsider.id}})).status()).toBe(409);
  await database(async db=>{const team=await db.collection('teams').findOne({_id:new ObjectId(l.teams[0].id)});expect(team!.owner_id).toBe(a.manager.id);expect(team!.co_owner_ids).toEqual([a.manager2.id]);});
 }finally{await dispose(a);}
});
