// @ts-nocheck
// Iter 232L (refactor) — Slimmed Transactions page. The heavy card + row
// rendering was extracted into `./transactions/*` so this file focuses on
// data loading, filter state, and layout composition.
import { useState, useEffect, useMemo } from "react";
import { AppLayout } from "@/components/layout/AppLayout";
import { useActiveLeague } from "@/hooks/use-active-league";
import api from "@/lib/api";
import LeagueContextBanner from "@/lovable/components/dashboard/LeagueContextBanner";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Clock, Activity, Zap, Filter, X } from "lucide-react";
import { toast } from "sonner";

import { TradeCard } from "./transactions/TradeCard";
import { ConditionalTradeCard } from "./transactions/ConditionalTradeCard";
import { StatViewToggle } from "./transactions/StatViewToggle";
import { mapAssetRow, mapTrade } from "./transactions/mapTrade";

const Transactions = () => {
  const { league, leagueTeams } = useActiveLeague();
  const leagueTeamsCount = leagueTeams?.length || 0;

  const [tab, setTab] = useState("pending");
  // Iter 232L — Stat view toggle: FPts (season + per-game) vs Categories
  // (dynamic per-league counting stats). Applies to the whole page.
  const [viewMode, setViewMode] = useState(() => {
    try {
      const stored = window.localStorage.getItem("transactions.viewMode");
      return stored === "categories" ? "categories" : "fpts";
    } catch {
      return "fpts";
    }
  });
  useEffect(() => {
    try {
      window.localStorage.setItem("transactions.viewMode", viewMode);
    } catch {
      /* ignore storage errors */
    }
  }, [viewMode]);

  const [trades, setTrades] = useState([]);
  const [activity, setActivity] = useState([]);
  const [voteState, setVoteState] = useState({});
  const [reloadTick, setReloadTick] = useState(0);
  // Iter 170c — filter state. Multi-select team chips + date-range.
  const [selectedTeamIds, setSelectedTeamIds] = useState(new Set());
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  // Conditional trades — fetched lazily on tab open.
  const [conditionalTrades, setConditionalTrades] = useState(null);
  const [conditionalLoading, setConditionalLoading] = useState(false);
  const [subsByTrade, setSubsByTrade] = useState({});

  useEffect(() => {
    if (!league?.id) return;
    let cancelled = false;
    api.get(`/trades?league_id=${league.id}`)
      .then(({ data }) => {
        if (!cancelled) setTrades(Array.isArray(data) ? data : (data?.items || []));
      })
      .catch(() => {});
    api.get(`/activity/${league.id}?limit=100`)
      .then(({ data }) => {
        if (!cancelled) setActivity(data?.items || []);
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [league?.id, reloadTick]);

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
      const map = {};
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

  const toggleConditionalSubscription = async (tradeId, pickUpgradeIdx, currentlySubscribed) => {
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
    } catch (e) {
      toast.error("Couldn't update subscription", {
        description: e?.response?.data?.detail || e?.message,
      });
    }
  };

  // Pull live vote details once we know which pending trades exist.
  useEffect(() => {
    if (!Array.isArray(trades) || trades.length === 0) return;
    const pendingIds = trades
      .filter((t) => (t.status || "pending") === "pending")
      .map((t) => t._id || t.id);
    let cancelled = false;
    Promise.all(pendingIds.map((id) =>
      api.get(`/trades/${id}/votes`).then((r) => [id, r.data]).catch(() => [id, null]),
    )).then((rows) => {
      if (cancelled) return;
      const map = {};
      for (const [id, data] of rows) if (data) map[id] = data;
      setVoteState(map);
    });
    return () => { cancelled = true; };
  }, [trades]);

  const castVote = async (tradeId, vote) => {
    try {
      const { data } = await api.post(`/trades/${tradeId}/vote`, { vote });
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
    } catch (e) {
      // surface via console; existing toast infra hooks up at a higher level
      // eslint-disable-next-line no-console
      console.warn("vote failed", e?.response?.data?.detail || e?.message);
    }
  };

  const teamName = (tid) => (leagueTeams || []).find((t) => t.id === tid)?.name || tid;

  const mappedWithIds = useMemo(() => {
    return (trades || []).map((t) => mapTrade(t, { teamName, leagueTeamsCount, voteState, castVote }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [trades, leagueTeams, leagueTeamsCount, voteState]);

  const allTrades = useMemo(() => {
    let rows = mappedWithIds.filter(
      ({ card }) =>
        ((card.assetsFromA?.length || 0) > 0 || (card.assetsFromB?.length || 0) > 0) &&
        card.teamA && card.teamB && card.teamA !== card.teamB,
    );
    if (selectedTeamIds.size > 0) {
      rows = rows.filter(
        ({ _proposerId, _targetId }) =>
          (_proposerId && selectedTeamIds.has(_proposerId)) ||
          (_targetId && selectedTeamIds.has(_targetId)),
      );
    }
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
  // Iter 232L — Processed tab surfaces the trade history (executed +
  // processed). Vetoed / rejected / withdrawn stay on the All tab.
  const processed = allTrades.filter((t) => t.status === "executed" || t.status === "processed");
  const all = allTrades;

  // Iter 170d — KPI strip. Runs over the SAME filtered rows that drive
  // the tabs so the numbers always match what's on screen below.
  const kpis = useMemo(() => {
    const filtered = mappedWithIds
      .filter(({ card }) =>
        ((card.assetsFromA?.length || 0) > 0 || (card.assetsFromB?.length || 0) > 0) &&
        card.teamA && card.teamB && card.teamA !== card.teamB,
      )
      .filter(({ _proposerId, _targetId, _createdAt }) => {
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
    const teamCounts = {};
    for (const row of filtered) {
      const ts = row._createdAt ? new Date(row._createdAt) : null;
      if (ts && !isNaN(ts.getTime())) {
        if (ts >= sevenDays) weekCount += 1;
        if (ts >= thirtyDays) monthCount += 1;
      }
      if (row._proposerId) teamCounts[row._proposerId] = (teamCounts[row._proposerId] || 0) + 1;
      if (row._targetId) teamCounts[row._targetId] = (teamCounts[row._targetId] || 0) + 1;
    }
    let topTeamId = null;
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

  const renderEmpty = (msg) => (
    <Card><CardContent className="py-8 text-center text-muted-foreground">{msg}</CardContent></Card>
  );

  return (
    <AppLayout>
      <div className="container py-8">
        <LeagueContextBanner
          title="Transactions"
          kpiLabel="Trades this season"
          kpiValue={all.length}
          primaryHref="/trade-block"
          primaryLabel="Open Trade Block"
        />
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
                  {kpis.mostActive
                    ? `${kpis.mostActive.count} trade${kpis.mostActive.count === 1 ? "" : "s"}`
                    : "no trades in range"}
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
              {(leagueTeams || []).map((t) => {
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
                <Label htmlFor="trans-date-from" className="text-[10px] uppercase tracking-wider text-muted-foreground">From</Label>
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
                <Label htmlFor="trans-date-to" className="text-[10px] uppercase tracking-wider text-muted-foreground">To</Label>
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
            <StatViewToggle viewMode={viewMode} onChange={setViewMode} />
          </div>

          <TabsContent value="pending" className="space-y-4">
            {pending.length === 0
              ? renderEmpty("No pending trades.")
              : pending.map((t) => <TradeCard key={t.id} trade={t} viewMode={viewMode} />)}
          </TabsContent>

          <TabsContent value="accepted" className="space-y-4">
            {accepted.length === 0
              ? renderEmpty("No accepted trades awaiting processing.")
              : accepted.map((t) => <TradeCard key={t.id} trade={t} viewMode={viewMode} />)}
          </TabsContent>

          <TabsContent value="processed" className="space-y-4">
            {processed.length === 0
              ? renderEmpty("No processed trades yet. Trades appear here once they have executed.")
              : processed.map((t) => <TradeCard key={t.id} trade={t} viewMode={viewMode} />)}
          </TabsContent>

          <TabsContent value="all" className="space-y-4">
            {all.length === 0
              ? renderEmpty("No trades yet in this league. When managers propose trades they will appear here.")
              : all.map((t) => <TradeCard key={t.id} trade={t} viewMode={viewMode} />)}
          </TabsContent>

          <TabsContent value="conditional" className="space-y-4" data-testid="transactions-conditional-content">
            {conditionalLoading && conditionalTrades === null ? (
              renderEmpty("Loading conditional trades…")
            ) : (conditionalTrades || []).length === 0 ? (
              <Card>
                <CardContent className="py-8 text-center text-muted-foreground" data-testid="conditional-empty">
                  No executed trades with conditions or pick protections yet.
                  <span className="block text-xs mt-2">
                    Conditional trades appear here once they have been accepted and processed.
                  </span>
                </CardContent>
              </Card>
            ) : (
              (conditionalTrades || []).map((t) => {
                // Reuse the mapper used by the other tabs so the asset rows are
                // formatted consistently with the rest of the page.
                const tradeId = t._id || t.id;
                const fromAssets = t.assets_offered || t.from_assets || t.team_a_assets || [];
                const toAssets = t.assets_requested || t.to_assets || t.team_b_assets || [];
                const mapped = {
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
                return (
                  <ConditionalTradeCard
                    key={tradeId}
                    trade={t}
                    mapped={mapped}
                    viewMode={viewMode}
                    subscribedTradeIdxs={subsByTrade[tradeId] || new Set()}
                    onToggleSubscribe={toggleConditionalSubscription}
                  />
                );
              })
            )}
          </TabsContent>

          <TabsContent value="activity" className="space-y-2">
            {activity.length === 0 ? renderEmpty("No recent activity.") : (
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
                      {activity.map((a) => (
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
