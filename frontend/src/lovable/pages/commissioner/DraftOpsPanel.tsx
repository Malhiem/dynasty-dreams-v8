/**
 * Iter 232N.46 — Draft Ops Panel.
 *
 * Commissioner-facing observability card for a league's draft workers +
 * per-draft health. Renders inside the Commissioner Settings → Draft tab.
 *
 * Data source: `GET /api/leagues/{leagueId}/draft-ops` (auth: commissioner
 * or platform admin). Auto-polls every 30 seconds so the "seconds
 * remaining" clock stays fresh without user intervention. Polls pause
 * when the browser tab is hidden.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Activity, RefreshCw, AlertTriangle, CircleDot, CircleDashed, Clock, Users, User } from "lucide-react";
import api from "@/lib/api";

interface DraftOpsProps {
  leagueId?: string;
}

interface WorkerSummary {
  last_run_at: string | null;
  seconds_since_last_run: number | null;
  counts: Record<string, number>;
  error: string | null;
  healthy: boolean;
  expected_interval_seconds: number;
}

interface OwnerSlot {
  id: string;
  name: string;
  online: boolean;
}

interface OnClockInfo {
  abbr: string;
  team_id: string | null;
  team_name: string;
  owners: OwnerSlot[];
  admin_managed: boolean;
  is_ownerless: boolean;
}

interface DraftRow {
  id: string;
  name: string;
  status: string;
  scheduled_time: string | null;
  started_at: string | null;
  current_pick: number;
  total_picks: number | null;
  picks_made: number;
  team_count: number;
  total_rounds: number;
  time_per_pick: number | null;
  personal_pick_timer_seconds: number | null;
  missed_pick_action: string;
  timer_paused: boolean;
  current_pick_started_at: string | null;
  seconds_remaining: number | null;
  on_clock: OnClockInfo | null;
}

interface DraftOpsResponse {
  league_id: string;
  checked_at: string;
  workers: { autostart: WorkerSummary; pick_timer: WorkerSummary };
  drafts: DraftRow[];
}

const fmtSeconds = (s: number | null | undefined): string => {
  if (s == null) return "—";
  const abs = Math.abs(s);
  const h = Math.floor(abs / 3600);
  const m = Math.floor((abs % 3600) / 60);
  const sec = abs % 60;
  const sign = s < 0 ? "-" : "";
  if (h > 0) return `${sign}${h}h ${m}m`;
  if (m > 0) return `${sign}${m}m ${sec}s`;
  return `${sign}${sec}s`;
};

const statusBadgeClass = (status: string): string => {
  switch (status) {
    case "active":
      return "bg-emerald-500/15 text-emerald-400 border-emerald-500/30";
    case "scheduled":
      return "bg-amber-500/15 text-amber-400 border-amber-500/30";
    case "completed":
      return "bg-cyan-500/15 text-cyan-400 border-cyan-500/30";
    default:
      return "bg-muted text-muted-foreground";
  }
};

function WorkerCard({ label, worker }: { label: string; worker: WorkerSummary }) {
  const healthy = worker.healthy;
  return (
    <div
      className={`rounded-md border p-3 ${
        healthy
          ? "bg-emerald-500/5 border-emerald-500/30"
          : "bg-rose-500/5 border-rose-500/40"
      }`}
      data-testid={`draft-ops-worker-${label.toLowerCase().replace(/\s/g, "-")}`}
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-sm font-medium">
          {healthy ? (
            <CircleDot className="h-3.5 w-3.5 text-emerald-400" />
          ) : (
            <AlertTriangle className="h-3.5 w-3.5 text-rose-400" />
          )}
          {label}
        </div>
        <Badge variant="outline" className="text-[10px]">
          every {worker.expected_interval_seconds}s
        </Badge>
      </div>
      <div className="mt-2 text-xs text-muted-foreground">
        Last run{" "}
        <span className="font-medium text-foreground" data-testid={`draft-ops-worker-${label.toLowerCase().replace(/\s/g, "-")}-age`}>
          {worker.seconds_since_last_run != null
            ? fmtSeconds(worker.seconds_since_last_run) + " ago"
            : "never"}
        </span>
      </div>
      <div className="mt-2 flex flex-wrap gap-1">
        {Object.entries(worker.counts).map(([k, v]) => (
          <Badge key={k} variant="outline" className="text-[10px] capitalize">
            {k}: {v}
          </Badge>
        ))}
      </div>
      {worker.error && (
        <div className="mt-2 text-xs text-rose-400 font-mono truncate" title={worker.error}>
          {worker.error}
        </div>
      )}
    </div>
  );
}

function DraftRowCard({ draft }: { draft: DraftRow }) {
  const onlineCount = draft.on_clock?.owners.filter((o) => o.online).length ?? 0;
  const hasOwners = (draft.on_clock?.owners.length ?? 0) > 0;
  const isStalledOffline =
    draft.status === "active" &&
    draft.on_clock != null &&
    hasOwners &&
    onlineCount === 0 &&
    (draft.seconds_remaining ?? 1) <= 0;
  return (
    <div
      className={`rounded-md border p-3 ${
        isStalledOffline
          ? "border-rose-500/40 bg-rose-500/5"
          : "border-border bg-card/60"
      }`}
      data-testid={`draft-ops-draft-${draft.id}`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <div className="text-sm font-semibold truncate" title={draft.name}>
              {draft.name}
            </div>
            <Badge variant="outline" className={`text-[10px] ${statusBadgeClass(draft.status)}`}>
              {draft.status}
            </Badge>
            {draft.timer_paused && (
              <Badge variant="outline" className="text-[10px] bg-amber-500/15 text-amber-400 border-amber-500/30">
                paused
              </Badge>
            )}
            {isStalledOffline && (
              <Badge variant="outline" className="text-[10px] bg-rose-500/15 text-rose-400 border-rose-500/30">
                <AlertTriangle className="h-3 w-3 mr-1" />
                stalled offline
              </Badge>
            )}
          </div>
          <div className="mt-1 text-xs text-muted-foreground">
            Pick{" "}
            <span className="font-medium text-foreground">{draft.current_pick}</span>
            {draft.total_picks != null && (
              <>
                {" of "}
                <span className="font-medium text-foreground">{draft.total_picks}</span>
              </>
            )}{" · "}
            <span className="font-medium text-foreground">{draft.picks_made}</span> picks made{" · "}
            <span className="font-medium text-foreground">{draft.team_count}</span> teams{" · "}
            <span className="font-medium text-foreground">{draft.total_rounds}</span> rounds
          </div>
        </div>
        {draft.status === "active" && draft.seconds_remaining != null && (
          <div className="text-right shrink-0" data-testid={`draft-ops-remaining-${draft.id}`}>
            <div className="text-[10px] uppercase tracking-wider text-muted-foreground">
              Clock
            </div>
            <div
              className={`text-lg font-mono font-semibold tabular-nums ${
                draft.seconds_remaining <= 0 ? "text-rose-400" : "text-emerald-400"
              }`}
            >
              {draft.seconds_remaining > 0
                ? fmtSeconds(draft.seconds_remaining)
                : "expired"}
            </div>
          </div>
        )}
      </div>

      {draft.on_clock && (
        <div className="mt-2 pt-2 border-t border-border/50">
          <div className="flex items-center gap-2 text-xs">
            <Users className="h-3.5 w-3.5 text-muted-foreground" />
            <span className="text-muted-foreground">On the clock:</span>
            <span className="font-medium">{draft.on_clock.team_name}</span>
            <Badge variant="outline" className="text-[10px]">
              {draft.on_clock.abbr}
            </Badge>
            {draft.on_clock.is_ownerless && (
              <Badge variant="outline" className="text-[10px] bg-rose-500/10 text-rose-400 border-rose-500/30">
                ownerless (auto)
              </Badge>
            )}
            {draft.on_clock.admin_managed && (
              <Badge variant="outline" className="text-[10px] bg-fuchsia-500/10 text-fuchsia-400 border-fuchsia-500/30">
                admin-managed
              </Badge>
            )}
          </div>
          {draft.on_clock.owners.length > 0 && (
            <div className="mt-1.5 flex flex-wrap gap-2">
              {draft.on_clock.owners.map((o) => (
                <div
                  key={o.id}
                  className="flex items-center gap-1.5 text-[11px]"
                  data-testid={`draft-ops-owner-${draft.id}-${o.id}`}
                >
                  {o.online ? (
                    <CircleDot className="h-3 w-3 text-emerald-400 fill-emerald-400" />
                  ) : (
                    <CircleDashed className="h-3 w-3 text-muted-foreground" />
                  )}
                  <User className="h-3 w-3 text-muted-foreground" />
                  <span className={o.online ? "text-emerald-400" : "text-muted-foreground"}>
                    {o.name}
                  </span>
                  <span className="text-[10px] text-muted-foreground">
                    ({o.online ? "online" : "offline"})
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      <div className="mt-2 pt-2 border-t border-border/50 flex flex-wrap gap-1.5 text-[10px]">
        <Badge variant="outline">
          <Clock className="h-2.5 w-2.5 mr-1" />
          {draft.time_per_pick ? `${Math.round(draft.time_per_pick / 60)}m per pick` : "no clock"}
        </Badge>
        {draft.personal_pick_timer_seconds ? (
          <Badge variant="outline" className="bg-indigo-500/10 text-indigo-400 border-indigo-500/30">
            personal cap {Math.round(draft.personal_pick_timer_seconds / 60)}m
          </Badge>
        ) : null}
        <Badge variant="outline" className="capitalize">
          missed: {draft.missed_pick_action}
        </Badge>
        {draft.scheduled_time && (
          <Badge variant="outline">
            sched {new Date(draft.scheduled_time).toLocaleString()}
          </Badge>
        )}
      </div>
    </div>
  );
}

export default function DraftOpsPanel({ leagueId }: DraftOpsProps) {
  const [data, setData] = useState<DraftOpsResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchOps = useCallback(async () => {
    if (!leagueId) return;
    setLoading(true);
    try {
      const { data } = await api.get(`/leagues/${leagueId}/draft-ops`);
      setData(data);
      setError(null);
    } catch (e: any) {
      const detail = e?.response?.data?.detail || e?.message || "Failed to load draft ops";
      setError(detail);
    } finally {
      setLoading(false);
    }
  }, [leagueId]);

  useEffect(() => {
    fetchOps();
  }, [fetchOps]);

  // Auto-poll every 30s; pause when tab is hidden.
  useEffect(() => {
    if (!leagueId) return;
    const tick = () => {
      if (document.visibilityState === "visible") {
        fetchOps();
      }
    };
    const id = window.setInterval(tick, 30_000);
    return () => window.clearInterval(id);
  }, [leagueId, fetchOps]);

  const stalledCount = useMemo(() => {
    if (!data) return 0;
    return data.drafts.filter(
      (d) =>
        d.status === "active" &&
        d.on_clock != null &&
        (d.on_clock.owners.length ?? 0) > 0 &&
        d.on_clock.owners.every((o) => !o.online) &&
        (d.seconds_remaining ?? 1) <= 0,
    ).length;
  }, [data]);

  if (!leagueId) {
    return null;
  }

  if (error && !data) {
    // Non-commissioners get a 403 here — hide the panel silently so it
    // doesn't leak into non-admin UIs.
    if (error.toLowerCase().includes("commissioner")) return null;
    return (
      <Card className="border-rose-500/40 bg-rose-500/5">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-rose-400">
            <AlertTriangle className="h-4 w-4" />
            Draft Ops
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-sm text-rose-300 font-mono">{error}</div>
          <Button
            variant="outline"
            size="sm"
            onClick={fetchOps}
            className="mt-3"
            data-testid="draft-ops-retry-btn"
          >
            <RefreshCw className="h-3 w-3 mr-1" />
            Retry
          </Button>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="bg-card border-border" data-testid="draft-ops-panel">
      <CardHeader>
        <div className="flex items-start justify-between gap-3">
          <div>
            <CardTitle className="flex items-center gap-2">
              <Activity className="h-4 w-4 text-cyan-400" />
              Draft Ops
              {stalledCount > 0 && (
                <Badge className="bg-rose-500/20 text-rose-300 border-rose-500/40" variant="outline">
                  {stalledCount} stalled
                </Badge>
              )}
            </CardTitle>
            <CardDescription>
              Worker health + per-draft snapshot. Refreshes every 30s.
            </CardDescription>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={fetchOps}
            disabled={loading}
            data-testid="draft-ops-refresh-btn"
          >
            <RefreshCw className={`h-3 w-3 mr-1 ${loading ? "animate-spin" : ""}`} />
            Refresh
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {data ? (
          <>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <WorkerCard label="Auto-start" worker={data.workers.autostart} />
              <WorkerCard label="Pick timer" worker={data.workers.pick_timer} />
            </div>

            {data.drafts.length === 0 ? (
              <div className="text-sm text-muted-foreground italic">
                No active or scheduled drafts in this league.
              </div>
            ) : (
              <div className="space-y-2">
                {data.drafts.map((d) => (
                  <DraftRowCard key={d.id} draft={d} />
                ))}
              </div>
            )}
            <div className="text-[10px] text-muted-foreground text-right">
              Checked at {new Date(data.checked_at).toLocaleTimeString()}
            </div>
          </>
        ) : (
          <div className="text-sm text-muted-foreground">Loading draft ops…</div>
        )}
      </CardContent>
    </Card>
  );
}
