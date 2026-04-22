// @ts-nocheck
import { useEffect, useState } from "react";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { X } from "lucide-react";

export type TradeCondition = {
  id: string;
  subject: "offered" | "requested";
  metric: string;
  operator: string;
  threshold: number;
  description?: string;
};

const METRIC_OPTIONS = [
  { value: "nhl_points",           label: "NHL points (G+A)" },
  { value: "nhl_goals",            label: "NHL goals" },
  { value: "nhl_assists",          label: "NHL assists" },
  { value: "nhl_wins",             label: "NHL wins (goalie)" },
  { value: "games_played",         label: "Games played" },
  { value: "fantasy_points",       label: "Fantasy points (season)" },
  { value: "live_fantasy_points",  label: "Fantasy points (live)" },
];

const OPERATOR_LABELS: Record<string, string> = { gte: "≥", lte: "≤", eq: "=" };

export function TradeConditionsEditor() {
  const [rows, setRows] = useState<TradeCondition[]>([]);

  // Expose an imperative add handler on window so the parent button can fire it
  useEffect(() => {
    (window as any).__addTradeCondition = () => {
      setRows((prev) => [...prev, {
        id: `c_${Date.now()}_${prev.length}`,
        subject: "offered",
        metric: "nhl_points",
        operator: "gte",
        threshold: 100,
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
      {rows.map((r, i) => (
        <div key={r.id} className="flex flex-wrap items-center gap-1.5 bg-card border border-border rounded-md px-2 py-1.5" data-testid={`trade-condition-row-${i}`}>
          <Select value={r.subject} onValueChange={(v) => update(r.id, { subject: v as any })}>
            <SelectTrigger className="h-7 w-[120px] text-[11px]"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="offered">Asset I send</SelectItem>
              <SelectItem value="requested">Asset I receive</SelectItem>
            </SelectContent>
          </Select>
          <Select value={r.metric} onValueChange={(v) => update(r.id, { metric: v })}>
            <SelectTrigger className="h-7 w-[180px] text-[11px]"><SelectValue /></SelectTrigger>
            <SelectContent>
              {METRIC_OPTIONS.map(m => <SelectItem key={m.value} value={m.value}>{m.label}</SelectItem>)}
            </SelectContent>
          </Select>
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
      ))}
    </div>
  );
}
