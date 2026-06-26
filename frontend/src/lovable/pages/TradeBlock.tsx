// @ts-nocheck
import { useState, useMemo, useEffect } from "react";
import { Link, useNavigate } from "react-router-dom";
import { AppLayout } from "@/components/layout/AppLayout";
import { useActiveLeague } from "@/hooks/use-active-league";
import { useSeasonStreaks, streakChip } from "@/hooks/use-season-streaks";
import { useTradeBlockUiPrefs } from "@/hooks/use-trade-block-ui-prefs";
import { useSocket } from "@/hooks/use-socket";
import { useAuth } from "@/contexts/AuthContext";
import api from "@/lib/api";
import LeagueContextBanner from "@/lovable/components/dashboard/LeagueContextBanner";
import { MinorEligibleBadge } from "@/lovable/components/MinorEligibleBadge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Plus, ArrowRightLeft, MessageSquare, TrendingUp, TrendingDown, Crown,
  X, ArrowUp, ArrowDown, EyeOff,
} from "lucide-react";
import { TradeProposalModal } from "@/lovable/components/trade/TradeProposalModal";
import TeamLink from "@/lovable/components/TeamLink";
import TeamLogo from "@/lovable/components/TeamLogo";
// Iter 207 — Report this user (flag icon next to owner name)
import ReportUserButton from "@/components/ReportUserButton";
// Iter 230 — Tile + List view extracted into their own components.
import TradeBlockCard from "@/lovable/pages/trade-block/TradeBlockCard";
import TradeBlockListView from "@/lovable/pages/trade-block/TradeBlockListView";
// Iter 230i — Types, mocks, MyPlayersTab, FiltersBar extracted.
import type { TradeBlockItem, ItemType } from "@/lovable/pages/trade-block/types";
import { tradeBlockItemsMock as tradeBlockItems, POSITIONS as positions } from "@/lovable/pages/trade-block/mocks";
import MyPlayersTab from "@/lovable/pages/trade-block/MyPlayersTab";
import TradeBlockFiltersBar from "@/lovable/pages/trade-block/TradeBlockFiltersBar";

// Iter 230i — `TradeBlockItem` / `ItemType` types + the static
// `tradeBlockItems` seed array + the `POSITIONS` constant are all
// extracted to `trade-block/types.ts` and `trade-block/mocks.ts`.

const TradeBlock = () => {
  const { league, leagueTeams, myTeam } = useActiveLeague();
  const { user } = useAuth();
  const { streaks } = useSeasonStreaks(league?.id);
  const navigate = useNavigate();
  const leagueTeamsCount = leagueTeams?.length || 0;

  // ── Per-league UI prefs (view mode, hidden players, sort) ──
  // Persisted in localStorage so each league remembers its own setup.
  const prefs = useTradeBlockUiPrefs(league?.id);

  const [positionFilter, setPositionFilter] = useState("All");
  const [ownerFilter, setOwnerFilter] = useState("All Teams");
  const [tradeModalOpen, setTradeModalOpen] = useState(false);
  const [selectedOwner, setSelectedOwner] = useState("");
  const [selectedOwnerPlayers, setSelectedOwnerPlayers] = useState<any[]>([]);
  // The specific player the user clicked Trade on — pre-populated as the
  // "want" side in the proposal modal. Optional; falls back to "show all
  // players from this team" when null (legacy "owner-level" Trade button).
  const [prefilledIds, setPrefilledIds] = useState<number[]>([]);
  const [liveItems, setLiveItems] = useState<any[]>([]);
  const [myRoster, setMyRoster] = useState<any[]>([]);

  // Fetch real trade-block items
  // Iter 228z — Bump a tick to re-fetch whenever a `trade_block_changed`
  // socket event arrives, so the page lights up the instant any league
  // member adds/removes/updates a listing.
  const [tradeBlockTick, setTradeBlockTick] = useState(0);
  useEffect(() => {
    if (!league?.id) return;
    let cancelled = false;
    api.get(`/trade-block?league_id=${league.id}`).then(({ data }) => {
      if (cancelled) return;
      setLiveItems(Array.isArray(data) ? data : []);
    }).catch(() => {});
    return () => { cancelled = true; };
  }, [league?.id, tradeBlockTick]);

  useSocket(
    league?.id ? `league_${league.id}` : null,
    { trade_block_changed: () => setTradeBlockTick((t) => t + 1) },
    user?.id || user?._id,
  );

  // My roster (for "My Players" tab)
  useEffect(() => {
    if (!myTeam?.id) return;
    let cancelled = false;
    api.get(`/roster/${myTeam.id}/detail`).then(({ data }) => {
      if (!cancelled) setMyRoster(data?.players || []);
    }).catch(() => {});
    return () => { cancelled = true; };
  }, [myTeam?.id]);

  // Map backend trade-block rows into the card shape expected by the UI
  const ownerNameFor = (ownerId: string) => {
    const t = (leagueTeams || []).find(tt => tt.owner_id === ownerId);
    return t?.name || "Unknown";
  };
  const ownerAbbrFor = (ownerId: string) => {
    const t = (leagueTeams || []).find(tt => tt.owner_id === ownerId);
    return t?.logo_abbr || "TBD";
  };
  // Iter 229k — Surface the owner team's preset theme color so the
  // trade-block owner chip renders in their brand tint (matches Standings).
  const ownerThemeColorFor = (ownerId: string) => {
    const t = (leagueTeams || []).find(tt => tt.owner_id === ownerId);
    return t?.theme_color || null;
  };
  const realTradeItems: TradeBlockItem[] = useMemo(() => (liveItems || []).map((it: any, idx: number) => ({
    id: it._id || idx,
    name: it.name || "Unknown",
    position: it.position || "—",
    team: it.nhl_team || (it.item_type === "pick" ? "Own" : ""),
    team_id: it.team_id,
    age: it.age || undefined,
    aav: it.aav || null,
    dynastyValue: Math.round(((it.points || 0) * 80) + 1000),
    owner: ownerNameFor(it.owner_id),
    owner_id: it.owner_id,
    ownerAvatar: ownerAbbrFor(it.owner_id),
    ownerThemeColor: ownerThemeColorFor(it.owner_id),
    lookingFor: (it.looking_for || []).length ? it.looking_for : ["Best Offer"],
    trend: "stable" as const,
    weeklyPoints: 0,
    type: (it.item_type || "player") as ItemType,
    year: it.pick_year,
    round: it.pick_round,
    gp: it.games_played, g: it.goals, a: it.assists,
    plusMinus: it.plus_minus,
    sog: it.points, // placeholder; real sog not stored on trade-block row
  })), [liveItems, leagueTeams]);

  // Dynamic owner list from real leagueTeams
  const realOwners = useMemo(
    () => ["All Teams", ...((leagueTeams || []).map(t => t.name))],
    [leagueTeams]
  );

  // ── "My Players" tab data ──
  // Single source of truth: backend `db.trade_block`. We surface ONLY this
  // user's currently-listed players (filtered by owner_id) so the tab is in
  // lockstep with the roster-page bullhorn toggle. When a trade executes,
  // the backend wipes those rows, so this list updates automatically.
  const myOnBlockPlayers = useMemo(() => {
    if (!myTeam?.id) return [];
    const rosterById = new Map((myRoster || []).map((p: any) => [String(p.player_id || p.id), p]));
    return (liveItems || [])
      .filter((it: any) => it.team_id === myTeam.id && it.player_id)
      .map((it: any) => {
        const r = rosterById.get(String(it.player_id));
        return {
          id: it._id || it.player_id,
          player_id: String(it.player_id),
          name: it.name || r?.name || "Unknown",
          position: it.position || r?.position || "—",
          team: it.nhl_team || r?.nhl_team || "",
          nhl_team: r?.nhl_team,
          lookingFor: it.looking_for || [],
        };
      });
  }, [liveItems, myRoster, myTeam?.id]);

  const sortedAndFilteredItems = useMemo(() => {
    // Prefer live items; fall back to seeded mock when league has no trade-block entries
    let items = realTradeItems.length > 0 ? [...realTradeItems] : [...tradeBlockItems];

    // Filter by position
    if (positionFilter !== "All") {
      if (positionFilter === "Prospect") {
        items = items.filter((item) => item.type === "prospect");
      } else if (positionFilter === "Pick") {
        items = items.filter((item) => item.type === "pick");
      } else {
        items = items.filter((item) => item.position === positionFilter && item.type === "player");
      }
    }

    // Filter by owner
    if (ownerFilter !== "All Teams") {
      items = items.filter((item) => item.owner === ownerFilter);
    }

    // ── Sort ──
    // List view: respect the user's chosen sort key + direction.
    // Tile view: always use the default highest-FP → prospect → pick ordering
    //   (sortable columns only make sense in list/table view).
    if (prefs.viewMode === "list") {
      const { key, dir } = prefs.sort || { key: "weeklyPoints", dir: "desc" };
      const factor = dir === "asc" ? 1 : -1;
      items.sort((a, b) => {
        const av = a[key];
        const bv = b[key];
        if (typeof av === "string" || typeof bv === "string") {
          return String(av || "").localeCompare(String(bv || "")) * factor;
        }
        return ((av ?? 0) - (bv ?? 0)) * factor;
      });
    } else {
      const typeOrder = { player: 0, prospect: 1, pick: 2 };
      items.sort((a, b) => {
        if (typeOrder[a.type] !== typeOrder[b.type]) {
          return typeOrder[a.type] - typeOrder[b.type];
        }
        if (a.type === "player" && b.type === "player") {
          return (b.weeklyPoints || 0) - (a.weeklyPoints || 0);
        }
        return b.dynastyValue - a.dynastyValue;
      });
    }

    return items;
  }, [positionFilter, ownerFilter, realTradeItems, prefs.viewMode, prefs.sort]);

  // Tile view honors the per-league hidden list; list view always shows all.
  const visibleItems = useMemo(() => {
    if (prefs.viewMode !== "tile") return sortedAndFilteredItems;
    return sortedAndFilteredItems.filter((it) => !prefs.isHidden(it.id));
  }, [sortedAndFilteredItems, prefs.viewMode, prefs.hiddenIds]);

  const hiddenCountAfterFilters = useMemo(() => (
    sortedAndFilteredItems.length - visibleItems.length
  ), [sortedAndFilteredItems, visibleItems]);

  const handleProposeTrade = (owner: string, prefilledItem?: TradeBlockItem) => {
    // Real trade items (preferred) take priority over the seeded mock. The
    // pre-filled player from the per-card Trade button is force-included so
    // even if the owner has nothing else listed, the proposal modal can
    // still target that specific asset.
    const liveItems = realTradeItems.filter((it) => it.owner === owner && it.type === "player");
    const fallback = tradeBlockItems.filter((it) => it.owner === owner && it.type === "player");
    const pool = liveItems.length > 0 ? liveItems : fallback;
    const merged = prefilledItem && !pool.some((p) => p.id === prefilledItem.id)
      ? [prefilledItem, ...pool]
      : pool;
    const ownerItems = merged.map((item) => ({
      id: item.id,
      name: item.name,
      position: item.position,
      team: item.team,
      dynastyValue: item.dynastyValue,
    }));
    setSelectedOwner(owner);
    setSelectedOwnerPlayers(ownerItems);
    setPrefilledIds(prefilledItem ? [prefilledItem.id] : []);
    setTradeModalOpen(true);
  };

  // Trade-from-player-card: navigate to the owner's roster page and open the
  // proposal modal with that exact player pre-checked on the "want" side.
  const handleTradeForPlayer = (item: TradeBlockItem) => {
    const ownerTeam = (leagueTeams || []).find((t: any) => t.name === item.owner);
    handleProposeTrade(item.owner, item);
    if (ownerTeam?.id) navigate(`/teams/${ownerTeam.id}`);
  };

  return (
    <AppLayout>
        <div className="container py-8 space-y-6">
          <LeagueContextBanner title="Trade Block" kpiLabel="Teams on block" kpiValue={leagueTeamsCount} primaryHref="/transactions" primaryLabel="Full transactions log" />
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold">Trade Block</h1>
            <p className="text-muted-foreground">Players available for trade across the league</p>
          </div>
          <Button className="bg-primary hover:bg-primary/90">
            <Plus className="h-4 w-4 mr-2" />
            Add to Trade Block
          </Button>
        </div>

        <Tabs defaultValue="league" className="space-y-4">
          <TabsList className="bg-secondary">
            <TabsTrigger value="league">League Trade Block</TabsTrigger>
            <TabsTrigger value="my-players">My Players</TabsTrigger>
          </TabsList>

          <TabsContent value="league">
            {/* Iter 230i — Filters + view-toggle bar extracted. */}
            <TradeBlockFiltersBar
              positions={positions}
              realOwners={realOwners}
              positionFilter={positionFilter}
              setPositionFilter={setPositionFilter}
              ownerFilter={ownerFilter}
              setOwnerFilter={setOwnerFilter}
              visibleCount={visibleItems.length}
              hiddenCountAfterFilters={hiddenCountAfterFilters}
              viewMode={prefs.viewMode}
              setViewMode={prefs.setViewMode}
              hiddenIds={prefs.hiddenIds}
              clearHidden={prefs.clearHidden}
            />

            {prefs.viewMode === "list" ? (
              <TradeBlockListView
                items={visibleItems}
                sort={prefs.sort}
                onToggleSort={prefs.toggleSort}
                onTrade={handleTradeForPlayer}
                onHide={prefs.hide}
                capEnabled={Boolean(league?.salary_cap_enabled)}
                capColumnLabel={"AAV"}
              />
            ) : (
              <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3" data-testid="trade-block-tile-grid">
                {visibleItems.map((item) => (
                  <TradeBlockCard
                    key={item.id}
                    item={item}
                    streakChipData={item.team_id ? streakChip(streaks?.[item.team_id]?.active) : null}
                    onProposeTrade={() => handleTradeForPlayer(item)}
                    onHide={() => prefs.hide(item.id)}
                  />
                ))}
                {visibleItems.length === 0 && (
                  <Card className="bg-card border-border sm:col-span-2 xl:col-span-3">
                    <CardContent className="p-8 text-center text-muted-foreground">
                      {hiddenCountAfterFilters > 0
                        ? "All matching items are hidden. Click 'Show hidden' above to reveal them."
                        : "No items match your filters"}
                    </CardContent>
                  </Card>
                )}
              </div>
            )}
          </TabsContent>

          <TabsContent value="my-players">
            {/* Iter 230i — My Players tab extracted. */}
            <MyPlayersTab players={myOnBlockPlayers} myTeam={myTeam} />
          </TabsContent>
        </Tabs>
      </div>

      <TradeProposalModal
        open={tradeModalOpen}
        onOpenChange={setTradeModalOpen}
        targetTeam={selectedOwner}
        targetPlayers={selectedOwnerPlayers}
        prefilledTheirPlayerIds={prefilledIds}
      />
    </AppLayout>
  );
};


export default TradeBlock;
