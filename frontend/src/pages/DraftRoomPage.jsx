import { useState, useMemo, useEffect, useCallback } from "react";
import { AppLayout } from "@/components/layout/AppLayout";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { LayoutGrid, Star, Search, Play, ListOrdered, Repeat } from "lucide-react";
import { cn } from "@/lib/utils";
import api from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { useParams } from "react-router-dom";
import { useTradeBuilder } from "@/lovable/state/TradeBuilderContext";
import { toast } from "sonner";
import { useDraftSocket } from "@/hooks/use-socket";
// Iter 232N.27 — Slow-poke leaderboard sidebar (Speed Demon, Slow-Poke,
// Auto-Pilot, Wheeler-Dealer, Iron Man, Queue Master).
import DraftLeaderboard from "@/components/DraftLeaderboard";
// Iter 232N.35 — Draft Room split into three focused components.
import DraftTimerCard from "@/components/draft/DraftTimerCard";
import DraftBoardGrid from "@/components/draft/DraftBoardGrid";
import DraftChatPanel from "@/components/draft/DraftChatPanel";

const teamByAbbr = (teams, abbr) => {
  if (!abbr || !teams?.length) return null;
  return teams.find((t) => (t.logo_abbr || (t.name || "").slice(0, 3).toUpperCase()) === abbr) || null;
};

const positionColors = {
  C: "bg-blue-600/80 text-blue-100 border-blue-500/50",
  LW: "bg-emerald-600/80 text-emerald-100 border-emerald-500/50",
  RW: "bg-teal-600/80 text-teal-100 border-teal-500/50",
  D: "bg-amber-600/80 text-amber-100 border-amber-500/50",
  G: "bg-purple-600/80 text-purple-100 border-purple-500/50",
};

export default function DraftRoomPage() {
  const { id: draftId } = useParams();
  const { user } = useAuth();

  const [draft, setDraft] = useState(null);
  const [players, setPlayers] = useState([]);
  const [teams, setTeams] = useState([]);
  const [shortlist, setShortlist] = useState(new Set());
  const [queue, setQueue] = useState([]);
  const [chatMessages, setChatMessages] = useState([]);
  const [chatInput, setChatInput] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [positionFilter, setPositionFilter] = useState("all");
  const [pickTimeLeft, setPickTimeLeft] = useState(120);
  // Iter 232N.26 — Personal pick-timer countdown state.
  const [personalTimeLeft, setPersonalTimeLeft] = useState(0);
  const [autoPickPref, setAutoPickPref] = useState("queue_then_best");
  const [savingAutoPickPref, setSavingAutoPickPref] = useState(false);
  const [timerPaused, setTimerPaused] = useState(false);
  const [loading, setLoading] = useState(true);

  // Fetch draft data
  const fetchDraft = useCallback(async () => {
    if (!draftId) return;
    try {
      const { data } = await api.get(`/drafts/${draftId}`);
      setDraft(data);
      setChatMessages(data.chat_messages || []);
      // Iter 232N.33 — Compute the actual remaining time from
      // `current_pick_started_at` so refreshes / tab returns display the
      // real countdown that the server-side worker will use to auto-pick.
      const baseSeconds = Number(data.time_per_pick || data.pick_time_seconds || 120);
      if (data.current_pick_started_at) {
        try {
          const started = new Date(data.current_pick_started_at).getTime();
          const elapsed = Math.max(0, Math.floor((Date.now() - started) / 1000));
          setPickTimeLeft(Math.max(0, baseSeconds - elapsed));
        } catch {
          setPickTimeLeft(baseSeconds);
        }
      } else {
        setPickTimeLeft(baseSeconds);
      }
      // Iter 232N.26/N.33 — Same treatment for the personal cap.
      if (data.personal_pick_timer_seconds) {
        const personalBase = Number(data.personal_pick_timer_seconds);
        if (data.current_pick_started_at) {
          try {
            const startedAt = new Date(data.current_pick_started_at).getTime();
            const elapsed = Math.max(0, Math.floor((Date.now() - startedAt) / 1000));
            setPersonalTimeLeft(Math.max(0, personalBase - elapsed));
          } catch {
            setPersonalTimeLeft(personalBase);
          }
        } else {
          setPersonalTimeLeft(personalBase);
        }
      } else {
        setPersonalTimeLeft(0);
      }
      setTimerPaused(data.timer_paused || false);
      if (data.league_id) {
        try {
          const { data: t } = await api.get(`/teams?league_id=${data.league_id}`);
          setTeams(t || []);
        } catch (e) { /* ignore */ }
      }
    } catch (e) {
      console.error("Failed to fetch draft", e);
    }
  }, [draftId]);

  // Fetch eligible players
  const fetchPlayers = useCallback(async () => {
    if (!draftId) return;
    try {
      const params = new URLSearchParams();
      if (searchQuery) params.append("search", searchQuery);
      if (positionFilter !== "all") params.append("position", positionFilter);
      params.append("limit", "50");
      const { data } = await api.get(`/drafts/${draftId}/eligible-players?${params}`);
      setPlayers(data.players || []);
    } catch (e) {
      console.error("Failed to fetch players", e);
    }
  }, [draftId, searchQuery, positionFilter]);

  useEffect(() => {
    const init = async () => {
      setLoading(true);
      await fetchDraft();
      await fetchPlayers();
      setLoading(false);
    };
    init();
  }, [fetchDraft, fetchPlayers]);

  // Refresh eligible players on search/filter change
  useEffect(() => {
    const t = setTimeout(fetchPlayers, 300);
    return () => clearTimeout(t);
  }, [searchQuery, positionFilter, fetchPlayers]);

  // Pick timer
  useEffect(() => {
    if (!draft?.draft_started || draft?.early_start || timerPaused) return;
    const interval = setInterval(() => {
      setPickTimeLeft((prev) => {
        if (prev <= 1) return draft.time_per_pick || 120;
        return prev - 1;
      });
      // Iter 232N.26 — Personal timer ticks alongside the main clock.
      if (draft?.personal_pick_timer_seconds) {
        setPersonalTimeLeft((prev) => {
          if (prev <= 1) return draft.personal_pick_timer_seconds;
          return prev - 1;
        });
      }
    }, 1000);
    return () => clearInterval(interval);
  }, [draft, timerPaused]);

  // Poll for updates every 30s as WebSocket fallback
  useEffect(() => {
    if (!draftId) return;
    const interval = setInterval(async () => {
      await fetchDraft();
      await fetchPlayers();
    }, 30000);
    return () => clearInterval(interval);
  }, [draftId, fetchDraft, fetchPlayers]);

  // WebSocket: real-time draft events + presence
  const { onlineUserIds } = useDraftSocket(draftId, {
    userId: user?.id,
    onDraftStarted: () => { fetchDraft(); },
    onDraftPick: () => {
      fetchDraft();
      fetchPlayers();
      setPickTimeLeft(draft?.time_per_pick || 120);
    },
    onChatMessage: (msg) => {
      setChatMessages((prev) => [...prev, msg]);
    },
    onTimerToggle: (data) => {
      setTimerPaused(data.paused);
    },
    onConfigUpdated: () => { fetchDraft(); },
    onDraftCompleted: () => { fetchDraft(); },
  });

  // Actions
  const handleStartDraft = async (earlyStart) => {
    try {
      await api.post(`/drafts/${draftId}/start?early_start=${earlyStart}`);
      await fetchDraft();
    } catch (e) { console.error(e); }
  };

  const handleMakePick = async (playerId) => {
    try {
      await api.post(`/drafts/${draftId}/pick`, { player_id: playerId });
      await fetchDraft();
      await fetchPlayers();
    } catch (e) { console.error(e); }
  };

  const handlePauseTimer = async () => {
    try {
      const { data } = await api.post(`/drafts/${draftId}/pause`);
      setTimerPaused(data.paused);
    } catch (e) { console.error(e); }
  };

  const handleSendChat = async () => {
    if (!chatInput.trim()) return;
    try {
      await api.post(`/drafts/${draftId}/chat`, { text: chatInput.trim() });
      setChatInput("");
      await fetchDraft();
    } catch (e) { console.error(e); }
  };

  const toggleShortlist = (playerId) => {
    setShortlist((prev) => {
      const next = new Set(prev);
      if (next.has(playerId)) next.delete(playerId);
      else next.add(playerId);
      return next;
    });
  };

  const toggleQueue = (playerId) => {
    setQueue((prev) => (prev.includes(playerId) ? prev.filter((id) => id !== playerId) : [...prev, playerId]));
  };

  // Derived
  const teamAbbrs = draft?.team_abbrs || [];
  const totalTeams = teamAbbrs.length;
  const currentPick = draft?.current_pick || 1;
  const totalRounds = draft?.total_rounds || 5;
  const picks = draft?.picks || [];
  const isActive = draft?.status === "active";

  const getTeamForPick = (overall) => {
    if (!totalTeams) return "";
    const round = Math.ceil(overall / totalTeams);
    const pickInRound = (overall - 1) % totalTeams;
    const order = draft?.snake_draft && round % 2 === 0 ? [...teamAbbrs].reverse() : teamAbbrs;
    return order[pickInRound] || "";
  };

  const onTheClockTeam = getTeamForPick(currentPick);
  const currentRound = totalTeams ? Math.ceil(currentPick / totalTeams) : 1;
  const currentPickInRound = totalTeams ? ((currentPick - 1) % totalTeams) + 1 : 1;

  // Iter 146 — Propose-trade mode (mirrors Draft Board)
  const [tradeMode, setTradeMode] = useState(false);
  const tradeBuilder = useTradeBuilder();
  const myTeam = useMemo(() => {
    if (!user || !teams?.length) return null;
    const mine = teams.find((t) => t.owner_id === user.id);
    if (!mine) return null;
    return {
      id: mine.id,
      name: mine.name,
      abbr: mine.logo_abbr || (mine.name || "").slice(0, 3).toUpperCase(),
      owner: user.username || user.email,
      auto_pick_preference: mine.auto_pick_preference || "queue_then_best",
    };
  }, [user, teams]);

  // Iter 232N.26 — Sync the auto-pick preference selector with team payload.
  useEffect(() => {
    if (myTeam?.auto_pick_preference) {
      setAutoPickPref(myTeam.auto_pick_preference);
    }
  }, [myTeam?.auto_pick_preference]);

  const saveAutoPickPref = useCallback(async (nextValue) => {
    if (!myTeam?.id) return;
    setAutoPickPref(nextValue);
    setSavingAutoPickPref(true);
    try {
      await api.patch(`/teams/${myTeam.id}/auto-pick-preference`, {
        auto_pick_preference: nextValue,
      });
      toast.success(
        nextValue === "best_available"
          ? "Auto-pick set to best available"
          : "Auto-pick set to draft queue first",
      );
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed to save auto-pick preference");
    } finally {
      setSavingAutoPickPref(false);
    }
  }, [myTeam?.id]);

  const handleAddDraftPickToTrade = (ownerAbbr, round, overall, player) => {
    if (!myTeam) {
      toast.error("Join a team in this league to propose trades");
      return;
    }
    if (!draft?.league_id) {
      toast.error("League context missing");
      return;
    }
    tradeBuilder.openBuilder({ leagueId: draft.league_id, myTeam });
    const ownerTeam = teams.find(
      (t) => (t.logo_abbr || (t.name || "").slice(0, 3).toUpperCase()) === ownerAbbr,
    );
    const year = draft?.year || draft?.season || new Date().getFullYear();
    tradeBuilder.addPick({
      id: `draft-${draftId}-${overall}`,
      year,
      round,
      ownerTeamId: ownerTeam?.id,
      ownerTeamName: ownerTeam?.name || ownerAbbr,
      originalTeamId: ownerTeam?.id,
      originalTeamName: ownerAbbr,
      label: player?.name
        ? `${year} R${round} · #${overall} (${ownerAbbr} — ${player.name})`
        : `${year} R${round} · #${overall} (${ownerAbbr})`,
    });
  };

  const filteredPlayers = players.filter((p) => !p.drafted);
  const shortlistedPlayers = players.filter((p) => shortlist.has(p.id) && !p.drafted);
  const queuedPlayers = queue.map((id) => players.find((p) => p.id === id)).filter(Boolean);

  // Build pick grid
  const allPicks = useMemo(() => {
    const grid = [];
    const pickMap = {};
    picks.forEach((p) => { pickMap[p.overall] = p; });
    for (let r = 1; r <= totalRounds; r++) {
      const order = draft?.snake_draft && r % 2 === 0 ? [...teamAbbrs].reverse() : teamAbbrs;
      const roundPicks = order.map((team, idx) => {
        const overall = (r - 1) * totalTeams + idx + 1;
        return pickMap[overall] || { round: r, pick_in_round: idx + 1, overall, team, player: null };
      });
      grid.push(roundPicks);
    }
    return grid;
  }, [picks, totalRounds, teamAbbrs, totalTeams, draft?.snake_draft]);

  if (loading) {
    return (
      <AppLayout>
        <div className="flex items-center justify-center h-[60vh]">
          <div className="text-[#A1A1AA]">Loading draft room...</div>
        </div>
      </AppLayout>
    );
  }

  if (!draft) {
    return (
      <AppLayout>
        <div className="text-center py-20">
          <LayoutGrid className="h-16 w-16 text-[#52525B] mx-auto mb-4" />
          <h2 className="text-xl text-white mb-2">Draft not found</h2>
          <p className="text-[#A1A1AA]">This draft may not exist or has been removed.</p>
        </div>
      </AppLayout>
    );
  }

  return (
    <AppLayout>
      <div className="space-y-4" data-testid="draft-room-page">
        {/* Header */}
        <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-white flex items-center gap-2">
              <LayoutGrid className="h-6 w-6 text-[#00D2FF]" />
              Draft Room
            </h1>
            <p className="text-sm text-[#A1A1AA]">
              {draft.league_name || "League"} — {draft.draft_type} Draft
            </p>
            <div className="mt-2">
              {/* Iter 146 — Propose Trade toggle (mirrors Draft Board) */}
              <Button
                size="sm"
                variant={tradeMode ? "default" : "outline"}
                onClick={() => setTradeMode((v) => !v)}
                data-testid="draft-room-trade-toggle"
                aria-pressed={tradeMode}
                className={tradeMode ? "bg-emerald-500 hover:bg-emerald-600 text-white" : "border-white/10 text-white"}
              >
                <Repeat className="h-4 w-4 mr-1" />
                {tradeMode ? "Trade Mode: On" : "Trade Mode: Off"}
              </Button>
            </div>
          </div>

          {/* Timer Card */}
          <DraftTimerCard
            draft={draft}
            teams={teams}
            onTheClockTeam={onTheClockTeam}
            onTheClockTeamObj={teamByAbbr(teams, onTheClockTeam)}
            currentRound={currentRound}
            currentPickInRound={currentPickInRound}
            currentPick={currentPick}
            pickTimeLeft={pickTimeLeft}
            personalTimeLeft={personalTimeLeft}
            timerPaused={timerPaused}
            picks={picks}
            myTeam={myTeam}
            autoPickPref={autoPickPref}
            savingAutoPickPref={savingAutoPickPref}
            onStartDraft={handleStartDraft}
            onPauseTimer={handlePauseTimer}
            onSaveAutoPickPref={saveAutoPickPref}
          />
        </div>

        {/* Draft Board */}
        <DraftBoardGrid
          teams={teams}
          teamAbbrs={teamAbbrs}
          totalTeams={totalTeams}
          allPicks={allPicks}
          currentPick={currentPick}
          onTheClockTeam={onTheClockTeam}
          isActive={isActive}
          onlineUserIds={onlineUserIds}
          tradeMode={tradeMode}
          onAddPickToTrade={handleAddDraftPickToTrade}
        />

        {/* Bottom: Queue | Player Search | Chat */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
          {/* Queue */}
          <div className="lg:col-span-2">
            <Card className="border-white/10 h-full">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm flex items-center gap-2 text-white">
                  <ListOrdered className="h-4 w-4 text-[#00D2FF]" />My Queue
                </CardTitle>
              </CardHeader>
              <CardContent className="p-2">
                <ScrollArea className="h-[400px]">
                  {queuedPlayers.length === 0 ? (
                    <div className="text-center py-8">
                      <ListOrdered className="h-6 w-6 text-[#52525B] mx-auto" />
                      <p className="text-xs text-[#A1A1AA] mt-2">Queue is empty</p>
                    </div>
                  ) : queuedPlayers.map((player, idx) => (
                    <div key={player.id} className="flex items-center gap-1.5 p-1.5 rounded-md bg-[#1A1A1A]/30 mb-1 group">
                      <span className="text-[10px] font-mono text-[#A1A1AA] w-4 text-right">{idx + 1}.</span>
                      <Badge className={cn("text-[9px] px-1 py-0 h-3.5 border", positionColors[player.position])}>
                        {player.position}
                      </Badge>
                      <span className="text-xs font-medium text-white truncate flex-1">{player.name}</span>
                      {isActive && (
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-5 w-5 text-[#00D2FF] opacity-0 group-hover:opacity-100"
                          onClick={() => handleMakePick(player.id)}
                        >
                          <Play className="h-3 w-3" />
                        </Button>
                      )}
                    </div>
                  ))}
                </ScrollArea>
              </CardContent>
            </Card>
          </div>

          {/* Player Search */}
          <div className="lg:col-span-5">
            <Tabs defaultValue="eligible" className="w-full">
              <TabsList className="w-full grid grid-cols-2">
                <TabsTrigger value="eligible">Eligible Players</TabsTrigger>
                <TabsTrigger value="shortlist">
                  <Star className="h-3.5 w-3.5 mr-1" />Shortlist ({shortlistedPlayers.length})
                </TabsTrigger>
              </TabsList>
              <TabsContent value="eligible" className="mt-3 space-y-3">
                <div className="flex gap-2">
                  <div className="relative flex-1">
                    <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-[#A1A1AA]" />
                    <Input
                      placeholder="Search players..."
                      className="pl-8 h-8 text-sm bg-[#1A1A1A] border-white/10 text-white"
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      data-testid="draft-search"
                    />
                  </div>
                  <Select value={positionFilter} onValueChange={setPositionFilter}>
                    <SelectTrigger className="w-[100px] h-8 text-xs bg-[#1A1A1A] border-white/10 text-white">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent className="bg-[#141414] border-white/10">
                      {[{ v: "all", l: "All" }, { v: "C", l: "C" }, { v: "LW", l: "LW" }, { v: "RW", l: "RW" }, { v: "D", l: "D" }, { v: "G", l: "G" }].map((p) => (
                        <SelectItem key={p.v} value={p.v} className="text-white">{p.l}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <Badge variant="secondary" className="text-[10px]">{filteredPlayers.length} players available</Badge>
                <ScrollArea className="h-[400px]">
                  <div className="space-y-1">
                    {filteredPlayers.map((player) => (
                      <div key={player.id} className="flex items-center gap-2 p-2 rounded-md hover:bg-[#1A1A1A]/40 transition-colors group">
                        <span className="text-[10px] font-mono text-[#A1A1AA] w-5 text-right">{player.ranking}</span>
                        <Badge className={cn("text-[9px] px-1 py-0 h-3.5 border", positionColors[player.position])}>{player.position}</Badge>
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium text-white truncate">{player.name}</p>
                          <p className="text-[10px] text-[#A1A1AA]">{player.nhlTeam} · {player.gp}GP {player.g}G {player.a}A {player.pts}P</p>
                        </div>
                        <Button
                          variant="ghost"
                          size="icon"
                          className={cn("h-7 w-7", shortlist.has(player.id) ? "text-[#FF3B30]" : "text-[#52525B] hover:text-[#FF3B30]")}
                          onClick={() => toggleShortlist(player.id)}
                        >
                          <Star className={cn("h-3.5 w-3.5", shortlist.has(player.id) && "fill-current")} />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          className={cn("h-7 w-7", queue.includes(player.id) ? "text-[#00D2FF]" : "text-[#52525B] hover:text-[#00D2FF]")}
                          onClick={() => toggleQueue(player.id)}
                        >
                          <ListOrdered className="h-3.5 w-3.5" />
                        </Button>
                        {isActive && (
                          <Button
                            size="sm"
                            className="h-7 bg-[#00D2FF] text-black text-xs opacity-0 group-hover:opacity-100"
                            onClick={() => handleMakePick(player.id)}
                            data-testid={`pick-${player.id}`}
                          >
                            Pick
                          </Button>
                        )}
                      </div>
                    ))}
                  </div>
                </ScrollArea>
              </TabsContent>
              <TabsContent value="shortlist" className="mt-3">
                <ScrollArea className="h-[450px]">
                  {shortlistedPlayers.length === 0 ? (
                    <div className="text-center py-12">
                      <Star className="h-8 w-8 text-[#52525B] mx-auto" />
                      <p className="text-sm text-[#A1A1AA] mt-2">No players shortlisted</p>
                    </div>
                  ) : shortlistedPlayers.map((player, idx) => (
                    <div key={player.id} className="flex items-center gap-2 p-2 rounded-md bg-[#1A1A1A]/30 mb-1">
                      <span className="text-[10px] text-[#A1A1AA] w-4">{idx + 1}.</span>
                      <Badge className={cn("text-[9px] px-1 py-0 h-3.5 border", positionColors[player.position])}>{player.position}</Badge>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-white truncate">{player.name}</p>
                        <p className="text-[10px] text-[#A1A1AA]">#{player.ranking} · {player.nhlTeam} · {player.pts}P</p>
                      </div>
                    </div>
                  ))}
                </ScrollArea>
              </TabsContent>
            </Tabs>
          </div>

          {/* Chat */}
          <div className="lg:col-span-5 space-y-4">
            <DraftChatPanel
              chatMessages={chatMessages}
              chatInput={chatInput}
              onChatInputChange={setChatInput}
              onSendChat={handleSendChat}
            />
            {/* Iter 232N.27 — Draft Leaderboard sits below the chat so
                trash-talk about who's stalling is a scroll away. */}
            <DraftLeaderboard draftId={draftId} refreshTick={draft?.picks?.length || 0} />
          </div>
        </div>
      </div>
    </AppLayout>
  );
}
