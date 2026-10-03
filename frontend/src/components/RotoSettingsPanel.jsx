/**
 * Iter 232N.86 — Rotisserie (Roto) league settings panel.
 *
 * Rendered inside BasicsStep + Commissioner Settings whenever
 * `scoring_format === "roto"`. Presents:
 *   • Category picker (skater + goalie stat catalog with checkboxes)
 *   • Scoring period length (0 = single full-season period, else # of weeks)
 *   • Tiebreak rule (split vs high)
 *   • Playoffs toggle (default off) + auto-recompute toggle
 *
 * Reads the catalog via GET /leagues/{id}/roto/categories/catalog and
 * persists via PUT /leagues/{id} on save.
 */
import { useEffect, useState } from "react";
import { Trophy, Settings, RefreshCw, ListChecks } from "lucide-react";
import api from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Checkbox } from "@/components/ui/checkbox";

export default function RotoSettingsPanel({ leagueId, embedded = false }) {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [catalog, setCatalog] = useState([]);
  const [selected, setSelected] = useState(new Set());
  const [periodLength, setPeriodLength] = useState(1);
  const [tiebreak, setTiebreak] = useState("split");
  const [playoffsEnabled, setPlayoffsEnabled] = useState(false);
  const [autoRecompute, setAutoRecompute] = useState(true);

  useEffect(() => {
    if (!leagueId) return;
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const { data } = await api.get(`/leagues/${leagueId}/roto/categories/catalog`);
        if (cancelled) return;
        setCatalog(data.categories || []);
        setSelected(new Set(data.selected || []));
        setPeriodLength(Number(data.period_length_weeks ?? 1));
        setTiebreak(data.tiebreak || "split");
        setPlayoffsEnabled(Boolean(data.playoffs_enabled));
        setAutoRecompute(Boolean(data.auto_recompute));
      } catch (e) {
        toast.error(e?.response?.data?.detail || "Failed to load Roto settings");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [leagueId]);

  const toggle = (k) => setSelected((prev) => {
    const next = new Set(prev);
    if (next.has(k)) next.delete(k); else next.add(k);
    return next;
  });

  const save = async () => {
    if (selected.size === 0) {
      toast.error("Pick at least one scoring category");
      return;
    }
    setSaving(true);
    try {
      await api.put(`/leagues/${leagueId}`, {
        roto_categories: [...selected],
        roto_period_length_weeks: Math.max(0, Math.min(52, Number(periodLength) || 0)),
        roto_tiebreak: tiebreak,
        roto_playoffs_enabled: playoffsEnabled,
        roto_auto_recompute: autoRecompute,
      });
      toast.success(`Roto settings saved · ${selected.size} categories`);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Save failed");
    } finally {
      setSaving(false);
    }
  };

  if (loading) return (
    <div className="text-xs text-muted-foreground flex items-center gap-2 py-4">
      <RefreshCw className="h-3 w-3 animate-spin" /> Loading roto settings…
    </div>
  );

  const skater = catalog.filter((c) => c.type === "skater");
  const goalie = catalog.filter((c) => c.type === "goalie");
  return (
    <div
      className={embedded ? "space-y-3" : "space-y-4 border border-emerald-500/40 bg-emerald-500/5 rounded p-4"}
      data-testid="roto-settings-panel"
    >
      <div className="flex items-center gap-2 flex-wrap">
        <Trophy className="h-4 w-4 text-emerald-300" />
        <h3 className="text-sm font-semibold text-white">Rotisserie Scoring</h3>
        <span className="text-[11px] text-muted-foreground">
          Pick the stat categories, scoring cadence, and tiebreak rule.
        </span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div className="rounded border border-border p-3 space-y-2" data-testid="roto-skater-cats">
          <p className="text-[11px] font-semibold uppercase tracking-wide flex items-center gap-1">
            <ListChecks className="h-3 w-3" /> Skater categories
          </p>
          {skater.map((c) => (
            <label key={c.key} className="flex items-center gap-2 text-xs">
              <Checkbox
                checked={selected.has(c.key)}
                onCheckedChange={() => toggle(c.key)}
                data-testid={`roto-cat-${c.key}`}
              />
              <span>{c.label}</span>
              {!c.higher_is_better && (
                <span className="text-[9px] uppercase tracking-wider text-amber-300/80">lower better</span>
              )}
            </label>
          ))}
        </div>
        <div className="rounded border border-border p-3 space-y-2" data-testid="roto-goalie-cats">
          <p className="text-[11px] font-semibold uppercase tracking-wide flex items-center gap-1">
            <ListChecks className="h-3 w-3" /> Goalie categories
          </p>
          {goalie.map((c) => (
            <label key={c.key} className="flex items-center gap-2 text-xs">
              <Checkbox
                checked={selected.has(c.key)}
                onCheckedChange={() => toggle(c.key)}
                data-testid={`roto-cat-${c.key}`}
              />
              <span>{c.label}</span>
              {!c.higher_is_better && (
                <span className="text-[9px] uppercase tracking-wider text-amber-300/80">lower better</span>
              )}
            </label>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <div>
          <Label className="text-[11px]" htmlFor="roto-period-len">
            Scoring period (weeks)
          </Label>
          <Input
            id="roto-period-len"
            type="number" min={0} max={52}
            value={periodLength}
            onChange={(e) => setPeriodLength(Math.max(0, Math.min(52, parseInt(e.target.value || "0", 10))))}
            className="h-8 text-xs"
            data-testid="roto-period-length"
          />
          <p className="text-[10px] text-muted-foreground mt-1">
            {periodLength === 0 ? "Single full-season period" : `Re-rank every ${periodLength} week${periodLength === 1 ? "" : "s"}`}
          </p>
        </div>
        <div>
          <Label className="text-[11px]">Tiebreak rule</Label>
          <div className="flex gap-1 mt-1" data-testid="roto-tiebreak-group">
            {["split", "high"].map((t) => (
              <button
                key={t}
                type="button"
                onClick={() => setTiebreak(t)}
                className={`text-[11px] px-2 py-1 rounded border transition-colors ${
                  tiebreak === t
                    ? "bg-emerald-500/20 border-emerald-500/50 text-emerald-50"
                    : "border-border text-muted-foreground"
                }`}
                data-testid={`roto-tiebreak-${t}`}
              >
                {t === "split" ? "Split evenly" : "Top rank wins"}
              </button>
            ))}
          </div>
          <p className="text-[10px] text-muted-foreground mt-1">
            {tiebreak === "split"
              ? "Tied teams share the sum of their ranks' points."
              : "Tied teams both receive the higher rank's points."}
          </p>
        </div>
        <div className="space-y-2">
          <div className="flex items-center justify-between gap-2">
            <Label className="text-[11px]" htmlFor="roto-playoffs-toggle">
              Playoffs enabled
            </Label>
            <Switch
              id="roto-playoffs-toggle"
              checked={playoffsEnabled}
              onCheckedChange={setPlayoffsEnabled}
              data-testid="roto-playoffs-toggle"
            />
          </div>
          <div className="flex items-center justify-between gap-2">
            <Label className="text-[11px]" htmlFor="roto-auto-recompute-toggle">
              Auto-recompute on stat corrections
            </Label>
            <Switch
              id="roto-auto-recompute-toggle"
              checked={autoRecompute}
              onCheckedChange={setAutoRecompute}
              data-testid="roto-auto-recompute-toggle"
            />
          </div>
        </div>
      </div>

      <div className="flex justify-end">
        <Button
          size="sm"
          onClick={save}
          disabled={saving}
          data-testid="roto-settings-save-btn"
          className="bg-emerald-500/90 hover:bg-emerald-400 text-emerald-950"
        >
          <Settings className="h-3.5 w-3.5 mr-1" />
          {saving ? "Saving…" : "Save Roto settings"}
        </Button>
      </div>
    </div>
  );
}
