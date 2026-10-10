import type { Page } from '@playwright/test';
export const profileActions = (page: Page) => ({
  open: (username: string) => page.goto(`/u/${encodeURIComponent(username)}`),
  reload: () => page.reload(),
});
