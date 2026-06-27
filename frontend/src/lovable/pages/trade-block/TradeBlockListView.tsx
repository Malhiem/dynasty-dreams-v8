// @ts-nocheck
/**
 * Iter 230 — Extracted from TradeBlock.tsx.
 *
 * Sortable list/table view of Trade Block items. Renders a row per
 * listing with the standard column set (Name/Pos/Team/Age/Pts/Owner/
 * Looking for) plus an optional Cap (AAV) column when the league
 * has a salary cap configured. Trade + Hide actions per row.
 */
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { ArrowRightLeft, ArrowUp, ArrowDown, EyeOff } from "lucide-react";
import TeamLink from "@/lovable/components/TeamLink";

const TradeBlockListView = ({
  items,
  sort,
  onToggleSort,
  onTrade,
  onHide,
  capEnabled,
  capColumnLabel,
}) => {
  const columns = [
    { key: "name", label: "Player", numeric: false, testid: "trade-block-col-name" },
    { key: "position", label: "Pos", numeric: false, testid: "trade-block-col-position" },
    { key: "team", label: "Team", numeric: false, testid: "trade-block-col-team" },
    { key: "age", label: "Age", numeric: true, testid: "trade-block-col-age" },
    { key: "weeklyPoints", label: "Pts/Wk", numeric: true, testid: "trade-block-col-weekly" },
    ...(capEnabled ? [{ key: "aav", label: capColumnLabel, numeric: true, testid: "trade-block-col-aav" }] : []),
    { key: "owner", label: "Owner", numeric: false, testid: "trade-block-col-owner" },
    { key: "lookingFor", label: "Looking For", numeric: false, testid: "trade-block-col-looking-for" },
  ];

  const fmtCurrency = (v) => {
    if (!v) return "—";
    if (v >= 1_000_000) return `$${(v / 1_000_000).toFixed(2)}M`;
    if (v >= 1_000) return `$${(v / 1_000).toFixed(0)}K`;
    return `$${v}`;
  };

  return (
    <Card className="bg-card border-border" data-testid="trade-block-list-view">
      <CardContent className="p-0">
        <Table>
          <TableHeader>
            <TableRow>
              {columns.map((col) => {
                const active = sort?.key === col.key;
                return (
                  <TableHead
                    key={col.key}
                    className={`cursor-pointer select-none hover:text-foreground transition-colors ${col.numeric ? "text-right" : ""}`}
                    onClick={() => onToggleSort(col.key)}
                    data-testid={col.testid}
                    aria-sort={active ? (sort.dir === "asc" ? "ascending" : "descending") : "none"}
                  >
                    <span className="inline-flex items-center gap-1">
                      {col.label}
                      {active && (sort.dir === "asc"
                        ? <ArrowUp className="h-3 w-3 text-primary" />
                        : <ArrowDown className="h-3 w-3 text-primary" />)}
                    </span>
                  </TableHead>
                );
              })}
              <TableHead className="text-right w-[180px]">Action</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {items.length === 0 ? (
              <TableRow>
                <TableCell colSpan={columns.length + 1} className="text-center py-8 text-muted-foreground">
                  No items match your filters
                </TableCell>
              </TableRow>
            ) : items.map((item) => (
              <TableRow key={item.id} data-testid={`trade-block-row-${item.id}`}>
                <TableCell className="font-medium">{item.name}</TableCell>
                <TableCell>{item.position}</TableCell>
                <TableCell>{item.team || "—"}</TableCell>
                <TableCell className="text-right">{item.age ?? "—"}</TableCell>
                <TableCell className="text-right text-primary">
                  {item.weeklyPoints && item.weeklyPoints > 0 ? item.weeklyPoints.toFixed(1) : "—"}
                </TableCell>
                {capEnabled && (
                  <TableCell className="text-right tabular-nums">{fmtCurrency(item.aav)}</TableCell>
                )}
                <TableCell><TeamLink name={item.owner} /></TableCell>
                <TableCell>
                  <div className="flex flex-wrap gap-1 max-w-[260px]">
                    {(item.lookingFor || []).slice(0, 3).map((req, idx) => (
                      <Badge key={idx} variant="secondary" className="text-[10px] py-0 px-1.5">
                        {req}
                      </Badge>
                    ))}
                  </div>
                </TableCell>
                <TableCell className="text-right">
                  <div className="flex items-center justify-end gap-1">
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => onTrade(item)}
                      data-testid={`trade-block-list-trade-${item.id}`}
                    >
                      <ArrowRightLeft className="h-3.5 w-3.5 mr-1" />
                      Trade
                    </Button>
                    <Button
                      size="icon"
                      variant="ghost"
                      onClick={() => onHide(item.id)}
                      title="Hide this player"
                      aria-label="Hide from Trade Block"
                      data-testid={`trade-block-list-hide-${item.id}`}
                      className="h-8 w-8 text-muted-foreground/70 hover:text-foreground"
                    >
                      <EyeOff className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
};

export default TradeBlockListView;
