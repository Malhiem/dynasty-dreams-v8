// @ts-nocheck
/* UserReportsPanel — extracted from AdminDashboard.tsx during Iter 224 refactor. */
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import api from "@/lib/api";
import { Flag, User } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import TrustScoreBadge from "@/components/TrustScoreBadge";
import { ModNotesPanel } from "./ModNotesPanel";



/* ─── Iter 205 — User Reports / Flag Moderation Queue ────────────────────
 * Lists submitted user reports with filters and inline resolve actions.
 * Admin can mark each report as resolved or dismissed, optionally
 * applying a moderation action (warning / timeout / ban / none).
 */
export function UserReportsPanel() {
  const [reports, setReports] = useState<any[]>([]);
  const [openCount, setOpenCount] = useState(0);
  const [loading, setLoading] = useState(false);
  const [statusFilter, setStatusFilter] = useState<"open" | "resolved" | "dismissed" | "all">("open");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get(`/admin/platform/reports?status=${statusFilter}`);
      setReports(data?.reports || []);
      setOpenCount(data?.open_count || 0);
    } catch (e: any) {
      toast.error("Could not load reports");
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => { load(); }, [load]);

  const resolve = async (report_id: string, action: "resolved" | "dismissed", applied: string) => {
    try {
      await api.post(`/admin/platform/reports/${report_id}/resolve`, {
        action,
        applied_action: applied,
        note: "",
      });
      toast.success(`Report ${action}`);
      await load();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Failed to resolve report");
    }
  };

  return (
    <section className="space-y-3" data-testid="reports-section">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold flex items-center gap-2">
            User Reports
            {openCount > 0 && (
              <span className="text-xs px-2 py-0.5 rounded-full bg-rose-500/20 text-rose-300" data-testid="reports-open-badge">
                {openCount} open
              </span>
            )}
          </h2>
          <p className="text-xs text-muted-foreground">
            Reports submitted by users about other users (chat misconduct,
            offensive names, suspicious trades, etc.).
          </p>
        </div>
        <Select value={statusFilter} onValueChange={(v: any) => setStatusFilter(v)}>
          <SelectTrigger className="w-40" data-testid="reports-status-filter">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="open">Open</SelectItem>
            <SelectItem value="resolved">Resolved</SelectItem>
            <SelectItem value="dismissed">Dismissed</SelectItem>
            <SelectItem value="all">All</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {loading && (
        <div className="text-sm text-muted-foreground py-6 text-center" data-testid="reports-loading">
          Loading reports…
        </div>
      )}

      {!loading && reports.length === 0 && (
        <div className="text-sm text-muted-foreground py-6 text-center border border-dashed border-border rounded-lg" data-testid="reports-empty">
          No {statusFilter === "all" ? "" : statusFilter} reports.
        </div>
      )}

      {!loading && reports.length > 0 && (
        <div className="space-y-3" data-testid="reports-list">
          {reports.map((r: any) => (
            <div key={r.report_id} className="rounded-lg border border-border bg-muted/20 p-4" data-testid={`report-${r.report_id}`}>
              <div className="flex items-start justify-between mb-2 gap-3">
                <div className="text-sm">
                  <div className="font-medium flex items-center gap-2 flex-wrap">
                    <span>{r.reporter_email || r.reporter_id} reported {r.target_user_email || r.target_user_id}</span>
                    {r.target_user_id && <TrustScoreBadge userId={r.target_user_id} />}
                  </div>
                  <div className="text-xs text-muted-foreground mt-0.5">
                    {new Date(r.created_at).toLocaleString()} · category:{" "}
                    <span className="capitalize">{r.category?.replace(/_/g, " ")}</span>
                    {r.league_id && <> · league {r.league_id}</>}
                  </div>
                </div>
                <span
                  className={`text-[10px] px-2 py-0.5 rounded-full border ${
                    r.status === "open"
                      ? "border-amber-500/40 text-amber-300"
                      : r.status === "resolved"
                        ? "border-emerald-500/40 text-emerald-300"
                        : "border-slate-500/40 text-slate-300"
                  }`}
                >
                  {r.status}
                </span>
              </div>
              {r.reason && (
                <div className="text-sm bg-secondary/30 rounded p-2 mb-2" data-testid={`report-reason-${r.report_id}`}>
                  {r.reason}
                </div>
              )}
              {r.context_url && (
                <div className="text-xs text-muted-foreground mb-2">
                  Context: <code className="bg-secondary/40 px-1.5 py-0.5 rounded">{r.context_url}</code>
                </div>
              )}
              {r.status === "open" && (
                <div className="flex items-center gap-2 mt-2">
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => resolve(r.report_id, "resolved", "warning")}
                    data-testid={`report-warn-${r.report_id}`}
                  >
                    Resolve · Warn
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    className="border-rose-500/50 text-rose-300 hover:bg-rose-500/10"
                    onClick={() => resolve(r.report_id, "resolved", "ban")}
                    data-testid={`report-ban-${r.report_id}`}
                  >
                    Resolve · Ban
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => resolve(r.report_id, "dismissed", "none")}
                    data-testid={`report-dismiss-${r.report_id}`}
                  >
                    Dismiss
                  </Button>
                </div>
              )}
              {r.status !== "open" && r.resolution_note && (
                <div className="text-xs text-muted-foreground mt-1">
                  <strong>Resolution:</strong> {r.resolution_action} — {r.resolution_note}
                </div>
              )}
              {/* Iter 209 — Mod notes thread per target user */}
              {r.target_user_id && (
                <ModNotesPanel
                  userId={r.target_user_id}
                  userEmail={r.target_user_email}
                />
              )}
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

