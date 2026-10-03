import type {Page} from '@playwright/test';
export const selectors={
 points:(p:Page,id:string)=>p.getByTestId(`scoring-points-${id}`),
 category:(p:Page,id:string)=>p.getByTestId(`scoring-row-${id}`).getByRole('checkbox'),
 error:(p:Page,text:string)=>p.getByRole('alert').filter({hasText:text}),
 retry:(p:Page)=>p.getByRole('button',{name:'Retry loading scoring'}),
 denied:(p:Page)=>p.getByRole('alert').filter({hasText:'Only the league commissioner can administer this league.'}),
 heading:(p:Page)=>p.getByRole('heading',{name:'League Administration',exact:true}),
 scoring:(p:Page)=>p.getByTestId('commissioner-scoring-tab'),
 goals:(p:Page)=>p.getByTestId('scoring-points-goals'),
 save:(p:Page)=>p.getByTestId('scoring-save-btn'),
 complete:(p:Page)=>p.getByTestId('health-complete-season-btn'),
};
