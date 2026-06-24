// @ts-nocheck
/**
 * Iter 228e — Admin Archived Drafts Panel.
 *
 * Browse every soft-deleted draft across the platform with the
 * remaining-days-until-purge countdown. Each row has Restore (revives
 * the draft) and Purge Now (permanent delete, bypasses the 15-day TTL).
 *
 * Endpoints used:
 *   GET  /api/admin/drafts/archived
 *   POST /api/admin/drafts/{id}/restore
 *   POST /api/admin/drafts/{id}/purge
 */
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Archive, RefreshCcw, RotateCcw, Trash2 } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import api from "@/lib/api";

export default function ArchivedDraftsPanel() {
  const [drafts, setDrafts] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);

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
    </Card>
  );
}
