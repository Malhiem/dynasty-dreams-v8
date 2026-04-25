// @ts-nocheck
/**
 * Reusable player-card UI used inside confirmation toasts (drop, trade block).
 * Renders a compact card: headshot, name, position, NHL team, season stats,
 * fantasy points, salary, and % Owned (per-league + global tooltip).
 */
import { User as UserIcon } from "lucide-react";
import {
  Tooltip, TooltipContent, TooltipProvider, TooltipTrigger,
} from "@/components/ui/tooltip";

const formatSalary = (s) => `$${((s || 0) / 1_000_000).toFixed(1)}M`;

export function PlayerCardChip({ player, ownership }) {
  const stats = player?.stats || player?.categoryBreakdown || {};
  const fpts = Math.round(player?.fpts ?? player?.fantasy_points ?? player?.points ?? 0);

  const leaguePct = ownership?.league_pct;
  const globalPct = ownership?.global_pct;
  const leagueText = ownership && leaguePct != null
    ? `Owned in ${ownership.league_owned}/${ownership.league_total} league teams (${leaguePct}%)`
    : null;
  const globalText = ownership && globalPct != null
    ? `${ownership.global_owned}/${ownership.global_total} (${globalPct}%) across DD`
    : null;

  return (
    <div
      className="flex items-start gap-2 p-2 rounded-md border border-border/40 bg-background/40 min-w-0"
      data-testid={`toast-player-card-${player?.id}`}
    >
      {/* Headshot */}
      <div className="h-10 w-10 rounded-full bg-gradient-to-br from-secondary to-muted flex items-center justify-center text-[10px] font-bold shrink-0 overflow-hidden">
        {player?.headshot ? (
          <img src={player.headshot} alt={player.name} className="h-full w-full object-cover" />
        ) : (
          <UserIcon className="h-4 w-4 text-muted-foreground" />
        )}
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-xs font-bold truncate">{player?.name}</span>
          {player?.position && (
            <span className="text-[9px] uppercase tracking-wider text-muted-foreground">
              {player.position}
            </span>
          )}
          {(player?.team || player?.nhl_team) && (
            <span className="text-[9px] text-muted-foreground">
              · {player.team || player.nhl_team}
            </span>
          )}
        </div>
        <div className="grid grid-cols-5 gap-1 mt-1 text-[10px] text-muted-foreground">
          <span><span className="text-foreground font-semibold">{stats.G ?? player?.goals ?? 0}</span> G</span>
          <span><span className="text-foreground font-semibold">{stats.A ?? player?.assists ?? 0}</span> A</span>
          <span><span className="text-foreground font-semibold">{(stats.G ?? 0) + (stats.A ?? 0) || (player?.points ?? 0)}</span> P</span>
          <span><span className={(stats["+/-"] ?? 0) >= 0 ? "text-emerald-400 font-semibold" : "text-rose-400 font-semibold"}>
            {(stats["+/-"] ?? 0) >= 0 ? "+" : ""}{stats["+/-"] ?? 0}
          </span> ±</span>
          <span><span className="text-primary font-semibold">{fpts}</span> FPts</span>
        </div>
        <div className="flex items-center justify-between mt-1 text-[10px]">
          <span className="text-amber-400 font-semibold">
            {formatSalary(player?.contract?.salary || player?.salary || 0)}
          </span>
          {leagueText && (
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <span
                    className="text-cyan-300 font-semibold cursor-help"
                    data-testid={`toast-pct-owned-${player?.id}`}
                  >
                    {leaguePct}% owned
                  </span>
                </TooltipTrigger>
                <TooltipContent side="top" className="text-[10px]">
                  <div>{leagueText}</div>
                  {globalText && <div className="text-muted-foreground">{globalText}</div>}
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
          )}
        </div>
      </div>
    </div>
  );
}
