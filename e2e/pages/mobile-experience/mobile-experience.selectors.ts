import type {Page} from '@playwright/test';
export const mobileExperienceSelectors=(page:Page)=>({
 dashboard:page.getByTestId('dashboard-page'),
 menu:page.getByRole('button',{name:'Toggle navigation menu',exact:true}),
 drawer:page.getByRole('dialog').filter({has:page.getByRole('link',{name:'User Dashboard',exact:true})}),
 chat:page.getByTestId('chat-page'),input:page.getByTestId('chat-message-input'),send:page.getByTestId('chat-send-btn'),
 bannerDismiss:page.getByTestId('pwa-install-banner-dismiss'),notifications:page.getByTestId('notifications-panel'),notificationButton:page.getByTestId('notifications-btn'),
 message:(id:string)=>page.getByTestId(`chat-message-${id}`),notification:(id:string)=>page.getByTestId(`notification-item-${id}`),
});
