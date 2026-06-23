// @ts-nocheck
/* LineupAuditPanel — extracted from AdminDashboard.tsx during Iter 224 refactor. */
import { useEffect, useState } from "react";
import { toast } from "sonner";
import api from "@/lib/api";
import { Monitor } from "lucide-react";

/* ─── Iter 201d — Lineup Audit panel ───────────────────────────────── */
export function LineupAuditPanel() {
  const [data, setData] = useState({ entries: [], multi_account_flags: [] });
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    (async () => {
      try {
        const { data } = await api.get(`/admin/platform/lineup-audit?limit=100`);
        setData(data);
      } catch (e) {
        toast.error(e?.response?.data?.detail || "Failed to load lineup audit");
      } finally { setLoading(false); }
    })();
  }, []);
  return (
    <section data-testid="lineup-audit-section" className="space-y-3">
      <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-2">
        <Monitor className="h-4 w-4" />
        Lineup Audit Trail · IP / UA fingerprinting
      </h2>

      {data.multi_account_flags.length > 0 && (
        <div className="rounded-lg border border-rose-500/40 bg-rose-500/10 p-3 space-y-2"
          data-testid="multi-account-flags-block">
          <div className="text-sm font-bold text-rose-300">
            Multi-account warning · same IP setting lineups for multiple accounts
          </div>
          <ul className="space-y-1">
            {data.multi_account_flags.map((f) => (
              <li key={f.ip} className="text-xs flex items-center justify-between border-t border-rose-500/30 pt-1">
                <span className="font-mono text-rose-200">{f.ip}</span>
                <span>{f.user_count} accounts: {f.users.join(", ")}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="rounded-lg border border-border overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-secondary/50 text-xs uppercase tracking-wider text-muted-foreground">
            <tr>
              <th className="text-left px-3 py-2">When</th>
              <th className="text-left px-3 py-2">League</th>
              <th className="text-left px-3 py-2">Actor</th>
              <th className="text-left px-3 py-2">IP</th>
              <th className="text-left px-3 py-2">UA</th>
              <th className="text-left px-3 py-2">Summary</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={6} className="text-center text-muted-foreground py-6">Loading…</td></tr>
            ) : data.entries.length === 0 ? (
              <tr><td colSpan={6} className="text-center text-muted-foreground py-6">No lineup events yet. Once owners save lineups, they’ll appear here.</td></tr>
            ) : data.entries.map((e) => (
              <tr key={e.id} className="border-t border-border" data-testid={`lineup-row-${e.id}`}>
                <td className="px-3 py-2 text-xs text-muted-foreground whitespace-nowrap">{(e.created_at || "").slice(0, 19).replace("T", " ")}</td>
                <td className="px-3 py-2 text-xs">{e.league_name || e.league_id?.slice(0, 8)}</td>
                <td className="px-3 py-2 text-xs">{e.user?.email || e.user_id?.slice(0, 8)}</td>
                <td className="px-3 py-2 text-xs font-mono">{e.ip || "—"}</td>
                <td className="px-3 py-2 text-xs text-muted-foreground max-w-[180px] truncate" title={e.user_agent}>{e.user_agent || "—"}</td>
                <td className="px-3 py-2 text-xs">{e.summary || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

