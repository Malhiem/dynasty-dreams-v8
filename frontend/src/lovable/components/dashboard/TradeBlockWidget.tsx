// @ts-nocheck
import { useEffect, useMemo, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import {
  ArrowRightLeft, LayoutGrid, List as ListIcon, X, Eye, ArrowUp, ArrowDown,
} from "lucide-react";
import TeamLink from "@/lovable/components/TeamLink";
import api from "@/lib/api";
import { useActiveLeague } from "@/hooks/use-active-league";
import { useTradeBlockUiPrefs } from "@/hooks/use-trade-block-ui-prefs";

// (List-view columns are now computed inside the component so we can drop
// the AAV column when the active league has no salary cap.)

// Used when the active league has no trade-block entries yet — keeps the
// widget from looking empty during seed/initial state.
const FALLBACK_ITEMS = [
  { id: "f1", name: "Connor McDavid", position: "C", team: "EDM", age: 28, weeklyPoints: 38.4, owner: "Arctic Wolves", ownerAvatar: "AW" },
  { id: "f2", name: "Cale Makar", position: "D", team: "COL", age: 26, weeklyPoints: 31.2, owner: "Glacier Kings", ownerAvatar: "GK" },
  { id: "f3", name: "Igor Shesterkin", position: "G", team: "NYR", age: 29, weeklyPoints: 26.6, owner: "Frozen Thunder", ownerAvatar: "FT" },
  { id: "f4", name: "Tim Stützle", position: "C", team: "OTT", age: 23, weeklyPoints: 29.0, owner: "Ice Crushers", ownerAvatar: "IC" },
];

const TradeBlockWidget = () => {
  const { league, leagueTeams } = useActiveLeague();
  const prefs = useTradeBlockUiPrefs(league?.id);
  const [liveItems, setLiveItems] = useState<any[]>([]);
  const capEnabled = Boolean((league as any)?.salary_cap_enabled);

  // Widget table columns — Player / Pos / Team / Pts/Wk / (AAV?) / Owner / Looking For.
  // We hide AAV when the league has no salary cap (mirrors the page contract).
  const widgetColumns = useMemo(() => ([
    { key: "name", label: "Player", numeric: false },
    { key: "position", label: "Pos", numeric: false },
    { key: "team", label: "Team", numeric: false },
    { key: "weeklyPoints", label: "Pts/Wk", numeric: true },
    ...(capEnabled ? [{ key: "aav", label: "AAV", numeric: true }] : []),
    { key: "owner", label: "Owner", numeric: false },
    { key: "lookingFor", label: "Looking For", numeric: false },
  ]), [capEnabled]);

  const fmtCurrency = (v: number | null | undefined) => {
    if (!v) return "—";
    if (v >= 1_000_000) return `$${(v / 1_000_000).toFixed(2)}M`;
    if (v >= 1_000) return `$${(v / 1_000).toFixed(0)}K`;
    return `$${v}`;
  };

  useEffect(() => {
    if (!league?.id) return;
    let cancelled = false;
    api.get(`/trade-block?league_id=${league.id}`)
      .then(({ data }) => { if (!cancelled) setLiveItems(Array.isArray(data) ? data : []); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [league?.id]);

  const ownerName = (oid: string) => (leagueTeams || []).find((t: any) => t.owner_id === oid)?.name || "Unknown";
  const ownerAbbr = (oid: string) => (leagueTeams || []).find((t: any) => t.owner_id === oid)?.logo_abbr || "?";

  const items = useMemo(() => {
    const real = (liveItems || []).map((it: any, idx: number) => ({
      id: String(it._id || idx),
      name: it.name || "Unknown",
      position: it.position || "—",
      team: it.nhl_team || (it.item_type === "pick" ? "Own" : ""),
      age: it.age || null,
      weeklyPoints: Number(it.points || 0),
      aav: it.aav || null,
      owner: ownerName(it.owner_id),
      ownerAvatar: ownerAbbr(it.owner_id),
      lookingFor: (it.looking_for || []).length ? it.looking_for : ["Best Offer"],
    }));
    return real.length > 0 ? real : FALLBACK_ITEMS;
  }, [liveItems, leagueTeams]);

  const sortedItems = useMemo(() => {
    const out = [...items];
    if (prefs.viewMode === "list") {
      const { key, dir } = prefs.sort || { key: "weeklyPoints", dir: "desc" };
      const factor = dir === "asc" ? 1 : -1;
      out.sort((a: any, b: any) => {
        const av = a[key]; const bv = b[key];
        if (typeof av === "string" || typeof bv === "string") {
          return String(av || "").localeCompare(String(bv || "")) * factor;
        }
        return ((av ?? 0) - (bv ?? 0)) * factor;
      });
    } else {
      out.sort((a: any, b: any) => (b.weeklyPoints || 0) - (a.weeklyPoints || 0));
    }
    return out;
  }, [items, prefs.viewMode, prefs.sort]);

  const visible = useMemo(() => {
    if (prefs.viewMode !== "tile") return sortedItems;
    return sortedItems.filter((it: any) => !prefs.isHidden(it.id));
  }, [sortedItems, prefs.viewMode, prefs.hiddenIds]);

  // Cap the widget at 6 rows to keep it dashboard-sized.
  const display = visible.slice(0, 6);

  return (
    <Card className="bg-card border-border" data-testid="trade-block-widget">
      <CardHeader className="pb-3 flex flex-row items-center justify-between gap-2">
        <CardTitle className="text-lg flex items-center gap-2">
          <ArrowRightLeft className="h-5 w-5 text-primary" />
          Trading Block
        </CardTitle>
        <div className="flex items-center gap-2">
          {prefs.viewMode === "tile" && prefs.hiddenIds.length > 0 && (
            <button
              type="button"
              onClick={prefs.clearHidden}
              data-testid="trade-block-widget-show-hidden"
              className="text-[11px] text-muted-foreground hover:text-foreground inline-flex items-center gap-1"
              title="Show hidden players"
            >
              <Eye className="h-3 w-3" /> {prefs.hiddenIds.length}
            </button>
          )}
          <div className="inline-flex items-center rounded-md border border-border bg-secondary/40 overflow-hidden" data-testid="trade-block-widget-view-toggle">
            <button
              type="button"
              onClick={() => prefs.setViewMode("tile")}
              aria-pressed={prefs.viewMode === "tile"}
              data-testid="trade-block-widget-view-tile"
              className={`px-1.5 py-0.5 ${prefs.viewMode === "tile" ? "bg-primary/15 text-primary" : "text-muted-foreground hover:text-foreground"}`}
              title="Tile view"
            >
              <LayoutGrid className="h-3.5 w-3.5" />
            </button>
            <button
              type="button"
              onClick={() => prefs.setViewMode("list")}
              aria-pressed={prefs.viewMode === "list"}
              data-testid="trade-block-widget-view-list"
              className={`px-1.5 py-0.5 border-l border-border ${prefs.viewMode === "list" ? "bg-primary/15 text-primary" : "text-muted-foreground hover:text-foreground"}`}
              title="List view"
            >
              <ListIcon className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>
      </CardHeader>

      <CardContent className={prefs.viewMode === "list" ? "p-0" : "space-y-3"}>
        {prefs.viewMode === "list" ? (
          <Table>
            <TableHeader>
              <TableRow>
                {widgetColumns.map((col) => {
                  const active = prefs.sort?.key === col.key;
                  return (
                    <TableHead
                      key={col.key}
                      className={`cursor-pointer select-none text-xs ${col.numeric ? "text-right" : ""}`}
                      onClick={() => prefs.toggleSort(col.key)}
                      data-testid={`trade-block-widget-col-${col.key}`}
                      aria-sort={active ? (prefs.sort.dir === "asc" ? "ascending" : "descending") : "none"}
                    >
                      <span className="inline-flex items-center gap-1">
                        {col.label}
                        {active && (prefs.sort.dir === "asc"
                          ? <ArrowUp className="h-3 w-3 text-primary" />
                          : <ArrowDown className="h-3 w-3 text-primary" />)}
                      </span>
                    </TableHead>
                  );
                })}
                <TableHead className="text-right w-[40px]"></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {display.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={widgetColumns.length + 1} className="text-center py-4 text-xs text-muted-foreground">
                    Nothing on the trade block.
                  </TableCell>
                </TableRow>
              ) : display.map((p: any) => (
                <TableRow key={p.id} data-testid={`trade-block-widget-row-${p.id}`} className="text-xs">
                  <TableCell className="font-medium">{p.name}</TableCell>
                  <TableCell>{p.position}</TableCell>
                  <TableCell>{p.team}</TableCell>
                  <TableCell className="text-right text-primary">{p.weeklyPoints ? p.weeklyPoints.toFixed(1) : "—"}</TableCell>
                  {capEnabled && (
                    <TableCell className="text-right tabular-nums">{fmtCurrency(p.aav)}</TableCell>
                  )}
                  <TableCell><TeamLink name={p.owner} /></TableCell>
                  <TableCell>
                    <div className="flex flex-wrap gap-0.5 max-w-[160px]">
                      {(p.lookingFor || []).slice(0, 2).map((req: string, idx: number) => (
                        <span key={idx} className="text-[10px] bg-secondary/60 rounded px-1 py-0.5">{req}</span>
                      ))}
                    </div>
                  </TableCell>
                  <TableCell className="text-right">
                    <button
                      type="button"
                      onClick={(e) => { e.stopPropagation(); prefs.hide(p.id); }}
                      title="Hide this player"
                      aria-label="Hide from Trade Block"
                      data-testid={`trade-block-widget-list-hide-${p.id}`}
                      className="h-6 w-6 rounded-md text-muted-foreground/60 hover:text-foreground hover:bg-secondary inline-flex items-center justify-center"
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ) : (
          <>
            {display.length === 0 ? (
              <p className="text-xs text-muted-foreground text-center py-4">
                {prefs.hiddenIds.length > 0
                  ? "All trade-block items are hidden."
                  : "Nothing on the trade block."}
              </p>
            ) : display.map((p: any) => {
              const isGoalie = p.position === "G";
              return (
                <div
                  key={p.id}
                  data-testid={`trade-block-widget-tile-${p.id}`}
                  className="relative flex items-center justify-between p-3 rounded-lg bg-muted/30 hover:bg-muted/50 transition-colors gap-3"
                >
                  <button
                    type="button"
                    onClick={(e) => { e.stopPropagation(); prefs.hide(p.id); }}
                    className="absolute top-1.5 right-1.5 h-5 w-5 rounded-md text-muted-foreground/60 hover:text-foreground hover:bg-secondary flex items-center justify-center"
                    title="Hide this player"
                    aria-label="Hide from Trade Block"
                    data-testid={`trade-block-widget-hide-${p.id}`}
                  >
                    <X className="h-3 w-3" />
                  </button>
                  <div className="min-w-0">
                    <p className="font-semibold text-sm">{p.name}</p>
                    <p className="text-xs text-muted-foreground">
                      <TeamLink name={p.owner} /> · {p.position}{p.age ? ` · Age ${p.age}` : ""}
                    </p>
                  </div>
                  <div className="text-right flex-shrink-0 pr-5">
                    <p className="text-sm font-semibold text-primary">{(p.weeklyPoints || 0).toFixed(1)} FP</p>
                  </div>
                </div>
              );
            })}
          </>
        )}
      </CardContent>
    </Card>
  );
};

export default TradeBlockWidget;
