// @ts-nocheck
import { useState, useEffect } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
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
import { POSITIONS as positions } from "@/lovable/pages/trade-block/mocks";
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
  // Iter 232M.1 — Counter-from-existing-trade deep link. When TradeDetail's
  // Counter button navigates here as `/trade-block?counter_from={id}&with={teamId}`,
  // auto-open the modal with the specified partner pre-selected and thread
  // the trade id into the modal so submit posts to /respond (action=counter).
  const [searchParams, setSearchParams] = useSearchParams();
  const counterFromTradeId = searchParams.get("counter_from");
  const counterWithTeamId = searchParams.get("with");
  useEffect(() => {
    if (!counterFromTradeId || !counterWithTeamId) return;
    const partner = (leagueTeams || []).find((t: any) => t.id === counterWithTeamId);
    if (!partner) return;
    handleProposeTrade(partner.name);
    // We keep the query params so a page reload preserves counter mode.
  }, [counterFromTradeId, counterWithTeamId, leagueTeams?.length]);

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
    // Iter 230ao — Use only LIVE trade-block items as the pool. Mock
    // fallback was removed because it surfaced fake "Connor McDavid"
    // listings in real leagues that didn't actually have anything on
    // the block.
    const pool = realTradeItems.filter((it) => it.owner === owner && it.type === "player");
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
        onOpenChange={(open) => {
          setTradeModalOpen(open);
          // Clear counter-mode query params when the user closes the modal
          // so the next open (via the normal Trade button) isn't stuck in
          // counter mode.
          if (!open && (counterFromTradeId || counterWithTeamId)) {
            setSearchParams({}, { replace: true });
          }
        }}
        targetTeam={selectedOwner}
        targetPlayers={selectedOwnerPlayers}
        prefilledTheirPlayerIds={prefilledIds}
        leagueId={league?.id}
        targetTeamId={
          counterWithTeamId
          || (leagueTeams || []).find((t: any) => t.name === selectedOwner)?.id
          || null
        }
        myTeamId={myTeam?.id}
        counterFromTradeId={counterFromTradeId}
      />
    </AppLayout>
  );
};


export default TradeBlock;
