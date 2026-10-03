// @ts-nocheck
// Iter 232L (refactor) — TradeCard extracted from Transactions.tsx.
// Renders a pending/accepted/processed trade with the FPts↔Categories
// column set driven by `viewMode`. Voting controls only render on pending.
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ArrowRightLeft, ThumbsUp, ThumbsDown, AlertTriangle } from "lucide-react";
import TeamLink from "@/lovable/components/TeamLink";
import { MinorEligibleBadge } from "@/lovable/components/MinorEligibleBadge";
import { statusConfig, DEFERRED_PILL } from "./statusConfig";
import { selectCategoriesForAssets, computeAssetTotals, formatCategoryTotal, fmtCapHit } from "./types";

export function TradeCard({ trade, viewMode }) {
  // Fall back to pending badge for unknown backend statuses.
  const status = statusConfig[trade.status] || statusConfig.pending;
  const StatusIcon = status.icon;

  const categoriesToShow = viewMode === "categories"
    ? selectCategoriesForAssets(
        [...trade.assetsFromA, ...trade.assetsFromB],
        trade.scoringCategories,
      )
    : [];

  const renderAssetTable = (assets, sideLabel) => {
    const totals = computeAssetTotals(assets, categoriesToShow);
    return (
    <div className="overflow-x-auto -mx-2 sm:mx-0">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="text-xs whitespace-nowrap">Player</TableHead>
            <TableHead className="text-xs whitespace-nowrap">Pos</TableHead>
            <TableHead className="text-xs whitespace-nowrap">Age</TableHead>
            <TableHead className="text-xs whitespace-nowrap">Cap Hit</TableHead>
            {viewMode === "fpts" ? (
              <>
                <TableHead className="text-xs whitespace-nowrap">GP</TableHead>
                <TableHead className="text-xs whitespace-nowrap">FPts</TableHead>
                <TableHead className="text-xs whitespace-nowrap">FP/G</TableHead>
              </>
            ) : (
              categoriesToShow.map((c) => (
                <TableHead key={c.key} className="text-xs whitespace-nowrap" title={c.key}>
                  {c.label}
                </TableHead>
              ))
            )}
          </TableRow>
        </TableHeader>
        <TableBody>
          {assets.map((asset) => (
            <TableRow key={asset.name}>
              <TableCell className="font-medium text-sm whitespace-nowrap">
                <span className="inline-flex items-center gap-1.5">
                  {asset.name}
                  <MinorEligibleBadge eligible={asset.type === "player" && asset.minorEligible} />
                </span>
                {asset.type === "pick" && (
                  <Badge variant="secondary" className="ml-1 text-[10px]">Pick</Badge>
                )}
              </TableCell>
              <TableCell className="text-sm">{asset.position}</TableCell>
              <TableCell className="text-sm">
                {asset.type === "player" ? asset.age || "—" : "—"}
              </TableCell>
              <TableCell className="text-sm whitespace-nowrap">{asset.capHit}</TableCell>
              {viewMode === "fpts" ? (
                <>
                  <TableCell className="text-sm">
                    {asset.type === "player" ? asset.gamesPlayed ?? 0 : "—"}
                  </TableCell>
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
                    {asset.type === "player" ? asset.statCategories?.[c.key]?.value ?? 0 : "—"}
                  </TableCell>
                ))
              )}
            </TableRow>
          ))}
          {/* Iter 232L.4 — Totals row so managers can compare aggregate
              output flowing each way in one glance. Rate stats
              (SV%, GAA) are shown as games-weighted averages; everything
              else is a straight sum. Hidden when there are no players on
              the side (e.g. picks-only). */}
          {totals.hasPlayers && (
            <TableRow
              className="border-t-2 border-border/60 bg-secondary/25 font-semibold"
              data-testid={`trade-totals-${sideLabel}-${trade.id}`}
            >
              <TableCell className="text-xs uppercase tracking-wider text-muted-foreground whitespace-nowrap">
                Total
              </TableCell>
              <TableCell className="text-sm">—</TableCell>
              <TableCell className="text-sm">—</TableCell>
              <TableCell className="text-sm whitespace-nowrap">{fmtCapHit(totals.capHit)}</TableCell>
              {viewMode === "fpts" ? (
                <>
                  <TableCell className="text-sm">{totals.gp}</TableCell>
                  <TableCell className="text-sm text-primary">
                    {totals.fpts.toFixed(1)}
                  </TableCell>
                  <TableCell className="text-sm text-primary/80">
                    {totals.fptsPerGame.toFixed(2)}
                  </TableCell>
                </>
              ) : (
                categoriesToShow.map((c) => (
                  <TableCell key={c.key} className="text-sm">
                    {formatCategoryTotal(c.key, totals.categories[c.key] ?? 0)}
                  </TableCell>
                ))
              )}
            </TableRow>
          )}
        </TableBody>
      </Table>
    </div>
    );
  };

  return (
    <Card className="border-border/50" data-testid={`trade-card-${trade.id}`}>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <ArrowRightLeft className="h-5 w-5 text-primary" />
            <CardTitle className="text-lg">
              <TeamLink name={trade.teamA} />
              <span className="text-muted-foreground mx-1">↔</span>
              <TeamLink name={trade.teamB} />
            </CardTitle>
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            <Badge variant={status.variant} className={status.className}>
              <StatusIcon className="h-3 w-3 mr-1" />
              {status.label}
            </Badge>
            {trade.deferReason === "matchup_locked" && (
              <Badge
                variant="outline"
                className={DEFERRED_PILL.className}
                data-testid={`trade-deferred-${trade.id}`}
                title={
                  trade.deferNextUnlock
                    ? `Trade will execute after lineup lock lifts at ${trade.deferNextUnlock.slice(0, 16).replace("T", " ")}`
                    : "Held until the next matchup unlock"
                }
              >
                <DEFERRED_PILL.icon className="h-3 w-3 mr-1" />
                {DEFERRED_PILL.label}
              </Badge>
            )}
          </div>
        </div>
        <div className="flex items-center gap-4 text-xs text-muted-foreground mt-1">
          <span>Submitted: {trade.submittedAt}</span>
          <span>Processes: {trade.processesAt}</span>
          <span>
            Votes: {trade.votes.approve} approve / {trade.votes.veto} veto of {trade.votes.total}
          </span>
        </div>
      </CardHeader>
      <CardContent>
        {/* Iter 232L.3 — In Categories view the per-side asset table has
            10+ columns; stack the two teams vertically so each side gets
            the full page width and no columns get clipped. FPts view
            keeps the side-by-side two-column layout on desktop. */}
        <div className={
          viewMode === "categories"
            ? "grid grid-cols-1 gap-4"
            : "grid grid-cols-1 lg:grid-cols-2 gap-4"
        }>
          <div>
            <p className="text-sm font-medium text-muted-foreground mb-2">
              <TeamLink name={trade.teamA} /> sends:
            </p>
            {renderAssetTable(trade.assetsFromA, "a")}
          </div>
          <div>
            <p className="text-sm font-medium text-muted-foreground mb-2">
              <TeamLink name={trade.teamB} /> sends:
            </p>
            {renderAssetTable(trade.assetsFromB, "b")}
          </div>
        </div>

        {trade.salaryRetained && (
          <div className="mt-3 flex items-center gap-2 text-xs">
            <AlertTriangle className="h-3.5 w-3.5 text-amber-400" />
            <span className="text-muted-foreground">
              Salary retained:{" "}
              <span className="text-foreground font-medium">{trade.salaryRetained.team}</span>{" "}
              retains{" "}
              <span className="text-foreground font-medium">{trade.salaryRetained.amount}</span>{" "}
              for{" "}
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
                title={
                  trade.yourVote === "approve"
                    ? "You voted Approve (click again to confirm/unchange)"
                    : "Vote Approve"
                }
              >
                <ThumbsUp className="h-3.5 w-3.5 mr-1" /> Approve
                {trade.yourVote === "approve" && (
                  <span className="ml-1 text-[10px]">(your vote)</span>
                )}
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
                title={
                  trade.yourVote === "veto"
                    ? "You voted Veto (click Approve to switch)"
                    : "Vote Veto"
                }
              >
                <ThumbsDown className="h-3.5 w-3.5 mr-1" /> Veto
                {trade.yourVote === "veto" && (
                  <span className="ml-1 text-[10px]">(your vote)</span>
                )}
              </Button>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
