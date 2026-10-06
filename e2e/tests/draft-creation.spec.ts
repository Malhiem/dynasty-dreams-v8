import { expect, test } from "@playwright/test";
import { MongoClient, ObjectId } from "mongodb";
import { LoginPage } from "../pages/login/login.page";

test("five-round draft creates five picks per league team and renders the board", async ({ page }, testInfo) => {
  test.setTimeout(90000);
  if (process.env.E2E_BASE_URL !== "http://web" || process.env.DRAFT_TEST_ISOLATED !== "1")
    throw new Error("Requires the dedicated disposable draft test Compose stack");
  await new LoginPage(page).goto();
  await new LoginPage(page).logIn({ email: "admin@e2e.dynastydreams.com", password: "e2e-admin-password" });
  await expect(page).toHaveURL(/\/dashboard(?:\?|$)/);
  const created = await page.request.post("/api/leagues", { data: {
    name: `Draft distribution ${crypto.randomUUID()}`, sport: "nhl", format: "dynasty",
    scoring_format: "head_to_head", max_teams: 4, roster_spots: 20, is_private: true,
  } });
  expect(created.ok(), await created.text()).toBeTruthy();
  const league = await created.json();
  const teams = ["ALP", "BET", "GAM", "DEL"].map((abbr, i) => ({
    _id: new ObjectId(), league_id: league.id, owner_id: league.commissioner_id,
    owner_name: league.commissioner_name, name: `Draft Team ${abbr}`, logo_abbr: abbr, logo_abbr_override: abbr,
    roster: [], lineup: {}, is_commissioner_team: i === 0,
  }));
  const client = new MongoClient("mongodb://mongo:27017");
  try {
    const db = client.db("dynasty_dreams_e2e");
    await db.collection("teams").deleteMany({ league_id: league.id });
    await db.collection("teams").insertMany(teams);
    await db.collection("leagues").updateOne({ _id: new ObjectId(league.id) },
      { $set: { current_teams: 4, setup_wizard_complete: true, season: String(new Date().getFullYear()) } });
    const response = await page.request.post("/api/drafts", { data: {
      league_id: league.id, name: "Five rounds four teams", total_rounds: 5,
      time_per_pick: 60, draft_type: "snake", snake_draft: true,
      pick_trading_enabled: true, trading_window_opens: "immediately",
    } });
    expect(response.ok(), await response.text()).toBeTruthy();
    const draft = await response.json();
    draft.id = draft.id || draft._id;
    expect(draft.id).toBeTruthy();
    expect(draft.picks_generated).toBe(20);
    const picks = await db.collection("draft_picks").find({ league_id: league.id, draft_id: draft.id }).toArray();
    expect(picks).toHaveLength(20);
    for (const team of teams) {
      const owned = picks.filter(p => p.current_team_id === String(team._id));
      expect(owned, team.name).toHaveLength(5);
      expect(owned.map(p => p.round).sort((a, b) => a - b)).toEqual([1, 2, 3, 4, 5]);
      for (const pick of owned) {
        expect(pick.original_team_id).toBe(String(team._id));
        expect(pick.tradeable).toBe(true);
      }
    }
    const boardResponse = await page.request.get(`/api/drafts/${draft.id}/board`);
    expect(boardResponse.ok()).toBeTruthy();
    const board = await boardResponse.json();
    expect(board.total_rounds).toBe(5);
    expect(board.team_abbrs.slice().sort()).toEqual(teams.map(t => t.logo_abbr).sort());
    expect(board.board).toHaveLength(5);
    for (const [index, round] of board.board.entries()) {
      expect(round).toHaveLength(4);
      expect(round.map((p: any) => p.team)).toEqual(index % 2 ? [...board.team_abbrs].reverse() : board.team_abbrs);
      expect(round.map((p: any) => p.overall)).toEqual([1,2,3,4].map(p => index * 4 + p));
      for (const pick of round) expect(pick.round).toBe(index + 1);
    }
    const assetsResponse = await page.request.get(`/api/drafts/${league.id}/picks?draft_id=${draft.id}`);
    expect(assetsResponse.ok()).toBeTruthy();
    const assets = await assetsResponse.json();
    expect(assets.picks).toHaveLength(20);
    for (const team of teams) {
      expect(assets.picks.filter((p: any) => p.current_team_id === String(team._id)).map((p: any) => p.round).sort((a: number,b: number) => a-b)).toEqual([1,2,3,4,5]);
    }
    await testInfo.attach("draft-api-evidence", { body: JSON.stringify({ league, draft, picks, board, assets }, null, 2), contentType: "application/json" });
    await page.addInitScript(id => localStorage.setItem("dd_active_league_id", id), league.id);
    await page.goto("/draft-board");
    for (const team of teams) await expect(page.getByTestId(`draft-board-summary-${team.logo_abbr}`)).toHaveText(`${team.logo_abbr}: 5 picks`);
    const grid = page.locator("table").filter({ has: page.getByRole("columnheader", { name: "Rd 1", exact: true }) });
    await expect(grid).toHaveCount(1);
    await expect(grid.locator("thead th")).toHaveText(["Team", "Rd 1", "Rd 2", "Rd 3", "Rd 4", "Rd 5"]);
    await expect(grid.locator("tbody tr")).toHaveCount(4);
    for (const team of teams) {
      const row = grid.locator("tbody tr").filter({ hasText: team.name });
      await expect(row).toHaveCount(1);
      await expect(row.locator("td")).toHaveCount(6);
      await expect(row.locator("td").first()).toContainText("5 picks");
      for (let round = 1; round <= 5; round++) await expect(row.locator("td").nth(round)).toHaveText(team.logo_abbr);
    }
    await page.screenshot({ path: testInfo.outputPath("draft-board.png"), fullPage: true });
  } finally { await client.close(); }
});
