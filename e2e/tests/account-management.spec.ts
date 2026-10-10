import { expect,test } from '@playwright/test';
import { AccountPage } from '../pages/account/account.page';
import { account,seedAccount,mail,database,allowVerification,expireVerification } from '../support/account';
import { ObjectId } from 'mongodb';

test('A01 browser signup, generated verification link and fresh-session login',async({page,browser})=>{
  const user=account();const app=new AccountPage(page);await app.goto('/register');await app.signup(user);
  await expect(page).toHaveURL(/\/dashboard/);
  await page.reload();await expect(page).toHaveURL(/\/dashboard/);
  const link=await mail(user.email,'Verify your email');await app.goto(link.pathname+link.search);await app.ui.verify.click();
  await expect(app.ui.status).toContainText('Email verified');
  const fresh=await browser.newContext();try{const p=await fresh.newPage();const other=new AccountPage(p);await other.goto('/login');await other.login(user);await expect(p).toHaveURL(/\/dashboard/);await other.goto('/profile/edit');await expect(other.ui.verified).toBeVisible();}finally{await fresh.close();}
});
test('A02 signup validation and generic collision errors',async({page})=>{
  const user=await seedAccount();const app=new AccountPage(page);await app.goto('/register');
  await app.ui.username.fill('ab');await app.ui.email.fill(user.email);await app.ui.password.fill('weak');await app.ui.confirm.fill('weak');await expect(app.ui.signup).toBeDisabled();
  await app.signup({...user,username:user.username.toUpperCase()});await expect(app.ui.signupError).toHaveText('Email or username is already in use');
  await expect(app.ui.email).toHaveValue(user.email);
});
test('A03 full recovery journey, old-password rejection and reset-link replay',async({page})=>{
  const user=await seedAccount();const app=new AccountPage(page);await app.goto('/login');await page.getByRole('link',{name:'Forgot password?'}).click();
  await app.ui.recoveryEmail.fill(user.email);await app.ui.requestReset.click();await expect(app.ui.status).toContainText('If an account exists');
  const link=await mail(user.email,'Reset your password');await app.goto(link.pathname+link.search);await app.reset('RecoveryPassword2026!');await expect(app.ui.status).toContainText('Password reset successfully');
  await app.goto('/login');await app.login(user);await expect(app.ui.loginError).toHaveText('Invalid email or password');
  await app.login({...user,password:'RecoveryPassword2026!'});await expect(page).toHaveURL(/\/dashboard/);
  await app.goto(link.pathname+link.search);await app.reset('OtherPassword2026!');await expect(app.ui.alert).toContainText('Invalid or expired token');
});
test('A04 expired verification and invalid recovery links offer recovery',async({page})=>{
  const user=await seedAccount();await expireVerification(user.id);const link=await mail(user.email,'Verify your email');const app=new AccountPage(page);
  await app.goto(link.pathname+link.search);await app.ui.verify.click();await expect(app.ui.alert).toContainText('Invalid or expired verification link');
  await app.goto('/reset-password?token=invalid');await app.reset('RecoveryPassword2026!');await expect(app.ui.alert).toContainText('Invalid or expired token');
  await expect(page.getByRole('link',{name:'Request a new reset link'})).toBeVisible();
});
test('A05 username edit persists after reload and a new session',async({page,browser})=>{
  const user=await seedAccount();const app=new AccountPage(page);await app.goto('/login');await app.login(user);await expect(page).toHaveURL(/\/dashboard/);
  await app.goto('/profile/edit');await expect(app.ui.profileUsername).toHaveValue(user.username);
  const name=account().username;await app.ui.profileUsername.fill(name);await app.ui.profileSave.click();await expect(page).toHaveURL(new RegExp('/u/'+name.replaceAll('.','\\.')));
  await app.goto('/profile/edit');await expect(app.ui.profileUsername).toHaveValue(name);await page.reload();await expect(app.ui.profileUsername).toHaveValue(name);
  const context=await browser.newContext();try{const p=await context.newPage();const other=new AccountPage(p);await other.goto('/login');await other.login(user);await expect(p).toHaveURL(/\/dashboard/);await other.goto('/profile/edit');await expect(other.ui.profileUsername).toHaveValue(name);}finally{await context.close();}
});
test('A06 email edit requires password and confirmation before changing login',async({page})=>{
  const user=await seedAccount();await allowVerification(user.id);const app=new AccountPage(page);await app.goto('/login');await app.login(user);await expect(page).toHaveURL(/\/dashboard/);
  await app.goto('/profile/edit');await expect(app.ui.profileEmail).toHaveValue(user.email);
  const target=account().email;await app.ui.profileEmail.fill(target);await app.ui.emailPassword.fill(user.password);
  const saved=page.waitForResponse(r=>r.url().endsWith('/api/users/me/profile') && r.request().method()==='PUT');await app.ui.profileSave.click();expect((await saved).status()).toBe(200);
  expect((await page.request.get('/api/auth/me')).ok()).toBeTruthy();expect((await (await page.request.get('/api/auth/me')).json()).email).toBe(user.email);
  const link=await mail(target,'Verify your email');await app.goto(link.pathname+link.search);await app.ui.verify.click();await expect(app.ui.status).toContainText('Email verified');
  expect((await (await page.request.get('/api/auth/me')).json()).email).toBe(target);
});
test('A07 password change checks current password and signs out existing sessions',async({page,browser})=>{
  const user=await seedAccount();const app=new AccountPage(page);await app.goto('/login');await app.login(user);await expect(page).toHaveURL(/\/dashboard/);await app.goto('/profile/edit');await expect(app.ui.profileEmail).toHaveValue(user.email);
  await app.change('WrongPassword2026!','ChangedPassword2026!');await expect(app.ui.alert).toHaveText('Current password is incorrect');
  await app.change(user.password,'ChangedPassword2026!');await expect(page).toHaveURL(/\/login/);
  await app.login(user);await expect(app.ui.loginError).toHaveText('Invalid email or password');await app.login({...user,password:'ChangedPassword2026!'});await expect(page).toHaveURL(/\/profile\/edit/);await expect(app.ui.profileEmail).toHaveValue(user.email);
});
test('A08 expired access cookie refreshes without losing the user',async({page,context})=>{
  const user=await seedAccount();const app=new AccountPage(page);await app.goto('/login');await app.login(user);await expect(page).toHaveURL(/\/dashboard/);
  const cookies=await context.cookies();await context.addCookies(cookies.filter(c=>c.name==='access_token').map(c=>({...c,value:'expired-access-token'})));
  await page.reload();await expect(page).toHaveURL(/\/dashboard/);expect((await page.request.get('/api/auth/me')).status()).toBe(200);
});
test('A09 revoked account leaves protected page on reload',async({page})=>{
  const user=await seedAccount();const app=new AccountPage(page);await app.goto('/login');await app.login(user);await expect(page).toHaveURL(/\/dashboard/);
  await database(async db=>{await db.collection('users').updateOne({_id:new ObjectId(user.id)},{$set:{status:'deactivated',is_active:false}});});
  await page.reload();await expect(page).toHaveURL(/\/login/);expect((await page.request.get('/api/auth/me')).status()).toBe(401);
});
for(const path of ['/register','/login','/forgot-password','/reset-password?token=invalid']){
  test(`A10 ${path} fits 320px and exposes labelled fields`,async({page})=>{
    await page.setViewportSize({width:320,height:800});const app=new AccountPage(page);await app.goto(path);
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=document.documentElement.clientWidth)).toBeTruthy();
    const field=path==='/register'?app.ui.username:path==='/login'?app.ui.loginEmail:path==='/forgot-password'?app.ui.recoveryEmail:app.ui.newPassword;
    await field.focus();await expect(field).toBeFocused();await field.press('Tab');await expect(field).not.toBeFocused();
    if(path==='/register' || path==='/login')await expect(page.getByRole('button',{name:'Show password'})).toBeVisible();
  });
}


test('A11 logout propagates to another tab and protects reload/back navigation',async({page,context})=>{
  const user=await seedAccount();const app=new AccountPage(page);await app.goto('/login');await app.login(user);await expect(page).toHaveURL(/\/dashboard/);
  const other=await context.newPage();await other.goto('/dashboard');await expect(other).toHaveURL(/\/dashboard/);
  await page.getByRole('button',{name:'Sign out',exact:true}).click();await expect(page).toHaveURL(/\/login/);await expect(other).toHaveURL(/\/login/);
  await page.reload();await expect(page).toHaveURL(/\/login/);await app.goto('/dashboard');await expect(page).toHaveURL(/\/login/);
  expect((await page.request.get('/api/auth/me')).status()).toBe(401);
});

test('A12 merged-source account loses browser and API access',async({page})=>{
  const {request}=await import('@playwright/test');const source=await seedAccount();const target=await seedAccount();
  const app=new AccountPage(page);await app.goto('/login');await app.login(source);await expect(page).toHaveURL(/\/dashboard/);
  const admin=await request.newContext({baseURL:'http://web'});
  try{
    const login=await admin.post('/api/auth/login',{data:{email:'admin@e2e.dynastydreams.com',password:'e2e-admin-password'}});expect(login.ok()).toBeTruthy();
    const merge=await admin.post(`/api/admin/platform/users/${target.id}/merge-accounts`,{data:{source_user_id:source.id,reason:'Disposable acceptance fixture'}});expect(merge.ok()).toBeTruthy();
  }finally{await admin.dispose();}
  await page.reload();await expect(page).toHaveURL(/\/login/);expect((await page.request.get('/api/auth/me')).status()).toBe(401);
  await app.login(source);await expect(app.ui.loginError).toBeVisible();await expect(page).toHaveURL(/\/login/);
});
