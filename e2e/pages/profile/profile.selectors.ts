import type { Page } from '@playwright/test';
export const profileSelectors = (page: Page) => ({
  root: page.getByTestId('profile-page'),
  trophyCase: page.getByTestId('profile-trophy-case'),
  earnedChampionships: page.getByTestId(/^trophy-championship-/),
  championshipXp: page.getByTestId('profile-page').getByText('500 XP × 0.5 = 250 XP'),
  championships: page.getByTestId('stat-championships'),
  initialXP: page.getByText('0 / 150 XP to next level', {exact:true}),
  empty: page.getByText('No teams yet. This user is just getting started.', {exact:true}),
  failed: page.getByText('Could not load profile', {exact:true}),
  missing: page.getByText('User not found', {exact:true}),
});
