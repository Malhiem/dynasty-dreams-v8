// @ts-nocheck
import { useState, useCallback, useEffect, useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import { AppLayout } from "@/components/layout/AppLayout";
import PlayerRoster from "@/lovable/components/dashboard/PlayerRoster";
import LiveTeamHeader from "@/lovable/components/dashboard/LiveTeamHeader";
import TeamDraftPicks from "@/lovable/components/dashboard/TeamDraftPicks";
import TeamSalaryCap from "@/lovable/components/dashboard/TeamSalaryCap";
import CommissionerPendingTrades from "@/lovable/components/dashboard/CommissionerPendingTrades";
import StatCard from "@/lovable/components/dashboard/StatCard";
import { Trophy, TrendingUp, Users, Shield, ArrowRightLeft, X, AlertTriangle, DollarSign, UserMinus, UserPlus } from "lucide-react";
import TeamLogo from "@/lovable/components/TeamLogo";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { useActiveLeague } from "@/hooks/use-active-league";
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

interface TradeAssetState {
  player: TradePlayer;
  retainSalary: boolean;
  retainedPercentage: number;
}

const Team = () => {
  const [searchParams] = useSearchParams();
  const { leagueTeams, myTeam } = useActiveLeague();

  // Shape real teams into the { id, name, abbr, owner } format the Lovable UI expects
  const allTeams = useMemo(() => {
    const list = (leagueTeams || []).map(t => ({
      id: t.id,
      name: t.name,
      abbr: t.logo_abbr || t.name?.slice(0, 3).toUpperCase() || "TBD",
      owner: t.owner_name || "—",
      wins: t.wins || 0,
      losses: t.losses || 0,
      ties: t.ties || 0,
      points_for: t.points_for || 0,
      live_points: t.live_points || 0,
      roster_count: (t.roster || []).length,
      owner_id: t.owner_id,
    }));
    return list;
  }, [leagueTeams]);

  const myTeamId = myTeam?.id;

  const [selectedTeamId, setSelectedTeamId] = useState<string | null>(null);

  // Resolve initial team: ?team query param, else my team, else first team
  useEffect(() => {
    if (!allTeams.length) return;
    const teamParam = searchParams.get("team");
    if (teamParam) {
      // Allow either raw id or slugified name
      const found = allTeams.find(
        t => t.id === teamParam ||
             t.name.toLowerCase().replace(/\s+/g, "-") === teamParam.toLowerCase()
      );
      if (found) {
        setSelectedTeamId(found.id);
        return;
      }
    }
    if (!selectedTeamId || !allTeams.some(t => t.id === selectedTeamId)) {
      setSelectedTeamId(myTeamId || allTeams[0].id);
    }
  }, [allTeams, myTeamId, searchParams]); // eslint-disable-line

  const [commissionerMode, setCommissionerMode] = useState(false);
  const [tradeBannerDismissed, setTradeBannerDismissed] = useState(false);

  const selectedTeam = allTeams.find(t => t.id === selectedTeamId) || null;
  const isOwnTeam = selectedTeamId && selectedTeamId === myTeamId;

  // Rank among all teams by season points + live fpts
  const rank = useMemo(() => {
    if (!selectedTeam || !allTeams.length) return "—";
    const ranked = [...allTeams].sort((a, b) =>
      (b.points_for + b.live_points) - (a.points_for + a.live_points)
    );
    const idx = ranked.findIndex(t => t.id === selectedTeam.id);
    return idx >= 0 ? `#${idx + 1}` : "—";
  }, [selectedTeam, allTeams]);

  const pointsTotal = selectedTeam
    ? Math.round((selectedTeam.points_for || 0) + (selectedTeam.live_points || 0))
    : 0;

  // No real pending trades yet — keep empty so banner hides
  const pendingTrades: any[] = [];

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

  const handleRemovePlayer = useCallback((playerId: number | string) => {
    setTradeAssets(prev => prev.filter(a => a.player.id !== playerId));
  }, []);

  const handleRemovePick = useCallback((pickId: string) => {
    setTradePicks(prev => prev.filter(p => p.id !== pickId));
  }, []);

  const handleToggleRetain = useCallback((playerId: number | string) => {
    setTradeAssets(prev => prev.map(a =>
      a.player.id === playerId ? { ...a, retainSalary: !a.retainSalary, retainedPercentage: a.retainSalary ? 0 : 10 } : a
    ));
  }, []);

  const handleUpdateRetention = useCallback((playerId: number | string, pct: number) => {
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

  const handleTradeFromOtherTeam = useCallback((player: TradePlayer) => {
    if (selectedTeam && !isOwnTeam) {
      setTradePartner(selectedTeam.name);
    }
    handleAddPlayerToTrade(player);
  }, [selectedTeam, isOwnTeam, handleAddPlayerToTrade]);

  const handleTradePickFromOtherTeam = useCallback((pick: TradeDraftPick) => {
    if (selectedTeam && !isOwnTeam) {
      setTradePartner(selectedTeam.name);
    }
    handleAddPickToTrade(pick);
  }, [selectedTeam, isOwnTeam, handleAddPickToTrade]);

  const handleNext = useCallback(() => {
    if (myTeamId) setSelectedTeamId(myTeamId);
  }, [myTeamId]);

  const onTradePlayer = isOwnTeam ? handleAddPlayerToTrade : handleTradeFromOtherTeam;

  if (!allTeams.length || !selectedTeam) {
    return (
      <AppLayout>
        <div className="container py-8">
          <div className="surface p-6 border border-white/5 text-center text-sm text-[#A1A1AA]" data-testid="team-page-empty-state">
            Loading your teams... If this persists, please join or create a league.
          </div>
        </div>
      </AppLayout>
    );
  }

  return (
    <AppLayout>
      <div className="container py-8 space-y-6" data-testid="team-page">
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
                      data-testid="commissioner-mode-switch"
                    />
                  </div>
                </TooltipTrigger>
                <TooltipContent>
                  <p className="text-xs">Enable to edit any team's roster across all scoring periods</p>
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>

            <Select value={selectedTeamId || undefined} onValueChange={setSelectedTeamId}>
              <SelectTrigger className="w-[240px] bg-secondary border-border" data-testid="team-switcher-select">
                <SelectValue placeholder="Select a team" />
              </SelectTrigger>
              <SelectContent className="bg-popover border-border z-50">
                {allTeams.map((team) => (
                  <SelectItem key={team.id} value={team.id} data-testid={`team-option-${team.id}`}>
                    <span className="flex items-center gap-2">
                      <span className="font-mono text-xs text-muted-foreground w-8">{team.abbr}</span>
                      <span>{team.name}</span>
                      {team.id === myTeamId && (
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
          </div>
        )}

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          <StatCard title="League Rank" value={rank} subtitle={`of ${allTeams.length} teams`} icon={Trophy} highlight />
          <StatCard title="Total Points" value={String(pointsTotal)} subtitle="Season + live" icon={TrendingUp} />
          <StatCard title="Roster Size" value={String(selectedTeam.roster_count)} subtitle={`${Math.max(0, 25 - selectedTeam.roster_count)} spots open`} icon={Users} />
        </div>

        {commissionerMode && !isOwnTeam && (
          <CommissionerPendingTrades teamId={selectedTeamId} teamName={selectedTeam.name} />
        )}

        <PlayerRoster
          isOwnTeam={!!isOwnTeam}
          commissionerMode={commissionerMode}
          onTradePlayer={onTradePlayer}
          isTradeBuilderOpen={tradeOpen}
          currentTeamContext={isOwnTeam ? "mine" : selectedTeam.name}
          teamId={selectedTeamId as string}
        />

        <TeamSalaryCap />
        <TeamDraftPicks
          onTradePick={isOwnTeam ? handleAddPickToTrade : handleTradePickFromOtherTeam}
          isOwnTeam={!!isOwnTeam}
          currentTeamContext={isOwnTeam ? "mine" : selectedTeam.name}
          teamId={selectedTeamId as string}
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
        myTeamId={myTeamId || ""}
        onNavigateToTeam={setSelectedTeamId}
        onNext={!isOwnTeam ? handleNext : undefined}
      />
    </AppLayout>
  );
};

export default Team;
