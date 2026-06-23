// @ts-nocheck
/* CollusionPanel — extracted from AdminDashboard.tsx during Iter 224 refactor. */
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import api from "@/lib/api";
import { User, UserX } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

/* ─── Iter 201c — Collusion panel ──────────────────────────────────── */
export function CollusionPanel() {
  const [data, setData] = useState({ pairs: [] });
  const [locks, setLocks] = useState([]);
  const [minTrades, setMinTrades] = useState(3);
  const [minNetFavor, setMinNetFavor] = useState(30);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [pairs, locksRes] = await Promise.all([
        api.get(`/admin/platform/collusion-flags?min_trades=${minTrades}&min_net_favor_pct=${minNetFavor}`),
        api.get(`/admin/platform/pairs/locks`),
      ]);
      setData(pairs.data);
      setLocks(locksRes.data?.locks || []);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed to load collusion flags");
    } finally { setLoading(false); }
  }, [minTrades, minNetFavor]);
  useEffect(() => { load(); }, [load]);

  return (
    <section data-testid="collusion-section" className="space-y-3">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-2">
          <UserX className="h-4 w-4 text-rose-400" />
          Collusion Detection
        </h2>
        <div className="flex items-center gap-2 text-xs">
          <span className="text-muted-foreground">Min trades</span>
          <Input
            type="number" min={2} max={20} value={minTrades}
            onChange={(e) => setMinTrades(parseInt(e.target.value) || 3)}
            className="h-8 w-16 text-xs" data-testid="collusion-min-trades"
          />
          <span className="text-muted-foreground">Min net favor %</span>
          <Input
            type="number" min={10} max={100} value={minNetFavor}
            onChange={(e) => setMinNetFavor(parseInt(e.target.value) || 30)}
            className="h-8 w-16 text-xs" data-testid="collusion-min-favor"
          />
        </div>
      </div>
      <div className="rounded-lg border border-border overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-secondary/50 text-xs uppercase tracking-wider text-muted-foreground">
            <tr>
              <th className="text-left px-3 py-2">Pair</th>
              <th className="text-left px-3 py-2">Trades</th>
              <th className="text-left px-3 py-2">Net Favor</th>
              <th className="text-left px-3 py-2">Favored User</th>
              <th className="text-right px-3 py-2">Action</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={5} className="text-center text-muted-foreground py-6">Loading…</td></tr>
            ) : data.pairs.length === 0 ? (
              <tr><td colSpan={5} className="text-center text-muted-foreground py-6">No suspicious pairs flagged.</td></tr>
            ) : data.pairs.map((p, idx) => {
              const favEmail = (p.users || {})[p.favored_user_id]?.email || p.favored_user_id;
              return (
                <tr key={idx} className="border-t border-border" data-testid={`collusion-pair-${idx}`}>
                  <td className="px-3 py-2 text-xs">
                    {Object.values(p.users || {}).map((u) => u.email).join(" ↔ ")}
                  </td>
                  <td className="px-3 py-2 text-xs font-mono">{p.trade_count}</td>
                  <td className="px-3 py-2 text-xs">
                    <span className="font-mono text-rose-300">{p.net_favor > 0 ? "+" : ""}{p.net_favor}</span>
                  </td>
                  <td className="px-3 py-2 text-xs">{favEmail}</td>
                  <td className="px-3 py-2 text-right">
                    <Button
                      size="sm" variant="ghost" className="text-xs h-7"
                      onClick={async () => {
                        const reason = prompt("Lock reason (optional)?") || "";
                        try {
                          await api.post("/admin/platform/pairs/lock", {
                            user_ids: p.pair, reason,
                          });
                          toast.success("Pair locked");
                          load();
                        } catch (err) {
                          toast.error(err?.response?.data?.detail || "Failed to lock");
                        }
                      }}
                      data-testid={`collusion-lock-btn-${idx}`}
                    >
                      Lock pair
                    </Button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Active locks */}
      {locks.length > 0 && (
        <div className="rounded-lg border border-rose-500/40 bg-rose-500/5 p-3 space-y-2" data-testid="active-locks-block">
          <div className="text-xs font-bold uppercase tracking-wider text-rose-300">Active Trade Locks ({locks.length})</div>
          <ul className="space-y-1">
            {locks.map((l) => (
              <li key={l.lock_id} className="flex items-center justify-between text-xs border-t border-rose-500/20 pt-1.5" data-testid={`lock-row-${l.lock_id}`}>
                <span>
                  <span className="font-medium">{(l.emails || []).join(" ↔ ")}</span>
                  {l.reason && <span className="text-muted-foreground"> · &ldquo;{l.reason}&rdquo;</span>}
                  <span className="text-muted-foreground"> · locked {l.locked_at?.slice(0, 10)}</span>
                </span>
                <Button
                  size="sm" variant="ghost" className="text-xs h-7"
                  onClick={async () => {
                    try {
                      await api.delete(`/admin/platform/pairs/locks/${l.lock_id}`);
                      toast.success("Lock released");
                      load();
                    } catch (e) {
                      toast.error(e?.response?.data?.detail || "Failed to release");
                    }
                  }}
                  data-testid={`lock-release-btn-${l.lock_id}`}
                >
                  Release
                </Button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}

