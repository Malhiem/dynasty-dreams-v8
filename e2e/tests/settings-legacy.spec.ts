import {test,expect} from '@playwright/test';
import {ObjectId} from 'mongodb';
import {actors,dispose,league} from '../support/access-history';
import {database,result} from '../support/h2h';
test('Legacy out-of-range claim settings remain readable and can be corrected',async()=>{
 const a=await actors();try{const l=await league(a);await database(db=>db.collection('leagues').updateOne({_id:new ObjectId(l.id)},{$set:{transactions_config:{claim_limits:{week:{total:101}}}}}));
 const stored=await result(await a.commissioner.api.get(`/api/leagues/${l.id}/transactions-config`));expect(stored.claim_limits.week.total).toBe(101);
 await result(await a.commissioner.api.put(`/api/leagues/${l.id}/transactions-config`,{data:{claim_limits:{week:{total:100}}}}));expect((await result(await a.commissioner.api.get(`/api/leagues/${l.id}/transactions-config`))).claim_limits.week.total).toBe(100);
 }finally{await dispose(a);}
});
