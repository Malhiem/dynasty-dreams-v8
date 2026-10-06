type History = {
  seasons?: Array<{ season_year?: number | string }>;
  team_banners?: Array<{ banners: Array<{ year: number | string }> }>;
};

export function recordedSeasonYears(data: History | null): number[] {
  const years = new Set<number>();
  for (const season of data?.seasons || []) {
    if (season.season_year != null) years.add(Number(season.season_year));
  }
  for (const team of data?.team_banners || []) {
    for (const banner of team.banners) years.add(Number(banner.year));
  }
  return [...years].filter(Number.isFinite).sort((a, b) => b - a);
}

// Recorded seasons can have gaps: recent means the newest three records,
// with a selected year intersecting that same scope for every award section.
export function selectSeasonYears(years: number[], recent: boolean, selected: number | null): Set<number> {
  return new Set((recent ? years.slice(0, 3) : years).filter(year => selected == null || year === selected));
}
