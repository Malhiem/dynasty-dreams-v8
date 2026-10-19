import {test,expect} from '@playwright/test';
import {actors,dispose} from '../support/access-history';
import {salaryLeague} from '../support/salary';
import {SalaryPage} from '../pages/salary/salary.page';
for(const viewport of [{width:390,height:500},{width:430,height:350}]){
 test(`mobile settings picker stays reachable after reload at ${viewport.width}x${viewport.height}`,async({page},info)=>{
  await page.setViewportSize(viewport);const a=await actors();
  try{
   const league=await salaryLeague(a);await page.context().addCookies((await a.commissioner.api.storageState()).cookies);const salary=new SalaryPage(page);await salary.goto(league.id);
   await salary.selectors.saveCap(page).scrollIntoViewIfNeeded();await page.reload();
   const picker=salary.selectors.mobilePicker(page);await picker.selectOption('admin');await expect(picker).toHaveValue('admin');await picker.selectOption('salary-cap-contracts');
   await expect(picker).toHaveValue('salary-cap-contracts');await expect(salary.selectors.amount(page)).toHaveValue('100,000,000');
   await picker.scrollIntoViewIfNeeded();const box=await picker.boundingBox();expect(box!.height).toBeGreaterThanOrEqual(44);expect(box!.x).toBeGreaterThanOrEqual(0);expect(box!.x+box!.width).toBeLessThanOrEqual(viewport.width);
   await info.attach('bounded-settings-picker',{body:await page.screenshot(),contentType:'image/png'});
  }finally{await dispose(a);}
 });
}
