import { expect, test } from "@playwright/test";
import { LoginPage } from "../pages/login/login.page";
import { LeagueScoringPage } from "../pages/league-scoring/league-scoring.page";
import { createCondensedFixture, seedPlayoffWindow } from "../support/rotisserie";

test.beforeEach(async ({ page }) => {
  const login = new LoginPage(page);
  await login.goto();
  await login.logIn({ email: process.env.E2E_ADMIN_EMAIL || "admin@e2e.dynastydreams.com",
    password: process.env.E2E_ADMIN_PASSWORD || "e2e-admin-password" });
  await expect(page).toHaveURL(/\/dashboard(?:\?|$)/);
});

test("Condensed fresh-total toggle and eight seed bonuses save through the UI", async ({ page }) => {
  const league = await createCondensedFixture(page.request);
  const scoring = new LeagueScoringPage(page);
  await scoring.structure(league.id);
  await expect(scoring.selectors.freshTotals(page)).toBeChecked();
  for (const fresh of [false, true]) {
    await scoring.selectors.freshTotals(page).setChecked(fresh);
    for (let seed = 1; seed <= 8; seed++) await scoring.selectors.seedBonus(page, seed).fill(String(seed <= 4 ? 2 * (5 - seed) : 0));
    const saved = page.waitForResponse(r => r.request().method() === "PUT" && new URL(r.url()).pathname === `/api/leagues/${league.id}`);
    await scoring.selectors.playoffSave(page).click();
    expect((await saved).ok()).toBeTruthy();
    const response = await page.request.get(`/api/leagues/${league.id}`);
    expect(response.ok()).toBeTruthy();
    const config = await response.json();
    expect(config).toMatchObject({ playoff_format: "condensed_roto", playoff_roto_fresh_totals: fresh,
      playoff_roto_seed_bonuses: { "1": 8, "2": 6, "3": 4, "4": 2 } });
    for (let seed = 5; seed <= 8; seed++) expect(config.playoff_roto_seed_bonuses[String(seed)] ?? 0).toBe(0);
    await page.reload();
    await expect(scoring.selectors.freshTotals(page)).toBeChecked({ checked: fresh });
    for (let seed = 1; seed <= 8; seed++) await expect(scoring.selectors.seedBonus(page, seed)).toHaveValue(String(seed <= 4 ? 2 * (5 - seed) : 0));
  }
});

test("Explicit playoff period ranks eight teams and sums goals and assists correctly", async ({ page }, info) => {
  const league = await createCondensedFixture(page.request);
  const response = await page.request.get(`/api/leagues/${league.id}/roto/matchup?period=26`);
  expect(response.ok()).toBeTruthy();
  const result = await response.json();
  await info.attach("period-26", { body: JSON.stringify(result, null, 2), contentType: "application/json" });
  expect(result.num_teams).toBe(8);
  expect(result.categories.map((c: { key: string }) => c.key)).toEqual(["goals", "assists"]);
  for (const [i, team] of league.teams.entries()) {
    for (const cat of result.categories) {
      expect(cat.team_stats[team.id]).toBe(2 * (i + 1));
      expect(cat.ranks[team.id]).toBe(8 - i);
      expect(cat.points[team.id]).toBe(i + 1);
    }
    // Raw category points only; applied seed bonus is checked independently below.
    expect(result.totals[team.id].total_points).toBe(2 * (i + 1));
  }
});

test("Fresh condensed standings exclude regular-season stats", async ({ page }, info) => {
  const league = await createCondensedFixture(page.request);
  const response = await page.request.get(`/api/leagues/${league.id}/roto/standings`);
  expect(response.ok()).toBeTruthy();
  const result = await response.json();
  await info.attach("fresh-standings", { body: JSON.stringify(result, null, 2), contentType: "application/json" });
  for (const [i, team] of league.teams.entries()) for (const cat of result.categories) {
    expect.soft(cat.team_stats[team.id], `${team.name} ${cat.key} must use playoff stats`).toBe(2 * (i + 1));
  }
});

test("Closed playoff standings apply seed bonuses once across repeated recomputes", async ({ page }, info) => {
  const league = await createCondensedFixture(page.request);
  for (let attempt = 1; attempt <= 2; attempt++) {
    const recompute = await page.request.post(`/api/leagues/${league.id}/roto/recompute`, { data: { period: 26, close: true } });
    expect(recompute.ok()).toBeTruthy();
    const response = await page.request.get(`/api/leagues/${league.id}/roto/standings`);
    expect(response.ok()).toBeTruthy();
    const result = await response.json();
    await info.attach(`bonus-standings-${attempt}`, { body: JSON.stringify(result, null, 2), contentType: "application/json" });
    expect(result.periods_closed).toBe(1);
    for (const [i, team] of league.teams.entries()) {
      const bonus = i < 4 ? 4 - i : 0;
      expect.soft(result.totals[team.id].total_points, `${team.name}: earned ${2*(i+1)} + seed bonus ${bonus}, recompute ${attempt}`).toBe(2*(i+1)+bonus);
    }
  }
});

test("Condensed multiweek playoffs rank combined stats and apply bonuses once", async ({ page }, info) => {
  const league = await createCondensedFixture(page.request);
  await seedPlayoffWindow(league);
  expect((await page.request.put(`/api/leagues/${league.id}`, { data: { playoff_end_week: 27 } })).ok()).toBeTruthy();
  for (const period of [25, 26, 27, 28, 27]) {
    expect((await page.request.post(`/api/leagues/${league.id}/roto/recompute`, { data: { period, close: true } })).ok()).toBeTruthy();
  }
  for (let attempt = 1; attempt <= 2; attempt++) {
    const response = await page.request.get(`/api/leagues/${league.id}/roto/standings`);
    expect(response.ok()).toBeTruthy();
    const result = await response.json();
    await info.attach(`combined-window-${attempt}`, { body: JSON.stringify(result), contentType: "application/json" });
    expect(result.periods_closed).toBe(2);
    expect(result.periods).toEqual([26, 27]);
    for (const [i, team] of league.teams.entries()) {
      for (const cat of result.categories) {
        expect(cat.team_stats[team.id]).toBe(50 - 4 * i);
        expect(cat.ranks[team.id]).toBe(i + 1);
        expect(cat.points[team.id]).toBe(8 - i);
      }
      expect(result.totals[team.id].total_points).toBe(2 * (8 - i) + (i < 4 ? 4 - i : 0));
    }
    expect((await page.request.post(`/api/leagues/${league.id}/roto/recompute`, { data: { period: 27, close: true } })).ok()).toBeTruthy();
  }
});

test("Seed bonus changes condensed playoff champion", async ({ page }, info) => {
  for (const bonus of [0, 15]) {
    const league = await createCondensedFixture(page.request);
    expect((await page.request.put(`/api/leagues/${league.id}`, { data: { playoff_roto_seed_bonuses: { "1": bonus, "2": 0, "3": 0, "4": 0 } } })).ok()).toBeTruthy();
    const response = await page.request.get(`/api/leagues/${league.id}/roto/standings`);
    expect(response.ok()).toBeTruthy();
    const standings = await response.json();
    await info.attach(`bonus-${bonus}-standings`, { body: JSON.stringify(standings), contentType: "application/json" });
    expect(standings.totals[league.teams[0].id].total_points).toBe(2 + bonus);
    expect(standings.totals[league.teams[7].id].total_points).toBe(16);
    const completion = await page.request.post(`/api/leagues/${league.id}/complete-season`, { data: { season_year: 2026 } });
    expect(completion.ok()).toBeTruthy();
    const result = await completion.json();
    await info.attach(`bonus-${bonus}-champion`, { body: JSON.stringify(result), contentType: "application/json" });
    expect(result.champion).toBe(league.teams[bonus ? 0 : 7].name);
  }
});
