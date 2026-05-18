// @ts-nocheck
import { useState, useEffect, useMemo } from "react";
import { AppLayout } from "@/components/layout/AppLayout";
import { useActiveLeague } from "@/hooks/use-active-league";
import api from "@/lib/api";
import LeagueContextBanner from "@/lovable/components/dashboard/LeagueContextBanner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ArrowRightLeft, ThumbsUp, ThumbsDown, Clock, CheckCircle2, XCircle, AlertTriangle, Activity, GitBranch, Zap, MinusCircle, Bell, BellOff } from "lucide-react";
import { toast } from "sonner";
import TeamLink from "@/lovable/components/TeamLink";

interface TradeAsset {
  name: string;
  position: string;
  age: number;
  capHit: string;
  goals: number;
  assists: number;
  points: number;
  fantasyPts: number;
  type: "player" | "pick";
}

interface PendingTrade {
  id: string;
  teamA: string;
  teamB: string;
  assetsFromA: TradeAsset[];
  assetsFromB: TradeAsset[];
  status: "pending" | "accepted" | "vetoed" | "processed";
  submittedAt: string;
  processesAt: string;
  votes: { approve: number; veto: number; total: number };
  salaryRetained?: { team: string; amount: string; duration: string };
  // iter 82: per-card vote state + handler so the buttons can highlight the
  // user's current choice and let them toggle.
  yourVote?: "approve" | "veto" | null;
  vetoThreshold?: number;
  onVote?: (vote: "approve" | "veto") => void;
}

const MOCK_TRADES: PendingTrade[] = [
  {
    id: "T-001",
    teamA: "Frost Giants",
    teamB: "Ice Wolves",
    assetsFromA: [
      { name: "Connor McDavid", position: "C", age: 29, capHit: "$12.5M", goals: 38, assists: 62, points: 100, fantasyPts: 412, type: "player" },
    ],
    assetsFromB: [
      { name: "Auston Matthews", position: "C", age: 28, capHit: "$13.25M", goals: 42, assists: 38, points: 80, fantasyPts: 368, type: "player" },
      { name: "2026 1st Round Pick", position: "—", age: 0, capHit: "—", goals: 0, assists: 0, points: 0, fantasyPts: 0, type: "pick" },
    ],
    status: "pending",
    submittedAt: "2026-02-20 14:30",
    processesAt: "2026-02-23 14:30",
    votes: { approve: 5, veto: 2, total: 12 },
  },
  {
    id: "T-002",
    teamA: "Northern Lights",
    teamB: "Blizzard",
    assetsFromA: [
      { name: "Cale Makar", position: "D", age: 27, capHit: "$9.0M", goals: 18, assists: 52, points: 70, fantasyPts: 310, type: "player" },
    ],
    assetsFromB: [
      { name: "Quinn Hughes", position: "D", age: 26, capHit: "$7.85M", goals: 12, assists: 58, points: 70, fantasyPts: 295, type: "player" },
      { name: "2027 2nd Round Pick", position: "—", age: 0, capHit: "—", goals: 0, assists: 0, points: 0, fantasyPts: 0, type: "pick" },
    ],
    status: "pending",
    submittedAt: "2026-02-21 09:15",
    processesAt: "2026-02-24 09:15",
    votes: { approve: 3, veto: 1, total: 12 },
    salaryRetained: { team: "Northern Lights", amount: "$1.5M", duration: "2 years" },
  },
  {
    id: "T-003",
    teamA: "Avalanche",
    teamB: "Storm Surge",
    assetsFromA: [
      { name: "Mikko Rantanen", position: "RW", age: 29, capHit: "$9.25M", goals: 30, assists: 35, points: 65, fantasyPts: 290, type: "player" },
    ],
    assetsFromB: [
      { name: "Tim Stützle", position: "C", age: 24, capHit: "$8.35M", goals: 28, assists: 42, points: 70, fantasyPts: 305, type: "player" },
    ],
    status: "accepted",
    submittedAt: "2026-02-18 11:00",
    processesAt: "2026-02-21 11:00",
    votes: { approve: 8, veto: 1, total: 12 },
  },
];

const statusConfig = {
  pending: { label: "Pending Review", icon: Clock, variant: "outline" as const, className: "border-amber-500/50 text-amber-400" },
  accepted: { label: "Accepted", icon: CheckCircle2, variant: "outline" as const, className: "border-emerald-500/50 text-emerald-400" },
  vetoed: { label: "Vetoed", icon: XCircle, variant: "destructive" as const, className: "" },
  processed: { label: "Processed", icon: CheckCircle2, variant: "outline" as const, className: "border-muted-foreground/50 text-muted-foreground" },
};

function TradeCard({ trade }: { trade: PendingTrade }) {
  const status = statusConfig[trade.status];
  const StatusIcon = status.icon;

  return (
    <Card className="border-border/50">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <ArrowRightLeft className="h-5 w-5 text-primary" />
            <CardTitle className="text-lg">
              <TeamLink name={trade.teamA} /> <span className="text-muted-foreground mx-1">↔</span> <TeamLink name={trade.teamB} />
            </CardTitle>
          </div>
          <div className="flex items-center gap-2">
            <Badge variant={status.variant} className={status.className}>
              <StatusIcon className="h-3 w-3 mr-1" />
              {status.label}
            </Badge>
          </div>
        </div>
        <div className="flex items-center gap-4 text-xs text-muted-foreground mt-1">
          <span>Submitted: {trade.submittedAt}</span>
          <span>Processes: {trade.processesAt}</span>
          <span>Votes: {trade.votes.approve} approve / {trade.votes.veto} veto of {trade.votes.total}</span>
        </div>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {/* Team A sends */}
          <div>
            <p className="text-sm font-medium text-muted-foreground mb-2"><TeamLink name={trade.teamA} /> sends:</p>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="text-xs">Player</TableHead>
                  <TableHead className="text-xs">Pos</TableHead>
                  <TableHead className="text-xs">Age</TableHead>
                  <TableHead className="text-xs">Cap Hit</TableHead>
                  <TableHead className="text-xs">G</TableHead>
                  <TableHead className="text-xs">A</TableHead>
                  <TableHead className="text-xs">P</TableHead>
                  <TableHead className="text-xs">FPts</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {trade.assetsFromA.map((asset) => (
                  <TableRow key={asset.name}>
                    <TableCell className="font-medium text-sm">
                      {asset.name}
                      {asset.type === "pick" && <Badge variant="secondary" className="ml-1 text-[10px]">Pick</Badge>}
                    </TableCell>
                    <TableCell className="text-sm">{asset.position}</TableCell>
                    <TableCell className="text-sm">{asset.type === "player" ? asset.age : "—"}</TableCell>
                    <TableCell className="text-sm">{asset.capHit}</TableCell>
                    <TableCell className="text-sm">{asset.type === "player" ? asset.goals : "—"}</TableCell>
                    <TableCell className="text-sm">{asset.type === "player" ? asset.assists : "—"}</TableCell>
                    <TableCell className="text-sm">{asset.type === "player" ? asset.points : "—"}</TableCell>
                    <TableCell className="text-sm font-semibold text-primary">{asset.type === "player" ? asset.fantasyPts : "—"}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>

          {/* Team B sends */}
          <div>
            <p className="text-sm font-medium text-muted-foreground mb-2"><TeamLink name={trade.teamB} /> sends:</p>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="text-xs">Player</TableHead>
                  <TableHead className="text-xs">Pos</TableHead>
                  <TableHead className="text-xs">Age</TableHead>
                  <TableHead className="text-xs">Cap Hit</TableHead>
                  <TableHead className="text-xs">G</TableHead>
                  <TableHead className="text-xs">A</TableHead>
                  <TableHead className="text-xs">P</TableHead>
                  <TableHead className="text-xs">FPts</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {trade.assetsFromB.map((asset) => (
                  <TableRow key={asset.name}>
                    <TableCell className="font-medium text-sm">
                      {asset.name}
                      {asset.type === "pick" && <Badge variant="secondary" className="ml-1 text-[10px]">Pick</Badge>}
                    </TableCell>
                    <TableCell className="text-sm">{asset.position}</TableCell>
                    <TableCell className="text-sm">{asset.type === "player" ? asset.age : "—"}</TableCell>
                    <TableCell className="text-sm">{asset.capHit}</TableCell>
                    <TableCell className="text-sm">{asset.type === "player" ? asset.goals : "—"}</TableCell>
                    <TableCell className="text-sm">{asset.type === "player" ? asset.assists : "—"}</TableCell>
                    <TableCell className="text-sm">{asset.type === "player" ? asset.points : "—"}</TableCell>
                    <TableCell className="text-sm font-semibold text-primary">{asset.type === "player" ? asset.fantasyPts : "—"}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </div>

        {trade.salaryRetained && (
          <div className="mt-3 flex items-center gap-2 text-xs">
            <AlertTriangle className="h-3.5 w-3.5 text-amber-400" />
            <span className="text-muted-foreground">
              Salary retained: <span className="text-foreground font-medium">{trade.salaryRetained.team}</span> retains{" "}
              <span className="text-foreground font-medium">{trade.salaryRetained.amount}</span> for{" "}
              <span className="text-foreground font-medium">{trade.salaryRetained.duration}</span>
            </span>
          </div>
        )}

        {trade.status === "pending" && (
          <div className="flex flex-col items-end gap-2 mt-4">
            <div className="text-xs text-muted-foreground">
              {trade.vetoThreshold ? (
                <>
                  {trade.votes.veto} / <span className="font-semibold">{trade.vetoThreshold}</span>{" "}
                  veto{trade.vetoThreshold === 1 ? "" : "s"} needed to block.
                </>
              ) : (
                <>Vetoes disabled — trade will process at the scheduled time.</>
              )}
            </div>
            <div className="flex gap-2 justify-end">
              <Button
                variant={trade.yourVote === "approve" ? "default" : "outline"}
                size="sm"
                className={
                  trade.yourVote === "approve"
                    ? "bg-emerald-500/30 text-emerald-300 border-emerald-500/50 hover:bg-emerald-500/40"
                    : "text-emerald-400 border-emerald-500/30 hover:bg-emerald-500/10"
                }
                onClick={() => trade.onVote?.("approve")}
                disabled={!trade.onVote}
                data-testid={`trade-vote-approve-${trade.id}`}
                title={trade.yourVote === "approve" ? "You voted Approve (click again to confirm/unchange)" : "Vote Approve"}
              >
                <ThumbsUp className="h-3.5 w-3.5 mr-1" /> Approve
                {trade.yourVote === "approve" && <span className="ml-1 text-[10px]">(your vote)</span>}
              </Button>
              <Button
                variant={trade.yourVote === "veto" ? "default" : "outline"}
                size="sm"
                className={
                  trade.yourVote === "veto"
                    ? "bg-destructive/40 text-destructive-foreground border-destructive hover:bg-destructive/50"
                    : "text-destructive border-destructive/30 hover:bg-destructive/10"
                }
                onClick={() => trade.onVote?.("veto")}
                disabled={!trade.onVote}
                data-testid={`trade-vote-veto-${trade.id}`}
                title={trade.yourVote === "veto" ? "You voted Veto (click Approve to switch)" : "Vote Veto"}
              >
                <ThumbsDown className="h-3.5 w-3.5 mr-1" /> Veto
                {trade.yourVote === "veto" && <span className="ml-1 text-[10px]">(your vote)</span>}
              </Button>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ─── Conditional Trade rendering ──────────────────────────────────────
// Maps backend metric keys → human-readable labels.
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

const OP_LABEL: Record<string, string> = {
  gte: "≥",
  lte: "≤",
  eq: "=",
};

function describeCondition(c: any): string {
  if (c?.description) return c.description;
  const m = METRIC_LABELS[c?.metric] || c?.metric || "metric";
  const op = OP_LABEL[c?.operator] || c?.operator || "";
  return `${m} ${op} ${c?.threshold}`;
}

function ConditionEvalRow({ row, subscribed, onToggleSubscribe }: { row: any; subscribed?: boolean; onToggleSubscribe?: () => void }) {
  const c = row?.condition || {};
  const met = !!row?.met;
  const showBell = !met && !!onToggleSubscribe;  // only on pending rows
  return (
    <div
      className={`flex items-start gap-2 rounded-md border px-3 py-2 ${
        met
          ? "border-emerald-500/30 bg-emerald-500/5"
          : "border-amber-500/30 bg-amber-500/5"
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
          Current: <span className="font-semibold text-foreground">
            {row?.actual_value != null ? Number(row.actual_value).toLocaleString(undefined, { maximumFractionDigits: 2 }) : "—"}
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
          title={subscribed ? "You'll be notified when this resolves. Click to stop." : "Notify me when this resolves"}
          data-testid={`condition-subscribe-${c.metric}-${c.threshold}`}
          aria-pressed={subscribed}
        >
          {subscribed ? <Bell className="h-3.5 w-3.5" /> : <BellOff className="h-3.5 w-3.5" />}
        </button>
      )}
    </div>
  );
}

function PickUpgradeRow({ row, subscribed, onToggleSubscribe }: { row: any; subscribed?: boolean; onToggleSubscribe?: () => void }) {
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
              · Current: <span className="font-semibold text-foreground">{Number(row.actual_value).toLocaleString(undefined, { maximumFractionDigits: 2 })}</span>
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

function ConditionalTradeCard({
  trade, mapped, subscribedTradeIdxs, onToggleSubscribe,
}: {
  trade: any;
  mapped: PendingTrade;
  /** Set of `pick_upgrade_idx` (-1 = whole-trade) the user has subscribed to. */
  subscribedTradeIdxs: Set<number>;
  onToggleSubscribe: (tradeId: string, pickUpgradeIdx: number, currentlySubscribed: boolean) => void;
}) {
  const conds = trade?.conditions_eval || [];
  const upgrades = trade?.pick_upgrades_state || [];
  const hasAny = conds.length > 0 || upgrades.length > 0;
  return (
    <Card className="border-border/50" data-testid={`conditional-trade-${trade._id}`}>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div className="flex items-center gap-3">
            <GitBranch className="h-5 w-5 text-primary" />
            <CardTitle className="text-lg">
              <TeamLink name={mapped.teamA} /> <span className="text-muted-foreground mx-1">↔</span> <TeamLink name={mapped.teamB} />
            </CardTitle>
          </div>
          <div className="flex items-center gap-2">
            <Badge variant="outline" className="border-emerald-500/50 text-emerald-400">
              <CheckCircle2 className="h-3 w-3 mr-1" />
              Executed
            </Badge>
            {conds.length > 0 && (
              <Badge variant="outline" className="border-primary/50 text-primary">
                {conds.length} trigger condition{conds.length === 1 ? "" : "s"}
              </Badge>
            )}
            {upgrades.length > 0 && (
              <Badge variant="outline" className="border-amber-500/50 text-amber-400">
                {upgrades.length} pick protection{upgrades.length === 1 ? "" : "s"}
              </Badge>
            )}
          </div>
        </div>
        <div className="flex items-center gap-4 text-xs text-muted-foreground mt-1">
          <span>Executed: {(trade.executed_at || trade.processed_at || "").slice(0, 16).replace("T", " ") || "—"}</span>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Trade assets — reuses the same layout block as TradeCard for consistency */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div>
            <p className="text-sm font-medium text-muted-foreground mb-2"><TeamLink name={mapped.teamA} /> sent:</p>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="text-xs">Player</TableHead>
                  <TableHead className="text-xs">Pos</TableHead>
                  <TableHead className="text-xs">Cap</TableHead>
                  <TableHead className="text-xs">G</TableHead>
                  <TableHead className="text-xs">A</TableHead>
                  <TableHead className="text-xs">P</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {mapped.assetsFromA.map((a) => (
                  <TableRow key={a.name}>
                    <TableCell className="font-medium text-sm">
                      {a.name}
                      {a.type === "pick" && <Badge variant="secondary" className="ml-1 text-[10px]">Pick</Badge>}
                    </TableCell>
                    <TableCell className="text-sm">{a.position}</TableCell>
                    <TableCell className="text-sm">{a.capHit}</TableCell>
                    <TableCell className="text-sm">{a.type === "player" ? a.goals : "—"}</TableCell>
                    <TableCell className="text-sm">{a.type === "player" ? a.assists : "—"}</TableCell>
                    <TableCell className="text-sm">{a.type === "player" ? a.points : "—"}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
          <div>
            <p className="text-sm font-medium text-muted-foreground mb-2"><TeamLink name={mapped.teamB} /> sent:</p>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="text-xs">Player</TableHead>
                  <TableHead className="text-xs">Pos</TableHead>
                  <TableHead className="text-xs">Cap</TableHead>
                  <TableHead className="text-xs">G</TableHead>
                  <TableHead className="text-xs">A</TableHead>
                  <TableHead className="text-xs">P</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {mapped.assetsFromB.map((a) => (
                  <TableRow key={a.name}>
                    <TableCell className="font-medium text-sm">
                      {a.name}
                      {a.type === "pick" && <Badge variant="secondary" className="ml-1 text-[10px]">Pick</Badge>}
                    </TableCell>
                    <TableCell className="text-sm">{a.position}</TableCell>
                    <TableCell className="text-sm">{a.capHit}</TableCell>
                    <TableCell className="text-sm">{a.type === "player" ? a.goals : "—"}</TableCell>
                    <TableCell className="text-sm">{a.type === "player" ? a.assists : "—"}</TableCell>
                    <TableCell className="text-sm">{a.type === "player" ? a.points : "—"}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </div>

        {/* Conditions + Pick upgrades block */}
        {hasAny && (
          <div className="rounded-lg border border-border bg-secondary/20 p-3 space-y-3" data-testid={`conditional-clauses-${trade._id}`}>
            {conds.length > 0 && (
              <div className="space-y-2">
                <p className="text-[11px] uppercase tracking-wider text-muted-foreground font-semibold flex items-center gap-1.5">
                  <Zap className="h-3.5 w-3.5" /> Trigger Conditions
                </p>
                {conds.map((row: any, idx: number) => {
                  // Whole-trade triggers share a single subscription bucket (idx = -1)
                  const subscribed = subscribedTradeIdxs.has(-1);
                  return (
                    <ConditionEvalRow
                      key={idx}
                      row={row}
                      subscribed={subscribed}
                      onToggleSubscribe={() => onToggleSubscribe(trade._id, -1, subscribed)}
                    />
                  );
                })}
              </div>
            )}
            {upgrades.length > 0 && (
              <div className="space-y-2">
                <p className="text-[11px] uppercase tracking-wider text-muted-foreground font-semibold flex items-center gap-1.5">
                  <GitBranch className="h-3.5 w-3.5" /> Pick Protections / Upgrades
                </p>
                {upgrades.map((row: any, idx: number) => {
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
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

const Transactions = () => {
  const { league, leagueTeams } = useActiveLeague();
  const leagueTeamsCount = leagueTeams?.length || 0;

  const [tab, setTab] = useState("pending");
  const [trades, setTrades] = useState<any[]>([]);
  const [activity, setActivity] = useState<any[]>([]);
  // Per-trade vote payload: { [tradeId]: { yourVote, threshold, votes } }
  const [voteState, setVoteState] = useState<Record<string, any>>({});
  const [reloadTick, setReloadTick] = useState(0);
  // Conditional / pick-protection trades — populated only when the user
  // opens the Conditional tab (avoids extra work on first paint).
  const [conditionalTrades, setConditionalTrades] = useState<any[] | null>(null);
  const [conditionalLoading, setConditionalLoading] = useState(false);
  // Map trade_id → Set of subscribed pick_upgrade_idx (-1 = whole-trade)
  const [subsByTrade, setSubsByTrade] = useState<Record<string, Set<number>>>({});

  useEffect(() => {
    if (!league?.id) return;
    let cancelled = false;
    api.get(`/trades?league_id=${league.id}`)
      .then(({ data }) => { if (!cancelled) setTrades(Array.isArray(data) ? data : (data?.items || [])); })
      .catch(() => {});
    api.get(`/activity/${league.id}?limit=100`)
      .then(({ data }) => { if (!cancelled) setActivity(data?.items || []); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [league?.id, reloadTick]);

  // Conditional trades — fetched lazily on tab open + every reload tick.
  useEffect(() => {
    if (tab !== "conditional" || !league?.id) return;
    let cancelled = false;
    setConditionalLoading(true);
    Promise.all([
      api.get(`/trades/conditional?league_id=${league.id}`).catch(() => ({ data: { trades: [] } })),
      api.get(`/trades/conditional/subscriptions?league_id=${league.id}`).catch(() => ({ data: { subscriptions: [] } })),
    ]).then(([tradesRes, subsRes]) => {
      if (cancelled) return;
      setConditionalTrades(tradesRes.data?.trades || []);
      const map: Record<string, Set<number>> = {};
      for (const s of (subsRes.data?.subscriptions || [])) {
        const tid = s.trade_id;
        const idx = typeof s.pick_upgrade_idx === "number" ? s.pick_upgrade_idx : -1;
        if (!map[tid]) map[tid] = new Set();
        map[tid].add(idx);
      }
      setSubsByTrade(map);
    }).finally(() => { if (!cancelled) setConditionalLoading(false); });
    return () => { cancelled = true; };
  }, [tab, league?.id, reloadTick]);

  const toggleConditionalSubscription = async (
    tradeId: string, pickUpgradeIdx: number, currentlySubscribed: boolean,
  ) => {
    const action = currentlySubscribed ? "unsubscribe" : "subscribe";
    try {
      await api.post(`/trades/conditional/${tradeId}/subscribe`, {
        pick_upgrade_idx: pickUpgradeIdx,
        action,
      });
      setSubsByTrade((prev) => {
        const next = { ...prev };
        const set = new Set(next[tradeId] || []);
        if (currentlySubscribed) set.delete(pickUpgradeIdx);
        else set.add(pickUpgradeIdx);
        next[tradeId] = set;
        return next;
      });
      toast.success(
        currentlySubscribed
          ? "Notifications off for this trigger"
          : "You'll get a notification in the top bell when this resolves",
      );
    } catch (e: any) {
      toast.error("Couldn't update subscription", {
        description: e?.response?.data?.detail || e?.message,
      });
    }
  };

  // Pull live vote details once we know which pending trades exist
  useEffect(() => {
    if (!Array.isArray(trades) || trades.length === 0) return;
    const pendingIds = trades
      .filter((t: any) => (t.status || "pending") === "pending")
      .map((t: any) => t._id || t.id);
    let cancelled = false;
    Promise.all(pendingIds.map((id: string) =>
      api.get(`/trades/${id}/votes`).then(r => [id, r.data] as const).catch(() => [id, null] as const),
    )).then((rows) => {
      if (cancelled) return;
      const map: Record<string, any> = {};
      for (const [id, data] of rows) if (data) map[id] = data;
      setVoteState(map);
    });
    return () => { cancelled = true; };
  }, [trades]);

  const castVote = async (tradeId: string, vote: "approve" | "veto") => {
    try {
      const { data } = await api.post(`/trades/${tradeId}/vote`, { vote });
      // Optimistically update the local cache; reload tick refetches if the
      // trade auto-vetoed (status changed).
      setVoteState((prev) => ({
        ...prev,
        [tradeId]: {
          ...(prev[tradeId] || {}),
          your_vote: data.your_vote ?? vote,
          votes: data.votes,
          veto_threshold: data.veto_threshold,
        },
      }));
      if (data.status === "vetoed") setReloadTick((t) => t + 1);
    } catch (e: any) {
      // surface via console; existing toast infra hooks up at a higher level
      // eslint-disable-next-line no-console
      console.warn("vote failed", e?.response?.data?.detail || e?.message);
    }
  };

  // Map backend trades to the TradeCard shape and drop empties (no assets on
  // EITHER side). Cleans up the historic "ghost trade" rows that appeared
  // when proposals were accidentally submitted blank.
  const teamName = (tid: string) => (leagueTeams || []).find(t => t.id === tid)?.name || tid;
  const allTrades: PendingTrade[] = useMemo(() => {
    const mapped = (trades || []).map((t: any) => {
      const tradeId = t._id || t.id;
      // Backend canonical fields: assets_offered / assets_requested + proposer/target ids
      const fromAssets = t.assets_offered || t.from_assets || t.team_a_assets || [];
      const toAssets = t.assets_requested || t.to_assets || t.team_b_assets || [];
      return {
        id: tradeId,
        teamA: teamName(t.proposer_team_id || t.from_team_id || t.team_a_id),
        teamB: teamName(t.target_team_id || t.to_team_id || t.team_b_id),
        assetsFromA: fromAssets.map((a: any) => ({
          name: a.player_name || a.name || (a.asset_type === "pick" ? `${a.pick_year || ""} ${a.pick_round || ""} Pick` : "Unknown"),
          position: a.position || "—",
          age: a.age || 0,
          capHit: a.salary ? `$${(a.salary / 1000000).toFixed(1)}M` : "—",
          goals: a.goals || 0,
          assists: a.assists || 0,
          points: a.points || 0,
          fantasyPts: a.fantasy_points || 0,
          type: (a.asset_type === "pick" || a.item_type === "pick" ? "pick" : "player") as "player" | "pick",
        })),
        assetsFromB: toAssets.map((a: any) => ({
          name: a.player_name || a.name || (a.asset_type === "pick" ? `${a.pick_year || ""} ${a.pick_round || ""} Pick` : "Unknown"),
          position: a.position || "—",
          age: a.age || 0,
          capHit: a.salary ? `$${(a.salary / 1000000).toFixed(1)}M` : "—",
          goals: a.goals || 0,
          assists: a.assists || 0,
          points: a.points || 0,
          fantasyPts: a.fantasy_points || 0,
          type: (a.asset_type === "pick" || a.item_type === "pick" ? "pick" : "player") as "player" | "pick",
        })),
        status: (t.status || "pending") as any,
        submittedAt: (t.created_at || "").slice(0, 16).replace("T", " "),
        processesAt: (t.expires_at || t.processes_at || "").slice(0, 16).replace("T", " "),
        votes: {
          approve: voteState[tradeId]?.votes?.approve ?? (t.votes?.approve || 0),
          veto: voteState[tradeId]?.votes?.veto ?? (t.votes?.veto || 0),
          total: leagueTeamsCount,
        },
        yourVote: voteState[tradeId]?.your_vote || null,
        vetoThreshold: voteState[tradeId]?.veto_threshold?.teams_required ?? 0,
        onVote: (vote: "approve" | "veto") => castVote(tradeId, vote),
      };
    });
    // Drop empty trades — neither side has any asset (corrupted seeds /
    // legacy bug). A real trade must move at least one player or pick.
    const nonEmpty = mapped.filter(
      (t) => (t.assetsFromA?.length || 0) > 0 || (t.assetsFromB?.length || 0) > 0,
    );
    // Drop ghost trades — neither team resolved to a real name.
    const hasTeams = nonEmpty.filter(
      (t) => t.teamA && t.teamB && t.teamA !== t.teamB,
    );
    return hasTeams;
  }, [trades, leagueTeams, leagueTeamsCount, voteState]);

  const pending = allTrades.filter((t) => t.status === "pending");
  const accepted = allTrades.filter((t) => t.status === "accepted");
  const all = allTrades;

  return (
    <AppLayout>
        <div className="container py-8">
          <LeagueContextBanner title="Transactions" kpiLabel="Trades this season" kpiValue={all.length} primaryHref="/trade-block" primaryLabel="Open Trade Block" />
        <div className="mb-6 animate-fade-in">
          <h1 className="text-3xl font-bold mb-2">Transactions</h1>
          <p className="text-muted-foreground">Review pending and accepted trades, plus league activity. Cast your vote to approve or veto.</p>
        </div>

        <Tabs value={tab} onValueChange={setTab}>
          <TabsList className="mb-6">
            <TabsTrigger value="pending" data-testid="transactions-tab-pending">
              Pending
              {pending.length > 0 && (
                <Badge variant="secondary" className="ml-2 text-xs">{pending.length}</Badge>
              )}
            </TabsTrigger>
            <TabsTrigger value="accepted" data-testid="transactions-tab-accepted">
              Accepted
              {accepted.length > 0 && (
                <Badge variant="secondary" className="ml-2 text-xs">{accepted.length}</Badge>
              )}
            </TabsTrigger>
            <TabsTrigger value="all" data-testid="transactions-tab-all">All</TabsTrigger>
            <TabsTrigger value="conditional" data-testid="transactions-tab-conditional">
              Conditional
              {conditionalTrades && conditionalTrades.length > 0 && (
                <Badge variant="secondary" className="ml-2 text-xs">{conditionalTrades.length}</Badge>
              )}
            </TabsTrigger>
            <TabsTrigger value="activity" data-testid="transactions-tab-activity">
              Activity
              {activity.length > 0 && (
                <Badge variant="secondary" className="ml-2 text-xs">{activity.length}</Badge>
              )}
            </TabsTrigger>
          </TabsList>

          <TabsContent value="pending" className="space-y-4">
            {pending.length === 0 ? (
              <Card><CardContent className="py-8 text-center text-muted-foreground">No pending trades.</CardContent></Card>
            ) : pending.map((t) => <TradeCard key={t.id} trade={t} />)}
          </TabsContent>

          <TabsContent value="accepted" className="space-y-4">
            {accepted.length === 0 ? (
              <Card><CardContent className="py-8 text-center text-muted-foreground">No accepted trades awaiting processing.</CardContent></Card>
            ) : accepted.map((t) => <TradeCard key={t.id} trade={t} />)}
          </TabsContent>

          <TabsContent value="all" className="space-y-4">
            {all.length === 0 ? (
              <Card><CardContent className="py-8 text-center text-muted-foreground">No trades yet in this league. When managers propose trades they'll appear here.</CardContent></Card>
            ) : all.map((t) => <TradeCard key={t.id} trade={t} />)}
          </TabsContent>

          <TabsContent value="conditional" className="space-y-4" data-testid="transactions-conditional-content">
            {conditionalLoading && conditionalTrades === null ? (
              <Card><CardContent className="py-8 text-center text-muted-foreground">Loading conditional trades…</CardContent></Card>
            ) : (conditionalTrades || []).length === 0 ? (
              <Card>
                <CardContent className="py-8 text-center text-muted-foreground" data-testid="conditional-empty">
                  No executed trades with conditions or pick protections yet.
                  <span className="block text-xs mt-2">
                    Conditional trades appear here once they've been accepted and processed.
                  </span>
                </CardContent>
              </Card>
            ) : (
              (conditionalTrades || []).map((t: any) => {
                // Reuse the mapper used by the other tabs so the asset rows are
                // formatted consistently with the rest of the page.
                const tradeId = t._id || t.id;
                const fromAssets = t.assets_offered || t.from_assets || t.team_a_assets || [];
                const toAssets = t.assets_requested || t.to_assets || t.team_b_assets || [];
                const mapAsset = (a: any): TradeAsset => ({
                  name: a.player_name || a.name || (a.asset_type === "pick" ? `${a.pick_year || ""} ${a.pick_round ? "R" + a.pick_round : ""} Pick` : "Unknown"),
                  position: a.position || "—",
                  age: a.age || 0,
                  capHit: a.salary ? `$${(a.salary / 1000000).toFixed(1)}M` : "—",
                  goals: a.goals || 0,
                  assists: a.assists || 0,
                  points: a.points || 0,
                  fantasyPts: a.fantasy_points || 0,
                  type: (a.asset_type === "pick" || a.item_type === "pick" ? "pick" : "player"),
                });
                const mapped: PendingTrade = {
                  id: tradeId,
                  teamA: teamName(t.proposer_team_id || t.from_team_id || t.team_a_id),
                  teamB: teamName(t.target_team_id || t.to_team_id || t.team_b_id),
                  assetsFromA: fromAssets.map(mapAsset),
                  assetsFromB: toAssets.map(mapAsset),
                  status: "accepted",
                  submittedAt: "",
                  processesAt: "",
                  votes: { approve: 0, veto: 0, total: 0 },
                };
                return <ConditionalTradeCard
                  key={tradeId}
                  trade={t}
                  mapped={mapped}
                  subscribedTradeIdxs={subsByTrade[tradeId] || new Set<number>()}
                  onToggleSubscribe={toggleConditionalSubscription}
                />;
              })
            )}
          </TabsContent>

          <TabsContent value="activity" className="space-y-2">
            {activity.length === 0 ? (
              <Card><CardContent className="py-8 text-center text-muted-foreground">No recent activity.</CardContent></Card>
            ) : (
              <Card className="bg-card border-border">
                <CardContent className="p-0">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead className="w-32">Event</TableHead>
                        <TableHead>Detail</TableHead>
                        <TableHead className="w-48 text-right">When</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {activity.map((a: any) => (
                        <TableRow key={a._id} data-testid={`activity-row-${a._id}`}>
                          <TableCell>
                            <Badge variant="outline" className="capitalize text-xs">
                              <Activity className="h-3 w-3 mr-1" />
                              {(a.event_type || "event").replace(/_/g, " ")}
                            </Badge>
                          </TableCell>
                          <TableCell className="text-sm">{a.description || a.message || ""}</TableCell>
                          <TableCell className="text-right text-xs text-muted-foreground">
                            {(a.created_at || "").slice(0, 16).replace("T", " ")}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </CardContent>
              </Card>
            )}
          </TabsContent>
        </Tabs>
      </div>
    </AppLayout>
  );
};

export default Transactions;
