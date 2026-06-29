/**
 * Iter 231ar — `<RecentCrashesPanel />`
 *
 * Triage view for crashes captured by `<GlobalErrorBoundary />` and the
 * global `window.onerror` / `unhandledrejection` listeners. Renders
 * inside the AdminDashboard so platform admins (Emergent operators) can
 * see what's burning in one click instead of curl-ing
 * `GET /api/client-errors`.
 *
 * Pairs naturally with the DB Hygiene + Audit Log + Recent Admin Actions
 * tiles already living on the dashboard.
 */
import { useEffect, useState } from "react";
import api from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { AlertTriangle, RefreshCw, ChevronDown, ChevronUp } from "lucide-react";

type CrashRow = {
  _id: string;
  message?: string;
  stack?: string;
  component_stack?: string;
  url?: string;
  user_agent?: string;
  user_id?: string;
  user_email?: string;
  app_version?: string;
  breadcrumbs?: Array<{ ts?: string; kind?: string; detail?: string }>;
  created_at?: string;
  ip?: string;
};

function relativeTime(iso?: string): string {
  if (!iso) return "—";
  try {
    const then = new Date(iso).getTime();
    const diff = (Date.now() - then) / 1000;
    if (diff < 60) return `${Math.max(0, Math.floor(diff))}s ago`;
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
    return `${Math.floor(diff / 86400)}d ago`;
  } catch {
    return iso;
  }
}

export default function RecentCrashesPanel() {
  const [rows, setRows] = useState<CrashRow[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const { data } = await api.get("/client-errors?limit=20");
      setRows(data?.errors || []);
      setTotal(Number(data?.total || 0));
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || "Failed to load crashes");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  return (
    <Card className="bg-card border-border" data-testid="admin-recent-crashes-panel">
      <CardHeader className="flex flex-row items-start justify-between gap-3 space-y-0 pb-3">
        <div>
          <CardTitle className="flex items-center gap-2 text-base">
            <AlertTriangle className="h-4 w-4 text-amber-400" />
            Recent Crashes
            <Badge variant="secondary" className="text-[10px]" data-testid="admin-recent-crashes-total">
              {total} total
            </Badge>
          </CardTitle>
          <p className="text-xs text-muted-foreground mt-1">
            Newest 20 client errors captured by the global ErrorBoundary +
            <code className="mx-1">window.onerror</code> / <code>unhandledrejection</code>.
          </p>
        </div>
        <Button
          size="sm"
          variant="outline"
          onClick={load}
          disabled={loading}
          data-testid="admin-recent-crashes-refresh"
        >
          <RefreshCw className={`h-3 w-3 mr-1.5 ${loading ? "animate-spin" : ""}`} />
          Refresh
        </Button>
      </CardHeader>
      <CardContent className="pt-0">
        {error && (
          <p className="text-sm text-red-400" data-testid="admin-recent-crashes-error">{error}</p>
        )}
        {!error && !loading && rows.length === 0 && (
          <p className="text-sm text-muted-foreground" data-testid="admin-recent-crashes-empty">
            🎉 No client crashes captured. The boundary is mounted but never triggered — give it some time.
          </p>
        )}
        {!error && rows.length > 0 && (
          <ScrollArea className="h-[480px] pr-2" data-testid="admin-recent-crashes-list">
            <ul className="space-y-2">
              {rows.map((r) => {
                const isOpen = !!expanded[r._id];
                return (
                  <li
                    key={r._id}
                    className="rounded-md border border-border bg-secondary/30 px-3 py-2 text-xs"
                    data-testid={`admin-recent-crashes-row-${r._id}`}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0 flex-1">
                        <p className="font-medium text-foreground truncate" title={r.message}>
                          {r.message || "(no message)"}
                        </p>
                        <p className="text-[10px] text-muted-foreground mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5">
                          <span>{relativeTime(r.created_at)}</span>
                          {r.url && <span className="truncate max-w-[260px]" title={r.url}>· {r.url}</span>}
                          {r.user_email && <span>· {r.user_email}</span>}
                          {!r.user_email && r.ip && <span>· {r.ip}</span>}
                          {r.app_version && r.app_version !== "dev" && (
                            <Badge variant="outline" className="text-[9px] h-4 px-1">{r.app_version}</Badge>
                          )}
                        </p>
                      </div>
                      <Button
                        size="sm"
                        variant="ghost"
                        className="h-6 px-2 shrink-0"
                        onClick={() => setExpanded((p) => ({ ...p, [r._id]: !isOpen }))}
                        data-testid={`admin-recent-crashes-row-${r._id}-toggle`}
                      >
                        {isOpen ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
                      </Button>
                    </div>
                    {isOpen && (
                      <div className="mt-2 space-y-2">
                        {r.stack && (
                          <pre className="text-[10px] text-muted-foreground bg-black/40 border border-white/5 rounded p-2 overflow-auto max-h-48">
                            {r.stack}
                          </pre>
                        )}
                        {r.component_stack && (
                          <details className="text-[10px]">
                            <summary className="cursor-pointer text-muted-foreground hover:text-foreground">
                              Component stack
                            </summary>
                            <pre className="mt-1 bg-black/40 border border-white/5 rounded p-2 overflow-auto max-h-32">
                              {r.component_stack}
                            </pre>
                          </details>
                        )}
                        {(r.breadcrumbs || []).length > 0 && (
                          <details className="text-[10px]">
                            <summary className="cursor-pointer text-muted-foreground hover:text-foreground">
                              {r.breadcrumbs!.length} breadcrumb{r.breadcrumbs!.length === 1 ? "" : "s"}
                            </summary>
                            <ul className="mt-1 space-y-0.5 pl-4">
                              {r.breadcrumbs!.map((bc, i) => (
                                <li key={i} className="text-muted-foreground">
                                  <span className="text-foreground">{bc.kind}</span>{" "}
                                  {bc.detail && <span className="opacity-80">— {bc.detail}</span>}
                                </li>
                              ))}
                            </ul>
                          </details>
                        )}
                        {r.user_agent && (
                          <p className="text-[10px] text-muted-foreground truncate" title={r.user_agent}>
                            UA: {r.user_agent}
                          </p>
                        )}
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>
          </ScrollArea>
        )}
      </CardContent>
    </Card>
  );
}
