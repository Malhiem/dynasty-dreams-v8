// @ts-nocheck
import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

export function KeywordFiltersPanel() {
  const [filters, setFilters] = useState<any[]>([]);
  const [word, setWord] = useState("");
  const [severity, setSeverity] = useState("medium");
  const [loaded, setLoaded] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const requestId = useRef(0);
  const pending = useRef(false);

  const load = useCallback(async () => {
    const id = ++requestId.current;
    setLoading(true); setError("");
    try {
      const { data } = await api.get("/admin/platform/keyword-filters");
      if (id !== requestId.current) return;
      setFilters(data?.filters || []); setLoaded(true);
    } catch (e: any) {
      if (id !== requestId.current) return;
      if ([401, 403].includes(e?.response?.status)) { setFilters([]); setLoaded(false); }
      setError(typeof e?.response?.data?.detail === "string" ? e.response.data.detail : "Could not load keyword filters. Check your connection and retry.");
    } finally {
      if (id === requestId.current) setLoading(false);
    }
  }, []);

  useEffect(() => { load(); return () => { requestId.current++; }; }, [load]);

  const mutate = async (operation: () => Promise<any>, success: string) => {
    if (pending.current || !loaded || loading) return;
    pending.current = true; setBusy(true);
    try {
      const result = await operation();
      if (result?.data?.deduped) toast.info("Already filtered"); else toast.success(success);
      await load();
    } catch (e: any) {
      if ([401, 403].includes(e?.response?.status)) { setFilters([]); setLoaded(false); }
      toast.error(e?.response?.data?.detail || "Keyword change failed. Your rules were not removed from this view.");
    } finally { pending.current = false; setBusy(false); }
  };

  const add = () => {
    if (!word.trim()) return;
    mutate(async () => {
      const result = await api.post("/admin/platform/keyword-filters", { word: word.trim(), severity });
      setWord(""); return result;
    }, "Keyword added");
  };

  return (
    <section className="space-y-3 mt-6 pt-6 border-t border-border" data-testid="keyword-filters-section" aria-busy={loading}>
      <div className="flex items-start justify-between gap-2">
        <div><h2 className="text-lg font-semibold">Keyword Filters</h2>
          <p className="text-xs text-muted-foreground">Words/phrases that auto-flag content. Case-insensitive, word-boundary matched.</p></div>
        <Button variant="outline" onClick={load} disabled={loading || busy}>Refresh rules</Button>
      </div>
      {loading && <p role="status">{loaded ? "Refreshing keyword filters…" : "Loading keyword filters…"}</p>}
      {error && <div role="alert" className="rounded border border-amber-500/50 p-3 space-y-2">
        <p>{error}</p>{loaded && <p>Showing the last successful rules. They may be out of date.</p>}
        <Button onClick={load} disabled={loading}>Retry</Button>
      </div>}
      <div className="flex flex-wrap items-center gap-2">
        <Input placeholder="Banned word or phrase…" aria-label="Keyword or phrase" value={word} onChange={(e) => setWord(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); add(); } }}
          className="max-w-xs" data-testid="keyword-add-input" disabled={!loaded || busy} />
        <Select value={severity} onValueChange={setSeverity} disabled={!loaded || busy}>
          <SelectTrigger className="w-28" data-testid="keyword-severity-select" aria-label="Keyword severity"><SelectValue /></SelectTrigger>
          <SelectContent><SelectItem value="low">Low</SelectItem><SelectItem value="medium">Medium</SelectItem><SelectItem value="high">High</SelectItem></SelectContent>
        </Select>
        <Button onClick={add} disabled={!loaded || busy || loading || !word.trim()} data-testid="keyword-add-btn">Add</Button>
      </div>
      {loaded && filters.length === 0 && !error && !loading && <p className="text-sm text-muted-foreground py-2">No keywords configured yet.</p>}
      {loaded && filters.length > 0 && <div className="flex flex-wrap gap-2" data-testid="keyword-list">
        {filters.map((f) => <div key={f.filter_id} className="px-2 py-1 rounded border border-border bg-secondary/30 text-xs flex items-center gap-2" data-testid={`keyword-${f.filter_id}`}>
          <span className="font-mono">{f.word}</span><span className="text-muted-foreground">{f.severity}</span>
          <button type="button" aria-label={`Remove keyword ${f.word}`} disabled={busy || loading}
            onClick={() => mutate(() => api.delete(`/admin/platform/keyword-filters/${f.filter_id}`), "Keyword removed")}
            data-testid={`keyword-remove-${f.filter_id}`} className="text-rose-400">✕</button>
        </div>)}
      </div>}
    </section>
  );
}
