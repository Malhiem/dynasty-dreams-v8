/**
 * Iter 232N.57 — "What needs attention today?" feed.
 *
 * Consumes `GET /api/admin/metric-anomalies` and surfaces the top
 * spikes/dips (> Nσ deviation from 30-day mean) across every registered
 * metric in the daily-rollup framework.
 *
 * Two visual modes controlled by the `compact` prop:
 *   • compact=true  → badge-only summary (used on Admin Overview tab).
 *   • compact=false → full card with per-row detail (used inside
 *                    Metric Explorer tab).
 */
import { useCallback, useEffect, useState } from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  AlertTriangle,
  TrendingUp,
  TrendingDown,
  RefreshCw,
  Sparkles,
  CheckCircle2,
  Flame,
} from "lucide-react";
import api from "@/lib/api";

interface AnomalyRow {
  metric: string;
  kind: string;
  id: string;
  name: string;
  today_count: number;
  mean: number;
  stddev: number;
  sigma: number | null;
  direction: "spike" | "dip";
  delta: number;
  any_streak?: number;
  directional_streak?: number;
}

interface StreakRow {
  metric: string;
  kind: string;
  id: string;
  name: string;
  any_streak: number;
  directional_streak: number;
  latest_day: string;
  latest_direction: "spike" | "dip";
  latest_sigma: number | null;
  latest_delta: number;
}

interface AnomalyResponse {
  checked_at: string;
  threshold_sigma: number;
  window_days: number;
  min_samples: number;
  per_metric: {
    metric: string;
    today: string | null;
    anomalies: AnomalyRow[];
  }[];
  top_anomalies: AnomalyRow[];
  totals: { flagged: number; spikes: number; dips: number };
}

function humanizeKey(k: string): string {
  return k.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function AnomalyBadge({ row }: { row: AnomalyRow }) {
  const isSpike = row.direction === "spike";
  const Icon = isSpike ? TrendingUp : TrendingDown;
  const color = isSpike
    ? "bg-rose-500/10 text-rose-300 border-rose-500/30"
    : "bg-amber-500/10 text-amber-300 border-amber-500/30";
  const streak = row.any_streak ?? 0;
  return (
    <div
      className="flex items-start gap-2 rounded-md border border-border/60 bg-card/40 p-2.5"
      data-testid={`attention-row-${row.metric}-${row.id}`}
    >
      <Icon
        className={`h-4 w-4 mt-0.5 shrink-0 ${
          isSpike ? "text-rose-400" : "text-amber-400"
        }`}
      />
      <div className="flex-1 min-w-0 space-y-0.5">
        <div className="flex items-center gap-1.5 flex-wrap">
          <span className="text-xs font-semibold truncate">{row.name}</span>
          <Badge variant="outline" className="text-[9px] bg-secondary/40">
            {humanizeKey(row.metric)}
          </Badge>
          <Badge variant="outline" className={`text-[9px] ${color}`}>
            {isSpike ? "spike" : "dip"}
            {row.sigma !== null && ` · ${Math.abs(row.sigma).toFixed(1)}σ`}
          </Badge>
          {streak >= 2 && (
            <Badge
              variant="outline"
              className="text-[9px] bg-orange-500/10 text-orange-300 border-orange-500/30"
              data-testid={`attention-streak-badge-${row.metric}-${row.id}`}
              title={`Any streak: ${streak}d · Same-direction streak: ${row.directional_streak ?? streak}d`}
            >
              <Flame className="h-2.5 w-2.5 mr-0.5" />
              {streak}d streak
            </Badge>
          )}
        </div>
        <div className="text-[10px] text-muted-foreground">
          Today: <span className="font-mono font-semibold text-foreground">{row.today_count}</span>
          {" · "}
          30d avg: <span className="font-mono">{row.mean}</span>
          {row.stddev > 0 && (
            <>
              {" ± "}
              <span className="font-mono">{row.stddev}</span>
            </>
          )}
          {" · "}
          <span className={isSpike ? "text-rose-300" : "text-amber-300"}>
            {row.delta > 0 ? "+" : ""}
            {row.delta}
          </span>
        </div>
      </div>
    </div>
  );
}

function StreakBadge({ row }: { row: StreakRow }) {
  const isSpike = row.latest_direction === "spike";
  const streakColor =
    row.any_streak >= 5
      ? "bg-rose-500/15 text-rose-300 border-rose-500/40"
      : row.any_streak >= 3
      ? "bg-orange-500/15 text-orange-300 border-orange-500/40"
      : "bg-amber-500/15 text-amber-300 border-amber-500/40";
  return (
    <div
      className="flex items-start gap-2 rounded-md border border-border/60 bg-card/40 p-2.5"
      data-testid={`streak-row-${row.metric}-${row.id}`}
    >
      <Flame
        className={`h-4 w-4 mt-0.5 shrink-0 ${
          row.any_streak >= 5
            ? "text-rose-400"
            : row.any_streak >= 3
            ? "text-orange-400"
            : "text-amber-400"
        }`}
      />
      <div className="flex-1 min-w-0 space-y-0.5">
        <div className="flex items-center gap-1.5 flex-wrap">
          <span className="text-xs font-semibold truncate">{row.name}</span>
          <Badge variant="outline" className="text-[9px] bg-secondary/40">
            {humanizeKey(row.metric)}
          </Badge>
          <Badge variant="outline" className={`text-[9px] ${streakColor}`}>
            {row.any_streak}d streak
          </Badge>
          <Badge
            variant="outline"
            className={`text-[9px] ${
              isSpike
                ? "bg-rose-500/10 text-rose-300 border-rose-500/30"
                : "bg-amber-500/10 text-amber-300 border-amber-500/30"
            }`}
          >
            {isSpike ? "spike" : "dip"}
            {row.latest_sigma !== null &&
              ` · ${Math.abs(row.latest_sigma).toFixed(1)}σ`}
          </Badge>
        </div>
        <div className="text-[10px] text-muted-foreground">
          {row.directional_streak}d same-direction · latest{" "}
          <span className="font-mono">{row.latest_day}</span>
        </div>
      </div>
    </div>
  );
}

export default function AttentionFeedPanel({
  compact = false,
}: {
  compact?: boolean;
}) {
  const [data, setData] = useState<AnomalyResponse | null>(null);
  const [streaks, setStreaks] = useState<StreakRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [threshold, setThreshold] = useState<number>(2.0);
  const [windowDays, setWindowDays] = useState<number>(30);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [anom, str] = await Promise.all([
        api.get("/admin/metric-anomalies", {
          params: { threshold_sigma: threshold, days: windowDays },
        }),
        api.get("/admin/anomaly-streaks", {
          params: { min_streak: 2, limit: 10, max_lookback_days: 30 },
        }),
      ]);
      setData(anom.data);
      setStreaks(str.data?.streaks ?? []);
    } catch (e: any) {
      const detail =
        e?.response?.data?.detail || e?.message || "Failed to load anomalies";
      setError(detail);
      setData(null);
      setStreaks([]);
    } finally {
      setLoading(false);
    }
  }, [threshold, windowDays]);

  useEffect(() => {
    load();
  }, [load]);

  const flagged = data?.totals?.flagged ?? 0;
  const spikes = data?.totals?.spikes ?? 0;
  const dips = data?.totals?.dips ?? 0;

  // ── Compact mode: single-line badge summary for the Overview tab ─
  if (compact) {
    return (
      <Card
        className="bg-card border-border"
        data-testid="attention-feed-compact"
      >
        <CardContent className="py-3">
          <div className="flex items-center justify-between gap-3 flex-wrap">
            <div className="flex items-center gap-2 min-w-0">
              {flagged > 0 ? (
                <AlertTriangle className="h-4 w-4 text-rose-400 shrink-0" />
              ) : (
                <CheckCircle2 className="h-4 w-4 text-emerald-400 shrink-0" />
              )}
              <div className="min-w-0">
                <div className="text-sm font-semibold flex items-center gap-2 flex-wrap">
                  What needs attention today
                  {flagged > 0 ? (
                    <Badge
                      variant="outline"
                      className="text-[10px] bg-rose-500/10 text-rose-300 border-rose-500/30"
                      data-testid="attention-flagged-count"
                    >
                      {flagged} flagged · {spikes} ↑ / {dips} ↓
                    </Badge>
                  ) : (
                    <Badge
                      variant="outline"
                      className="text-[10px] bg-emerald-500/10 text-emerald-300 border-emerald-500/30"
                    >
                      All quiet
                    </Badge>
                  )}
                  {streaks.length > 0 && (
                    <Badge
                      variant="outline"
                      className="text-[10px] bg-orange-500/10 text-orange-300 border-orange-500/30"
                      data-testid="attention-streaks-count"
                      title={`${streaks.length} ongoing anomaly streak${streaks.length === 1 ? "" : "s"}`}
                    >
                      <Flame className="h-2.5 w-2.5 mr-0.5" />
                      {streaks.length} streak{streaks.length === 1 ? "" : "s"}
                    </Badge>
                  )}
                </div>
                {flagged > 0 && data && (
                  <div className="text-[11px] text-muted-foreground truncate">
                    Top:{" "}
                    <span className="text-foreground font-medium">
                      {data.top_anomalies[0].name}
                    </span>{" "}
                    ·{" "}
                    <span
                      className={
                        data.top_anomalies[0].direction === "spike"
                          ? "text-rose-300"
                          : "text-amber-300"
                      }
                    >
                      {humanizeKey(data.top_anomalies[0].metric)}{" "}
                      {data.top_anomalies[0].direction}
                      {data.top_anomalies[0].sigma !== null &&
                        ` · ${Math.abs(data.top_anomalies[0].sigma).toFixed(1)}σ`}
                    </span>
                  </div>
                )}
              </div>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={load}
              disabled={loading}
              data-testid="attention-feed-compact-refresh"
              className="h-7 shrink-0"
            >
              <RefreshCw className={`h-3 w-3 ${loading ? "animate-spin" : ""}`} />
            </Button>
          </div>
        </CardContent>
      </Card>
    );
  }

  // ── Full mode: detailed card with all flagged rows ────────────────
  return (
    <Card className="bg-card border-border" data-testid="attention-feed-panel">
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-3 flex-wrap">
          <div>
            <CardTitle className="flex items-center gap-2 text-base">
              <Sparkles className="h-4 w-4 text-rose-400" />
              What needs attention today
              {flagged > 0 && (
                <Badge
                  variant="outline"
                  className="text-[10px] bg-rose-500/10 text-rose-300 border-rose-500/30"
                  data-testid="attention-feed-badge"
                >
                  {flagged} flagged
                </Badge>
              )}
            </CardTitle>
            <CardDescription className="text-[11px]">
              Rows deviating &gt; {threshold}σ from their {windowDays}-day mean,
              across every registered metric.
            </CardDescription>
          </div>
          <div className="flex items-center gap-2">
            <Select
              value={String(threshold)}
              onValueChange={(v) => setThreshold(Number(v))}
            >
              <SelectTrigger
                className="h-8 text-xs w-[110px]"
                data-testid="attention-feed-threshold"
              >
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="1.5">≥ 1.5σ</SelectItem>
                <SelectItem value="2">≥ 2σ</SelectItem>
                <SelectItem value="2.5">≥ 2.5σ</SelectItem>
                <SelectItem value="3">≥ 3σ</SelectItem>
              </SelectContent>
            </Select>
            <Select
              value={String(windowDays)}
              onValueChange={(v) => setWindowDays(Number(v))}
            >
              <SelectTrigger
                className="h-8 text-xs w-[130px]"
                data-testid="attention-feed-window"
              >
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="7">7-day mean</SelectItem>
                <SelectItem value="14">14-day mean</SelectItem>
                <SelectItem value="30">30-day mean</SelectItem>
                <SelectItem value="60">60-day mean</SelectItem>
                <SelectItem value="90">90-day mean</SelectItem>
              </SelectContent>
            </Select>
            <Button
              variant="outline"
              size="sm"
              onClick={load}
              disabled={loading}
              data-testid="attention-feed-refresh"
              className="h-8"
            >
              <RefreshCw
                className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`}
              />
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {error && (
          <div
            className="flex items-center gap-2 text-xs text-rose-400"
            data-testid="attention-feed-error"
          >
            <AlertTriangle className="h-3.5 w-3.5" />
            {error}
          </div>
        )}
        {data && flagged === 0 && (
          <div
            className="flex items-center gap-2 text-xs text-emerald-300 rounded-md border border-emerald-500/30 bg-emerald-500/5 p-2"
            data-testid="attention-feed-empty"
          >
            <CheckCircle2 className="h-3.5 w-3.5" />
            All metrics within {threshold}σ of their {windowDays}-day means —
            nothing unusual today.
          </div>
        )}
        {data && flagged > 0 && (
          <>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
              {data.top_anomalies.map((row) => (
                <AnomalyBadge
                  key={`${row.metric}-${row.kind}-${row.id}`}
                  row={row}
                />
              ))}
            </div>
            <div className="text-[10px] text-muted-foreground text-right">
              {spikes} spike{spikes === 1 ? "" : "s"} · {dips} dip
              {dips === 1 ? "" : "s"} · updated{" "}
              {data && new Date(data.checked_at).toLocaleTimeString()}
            </div>
          </>
        )}

        {/* ── Top ongoing streaks (232N.58) ─────────────────────── */}
        {streaks.length > 0 && (
          <div
            className="pt-3 border-t border-border/40 space-y-2"
            data-testid="attention-streaks-section"
          >
            <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-muted-foreground">
              <Flame className="h-3 w-3 text-orange-400" />
              Top ongoing streaks
              <Badge
                variant="outline"
                className="text-[9px] bg-orange-500/10 text-orange-300 border-orange-500/30"
              >
                {streaks.length}
              </Badge>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
              {streaks.map((s) => (
                <StreakBadge key={`${s.metric}-${s.kind}-${s.id}`} row={s} />
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
