// @ts-nocheck
import { useEffect, useState } from "react";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { X } from "lucide-react";

export type TradeCondition = {
  id: string;
  subject_type: "player" | "team";
  subject: "offered" | "requested";
  metric: string;
  operator: string;
  threshold: number;
  description?: string;
};

const PLAYER_METRIC_OPTIONS = [
  { value: "nhl_points",           label: "NHL points (G+A)" },
  { value: "nhl_goals",            label: "NHL goals" },
  { value: "nhl_assists",          label: "NHL assists" },
  { value: "nhl_wins",             label: "NHL wins (goalie)" },
  { value: "games_played",         label: "Games played" },
  { value: "fantasy_points",       label: "Fantasy points (season)" },
  { value: "live_fantasy_points",  label: "Fantasy points (live)" },
];

const TEAM_METRIC_OPTIONS = [
  { value: "won_championship",  label: "Won championship" },
  { value: "won_division",      label: "Won division" },
  { value: "made_playoffs",     label: "Made playoffs" },
  { value: "team_rank",         label: "Team rank in league" },
  { value: "team_wins",         label: "Team wins" },
  { value: "team_losses",       label: "Team losses" },
  { value: "team_points_for",   label: "Team points scored" },
];

const OPERATOR_LABELS: Record<string, string> = { gte: "≥", lte: "≤", eq: "=" };

export function TradeConditionsEditor() {
  const [rows, setRows] = useState<TradeCondition[]>([]);

  // Expose an imperative add handler on window so the parent button can fire it
  useEffect(() => {
    (window as any).__addTradeCondition = (subjectType: "player" | "team" = "player") => {
      setRows((prev) => [...prev, {
        id: `c_${Date.now()}_${prev.length}`,
        subject_type: subjectType,
        subject: "offered",
        metric: subjectType === "team" ? "won_championship" : "nhl_points",
        operator: subjectType === "team" ? "eq" : "gte",
        threshold: subjectType === "team" ? 1 : 100,
      }]);
    };
    (window as any).__getTradeConditions = () => rows;
    return () => {
      delete (window as any).__addTradeCondition;
      delete (window as any).__getTradeConditions;
    };
  }, [rows]);

  const update = (id: string, patch: Partial<TradeCondition>) => {
    setRows((prev) => prev.map(r => r.id === id ? { ...r, ...patch } : r));
  };
  const remove = (id: string) => setRows((prev) => prev.filter(r => r.id !== id));

  if (rows.length === 0) {
    return (
      <div
        className="text-[11px] text-muted-foreground italic border border-dashed border-border rounded-md px-3 py-2"
        data-testid="trade-conditions-empty"
      >
        No conditional triggers. Click "Add condition" to lock this trade behind a performance threshold.
      </div>
    );
  }

  return (
    <div className="space-y-2" data-testid="trade-conditions-list">
      {rows.map((r, i) => {
        const metricOptions = r.subject_type === "team" ? TEAM_METRIC_OPTIONS : PLAYER_METRIC_OPTIONS;
        const isBoolMetric = r.subject_type === "team" && ["won_championship", "won_division", "made_playoffs"].includes(r.metric);
        return (
        <div key={r.id} className="flex flex-wrap items-center gap-1.5 bg-card border border-border rounded-md px-2 py-1.5" data-testid={`trade-condition-row-${i}`}>
          <Select value={r.subject_type} onValueChange={(v) => update(r.id, {
            subject_type: v as any,
            metric: v === "team" ? "won_championship" : "nhl_points",
            operator: v === "team" ? "eq" : "gte",
            threshold: v === "team" ? 1 : 100,
          })}>
            <SelectTrigger className="h-7 w-[90px] text-[11px]" data-testid={`trade-condition-type-${i}`}><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="player">Player</SelectItem>
              <SelectItem value="team">Team</SelectItem>
            </SelectContent>
          </Select>
          <Select value={r.subject} onValueChange={(v) => update(r.id, { subject: v as any })}>
            <SelectTrigger className="h-7 w-[128px] text-[11px]"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="offered">{r.subject_type === "team" ? "My team" : "Asset I send"}</SelectItem>
              <SelectItem value="requested">{r.subject_type === "team" ? "Partner team" : "Asset I receive"}</SelectItem>
            </SelectContent>
          </Select>
          <Select value={r.metric} onValueChange={(v) => update(r.id, { metric: v })}>
            <SelectTrigger className="h-7 w-[190px] text-[11px]"><SelectValue /></SelectTrigger>
            <SelectContent>
              {metricOptions.map(m => <SelectItem key={m.value} value={m.value}>{m.label}</SelectItem>)}
            </SelectContent>
          </Select>
          {!isBoolMetric && (
            <>
              <Select value={r.operator} onValueChange={(v) => update(r.id, { operator: v })}>
                <SelectTrigger className="h-7 w-[60px] text-[11px]"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="gte">{OPERATOR_LABELS.gte}</SelectItem>
                  <SelectItem value="lte">{OPERATOR_LABELS.lte}</SelectItem>
                  <SelectItem value="eq">{OPERATOR_LABELS.eq}</SelectItem>
                </SelectContent>
              </Select>
              <Input
                type="number"
                value={r.threshold}
                onChange={(e) => update(r.id, { threshold: Number(e.target.value) })}
                className="h-7 w-[84px] text-[11px]"
                data-testid={`trade-condition-threshold-${i}`}
              />
            </>
          )}
          {isBoolMetric && (
            <span className="text-[11px] text-muted-foreground italic">must be true</span>
          )}
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7 ml-auto"
            onClick={() => remove(r.id)}
            data-testid={`trade-condition-remove-${i}`}
          >
            <X className="h-3.5 w-3.5" />
          </Button>
        </div>
        );
      })}
    </div>
  );
}
