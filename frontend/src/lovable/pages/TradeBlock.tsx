// @ts-nocheck
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { AppLayout } from "@/components/layout/AppLayout";
import { useActiveLeague } from "@/hooks/use-active-league";
import { useSeasonStreaks, streakChip } from "@/hooks/use-season-streaks";
import { useTradeBlockUiPrefs } from "@/hooks/use-trade-block-ui-prefs";
import { useAuth } from "@/contexts/AuthContext";
import LeagueContextBanner from "@/lovable/components/dashboard/LeagueContextBanner";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Plus } from "lucide-react";
import { TradeProposalModal } from "@/lovable/components/trade/TradeProposalModal";
// Iter 230 — Tile + List view extracted into their own components.
import TradeBlockCard from "@/lovable/pages/trade-block/TradeBlockCard";
import TradeBlockListView from "@/lovable/pages/trade-block/TradeBlockListView";
// Iter 230i — Types, mocks, MyPlayersTab, FiltersBar extracted.
import type { TradeBlockItem } from "@/lovable/pages/trade-block/types";
import { POSITIONS as positions, tradeBlockItemsMock as tradeBlockItems } from "@/lovable/pages/trade-block/mocks";
import MyPlayersTab from "@/lovable/pages/trade-block/MyPlayersTab";
import TradeBlockFiltersBar from "@/lovable/pages/trade-block/TradeBlockFiltersBar";
// Iter 230j — Data layer + sort/filter pipeline extracted to hooks.
import useTradeBlockData from "@/hooks/use-trade-block-data";
import useTradeBlockSortFilter from "@/hooks/use-trade-block-sort-filter";

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

  // Iter 230j — Data fetching + ownership decoration + derived
  // collections moved into `useTradeBlockData`.
  const { realTradeItems, realOwners, myOnBlockPlayers } = useTradeBlockData({
    leagueId: league?.id,
    leagueTeams,
    myTeamId: myTeam?.id,
    userIdForSocket: user?.id || (user as any)?._id,
  });

  // Iter 230j — Filter + sort + hidden-card pipeline extracted to
  // `useTradeBlockSortFilter`.
  const { sortedAndFilteredItems, visibleItems, hiddenCountAfterFilters } =
    useTradeBlockSortFilter({
      realTradeItems,
      positionFilter,
      ownerFilter,
      viewMode: prefs.viewMode,
      sort: prefs.sort,
      isHidden: prefs.isHidden,
    });

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
    if (ownerTeam?.id) navigate(`/roster?team_id=${ownerTeam.id}`);
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
