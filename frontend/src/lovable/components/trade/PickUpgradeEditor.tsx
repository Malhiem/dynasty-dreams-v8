// @ts-nocheck
import { useEffect, useMemo, useState } from "react";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { X, TrendingUp, TrendingDown } from "lucide-react";
import { useTradeBuilder } from "@/lovable/state/TradeBuilderContext";

/**
 * Outcome-modifying conditional clause: when a trigger fires, a draft pick
 * already in this trade has its round (and optionally year) rewritten.
 *
 * Window-bridge contract:
 *   window.__addPickUpgrade()        — add an empty row
 *   window.__getPickUpgrades()       — read the current rows for proposal payload
 *
 * Each row binds to a pick that's part of the trade's `picks` array
 * (TradeBuilderContext) so we can show the live "2nd → 1st" preview.
 */

const TRIGGER_OPTIONS = [
  { value: "won_championship", label: "wins the championship" },
  { value: "won_conference",   label: "wins their conference" },
  { value: "won_division",     label: "wins their division" },
  { value: "made_playoffs",    label: "makes the playoffs" },
  { value: "won_consolation",  label: "wins the consolation bracket" },
  { value: "team_wins",        label: "team wins (≥)" },
  { value: "team_losses",      label: "team losses (≥)" },
  { value: "team_rank",        label: "team rank (≤ better)" },
  { value: "team_points_for",  label: "team points-for (≥)" },
];

// Triggers that don't take a numeric threshold
const BOOL_TRIGGERS = new Set([
  "won_championship", "won_conference", "won_division",
  "made_playoffs", "won_consolation",
]);

const ROUND_LABELS = ["", "1st", "2nd", "3rd", "4th", "5th", "6th", "7th", "8th", "9th", "10th"];

const NEXT_4_YEARS = (() => {
  const now = new Date();
  const start = now.getMonth() >= 6 ? now.getFullYear() + 1 : now.getFullYear();
  return [start, start + 1, start + 2, start + 3];
})();

export function PickUpgradeEditor() {
  const ctx = useTradeBuilder();
  const tradePicks = ctx?.picks || [];
  const partners = ctx?.partners || [];

  const [rows, setRows] = useState([]);

  useEffect(() => {
    (window as any).__addPickUpgrade = () => {
      setRows((prev) => [...prev, {
        id: `pu_${Date.now()}_${prev.length}`,
        pick_id: tradePicks[0]?.pick?.pickId || tradePicks[0]?.pick?.id || "",
        new_round: 1,
        new_year: null,
        condition: {
          subject_type: "team",
          subject: "offered",
          team_id: ctx?.myTeamId || "",
          metric: "won_championship",
          operator: "eq",
          threshold: 1,
          description: "If my team wins the championship",
        },
      }]);
    };
    (window as any).__getPickUpgrades = () =>
      rows
        .filter((r) => r.pick_id && r.new_round)
        .map((r) => ({
          pick_id: r.pick_id,
          new_round: Number(r.new_round),
          new_year: r.new_year ? Number(r.new_year) : null,
          condition: {
            ...r.condition,
            threshold: Number(r.condition?.threshold ?? 1),
          },
          description: r.description,
        }));
    return () => {
      delete (window as any).__addPickUpgrade;
      delete (window as any).__getPickUpgrades;
    };
  }, [rows, tradePicks, ctx?.myTeamId]);

  const update = (id, patch) =>
    setRows((prev) => prev.map((r) => (r.id === id ? { ...r, ...patch } : r)));
  const updateCond = (id, patch) =>
    setRows((prev) =>
      prev.map((r) => (r.id === id ? { ...r, condition: { ...r.condition, ...patch } } : r)),
    );
  const remove = (id) => setRows((prev) => prev.filter((r) => r.id !== id));

  const teamOptions = useMemo(() => {
    const seen = new Set();
    const out = [];
    for (const p of partners) {
      if (!p?.id || seen.has(p.id)) continue;
      seen.add(p.id);
      out.push({ id: p.id, name: p.name });
    }
    return out;
  }, [partners]);

  const noPicks = tradePicks.length === 0;

  if (rows.length === 0 && noPicks) {
    return (
      <div
        className="text-[11px] text-muted-foreground italic border border-dashed border-border rounded-md px-3 py-2"
        data-testid="pick-upgrades-empty"
      >
        Add a draft pick to this trade first, then click <strong>+ Pick upgrade</strong> to lock a round-swap behind a season outcome.
      </div>
    );
  }
  if (rows.length === 0) {
    return (
      <div
        className="text-[11px] text-muted-foreground italic border border-dashed border-border rounded-md px-3 py-2"
        data-testid="pick-upgrades-empty"
      >
        No pick upgrades yet. Click <strong>+ Pick upgrade</strong> to set a round-swap trigger like "if my team wins the championship, this 2nd becomes a 1st".
      </div>
    );
  }

  return (
    <div className="space-y-2" data-testid="pick-upgrades-list">
      {rows.map((r, i) => {
        const pickRow = tradePicks.find((p) => (p.pick.pickId || p.pick.id) === r.pick_id);
        const currentRound = Number(pickRow?.pick?.round || 0);
        const newRound = Number(r.new_round || 0);
        const direction =
          currentRound && newRound
            ? newRound < currentRound
              ? "upgrade"
              : newRound > currentRound
              ? "downgrade"
              : "same"
            : null;
        const isBool = BOOL_TRIGGERS.has(r.condition?.metric);
        return (
          <div
            key={r.id}
            data-testid={`pick-upgrade-row-${i}`}
            className="bg-card border border-border rounded-md px-3 py-2 space-y-1.5"
          >
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
                <span>Pick:</span>
                <Select value={r.pick_id} onValueChange={(v) => update(r.id, { pick_id: v })}>
                  <SelectTrigger
                    data-testid={`pick-upgrade-pick-${i}`}
                    className="h-7 w-[200px] text-[11px]"
                  >
                    <SelectValue placeholder={noPicks ? "Add picks first" : "Select pick"} />
                  </SelectTrigger>
                  <SelectContent>
                    {tradePicks.map((p) => {
                      const pid = p.pick.pickId || p.pick.id;
                      return (
                        <SelectItem key={pid} value={pid}>
                          {p.pick.year} R{p.pick.round} (from {p.pick.ownerTeamName || "?"})
                        </SelectItem>
                      );
                    })}
                  </SelectContent>
                </Select>
                {direction === "upgrade" && (
                  <Badge variant="outline" className="border-emerald-500/50 text-emerald-500 text-[10px] h-4 gap-1">
                    <TrendingUp className="h-2.5 w-2.5" />
                    Upgrade
                  </Badge>
                )}
                {direction === "downgrade" && (
                  <Badge variant="outline" className="border-rose-500/50 text-rose-500 text-[10px] h-4 gap-1">
                    <TrendingDown className="h-2.5 w-2.5" />
                    Downgrade
                  </Badge>
                )}
              </div>
              <Button
                variant="ghost"
                size="icon"
                className="h-6 w-6"
                onClick={() => remove(r.id)}
                data-testid={`pick-upgrade-remove-${i}`}
              >
                <X className="h-3.5 w-3.5" />
              </Button>
            </div>
            <div className="flex flex-wrap items-center gap-1.5 text-[11px]">
              <span className="text-muted-foreground">If</span>
              <Select
                value={r.condition?.team_id}
                onValueChange={(v) => updateCond(r.id, { team_id: v })}
              >
                <SelectTrigger
                  data-testid={`pick-upgrade-team-${i}`}
                  className="h-7 w-[140px] text-[11px]"
                >
                  <SelectValue placeholder="Team" />
                </SelectTrigger>
                <SelectContent>
                  {teamOptions.map((t) => (
                    <SelectItem key={t.id} value={t.id}>{t.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Select
                value={r.condition?.metric}
                onValueChange={(v) =>
                  updateCond(r.id, {
                    metric: v,
                    operator: BOOL_TRIGGERS.has(v) ? "eq" : (r.condition?.operator || "gte"),
                    threshold: BOOL_TRIGGERS.has(v) ? 1 : (r.condition?.threshold || 1),
                  })
                }
              >
                <SelectTrigger
                  data-testid={`pick-upgrade-trigger-${i}`}
                  className="h-7 w-[200px] text-[11px]"
                >
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {TRIGGER_OPTIONS.map((opt) => (
                    <SelectItem key={opt.value} value={opt.value}>{opt.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {!isBool && (
                <Input
                  type="number"
                  data-testid={`pick-upgrade-threshold-${i}`}
                  className="h-7 w-[64px] text-[11px]"
                  value={r.condition?.threshold ?? 1}
                  onChange={(e) => updateCond(r.id, { threshold: Number(e.target.value) })}
                />
              )}
              <span className="text-muted-foreground">then pick becomes</span>
              <Select
                value={String(r.new_round)}
                onValueChange={(v) => update(r.id, { new_round: Number(v) })}
              >
                <SelectTrigger
                  data-testid={`pick-upgrade-new-round-${i}`}
                  className="h-7 w-[88px] text-[11px]"
                >
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {ROUND_LABELS.slice(1).map((lbl, idx) => (
                    <SelectItem key={idx + 1} value={String(idx + 1)}>{lbl} round</SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Select
                value={r.new_year ? String(r.new_year) : "__same__"}
                onValueChange={(v) => update(r.id, { new_year: v === "__same__" ? null : Number(v) })}
              >
                <SelectTrigger
                  data-testid={`pick-upgrade-new-year-${i}`}
                  className="h-7 w-[110px] text-[11px]"
                >
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__same__">Same year</SelectItem>
                  {NEXT_4_YEARS.map((y) => (
                    <SelectItem key={y} value={String(y)}>{y}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
        );
      })}
    </div>
  );
}
