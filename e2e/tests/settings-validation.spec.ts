import {test,expect} from '@playwright/test';
import {actors,dispose,league} from '../support/access-history';
import {result} from '../support/h2h';
import {PermissionPage} from '../pages/permission-ui/permission-ui.page';
test('V01 API rejects and does not store weekly claim limit above advertised maximum',async({},info)=>{
 const a=await actors();try{const l=await league(a);const before=await result(await a.commissioner.api.get(`/api/leagues/${l.id}/transactions-config`));
 const response=await a.commissioner.api.put(`/api/leagues/${l.id}/transactions-config`,{data:{claim_limits:{season:{total:12},week:{total:101}}}});
 const after=await result(await a.commissioner.api.get(`/api/leagues/${l.id}/transactions-config`));
 await info.attach('invalid-claim-limit',{body:JSON.stringify({status:response.status(),body:await response.json(),before,after}),contentType:'application/json'});
 expect(after.claim_limits.week.total,'Invalid weekly limit must not become 101').not.toBe(101);expect([400,422]).toContain(response.status());}finally{await dispose(a);}
});
test('V02 blank enabled scoring weight does not silently overwrite persisted weight with zero',async({page},info)=>{
 const a=await actors();try{const l=await league(a);await page.context().addCookies((await a.commissioner.api.storageState()).cookies);const p=new PermissionPage(page);await p.goto(l.id);await expect(p.selectors.goals(page)).toHaveValue('1');
 await p.selectors.goals(page).fill('');await p.selectors.save(page).click();await expect(page.getByRole('alert')).toContainText('Enter a valid number');
 const after=await result(await a.commissioner.api.get(`/api/scoring/config?league_id=${l.id}`));await info.attach('blank-score',{body:JSON.stringify({after}),contentType:'application/json'});
 expect(after.skater_scoring.goals).toBe(1);}finally{await dispose(a);}
});
