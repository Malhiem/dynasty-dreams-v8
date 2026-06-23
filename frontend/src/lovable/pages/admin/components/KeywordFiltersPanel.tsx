// @ts-nocheck
/* KeywordFiltersPanel — extracted from AdminDashboard.tsx during Iter 224 refactor. */
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

/* ─── Iter 206 — Keyword Filters Manager ─────────────────────────────── */
export function KeywordFiltersPanel() {
  const [filters, setFilters] = useState<any[]>([]);
  const [word, setWord] = useState("");
  const [severity, setSeverity] = useState<"low" | "medium" | "high">("medium");

  const load = useCallback(async () => {
    try {
      const { data } = await api.get("/admin/platform/keyword-filters");
      setFilters(data?.filters || []);
    } catch { /* noop */ }
  }, []);

  useEffect(() => { load(); }, [load]);

  const add = async () => {
    if (!word.trim()) return;
    try {
      const { data } = await api.post("/admin/platform/keyword-filters", { word: word.trim(), severity });
      if (data?.deduped) toast.info("Already filtered");
      else toast.success("Keyword added");
      setWord("");
      await load();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Failed");
    }
  };

  const remove = async (id: string) => {
    try {
      await api.delete(`/admin/platform/keyword-filters/${id}`);
      toast.success("Keyword removed");
      await load();
    } catch { /* noop */ }
  };

  return (
    <section className="space-y-3 mt-6 pt-6 border-t border-border" data-testid="keyword-filters-section">
      <div>
        <h2 className="text-lg font-semibold">Keyword Filters</h2>
        <p className="text-xs text-muted-foreground">
          Words/phrases that auto-flag content into the moderation queue. Case-insensitive, word-boundary matched.
        </p>
      </div>
      <div className="flex items-center gap-2">
        <Input
          placeholder="Banned word or phrase…"
          value={word}
          onChange={(e) => setWord(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && add()}
          className="max-w-xs"
          data-testid="keyword-add-input"
        />
        <Select value={severity} onValueChange={(v: any) => setSeverity(v)}>
          <SelectTrigger className="w-28" data-testid="keyword-severity-select"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="low">Low</SelectItem>
            <SelectItem value="medium">Medium</SelectItem>
            <SelectItem value="high">High</SelectItem>
          </SelectContent>
        </Select>
        <Button onClick={add} data-testid="keyword-add-btn">Add</Button>
      </div>
      {filters.length === 0 ? (
        <div className="text-sm text-muted-foreground py-2">No keywords configured yet.</div>
      ) : (
        <div className="flex flex-wrap gap-2" data-testid="keyword-list">
          {filters.map((f: any) => (
            <div key={f.filter_id} className="px-2 py-1 rounded border border-border bg-secondary/30 text-xs flex items-center gap-2" data-testid={`keyword-${f.filter_id}`}>
              <span className="font-mono">{f.word}</span>
              <span className={`text-[9px] uppercase ${
                f.severity === "high" ? "text-rose-300" : f.severity === "low" ? "text-emerald-300" : "text-amber-300"
              }`}>{f.severity}</span>
              <button onClick={() => remove(f.filter_id)} className="text-rose-400 hover:text-rose-300 text-[10px]" data-testid={`keyword-remove-${f.filter_id}`}>✕</button>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}


