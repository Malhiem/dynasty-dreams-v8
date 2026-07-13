/**
 * Iter 232N.52 — Recent Commissioner Overrides Panel.
 *
 * Read-only feed of every commissioner-fired action in this league:
 * pick undos (`draft_undo_audit`) + offline-manager pings
 * (`commissioner_pings`). Visible to any league member — this is a
 * transparency surface, not a privileged one. Renders inline inside
 * the Draft Ops dashboard but can also be composed elsewhere.
 *
 * Data source: `GET /api/leagues/{leagueId}/commissioner-overrides`
 */
import { useCallback, useEffect, useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Gavel,
  RefreshCw,
  Undo2,
  BellRing,
  ChevronDown,
  ChevronRight,
  ShieldAlert,
} from "lucide-react";
import api from "@/lib/api";

interface Props {
  leagueId?: string;
  /** Max events to load per fetch (server-capped at 100). Default 30. */
  limit?: number;
  /** Auto-poll interval in ms. 0 disables polling. Default 60s. */
  pollMs?: number;
  /** When true, starts collapsed. */
  defaultCollapsed?: boolean;
}

interface Commissioner {
  id: string | null;
  name: string;
}

interface UndoDetail {
  pick_number: number;
  removed_count: number;
  cascade: boolean;
  player_name: string | null;
  team: string | null;
  on_the_clock_after: string | null;
}

interface PingDetail {
  target_user_id: string;
  target_name: string;
  target_team_name: string | null;
  draft_id: string;
  channels_fired: string[];
}

interface EventRow {
  type: "pick_undo" | "owner_ping";
  at: string;
  commissioner: Commissioner;
  reason: string | null;
  detail: UndoDetail | PingDetail;
}

interface Response {
  league_id: string;
  checked_at: string;
  count: number;
  events: EventRow[];
}

function relativeTime(iso: string): string {
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return "unknown";
  const diffSec = Math.round((Date.now() - t) / 1000);
  if (diffSec < 60) return `${diffSec}s ago`;
  if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m ago`;
  if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}h ago`;
  return `${Math.floor(diffSec / 86400)}d ago`;
}

function UndoRow({ ev }: { ev: EventRow & { detail: UndoDetail } }) {
  const d = ev.detail;
  return (
    <div
      className="flex items-start gap-2 border-l-2 border-amber-500/40 pl-3 py-1.5"
      data-testid={`override-undo-${d.pick_number}`}
    >
      <Undo2 className="h-3.5 w-3.5 text-amber-400 mt-0.5 shrink-0" />
      <div className="flex-1 min-w-0">
        <div className="text-xs">
          <span className="font-semibold">{ev.commissioner.name}</span>
          <span className="text-muted-foreground"> undid pick </span>
          <span className="font-mono font-semibold">#{d.pick_number}</span>
          {d.player_name && (
            <>
              {" "}
              <span className="text-muted-foreground">·</span>{" "}
              <span className="font-medium">{d.player_name}</span>
              {d.team && (
                <span className="text-muted-foreground"> ({d.team})</span>
              )}
            </>
          )}
          {d.cascade && d.removed_count > 1 && (
            <Badge
              variant="outline"
              className="ml-1.5 text-[9px] bg-rose-500/15 text-rose-300 border-rose-500/30"
            >
              cascade × {d.removed_count}
            </Badge>
          )}
        </div>
        {d.on_the_clock_after && (
          <div className="text-[10px] text-muted-foreground mt-0.5">
            → <span className="text-emerald-400 font-medium">{d.on_the_clock_after}</span> back on the clock
          </div>
        )}
        {ev.reason && (
          <div className="text-[10px] text-muted-foreground italic mt-0.5">
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

function PingRow({ ev }: { ev: EventRow & { detail: PingDetail } }) {
  const d = ev.detail;
  return (
    <div
      className="flex items-start gap-2 border-l-2 border-cyan-500/40 pl-3 py-1.5"
      data-testid={`override-ping-${d.target_user_id}`}
    >
      <BellRing className="h-3.5 w-3.5 text-cyan-400 mt-0.5 shrink-0" />
      <div className="flex-1 min-w-0">
        <div className="text-xs">
          <span className="font-semibold">{ev.commissioner.name}</span>
          <span className="text-muted-foreground"> pinged </span>
          <span className="font-medium">{d.target_name}</span>
          {d.target_team_name && (
            <span className="text-muted-foreground"> ({d.target_team_name})</span>
          )}
        </div>
        {d.channels_fired && d.channels_fired.length > 0 && (
          <div className="flex flex-wrap gap-1 mt-0.5">
            {d.channels_fired.map((c) => (
              <Badge
                key={c}
                variant="outline"
                className="text-[9px] bg-cyan-500/10 text-cyan-300 border-cyan-500/30"
              >
                {c}
              </Badge>
            ))}
          </div>
        )}
        {ev.reason && (
          <div className="text-[10px] text-muted-foreground italic mt-0.5">
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

export default function RecentOverridesPanel({
  leagueId,
  limit = 30,
  pollMs = 60_000,
  defaultCollapsed = false,
}: Props) {
  const [data, setData] = useState<Response | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [collapsed, setCollapsed] = useState(defaultCollapsed);

  const fetchOverrides = useCallback(async () => {
    if (!leagueId) return;
    setLoading(true);
    try {
      const { data } = await api.get(
        `/leagues/${leagueId}/commissioner-overrides?limit=${limit}`,
      );
      setData(data);
      setError(null);
    } catch (e: any) {
      const detail = e?.response?.data?.detail || e?.message || "Failed to load overrides";
      setError(detail);
    } finally {
      setLoading(false);
    }
  }, [leagueId, limit]);

  useEffect(() => {
    fetchOverrides();
  }, [fetchOverrides]);

  useEffect(() => {
    if (!leagueId || !pollMs) return;
    const tick = () => {
      if (document.visibilityState === "visible") fetchOverrides();
    };
    const id = window.setInterval(tick, pollMs);
    return () => window.clearInterval(id);
  }, [leagueId, pollMs, fetchOverrides]);

  if (!leagueId) return null;

  // 403 for non-members — hide entirely so the panel doesn't leak into
  // outsider UIs.
  if (error && !data && error.toLowerCase().includes("league members")) {
    return null;
  }

  const count = data?.count ?? 0;

  return (
    <Card className="bg-card border-border" data-testid="recent-overrides-panel">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between gap-3">
          <button
            className="flex items-center gap-2 text-left flex-1 min-w-0"
            onClick={() => setCollapsed((c) => !c)}
            data-testid="recent-overrides-toggle"
          >
            {collapsed ? (
              <ChevronRight className="h-4 w-4 text-muted-foreground" />
            ) : (
              <ChevronDown className="h-4 w-4 text-muted-foreground" />
            )}
            <Gavel className="h-4 w-4 text-fuchsia-400" />
            <CardTitle className="text-sm">Recent commissioner overrides</CardTitle>
            {count > 0 && (
              <Badge
                variant="outline"
                className="text-[10px] bg-fuchsia-500/10 text-fuchsia-300 border-fuchsia-500/30"
              >
                {count}
              </Badge>
            )}
          </button>
          <Button
            variant="ghost"
            size="sm"
            onClick={(e) => {
              e.stopPropagation();
              fetchOverrides();
            }}
            disabled={loading}
            data-testid="recent-overrides-refresh-btn"
            className="h-7 w-7 p-0"
          >
            <RefreshCw className={`h-3 w-3 ${loading ? "animate-spin" : ""}`} />
          </Button>
        </div>
        {!collapsed && (
          <CardDescription className="text-[11px] pl-6">
            Every pick undo + offline-manager ping fired by league admins. Visible to all league members for transparency.
          </CardDescription>
        )}
      </CardHeader>
      {!collapsed && (
        <CardContent className="pt-0">
          {error && !data && (
            <div className="flex items-center gap-2 text-xs text-rose-400">
              <ShieldAlert className="h-3.5 w-3.5" />
              {error}
            </div>
          )}
          {data && data.events.length === 0 && (
            <div className="text-xs text-muted-foreground italic">
              No commissioner overrides yet — a clean audit trail.
            </div>
          )}
          {data && data.events.length > 0 && (
            <div className="space-y-0.5 max-h-[320px] overflow-y-auto pr-1">
              {data.events.map((ev, i) =>
                ev.type === "pick_undo" ? (
                  <UndoRow key={`undo-${i}-${ev.at}`} ev={ev as any} />
                ) : (
                  <PingRow key={`ping-${i}-${ev.at}`} ev={ev as any} />
                ),
              )}
            </div>
          )}
        </CardContent>
      )}
    </Card>
  );
}
