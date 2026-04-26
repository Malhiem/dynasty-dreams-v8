// @ts-nocheck
import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ArrowRightLeft, ExternalLink } from "lucide-react";
import { useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { useActiveLeague } from "@/hooks/use-active-league";

/**
 * PendingTrades — Dashboard widget that lists OPEN trade proposals in the
 * user's active league. Fetches real data from /api/leagues/{id}/pending-trades
 * and renders null when the list is empty so the dashboard slot collapses
 * cleanly instead of showing a fake placeholder.
 */
const PendingTrades = () => {
  const navigate = useNavigate();
  const { league } = useActiveLeague();
  const [trades, setTrades] = useState([]);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    if (!league?.id) return;
    let cancelled = false;
    api
      .get(`/leagues/${league.id}/pending-trades`)
      .then(({ data }) => {
        if (cancelled) return;
        setTrades(data?.pending_trades || []);
        setLoaded(true);
      })
      .catch(() => setLoaded(true));
    return () => {
      cancelled = true;
    };
  }, [league?.id]);

  // Don't render the widget at all until we know the answer, AND don't
  // render anything when there are no pending trades — keeps the dashboard
  // tidy.
  if (!loaded || trades.length === 0) return null;

  const summarize = (t) => {
    if (Array.isArray(t.parties) && t.parties.length > 0) {
      return t.parties.map((p) => p.team_name).join(" ↔ ");
    }
    return `${t.proposer_team_name || "?"} ↔ ${t.target_team_name || "?"}`;
  };

  const assetSummary = (t) => {
    const offered = (t.assets_offered || []).slice(0, 2).map((a) => a.player_name).filter(Boolean);
    const requested = (t.assets_requested || []).slice(0, 2).map((a) => a.player_name).filter(Boolean);
    if (!offered.length && !requested.length) return "Picks / FAAB";
    return `${offered.join(", ") || "—"} for ${requested.join(", ") || "—"}`;
  };

  return (
    <Card
      className="border-border/50 hover:border-primary/20 transition-colors cursor-pointer"
      onClick={() => navigate("/transactions")}
      data-testid="dashboard-pending-trades"
    >
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-base flex items-center gap-2">
            <ArrowRightLeft className="h-4 w-4 text-primary" />
            Pending Trades
          </CardTitle>
          <Badge variant="secondary" className="text-xs">{trades.length} active</Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {trades.slice(0, 5).map((t) => (
          <div
            key={t._id || t.id}
            className="flex items-center justify-between p-2 rounded-lg bg-secondary/30 hover:bg-secondary/50 transition-colors"
            data-testid={`dashboard-pending-trade-${t._id || t.id}`}
          >
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium truncate">{summarize(t)}</p>
              <p className="text-xs text-muted-foreground truncate">{assetSummary(t)}</p>
            </div>
            <Badge
              variant="outline"
              className={
                t.status === "accepted"
                  ? "border-emerald-500/50 text-emerald-400 text-[10px] ml-2 shrink-0"
                  : "border-amber-500/50 text-amber-400 text-[10px] ml-2 shrink-0"
              }
            >
              {t.status === "accepted" ? "Accepted" : "Pending"}
            </Badge>
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
