import type {Page} from '@playwright/test';
import {mobileExperienceSelectors} from './mobile-experience.selectors';
export async function dismissInstallIfPresent(page:Page){const ui=mobileExperienceSelectors(page);if(await ui.bannerDismiss.isVisible())await ui.bannerDismiss.click();}
export async function viaMenu(page:Page,name:string){const ui=mobileExperienceSelectors(page);await ui.menu.click();await ui.drawer.getByRole('link',{name,exact:true}).click();}
