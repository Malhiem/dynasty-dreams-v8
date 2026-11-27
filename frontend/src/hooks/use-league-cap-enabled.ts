import { useActiveLeague } from "@/hooks/use-active-league";

/**
 * "No cap, no salaries": league views (roster, team tables, trades, depth
 * chart) only show player salary / cap figures when the active league has a
 * salary cap enabled. The player card is the one place salary stays visible.
 */
export function useLeagueCapEnabled(): boolean {
  const { league } = useActiveLeague();
  return Boolean((league as any)?.salary_cap_enabled);
}
