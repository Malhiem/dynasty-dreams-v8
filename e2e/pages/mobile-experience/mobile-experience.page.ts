import type {Page} from '@playwright/test';
import {mobileExperienceSelectors} from './mobile-experience.selectors';
import * as actions from './mobile-experience.actions';
export class MobileExperiencePage {
 constructor(readonly page:Page){}
 get ui(){return mobileExperienceSelectors(this.page);}
 get dashboard(){return this.ui.dashboard;} get menu(){return this.ui.menu;} get drawer(){return this.ui.drawer;}
 get chat(){return this.ui.chat;} get input(){return this.ui.input;} get send(){return this.ui.send;}
 get bannerDismiss(){return this.ui.bannerDismiss;} get notifications(){return this.ui.notifications;} get notificationButton(){return this.ui.notificationButton;}
 message(id:string){return this.ui.message(id);} notification(id:string){return this.ui.notification(id);}
 goto(path:string){return this.page.goto(path);}
 dismissInstallIfPresent(){return actions.dismissInstallIfPresent(this.page);}
 viaMenu(name:string){return actions.viaMenu(this.page,name);}
}
