import {generatedFixture} from '../support/roto-generation';
import { expect, test } from "@playwright/test";
import { LoginPage } from "../pages/login/login.page";
import { LeagueScoringPage } from "../pages/league-scoring/league-scoring.page";
import { createCondensedFixture, seedSecondPeriod } from "../support/rotisserie";

test.beforeEach(async ({ page }) => {
  const login = new LoginPage(page);
  await login.goto();
  await login.logIn({ email: process.env.E2E_ADMIN_EMAIL || "admin@e2e.dynastydreams.com", password: process.env.E2E_ADMIN_PASSWORD || "e2e-admin-password" });
  await expect(page).toHaveURL(/\/dashboard(?:\?|$)/);
});

test("Playoff toggle persists off and on through the UI", async ({ page }) => {
  const league = await createCondensedFixture(page.request);
  const scoring = new LeagueScoringPage(page);
  await scoring.goto(league.id);
  for (const enabled of [false, true]) {
    await expect(scoring.selectors.playoffToggle(page)).toBeEnabled();
    const saved = page.waitForResponse(r => r.request().method() === "PUT" && new URL(r.url()).pathname === `/api/leagues/${league.id}`);
    await scoring.selectors.playoffToggle(page).setChecked(enabled);
    expect((await saved).ok()).toBeTruthy();
    expect((await (await page.request.get(`/api/leagues/${league.id}`)).json()).playoffs_enabled).toBe(enabled);
    await page.reload();
    await expect(scoring.selectors.playoffToggle(page)).toBeChecked({ checked: enabled });
  }
});

test("Disabled playoffs preserve a full-season schedule with no playoff matchups", async ({ page }, info) => {
  const league = await createCondensedFixture(page.request);
  const scoring = new LeagueScoringPage(page);
  await scoring.goto(league.id);
  const disabled = page.waitForResponse(r => r.request().method() === "PUT" && new URL(r.url()).pathname === `/api/leagues/${league.id}`);
  await scoring.selectors.playoffToggle(page).setChecked(false);
  expect((await disabled).ok()).toBeTruthy();
  const boundsResponse = await page.request.get("/api/nhl-season-bounds");
  expect(boundsResponse.ok()).toBeTruthy();
  const weeks = (await boundsResponse.json()).weeks.slice(0, 28);
  expect(weeks.length).toBeGreaterThan(0);
  const first = weeks[0], last = weeks[weeks.length - 1];
  await scoring.structure(league.id);
  await expect(scoring.selectors.structure(page)).toBeVisible();
  await expect.soft(scoring.selectors.playoffSave(page)).toBeHidden();
  await scoring.selectors.regularWeeks(page).fill(String(weeks.length));
  await scoring.selectors.statsStart(page).click();
  await page.getByRole("option", { name: first.label, exact: true }).click();
  await scoring.selectors.statsEnd(page).click();
  await page.getByRole("option", { name: last.label, exact: true }).click();
  const saved = page.waitForResponse(r => r.request().method() === "PUT" && new URL(r.url()).pathname === `/api/leagues/${league.id}`);
  await scoring.selectors.scheduleSave(page).click();
  const savedResponse = await saved;
  await info.attach("disabled-schedule-save", { body: await savedResponse.text(), contentType: "application/json" });
  expect(savedResponse.ok()).toBeTruthy();
  await page.reload();
  await expect(scoring.selectors.regularWeeks(page)).toHaveValue(String(weeks.length));
  await expect(scoring.selectors.statsStart(page)).toContainText(first.label);
  await expect(scoring.selectors.statsEnd(page)).toContainText(last.label);
  const config = await (await page.request.get(`/api/leagues/${league.id}`)).json();
  expect(config).toMatchObject({ playoffs_enabled: false, regular_season_weeks: weeks.length,
    stats_count_start_date: first.start_date, stats_count_end_date: last.end_date });
  const generated = await page.request.post("/api/matchups/generate-schedule", { data: { league_id: league.id } });
  await info.attach("generated-disabled-schedule", { body: await generated.text(), contentType: "application/json" });
  expect(generated.ok()).toBeTruthy();
  const response = await page.request.get(`/api/matchups/${league.id}`);
  expect(response.ok()).toBeTruthy();
  const rows = await response.json();
  expect(rows.filter((m: { is_playoff?: boolean }) => m.is_playoff)).toHaveLength(0);
  expect(rows).toHaveLength(0);
  const calendar = await (await page.request.get(`/api/leagues/${league.id}/roto/schedule`)).json();
  expect(calendar.periods).toHaveLength(weeks.length);
  expect(calendar.periods[0].startDate).toBe(first.start_date);
  expect(calendar.periods[calendar.periods.length-1].endDate).toBe(last.end_date);
});

test("Two closed weeks accumulate once and exclude open weeks", async ({ page }, info) => {
  const league = await createCondensedFixture(page.request);
  expect((await page.request.put(`/api/leagues/${league.id}`, { data: { playoffs_enabled: false, roto_playoffs_enabled: false } })).ok()).toBeTruthy();
  await seedSecondPeriod(league);
  for (const [period, close] of [[26, true], [27, false], [27, true], [27, true]] as const) {
    const result = await page.request.post(`/api/leagues/${league.id}/roto/recompute`, { data: { period, close } });
    expect(result.ok()).toBeTruthy();
    const standings = await (await page.request.get(`/api/leagues/${league.id}/roto/standings`)).json();
    await info.attach(`period-${period}-closed-${close}`, { body: JSON.stringify(standings), contentType: "application/json" });
    expect(standings.periods_closed).toBe(period === 27 && close ? 2 : 1);
    for (const [i, team] of league.teams.entries()) expect(standings.totals[team.id].total_points).toBe(period === 27 && close ? 18 : 2 * (i + 1));
  }
});

test("Generated elimination playoffs advance 8 to 4 to 2 to champion through scored weeks", async ({ page }, info) => {
  const league = await generatedFixture(page.request);
  const generated = await page.request.post("/api/matchups/generate-schedule", { data: { league_id: league.id } });
  expect(generated.ok()).toBeTruthy();
  const regular = await page.request.post(`/api/leagues/${league.id}/roto/recompute`, {data:{period:1,close:true}});
  expect(regular.ok()).toBeTruthy();
  let previousWinners: string[] = [];
  for (const [week, count] of [[2, 4], [3, 2], [4, 1]]) {
    const before = await (await page.request.get(`/api/matchups/${league.id}/results?week=${week}`)).json();
    await info.attach(`week-${week}-before`, { body: JSON.stringify(before), contentType: "application/json" });
    const playoffs = before.filter((m: { is_playoff?: boolean }) => m.is_playoff);
    expect.soft(playoffs.length, `Week ${week} matchup count`).toBe(count);
    if (previousWinners.length) expect.soft(playoffs.flatMap((m: { home_team_id: string; away_team_id: string }) => [m.home_team_id, m.away_team_id]).sort()).toEqual([...previousWinners].sort());
    const simulation = await page.request.post("/api/matchups/simulate-week", { data: { league_id: league.id, week } });
    await info.attach(`week-${week}-simulation`, { body: await simulation.text(), contentType: "text/plain" });
    expect(simulation.ok(), `Week ${week}: ${simulation.status()}`).toBeTruthy();
    const after = await (await page.request.get(`/api/matchups/${league.id}/results?week=${week}`)).json();
    previousWinners = after.filter((m: { is_playoff?: boolean }) => m.is_playoff).map((m: { home_team_id: string; away_team_id: string; home_score: number; away_score: number }) => m.home_score > m.away_score ? m.home_team_id : m.away_team_id);
    expect(new Set(previousWinners).size).toBe(count);
  }
  const completed = await page.request.post(`/api/leagues/${league.id}/complete-season`, { data: { season_year: 2025 } });
  expect(completed.ok()).toBeTruthy();
  expect((await completed.json()).champion).toBe(league.teams.find(t => t.id === previousWinners[0])!.name);
});
