import {test,expect} from '@playwright/test';
import {actors,dispose,league} from '../support/access-history';
import {result} from '../support/h2h';
test('candidate access authenticates before lookup and requires league membership',async()=>{
 const a=await actors();try{
  const l=await league(a);const draft=await result(await a.commissioner.api.post('/api/drafts',{data:{league_id:l.id,name:'Candidate access',total_rounds:5,time_per_pick:3600,player_criteria:['all']}}));
  const id=draft.id||draft._id;const url=`/api/drafts/${id}/eligible-players?limit=1`;
  expect((await a.anonymous.api.get(url)).status()).toBe(401);
  expect((await a.anonymous.api.get('/api/drafts/000000000000000000000000/eligible-players')).status()).toBe(401);
  expect((await a.outsider.api.get(url)).status()).toBe(403);
  for(const actor of [a.commissioner,a.manager,a.manager2])expect((await actor.api.get(url)).ok()).toBeTruthy();
 }finally{await dispose(a);}
});
