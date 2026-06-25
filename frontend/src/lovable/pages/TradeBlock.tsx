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
  Plus, ArrowRightLeft, MessageSquare, TrendingUp, TrendingDown, Filter, Crown,
  LayoutGrid, List as ListIcon, X, ArrowUp, ArrowDown, EyeOff, Eye,
} from "lucide-react";
import { TradeProposalModal } from "@/lovable/components/trade/TradeProposalModal";
import TeamLink from "@/lovable/components/TeamLink";
import TeamLogo from "@/lovable/components/TeamLogo";
// Iter 207 — Report this user (flag icon next to owner name)
import ReportUserButton from "@/components/ReportUserButton";

type ItemType = "player" | "prospect" | "pick";

interface TradeBlockItem {
  id: number;
  name: string;
  position: string;
  team: string;
  team_id?: string;
  age?: number;
  dynastyValue: number;
  aav?: number | null;
  owner: string;
  owner_id?: string;
  ownerAvatar: string;
  // Iter 229k — Owner team's preset theme color (hex).
  ownerThemeColor?: string | null;
  lookingFor: string[];
  trend: "up" | "down" | "stable";
  weeklyPoints?: number;
  type: ItemType;
  year?: number;
  round?: string;
  // Skater stats
  gp?: number;
  g?: number;
  a?: number;
  plusMinus?: number;
  ppp?: number;
  shp?: number;
  gwg?: number;
  sog?: number;
  hit?: number;
  blk?: number;
  fow?: number;
  fol?: number;
  // Goalie stats
  w?: number;
  l?: number;
  sol?: number;
  sv?: number;
  ga?: number;
  so?: number;
}

const tradeBlockItems: TradeBlockItem[] = [
  {
    id: 1,
    name: "Adam Fox",
    position: "D",
    team: "NYR",
    age: 25,
    dynastyValue: 8500,
    owner: "Frozen Thunder",
    ownerAvatar: "FT",
    lookingFor: ["Young D-man", "Multiple Assets"],
    trend: "up",
    weeklyPoints: 42.5,
    type: "player",
    gp: 52, g: 8, a: 36, plusMinus: 14, ppp: 10, shp: 0, gwg: 2, sog: 124, hit: 42, blk: 88, fow: 0, fol: 0,
  },
  {
    id: 2,
    name: "Mitch Marner",
    position: "RW",
    team: "TOR",
    age: 26,
    dynastyValue: 7800,
    owner: "Glacier Kings",
    ownerAvatar: "GK",
    lookingFor: ["Elite Center", "2+ Picks"],
    trend: "up",
    weeklyPoints: 38.2,
    type: "player",
    gp: 50, g: 14, a: 42, plusMinus: 8, ppp: 16, shp: 1, gwg: 3, sog: 132, hit: 22, blk: 16, fow: 0, fol: 0,
  },
  {
    id: 3,
    name: "Sidney Crosby",
    position: "C",
    team: "PIT",
    age: 36,
    dynastyValue: 5100,
    owner: "Puck Masters",
    ownerAvatar: "PM",
    lookingFor: ["1st Round Pick", "Proven Scorer"],
    trend: "stable",
    weeklyPoints: 28.7,
    type: "player",
    gp: 48, g: 18, a: 30, plusMinus: 6, ppp: 12, shp: 0, gwg: 5, sog: 168, hit: 36, blk: 12, fow: 528, fol: 396,
  },
  {
    id: 4,
    name: "Alex Ovechkin",
    position: "LW",
    team: "WSH",
    age: 38,
    dynastyValue: 4200,
    owner: "Ice Crushers",
    ownerAvatar: "IC",
    lookingFor: ["Draft Picks", "Young Forwards"],
    trend: "down",
    weeklyPoints: 22.1,
    type: "player",
    gp: 44, g: 24, a: 12, plusMinus: -4, ppp: 10, shp: 2, gwg: 4, sog: 210, hit: 86, blk: 8, fow: 0, fol: 0,
  },
  {
    id: 5,
    name: "Connor Bedard",
    position: "C",
    team: "CHI",
    age: 18,
    dynastyValue: 6500,
    owner: "Blizzard FC",
    ownerAvatar: "BF",
    lookingFor: ["Established Star", "Picks"],
    trend: "up",
    weeklyPoints: 0,
    type: "prospect",
  },
  {
    id: 6,
    name: "Matvei Michkov",
    position: "RW",
    team: "PHI",
    age: 19,
    dynastyValue: 5800,
    owner: "Ice Crushers",
    ownerAvatar: "IC",
    lookingFor: ["NHL Ready Forward"],
    trend: "up",
    weeklyPoints: 0,
    type: "prospect",
  },
  {
    id: 7,
    name: "2025 1st Round",
    position: "Pick",
    team: "Own",
    dynastyValue: 3500,
    owner: "Glacier Kings",
    ownerAvatar: "GK",
    lookingFor: ["Young Player"],
    trend: "stable",
    type: "pick",
    year: 2025,
    round: "1st",
  },
  {
    id: 8,
    name: "2025 2nd Round",
    position: "Pick",
    team: "Own",
    dynastyValue: 1800,
    owner: "Puck Masters",
    ownerAvatar: "PM",
    lookingFor: ["Depth Player"],
    trend: "stable",
    type: "pick",
    year: 2025,
    round: "2nd",
  },
];

const myAvailablePlayers = [
  { id: 1, name: "Nathan MacKinnon", position: "C", team: "COL", dynastyValue: 9200, onBlock: false },
  { id: 2, name: "Cale Makar", position: "D", team: "COL", dynastyValue: 9500, onBlock: false },
  { id: 3, name: "Igor Shesterkin", position: "G", team: "NYR", dynastyValue: 7200, onBlock: true },
];

const positions = ["All", "C", "LW", "RW", "D", "G", "Prospect", "Pick"];
const owners = ["All Teams", "Frozen Thunder", "Glacier Kings", "Puck Masters", "Ice Crushers", "Blizzard FC"];

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
            {/* Filters */}
            <div className="flex items-center gap-4 mb-4">
              <div className="flex items-center gap-2">
                <Filter className="h-4 w-4 text-muted-foreground" />
                <span className="text-sm text-muted-foreground">Filter:</span>
              </div>
              <Select value={positionFilter} onValueChange={setPositionFilter}>
                <SelectTrigger className="w-36 bg-secondary border-border">
                  <SelectValue placeholder="Position" />
                </SelectTrigger>
                <SelectContent>
                  {positions.map((pos) => (
                    <SelectItem key={pos} value={pos}>
                      {pos === "All" ? "All Positions" : pos}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Select value={ownerFilter} onValueChange={setOwnerFilter}>
                <SelectTrigger className="w-44 bg-secondary border-border" data-testid="trade-block-owner-filter">
                  <SelectValue placeholder="Team" />
                </SelectTrigger>
                <SelectContent>
                  {realOwners.map((owner) => (
                    <SelectItem key={owner} value={owner}>
                      {owner}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Badge variant="outline" className="ml-auto" data-testid="trade-block-count">
                {visibleItems.length} items{hiddenCountAfterFilters > 0 && (
                  <span className="ml-1 text-muted-foreground/70">· {hiddenCountAfterFilters} hidden</span>
                )}
              </Badge>
              {/* View toggle — list ↔ tile. Selection persists per-league. */}
              <div
                className="inline-flex items-center rounded-md border border-border bg-secondary/40 overflow-hidden"
                data-testid="trade-block-view-toggle"
              >
                <button
                  type="button"
                  onClick={() => prefs.setViewMode("tile")}
                  data-testid="trade-block-view-tile"
                  aria-pressed={prefs.viewMode === "tile"}
                  className={`flex items-center gap-1 px-2.5 py-1 text-xs ${prefs.viewMode === "tile" ? "bg-primary/15 text-primary" : "text-muted-foreground hover:text-foreground"}`}
                  title="Tile view"
                >
                  <LayoutGrid className="h-3.5 w-3.5" /> Tile
                </button>
                <button
                  type="button"
                  onClick={() => prefs.setViewMode("list")}
                  data-testid="trade-block-view-list"
                  aria-pressed={prefs.viewMode === "list"}
                  className={`flex items-center gap-1 px-2.5 py-1 text-xs border-l border-border ${prefs.viewMode === "list" ? "bg-primary/15 text-primary" : "text-muted-foreground hover:text-foreground"}`}
                  title="List view"
                >
                  <ListIcon className="h-3.5 w-3.5" /> List
                </button>
              </div>
              {prefs.viewMode === "tile" && prefs.hiddenIds.length > 0 && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={prefs.clearHidden}
                  data-testid="trade-block-show-hidden"
                  className="text-xs h-7"
                >
                  <Eye className="h-3.5 w-3.5 mr-1" />
                  Show {prefs.hiddenIds.length} hidden
                </Button>
              )}
            </div>

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
            <Card className="bg-card border-border">
              <CardHeader className="flex flex-row items-start justify-between gap-2">
                <div>
                  <CardTitle>My Trade-Block Players</CardTitle>
                  <p className="text-xs text-muted-foreground mt-1">
                    Players you've shopped from your roster. To add or remove
                    listings, use the trade-block toggle on the{" "}
                    {myTeam ? (
                      <Link
                        to={`/teams/${myTeam.id}`}
                        className="text-primary hover:underline"
                        data-testid="my-players-roster-link"
                      >
                        Roster page
                      </Link>
                    ) : "Roster page"}
                    .
                  </p>
                </div>
                <Badge variant="outline" data-testid="my-players-count">
                  {myOnBlockPlayers.length} on block
                </Badge>
              </CardHeader>
              <CardContent>
                {myOnBlockPlayers.length === 0 ? (
                  <div
                    className="text-center py-10 text-sm text-muted-foreground"
                    data-testid="my-players-empty"
                  >
                    None of your players are on the trade block yet.
                    <div className="mt-2">
                      {myTeam && (
                        <Button asChild variant="outline" size="sm">
                          <Link
                            to={`/teams/${myTeam.id}`}
                            data-testid="my-players-go-to-roster"
                          >
                            Go to Roster →
                          </Link>
                        </Button>
                      )}
                    </div>
                  </div>
                ) : (
                  <div className="space-y-3">
                    {myOnBlockPlayers.map((player: any) => (
                      <div
                        key={player.id}
                        data-testid={`my-players-row-${player.id}`}
                        className="flex items-center justify-between p-4 rounded-lg bg-secondary/30 hover:bg-secondary/50 transition-colors"
                      >
                        <div className="flex items-center gap-3 min-w-0 flex-1">
                          <div className="h-10 w-10 rounded-lg bg-secondary flex items-center justify-center text-xs font-bold shrink-0">
                            {player.team || player.nhl_team || "?"}
                          </div>
                          <div className="min-w-0">
                            <p className="font-medium truncate flex items-center gap-1.5">
                              {player.name}
                              <MinorEligibleBadge eligible={(player as any).minor_eligible || (player as any).player_type === "prospect"} />
                            </p>
                            <p className="text-sm text-muted-foreground flex flex-wrap items-center gap-1">
                              <span>{player.position}</span>
                              {(player.lookingFor || []).length > 0 && (
                                <>
                                  <span className="text-muted-foreground/60">·</span>
                                  <span className="text-xs">Looking for:</span>
                                  {(player.lookingFor || []).slice(0, 3).map((r: string, i: number) => (
                                    <Badge key={i} variant="secondary" className="text-[10px] py-0 px-1.5">{r}</Badge>
                                  ))}
                                </>
                              )}
                            </p>
                          </div>
                        </div>
                        <Button asChild variant="outline" size="sm" data-testid={`my-players-manage-${player.id}`}>
                          <Link to={`/teams/${myTeam?.id}`}>Manage on Roster →</Link>
                        </Button>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
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

const TradeBlockCard = ({
  item,
  onProposeTrade,
  onHide,
  streakChipData,
}: {
  item: TradeBlockItem;
  onProposeTrade: () => void;
  onHide?: () => void;
  streakChipData?: { emoji: string; label: string; count: number; tone: string } | null;
}) => {
  const getTypeLabel = () => {
    if (item.type === "prospect") return "Prospect";
    if (item.type === "pick") return "Draft Pick";
    return null;
  };

  return (
    <Card className="bg-card border-border hover:border-primary/30 transition-colors relative">
      {onHide && (
        <button
          type="button"
          onClick={(e) => { e.stopPropagation(); onHide(); }}
          className="absolute top-2 right-2 z-10 h-6 w-6 rounded-md text-muted-foreground/60 hover:text-foreground hover:bg-secondary flex items-center justify-center transition-colors"
          title="Hide this player from the Trade Block"
          aria-label="Hide from Trade Block"
          data-testid={`trade-block-hide-${item.id}`}
        >
          <X className="h-3.5 w-3.5" />
        </button>
      )}
      <CardContent className="p-6">
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-start gap-4">
            <div className="h-14 w-14 rounded-lg bg-gradient-to-br from-secondary to-muted flex items-center justify-center text-sm font-bold">
              {item.type === "pick" ? "📋" : item.team}
            </div>

            <div>
              <div className="flex items-center gap-2 mb-1">
                <h3 className="font-semibold text-lg">{item.name}</h3>
                {item.trend === "up" && <TrendingUp className="h-4 w-4 text-success" />}
                {item.trend === "down" && <TrendingDown className="h-4 w-4 text-destructive" />}
                {getTypeLabel() && (
                  <Badge variant="secondary" className="text-xs">
                    {getTypeLabel()}
                  </Badge>
                )}
              </div>

              <div className="flex items-center gap-3 text-sm text-muted-foreground mb-3">
                <span>{item.position}</span>
                {item.team !== "Own" && (
                  <>
                    <span>•</span>
                    <span>{item.team}</span>
                  </>
                )}
                {item.age && (
                  <>
                    <span>•</span>
                    <span>Age {item.age}</span>
                  </>
                )}
                {item.weeklyPoints !== undefined && item.weeklyPoints > 0 && (
                  <>
                    <span>•</span>
                    <span className="text-primary">{item.weeklyPoints} pts/wk</span>
                  </>
                )}
              </div>

              {item.type === "player" && item.gp !== undefined && (
                <div className="text-xs text-muted-foreground mb-3 flex flex-wrap gap-x-3 gap-y-1">
                  {item.position === "G" ? (
                    <>
                      <span>GP {item.gp}</span>
                      <span>{item.w}W</span>
                      <span>{item.l}L</span>
                      <span>{item.sol}SOL</span>
                      <span>{item.sv}SV</span>
                      <span>{item.ga}GA</span>
                      <span>{item.so}SO</span>
                    </>
                  ) : (
                    <>
                      <span>GP {item.gp}</span>
                      <span>{item.g}G</span>
                      <span>{item.a}A</span>
                      <span>{(item.plusMinus ?? 0) >= 0 ? '+' : ''}{item.plusMinus}</span>
                      <span>{item.ppp}PPP</span>
                      <span>{item.shp}SHP</span>
                      <span>{item.gwg}GWG</span>
                      <span>{item.sog}SOG</span>
                      <span>{item.hit}HIT</span>
                      <span>{item.blk}BLK</span>
                      <span>{item.fow}FOW</span>
                      <span>{item.fol}FOL</span>
                    </>
                  )}
                </div>
              )}

              <div className="flex flex-wrap gap-2">
                <span className="text-xs text-muted-foreground">Looking for:</span>
                {item.lookingFor.map((req, idx) => (
                  <Badge key={idx} variant="outline" className="bg-secondary/50">
                    {req}
                  </Badge>
                ))}
              </div>
            </div>
          </div>

          <div className="flex flex-col items-end gap-3">
            <div className="flex items-center gap-2">
              {/* Iter 229k — Owner chip uses the team's saved theme_color */}
              <TeamLogo
                name={item.owner}
                abbr={item.ownerAvatar}
                themeColor={item.ownerThemeColor}
                size="sm"
                className="rounded-full"
              />
              <span className="text-sm text-muted-foreground"><TeamLink name={item.owner} /></span>
              {/* Iter 207 — Report this trade-block owner */}
              {item.owner_id && (
                <ReportUserButton
                  targetUserId={item.owner_id}
                  targetUserEmail={item.owner}
                  targetTeamId={item.team_id}
                  contextUrl={`/trade-block#item-${item.id}`}
                />
              )}
              {item.team_id && (
                <Link
                  to={`/trophy-room/team/${item.team_id}`}
                  title={`${item.owner} trophy room`}
                  data-testid={`trade-block-trophy-link-${item.team_id}`}
                  className="text-amber-400/70 hover:text-amber-300 inline-flex"
                >
                  <Crown className="h-4 w-4" />
                </Link>
              )}
              {streakChipData && (
                <span
                  data-testid={`trade-block-streak-chip-${item.team_id}`}
                  title={`${streakChipData.count} consecutive ${streakChipData.label === "Hot" ? "winning" : "losing"} seasons`}
                  className={`inline-flex items-center justify-center gap-1 text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded-full border whitespace-nowrap leading-none ${
                    streakChipData.tone === "hot"
                      ? "bg-orange-500/20 text-orange-300 border-orange-400/40"
                      : "bg-sky-500/20 text-sky-200 border-sky-400/40"
                  }`}
                >
                  <span aria-hidden="true">{streakChipData.emoji}</span>
                  <span>{streakChipData.label}</span>
                  <span className="tabular-nums">{streakChipData.count}</span>
                </span>
              )}
            </div>

            <div className="flex gap-2">
              <Button variant="outline" size="sm">
                <MessageSquare className="h-4 w-4 mr-2" />
                Message
              </Button>
              <Button 
                size="sm" 
                className="bg-primary hover:bg-primary/90"
                onClick={onProposeTrade}
                data-testid={`trade-block-trade-btn-${item.id}`}
                title={`Trade for ${item.name} — opens proposal pre-filled with this player`}
              >
                <ArrowRightLeft className="h-4 w-4 mr-2" />
                Trade
              </Button>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
};

const TradeBlockListView = ({
  items,
  sort,
  onToggleSort,
  onTrade,
  onHide,
  capEnabled,
  capColumnLabel,
}: {
  items: TradeBlockItem[];
  sort: { key: string; dir: "asc" | "desc" };
  onToggleSort: (key: string) => void;
  onTrade: (item: TradeBlockItem) => void;
  onHide: (id: any) => void;
  capEnabled: boolean;
  capColumnLabel: string;
}) => {
  // Column set is computed per render so we can drop the cap column when the
  // active league has no salary cap configured.
  const columns: { key: string; label: string; numeric: boolean; testid: string }[] = [
    { key: "name", label: "Player", numeric: false, testid: "trade-block-col-name" },
    { key: "position", label: "Pos", numeric: false, testid: "trade-block-col-position" },
    { key: "team", label: "Team", numeric: false, testid: "trade-block-col-team" },
    { key: "age", label: "Age", numeric: true, testid: "trade-block-col-age" },
    { key: "weeklyPoints", label: "Pts/Wk", numeric: true, testid: "trade-block-col-weekly" },
    ...(capEnabled ? [{ key: "aav", label: capColumnLabel, numeric: true, testid: "trade-block-col-aav" }] : []),
    { key: "owner", label: "Owner", numeric: false, testid: "trade-block-col-owner" },
    { key: "lookingFor", label: "Looking For", numeric: false, testid: "trade-block-col-looking-for" },
  ];

  const fmtCurrency = (v: number | null | undefined) => {
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
                <TableCell>{item.team}</TableCell>
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

export default TradeBlock;
