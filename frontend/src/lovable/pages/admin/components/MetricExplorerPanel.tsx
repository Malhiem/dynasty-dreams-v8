/**
 * Iter 232N.56 — Metric Explorer Panel.
 *
 * Admin-only interactive surface for the generic daily-rollup framework
 * (`services/daily_rollup.py`). Lets an admin:
 *
 *   • pick any registered metric from a discovery dropdown
 *   • pick a bucketing dimension (`kind`) — e.g. league vs commissioner
 *   • view a per-day trend line (with breakdown series stacked)
 *   • view a top-N horizontal bar leaderboard
 *   • see grand totals + breakdown counts + freshness signal
 *
 * Talks to:
 *   • GET /api/admin/daily-metrics/registered
 *   • GET /api/admin/daily-metrics?metric=…&kind=…&days=…&limit=…
 */
import { useCallback, useEffect, useMemo, useState } from "react";
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
import { Label } from "@/components/ui/label";
import {
  BarChart3,
  RefreshCw,
  AlertTriangle,
  Sparkles,
  ClipboardCopy,
  Download,
} from "lucide-react";
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";
import { toast } from "sonner";
import api from "@/lib/api";

interface MetricEntry {
  key: string;
  description: string;
  kinds: string[];
  last_seen_day: string | null;
}

interface LeaderboardRow {
  id: string;
  name: string;
  count: number;
  breakdown: Record<string, number>;
}

interface TrendRow {
  day: string;
  count: number;
  breakdown: Record<string, number>;
}

interface MetricData {
  checked_at: string;
  metric: string;
  kind: string;
  window_days: number;
  leaderboard: LeaderboardRow[];
  trend: TrendRow[];
  totals: { count: number; breakdown: Record<string, number> };
}

// Colours reused across breakdown series so palettes stay coherent.
const SERIES_COLORS = [
  "#22d3ee", // cyan
  "#a78bfa", // violet
  "#f59e0b", // amber
  "#34d399", // emerald
  "#f472b6", // pink
  "#f87171", // rose
];

function fmt(n: number | undefined | null): string {
  if (n === undefined || n === null) return "—";
  return Number(n).toLocaleString();
}

function humanizeKey(k: string): string {
  return k
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

export default function MetricExplorerPanel() {
  const [metrics, setMetrics] = useState<MetricEntry[]>([]);
  const [selectedMetric, setSelectedMetric] = useState<string>("");
  const [selectedKind, setSelectedKind] = useState<string>("");
  const [windowDays, setWindowDays] = useState<number>(30);
  const [limit, setLimit] = useState<number>(10);
  const [data, setData] = useState<MetricData | null>(null);
  const [loadingMetrics, setLoadingMetrics] = useState(false);
  const [loadingData, setLoadingData] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // ── Load registered metrics on mount ───────────────────────────
  const loadRegistered = useCallback(async () => {
    setLoadingMetrics(true);
    setError(null);
    try {
      const { data } = await api.get("/admin/daily-metrics/registered");
      const list: MetricEntry[] = data?.metrics ?? [];
      setMetrics(list);
    } catch (e: any) {
      const detail =
        e?.response?.data?.detail || e?.message || "Failed to load metrics";
      setError(detail);
    } finally {
      setLoadingMetrics(false);
    }
  }, []);

  useEffect(() => {
    loadRegistered();
  }, [loadRegistered]);

  // Auto-select the first metric + a valid kind once discovery lands.
  useEffect(() => {
    if (metrics.length === 0 || selectedMetric) return;
    setSelectedMetric(metrics[0].key);
    setSelectedKind(metrics[0].kinds?.[0] ?? "league");
  }, [metrics, selectedMetric]);

  // ── When selected metric changes, snap kind to a valid value ───
  const activeMetric = useMemo(
    () => metrics.find((m) => m.key === selectedMetric),
    [metrics, selectedMetric],
  );

  useEffect(() => {
    if (!activeMetric) return;
    const kinds = activeMetric.kinds ?? [];
    if (kinds.length > 0 && !kinds.includes(selectedKind)) {
      setSelectedKind(kinds[0]);
    } else if (kinds.length === 0 && !selectedKind) {
      setSelectedKind("league");
    }
  }, [activeMetric, selectedKind]);

  // ── Load data whenever metric/kind/window/limit change ─────────
  const loadData = useCallback(async () => {
    if (!selectedMetric || !selectedKind) return;
    setLoadingData(true);
    setError(null);
    try {
      const { data } = await api.get("/admin/daily-metrics", {
        params: {
          metric: selectedMetric,
          kind: selectedKind,
          days: windowDays,
          limit,
        },
      });
      setData(data);
    } catch (e: any) {
      const detail =
        e?.response?.data?.detail || e?.message || "Failed to load metric data";
      setError(detail);
      setData(null);
    } finally {
      setLoadingData(false);
    }
  }, [selectedMetric, selectedKind, windowDays, limit]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // ── Derived data ───────────────────────────────────────────────
  const breakdownKeys = useMemo(() => {
    if (!data) return [] as string[];
    return Object.keys(data.totals.breakdown ?? {}).sort();
  }, [data]);

  const trendSeries = useMemo(() => {
    if (!data) return [] as any[];
    return data.trend.map((t) => {
      const row: Record<string, any> = {
        day: t.day.slice(5), // "MM-DD"
        fullDay: t.day,
        count: t.count,
      };
      for (const k of breakdownKeys) {
        row[k] = t.breakdown?.[k] ?? 0;
      }
      return row;
    });
  }, [data, breakdownKeys]);

  const leaderboardSeries = useMemo(() => {
    if (!data) return [] as any[];
    return data.leaderboard.map((r) => ({
      id: r.id,
      name:
        r.name.length > 24 ? `${r.name.slice(0, 22)}…` : r.name,
      fullName: r.name,
      count: r.count,
      ...(r.breakdown ?? {}),
    }));
  }, [data]);

  const copyRaw = () => {
    if (!data) return;
    try {
      navigator.clipboard.writeText(JSON.stringify(data, null, 2));
      toast.success("Raw JSON copied to clipboard");
    } catch {
      toast.error("Clipboard access denied");
    }
  };

  const downloadCsv = () => {
    if (!data) return;
    const headers = ["rank", "id", "name", "count", ...breakdownKeys];
    const rows = data.leaderboard.map((r, i) => [
      String(i + 1),
      r.id,
      `"${(r.name || "").replace(/"/g, '""')}"`,
      String(r.count),
      ...breakdownKeys.map((k) => String(r.breakdown?.[k] ?? 0)),
    ]);
    const csv = [headers.join(","), ...rows.map((r) => r.join(","))].join("\n");
    const blob = new Blob([csv], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `metric_${data.metric}_${data.kind}_${data.window_days}d.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  // ── Render ─────────────────────────────────────────────────────
  return (
    <Card className="bg-card border-border" data-testid="metric-explorer-panel">
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-3 flex-wrap">
          <div>
            <CardTitle className="flex items-center gap-2 text-base">
              <Sparkles className="h-4 w-4 text-fuchsia-400" />
              Metric Explorer
              {data && (
                <Badge
                  variant="outline"
                  className="text-[10px] bg-fuchsia-500/10 text-fuchsia-300 border-fuchsia-500/30"
                  data-testid="metric-explorer-total-badge"
                >
                  {fmt(data.totals.count)} in last {data.window_days}d
                </Badge>
              )}
            </CardTitle>
            <CardDescription className="text-[11px]">
              Explore any metric registered in the daily-rollup framework.
              Powered by <code className="text-[10px]">/admin/daily-metrics</code>.
            </CardDescription>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={loadData}
              disabled={loadingData || !selectedMetric}
              data-testid="metric-explorer-refresh"
              className="h-8"
            >
              <RefreshCw
                className={`h-3.5 w-3.5 ${loadingData ? "animate-spin" : ""}`}
              />
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={copyRaw}
              disabled={!data}
              data-testid="metric-explorer-copy-raw"
              className="h-8"
              title="Copy raw JSON"
            >
              <ClipboardCopy className="h-3.5 w-3.5" />
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={downloadCsv}
              disabled={!data || data.leaderboard.length === 0}
              data-testid="metric-explorer-download-csv"
              className="h-8"
              title="Download leaderboard as CSV"
            >
              <Download className="h-3.5 w-3.5" />
            </Button>
          </div>
        </div>
      </CardHeader>

      <CardContent className="space-y-4">
        {/* ── Controls row ───────────────────────────────────── */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
          <div className="space-y-1.5">
            <Label className="text-[10px] uppercase tracking-wider text-muted-foreground">
              Metric
            </Label>
            <Select
              value={selectedMetric}
              onValueChange={(v) => setSelectedMetric(v)}
              disabled={loadingMetrics || metrics.length === 0}
            >
              <SelectTrigger
                className="h-9 text-xs"
                data-testid="metric-explorer-metric-select"
              >
                <SelectValue placeholder="Choose a metric" />
              </SelectTrigger>
              <SelectContent>
                {metrics.map((m) => (
                  <SelectItem
                    key={m.key}
                    value={m.key}
                    textValue={humanizeKey(m.key)}
                  >
                    <span className="text-xs font-medium">
                      {humanizeKey(m.key)}
                    </span>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {activeMetric?.description && (
              <div className="text-[10px] text-muted-foreground italic leading-tight">
                {activeMetric.description}
              </div>
            )}
            {activeMetric?.last_seen_day && (
              <div className="text-[10px] text-muted-foreground">
                Last rolled up: {activeMetric.last_seen_day}
              </div>
            )}
          </div>

          <div className="space-y-1.5">
            <Label className="text-[10px] uppercase tracking-wider text-muted-foreground">
              Bucket by
            </Label>
            <Select
              value={selectedKind}
              onValueChange={(v) => setSelectedKind(v)}
              disabled={!activeMetric || (activeMetric.kinds?.length ?? 0) === 0}
            >
              <SelectTrigger
                className="h-9 text-xs"
                data-testid="metric-explorer-kind-select"
              >
                <SelectValue placeholder="Kind" />
              </SelectTrigger>
              <SelectContent>
                {(activeMetric?.kinds ?? []).map((k) => (
                  <SelectItem key={k} value={k}>
                    <span className="text-xs">{humanizeKey(k)}</span>
                  </SelectItem>
                ))}
                {(activeMetric?.kinds?.length ?? 0) === 0 && (
                  <SelectItem value="league" disabled>
                    <span className="text-xs text-muted-foreground">
                      (no rollup rows yet)
                    </span>
                  </SelectItem>
                )}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1.5">
            <Label className="text-[10px] uppercase tracking-wider text-muted-foreground">
              Window
            </Label>
            <Select
              value={String(windowDays)}
              onValueChange={(v) => setWindowDays(Number(v))}
            >
              <SelectTrigger
                className="h-9 text-xs"
                data-testid="metric-explorer-window-select"
              >
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="7">Last 7 days</SelectItem>
                <SelectItem value="30">Last 30 days</SelectItem>
                <SelectItem value="90">Last 90 days</SelectItem>
                <SelectItem value="180">Last 180 days</SelectItem>
                <SelectItem value="365">Last year</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1.5">
            <Label className="text-[10px] uppercase tracking-wider text-muted-foreground">
              Top N
            </Label>
            <Select
              value={String(limit)}
              onValueChange={(v) => setLimit(Number(v))}
            >
              <SelectTrigger
                className="h-9 text-xs"
                data-testid="metric-explorer-limit-select"
              >
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="5">Top 5</SelectItem>
                <SelectItem value="10">Top 10</SelectItem>
                <SelectItem value="25">Top 25</SelectItem>
                <SelectItem value="50">Top 50</SelectItem>
                <SelectItem value="100">Top 100</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>

        {error && (
          <div
            className="flex items-center gap-2 text-xs text-rose-400 rounded-md border border-rose-500/30 bg-rose-500/5 p-2"
            data-testid="metric-explorer-error"
          >
            <AlertTriangle className="h-3.5 w-3.5" />
            {error}
          </div>
        )}

        {/* ── Totals + breakdown chips ────────────────────────── */}
        {data && (
          <div
            className="flex flex-wrap items-center gap-2"
            data-testid="metric-explorer-totals"
          >
            <div className="rounded-md border border-border/60 bg-secondary/30 px-3 py-1.5">
              <div className="text-[10px] uppercase tracking-wider text-muted-foreground">
                Total
              </div>
              <div className="text-lg font-bold tabular-nums leading-tight">
                {fmt(data.totals.count)}
              </div>
            </div>
            {breakdownKeys.map((k, i) => (
              <div
                key={k}
                className="rounded-md border border-border/60 bg-secondary/30 px-3 py-1.5"
                data-testid={`metric-explorer-breakdown-${k}`}
              >
                <div className="text-[10px] uppercase tracking-wider text-muted-foreground flex items-center gap-1">
                  <span
                    className="inline-block w-2 h-2 rounded-sm"
                    style={{
                      backgroundColor: SERIES_COLORS[i % SERIES_COLORS.length],
                    }}
                  />
                  {humanizeKey(k)}
                </div>
                <div className="text-lg font-bold tabular-nums leading-tight">
                  {fmt(data.totals.breakdown?.[k])}
                </div>
              </div>
            ))}
          </div>
        )}

        {/* ── Trend chart ─────────────────────────────────────── */}
        {data && (
          <div
            className="rounded-md border border-border/60 bg-card/40 p-3"
            data-testid="metric-explorer-trend"
          >
            <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-2 flex items-center gap-1.5">
              <BarChart3 className="h-3 w-3" />
              Trend — daily {humanizeKey(selectedMetric)} ({humanizeKey(
                selectedKind,
              )})
            </div>
            <ResponsiveContainer width="100%" height={220}>
              <LineChart
                data={trendSeries}
                margin={{ top: 10, right: 12, left: 0, bottom: 0 }}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="#ffffff10" />
                <XAxis
                  dataKey="day"
                  tick={{ fontSize: 10, fill: "#94a3b8" }}
                  axisLine={{ stroke: "#ffffff20" }}
                  tickLine={{ stroke: "#ffffff20" }}
                />
                <YAxis
                  allowDecimals={false}
                  tick={{ fontSize: 10, fill: "#94a3b8" }}
                  axisLine={{ stroke: "#ffffff20" }}
                  tickLine={{ stroke: "#ffffff20" }}
                  width={30}
                />
                <Tooltip
                  contentStyle={{
                    background: "#0b1220",
                    border: "1px solid #334155",
                    borderRadius: 6,
                    fontSize: 11,
                  }}
                  labelFormatter={(v: any, payload: any) =>
                    payload?.[0]?.payload?.fullDay ?? v
                  }
                />
                <Legend wrapperStyle={{ fontSize: 10 }} />
                <Line
                  type="monotone"
                  dataKey="count"
                  name="Total"
                  stroke="#e879f9"
                  strokeWidth={2}
                  dot={false}
                  activeDot={{ r: 4 }}
                />
                {breakdownKeys.map((k, i) => (
                  <Line
                    key={k}
                    type="monotone"
                    dataKey={k}
                    name={humanizeKey(k)}
                    stroke={SERIES_COLORS[i % SERIES_COLORS.length]}
                    strokeWidth={1.5}
                    dot={false}
                    strokeOpacity={0.85}
                  />
                ))}
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}

        {/* ── Leaderboard ─────────────────────────────────────── */}
        {data && (
          <div
            className="rounded-md border border-border/60 bg-card/40 p-3"
            data-testid="metric-explorer-leaderboard"
          >
            <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-2">
              Top {leaderboardSeries.length} {humanizeKey(selectedKind)}s
            </div>
            {leaderboardSeries.length === 0 ? (
              <div className="text-xs text-muted-foreground italic">
                No rollup rows for this metric + kind in the selected window.
              </div>
            ) : (
              <>
                <ResponsiveContainer
                  width="100%"
                  height={Math.max(180, leaderboardSeries.length * 28 + 40)}
                >
                  <BarChart
                    data={leaderboardSeries}
                    layout="vertical"
                    margin={{ top: 5, right: 24, left: 8, bottom: 0 }}
                  >
                    <CartesianGrid
                      strokeDasharray="3 3"
                      stroke="#ffffff10"
                      horizontal={false}
                    />
                    <XAxis
                      type="number"
                      allowDecimals={false}
                      tick={{ fontSize: 10, fill: "#94a3b8" }}
                      axisLine={{ stroke: "#ffffff20" }}
                      tickLine={{ stroke: "#ffffff20" }}
                    />
                    <YAxis
                      type="category"
                      dataKey="name"
                      tick={{ fontSize: 10, fill: "#e2e8f0" }}
                      axisLine={{ stroke: "#ffffff20" }}
                      tickLine={{ stroke: "#ffffff20" }}
                      width={140}
                    />
                    <Tooltip
                      contentStyle={{
                        background: "#0b1220",
                        border: "1px solid #334155",
                        borderRadius: 6,
                        fontSize: 11,
                      }}
                      labelFormatter={(v: any, payload: any) =>
                        payload?.[0]?.payload?.fullName ?? v
                      }
                    />
                    {breakdownKeys.length > 0 ? (
                      breakdownKeys.map((k, i) => (
                        <Bar
                          key={k}
                          dataKey={k}
                          name={humanizeKey(k)}
                          stackId="s"
                          fill={SERIES_COLORS[i % SERIES_COLORS.length]}
                          radius={
                            i === breakdownKeys.length - 1
                              ? [0, 3, 3, 0]
                              : [0, 0, 0, 0]
                          }
                        />
                      ))
                    ) : (
                      <Bar
                        dataKey="count"
                        name="Count"
                        fill="#e879f9"
                        radius={[0, 3, 3, 0]}
                      />
                    )}
                    <Legend wrapperStyle={{ fontSize: 10 }} />
                  </BarChart>
                </ResponsiveContainer>

                {/* Detail table */}
                <div className="mt-3 overflow-x-auto">
                  <table
                    className="w-full text-[11px]"
                    data-testid="metric-explorer-leaderboard-table"
                  >
                    <thead>
                      <tr className="text-left text-muted-foreground border-b border-border/60">
                        <th className="py-1 pr-2 w-8">#</th>
                        <th className="py-1 pr-2">Name</th>
                        <th className="py-1 pr-2 text-right w-16">Total</th>
                        {breakdownKeys.map((k) => (
                          <th
                            key={k}
                            className="py-1 pr-2 text-right w-16"
                          >
                            {humanizeKey(k)}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {data.leaderboard.map((r, i) => (
                        <tr
                          key={r.id}
                          className="border-b border-border/30 last:border-0"
                          data-testid={`metric-explorer-row-${r.id}`}
                        >
                          <td className="py-1 pr-2 text-muted-foreground tabular-nums">
                            {i + 1}
                          </td>
                          <td className="py-1 pr-2 truncate max-w-[240px]">
                            {r.name}
                          </td>
                          <td className="py-1 pr-2 text-right font-mono font-semibold">
                            {fmt(r.count)}
                          </td>
                          {breakdownKeys.map((k) => (
                            <td
                              key={k}
                              className="py-1 pr-2 text-right font-mono text-muted-foreground"
                            >
                              {fmt(r.breakdown?.[k])}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            )}
          </div>
        )}

        {data && (
          <div className="text-[10px] text-muted-foreground text-right">
            updated {new Date(data.checked_at).toLocaleTimeString()}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
