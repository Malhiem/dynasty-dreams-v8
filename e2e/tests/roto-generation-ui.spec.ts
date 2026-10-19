import {test,expect} from '@playwright/test';
import {actors,dispose} from '../support/access-history';
import {generatedFixture} from '../support/roto-generation';
import {RotoSeasonPage} from '../pages/roto-season/roto-season.page';
test('mobile Rotisserie schedule generates and finalizes real scoring without opponent controls',async({page,context})=>{
 const a=await actors();try{
  const l=await generatedFixture(a.commissioner.api,false);await context.addCookies((await a.commissioner.api.storageState()).cookies);const ui=new RotoSeasonPage(page);await ui.open(l.id);await ui.generate();await expect(ui.controls.finalize()).toBeEnabled();await ui.finalize();await expect(ui.controls.status()).toBeVisible();await expect(ui.controls.finalize()).toBeDisabled();await page.reload();await ui.open(l.id);await expect(ui.controls.finalize()).toBeDisabled();
 }finally{await dispose(a);}
});
