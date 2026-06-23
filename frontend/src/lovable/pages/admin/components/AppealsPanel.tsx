// @ts-nocheck
/* AppealsPanel — extracted from AdminDashboard.tsx during Iter 224 refactor. */
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

/* ─── Iter 206 — Appeals Panel ───────────────────────────────────────── */
export function AppealsPanel() {
  const [appeals, setAppeals] = useState<any[]>([]);
  const [statusFilter, setStatusFilter] = useState<"open" | "approved" | "denied" | "all">("open");
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get(`/admin/platform/appeals?status=${statusFilter}`);
      setAppeals(data?.appeals || []);
    } catch { /* noop */ }
    finally { setLoading(false); }
  }, [statusFilter]);

  useEffect(() => { load(); }, [load]);

  const resolve = async (id: string, action: "approved" | "denied") => {
    try {
      await api.post(`/admin/platform/appeals/${id}/resolve`, { action, note: "" });
      toast.success(action === "approved" ? "Appeal approved · user reinstated" : "Appeal denied");
      await load();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Failed");
    }
  };

  return (
    <section className="space-y-3" data-testid="appeals-section">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">Ban Appeals</h2>
          <p className="text-xs text-muted-foreground">
            Banned/suspended users requesting reinstatement.
          </p>
        </div>
        <Select value={statusFilter} onValueChange={(v: any) => setStatusFilter(v)}>
          <SelectTrigger className="w-32" data-testid="appeals-status-filter"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="open">Open</SelectItem>
            <SelectItem value="approved">Approved</SelectItem>
            <SelectItem value="denied">Denied</SelectItem>
            <SelectItem value="all">All</SelectItem>
          </SelectContent>
        </Select>
      </div>
      {loading && <div className="text-sm text-muted-foreground py-4 text-center">Loading…</div>}
      {!loading && appeals.length === 0 && (
        <div className="text-sm text-muted-foreground py-6 text-center border border-dashed border-border rounded-lg" data-testid="appeals-empty">
          No {statusFilter === "all" ? "" : statusFilter} appeals.
        </div>
      )}
      {!loading && appeals.length > 0 && (
        <div className="space-y-3" data-testid="appeals-list">
          {appeals.map((a: any) => (
            <div key={a.appeal_id} className="rounded-lg border border-border bg-muted/20 p-3" data-testid={`appeal-${a.appeal_id}`}>
              <div className="flex items-center justify-between mb-1">
                <div className="text-sm font-medium">{a.user_email}</div>
                <span className={`text-[10px] px-2 py-0.5 rounded-full border ${
                  a.status === "open" ? "border-amber-500/40 text-amber-300" :
                  a.status === "approved" ? "border-emerald-500/40 text-emerald-300" :
                  "border-rose-500/40 text-rose-300"
                }`}>{a.status}</span>
              </div>
              <div className="text-[10px] text-muted-foreground mb-2">
                Original ban: <span className="capitalize">{a.ban_reason_code}</span> — {a.ban_reason}
              </div>
              <div className="text-sm bg-secondary/30 rounded p-2 mb-2 break-words">{a.message}</div>
              {a.status === "open" && (
                <div className="flex items-center gap-2">
                  <Button size="sm" variant="outline" className="border-emerald-500/50 text-emerald-300 hover:bg-emerald-500/10" onClick={() => resolve(a.appeal_id, "approved")} data-testid={`appeal-approve-${a.appeal_id}`}>
                    Approve · Reinstate
                  </Button>
                  <Button size="sm" variant="outline" className="border-rose-500/50 text-rose-300 hover:bg-rose-500/10" onClick={() => resolve(a.appeal_id, "denied")} data-testid={`appeal-deny-${a.appeal_id}`}>
                    Deny
                  </Button>
                </div>
              )}
              {a.status !== "open" && a.resolution_note && (
                <div className="text-xs text-muted-foreground mt-1">{a.resolution_note}</div>
              )}
            </div>
          ))}
        </div>
      )}
    </section>
  );
}



