import type { Page } from '@playwright/test';
import { accountSelectors } from './account.selectors';
import { signup,login,resetPassword,changePassword,type Account } from './account.actions';
export class AccountPage {
  readonly ui;constructor(readonly page:Page){this.ui=accountSelectors(page);}
  goto(path:string){return this.page.goto(path);}
  signup(user:Account){return signup(this.page,user);}
  login(user:Account){return login(this.page,user);}
  reset(password:string){return resetPassword(this.page,password);}
  change(current:string,password:string){return changePassword(this.page,current,password);}
}
