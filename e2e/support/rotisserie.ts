import type { APIRequestContext } from "@playwright/test";
import { MongoClient, ObjectId } from "mongodb";

export interface RotoTeam {
  id: string;
  name: string;
  goals: number;
  assists: number;
  goalPoints: number;
  assistPoints: number;
}

/** Seeds only the disposable Compose database; real HTTP endpoints remain under test. */
export async function createRotisserieFixture(request: APIRequestContext) {
  if (process.env.E2E_BASE_URL !== "http://web") {
    throw new Error("Rotisserie fixtures require the isolated E2E Compose stack (http://web).");
  }
  const response = await request.post("/api/leagues", { data: {
    name: `E2E Rotisserie ${crypto.randomUUID()}`, sport: "nhl", format: "dynasty",
    scoring_format: "rotisserie", max_teams: 12, is_private: true,
  } });
  if (!response.ok()) throw new Error(`Create fixture: ${response.status()} ${await response.text()}`);
  const league = await response.json();
  const client = new MongoClient("mongodb://mongo:27017");
  const teams: RotoTeam[] = [];
  try {
    const db = client.db("dynasty_dreams_e2e");
    // Replace only this newly created league's auto-created commissioner team.
    await db.collection("teams").deleteMany({ league_id: league.id });
    for (let i = 0; i < 12; i++) {
      const playerId = new ObjectId();
      const teamId = new ObjectId();
      const goalPoints = 12 - i;
      const assistPoints = i === 0 ? 12 : i;
      // Two contributing players ensure category stats are accumulated across the roster.
      const secondId = new ObjectId();
      await db.collection("players").insertMany([
        { _id: playerId, name: `E2E Skater ${i} A`, position: "C", goals: goalPoints * 2, assists: assistPoints * 3 },
        { _id: secondId, name: `E2E Skater ${i} B`, position: "C", goals: goalPoints, assists: assistPoints },
      ]);
      const name = `Roto Team ${String(i + 1).padStart(2, "0")}`;
      await db.collection("teams").insertOne({
        _id: teamId, league_id: league.id, name, owner_id: league.commissioner_id,
        owner_name: league.commissioner_name, roster: [String(playerId), String(secondId)],
        lineup: {}, wins: 0, losses: 0, ties: 0, points_for: 0, points_against: 0,
        is_commissioner_team: i === 0, created_at: new Date(),
      });
      teams.push({ id: String(teamId), name, goals: goalPoints * 3,
        assists: assistPoints * 4, goalPoints, assistPoints });
    }
    await db.collection("leagues").updateOne({ _id: new ObjectId(league.id) },
      { $set: { current_teams: 12, setup_wizard_complete: true } });
  } finally { await client.close(); }
  return { id: league.id as string, teams };
}

export async function configureCategories(request: APIRequestContext, leagueId: string, categories: string[]) {
  const response = await request.post("/api/scoring/config", { data: {
    league_id: leagueId, skater_scoring: {}, goalie_scoring: {}, roto_categories: categories,
  } });
  if (!response.ok()) throw new Error(`Configure categories: ${response.status()} ${await response.text()}`);
}

/** Eight qualifiers, reversed playoff vs season rankings; all stats explicitly seeded. */
export async function createCondensedFixture(request: APIRequestContext) {
  const league = await createRotisserieFixture(request);
  const teams = league.teams.slice(0, 8);
  const client = new MongoClient("mongodb://mongo:27017");
  try {
    const db = client.db("dynasty_dreams_e2e");
    await db.collection("teams").deleteMany({ league_id: league.id,
      _id: { $in: league.teams.slice(8).map(t => new ObjectId(t.id)) } });
    for (const [i, team] of teams.entries()) {
      const doc = await db.collection("teams").findOne({ _id: new ObjectId(team.id) });
      await db.collection("players").updateMany({ _id: { $in: doc!.roster.map((id: string) => new ObjectId(id)) } },
        { $set: { season_stats: { goals: 100 - i, assists: 100 - i },
          period_stats: { "26": { goals: i + 1, assists: i + 1 } } } });
      await db.collection("teams").updateOne({ _id: new ObjectId(team.id) },
        { $set: { wins: 8 - i, points_for: 100 - i } });
    }
    await db.collection("leagues").updateOne({ _id: new ObjectId(league.id) }, { $set: { current_teams: 8 } });
  } finally { await client.close(); }
  const response = await request.put(`/api/leagues/${league.id}`, { data: {
    playoff_format: "condensed_roto", playoffs_enabled: true, roto_playoffs_enabled: true,
    playoff_teams: 8, regular_season_weeks: 25, playoff_start_week: 26, playoff_end_week: 26,
    playoff_rounds: 1, roto_categories: ["goals", "assists"], roto_tiebreak: "split",
    playoff_roto_fresh_totals: true, playoff_roto_seed_bonuses: { "1": 4, "2": 3, "3": 2, "4": 1 },
  } });
  if (!response.ok()) throw new Error(`Condensed setup: ${response.status()} ${await response.text()}`);
  return { id: league.id, teams };
}

export async function seedSecondPeriod(league: { id: string; teams: RotoTeam[] }) {
  const client = new MongoClient("mongodb://mongo:27017");
  try {
    const db = client.db("dynasty_dreams_e2e");
    for (const [i, team] of league.teams.entries()) {
      const doc = await db.collection("teams").findOne({ _id: new ObjectId(team.id), league_id: league.id });
      await db.collection("players").updateMany({ _id: { $in: doc!.roster.map((id: string) => new ObjectId(id)) } },
        { $set: { "period_stats.27": { goals: 8 - i, assists: 8 - i } } });
    }
  } finally { await client.close(); }
}

/** Deterministic per-player weekly stats; restricted to the isolated E2E database. */
export async function seedPlayoffWindow(league: { id: string; teams: RotoTeam[] }) {
  if (process.env.E2E_BASE_URL !== "http://web") throw new Error("Isolated E2E stack required");
  const client = new MongoClient("mongodb://mongo:27017");
  try {
    const db = client.db("dynasty_dreams_e2e");
    for (const [i, team] of league.teams.entries()) {
      const doc = await db.collection("teams").findOne({ _id: new ObjectId(team.id), league_id: league.id });
      await db.collection("players").updateMany({ _id: { $in: doc!.roster.map((id: string) => new ObjectId(id)) } },
        { $set: {
          "period_stats.25": { goals: 1000 * (i + 1), assists: 1000 * (i + 1) },
          "period_stats.27": { goals: 3 * (8 - i), assists: 3 * (8 - i) },
          "period_stats.28": { goals: 2000 * (i + 1), assists: 2000 * (i + 1) },
        } });
    }
  } finally { await client.close(); }
}
