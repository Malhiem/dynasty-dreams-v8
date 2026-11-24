import {test,expect} from '@playwright/test';
import {actors,dispose,type Actors} from '../support/access-history';
import {salaryLeague,settings} from '../support/salary';

// No cap, no salaries: league views hide player salary when the cap is off.
let a:Actors;test.beforeAll(async()=>{a=await actors();});test.afterAll(async()=>{if(a)await dispose(a);});

async function openRoster(page:any,l:any){
  await page.context().addCookies((await a.manager.api.storageState()).cookies);
  await page.addInitScript((id:string)=>localStorage.setItem('dd_active_league_id',id),l.id);
  await page.goto('/team');
  await expect(page.getByTestId(`roster-trade-${l.teams[0].players[0]}`).or(page.locator('table').first())).toBeVisible();
}
const capHeader=(page:any)=>page.locator('table thead th',{hasText:/^Cap$/});

test('roster shows the Cap column and Cap Hit view when the league has a cap',async({page},info)=>{
  const l=await salaryLeague(a);await openRoster(page,l);
  await expect(capHeader(page).first()).toBeVisible();
  await expect(page.getByTestId('team-salary-cap-card')).toBeVisible();
  await expect(page.locator('a[href="/salary-cap"]').first()).toBeVisible();
  await expect(page.getByTestId('team-retention-no_preference')).toBeVisible();
  await page.screenshot({path:info.outputPath('roster-cap-on.png'),fullPage:true});
});

test('roster hides player salary and the Cap Hit view when the league has no cap',async({page},info)=>{
  const l=await salaryLeague(a);
  await a.commissioner.api.put(`/api/leagues/${l.id}/admin/cap-settings`,{data:{salary_cap_enabled:false}});
  await openRoster(page,l);
  await expect(page.locator('table thead th').first()).toBeVisible();
  await expect(capHeader(page)).toHaveCount(0);
  await expect(page.locator('table').first()).not.toContainText(/\$\d+(\.\d+)?M/);
  await expect(page.getByTestId('team-salary-cap-card')).toHaveCount(0);
  await expect(page.locator('a[href="/salary-cap"]')).toHaveCount(0);
  await expect(page.getByTestId('team-retention-no_preference')).toHaveCount(0);
  await page.screenshot({path:info.outputPath('roster-cap-off.png'),fullPage:true});
});
