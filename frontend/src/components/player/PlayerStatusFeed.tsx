/**
 * Iter 232N.5 — PlayerStatusFeed.
 *
 * Shared component that fetches `/api/player-status/feed` for a given
 * scope (user | league | team) and renders the grouped-by-player
 * results with a stacked mini-list per player (option (b) from the
 * spec — best balance of scan-ability + info density).
 *
 * Three consumer surfaces:
 *   1. Notifications inbox — new "Player Status" tab (scope="user")
 *   2. League Home recent activity card (scope="team")
 *   3. User Dashboard cross-league feed (scope="user")
 *
 * Empty-state renders inline; the parent doesn't need to guard.
 */
import { useEffect, useState } from "react";
import { Cross, ArrowDownToLine, FileWarning, Sparkles, Clock } from "lucide-react";
import api from "@/lib/api";
import { Link } from "react-router-dom";
import { PlayerTrendBadge } from "@/components/player/PlayerTrendBadge";

interface Update {
  notification_id: string;
  flag: "injured" | "in_minors" | "unsigned" | string;
  value: boolean;
  title: string;
  message: string;
  ts: string;
  league_id: string | null;
  read: boolean;
}

interface PlayerBucket {
  player_id: string;
  player_name: string;
  updates: Update[];
  // Iter 232N.7 — Cross-league mover trend chip surfaced next to
  // the player's name on the feed card. Backend attaches when the
  // player has an active trend snapshot.
  trends?: {
    trend?: "hot" | "dropped" | "traded" | null;
    adds_7d?: number;
    drops_7d?: number;
    trades_7d?: number;
    distinct_leagues_7d?: number;
  } | null;
}

interface Props {
  scope: "user" | "league" | "team";
  leagueId?: string;
  teamId?: string;
  days?: number;
  limit?: number;
  emptyMessage?: string;
  /** Iter 232N.5 — When the parent already renders a heading, hides
   *  the internal one so the feed nests cleanly inside a Card. */
  hideHeading?: boolean;
  /** Optional heading override. Defaults to "Player status updates". */
  heading?: string;
}

const FLAG_META: Record<string, { icon: any; tone: string }> = {
  injured: { icon: Cross, tone: "text-rose-400" },
  in_minors: { icon: ArrowDownToLine, tone: "text-amber-300" },
  unsigned: { icon: FileWarning, tone: "text-purple-300" },
  _fallback: { icon: Sparkles, tone: "text-emerald-300" },
};

function _relTime(iso: string) {
  try {
    const then = new Date(iso).getTime();
    const now = Date.now();
    const s = Math.max(1, Math.floor((now - then) / 1000));
    if (s < 60) return `${s}s ago`;
    const m = Math.floor(s / 60);
    if (m < 60) return `${m}m ago`;
    const h = Math.floor(m / 60);
    if (h < 24) return `${h}h ago`;
    const d = Math.floor(h / 24);
    return `${d}d ago`;
  } catch {
    return "";
  }
}

export function PlayerStatusFeed({
  scope,
  leagueId,
  teamId,
  days = 7,
  limit = 200,
  emptyMessage = "No player status changes yet.",
  hideHeading = false,
  heading = "Player status updates",
}: Props) {
  const [loading, setLoading] = useState(true);
  const [buckets, setBuckets] = useState<PlayerBucket[]>([]);
  const [total, setTotal] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    const params = new URLSearchParams();
    params.set("scope", scope);
    params.set("days", String(days));
    params.set("limit", String(limit));
    if (scope === "league" && leagueId) params.set("league_id", leagueId);
    if (scope === "team" && teamId) params.set("team_id", teamId);
    api
      .get(`/player-status/feed?${params.toString()}`)
      .then((res) => {
        if (cancelled) return;
        setBuckets(res.data?.players || []);
        setTotal(res.data?.total_updates || 0);
      })
      .catch(() => {
        if (cancelled) return;
        setBuckets([]);
        setTotal(0);
      })
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [scope, leagueId, teamId, days, limit]);

  return (
    <div className="w-full" data-testid={`player-status-feed-${scope}`}>
      {!hideHeading && (
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold text-foreground">{heading}</h3>
          <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
            Last {days}d · {total} {total === 1 ? "update" : "updates"}
          </span>
        </div>
      )}
      {loading ? (
        <p className="text-xs text-muted-foreground py-4" data-testid="player-status-feed-loading">
          Loading…
        </p>
      ) : buckets.length === 0 ? (
        <p className="text-xs text-muted-foreground py-4" data-testid="player-status-feed-empty">
          {emptyMessage}
        </p>
      ) : (
        <ul className="space-y-3" data-testid="player-status-feed-list">
          {buckets.map((b) => (
            <li
              key={b.player_id}
              className="rounded-md border border-border/40 bg-secondary/20 p-2.5"
              data-testid={`player-status-feed-player-${b.player_id}`}
            >
              <div className="flex items-baseline justify-between gap-2 mb-1.5">
                <Link
                  to={`/players/${b.player_id}`}
                  className="text-sm font-semibold text-foreground hover:text-primary transition-colors truncate"
                >
                  {b.player_name}
                </Link>
                <span className="text-[10px] text-muted-foreground shrink-0">
                  {b.updates.length} {b.updates.length === 1 ? "update" : "updates"}
                </span>
              </div>
              <ul className="space-y-1">
                {b.updates.map((u) => {
                  const meta = FLAG_META[u.flag] || FLAG_META._fallback;
                  const Icon = meta.icon;
                  return (
                    <li
                      key={u.notification_id}
                      className="flex items-start gap-2 text-xs"
                      data-testid={`player-status-feed-update-${u.notification_id}`}
                    >
                      <Icon className={`h-3 w-3 mt-0.5 shrink-0 ${meta.tone}`} />
                      <div className="min-w-0 flex-1">
                        <p className="text-foreground/90 leading-tight">{u.title}</p>
                        {u.message && (
                          <p className="text-muted-foreground text-[11px] leading-tight truncate">
                            {u.message}
                          </p>
                        )}
                      </div>
                      <span className="text-[10px] text-muted-foreground shrink-0 flex items-center gap-1">
                        <Clock className="h-2.5 w-2.5" />
                        {_relTime(u.ts)}
                      </span>
                    </li>
                  );
                })}
              </ul>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default PlayerStatusFeed;
