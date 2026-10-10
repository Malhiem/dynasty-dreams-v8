import type { Page } from '@playwright/test';
import { accountSelectors } from './account.selectors';
export interface Account {username:string;email:string;password:string;}
export async function signup(page:Page,user:Account){const ui=accountSelectors(page);await ui.username.fill(user.username);await ui.email.fill(user.email);await ui.password.fill(user.password);await ui.confirm.fill(user.password);await ui.signup.click();}
export async function login(page:Page,user:Account){const ui=accountSelectors(page);await ui.loginEmail.fill(user.email);await ui.loginPassword.fill(user.password);await ui.remember.check();await ui.loginSubmit.click();}
export async function resetPassword(page:Page,password:string){const ui=accountSelectors(page);await ui.newPassword.fill(password);await ui.confirmPassword.fill(password);await ui.reset.click();}
export async function changePassword(page:Page,current:string,password:string){const ui=accountSelectors(page);await ui.current.fill(current);await ui.securityNew.fill(password);await ui.securityConfirm.fill(password);await ui.change.click();}
