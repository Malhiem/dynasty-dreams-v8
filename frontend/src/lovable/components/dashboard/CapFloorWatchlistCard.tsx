// @ts-nocheck
/**
 * Iter 122 — Cap Floor Watchlist (commissioner-only card).
 *
 * Reads `GET /api/leagues/{league_id}/cap-floor-watchlist` and shows every
 * team's current-year payroll vs the league floor, with three states:
 *   • below      → red, $X short
 *   • watchlist  → amber, within warning threshold
 *   • above      → muted (not shown by default; toggle "Show all teams")
 *
 * Renders nothing when the league has no floor enabled or when the user
 * is NOT a commissioner of this league.
 */
import { useEffect, useState } from "react";
import { ShieldAlert, Users, EyeOff, Eye } from "lucide-react";
import api from "@/lib/api";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

const fmtMoney = (n) =>
  `$${(Number(n || 0) / 1_000_000).toFixed(1)}M`;

export default function CapFloorWatchlistCard({ leagueId, isCommissioner }) {
  const [data, setData] = useState(null);
  const [showAll, setShowAll] = useState(false);

  useEffect(() => {
    if (!leagueId || !isCommissioner) return;
    let cancelled = false;
    api.get(`/leagues/${leagueId}/cap-floor-watchlist`)
      .then(({ data }) => { if (!cancelled) setData(data); })
      .catch(() => { if (!cancelled) setData(null); });
    return () => { cancelled = true; };
  }, [leagueId, isCommissioner]);

  if (!isCommissioner || !data || !data.floor_enabled || data.floor <= 0) return null;

  const visibleRows = showAll
    ? data.teams
    : data.teams.filter((r) => r.status !== "above");
  const { below_count, watchlist_count } = data.summary || {};

  return (
    <Card className="bg-card border-border" data-testid="cap-floor-watchlist-card">
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-3 flex-wrap">
          <div>
            <CardTitle className="flex items-center gap-2 text-base">
              <ShieldAlert className="h-4 w-4 text-amber-400" />
              Cap Floor Watchlist
            </CardTitle>
            <CardDescription>
              Floor for {data.year}: <strong className="text-amber-300">{fmtMoney(data.floor)}</strong>.
              Teams within <strong>{fmtMoney(data.warning_threshold)}</strong> of the floor are flagged.
            </CardDescription>
          </div>
          <div className="flex items-center gap-2">
            <Badge className="bg-rose-500/15 border border-rose-500/40 text-rose-300" data-testid="cap-floor-below-count">
              {below_count ?? 0} below
            </Badge>
            <Badge className="bg-amber-500/15 border border-amber-500/40 text-amber-300" data-testid="cap-floor-watchlist-count">
              {watchlist_count ?? 0} on watch
            </Badge>
            <Button
              size="sm" variant="outline" onClick={() => setShowAll((s) => !s)}
              className="gap-1"
              data-testid="cap-floor-toggle-all"
            >
              {showAll ? <><EyeOff className="h-3 w-3" /> Hide compliant</> : <><Eye className="h-3 w-3" /> Show all teams</>}
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent className="pt-0">
        {visibleRows.length === 0 ? (
          <p className="text-sm text-muted-foreground italic flex items-center gap-2 py-3">
            <Users className="h-4 w-4" />
            All teams are comfortably above the floor.
          </p>
        ) : (
          <div className="rounded-md border border-border overflow-x-auto">
            <Table data-testid="cap-floor-watchlist-table">
              <TableHeader>
                <TableRow>
                  <TableHead>Team</TableHead>
                  <TableHead className="text-right">Payroll</TableHead>
                  <TableHead className="text-right">Δ to Floor</TableHead>
                  <TableHead className="text-right">Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {visibleRows.map((r) => (
                  <TableRow key={r.team_id} data-testid={`cap-floor-row-${r.status}`}>
                    <TableCell className="font-medium">{r.team_name}</TableCell>
                    <TableCell className="text-right font-mono text-xs">{fmtMoney(r.payroll)}</TableCell>
                    <TableCell className={`text-right font-mono text-xs ${r.delta_to_floor < 0 ? "text-rose-400 font-semibold" : ""}`}>
                      {r.delta_to_floor >= 0 ? "+" : ""}{fmtMoney(r.delta_to_floor)}
                    </TableCell>
                    <TableCell className="text-right">
                      {r.status === "below" ? (
                        <Badge className="bg-rose-500/15 border border-rose-500/40 text-rose-300">Below floor</Badge>
                      ) : r.status === "watchlist" ? (
                        <Badge className="bg-amber-500/15 border border-amber-500/40 text-amber-300">Watchlist</Badge>
                      ) : (
                        <Badge variant="outline" className="opacity-70">Compliant</Badge>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
