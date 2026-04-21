// @ts-nocheck
import { useState, useCallback, useEffect } from "react";
import { useSearchParams } from "react-router-dom";
import { AppLayout } from "@/components/layout/AppLayout";
import PlayerRoster from "@/lovable/components/dashboard/PlayerRoster";
import LiveTeamHeader from "@/lovable/components/dashboard/LiveTeamHeader";
import TeamDraftPicks from "@/lovable/components/dashboard/TeamDraftPicks";
import TeamSalaryCap from "@/lovable/components/dashboard/TeamSalaryCap";
import CommissionerPendingTrades from "@/lovable/components/dashboard/CommissionerPendingTrades";
import StatCard from "@/lovable/components/dashboard/StatCard";
import { Trophy, TrendingUp, Users, Target, Shield, ArrowRightLeft, X, AlertTriangle, DollarSign, UserMinus, UserPlus } from "lucide-react";
import TeamLogo from "@/lovable/components/TeamLogo";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { TradeBuilder } from "@/lovable/components/trade/TradeBuilder";
import type { TradePlayer, TradeDraftPick } from "@/lovable/components/trade/TradeBuilder";
import { toast } from "sonner";

const allTeams = [
  { id: "frostbite", name: "Team Frostbite", abbr: "FRO", owner: "You" },
  { id: "ice-dragons", name: "Ice Dragons", abbr: "ICE", owner: "Alex M." },
  { id: "blazers", name: "Blazers", abbr: "BLZ", owner: "Jordan K." },
  { id: "thunder", name: "Thunder", abbr: "THU", owner: "Chris P." },
  { id: "wolverines", name: "Wolverines", abbr: "WLV", owner: "Sam L." },
  { id: "phoenix", name: "Phoenix", abbr: "PHX", owner: "Taylor R." },
  { id: "storm-chasers", name: "Storm Chasers", abbr: "STM", owner: "Morgan W." },
  { id: "vipers", name: "Vipers", abbr: "VPR", owner: "Casey D." },
  { id: "avalanche", name: "Avalanche", abbr: "AVL", owner: "Riley N." },
  { id: "knights", name: "Knights", abbr: "KNT", owner: "Jamie B." },
  { id: "titans", name: "Titans", abbr: "TTN", owner: "Drew H." },
  { id: "hawks", name: "Hawks", abbr: "HWK", owner: "Pat F." },
  // Teams referenced in schedule, trades, waivers, etc.
  { id: "arctic-wolves", name: "Arctic Wolves", abbr: "ARC", owner: "Quinn S." },
  { id: "glacier-kings", name: "Glacier Kings", abbr: "GLC", owner: "Blake T." },
  { id: "frozen-thunder", name: "Frozen Thunder", abbr: "FTH", owner: "Derek M." },
  { id: "ice-crushers", name: "Ice Crushers", abbr: "ICR", owner: "Avery L." },
  { id: "puck-masters", name: "Puck Masters", abbr: "PKM", owner: "Logan R." },
  { id: "blizzard-brigade", name: "Blizzard Brigade", abbr: "BBR", owner: "Reese K." },
  { id: "snow-storm", name: "Snow Storm", abbr: "SNS", owner: "Skyler J." },
  { id: "frost-giants", name: "Frost Giants", abbr: "FGT", owner: "Dana W." },
  { id: "ice-wolves", name: "Ice Wolves", abbr: "IWV", owner: "Robin C." },
  { id: "northern-lights", name: "Northern Lights", abbr: "NTH", owner: "Frankie P." },
  { id: "blizzard", name: "Blizzard", abbr: "BLI", owner: "Jessie H." },
  { id: "storm-surge", name: "Storm Surge", abbr: "SSG", owner: "Parker D." },
  { id: "ice-breakers", name: "Ice Breakers", abbr: "IBR", owner: "Kendall V." },
  { id: "frozen-assets", name: "Frozen Assets", abbr: "FAS", owner: "Emery G." },
  { id: "puck-dynasty", name: "Puck Dynasty", abbr: "PDY", owner: "Harper N." },
  { id: "hat-trick-heroes", name: "Hat Trick Heroes", abbr: "HTH", owner: "Sage A." },
  { id: "slapshot-kings", name: "Slapshot Kings", abbr: "SLK", owner: "Rowan F." },
  { id: "net-ninjas", name: "Net Ninjas", abbr: "NNJ", owner: "Ellis B." },
  { id: "blue-line-bandits", name: "Blue Line Bandits", abbr: "BLB", owner: "Carey M." },
  { id: "power-play-pros", name: "Power Play Pros", abbr: "PPP", owner: "Finley T." },
  { id: "blizzard-kings", name: "Blizzard Kings", abbr: "BKG", owner: "Ash R." },
  { id: "frozen-fury", name: "Frozen Fury", abbr: "FRZ", owner: "Marley S." },
  { id: "glacier-bears", name: "Glacier Bears", abbr: "GLB", owner: "Lane W." },
  { id: "polar-phantoms", name: "Polar Phantoms", abbr: "POL", owner: "Peyton H." },
  { id: "snow-hawks", name: "Snow Hawks", abbr: "SNW", owner: "River J." },
  { id: "tundra-titans", name: "Tundra Titans", abbr: "TND", owner: "Shay K." },
  { id: "winter-storm", name: "Winter Storm", abbr: "WST", owner: "Jules D." },
  { id: "zero-below", name: "Zero Below", abbr: "ZRO", owner: "Oakley P." },
  { id: "polar-bears", name: "Polar Bears", abbr: "PLB", owner: "Micah G." },
  { id: "blizzard-fc", name: "Blizzard FC", abbr: "BFC", owner: "Tatum L." },
];

const MY_TEAM_ID = "frostbite";

/** Generate fallback stats for teams not explicitly defined */
const getTeamStats = (teamId: string): { rank: string; points: string; value: string; roster: string; spots: string } => {
  const explicit: Record<string, { rank: string; points: string; value: string; roster: string; spots: string }> = {
    frostbite: { rank: "#2", points: "812", value: "52,100", roster: "24", spots: "6 spots available" },
    "ice-dragons": { rank: "#1", points: "845", value: "54,200", roster: "26", spots: "4 spots available" },
    blazers: { rank: "#5", points: "742", value: "48,300", roster: "23", spots: "7 spots available" },
    thunder: { rank: "#3", points: "798", value: "50,100", roster: "25", spots: "5 spots available" },
    wolverines: { rank: "#7", points: "695", value: "44,800", roster: "22", spots: "8 spots available" },
    phoenix: { rank: "#4", points: "765", value: "49,500", roster: "24", spots: "6 spots available" },
    "storm-chasers": { rank: "#6", points: "720", value: "46,200", roster: "25", spots: "5 spots available" },
    vipers: { rank: "#9", points: "658", value: "42,100", roster: "21", spots: "9 spots available" },
    avalanche: { rank: "#8", points: "672", value: "43,500", roster: "23", spots: "7 spots available" },
    knights: { rank: "#10", points: "640", value: "41,000", roster: "22", spots: "8 spots available" },
    titans: { rank: "#11", points: "615", value: "39,800", roster: "20", spots: "10 spots available" },
    hawks: { rank: "#12", points: "590", value: "38,200", roster: "21", spots: "9 spots available" },
  };
  if (explicit[teamId]) return explicit[teamId];
  // Generate deterministic fallback based on team index
  const idx = allTeams.findIndex(t => t.id === teamId);
  const seed = idx >= 0 ? idx : teamId.length;
  const rank = `#${(seed % 20) + 1}`;
  const pts = 550 + ((seed * 37) % 300);
  const val = 35000 + ((seed * 47) % 20000);
  const ros = 20 + (seed % 8);
  return { rank, points: String(pts), value: val.toLocaleString(), roster: String(ros), spots: `${30 - ros} spots available` };
};

const teamStats = Object.fromEntries(allTeams.map(t => [t.id, getTeamStats(t.id)]));

interface TradeAssetState {
  player: TradePlayer;
  retainSalary: boolean;
  retainedPercentage: number;
}

const Team = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const [selectedTeamId, setSelectedTeamId] = useState(() => {
    const teamParam = searchParams.get("team");
    if (teamParam) {
      const found = allTeams.find(t => t.id === teamParam || t.name.toLowerCase().replace(/\s+/g, "-") === teamParam.toLowerCase());
      if (found) return found.id;
    }
    return MY_TEAM_ID;
  });
  const [commissionerMode, setCommissionerMode] = useState(false);
  const [tradeBannerDismissed, setTradeBannerDismissed] = useState(false);

  useEffect(() => {
    const teamParam = searchParams.get("team");
    if (teamParam) {
      const found = allTeams.find(t => t.id === teamParam || t.name.toLowerCase().replace(/\s+/g, "-") === teamParam.toLowerCase());
      if (found && found.id !== selectedTeamId) {
        setSelectedTeamId(found.id);
      }
    }
  }, [searchParams]);

  // Mock pending trade data with roster legality warnings
  const pendingTrades = [
    {
      id: 1,
      from: "Ice Dragons",
      summary: "N. MacKinnon for L. Draisaitl",
      warnings: [
        { type: "cap" as const, message: "Trade puts you $2.3M over the salary cap" },
        { type: "roster" as const, message: "Roster exceeds limit by 1 — must drop a player" },
        { type: "starting" as const, message: "Starting C slot will be empty — must fill position" },
      ],
    },
  ];
  const isOwnTeam = selectedTeamId === MY_TEAM_ID;
  const selectedTeam = allTeams.find((t) => t.id === selectedTeamId)!;
  const stats = teamStats[selectedTeamId] || teamStats.frostbite;

  // ── Trade Builder State ──
  const [tradeOpen, setTradeOpen] = useState(false);
  const [tradeAssets, setTradeAssets] = useState<TradeAssetState[]>([]);
  const [tradePicks, setTradePicks] = useState<TradeDraftPick[]>([]);
  const [tradePartner, setTradePartner] = useState("");

  const handleAddPlayerToTrade = useCallback((player: TradePlayer) => {
    setTradeAssets(prev => {
      if (prev.some(a => a.player.id === player.id)) {
        toast.info(`${player.name} is already in the trade`);
        return prev;
      }
      return [...prev, { player, retainSalary: false, retainedPercentage: 0 }];
    });
    setTradeOpen(true);
  }, []);

  const handleAddPickToTrade = useCallback((pick: TradeDraftPick) => {
    setTradePicks(prev => {
      if (prev.some(p => p.id === pick.id)) {
        toast.info("This pick is already in the trade");
        return prev;
      }
      return [...prev, pick];
    });
    setTradeOpen(true);
  }, []);

  const handleRemovePlayer = useCallback((playerId: number) => {
    setTradeAssets(prev => prev.filter(a => a.player.id !== playerId));
  }, []);

  const handleRemovePick = useCallback((pickId: string) => {
    setTradePicks(prev => prev.filter(p => p.id !== pickId));
  }, []);

  const handleToggleRetain = useCallback((playerId: number) => {
    setTradeAssets(prev => prev.map(a =>
      a.player.id === playerId ? { ...a, retainSalary: !a.retainSalary, retainedPercentage: a.retainSalary ? 0 : 10 } : a
    ));
  }, []);

  const handleUpdateRetention = useCallback((playerId: number, pct: number) => {
    setTradeAssets(prev => prev.map(a =>
      a.player.id === playerId ? { ...a, retainedPercentage: pct } : a
    ));
  }, []);

  const handleCloseTrade = useCallback(() => {
    setTradeOpen(false);
    setTradeAssets([]);
    setTradePicks([]);
    setTradePartner("");
  }, []);

  const handleSendProposal = useCallback(() => {
    toast.success("Trade proposal sent!", { description: `Proposal sent to ${tradePartner}` });
    handleCloseTrade();
  }, [tradePartner, handleCloseTrade]);

  // When viewing another team and clicking trade, auto-set partner but DON'T navigate back
  const handleTradeFromOtherTeam = useCallback((player: TradePlayer) => {
    const viewedTeam = allTeams.find(t => t.id === selectedTeamId);
    if (viewedTeam && !isOwnTeam) {
      setTradePartner(viewedTeam.name);
    }
    handleAddPlayerToTrade(player);
    // No auto-navigate — user clicks "Next" to go back to own roster
  }, [selectedTeamId, isOwnTeam, handleAddPlayerToTrade]);

  const handleTradePickFromOtherTeam = useCallback((pick: TradeDraftPick) => {
    const viewedTeam = allTeams.find(t => t.id === selectedTeamId);
    if (viewedTeam && !isOwnTeam) {
      setTradePartner(viewedTeam.name);
    }
    handleAddPickToTrade(pick);
    // No auto-navigate — user clicks "Next" to go back to own roster
  }, [selectedTeamId, isOwnTeam, handleAddPickToTrade]);

  // "Next" navigates back to the owner's team
  const handleNext = useCallback(() => {
    setSelectedTeamId(MY_TEAM_ID);
  }, []);

  const onTradePlayer = isOwnTeam ? handleAddPlayerToTrade : handleTradeFromOtherTeam;

  return (
    <AppLayout>
      <div className="container py-8 space-y-6">
        <LiveTeamHeader />
        <div className="flex flex-col sm:flex-row sm:items-center gap-4 justify-between">
          <div className="flex items-center gap-4">
            <TeamLogo name={selectedTeam.name} abbr={selectedTeam.abbr} size="lg" />
            <div>
              <h1 className="text-2xl font-bold">
                <span className="text-gradient-ice">{selectedTeam.name}</span>
              </h1>
              <p className="text-muted-foreground">
                {commissionerMode
                  ? `Commissioner Mode · Editing ${selectedTeam.name}`
                  : isOwnTeam
                    ? "Manage your dynasty roster"
                    : `Owner: ${selectedTeam.owner} · View-only (trade available)`}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-4">
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <div className={`flex items-center gap-2 px-3 py-1.5 rounded-lg border transition-colors ${commissionerMode ? 'border-primary bg-primary/10' : 'border-border bg-secondary/50'}`}>
                    <Shield className={`h-4 w-4 ${commissionerMode ? 'text-primary' : 'text-muted-foreground'}`} />
                    <Label htmlFor="commissioner-mode" className={`text-xs font-medium cursor-pointer ${commissionerMode ? 'text-primary' : 'text-muted-foreground'}`}>
                      Commissioner
                    </Label>
                    <Switch
                      id="commissioner-mode"
                      checked={commissionerMode}
                      onCheckedChange={setCommissionerMode}
                      className="scale-90"
                    />
                  </div>
                </TooltipTrigger>
                <TooltipContent>
                  <p className="text-xs">Enable to edit any team's roster across all scoring periods</p>
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>

            <Select value={selectedTeamId} onValueChange={setSelectedTeamId}>
              <SelectTrigger className="w-[220px] bg-secondary border-border">
                <SelectValue placeholder="Select a team" />
              </SelectTrigger>
              <SelectContent className="bg-popover border-border z-50">
                {allTeams.map((team) => (
                  <SelectItem key={team.id} value={team.id}>
                    <span className="flex items-center gap-2">
                      <span className="font-mono text-xs text-muted-foreground w-8">{team.abbr}</span>
                      <span>{team.name}</span>
                      {team.id === MY_TEAM_ID && (
                        <span className="text-[10px] text-primary font-semibold ml-1">(You)</span>
                      )}
                    </span>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>

        {isOwnTeam && pendingTrades.length > 0 && !tradeBannerDismissed && (
          <div className="space-y-2">
            <Alert className="bg-accent/10 border-accent/30">
              <AlertDescription className="flex items-center justify-between">
                <div className="flex items-center gap-2 text-sm">
                  <ArrowRightLeft className="h-4 w-4 text-accent" />
                  <span>
                    <span className="font-semibold text-accent">{pendingTrades.length} pending trade{pendingTrades.length > 1 ? "s" : ""}</span>
                    <span className="text-muted-foreground ml-1.5">— {pendingTrades[0].from}: {pendingTrades[0].summary}</span>
                  </span>
                </div>
                <Button variant="ghost" size="icon" className="h-6 w-6 flex-shrink-0" onClick={() => setTradeBannerDismissed(true)}>
                  <X className="h-3.5 w-3.5" />
                </Button>
              </AlertDescription>
            </Alert>

            {pendingTrades[0].warnings.length > 0 && (
              <div className="flex flex-col gap-1.5 pl-1">
                {pendingTrades[0].warnings.map((warning, idx) => {
                  const icons = {
                    cap: <DollarSign className="h-3.5 w-3.5 text-destructive" />,
                    roster: <UserMinus className="h-3.5 w-3.5 text-destructive" />,
                    starting: <UserPlus className="h-3.5 w-3.5 text-amber-400" />,
                  };
                  const borderColors = {
                    cap: "border-destructive/30 bg-destructive/5",
                    roster: "border-destructive/30 bg-destructive/5",
                    starting: "border-amber-500/30 bg-amber-500/5",
                  };
                  return (
                    <div
                      key={idx}
                      className={`flex items-center gap-2 text-xs px-3 py-2 rounded-md border ${borderColors[warning.type]}`}
                    >
                      <AlertTriangle className="h-3.5 w-3.5 text-destructive flex-shrink-0" />
                      {icons[warning.type]}
                      <span className="text-muted-foreground">{warning.message}</span>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          <StatCard title="League Rank" value={stats.rank} subtitle="of 12 teams" icon={Trophy} trend={{ value: 8, positive: true }} highlight />
          <StatCard title="Total Points" value={stats.points} subtitle="Season total" icon={TrendingUp} trend={{ value: 5.2, positive: true }} />
          <StatCard title="Roster Size" value={stats.roster} subtitle={stats.spots} icon={Users} />
        </div>

        {commissionerMode && !isOwnTeam && (
          <CommissionerPendingTrades teamId={selectedTeamId} teamName={selectedTeam.name} />
        )}

        <PlayerRoster
          isOwnTeam={isOwnTeam}
          commissionerMode={commissionerMode}
          onTradePlayer={onTradePlayer}
          isTradeBuilderOpen={tradeOpen}
          currentTeamContext={isOwnTeam ? "mine" : selectedTeam.name}
          teamId={selectedTeamId}
        />

        <TeamSalaryCap />
        <TeamDraftPicks
          onTradePick={isOwnTeam ? handleAddPickToTrade : handleTradePickFromOtherTeam}
          isOwnTeam={isOwnTeam}
          currentTeamContext={isOwnTeam ? "mine" : selectedTeam.name}
          teamId={selectedTeamId}
        />
      </div>

      <TradeBuilder
        open={tradeOpen}
        onClose={handleCloseTrade}
        assets={tradeAssets}
        picks={tradePicks}
        selectedTeam={tradePartner}
        onSelectTeam={setTradePartner}
        onRemovePlayer={handleRemovePlayer}
        onRemovePick={handleRemovePick}
        onToggleRetain={handleToggleRetain}
        onUpdateRetention={handleUpdateRetention}
        onSendProposal={handleSendProposal}
        teams={allTeams}
        myTeamId={MY_TEAM_ID}
        onNavigateToTeam={setSelectedTeamId}
        onNext={!isOwnTeam ? handleNext : undefined}
      />
    </AppLayout>
  );
};

export default Team;
