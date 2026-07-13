/**
 * Iter 232N.53 — Platform Commissioner Activity Panel.
 *
 * Admin-only cross-league surface: shows every commissioner override
 * (pick undos + offline-manager pings) across every league on the
 * platform, plus lightweight aggregates that surface problem patterns
 * (a commissioner with 12 undos in a week, a league with 40 pings).
 *
 * Data source: `GET /api/admin/commissioner-activity?limit=N&days=N`
 * (platform admin only).
 */
import { useCallback, useEffect, useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Undo2, BellRing, RefreshCw, Gavel, AlertTriangle, TrendingUp } from "lucide-react";
import api from "@/lib/api";

interface AggRow {
  id: string;
  name: string;
  undos: number;
  pings: number;
  total: number;
}

interface EventDetail {
  pick_number?: number;
  removed_count?: number;
  cascade?: boolean;
  player_name?: string | null;
  team?: string | null;
  on_the_clock_after?: string | null;
  target_user_id?: string;
  target_team_name?: string | null;
  draft_id?: string;
  channels_fired?: string[];
}

interface EventRow {
  type: "pick_undo" | "owner_ping";
  at: string;
  league_id: string;
  league_name: string;
  commissioner: { id: string | null; name: string };
  reason: string | null;
  detail: EventDetail;
}

interface Response {
  checked_at: string;
  window_days: number;
  count: number;
  events: EventRow[];
  aggregates: {
    by_league: AggRow[];
    by_commissioner: AggRow[];
    totals: { undos: number; pings: number; total: number };
  };
}

function relativeTime(iso: string): string {
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return "?";
  const diffSec = Math.round((Date.now() - t) / 1000);
  if (diffSec < 60) return `${diffSec}s ago`;
  if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m ago`;
  if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}h ago`;
  return `${Math.floor(diffSec / 86400)}d ago`;
}

function AggregateList({
  title,
  rows,
  totalHeat,
  emptyMsg,
}: {
  title: string;
  rows: AggRow[];
  totalHeat: number;
  emptyMsg: string;
}) {
  return (
    <div className="rounded-md border border-border/60 bg-card/40 p-3">
      <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-2 flex items-center gap-1.5">
        <TrendingUp className="h-3 w-3" />
        {title}
      </div>
      {rows.length === 0 ? (
        <div className="text-xs text-muted-foreground italic">{emptyMsg}</div>
      ) : (
        <div className="space-y-1">
          {rows.map((r) => {
            const pct = totalHeat > 0 ? Math.round((r.total / totalHeat) * 100) : 0;
            // Heat threshold — >= 20% of total activity or >= 10 events
            // marks a "hot" row worth investigating.
            const hot = pct >= 20 || r.total >= 10;
            return (
              <div
                key={r.id}
                className="flex items-center gap-2 text-xs"
                data-testid={`platform-agg-row-${r.id}`}
              >
                <div className="flex-1 min-w-0 truncate">
                  <span className={hot ? "text-rose-300 font-medium" : ""}>{r.name}</span>
                </div>
                <Badge
                  variant="outline"
                  className="text-[9px] bg-amber-500/10 text-amber-300 border-amber-500/30"
                  title="Undos"
                >
                  <Undo2 className="h-2.5 w-2.5 mr-0.5" />
                  {r.undos}
                </Badge>
                <Badge
                  variant="outline"
                  className="text-[9px] bg-cyan-500/10 text-cyan-300 border-cyan-500/30"
                  title="Pings"
                >
                  <BellRing className="h-2.5 w-2.5 mr-0.5" />
                  {r.pings}
                </Badge>
                <div className={`text-[10px] w-8 text-right font-mono ${hot ? "text-rose-300 font-semibold" : "text-muted-foreground"}`}>
                  {r.total}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function EventRowDisplay({ ev }: { ev: EventRow }) {
  const isUndo = ev.type === "pick_undo";
  return (
    <div
      className={`flex items-start gap-2 border-l-2 pl-2.5 py-1.5 ${
        isUndo ? "border-amber-500/40" : "border-cyan-500/40"
      }`}
      data-testid={`platform-event-${ev.type}-${ev.at}`}
    >
      {isUndo ? (
        <Undo2 className="h-3.5 w-3.5 text-amber-400 mt-0.5 shrink-0" />
      ) : (
        <BellRing className="h-3.5 w-3.5 text-cyan-400 mt-0.5 shrink-0" />
      )}
      <div className="flex-1 min-w-0">
        <div className="text-xs">
          <span className="text-muted-foreground">{ev.league_name}</span>
          <span className="text-muted-foreground/60"> · </span>
          <span className="font-semibold">{ev.commissioner.name}</span>
          {isUndo ? (
            <>
              <span className="text-muted-foreground"> undid </span>
              <span className="font-mono font-medium">#{ev.detail.pick_number}</span>
              {ev.detail.player_name && (
                <span> · <span className="font-medium">{ev.detail.player_name}</span></span>
              )}
              {ev.detail.cascade && (ev.detail.removed_count ?? 0) > 1 && (
                <Badge
                  variant="outline"
                  className="ml-1.5 text-[9px] bg-rose-500/15 text-rose-300 border-rose-500/30"
                >
                  cascade × {ev.detail.removed_count}
                </Badge>
              )}
            </>
          ) : (
            <>
              <span className="text-muted-foreground"> pinged </span>
              <span className="font-medium">{ev.detail.target_team_name || "manager"}</span>
              {(ev.detail.channels_fired?.length ?? 0) > 0 && (
                <span className="text-[10px] text-muted-foreground ml-1">
                  · {ev.detail.channels_fired!.join(", ")}
                </span>
              )}
            </>
          )}
        </div>
        {ev.reason && (
          <div className="text-[10px] text-muted-foreground italic mt-0.5 truncate">
            &ldquo;{ev.reason}&rdquo;
          </div>
        )}
      </div>
      <div className="text-[10px] text-muted-foreground shrink-0" title={new Date(ev.at).toLocaleString()}>
        {relativeTime(ev.at)}
      </div>
    </div>
  );
}

export default function PlatformCommissionerActivityPanel() {
  const [data, setData] = useState<Response | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [windowDays, setWindowDays] = useState<number>(30);

  const fetchActivity = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get(
        `/admin/commissioner-activity?limit=50&days=${windowDays}`,
      );
      setData(data);
      setError(null);
    } catch (e: any) {
      const detail = e?.response?.data?.detail || e?.message || "Failed to load activity";
      setError(detail);
    } finally {
      setLoading(false);
    }
  }, [windowDays]);

  useEffect(() => {
    fetchActivity();
  }, [fetchActivity]);

  // Hide entirely on 403 so this doesn't leak into non-admin pages that
  // happen to import the component.
  if (error && !data && error.toLowerCase().includes("platform admin")) {
    return null;
  }

  const totals = data?.aggregates?.totals ?? { undos: 0, pings: 0, total: 0 };

  return (
    <Card className="bg-card border-border" data-testid="platform-commish-activity">
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-3">
          <div>
            <CardTitle className="flex items-center gap-2 text-base">
              <Gavel className="h-4 w-4 text-fuchsia-400" />
              Commissioner activity — platform-wide
              {totals.total > 0 && (
                <Badge variant="outline" className="text-[10px] bg-fuchsia-500/10 text-fuchsia-300 border-fuchsia-500/30">
                  {totals.total} in last {windowDays}d
                </Badge>
              )}
            </CardTitle>
            <CardDescription className="text-[11px]">
              Every pick undo + offline-manager ping across every league.
              Early-warning signal for problem leagues or commissioners.
            </CardDescription>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <select
              value={windowDays}
              onChange={(e) => setWindowDays(Number(e.target.value))}
              className="text-[11px] bg-secondary/60 border border-border rounded px-2 py-1"
              data-testid="platform-commish-activity-window"
            >
              <option value={7}>Last 7d</option>
              <option value={30}>Last 30d</option>
              <option value={90}>Last 90d</option>
              <option value={365}>Last year</option>
            </select>
            <Button
              variant="outline"
              size="sm"
              onClick={fetchActivity}
              disabled={loading}
              data-testid="platform-commish-activity-refresh"
              className="h-7"
            >
              <RefreshCw className={`h-3 w-3 ${loading ? "animate-spin" : ""}`} />
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {error && !data && (
          <div className="flex items-center gap-2 text-xs text-rose-400">
            <AlertTriangle className="h-3.5 w-3.5" />
            {error}
          </div>
        )}
        {data && (
          <>
            {/* ─── Aggregates row ─── */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <AggregateList
                title="Hottest leagues"
                rows={data.aggregates.by_league}
                totalHeat={totals.total}
                emptyMsg="No league activity in this window."
              />
              <AggregateList
                title="Most active commissioners"
                rows={data.aggregates.by_commissioner}
                totalHeat={totals.total}
                emptyMsg="No commissioner activity in this window."
              />
            </div>

            {/* ─── Event stream ─── */}
            <div className="rounded-md border border-border/60 bg-card/40 p-3">
              <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-2">
                Recent events ({data.count})
              </div>
              {data.events.length === 0 ? (
                <div className="text-xs text-muted-foreground italic">
                  No commissioner overrides in this window — clean platform-wide.
                </div>
              ) : (
                <div className="space-y-0.5 max-h-[400px] overflow-y-auto pr-1">
                  {data.events.map((ev, i) => (
                    <EventRowDisplay key={`${ev.at}-${i}`} ev={ev} />
                  ))}
                </div>
              )}
            </div>

            <div className="text-[10px] text-muted-foreground text-right">
              {totals.undos} undo(s) · {totals.pings} ping(s) · updated {new Date(data.checked_at).toLocaleTimeString()}
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
