/**
 * Iter 232N.7 — League Movers widget.
 *
 * Compact card that surfaces the top cross-league movers in the last
 * 7 days. Three toggleable categories — Hot / Dropped / Traded — pull
 * from `/api/player-trends/leaderboard?movers=`. Rendered on both the
 * Dashboard and the League Home page so managers can spot smart-money
 * signals without hunting through the player pool.
 */
import { useEffect, useState } from "react";
import { Flame, ArrowDownFromLine, Repeat2 } from "lucide-react";
import { Link } from "react-router-dom";
import api from "@/lib/api";
import { PlayerTrendBadge } from "@/components/player/PlayerTrendBadge";

interface LeaderboardRow {
  player_id: string;
  name: string;
  position: string;
  team: string;
  trend: "hot" | "dropped" | "traded";
  adds_7d: number;
  drops_7d: number;
  trades_7d: number;
  distinct_leagues_7d: number;
}

const CATEGORIES: { id: "hot" | "dropped" | "traded"; label: string; icon: any }[] = [
  { id: "hot", label: "Hot", icon: Flame },
  { id: "dropped", label: "Dropped", icon: ArrowDownFromLine },
  { id: "traded", label: "Traded", icon: Repeat2 },
];

interface Props {
  limit?: number;
  heading?: string;
}

export function LeagueMoversWidget({ limit = 5, heading = "League Movers" }: Props) {
  const [active, setActive] = useState<"hot" | "dropped" | "traded">("hot");
  const [loading, setLoading] = useState(true);
  const [rows, setRows] = useState<LeaderboardRow[]>([]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    api
      .get(`/player-trends/leaderboard?movers=${active}&limit=${limit}`)
      .then((res) => {
        if (cancelled) return;
        setRows(res.data?.players || []);
      })
      .catch(() => !cancelled && setRows([]))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [active, limit]);

  return (
    <div className="w-full" data-testid="league-movers-widget">
      <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
        <h3 className="text-sm font-semibold text-foreground">{heading}</h3>
        <div
          className="inline-flex items-center gap-0.5 rounded-md bg-secondary/40 p-0.5"
          role="tablist"
          aria-label="Mover category"
        >
          {CATEGORIES.map((c) => {
            const isActive = c.id === active;
            const Icon = c.icon;
            return (
              <button
                key={c.id}
                type="button"
                role="tab"
                aria-selected={isActive}
                onClick={() => setActive(c.id)}
                className={`px-2 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wider transition-colors inline-flex items-center gap-1 ${
                  isActive
                    ? "bg-primary text-primary-foreground shadow-sm"
                    : "text-muted-foreground hover:text-foreground hover:bg-secondary/60"
                }`}
                data-testid={`league-movers-tab-${c.id}`}
              >
                <Icon className="h-3 w-3" />
                {c.label}
              </button>
            );
          })}
        </div>
      </div>
      {loading ? (
        <p className="text-xs text-muted-foreground py-3" data-testid="league-movers-loading">
          Loading…
        </p>
      ) : rows.length === 0 ? (
        <p className="text-xs text-muted-foreground py-3" data-testid="league-movers-empty">
          No {active} movers in the last 7 days across your leagues.
        </p>
      ) : (
        <ul className="space-y-1.5" data-testid="league-movers-list">
          {rows.map((r, idx) => (
            <li
              key={r.player_id}
              className="flex items-center gap-2 text-xs rounded-md border border-border/40 bg-secondary/20 px-2 py-1.5"
              data-testid={`league-movers-row-${r.player_id}`}
            >
              <span className="text-[10px] text-muted-foreground w-4 shrink-0">{idx + 1}</span>
              <Link
                to={`/players/${r.player_id}`}
                className="font-semibold text-foreground hover:text-primary truncate flex-1"
              >
                {r.name}
              </Link>
              <span className="text-[10px] uppercase tracking-wider text-muted-foreground shrink-0">
                {r.position}
                {r.team ? ` · ${r.team}` : ""}
              </span>
              <PlayerTrendBadge trends={r} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default LeagueMoversWidget;
