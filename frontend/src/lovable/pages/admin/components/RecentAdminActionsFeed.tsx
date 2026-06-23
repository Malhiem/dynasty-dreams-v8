// @ts-nocheck
/* RecentAdminActionsFeed — extracted from AdminDashboard.tsx during Iter 224 refactor. */
import { useEffect, useState } from "react";
import api from "@/lib/api";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

/* ─── Iter 216 — Recent admin actions feed (Overview tab) ──────────── */
export function RecentAdminActionsFeed() {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const { data } = await api.get("/admin/platform/recent-admin-actions?limit=20");
        if (!cancelled) setRows(data.actions || []);
      } catch {
        // non-fatal
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  return (
    <Card className="bg-card border-border" data-testid="recent-admin-actions-feed">
      <CardHeader>
        <CardTitle className="text-base">Recent Admin Actions</CardTitle>
        <CardDescription>Latest {rows.length} actions across the platform — full audit visibility.</CardDescription>
      </CardHeader>
      <CardContent>
        {loading && <p className="text-xs text-muted-foreground">Loading…</p>}
        {!loading && rows.length === 0 && (
          <p className="text-xs text-muted-foreground italic">No admin actions recorded yet.</p>
        )}
        {!loading && rows.length > 0 && (
          <ul className="divide-y divide-border/60 max-h-[440px] overflow-y-auto">
            {rows.map((r: any) => (
              <li key={r.id} className="py-2 flex items-start gap-3 text-xs" data-testid={`recent-action-${r.action}`}>
                <span className="font-mono text-foreground/90 min-w-[160px]">{r.action}</span>
                <span className="flex-1">
                  <span className="text-muted-foreground">target:</span>{" "}
                  <span className="text-foreground/90 truncate">{r.target_email || r.target_user_id?.slice(-8)}</span>
                  {r.reason && <span className="text-muted-foreground italic"> — &ldquo;{r.reason}&rdquo;</span>}
                </span>
                <span className="text-muted-foreground whitespace-nowrap">by {r.admin_email}</span>
                <span className="text-muted-foreground whitespace-nowrap min-w-[110px] text-right">
                  {r.ts ? new Date(r.ts).toLocaleString() : "—"}
                </span>
                {r.mocked && <span className="text-amber-300 text-[10px]">MOCKED</span>}
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

