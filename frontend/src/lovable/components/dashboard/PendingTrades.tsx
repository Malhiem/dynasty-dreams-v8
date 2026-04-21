// @ts-nocheck
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ArrowRightLeft, ExternalLink } from "lucide-react";
import { useNavigate } from "react-router-dom";
import TeamLink from "@/lovable/components/TeamLink";

const PENDING_TRADES = [
  {
    id: "T-001",
    teamA: "Frost Giants",
    teamB: "Ice Wolves",
    summary: "McDavid for Matthews + 2026 1st",
    status: "pending" as const,
    votes: { approve: 5, veto: 2, total: 12 },
  },
  {
    id: "T-002",
    teamA: "Northern Lights",
    teamB: "Blizzard",
    summary: "Makar for Hughes + 2027 2nd",
    status: "pending" as const,
    votes: { approve: 3, veto: 1, total: 12 },
  },
  {
    id: "T-003",
    teamA: "Avalanche",
    teamB: "Storm Surge",
    summary: "Rantanen for Stützle",
    status: "accepted" as const,
    votes: { approve: 8, veto: 1, total: 12 },
  },
];

const PendingTrades = () => {
  const navigate = useNavigate();

  return (
    <Card className="border-border/50 hover:border-primary/20 transition-colors cursor-pointer" onClick={() => navigate("/transactions")}>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-base flex items-center gap-2">
            <ArrowRightLeft className="h-4 w-4 text-primary" />
            Pending Trades
          </CardTitle>
          <Badge variant="secondary" className="text-xs">{PENDING_TRADES.filter(t => t.status === "pending").length} active</Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {PENDING_TRADES.map((trade) => (
          <div key={trade.id} className="flex items-center justify-between p-2 rounded-lg bg-secondary/30 hover:bg-secondary/50 transition-colors">
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium truncate">
                <TeamLink name={trade.teamA} /> ↔ <TeamLink name={trade.teamB} />
              </p>
              <p className="text-xs text-muted-foreground truncate">{trade.summary}</p>
            </div>
            <div className="flex items-center gap-2 ml-2 shrink-0">
              <Badge
                variant="outline"
                className={trade.status === "pending" ? "border-amber-500/50 text-amber-400 text-[10px]" : "border-emerald-500/50 text-emerald-400 text-[10px]"}
              >
                {trade.status === "pending" ? "Pending" : "Accepted"}
              </Badge>
            </div>
          </div>
        ))}
        <div className="flex items-center justify-center gap-1 text-xs text-primary pt-1">
          <span>View all transactions</span>
          <ExternalLink className="h-3 w-3" />
        </div>
      </CardContent>
    </Card>
  );
};

export default PendingTrades;
