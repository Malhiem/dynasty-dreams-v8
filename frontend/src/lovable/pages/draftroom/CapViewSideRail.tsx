/**
 * Iter 232N.62 — Cap View Side Rail.
 *
 * Compact per-team cap-usage panel rendered inside the Draft Room when
 * the user toggles Cap View on. Each row shows a colour-ramped bar
 * (green < 75%, amber 75–89%, orange 90–99%, rose ≥ 100%) plus the
 * exact used/cap/remaining figures. The caller's own team is pinned
 * to the top and highlighted so admins & managers see their own
 * standing first.
 */
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { DollarSign, Coins } from "lucide-react";

interface TeamCapRow {
  team_id: string;
  name: string;
  salary_used: number;
  salary_cap: number;
  remaining: number;
  percent_used: number;
  over_cap: boolean;
  approaching: boolean;
  picks_count: number;
}

function fmtM(n: number): string {
  if (Math.abs(n) >= 1_000_000) return `$${(n / 1_000_000).toFixed(1)}M`;
  if (Math.abs(n) >= 1_000) return `$${(n / 1_000).toFixed(0)}k`;
  return `$${n}`;
}

function barColour(pct: number, over: boolean): string {
  if (over) return "bg-rose-500";
  if (pct >= 90) return "bg-orange-400";
  if (pct >= 75) return "bg-amber-400";
  return "bg-emerald-400";
}

function TeamCapRowUI({ t, isMine }: { t: TeamCapRow; isMine: boolean }) {
  return (
    <div
      className={cn(
        "rounded-md p-2 border transition-colors",
        isMine
          ? "border-primary/60 bg-primary/10"
          : "border-border/50 bg-card/40",
      )}
      data-testid={`cap-side-team-${t.team_id}`}
    >
      <div className="flex items-center justify-between gap-2 mb-1">
        <div className="text-xs font-semibold truncate">
          {isMine ? "★ " : ""}
          {t.name}
        </div>
        <div className="flex items-center gap-1 shrink-0">
          {t.over_cap && (
            <Badge
              variant="outline"
              className="text-[9px] bg-rose-500/15 text-rose-300 border-rose-500/40"
            >
              Over cap
            </Badge>
          )}
          {!t.over_cap && t.approaching && (
            <Badge
              variant="outline"
              className="text-[9px] bg-orange-500/15 text-orange-300 border-orange-500/40"
            >
              ≥90%
            </Badge>
          )}
        </div>
      </div>
      <div className="h-1.5 bg-secondary/40 rounded-full overflow-hidden">
        <div
          className={cn(
            "h-full transition-all rounded-full",
            barColour(t.percent_used, t.over_cap),
          )}
          style={{ width: `${Math.min(100, t.percent_used)}%` }}
        />
      </div>
      <div className="text-[10px] text-muted-foreground mt-1 flex justify-between">
        <span>
          <span className="text-foreground font-mono font-semibold">
            {fmtM(t.salary_used)}
          </span>{" "}
          / {fmtM(t.salary_cap)}
        </span>
        <span className={cn(t.over_cap && "text-rose-300 font-semibold")}>
          {t.percent_used.toFixed(1)}%
        </span>
      </div>
      <div className="text-[10px] text-muted-foreground">
        {t.remaining >= 0 ? "Remaining " : "Over by "}
        <span className={cn(
          "font-mono",
          t.remaining < 0 ? "text-rose-300 font-semibold" : "text-emerald-300",
        )}>
          {fmtM(Math.abs(t.remaining))}
        </span>{" "}
        · {t.picks_count} pick{t.picks_count === 1 ? "" : "s"}
      </div>
    </div>
  );
}

export default function CapViewSideRail({
  teams,
  myTeamId,
  salaryCap,
  defaultRookieAav,
}: {
  teams: TeamCapRow[];
  myTeamId: string | null;
  salaryCap: number;
  defaultRookieAav: number;
}) {
  // Pin the caller's team first, then rank the rest by percent_used DESC.
  const sorted = [...teams].sort((a, b) => {
    if (a.team_id === myTeamId) return -1;
    if (b.team_id === myTeamId) return 1;
    return b.percent_used - a.percent_used;
  });

  return (
    <div
      className="rounded-md border border-border/60 bg-card/40 p-2 space-y-1.5"
      data-testid="cap-view-side-rail"
    >
      <div className="flex items-center justify-between gap-2 pb-1 border-b border-border/40">
        <div className="flex items-center gap-1.5">
          <DollarSign className="h-3.5 w-3.5 text-emerald-400" />
          <span className="text-xs font-semibold">Cap View</span>
        </div>
        <span className="text-[10px] text-muted-foreground font-mono">
          Cap {fmtM(salaryCap)}
        </span>
      </div>

      <div className="text-[10px] text-muted-foreground flex items-center gap-1">
        <Coins className="h-2.5 w-2.5" />
        Unpriced players charged {fmtM(defaultRookieAav)} (rookie default)
      </div>

      <div className="space-y-1.5 max-h-[420px] overflow-y-auto pr-1">
        {sorted.map((t) => (
          <TeamCapRowUI
            key={t.team_id}
            t={t}
            isMine={t.team_id === myTeamId}
          />
        ))}
      </div>
    </div>
  );
}
