// Active-league selection shared by every league-scoped screen.

export const ACTIVE_LEAGUE_KEY = 'active_league_id';

// The remembered league if the user is still in it, otherwise their first one.
export function pickActiveLeague(leagues, preferredId) {
  if (!Array.isArray(leagues) || leagues.length === 0) return null;
  return leagues.find((l) => l.id === preferredId) || leagues[0];
}
