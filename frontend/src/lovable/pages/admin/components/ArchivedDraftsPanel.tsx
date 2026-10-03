// @ts-nocheck
/**
 * Iter 228e — Admin Archived Drafts Panel.
 *
 * Browse every soft-deleted draft across the platform with the
 * remaining-days-until-purge countdown. Each row has Restore (revives
 * the draft) and Purge Now (permanent delete, bypasses the 15-day TTL).
 *
 * Iter 228l — Per-row "History" button opens a Sheet drawer that
 * fetches the merged audit timeline from GET /admin/drafts/{id}/audit
 * (archive → restore → archive → purge events) so compliance can
 * inspect the full lifecycle without leaving the page.
 *
 * Endpoints used:
 *   GET  /api/admin/drafts/archived
 *   POST /api/admin/drafts/{id}/restore
 *   POST /api/admin/drafts/{id}/purge
 *   GET  /api/admin/drafts/{id}/audit
 */
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import {
  Archive, RefreshCcw, RotateCcw, Trash2, History,
  ArchiveRestore, Trash, ShieldAlert, Loader2,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle,
} from "@/components/ui/sheet";
import api from "@/lib/api";

const ACTION_META = {
  draft_archive: {
    label: "Archived",
    icon: Archive,
    color: "text-amber-300 border-amber-500/40 bg-amber-500/10",
  },
  draft_restore: {
    label: "Restored",
    icon: ArchiveRestore,
    color: "text-emerald-300 border-emerald-500/40 bg-emerald-500/10",
  },
  draft_purge: {
    label: "Purged (admin)",
    icon: Trash,
    color: "text-rose-300 border-rose-500/40 bg-rose-500/10",
  },
  draft_auto_purge: {
    label: "Auto-purged (15-day TTL)",
    icon: ShieldAlert,
    color: "text-rose-300 border-rose-500/40 bg-rose-500/10",
  },
};

export default function ArchivedDraftsPanel() {
  const [drafts, setDrafts] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);

  // Iter 228l — History drawer state
  const [historyDraft, setHistoryDraft] = useState<any>(null);
  const [historyEntries, setHistoryEntries] = useState<any[] | null>(null);
  const [historyLoading, setHistoryLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/admin/drafts/archived");
      setDrafts(Array.isArray(data?.drafts) ? data.drafts : []);
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Failed to load archived drafts");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const handleRestore = async (id: string) => {
    setBusyId(id);
    try {
      await api.post(`/admin/drafts/${id}/restore`);
      toast.success("Draft restored to scheduled");
      await load();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Restore failed");
    } finally {
      setBusyId(null);
    }
  };

  const handlePurge = async (id: string, name: string) => {
    if (!window.confirm(
      `Permanently delete "${name}"? This bypasses the 15-day recovery window and CANNOT be undone.`,
    )) return;
    setBusyId(id);
    try {
      await api.post(`/admin/drafts/${id}/purge`);
      toast.success("Draft purged permanently");
      await load();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Purge failed");
    } finally {
      setBusyId(null);
    }
  };

  const openHistory = async (draft: any) => {
    setHistoryDraft(draft);
    setHistoryEntries(null);
    setHistoryLoading(true);
    try {
      const { data } = await api.get(`/admin/drafts/${draft.id}/audit`);
      setHistoryEntries(Array.isArray(data?.entries) ? data.entries : []);
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Failed to load history");
      setHistoryEntries([]);
    } finally {
      setHistoryLoading(false);
    }
  };

  const closeHistory = () => {
    setHistoryDraft(null);
    setHistoryEntries(null);
  };

  const fmt = (iso: string | null) => {
    if (!iso) return "—";
    try {
      return new Date(iso).toLocaleString(undefined, {
        month: "short", day: "numeric", year: "numeric",
        hour: "numeric", minute: "2-digit",
      });
    } catch { return iso; }
  };

  return (
    <Card className="hover-glow" data-testid="archived-drafts-panel">
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle className="flex items-center gap-2">
          <Archive className="h-4 w-4" />
          Archived Drafts
          <Badge variant="secondary" className="ml-2" data-testid="archived-drafts-count">
            {drafts.length}
          </Badge>
        </CardTitle>
        <Button
          size="sm" variant="outline" onClick={load} disabled={loading}
          data-testid="archived-drafts-refresh-btn"
        >
          <RefreshCcw className={`h-3.5 w-3.5 mr-1.5 ${loading ? "animate-spin" : ""}`} />
          Refresh
        </Button>
      </CardHeader>
      <CardContent>
        {drafts.length === 0 ? (
          <p className="text-sm text-muted-foreground italic" data-testid="archived-drafts-empty">
            No archived drafts. Soft-deleted drafts appear here for 15 days before they auto-purge.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-xs font-medium text-muted-foreground border-b border-border">
                <tr>
                  <th className="text-left py-2 pl-2">Draft</th>
                  <th className="text-left py-2">League</th>
                  <th className="text-left py-2">Archived</th>
                  <th className="text-center py-2">Days Left</th>
                  <th className="text-right py-2 pr-2">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/40">
                {drafts.map((d) => {
                  const days = Number(d.days_until_purge ?? 0);
                  const danger = days <= 3;
                  return (
                    <tr key={d.id} className="hover:bg-muted/20" data-testid={`archived-draft-row-${d.id}`}>
                      <td className="py-2 pl-2 font-medium">{d.name}</td>
                      <td className="py-2 text-muted-foreground text-xs">{d.league_name || d.league_id}</td>
                      <td className="py-2 text-xs">{fmt(d.archived_at)}</td>
                      <td className="py-2 text-center">
                        <Badge variant={danger ? "destructive" : "secondary"} data-testid={`archived-draft-days-${d.id}`}>
                          {days}d
                        </Badge>
                      </td>
                      <td className="py-2 pr-2 text-right space-x-1">
                        <Button
                          size="sm" variant="ghost"
                          onClick={() => openHistory(d)}
                          data-testid={`archived-draft-history-${d.id}`}
                          title="View audit history"
                        >
                          <History className="h-3.5 w-3.5 mr-1" />
                          History
                        </Button>
                        <Button
                          size="sm" variant="outline"
                          onClick={() => handleRestore(d.id)}
                          disabled={busyId === d.id}
                          data-testid={`archived-draft-restore-${d.id}`}
                        >
                          <RotateCcw className="h-3.5 w-3.5 mr-1" />
                          Restore
                        </Button>
                        <Button
                          size="sm" variant="destructive"
                          onClick={() => handlePurge(d.id, d.name)}
                          disabled={busyId === d.id}
                          data-testid={`archived-draft-purge-${d.id}`}
                        >
                          <Trash2 className="h-3.5 w-3.5 mr-1" />
                          Purge
                        </Button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>

      {/* Iter 228l — Audit-log timeline drawer */}
      <Sheet open={!!historyDraft} onOpenChange={(o) => { if (!o) closeHistory(); }}>
        <SheetContent
          side="right"
          className="w-full sm:max-w-lg overflow-y-auto"
          data-testid="archived-drafts-history-drawer"
        >
          <SheetHeader>
            <SheetTitle className="flex items-center gap-2">
              <History className="h-4 w-4" />
              Audit History
            </SheetTitle>
            <SheetDescription>
              <span className="block font-medium text-foreground">
                {historyDraft?.name || "—"}
              </span>
              <span className="block text-xs">
                {historyDraft?.league_name || historyDraft?.league_id}
              </span>
            </SheetDescription>
          </SheetHeader>

          <div className="mt-6">
            {historyLoading ? (
              <div className="flex items-center justify-center py-12 text-muted-foreground text-sm">
                <Loader2 className="h-4 w-4 animate-spin mr-2" />
                Loading timeline…
              </div>
            ) : !historyEntries || historyEntries.length === 0 ? (
              <p
                className="text-sm text-muted-foreground italic py-8 text-center"
                data-testid="archived-drafts-history-empty"
              >
                No audit entries yet — events appear here as the draft is archived, restored, or purged.
              </p>
            ) : (
              <ol
                className="relative border-l border-border/60 pl-4 space-y-4"
                data-testid="archived-drafts-history-list"
              >
                {historyEntries.map((entry) => {
                  const meta = ACTION_META[entry.action] || {
                    label: entry.action,
                    icon: History,
                    color: "text-muted-foreground border-border bg-muted/10",
                  };
                  const Icon = meta.icon;
                  const isSystem = entry.admin_id === "__system__";
                  return (
                    <li
                      key={entry.id}
                      className="relative"
                      data-testid={`archived-drafts-history-entry-${entry.id}`}
                    >
                      <span
                        className={`absolute -left-[26px] top-0 inline-flex h-5 w-5 items-center justify-center rounded-full border ${meta.color}`}
                      >
                        <Icon className="h-3 w-3" />
                      </span>
                      <div className={`rounded-md border p-3 ${meta.color}`}>
                        <div className="flex items-center justify-between gap-2">
                          <span className="text-xs font-semibold uppercase tracking-wider">
                            {meta.label}
                          </span>
                          <span className="text-[11px] text-muted-foreground tabular-nums">
                            {fmt(entry.ts)}
                          </span>
                        </div>
                        <p className="text-xs mt-1 text-foreground/80">
                          {isSystem
                            ? "Background sweeper · 15-day TTL"
                            : entry.admin_email || entry.admin_id || "—"}
                          {entry.admin_tier && !isSystem && (
                            <span className="ml-1 text-muted-foreground">
                              · {entry.admin_tier}
                            </span>
                          )}
                        </p>
                        {entry.reason && (
                          <p className="text-[11px] text-muted-foreground mt-1 italic">
                            {entry.reason}
                          </p>
                        )}
                      </div>
                    </li>
                  );
                })}
              </ol>
            )}
          </div>
        </SheetContent>
      </Sheet>
    </Card>
  );
}
