// @ts-nocheck
/* ModerationQueuePanel — extracted from AdminDashboard.tsx during Iter 224 refactor. */
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

/* ─── Iter 206 — Moderation Queue Panel ──────────────────────────────── */
export function ModerationQueuePanel() {
  const [items, setItems] = useState<any[]>([]);
  const [pendingCount, setPendingCount] = useState(0);
  const [statusFilter, setStatusFilter] = useState<"pending" | "approved" | "deleted" | "all">("pending");
  const [sourceFilter, setSourceFilter] = useState<string>("all");
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ status: statusFilter });
      if (sourceFilter !== "all") params.set("source", sourceFilter);
      const { data } = await api.get(`/admin/platform/moderation-queue?${params.toString()}`);
      setItems(data?.items || []);
      setPendingCount(data?.pending_count || 0);
    } catch {
      toast.error("Could not load moderation queue");
    } finally {
      setLoading(false);
    }
  }, [statusFilter, sourceFilter]);

  useEffect(() => { load(); }, [load]);

  const resolve = async (id: string, action: "approved" | "deleted") => {
    try {
      await api.post(`/admin/platform/moderation/${id}/resolve`, { action, note: "" });
      toast.success(`Item ${action}`);
      await load();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Failed");
    }
  };

  return (
    <section className="space-y-3" data-testid="moderation-queue-section">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold flex items-center gap-2">
            Moderation Queue
            {pendingCount > 0 && (
              <span className="text-xs px-2 py-0.5 rounded-full bg-rose-500/20 text-rose-300" data-testid="moderation-pending-badge">
                {pendingCount} pending
              </span>
            )}
          </h2>
          <p className="text-xs text-muted-foreground">
            Auto-flagged chat messages, usernames, and team names.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Select value={sourceFilter} onValueChange={setSourceFilter}>
            <SelectTrigger className="w-36" data-testid="moderation-source-filter">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All sources</SelectItem>
              <SelectItem value="chat">Chat</SelectItem>
              <SelectItem value="trade_block">Trade block</SelectItem>
              <SelectItem value="username">Usernames</SelectItem>
              <SelectItem value="team_name">Team names</SelectItem>
              <SelectItem value="avatar">Avatars</SelectItem>
            </SelectContent>
          </Select>
          <Select value={statusFilter} onValueChange={(v: any) => setStatusFilter(v)}>
            <SelectTrigger className="w-36" data-testid="moderation-status-filter">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="pending">Pending</SelectItem>
              <SelectItem value="approved">Approved</SelectItem>
              <SelectItem value="deleted">Deleted</SelectItem>
              <SelectItem value="all">All</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      {loading && <div className="text-sm text-muted-foreground py-4 text-center">Loading…</div>}

      {!loading && items.length === 0 && (
        <div className="text-sm text-muted-foreground py-6 text-center border border-dashed border-border rounded-lg" data-testid="moderation-empty">
          No {statusFilter === "all" ? "" : statusFilter} items.
        </div>
      )}

      {!loading && items.length > 0 && (
        <div className="space-y-2" data-testid="moderation-list">
          {items.map((it: any) => (
            <div key={it.item_id} className="rounded-lg border border-border bg-muted/20 p-3" data-testid={`mod-item-${it.item_id}`}>
              <div className="flex items-center justify-between mb-1.5 gap-3">
                <div className="text-xs text-muted-foreground">
                  <span className="uppercase tracking-wider font-semibold text-foreground/80">{it.source}</span>
                  {" · "}
                  <span className="text-rose-300">{it.matched_word ? `matched "${it.matched_word}"` : "manual"}</span>
                  {" · "}
                  <span className="capitalize">severity: {it.severity}</span>
                </div>
                <span className={`text-[10px] px-2 py-0.5 rounded-full border ${
                  it.status === "pending"
                    ? "border-amber-500/40 text-amber-300"
                    : it.status === "approved"
                      ? "border-emerald-500/40 text-emerald-300"
                      : "border-rose-500/40 text-rose-300"
                }`}>
                  {it.status}
                </span>
              </div>
              <div className="text-sm bg-secondary/30 rounded p-2 mb-2 break-words" data-testid={`mod-content-${it.item_id}`}>
                {it.content}
              </div>
              <div className="text-[10px] text-muted-foreground mb-2">
                by {it.author_email || it.author_id || "anonymous"} · {new Date(it.created_at).toLocaleString()}
              </div>
              {it.status === "pending" && (
                <div className="flex items-center gap-2">
                  <Button size="sm" variant="outline" onClick={() => resolve(it.item_id, "approved")} data-testid={`mod-approve-${it.item_id}`}>
                    Approve
                  </Button>
                  <Button size="sm" variant="outline" className="border-rose-500/50 text-rose-300 hover:bg-rose-500/10" onClick={() => resolve(it.item_id, "deleted")} data-testid={`mod-delete-${it.item_id}`}>
                    Delete
                  </Button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </section>
  );
}


