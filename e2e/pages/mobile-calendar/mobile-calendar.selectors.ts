import type {Page} from '@playwright/test';
export const selectors=(page:Page)=>({
 schedules:()=>page.getByRole('tab',{name:'Schedules',exact:true}),
 calendar:()=>page.getByTestId('scheduler'),
 interval:()=>page.getByLabel('Scoring Period Interval',{exact:true}),
 startDay:()=>page.getByLabel('Scoring Period Start Day',{exact:true}),
});
