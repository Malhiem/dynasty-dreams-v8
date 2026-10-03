import { expect, test } from "@playwright/test";
import { LoginPage } from "../pages/login/login.page";
import { LeagueScoringPage } from "../pages/league-scoring/league-scoring.page";
import { configureCategories, createRotisserieFixture, createCondensedFixture } from "../support/rotisserie";

test.beforeEach(async ({ page }) => {
  await new LoginPage(page).goto();
  await new LoginPage(page).logIn({
    email: process.env.E2E_ADMIN_EMAIL || "admin@e2e.dynastydreams.com",
    password: process.env.E2E_ADMIN_PASSWORD || "e2e-admin-password",
  });
  await expect(page).toHaveURL(/\/dashboard(?:\?|$)/);
});

const formats = [
  { label: "Rotisserie", value: "rotisserie", h2h: false },
  { label: "Points-Based", value: "points", h2h: false },
  { label: "Head-to-Head Points", value: "h2h-points", h2h: true },
  { label: "Head-to-Head Most Categories", value: "h2h-categories", h2h: true },
  { label: "Head-to-Head Each Category", value: "h2h-each", h2h: true },
];

for (const format of formats) {
  test(`League Setup persists ${format.label} and applies format restrictions`, async ({ page }) => {
    const league = await createRotisserieFixture(page.request);
    // Start with a different persisted format, including when selecting Rotisserie.
    const initial = format.value === "rotisserie" ? "h2h-points" : "rotisserie";
    expect((await page.request.put(`/api/leagues/${league.id}`, { data: { scoring_format: initial } })).ok()).toBeTruthy();
    const scoring = new LeagueScoringPage(page);
    await scoring.goto(league.id);
    await scoring.select(format.label);
    await expect(scoring.selectors.h2hRequired(page)).toBeVisible({ visible: !format.h2h });
    // The card has no Save action: selection must persist before navigation.
    await expect.poll(async () => (await (await page.request.get(`/api/leagues/${league.id}`)).json()).scoring_format,
      { message: `${format.label} must persist to the league API` }).toBe(format.value);
    await page.reload();
    await expect(scoring.selectors.h2hRequired(page)).toBeVisible({ visible: !format.h2h });
  });
}

test("Rotisserie allocates 12 through 1 per category and sums category points", async ({ page }, testInfo) => {
  const league = await createRotisserieFixture(page.request);
  for (const categories of [["goals"], ["assists"], ["goals", "assists"]]) {
    await configureCategories(page.request, league.id, categories);
    const response = await page.request.get(`/api/scoring/roto/${league.id}`);
    expect(response.ok()).toBeTruthy();
    const result = await response.json();
    await testInfo.attach(`roto-${categories.join("-")}`, { body: JSON.stringify(result, null, 2), contentType: "application/json" });
    expect(result.categories).toEqual(categories);
    expect(result.standings).toHaveLength(12);
    for (const team of league.teams) {
      const row = result.standings.find((entry: { team_id: string }) => entry.team_id === team.id);
      expect(row).toBeDefined();
      for (const category of categories) expect(row.stats[category]).toBe(team[category as "goals" | "assists"]);
      const expected = (categories.includes("goals") ? team.goalPoints : 0) +
        (categories.includes("assists") ? team.assistPoints : 0);
      expect(row.roto_points, team.name).toBe(expected);
    }
    if (categories.length === 1) expect(result.standings.map((row: { roto_points: number }) => row.roto_points)).toEqual([12,11,10,9,8,7,6,5,4,3,2,1]);
    expect(result.standings[0].team_id).toBe(league.teams[0].id);
    expect(result.standings.map((row: { roto_points: number }) => row.roto_points)).toEqual(
      result.standings.map((row: { roto_points: number }) => row.roto_points).sort((a: number, b: number) => b - a));
  }
});

test("Rotisserie standings display each season category rank", async ({ page }) => {
  const league = await createCondensedFixture(page.request);
  expect((await page.request.put(`/api/leagues/${league.id}`, { data: { playoffs_enabled: false, roto_playoffs_enabled: false } })).ok()).toBeTruthy();
  const scoring = new LeagueScoringPage(page);
  await scoring.roto(league.id);
  await expect(scoring.selectors.categoryRank(page, "goals")).toBeVisible();
  await expect(scoring.selectors.categoryRank(page, "assists")).toBeVisible();
  for (const [i, team] of league.teams.entries()) for (const category of ["goals", "assists"]) {
    await expect(scoring.selectors.categoryTeamRank(page, category, team.id)).toHaveText(String(i + 1));
  }
});

for (const playoffs of [false, true]) {
  test(`Rotisserie champion with playoffs ${playoffs ? "enabled" : "disabled"}`, async ({ page }, testInfo) => {
    const league = await createCondensedFixture(page.request);
    const saved = await page.request.put(`/api/leagues/${league.id}`, { data: {
      playoffs_enabled: playoffs, roto_playoffs_enabled: playoffs,
    } });
    expect(saved.ok()).toBeTruthy();
    const settings = await (await page.request.get(`/api/leagues/${league.id}`)).json();
    expect(settings.playoffs_enabled).toBe(playoffs);
    const response = await page.request.get(`/api/leagues/${league.id}/roto/standings`);
    expect(response.ok()).toBeTruthy();
    const standings = await response.json();
    await testInfo.attach("champion-standings", { body: JSON.stringify(standings, null, 2), contentType: "application/json" });
    expect(Boolean(standings.fresh_totals)).toBe(playoffs);
    const expectedPoints = playoffs ? [6, 7, 8, 9, 10, 12, 14, 16] : [16, 14, 12, 10, 8, 6, 4, 2];
    for (const [i, team] of league.teams.entries()) {
      expect(standings.totals[team.id].total_points, team.name).toBe(expectedPoints[i]);
    }
    const completion = await page.request.post(`/api/leagues/${league.id}/complete-season`, {
      data: { season_year: 2026 },
    });
    expect(completion.ok()).toBeTruthy();
    const completed = await completion.json();
    await testInfo.attach("season-completion", { body: JSON.stringify(completed, null, 2), contentType: "application/json" });
    expect(completed.teams_snapshotted).toBe(8);
    expect(completed.champion).toBe(league.teams[playoffs ? 7 : 0].name);
  });
}
