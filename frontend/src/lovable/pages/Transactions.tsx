// @ts-nocheck
import { useState, useEffect, useMemo } from "react";
import { AppLayout } from "@/components/layout/AppLayout";
import { useActiveLeague } from "@/hooks/use-active-league";
import api from "@/lib/api";
import LeagueContextBanner from "@/lovable/components/dashboard/LeagueContextBanner";
import { MinorEligibleBadge } from "@/lovable/components/MinorEligibleBadge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ArrowRightLeft, ThumbsUp, ThumbsDown, Clock, CheckCircle2, XCircle, AlertTriangle, Activity, GitBranch, Zap, MinusCircle, Bell, BellOff, Filter, X } from "lucide-react";
import { toast } from "sonner";
import TeamLink from "@/lovable/components/TeamLink";

interface StatCategory {
  label: string;
  value: number;
}

interface TradeAsset {
  name: string;
  position: string;
  age: number;
  capHit: string;
  goals: number;
  assists: number;
  points: number;
  fantasyPts: number;
  // Iter 232L — per-game FPts + full category breakdown so the
  // Transactions page can toggle between FPts summary and league
  // counting categories.
  fantasyPtsPerGame?: number;
  gamesPlayed?: number;
  statCategories?: Record<string, StatCategory>;
  playerType?: string;
  type: "player" | "pick";
  // Iter 181 — surface minor-eligibility in the transactions feed.
  minorEligible?: boolean;
}

interface ScoringCategoryDef {
  key: string;
  label: string;
}
interface ScoringCategoriesMap {
  skater: ScoringCategoryDef[];
  goalie: ScoringCategoryDef[];
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
  // Iter 232L — league scoring categories used for the Categories view.
  scoringCategories?: ScoringCategoriesMap;
}

// Iter 232L — view mode for the trade cards. Default `fpts` shows season
// FPts + per-game average. `categories` shows the league's counting stats
// dynamically based on the league scoring config.
type StatViewMode = "fpts" | "categories";

// Format a cap hit as either "$X.XM" for millions, "$XXXk" for thousands,
// or "—" when unknown/zero.
function fmtCapHit(salary: number | undefined | null): string {
  if (!salary || salary <= 0) return "—";
  if (salary >= 1_000_000) return `$${(salary / 1_000_000).toFixed(2)}M`;
  if (salary >= 1_000) return `$${Math.round(salary / 1_000)}k`;
  return `$${salary}`;
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

const statusConfig: Record<string, { label: string; icon: any; variant: "outline" | "destructive"; className: string }> = {
  pending: { label: "Pending Review", icon: Clock, variant: "outline" as const, className: "border-amber-500/50 text-amber-400" },
  accepted: { label: "Accepted", icon: CheckCircle2, variant: "outline" as const, className: "border-emerald-500/50 text-emerald-400" },
  vetoed: { label: "Vetoed", icon: XCircle, variant: "destructive" as const, className: "" },
  processed: { label: "Processed", icon: CheckCircle2, variant: "outline" as const, className: "border-muted-foreground/50 text-muted-foreground" },
  // Iter 168 — backend canonical statuses returned by /api/leagues/{id}/trades
  executed: { label: "Executed", icon: CheckCircle2, variant: "outline" as const, className: "border-emerald-500/50 text-emerald-400" },
  voting: { label: "Voting", icon: Clock, variant: "outline" as const, className: "border-amber-500/50 text-amber-400" },
  conditional: { label: "Conditional", icon: GitBranch, variant: "outline" as const, className: "border-sky-500/50 text-sky-400" },
  withdrawn: { label: "Withdrawn", icon: MinusCircle, variant: "outline" as const, className: "border-muted-foreground/50 text-muted-foreground" },
  rejected: { label: "Rejected", icon: XCircle, variant: "destructive" as const, className: "" },
};

function TradeCard({ trade, viewMode }: { trade: PendingTrade; viewMode: StatViewMode }) {
  // Iter 168 — fall back to "pending" config when backend returns an
  // unknown status so unknown statuses don't crash the page.
  const status = statusConfig[trade.status] || statusConfig.pending;
  const StatusIcon = status.icon;

  // Iter 232L — Derive the counting-category column set from the trade's
  // league scoring config. In Categories mode we show up to 6 columns; in
  // FPts mode we show FPts (season) + FPts/G.
  const skaterCats = trade.scoringCategories?.skater || [];
  const goalieCats = trade.scoringCategories?.goalie || [];
  // Prefer the position mix on this card — if any goalie is involved we
  // add goalie cats after skater cats so both rows render meaningfully.
  const hasGoalie = [...trade.assetsFromA, ...trade.assetsFromB].some(
    (a) => a.type === "player" && (a.playerType === "goalie" || a.position === "G"),
  );
  const hasSkater = [...trade.assetsFromA, ...trade.assetsFromB].some(
    (a) => a.type === "player" && a.playerType !== "goalie" && a.position !== "G",
  );
  const categoriesToShow: ScoringCategoryDef[] = viewMode === "categories"
    ? [
        ...(hasSkater ? skaterCats : []),
        ...(hasGoalie ? goalieCats : []),
      ].slice(0, 8)
    : [];

  const renderAssetTable = (assets: TradeAsset[]) => (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead className="text-xs">Player</TableHead>
          <TableHead className="text-xs">Pos</TableHead>
          <TableHead className="text-xs">Age</TableHead>
          <TableHead className="text-xs">Cap Hit</TableHead>
          {viewMode === "fpts" ? (
            <>
              <TableHead className="text-xs">GP</TableHead>
              <TableHead className="text-xs">FPts</TableHead>
              <TableHead className="text-xs">FP/G</TableHead>
            </>
          ) : (
            categoriesToShow.map((c) => (
              <TableHead key={c.key} className="text-xs" title={c.key}>{c.label}</TableHead>
            ))
          )}
        </TableRow>
      </TableHeader>
      <TableBody>
        {assets.map((asset) => (
          <TableRow key={asset.name}>
            <TableCell className="font-medium text-sm">
              <span className="inline-flex items-center gap-1.5">
                {asset.name}
                <MinorEligibleBadge eligible={asset.type === "player" && asset.minorEligible} />
              </span>
              {asset.type === "pick" && <Badge variant="secondary" className="ml-1 text-[10px]">Pick</Badge>}
            </TableCell>
            <TableCell className="text-sm">{asset.position}</TableCell>
            <TableCell className="text-sm">{asset.type === "player" ? (asset.age || "—") : "—"}</TableCell>
            <TableCell className="text-sm">{asset.capHit}</TableCell>
            {viewMode === "fpts" ? (
              <>
                <TableCell className="text-sm">{asset.type === "player" ? (asset.gamesPlayed ?? 0) : "—"}</TableCell>
                <TableCell className="text-sm font-semibold text-primary">
                  {asset.type === "player" ? asset.fantasyPts : "—"}
                </TableCell>
                <TableCell className="text-sm text-primary/80">
                  {asset.type === "player" ? (asset.fantasyPtsPerGame ?? 0).toFixed(2) : "—"}
                </TableCell>
              </>
            ) : (
              categoriesToShow.map((c) => (
                <TableCell key={c.key} className="text-sm">
                  {asset.type === "player" ? (asset.statCategories?.[c.key]?.value ?? 0) : "—"}
                </TableCell>
              ))
            )}
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );

  return (
    <Card className="border-border/50" data-testid={`trade-card-${trade.id}`}>
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
            {renderAssetTable(trade.assetsFromA)}
          </div>

          {/* Team B sends */}
          <div>
            <p className="text-sm font-medium text-muted-foreground mb-2"><TeamLink name={trade.teamB} /> sends:</p>
            {renderAssetTable(trade.assetsFromB)}
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

function ConditionalAssetTable({
  assets, viewMode, categories,
}: {
  assets: TradeAsset[];
  viewMode: StatViewMode;
  categories?: ScoringCategoriesMap;
}) {
  const hasGoalie = assets.some((a) => a.type === "player" && (a.playerType === "goalie" || a.position === "G"));
  const hasSkater = assets.some((a) => a.type === "player" && a.playerType !== "goalie" && a.position !== "G");
  const catsToShow: ScoringCategoryDef[] = viewMode === "categories"
    ? [
        ...(hasSkater ? (categories?.skater || []) : []),
        ...(hasGoalie ? (categories?.goalie || []) : []),
      ].slice(0, 8)
    : [];
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead className="text-xs">Player</TableHead>
          <TableHead className="text-xs">Pos</TableHead>
          <TableHead className="text-xs">Cap</TableHead>
          {viewMode === "fpts" ? (
            <>
              <TableHead className="text-xs">FPts</TableHead>
              <TableHead className="text-xs">FP/G</TableHead>
            </>
          ) : (
            catsToShow.map((c) => (
              <TableHead key={c.key} className="text-xs" title={c.key}>{c.label}</TableHead>
            ))
          )}
        </TableRow>
      </TableHeader>
      <TableBody>
        {assets.map((a) => (
          <TableRow key={a.name}>
            <TableCell className="font-medium text-sm">
              {a.name}
              {a.type === "pick" && <Badge variant="secondary" className="ml-1 text-[10px]">Pick</Badge>}
            </TableCell>
            <TableCell className="text-sm">{a.position}</TableCell>
            <TableCell className="text-sm">{a.capHit}</TableCell>
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
                  {a.type === "player" ? (a.statCategories?.[c.key]?.value ?? 0) : "—"}
                </TableCell>
              ))
            )}
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

function ConditionalTradeCard({
  trade, mapped, viewMode, subscribedTradeIdxs, onToggleSubscribe,
}: {
  trade: any;
  mapped: PendingTrade;
  viewMode: StatViewMode;
  /** Set of `pick_upgrade_idx` the user has subscribed to. */
  subscribedTradeIdxs: Set<number>;
  onToggleSubscribe: (tradeId: string, pickUpgradeIdx: number, currentlySubscribed: boolean) => void;
}) {
  const upgrades = trade?.pick_upgrades_state || [];
  const hasAny = upgrades.length > 0;
  // Aggregate state counts for the header badges
  const triggeredCount = upgrades.filter((u: any) => u.state === "triggered").length;
  const pendingCount = upgrades.filter((u: any) => u.state === "pending").length;
  const failedCount = upgrades.filter((u: any) => u.state === "failed").length;
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
          <span>Executed: {(trade.executed_at || trade.processed_at || "").slice(0, 16).replace("T", " ") || "—"}</span>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Trade assets — reuses the same layout block as TradeCard for consistency */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div>
            <p className="text-sm font-medium text-muted-foreground mb-2"><TeamLink name={mapped.teamA} /> sent:</p>
            <ConditionalAssetTable assets={mapped.assetsFromA} viewMode={viewMode} categories={mapped.scoringCategories} />
          </div>
          <div>
            <p className="text-sm font-medium text-muted-foreground mb-2"><TeamLink name={mapped.teamB} /> sent:</p>
            <ConditionalAssetTable assets={mapped.assetsFromB} viewMode={viewMode} categories={mapped.scoringCategories} />
          </div>
        </div>

        {/* Conditional clauses — every clause is of the form
            (condition on player/team metric) → (draft pick outcome). */}
        {hasAny && (
          <div className="rounded-lg border border-border bg-secondary/20 p-3 space-y-3" data-testid={`conditional-clauses-${trade._id}`}>
            <div className="space-y-2">
              <p className="text-[11px] uppercase tracking-wider text-muted-foreground font-semibold flex items-center gap-1.5">
                <GitBranch className="h-3.5 w-3.5" /> Conditional Pick Outcomes
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
  // Iter 232L — Stat view toggle: FPts (season + per-game) vs
  // Categories (dynamic per-league counting stats). Applies to the
  // whole page (all tabs) so managers can compare trades consistently.
  const [viewMode, setViewMode] = useState<StatViewMode>(() => {
    try {
      const stored = window.localStorage.getItem("transactions.viewMode");
      return stored === "categories" ? "categories" : "fpts";
    } catch { return "fpts"; }
  });
  useEffect(() => {
    try { window.localStorage.setItem("transactions.viewMode", viewMode); } catch {
      /* ignore storage errors */
    }
  }, [viewMode]);
  const [trades, setTrades] = useState<any[]>([]);
  const [activity, setActivity] = useState<any[]>([]);
  // Per-trade vote payload: { [tradeId]: { yourVote, threshold, votes } }
  const [voteState, setVoteState] = useState<Record<string, any>>({});
  const [reloadTick, setReloadTick] = useState(0);
  // Iter 170c — filter state. Multi-select team chips + date-range.
  // Both filters apply to the All / Pending / Accepted tabs (Conditional
  // and Activity tabs are independent).
  const [selectedTeamIds, setSelectedTeamIds] = useState<Set<string>>(new Set());
  const [dateFrom, setDateFrom] = useState<string>("");
  const [dateTo, setDateTo] = useState<string>("");
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
  // Keep the raw proposer/target team ids alongside the mapped TradeCard
  // shape so the team-chip filter can match by stable id (not display name).
  const mapAssetRow = (a: any): TradeAsset => {
    const isPick = a.asset_type === "pick" || a.item_type === "pick";
    const salary = typeof a.salary === "number" ? a.salary : (typeof a.cap_hit === "number" ? a.cap_hit : 0);
    return {
      name: a.player_name || a.name || (isPick ? `${a.pick_year || ""} ${a.pick_round ? "R" + a.pick_round : ""} Pick`.trim() : "Unknown"),
      position: a.position || "—",
      age: a.age || 0,
      capHit: isPick ? "—" : fmtCapHit(salary),
      goals: a.goals || 0,
      assists: a.assists || 0,
      points: a.points || 0,
      fantasyPts: a.fantasy_points || 0,
      fantasyPtsPerGame: a.fantasy_points_per_game || 0,
      gamesPlayed: a.games_played || 0,
      statCategories: a.stat_categories || {},
      playerType: a.player_type || "skater",
      type: (isPick ? "pick" : "player") as "player" | "pick",
      minorEligible: !!a.minor_eligible || a.player_type === "prospect",
    };
  };
  const mappedWithIds = useMemo(() => {
    return (trades || []).map((t: any) => {
      const tradeId = t._id || t.id;
      const fromAssets = t.assets_offered || t.from_assets || t.team_a_assets || [];
      const toAssets = t.assets_requested || t.to_assets || t.team_b_assets || [];
      const proposerId = t.proposer_team_id || t.from_team_id || t.team_a_id;
      const targetId = t.target_team_id || t.to_team_id || t.team_b_id;
      const createdAt = t.created_at || t.executed_at || t.submitted_at || "";
      // Iter 231h — Normalize the backend `proposed` status (waiting on
      // recipient) into `pending` for display so the review card renders
      // the same badge and vote controls.
      const rawStatus = t.status || "pending";
      const status = rawStatus === "proposed" ? "pending" : rawStatus;
      return {
        _proposerId: proposerId,
        _targetId: targetId,
        _createdAt: createdAt,
        card: {
          id: tradeId,
          teamA: teamName(proposerId),
          teamB: teamName(targetId),
          assetsFromA: fromAssets.map(mapAssetRow),
          assetsFromB: toAssets.map(mapAssetRow),
          status: status as any,
          submittedAt: (createdAt || "").slice(0, 16).replace("T", " "),
          processesAt: (t.expires_at || t.processes_at || "").slice(0, 16).replace("T", " "),
          votes: {
            approve: voteState[tradeId]?.votes?.approve ?? (t.votes?.approve || 0),
            veto: voteState[tradeId]?.votes?.veto ?? (t.votes?.veto || 0),
            total: leagueTeamsCount,
          },
          yourVote: voteState[tradeId]?.your_vote || null,
          vetoThreshold: voteState[tradeId]?.veto_threshold?.teams_required ?? 0,
          onVote: (vote: "approve" | "veto") => castVote(tradeId, vote),
          scoringCategories: t.scoring_categories,
        } as PendingTrade,
      };
    });
  }, [trades, leagueTeams, leagueTeamsCount, voteState]);

  const allTrades: PendingTrade[] = useMemo(() => {
    // Drop empty trades — neither side has any asset (corrupted seeds /
    // legacy bug). Then drop ghost trades — neither team resolved to a
    // real name.
    let rows = mappedWithIds.filter(
      ({ card }) =>
        ((card.assetsFromA?.length || 0) > 0 || (card.assetsFromB?.length || 0) > 0) &&
        card.teamA && card.teamB && card.teamA !== card.teamB,
    );
    // Iter 170c — team chip filter (match either side of the trade).
    if (selectedTeamIds.size > 0) {
      rows = rows.filter(
        ({ _proposerId, _targetId }) =>
          (_proposerId && selectedTeamIds.has(_proposerId)) ||
          (_targetId && selectedTeamIds.has(_targetId)),
      );
    }
    // Iter 170c — date range filter (inclusive, on yyyy-mm-dd prefix of
    // created_at). Empty bound = no constraint on that side.
    if (dateFrom || dateTo) {
      rows = rows.filter(({ _createdAt }) => {
        const day = (_createdAt || "").slice(0, 10);
        if (!day) return false;
        if (dateFrom && day < dateFrom) return false;
        if (dateTo && day > dateTo) return false;
        return true;
      });
    }
    return rows.map(({ card }) => card);
  }, [mappedWithIds, selectedTeamIds, dateFrom, dateTo]);

  const pending = allTrades.filter((t) => t.status === "pending");
  const accepted = allTrades.filter((t) => t.status === "accepted");
  // Iter 232L — Processed tab surfaces the trade history (executed
  // + processed statuses). Vetoed / rejected / withdrawn stay on the
  // All tab so managers can audit terminated proposals separately.
  const processed = allTrades.filter((t) => t.status === "executed" || t.status === "processed");
  const all = allTrades;

  // Iter 170d — KPI strip. Runs over the SAME filtered rows that drive
  // the tabs so the numbers always match what's on screen below.
  //   • This Week    = trades whose created_at falls in the last 7 days
  //   • This Month   = trades whose created_at falls in the last 30 days
  //   • Most Active  = team appearing on the most trades (counts both
  //                    proposer and target sides)
  const kpis = useMemo(() => {
    const filtered = mappedWithIds.filter(({ card }) =>
      ((card.assetsFromA?.length || 0) > 0 || (card.assetsFromB?.length || 0) > 0) &&
      card.teamA && card.teamB && card.teamA !== card.teamB,
    ).filter(({ _proposerId, _targetId, _createdAt }) => {
      if (selectedTeamIds.size > 0 &&
          !(_proposerId && selectedTeamIds.has(_proposerId)) &&
          !(_targetId && selectedTeamIds.has(_targetId))) return false;
      const day = (_createdAt || "").slice(0, 10);
      if (dateFrom && (!day || day < dateFrom)) return false;
      if (dateTo && (!day || day > dateTo)) return false;
      return true;
    });
    const now = new Date();
    const sevenDays = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
    const thirtyDays = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
    let weekCount = 0;
    let monthCount = 0;
    const teamCounts: Record<string, number> = {};
    for (const row of filtered) {
      const ts = row._createdAt ? new Date(row._createdAt) : null;
      if (ts && !isNaN(ts.getTime())) {
        if (ts >= sevenDays) weekCount += 1;
        if (ts >= thirtyDays) monthCount += 1;
      }
      if (row._proposerId) teamCounts[row._proposerId] = (teamCounts[row._proposerId] || 0) + 1;
      if (row._targetId) teamCounts[row._targetId] = (teamCounts[row._targetId] || 0) + 1;
    }
    let topTeamId: string | null = null;
    let topTeamCount = 0;
    for (const [tid, c] of Object.entries(teamCounts)) {
      if (c > topTeamCount) { topTeamId = tid; topTeamCount = c; }
    }
    return {
      total: filtered.length,
      week: weekCount,
      month: monthCount,
      mostActive: topTeamId
        ? { id: topTeamId, name: teamName(topTeamId), count: topTeamCount }
        : null,
    };
  }, [mappedWithIds, selectedTeamIds, dateFrom, dateTo, leagueTeams]);

  return (
    <AppLayout>
        <div className="container py-8">
          <LeagueContextBanner title="Transactions" kpiLabel="Trades this season" kpiValue={all.length} primaryHref="/trade-block" primaryLabel="Open Trade Block" />
        <div className="mb-6 animate-fade-in">
          <h1 className="text-3xl font-bold mb-2">Transactions</h1>
          <p className="text-muted-foreground">Review pending and accepted trades, plus league activity. Cast your vote to approve or veto.</p>
        </div>

        {/* Iter 170d — KPI strip. Reflects active filters in real-time. */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-6" data-testid="transactions-kpi-strip">
          <Card className="border-border/60">
            <CardContent className="py-3 px-4 flex items-center justify-between">
              <div>
                <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Trades · This Week</div>
                <div className="text-2xl font-semibold text-foreground leading-tight" data-testid="transactions-kpi-week">{kpis.week}</div>
                <div className="text-[10px] text-muted-foreground">last 7 days</div>
              </div>
              <Clock className="h-5 w-5 text-primary/70" />
            </CardContent>
          </Card>
          <Card className="border-border/60">
            <CardContent className="py-3 px-4 flex items-center justify-between">
              <div>
                <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Trades · This Month</div>
                <div className="text-2xl font-semibold text-foreground leading-tight" data-testid="transactions-kpi-month">{kpis.month}</div>
                <div className="text-[10px] text-muted-foreground">last 30 days</div>
              </div>
              <Activity className="h-5 w-5 text-accent/70" />
            </CardContent>
          </Card>
          <Card className="border-border/60">
            <CardContent className="py-3 px-4 flex items-center justify-between">
              <div className="min-w-0">
                <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Most Active Team</div>
                <div className="text-base font-semibold text-foreground leading-tight truncate" data-testid="transactions-kpi-most-active">
                  {kpis.mostActive ? kpis.mostActive.name : "—"}
                </div>
                <div className="text-[10px] text-muted-foreground">
                  {kpis.mostActive ? `${kpis.mostActive.count} trade${kpis.mostActive.count === 1 ? "" : "s"}` : "no trades in range"}
                </div>
              </div>
              <Zap className="h-5 w-5 text-yellow-500/70" />
            </CardContent>
          </Card>
        </div>

        {/* Iter 170c — trade filters: team chips + date range */}
        <Card className="mb-6 border-border/60" data-testid="transactions-filters">
          <CardContent className="py-4 space-y-3">
            <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-muted-foreground">
              <Filter className="h-3.5 w-3.5" />
              Filters
              {(selectedTeamIds.size > 0 || dateFrom || dateTo) && (
                <Button
                  size="sm"
                  variant="ghost"
                  className="h-6 ml-auto text-xs gap-1"
                  data-testid="transactions-filters-clear"
                  onClick={() => {
                    setSelectedTeamIds(new Set());
                    setDateFrom("");
                    setDateTo("");
                  }}
                >
                  <X className="h-3 w-3" />
                  Clear
                </Button>
              )}
            </div>
            <div className="flex items-center gap-2 flex-wrap" data-testid="transactions-team-chips">
              <span className="text-[10px] uppercase text-muted-foreground tracking-wider mr-1">
                {selectedTeamIds.size === 0
                  ? "Filter by team"
                  : `Showing ${selectedTeamIds.size} team${selectedTeamIds.size === 1 ? "" : "s"}`}
              </span>
              {(leagueTeams || []).map((t: any) => {
                const isOn = selectedTeamIds.has(t.id);
                return (
                  <button
                    key={t.id}
                    type="button"
                    aria-pressed={isOn}
                    data-testid={`transactions-team-chip-${t.id}`}
                    onClick={() => {
                      setSelectedTeamIds((prev) => {
                        const next = new Set(prev);
                        if (next.has(t.id)) next.delete(t.id);
                        else next.add(t.id);
                        return next;
                      });
                    }}
                    className={
                      "px-2 py-0.5 rounded text-[11px] font-medium uppercase border transition-colors " +
                      (isOn
                        ? "bg-primary/25 border-primary/60 text-primary"
                        : "bg-secondary/30 border-border/40 text-muted-foreground hover:border-primary/40 hover:text-foreground")
                    }
                  >
                    {t.logo_abbr || (t.name || "").slice(0, 3).toUpperCase()}
                  </button>
                );
              })}
            </div>
            <div className="flex items-end gap-3 flex-wrap">
              <div className="flex flex-col gap-1">
                <Label htmlFor="trans-date-from" className="text-[10px] uppercase tracking-wider text-muted-foreground">
                  From
                </Label>
                <Input
                  id="trans-date-from"
                  type="date"
                  value={dateFrom}
                  onChange={(e) => setDateFrom(e.target.value)}
                  data-testid="transactions-date-from"
                  className="h-8 text-xs w-40"
                />
              </div>
              <div className="flex flex-col gap-1">
                <Label htmlFor="trans-date-to" className="text-[10px] uppercase tracking-wider text-muted-foreground">
                  To
                </Label>
                <Input
                  id="trans-date-to"
                  type="date"
                  value={dateTo}
                  onChange={(e) => setDateTo(e.target.value)}
                  data-testid="transactions-date-to"
                  className="h-8 text-xs w-40"
                />
              </div>
            </div>
          </CardContent>
        </Card>

        <Tabs value={tab} onValueChange={setTab}>
          <div className="flex items-center justify-between gap-3 mb-4 flex-wrap">
            <TabsList>
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
              <TabsTrigger value="processed" data-testid="transactions-tab-processed">
                Processed
                {processed.length > 0 && (
                  <Badge variant="secondary" className="ml-2 text-xs">{processed.length}</Badge>
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

            {/* Iter 232L — Global stat view toggle. Applies to Pending,
                Accepted, Processed, All, and Conditional cards so managers
                can flip every trade on the page between FPts (season + per-
                game) and the league's counting categories. */}
            <div
              className="inline-flex items-center rounded-md border border-border/60 bg-secondary/30 p-0.5 text-xs"
              role="group"
              aria-label="Stat view mode"
              data-testid="transactions-view-toggle"
            >
              <button
                type="button"
                onClick={() => setViewMode("fpts")}
                aria-pressed={viewMode === "fpts"}
                data-testid="transactions-view-fpts"
                className={
                  "px-3 py-1.5 rounded transition-colors font-medium " +
                  (viewMode === "fpts"
                    ? "bg-primary text-primary-foreground shadow-sm"
                    : "text-muted-foreground hover:text-foreground")
                }
              >
                FPts
              </button>
              <button
                type="button"
                onClick={() => setViewMode("categories")}
                aria-pressed={viewMode === "categories"}
                data-testid="transactions-view-categories"
                className={
                  "px-3 py-1.5 rounded transition-colors font-medium " +
                  (viewMode === "categories"
                    ? "bg-primary text-primary-foreground shadow-sm"
                    : "text-muted-foreground hover:text-foreground")
                }
              >
                Categories
              </button>
            </div>
          </div>

          <TabsContent value="pending" className="space-y-4">
            {pending.length === 0 ? (
              <Card><CardContent className="py-8 text-center text-muted-foreground">No pending trades.</CardContent></Card>
            ) : pending.map((t) => <TradeCard key={t.id} trade={t} viewMode={viewMode} />)}
          </TabsContent>

          <TabsContent value="accepted" className="space-y-4">
            {accepted.length === 0 ? (
              <Card><CardContent className="py-8 text-center text-muted-foreground">No accepted trades awaiting processing.</CardContent></Card>
            ) : accepted.map((t) => <TradeCard key={t.id} trade={t} viewMode={viewMode} />)}
          </TabsContent>

          <TabsContent value="processed" className="space-y-4">
            {processed.length === 0 ? (
              <Card><CardContent className="py-8 text-center text-muted-foreground">No processed trades yet. Trades appear here once they have executed.</CardContent></Card>
            ) : processed.map((t) => <TradeCard key={t.id} trade={t} viewMode={viewMode} />)}
          </TabsContent>

          <TabsContent value="all" className="space-y-4">
            {all.length === 0 ? (
              <Card><CardContent className="py-8 text-center text-muted-foreground">No trades yet in this league. When managers propose trades they'll appear here.</CardContent></Card>
            ) : all.map((t) => <TradeCard key={t.id} trade={t} viewMode={viewMode} />)}
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
                const mapped: PendingTrade = {
                  id: tradeId,
                  teamA: teamName(t.proposer_team_id || t.from_team_id || t.team_a_id),
                  teamB: teamName(t.target_team_id || t.to_team_id || t.team_b_id),
                  assetsFromA: fromAssets.map(mapAssetRow),
                  assetsFromB: toAssets.map(mapAssetRow),
                  status: "accepted",
                  submittedAt: "",
                  processesAt: "",
                  votes: { approve: 0, veto: 0, total: 0 },
                  scoringCategories: t.scoring_categories,
                };
                return <ConditionalTradeCard
                  key={tradeId}
                  trade={t}
                  mapped={mapped}
                  viewMode={viewMode}
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
