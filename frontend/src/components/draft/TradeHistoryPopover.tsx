// @ts-nocheck
// Extracted from lovable/pages/DraftBoard.tsx (Iter 232N.34 refactor).
// Renders the trade-chain popover for a single draft pick — original owner,
// current owner, and a scrollable list of each trade step (with pick-upgrade
// support). The `leagueTeams` prop is the list used to resolve abbr → name.
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Badge } from "@/components/ui/badge";
import { ArrowRightLeft, ChevronDown } from "lucide-react";

interface PickTrade {
  step?: number;
  from?: string;
  from_team_name?: string;
  to?: string;
  to_team_name?: string;
  date?: string;
  kind?: string;
  fromRound?: number;
  toRound?: number;
  fromYear?: string;
  toYear?: string;
  trigger?: string;
  details?: string;
}

interface PickOwnership {
  originalTeam: string;
  currentOwner: string;
  tradeHistory: PickTrade[];
}

interface Props {
  pick: PickOwnership;
  leagueTeams: { name: string; abbr: string }[];
}

export default function TradeHistoryPopover({ pick, leagueTeams }: Props) {
  const originalTeam = leagueTeams.find((t) => t.abbr === pick.originalTeam);
  const currentOwner = leagueTeams.find((t) => t.abbr === pick.currentOwner);

  // Year-grouped "via X · MMM D" summary — trades that land in the same
  // calendar year are clumped under a single year header.
  const groupedSummary = (() => {
    const byYear: Record<string, string[]> = {};
    const order: string[] = [];
    (pick.tradeHistory || []).forEach((t: PickTrade) => {
      const raw = t?.date;
      if (!raw) return;
      const d = new Date(raw);
      if (Number.isNaN(d.getTime())) return;
      const y = String(d.getFullYear());
      const mmd = d.toLocaleString(undefined, { month: "short", day: "numeric" });
      const fromAbbr = t.from || t.from_team_name || "?";
      const seg = `via ${fromAbbr} (${mmd})`;
      if (!(y in byYear)) {
        byYear[y] = [];
        order.push(y);
      }
      byYear[y].push(seg);
    });
    return order.map((y) => ({ year: y, segs: byYear[y] }));
  })();

  return (
    <Popover>
      <PopoverTrigger asChild>
        <button className="flex items-center gap-1 text-xs font-semibold text-primary hover:text-primary/80 transition-colors cursor-pointer group">
          <span>{pick.currentOwner}</span>
          <ChevronDown className="h-3 w-3 opacity-60 group-hover:opacity-100 transition-opacity" />
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-80 p-0" align="start">
        <div className="p-3 border-b border-border">
          <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
            <ArrowRightLeft className="h-4 w-4 text-primary" />
            Trade History
          </div>
          <p className="text-xs text-muted-foreground mt-1">
            Originally: <span className="font-medium text-foreground">{originalTeam?.name} ({pick.originalTeam})</span>
            {" → "}
            Now: <span className="font-medium text-primary">{currentOwner?.name} ({pick.currentOwner})</span>
          </p>
          {groupedSummary.length > 0 && (
            <ul
              className="mt-2 space-y-0.5 text-[11px]"
              data-testid="pick-trade-grouped-summary"
            >
              {groupedSummary.map((g) => (
                <li key={g.year} className="leading-snug">
                  <span className="font-semibold text-foreground">{g.year}:</span>{" "}
                  <span className="text-muted-foreground">{g.segs.join(" · ")}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
        <div className="p-2 space-y-2 max-h-60 overflow-y-auto">
          {pick.tradeHistory.map((trade: PickTrade, idx) => (
            <div
              key={idx}
              data-testid={trade.kind === "pick_upgrade" ? `pick-upgrade-${idx}` : `pick-trade-${idx}`}
              className={`p-2 rounded-md border space-y-1 ${
                trade.kind === "pick_upgrade"
                  ? "bg-amber-500/10 border-amber-500/30"
                  : "bg-secondary/50 border-border/50"
              }`}
            >
              <div className="flex items-center justify-between">
                <Badge
                  variant="outline"
                  className={`text-[10px] px-1.5 h-4 ${
                    trade.kind === "pick_upgrade" ? "border-amber-500/50 text-amber-500" : ""
                  }`}
                >
                  {trade.kind === "pick_upgrade"
                    ? (trade.toRound! < trade.fromRound! ? "PASS · Upgrade" : "PASS · Downgrade")
                    : `Trade ${idx + 1}`}
                </Badge>
                <span className="text-[10px] text-muted-foreground">
                  {trade.date ? (typeof trade.date === "string" ? trade.date.slice(0, 10) : String(trade.date)) : ""}
                </span>
              </div>
              {trade.kind === "pick_upgrade" ? (
                <>
                  <p className="text-xs leading-relaxed">
                    <span className="font-medium text-amber-500">
                      {trade.fromYear || ""} R{trade.fromRound} → {trade.toYear || trade.fromYear || ""} R{trade.toRound}
                    </span>
                  </p>
                  {trade.trigger && (
                    <p className="text-[11px] text-muted-foreground italic">
                      Trigger: {trade.trigger}
                    </p>
                  )}
                </>
              ) : (
                <>
                  <p className="text-xs text-muted-foreground leading-relaxed">
                    <span className="font-medium text-foreground">{trade.from}</span>
                    {" → "}
                    <span className="font-medium text-foreground">{trade.to}</span>
                  </p>
                  {trade.details && (
                    <p className="text-[11px] text-muted-foreground">{trade.details}</p>
                  )}
                </>
              )}
            </div>
          ))}
        </div>
      </PopoverContent>
    </Popover>
  );
}
