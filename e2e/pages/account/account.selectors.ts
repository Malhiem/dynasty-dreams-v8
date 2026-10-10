import type { Page } from '@playwright/test';
export const accountSelectors = (page:Page) => ({
  username:page.getByTestId('register-username'),email:page.getByTestId('register-email'),password:page.getByTestId('register-password'),confirm:page.getByTestId('register-confirm-password'),signup:page.getByTestId('register-submit'),
  signupError:page.getByTestId('register-error'),loginEmail:page.getByTestId('login-email'),loginPassword:page.getByTestId('login-password'),loginSubmit:page.getByTestId('login-submit'),remember:page.getByTestId('login-remember-me'),loginError:page.getByTestId('login-error'),
  recoveryEmail:page.getByLabel('Email',{exact:true}),requestReset:page.getByRole('button',{name:'Send reset link',exact:true}),newPassword:page.getByLabel('New password',{exact:true}),confirmPassword:page.getByLabel('Confirm password',{exact:true}),reset:page.getByRole('button',{name:'Reset password',exact:true}),
  verify:page.getByRole('button',{name:'Verify email',exact:true}),status:page.getByRole('status'),alert:page.getByRole('alert'),
  profileUsername:page.getByTestId('edit-profile-username'),profileEmail:page.getByTestId('edit-profile-email'),profileSave:page.getByTestId('edit-profile-save'),emailPassword:page.getByLabel('Current password to change email'),
  current:page.getByLabel('Current password',{exact:true}),securityNew:page.getByLabel('New password',{exact:true}),securityConfirm:page.getByLabel('Confirm new password'),change:page.getByRole('button',{name:'Change password',exact:true}),
  verified:page.getByText('Email verified',{exact:true}),
  logout:page.getByRole('button',{name:/log out|sign out/i}),
});
