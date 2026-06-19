// @ts-nocheck
/**
 * Iter 184 — Daily Goalie Picker extracted from `PlayerRoster.tsx`
 * (was lines 694-786, ~94 lines). Renders a 7-day Mon→Sun grid of
 * starter-goalie locks for the current scoring week. Uses the same
 * `lockMap` shape the backend persists.
 */
import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";

export const DailyGoaliePicker = ({ roster, lockMap, onSave, saving, gpLimit, week }: any) => {
  const now = new Date();
  const weekStart = new Date(now);
  weekStart.setDate(now.getDate() - ((now.getDay() + 6) % 7));
  const days = Array.from({ length: 7 }, (_, i) => {
    const d = new Date(weekStart);
    d.setDate(weekStart.getDate() + i);
    return d;
  });
  const goalies = (roster || []).filter((p: any) =>
    p.position === "G" || p.player_type === "goalie",
  );
  const [draft, setDraft] = useState<Record<string, string>>(lockMap || {});
  useEffect(() => { setDraft(lockMap || {}); }, [lockMap]);
  const slottedCount = Object.values(draft).filter(Boolean).length;
  const overCap = gpLimit && slottedCount > gpLimit;

  const setSlot = (dateIso: string, playerId: string) => {
    setDraft((prev) => {
      const next = { ...prev };
      if (!playerId || playerId === "__none__") delete next[dateIso];
      else next[dateIso] = playerId;
      return next;
    });
  };

  const fmtDate = (d: Date) =>
    `${d.toLocaleDateString(undefined, { weekday: "short" })} ${d.toLocaleDateString(undefined, { month: "short", day: "numeric" })}`;
  const toIso = (d: Date) => d.toISOString().slice(0, 10);

  return (
    <div className="px-4 py-3 border-b border-border bg-emerald-500/5" data-testid="daily-goalie-picker">
      <div className="flex items-center justify-between flex-wrap gap-2 mb-2">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-xs font-semibold text-emerald-300 uppercase tracking-wider">
            Daily Goalie Lock · Week {week}
          </span>
          <span className={`text-[10px] px-2 py-0.5 rounded-full border ${
            overCap
              ? "bg-rose-500/10 text-rose-300 border-rose-500/30"
              : "bg-secondary text-muted-foreground border-border"
          }`}>
            {slottedCount} slotted{gpLimit ? ` / ${gpLimit} max` : ""}
          </span>
        </div>
        <Button
          size="sm"
          variant="outline"
          className="h-7 text-xs"
          onClick={() => onSave(draft)}
          disabled={saving || overCap || JSON.stringify(draft) === JSON.stringify(lockMap || {})}
          data-testid="daily-goalie-picker-save"
        >
          {saving ? "Saving…" : "Save Daily Locks"}
        </Button>
      </div>
      {overCap && (
        <div className="text-[11px] text-rose-300 mb-2">
          Exceeds the {gpLimit}-game cap — remove some slots before saving.
        </div>
      )}
      <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-2">
        {days.map((d) => {
          const iso = toIso(d);
          const slotted = draft[iso] || "";
          return (
            <div key={iso} className="rounded-md border border-border bg-secondary/30 p-2"
                 data-testid={`daily-goalie-${iso}`}>
              <div className="text-[10px] font-medium text-muted-foreground mb-1">{fmtDate(d)}</div>
              <select
                className="w-full bg-secondary border border-border rounded px-1.5 py-1 text-xs text-foreground"
                value={slotted}
                onChange={(e) => setSlot(iso, e.target.value)}
                data-testid={`daily-goalie-select-${iso}`}
              >
                <option value="__none__">— No starter —</option>
                {goalies.map((g: any) => (
                  <option key={g.id} value={g.id}>{g.name}</option>
                ))}
              </select>
            </div>
          );
        })}
      </div>
      {goalies.length === 0 && (
        <div className="text-[11px] text-muted-foreground italic mt-2">
          Your roster has no goalies yet — add one to enable per-day locks.
        </div>
      )}
    </div>
  );
};

export default DailyGoaliePicker;
