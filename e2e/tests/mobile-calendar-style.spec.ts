import {test,expect} from '@playwright/test';
import {actors,dispose} from '../support/access-history';
import {fixture} from '../support/h2h';
import {MobileCalendarPage} from '../pages/mobile-calendar/mobile-calendar.page';
function luminance(color:string){const rgb=color.match(/[\d.]+/g)!.slice(0,3).map(Number).map(n=>n/255).map(n=>n<=0.04045?n/12.92:((n+0.055)/1.055)**2.4);return rgb[0]*0.2126+rgb[1]*0.7152+rgb[2]*0.0722;}
test('calendar native values retain contrast and usable controls in both themes and enlarged text',async({page},info)=>{
 const a=await actors();
 try{
  const league=await fixture(a.commissioner.api,'h2h-points');await page.context().addCookies((await a.commissioner.api.storageState()).cookies);
  const calendar=new MobileCalendarPage(page);await calendar.open(league.id);await expect(calendar.calendar()).toBeVisible();
  const measured=[];
  for(const light of [false,true]){
   await calendar.theme(light);const style=await calendar.appearance();const a=luminance(style.color),b=luminance(style.background);const contrast=(Math.max(a,b)+0.05)/(Math.min(a,b)+0.05);
   measured.push({theme:light?'light':'dark',...style,contrast});expect(contrast).toBeGreaterThanOrEqual(4.5);expect(style.height).toBeGreaterThanOrEqual(44);expect(style.colorScheme).toBe(light?'light':'dark');
   await calendar.interval().selectOption('biweekly');await expect(calendar.interval()).toHaveValue('biweekly');await calendar.interval().selectOption('weekly');
  }
  await calendar.scaleText();await expect(calendar.interval()).toBeVisible();await calendar.startDay().selectOption('2');await expect(calendar.startDay()).toHaveValue('2');
  const box=await calendar.interval().boundingBox();expect(box!.x).toBeGreaterThanOrEqual(0);expect(box!.x+box!.width).toBeLessThanOrEqual(page.viewportSize()!.width);
  await info.attach('calendar-contrast-measurements',{body:JSON.stringify(measured,null,2),contentType:'application/json'});
 }finally{await dispose(a);}
});
