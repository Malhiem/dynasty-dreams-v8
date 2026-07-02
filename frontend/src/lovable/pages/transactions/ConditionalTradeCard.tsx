// @ts-nocheck
// Iter 232L (refactor) — ConditionalTradeCard + supporting rows + labels
// extracted from Transactions.tsx.
//
// A "conditional trade" in our model is (player/team metric) → (draft
// pick modification). The trade has already executed; each pick-upgrade
// clause tracks its own resolution lifecycle (pending / triggered /
// failed). This file renders the executed trade summary and the list of
// pick-outcome clauses with per-clause notification subscribe controls.
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  Clock, CheckCircle2, GitBranch, Zap, MinusCircle, Bell, BellOff,
} from "lucide-react";
import TeamLink from "@/lovable/components/TeamLink";
import { selectCategoriesForAssets } from "./types";

// ─── Human-readable metric + operator labels ─────────────────────────
const METRIC_LABELS: Record<string, string> = {
  // Player
  nhl_points: "NHL points",
  goals: "Goals",
  assists: "Assists",
  ppg: "Points per game",
  games_played: "Games played",
  fantasy_points: "Fantasy points",
  live_fantasy_points: "Live fantasy points",
  // Team
  team_wins: "Wins",
  team_losses: "Losses",
  team_points_for: "Points For",
  team_rank: "League rank",
  made_playoffs: "Made playoffs",
  won_division: "Won division",
  won_conference: "Won conference",
  won_championship: "Won championship",
  won_consolation: "Won consolation bracket",
  won_draft_lottery: "Won draft lottery",
  // Pick
  pick_slot: "Pick slot (#)",
  pick_round: "Pick round",
};
const OP_LABEL: Record<string, string> = { gte: "≥", lte: "≤", eq: "=" };

export function describeCondition(c: any): string {
  if (c?.description) return c.description;
  const m = METRIC_LABELS[c?.metric] || c?.metric || "metric";
  const op = OP_LABEL[c?.operator] || c?.operator || "";
  return `${m} ${op} ${c?.threshold}`;
}

// ─── ConditionalAssetTable — mirrors TradeCard's asset table but with a
//     tighter column set (no Age/GP; Cap + FPts/G is enough for a
//     completed trade). Reused via the ConditionalTradeCard.
function ConditionalAssetTable({ assets, viewMode, categories }) {
  const catsToShow = viewMode === "categories"
    ? selectCategoriesForAssets(assets, categories)
    : [];
  return (
    <div className="overflow-x-auto -mx-2 sm:mx-0">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="text-xs whitespace-nowrap">Player</TableHead>
            <TableHead className="text-xs whitespace-nowrap">Pos</TableHead>
            <TableHead className="text-xs whitespace-nowrap">Cap</TableHead>
            {viewMode === "fpts" ? (
              <>
                <TableHead className="text-xs whitespace-nowrap">FPts</TableHead>
                <TableHead className="text-xs whitespace-nowrap">FP/G</TableHead>
              </>
            ) : (
              catsToShow.map((c) => (
                <TableHead key={c.key} className="text-xs whitespace-nowrap" title={c.key}>
                  {c.label}
                </TableHead>
              ))
            )}
          </TableRow>
        </TableHeader>
        <TableBody>
          {assets.map((a) => (
            <TableRow key={a.name}>
              <TableCell className="font-medium text-sm whitespace-nowrap">
                {a.name}
                {a.type === "pick" && (
                  <Badge variant="secondary" className="ml-1 text-[10px]">Pick</Badge>
                )}
              </TableCell>
              <TableCell className="text-sm">{a.position}</TableCell>
              <TableCell className="text-sm whitespace-nowrap">{a.capHit}</TableCell>
              {viewMode === "fpts" ? (
                <>
                  <TableCell className="text-sm font-semibold text-primary">
                    {a.type === "player" ? a.fantasyPts : "—"}
                  </TableCell>
                  <TableCell className="text-sm text-primary/80">
                    {a.type === "player" ? (a.fantasyPtsPerGame ?? 0).toFixed(2) : "—"}
                  </TableCell>
                </>
              ) : (
                catsToShow.map((c) => (
                  <TableCell key={c.key} className="text-sm">
                    {a.type === "player" ? a.statCategories?.[c.key]?.value ?? 0 : "—"}
                  </TableCell>
                ))
              )}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

// ─── ConditionEvalRow — a proposal-stage condition (pre-execution) ────
export function ConditionEvalRow({ row, subscribed, onToggleSubscribe }) {
  const c = row?.condition || {};
  const met = !!row?.met;
  const showBell = !met && !!onToggleSubscribe;
  return (
    <div
      className={`flex items-start gap-2 rounded-md border px-3 py-2 ${
        met ? "border-emerald-500/30 bg-emerald-500/5" : "border-amber-500/30 bg-amber-500/5"
      }`}
      data-testid={`condition-eval-${c.metric}-${c.threshold}`}
    >
      {met ? (
        <CheckCircle2 className="h-4 w-4 mt-0.5 text-emerald-400 shrink-0" />
      ) : (
        <Clock className="h-4 w-4 mt-0.5 text-amber-400 shrink-0" />
      )}
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium">{describeCondition(c)}</p>
        <p className="text-[11px] text-muted-foreground mt-0.5">
          Current:{" "}
          <span className="font-semibold text-foreground">
            {row?.actual_value != null
              ? Number(row.actual_value).toLocaleString(undefined, { maximumFractionDigits: 2 })
              : "—"}
          </span>
          {" · "}
          <span className={met ? "text-emerald-400" : "text-amber-400"}>
            {met ? "Met — trade triggers" : "Not yet met"}
          </span>
        </p>
      </div>
      {showBell && (
        <button
          type="button"
          onClick={onToggleSubscribe}
          className={`shrink-0 rounded-md p-1.5 transition-colors ${
            subscribed
              ? "bg-primary/20 text-primary hover:bg-primary/30"
              : "text-muted-foreground hover:bg-secondary hover:text-foreground"
          }`}
          title={
            subscribed
              ? "You'll be notified when this resolves. Click to stop."
              : "Notify me when this resolves"
          }
          data-testid={`condition-subscribe-${c.metric}-${c.threshold}`}
          aria-pressed={subscribed}
        >
          {subscribed ? <Bell className="h-3.5 w-3.5" /> : <BellOff className="h-3.5 w-3.5" />}
        </button>
      )}
    </div>
  );
}

// ─── PickUpgradeRow — post-execution pick-outcome clause ─────────────
function PickUpgradeRow({ row, subscribed, onToggleSubscribe }) {
  const c = row?.condition || {};
  const state = row?.state || "pending";
  const pick = row?.pick || {};
  const stateConfig =
    state === "triggered"
      ? { icon: Zap, color: "text-emerald-400", border: "border-emerald-500/30", bg: "bg-emerald-500/5", label: "Triggered" }
      : state === "failed"
      ? { icon: MinusCircle, color: "text-muted-foreground", border: "border-border", bg: "bg-secondary/30", label: "Did not trigger" }
      : { icon: Clock, color: "text-amber-400", border: "border-amber-500/30", bg: "bg-amber-500/5", label: "Pending" };
  const Icon = stateConfig.icon;
  const showBell = state === "pending" && !!onToggleSubscribe;
  return (
    <div
      className={`flex items-start gap-2 rounded-md border ${stateConfig.border} ${stateConfig.bg} px-3 py-2`}
      data-testid={`pick-upgrade-${row?.pick_id}`}
    >
      <Icon className={`h-4 w-4 mt-0.5 ${stateConfig.color} shrink-0`} />
      <div className="min-w-0 flex-1 space-y-1">
        <div className="flex items-center gap-2 flex-wrap">
          <p className="text-sm font-medium">
            {row?.description || (
              <>Pick {pick.year} R{pick.round}{pick.pick_number ? ` #${pick.pick_number}` : ""}</>
            )}
          </p>
          <Badge variant="outline" className={`text-[10px] ${stateConfig.color} ${stateConfig.border}`}>
            {stateConfig.label}
          </Badge>
        </div>
        <p className="text-[11px] text-muted-foreground">
          <span className="uppercase tracking-wider mr-1">Condition:</span>
          {describeCondition(c)}
          {row?.actual_value != null && (
            <span className="ml-2">
              · Current:{" "}
              <span className="font-semibold text-foreground">
                {Number(row.actual_value).toLocaleString(undefined, { maximumFractionDigits: 2 })}
              </span>
            </span>
          )}
        </p>
        <p className="text-[11px] text-foreground/85">
          <span className="uppercase tracking-wider text-muted-foreground mr-1">Outcome:</span>
          {row?.outcome_text}
        </p>
      </div>
      {showBell && (
        <button
          type="button"
          onClick={onToggleSubscribe}
          className={`shrink-0 rounded-md p-1.5 transition-colors ${
            subscribed
              ? "bg-primary/20 text-primary hover:bg-primary/30"
              : "text-muted-foreground hover:bg-secondary hover:text-foreground"
          }`}
          title={subscribed ? "Notification on — click to turn off" : "Notify me when this resolves"}
          data-testid={`pick-upgrade-subscribe-${row?.pick_id}`}
          aria-pressed={subscribed}
        >
          {subscribed ? <Bell className="h-3.5 w-3.5" /> : <BellOff className="h-3.5 w-3.5" />}
        </button>
      )}
    </div>
  );
}

// ─── ConditionalTradeCard ────────────────────────────────────────────
export function ConditionalTradeCard({
  trade, mapped, viewMode, subscribedTradeIdxs, onToggleSubscribe,
}) {
  const upgrades = trade?.pick_upgrades_state || [];
  const hasAny = upgrades.length > 0;
  const triggeredCount = upgrades.filter((u) => u.state === "triggered").length;
  const pendingCount = upgrades.filter((u) => u.state === "pending").length;
  const failedCount = upgrades.filter((u) => u.state === "failed").length;
  return (
    <Card className="border-border/50" data-testid={`conditional-trade-${trade._id}`}>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div className="flex items-center gap-3">
            <GitBranch className="h-5 w-5 text-primary" />
            <CardTitle className="text-lg">
              <TeamLink name={mapped.teamA} />{" "}
              <span className="text-muted-foreground mx-1">↔</span>{" "}
              <TeamLink name={mapped.teamB} />
            </CardTitle>
          </div>
          <div className="flex items-center gap-2">
            <Badge variant="outline" className="border-emerald-500/50 text-emerald-400">
              <CheckCircle2 className="h-3 w-3 mr-1" />
              Executed
            </Badge>
            {triggeredCount > 0 && (
              <Badge variant="outline" className="border-emerald-500/50 text-emerald-400">
                <Zap className="h-3 w-3 mr-1" />
                {triggeredCount} triggered
              </Badge>
            )}
            {pendingCount > 0 && (
              <Badge variant="outline" className="border-amber-500/50 text-amber-400">
                <Clock className="h-3 w-3 mr-1" />
                {pendingCount} pending
              </Badge>
            )}
            {failedCount > 0 && (
              <Badge variant="outline" className="border-muted-foreground/50 text-muted-foreground">
                <MinusCircle className="h-3 w-3 mr-1" />
                {failedCount} did not trigger
              </Badge>
            )}
          </div>
        </div>
        <div className="flex items-center gap-4 text-xs text-muted-foreground mt-1">
          <span>
            Executed:{" "}
            {(trade.executed_at || trade.processed_at || "").slice(0, 16).replace("T", " ") || "—"}
          </span>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div>
            <p className="text-sm font-medium text-muted-foreground mb-2">
              <TeamLink name={mapped.teamA} /> sent:
            </p>
            <ConditionalAssetTable
              assets={mapped.assetsFromA}
              viewMode={viewMode}
              categories={mapped.scoringCategories}
            />
          </div>
          <div>
            <p className="text-sm font-medium text-muted-foreground mb-2">
              <TeamLink name={mapped.teamB} /> sent:
            </p>
            <ConditionalAssetTable
              assets={mapped.assetsFromB}
              viewMode={viewMode}
              categories={mapped.scoringCategories}
            />
          </div>
        </div>

        {hasAny && (
          <div
            className="rounded-lg border border-border bg-secondary/20 p-3 space-y-3"
            data-testid={`conditional-clauses-${trade._id}`}
          >
            <div className="space-y-2">
              <p className="text-[11px] uppercase tracking-wider text-muted-foreground font-semibold flex items-center gap-1.5">
                <GitBranch className="h-3.5 w-3.5" /> Conditional Pick Outcomes
              </p>
              {upgrades.map((row, idx) => {
                const subscribed = subscribedTradeIdxs.has(idx);
                return (
                  <PickUpgradeRow
                    key={idx}
                    row={row}
                    subscribed={subscribed}
                    onToggleSubscribe={() => onToggleSubscribe(trade._id, idx, subscribed)}
                  />
                );
              })}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
