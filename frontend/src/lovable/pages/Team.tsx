// @ts-nocheck
import { useState, useCallback, useEffect, useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import { AppLayout } from "@/components/layout/AppLayout";
import api from "@/lib/api";
import PlayerRoster from "@/lovable/components/dashboard/PlayerRoster";
import TradeBlockManager from "@/lovable/components/team/TradeBlockManager";
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
import type { TradePlayer, TradeDraftPick } from "@/lovable/components/trade/TradeBuilder";
import { useTradeBuilder } from "@/lovable/state/TradeBuilderContext";
import { toast } from "sonner";

interface TradeAssetState {
  player: TradePlayer;
  retainSalary: boolean;
  retainedPercentage: number;
}

const Team = () => {
  const [searchParams] = useSearchParams();
  const { league, leagueTeams, myTeam } = useActiveLeague();

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

  // Roster players (for the Trade Block quick-toggle UI)
  const [rosterPlayers, setRosterPlayers] = useState<any[]>([]);
  const [teamRecord, setTeamRecord] = useState<any>(null);
  // Trade-block player IDs for THIS selected team (used to "light up" the
  // bullhorn icon on each row).
  const [tradeBlockPlayerIds, setTradeBlockPlayerIds] = useState<string[]>([]);
  const [tradeBlockReloadKey, setTradeBlockReloadKey] = useState(0);

  useEffect(() => {
    if (!selectedTeamId) { setRosterPlayers([]); setTeamRecord(null); setTradeBlockPlayerIds([]); return; }
    let cancelled = false;
    Promise.all([
      api.get(`/roster/${selectedTeamId}`).catch(() => ({ data: { players: [] } })),
      api.get(`/teams/${selectedTeamId}`).catch(() => ({ data: null })),
      api.get(`/trade-block`, { params: { team_id: selectedTeamId } }).catch(() => ({ data: { items: [] } })),
    ]).then(([rosterRes, teamRes, tbRes]) => {
      if (cancelled) return;
      const players = (rosterRes.data?.players || []).map((p: any) => ({
        id: p.player_id || p.id,
        name: p.name,
        position: p.position,
        nhl_team: p.nhl_team,
      }));
      setRosterPlayers(players);
      setTeamRecord(teamRes.data || null);
      const tbItems = tbRes.data?.items || tbRes.data || [];
      setTradeBlockPlayerIds(
        tbItems.filter((i: any) => i.player_id).map((i: any) => String(i.player_id))
      );
    });
    return () => { cancelled = true; };
  }, [selectedTeamId, tradeBlockReloadKey]);

  // No real pending trades yet — keep empty so banner hides
  const pendingTrades: any[] = [];

  // ── Global Trade Builder (persistent, lives in AppLayout) ──
  const tradeBuilder = useTradeBuilder();

  const ensureTradeOpen = useCallback(() => {
    if (!myTeam?.id || !league?.id) return false;
    if (!tradeBuilder.open) {
      tradeBuilder.openBuilder({
        leagueId: league.id,
        myTeam: {
          id: myTeam.id,
          name: myTeam.name,
          abbr: myTeam.logo_abbr,
          owner_id: myTeam.owner_id,
          owner_name: myTeam.owner_name,
        },
      });
    }
    return true;
  }, [tradeBuilder, myTeam, league]);

  const handleAddPlayerToTrade = useCallback((player: TradePlayer) => {
    if (!ensureTradeOpen()) {
      toast.error("Cannot start a trade right now");
      return;
    }
    // Tag the player with which team they belong to (used by the global builder
    // to group sends by team and route assets correctly in 3+ way trades).
    const ownerTeamId = (player as any).ownerTeamId
      || (player.fromTeam === "mine" ? myTeam?.id : selectedTeamId);
    const ownerTeamName = (player as any).ownerTeamName
      || (ownerTeamId === myTeam?.id ? myTeam?.name : selectedTeam?.name);
    tradeBuilder.addAsset({
      ...player,
      ownerTeamId,
      ownerTeamName,
    });
    // If the asset belongs to a team not yet a partner, ensure we add it
    if (ownerTeamId && ownerTeamId !== myTeam?.id && selectedTeam) {
      tradeBuilder.addPartner({
        id: selectedTeam.id, name: selectedTeam.name,
        logo_abbr: selectedTeam.abbr, owner_id: selectedTeam.owner_id,
      });
    }
  }, [ensureTradeOpen, tradeBuilder, myTeam, selectedTeamId, selectedTeam]);

  const handleAddPickToTrade = useCallback((pick: TradeDraftPick) => {
    if (!ensureTradeOpen()) {
      toast.error("Cannot start a trade right now");
      return;
    }
    const ownerTeamId = (pick as any).ownerTeamId
      || (pick.fromTeam === "mine" ? myTeam?.id : selectedTeamId);
    const ownerTeamName = (pick as any).ownerTeamName
      || (ownerTeamId === myTeam?.id ? myTeam?.name : selectedTeam?.name);
    tradeBuilder.addPick({
      ...pick,
      ownerTeamId,
      ownerTeamName,
      pickId: (pick as any).pickId,
    });
    if (ownerTeamId && ownerTeamId !== myTeam?.id && selectedTeam) {
      tradeBuilder.addPartner({
        id: selectedTeam.id, name: selectedTeam.name,
        logo_abbr: selectedTeam.abbr, owner_id: selectedTeam.owner_id,
      });
    }
  }, [ensureTradeOpen, tradeBuilder, myTeam, selectedTeamId, selectedTeam]);

  const handleTradeFromOtherTeam = useCallback((player: TradePlayer) => {
    handleAddPlayerToTrade(player);
  }, [handleAddPlayerToTrade]);

  const handleTradePickFromOtherTeam = useCallback((pick: TradeDraftPick) => {
    handleAddPickToTrade(pick);
  }, [handleAddPickToTrade]);

  // ── Drop player flow: confirmation toast → POST /api/roster/{id}/drop
  // The dropped player becomes a free agent. Other teams may then claim him
  // via the existing waiver flow (POST /api/waivers/claim) if the league has
  // waivers configured.
  const handleDropPlayer = useCallback((player: any) => {
    if (!isOwnTeam || !selectedTeamId) return;
    const playerId = String(player.id);
    const playerName = player.name;
    const toastId = toast(
      `Drop ${playerName}?`,
      {
        description:
          "Player will be removed from your roster and placed in free agency. " +
          "If your league has waivers enabled, other teams must clear waivers before signing.",
        duration: Infinity,
        action: {
          label: "Confirm Drop",
          onClick: async () => {
            try {
              await api.post(`/roster/${selectedTeamId}/drop`, { player_id: playerId });
              toast.success(`${playerName} dropped to free agency`, {
                description: "League will process per waiver rules.",
              });
              setTradeBlockReloadKey((k) => k + 1);
            } catch (e: any) {
              toast.error("Drop failed", {
                description: e?.response?.data?.detail || e?.message || "Unknown error",
              });
            } finally {
              toast.dismiss(toastId);
            }
          },
        },
        cancel: { label: "Cancel", onClick: () => toast.dismiss(toastId) },
      },
    );
  }, [isOwnTeam, selectedTeamId]);

  // ── Trade-block toggle flow: confirmation toast → POST /api/trade-block
  // Owners must confirm before the player is announced on the trade block.
  const handleAddToTradeBlock = useCallback((player: any) => {
    if (!isOwnTeam || !selectedTeamId || !league?.id) return;
    const playerId = String(player.id);
    const playerName = player.name;
    const alreadyOnBlock = tradeBlockPlayerIds.includes(playerId);
    const toastId = toast(
      alreadyOnBlock ? `Remove ${playerName} from trade block?` : `Put ${playerName} on the trade block?`,
      {
        description: alreadyOnBlock
          ? "Other managers will no longer see this player listed in your trade block."
          : "Other managers will see this player listed in your trade block. You can remove them at any time.",
        duration: Infinity,
        action: {
          label: alreadyOnBlock ? "Remove" : "Submit",
          onClick: async () => {
            try {
              if (alreadyOnBlock) {
                // Find existing trade-block item id
                const list = await api.get(`/trade-block`, { params: { team_id: selectedTeamId } });
                const items = list.data?.items || list.data || [];
                const item = items.find((i: any) => String(i.player_id) === playerId);
                if (item?._id || item?.id) {
                  await api.delete(`/trade-block/${item._id || item.id}`);
                  toast.success(`${playerName} removed from trade block`);
                }
              } else {
                await api.post(`/trade-block`, {
                  league_id: league.id,
                  team_id: selectedTeamId,
                  item_type: "player",
                  player_id: playerId,
                  looking_for: [],
                });
                toast.success(`${playerName} added to trade block`);
              }
              setTradeBlockReloadKey((k) => k + 1);
            } catch (e: any) {
              toast.error("Trade block update failed", {
                description: e?.response?.data?.detail || e?.message || "Unknown error",
              });
            } finally {
              toast.dismiss(toastId);
            }
          },
        },
        cancel: { label: "Cancel", onClick: () => toast.dismiss(toastId) },
      },
    );
  }, [isOwnTeam, selectedTeamId, league, tradeBlockPlayerIds]);

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
          onDropPlayer={handleDropPlayer}
          onAddToTradeBlock={handleAddToTradeBlock}
          tradeBlockPlayerIds={tradeBlockPlayerIds}
          isTradeBuilderOpen={tradeBuilder.open}
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

        <TradeBlockManager
          team={{
            ...(teamRecord || {}),
            id: selectedTeamId,
            name: selectedTeam?.name,
            salary_retention_pref: teamRecord?.salary_retention_pref || "no_preference",
            _players: rosterPlayers,
          }}
          league={league ? { id: league.id, name: league.name } : null}
          isOwnTeam={!!isOwnTeam}
        />
      </div>

      {/* Trade Builder is mounted globally in AppLayout — no per-page panel here. */}
    </AppLayout>
  );
};

export default Team;
