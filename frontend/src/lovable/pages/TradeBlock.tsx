// @ts-nocheck
import { useState, useMemo, useEffect } from "react";
import { AppLayout } from "@/components/layout/AppLayout";
import { useActiveLeague } from "@/hooks/use-active-league";
import api from "@/lib/api";
import LeagueContextBanner from "@/lovable/components/dashboard/LeagueContextBanner";
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
import { Plus, ArrowRightLeft, MessageSquare, TrendingUp, TrendingDown, Filter } from "lucide-react";
import { TradeProposalModal } from "@/lovable/components/trade/TradeProposalModal";
import TeamLink from "@/lovable/components/TeamLink";

type ItemType = "player" | "prospect" | "pick";

interface TradeBlockItem {
  id: number;
  name: string;
  position: string;
  team: string;
  age?: number;
  dynastyValue: number;
  owner: string;
  ownerAvatar: string;
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
  const leagueTeamsCount = leagueTeams?.length || 0;

  const [positionFilter, setPositionFilter] = useState("All");
  const [ownerFilter, setOwnerFilter] = useState("All Teams");
  const [tradeModalOpen, setTradeModalOpen] = useState(false);
  const [selectedOwner, setSelectedOwner] = useState("");
  const [selectedOwnerPlayers, setSelectedOwnerPlayers] = useState<any[]>([]);
  const [liveItems, setLiveItems] = useState<any[]>([]);
  const [myRoster, setMyRoster] = useState<any[]>([]);

  // Fetch real trade-block items
  useEffect(() => {
    if (!league?.id) return;
    let cancelled = false;
    api.get(`/trade-block?league_id=${league.id}`).then(({ data }) => {
      if (cancelled) return;
      setLiveItems(Array.isArray(data) ? data : []);
    }).catch(() => {});
    return () => { cancelled = true; };
  }, [league?.id]);

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
  const realTradeItems: TradeBlockItem[] = useMemo(() => (liveItems || []).map((it: any, idx: number) => ({
    id: it._id || idx,
    name: it.name || "Unknown",
    position: it.position || "—",
    team: it.nhl_team || (it.item_type === "pick" ? "Own" : ""),
    age: it.age || undefined,
    dynastyValue: Math.round(((it.points || 0) * 80) + 1000),
    owner: ownerNameFor(it.owner_id),
    ownerAvatar: ownerAbbrFor(it.owner_id),
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

    // Sort: highest performing players → lowest → prospects → picks
    items.sort((a, b) => {
      const typeOrder = { player: 0, prospect: 1, pick: 2 };
      if (typeOrder[a.type] !== typeOrder[b.type]) {
        return typeOrder[a.type] - typeOrder[b.type];
      }
      if (a.type === "player" && b.type === "player") {
        return (b.weeklyPoints || 0) - (a.weeklyPoints || 0);
      }
      return b.dynastyValue - a.dynastyValue;
    });

    return items;
  }, [positionFilter, ownerFilter, realTradeItems]);

  const handleProposeTrade = (owner: string) => {
    const ownerItems = tradeBlockItems
      .filter((item) => item.owner === owner && item.type === "player")
      .map((item) => ({
        id: item.id,
        name: item.name,
        position: item.position,
        team: item.team,
        dynastyValue: item.dynastyValue,
      }));
    setSelectedOwner(owner);
    setSelectedOwnerPlayers(ownerItems);
    setTradeModalOpen(true);
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
              <Badge variant="outline" className="ml-auto">
                {sortedAndFilteredItems.length} items
              </Badge>
            </div>

            <div className="grid gap-4">
              {sortedAndFilteredItems.map((item) => (
                <TradeBlockCard 
                  key={item.id} 
                  item={item} 
                  onProposeTrade={() => handleProposeTrade(item.owner)} 
                />
              ))}
              {sortedAndFilteredItems.length === 0 && (
                <Card className="bg-card border-border">
                  <CardContent className="p-8 text-center text-muted-foreground">
                    No items match your filters
                  </CardContent>
                </Card>
              )}
            </div>
          </TabsContent>

          <TabsContent value="my-players">
            <Card className="bg-card border-border">
              <CardHeader>
                <CardTitle>Manage Your Trade Block</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  {myAvailablePlayers.map((player) => (
                    <div
                      key={player.id}
                      className="flex items-center justify-between p-4 rounded-lg bg-secondary/30 hover:bg-secondary/50 transition-colors"
                    >
                      <div className="flex items-center gap-3">
                        <div className="h-10 w-10 rounded-lg bg-secondary flex items-center justify-center text-xs font-bold">
                          {player.team}
                        </div>
                        <div>
                          <p className="font-medium">{player.name}</p>
                          <p className="text-sm text-muted-foreground">
                            {player.position}
                          </p>
                        </div>
                      </div>
                      <Button variant={player.onBlock ? "destructive" : "outline"} size="sm">
                        {player.onBlock ? "Remove from Block" : "Add to Block"}
                      </Button>
                    </div>
                  ))}
                </div>
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
      />
    </AppLayout>
  );
};

const TradeBlockCard = ({ 
  item, 
  onProposeTrade 
}: { 
  item: TradeBlockItem; 
  onProposeTrade: () => void;
}) => {
  const getTypeLabel = () => {
    if (item.type === "prospect") return "Prospect";
    if (item.type === "pick") return "Draft Pick";
    return null;
  };

  return (
    <Card className="bg-card border-border hover:border-primary/30 transition-colors">
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
              <div className="h-8 w-8 rounded-full bg-secondary flex items-center justify-center text-xs font-bold">
                {item.ownerAvatar}
              </div>
              <span className="text-sm text-muted-foreground"><TeamLink name={item.owner} /></span>
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

export default TradeBlock;
