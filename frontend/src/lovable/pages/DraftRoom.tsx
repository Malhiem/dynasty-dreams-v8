// @ts-nocheck
import { useState, useMemo, useEffect, useCallback } from "react";
import { AppLayout } from "@/components/layout/AppLayout";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { Progress } from "@/components/ui/progress";
import {
  LayoutGrid,
  Star,
  Search,
  Clock,
  Play,
  Pause,
  Timer,
  AlertCircle,
  X,
  ListOrdered,
  MessageSquare,
  Send,
  Info,
  Users,
  Repeat,
  Megaphone,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useTradeBuilder } from "@/lovable/state/TradeBuilderContext";
import { useAuth } from "@/contexts/AuthContext";
import { useActiveLeague } from "@/hooks/use-active-league";
import { toast } from "sonner";
import DraftChatPanel from "@/lovable/pages/draftroom/DraftChatPanel";
import TruncatedRosterPanel from "@/lovable/pages/draftroom/TruncatedRosterPanel";
import SelectedPlayerCard from "@/lovable/pages/draftroom/SelectedPlayerCard";
import PlayerCardModal from "@/lovable/components/dashboard/PlayerCardModal";

// ─── Types ───────────────────────────────────────────────────────────────────

interface DraftEligiblePlayer {
  id: string;
  name: string;
  position: string;
  nhlTeam: string;
  age: number;
  league: string;
  gp: number;
  g: number;
  a: number;
  pts: number;
  ranking: number;
  drafted: boolean;
  draftedBy?: string;
  draftedRound?: number;
  draftedPick?: number;
}

interface DraftPick {
  round: number;
  pickInRound: number;
  overall: number;
  team: string;
  player?: DraftEligiblePlayer;
}

interface DraftConfig {
  scheduledTime: Date | null;
  draftStarted: boolean;
  earlyStart: boolean;
  pickTimerSeconds: number;
  currentPick: number;
  totalRounds: number;
  snakeDraft: boolean;
}

interface ChatMessage {
  id: string;
  type: "chat" | "pick";
  sender: string;
  text: string;
  timestamp: Date;
}

// ─── League teams ────────────────────────────────────────────────────────────

const leagueTeams = [
  { name: "Arctic Wolves", abbr: "ARC" },
  { name: "Blizzard Kings", abbr: "BLZ" },
  { name: "Frozen Fury", abbr: "FRZ" },
  { name: "Glacier Bears", abbr: "GLC" },
  { name: "Ice Breakers", abbr: "ICE" },
  { name: "Northern Lights", abbr: "NTH" },
  { name: "Polar Phantoms", abbr: "POL" },
  { name: "Snow Hawks", abbr: "SNW" },
  { name: "Team Frostbite", abbr: "FRST" },
  { name: "Tundra Titans", abbr: "TND" },
  { name: "Winter Storm", abbr: "WST" },
  { name: "Zero Below", abbr: "ZRO" },
].sort((a, b) => a.name.localeCompare(b.name));

const teamAbbrs = leagueTeams.map((t) => t.abbr);

// ─── Position colors ─────────────────────────────────────────────────────────

const positionColors: Record<string, string> = {
  C: "bg-blue-600/80 text-blue-100 border-blue-500/50",
  LW: "bg-emerald-600/80 text-emerald-100 border-emerald-500/50",
  RW: "bg-teal-600/80 text-teal-100 border-teal-500/50",
  D: "bg-amber-600/80 text-amber-100 border-amber-500/50",
  G: "bg-purple-600/80 text-purple-100 border-purple-500/50",
};

// ─── Draft criteria descriptions ─────────────────────────────────────────────

const draftCriteria = [
  { value: "entry", label: "NHL Entry Draft", description: "Players aged 18-20 who have not been previously drafted by an NHL team. Includes CHL, European, and college players eligible for the first time." },
  { value: "rookies", label: "Rookies Only", description: "Players who have not played more than 25 games in any single preceding season or 6+ games in each of any two preceding seasons in the NHL." },
  { value: "prospects", label: "Prospects Only", description: "Players currently developing in junior, college, or minor professional leagues who have not yet established themselves on an NHL roster." },
  { value: "unsigned", label: "Unsigned / Draft Eligible", description: "Players who are currently without an NHL contract, including undrafted free agents and draft-eligible players whose rights have expired." },
  { value: "all", label: "All Players", description: "No restrictions. All players in the database are eligible to be selected regardless of age, contract status, or league affiliation." },
];

// ─── Mock eligible players ───────────────────────────────────────────────────

const mockEligiblePlayers: DraftEligiblePlayer[] = [
  { id: "e1", name: "James Hagens", position: "C", nhlTeam: "—", age: 17, league: "NTDP", gp: 52, g: 28, a: 42, pts: 70, ranking: 1, drafted: false },
  { id: "e2", name: "Porter Martone", position: "RW", nhlTeam: "—", age: 17, league: "OHL", gp: 60, g: 38, a: 40, pts: 78, ranking: 2, drafted: false },
  { id: "e3", name: "Ivan Ryabkin", position: "C", nhlTeam: "—", age: 17, league: "KHL", gp: 48, g: 18, a: 30, pts: 48, ranking: 3, drafted: false },
  { id: "e4", name: "Cameron Schmidt", position: "C", nhlTeam: "—", age: 17, league: "WHL", gp: 58, g: 45, a: 38, pts: 83, ranking: 4, drafted: false },
  { id: "e5", name: "Lukas Fischer", position: "D", nhlTeam: "—", age: 17, league: "SHL", gp: 44, g: 8, a: 28, pts: 36, ranking: 5, drafted: false },
  { id: "e6", name: "Cole Reschny", position: "C", nhlTeam: "—", age: 17, league: "WHL", gp: 62, g: 30, a: 42, pts: 72, ranking: 6, drafted: false },
  { id: "e7", name: "Linus Eriksson", position: "LW", nhlTeam: "—", age: 18, league: "SHL", gp: 50, g: 22, a: 30, pts: 52, ranking: 7, drafted: false },
  { id: "e8", name: "Roger McQueen", position: "C", nhlTeam: "—", age: 17, league: "OHL", gp: 56, g: 40, a: 32, pts: 72, ranking: 8, drafted: false },
  { id: "e9", name: "Jack Macgregor", position: "D", nhlTeam: "—", age: 17, league: "OHL", gp: 60, g: 12, a: 38, pts: 50, ranking: 9, drafted: false },
  { id: "e10", name: "Jonathan Morello", position: "RW", nhlTeam: "—", age: 17, league: "OHL", gp: 58, g: 35, a: 28, pts: 63, ranking: 10, drafted: false },
  { id: "e11", name: "Austin Burnevik", position: "C", nhlTeam: "—", age: 18, league: "NCAA", gp: 40, g: 24, a: 30, pts: 54, ranking: 11, drafted: false },
  { id: "e12", name: "Vac Vojtech", position: "G", nhlTeam: "—", age: 17, league: "CZE", gp: 34, g: 0, a: 2, pts: 2, ranking: 12, drafted: false },
  { id: "e13", name: "Blake Fiddler", position: "D", nhlTeam: "—", age: 17, league: "WHL", gp: 62, g: 10, a: 32, pts: 42, ranking: 13, drafted: false },
  { id: "e14", name: "Adam Jecho", position: "C", nhlTeam: "—", age: 18, league: "OHL", gp: 58, g: 26, a: 36, pts: 62, ranking: 14, drafted: false },
  { id: "e15", name: "Alex Huang", position: "LW", nhlTeam: "—", age: 17, league: "USHL", gp: 54, g: 28, a: 26, pts: 54, ranking: 15, drafted: false },
  { id: "e16", name: "Ben Merrill", position: "D", nhlTeam: "—", age: 18, league: "NCAA", gp: 38, g: 6, a: 24, pts: 30, ranking: 16, drafted: false },
  { id: "e17", name: "Dmitri Petrov", position: "RW", nhlTeam: "—", age: 17, league: "MHL", gp: 50, g: 20, a: 22, pts: 42, ranking: 17, drafted: false },
  { id: "e18", name: "William Chen", position: "C", nhlTeam: "—", age: 17, league: "QMJHL", gp: 60, g: 22, a: 38, pts: 60, ranking: 18, drafted: false },
  { id: "e19", name: "Oscar Nilsson", position: "G", nhlTeam: "—", age: 18, league: "SHL", gp: 30, g: 0, a: 1, pts: 1, ranking: 19, drafted: false },
  { id: "e20", name: "Marcus Lindqvist", position: "LW", nhlTeam: "—", age: 17, league: "FIN", gp: 48, g: 18, a: 24, pts: 42, ranking: 20, drafted: false },
  { id: "e21", name: "Nolan Reid", position: "D", nhlTeam: "—", age: 18, league: "OHL", gp: 62, g: 8, a: 30, pts: 38, ranking: 21, drafted: false },
  { id: "e22", name: "Filip Andersson", position: "RW", nhlTeam: "—", age: 17, league: "SHL", gp: 46, g: 16, a: 20, pts: 36, ranking: 22, drafted: false },
  { id: "e23", name: "Tyler Walsh", position: "C", nhlTeam: "—", age: 18, league: "WHL", gp: 56, g: 20, a: 28, pts: 48, ranking: 23, drafted: false },
  { id: "e24", name: "Erik Sundberg", position: "D", nhlTeam: "—", age: 17, league: "SHL", gp: 42, g: 4, a: 18, pts: 22, ranking: 24, drafted: false },
  { id: "e25", name: "Jake Morrison", position: "G", nhlTeam: "—", age: 17, league: "OHL", gp: 44, g: 0, a: 1, pts: 1, ranking: 25, drafted: false },
  { id: "e26", name: "Ryan Thompson", position: "LW", nhlTeam: "—", age: 18, league: "USHL", gp: 52, g: 24, a: 20, pts: 44, ranking: 26, drafted: false },
  { id: "e27", name: "Max Dubois", position: "C", nhlTeam: "—", age: 17, league: "QMJHL", gp: 58, g: 18, a: 34, pts: 52, ranking: 27, drafted: false },
  { id: "e28", name: "Sami Korhonen", position: "D", nhlTeam: "—", age: 18, league: "FIN", gp: 46, g: 6, a: 22, pts: 28, ranking: 28, drafted: false },
  { id: "e29", name: "Connor Blake", position: "RW", nhlTeam: "—", age: 17, league: "WHL", gp: 60, g: 26, a: 22, pts: 48, ranking: 29, drafted: false },
  { id: "e30", name: "Alexei Volkov", position: "G", nhlTeam: "—", age: 18, league: "KHL", gp: 28, g: 0, a: 0, pts: 0, ranking: 30, drafted: false },
];

// ─── Mock current roster ─────────────────────────────────────────────────────

const myRoster = [
  { name: "Connor McDavid", position: "C", pts: 128 },
  { name: "Leon Draisaitl", position: "C", pts: 110 },
  { name: "Cale Makar", position: "D", pts: 86 },
  { name: "Artemi Panarin", position: "LW", pts: 96 },
  { name: "Mika Zibanejad", position: "C", pts: 72 },
  { name: "Seth Jones", position: "D", pts: 52 },
  { name: "Jake Oettinger", position: "G", pts: 44 },
  { name: "Tage Thompson", position: "C", pts: 78 },
  { name: "Rasmus Dahlin", position: "D", pts: 64 },
  { name: "Andrei Svechnikov", position: "RW", pts: 74 },
];

// ─── Helpers ─────────────────────────────────────────────────────────────────

function formatCountdown(ms: number) {
  if (ms <= 0) return "00:00:00";
  const totalSec = Math.floor(ms / 1000);
  const h = Math.floor(totalSec / 3600);
  const m = Math.floor((totalSec % 3600) / 60);
  const s = totalSec % 60;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

function formatPickTimer(seconds: number) {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

// ─── Component ───────────────────────────────────────────────────────────────

export default function DraftRoom() {
  const totalTeams = leagueTeams.length;

  const [draftConfig, setDraftConfig] = useState<DraftConfig>({
    scheduledTime: new Date(Date.now() + 2 * 60 * 60 * 1000),
    draftStarted: false,
    earlyStart: false,
    pickTimerSeconds: 120,
    currentPick: 1,
    totalRounds: 5,
    snakeDraft: true,
  });

  const [players, setPlayers] = useState<DraftEligiblePlayer[]>(mockEligiblePlayers);
  const [shortlist, setShortlist] = useState<Set<string>>(new Set());
  const [queue, setQueue] = useState<string[]>([]);
  const [picks, setPicks] = useState<DraftPick[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [positionFilter, setPositionFilter] = useState("all");
  const [countdown, setCountdown] = useState<number>(0);
  const [pickTimeLeft, setPickTimeLeft] = useState<number>(draftConfig.pickTimerSeconds);
  const [selectedCriteria, setSelectedCriteria] = useState("entry");

  // Chat state
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([
    { id: "sys1", type: "pick", sender: "System", text: "Draft room is open. Good luck!", timestamp: new Date(Date.now() - 120000) },
    { id: "c1", type: "chat", sender: "Arctic Wolves", text: "Let's get this draft going 🏒", timestamp: new Date(Date.now() - 90000) },
    { id: "c2", type: "chat", sender: "Blizzard Kings", text: "Who's everyone eyeing at #1?", timestamp: new Date(Date.now() - 60000) },
  ]);
  const [chatInput, setChatInput] = useState("");
  const [timerPaused, setTimerPaused] = useState(false);
  const isLeagueManager = true; // Current user is LM or co-LM

  // ─── Countdown ──────────────────────────────────────────────────────────────

  useEffect(() => {
    if (!draftConfig.scheduledTime) return;
    const interval = setInterval(() => {
      const diff = draftConfig.scheduledTime!.getTime() - Date.now();
      setCountdown(Math.max(0, diff));
      if (diff <= 0 && !draftConfig.draftStarted) {
        setDraftConfig((prev) => ({ ...prev, draftStarted: true, earlyStart: false }));
      }
    }, 1000);
    return () => clearInterval(interval);
  }, [draftConfig.scheduledTime, draftConfig.draftStarted]);

  // ─── Pick timer ─────────────────────────────────────────────────────────────

  const isClockActive = draftConfig.draftStarted && !draftConfig.earlyStart;

  useEffect(() => {
    if (!isClockActive) return;
    setPickTimeLeft(draftConfig.pickTimerSeconds);
    setTimerPaused(false);
  }, [isClockActive, draftConfig.currentPick, draftConfig.pickTimerSeconds]);

  useEffect(() => {
    if (!isClockActive || timerPaused) return;
    const interval = setInterval(() => {
      setPickTimeLeft((prev) => {
        if (prev <= 1) return draftConfig.pickTimerSeconds;
        return prev - 1;
      });
    }, 1000);
    return () => clearInterval(interval);
  }, [isClockActive, timerPaused, draftConfig.pickTimerSeconds]);

  // ─── Draft order ────────────────────────────────────────────────────────────

  const getDraftOrder = useCallback(
    (round: number): string[] => {
      if (draftConfig.snakeDraft && round % 2 === 0) return [...teamAbbrs].reverse();
      return teamAbbrs;
    },
    [draftConfig.snakeDraft]
  );

  const getTeamForPick = useCallback(
    (overall: number): string => {
      const round = Math.ceil(overall / totalTeams);
      const pickInRound = (overall - 1) % totalTeams;
      const order = getDraftOrder(round);
      return order[pickInRound];
    },
    [getDraftOrder, totalTeams]
  );

  // ─── Shortlist & Queue ─────────────────────────────────────────────────────

  const toggleShortlist = (playerId: string) => {
    setShortlist((prev) => {
      const next = new Set(prev);
      if (next.has(playerId)) next.delete(playerId);
      else next.add(playerId);
      return next;
    });
  };

  const toggleQueue = (playerId: string) => {
    setQueue((prev) =>
      prev.includes(playerId) ? prev.filter((id) => id !== playerId) : [...prev, playerId]
    );
  };

  const removeFromQueue = (playerId: string) => {
    setQueue((prev) => prev.filter((id) => id !== playerId));
  };

  // ─── Filtered players ──────────────────────────────────────────────────────

  const filteredPlayers = useMemo(() => {
    return players
      .filter((p) => !p.drafted)
      .filter((p) => {
        const matchesSearch = p.name.toLowerCase().includes(searchQuery.toLowerCase());
        const matchesPos = positionFilter === "all" || p.position === positionFilter;
        return matchesSearch && matchesPos;
      })
      .sort((a, b) => a.ranking - b.ranking);
  }, [players, searchQuery, positionFilter]);

  const shortlistedPlayers = useMemo(() => {
    return players.filter((p) => shortlist.has(p.id) && !p.drafted);
  }, [players, shortlist]);

  const queuedPlayers = useMemo(() => {
    return queue.map((id) => players.find((p) => p.id === id)).filter((p): p is DraftEligiblePlayer => !!p && !p.drafted);
  }, [queue, players]);

  // ─── Pick grid ─────────────────────────────────────────────────────────────

  const allPicks = useMemo(() => {
    const grid: DraftPick[][] = [];
    for (let r = 1; r <= draftConfig.totalRounds; r++) {
      const order = getDraftOrder(r);
      const roundPicks: DraftPick[] = order.map((team, idx) => {
        const overall = (r - 1) * totalTeams + idx + 1;
        const existing = picks.find((p) => p.overall === overall);
        return existing || { round: r, pickInRound: idx + 1, overall, team };
      });
      grid.push(roundPicks);
    }
    return grid;
  }, [picks, draftConfig.totalRounds, getDraftOrder, totalTeams]);

  // ─── Draft actions ─────────────────────────────────────────────────────────

  const handleEarlyStart = () => {
    setDraftConfig((prev) => ({ ...prev, draftStarted: true, earlyStart: true }));
  };

  const handleSendChat = () => {
    if (!chatInput.trim()) return;
    setChatMessages((prev) => [
      ...prev,
      { id: `chat-${Date.now()}`, type: "chat", sender: "Team Frostbite", text: chatInput.trim(), timestamp: new Date() },
    ]);
    setChatInput("");
  };

  // ─── Derived values ────────────────────────────────────────────────────────

  const onTheClockTeam = getTeamForPick(draftConfig.currentPick);
  const onTheClockTeamFull = leagueTeams.find((t) => t.abbr === onTheClockTeam);

  // Iter 147 — Propose-trade mode (mirrors Draft Board)
  const [tradeMode, setTradeMode] = useState(false);
  // Iter 149 — Trading Block overlay mode
  const [tradeBlockMode, setTradeBlockMode] = useState(false);
  const [tradeBlockItems, setTradeBlockItems] = useState<any[]>([]);
  // Iter 152 — Selected player for the inline card above the Draft Board
  const [selectedPlayerId, setSelectedPlayerId] = useState<string | null>(null);
  // Iter 153 — Window-within-window expanded player card (PlayerCardModal)
  const [expandedPlayer, setExpandedPlayer] = useState<any>(null);
  // Iter 154 — When the expanded player has a Mongo ObjectId, fetch the real
  // record (NHL stats, contract, schedule) and merge over the lean fallback.
  useEffect(() => {
    if (!expandedPlayer?.id) return;
    // ObjectIds are 24 hex chars; mock IDs (e1, e2 …) don't match.
    if (!/^[0-9a-fA-F]{24}$/.test(String(expandedPlayer.id))) return;
    let cancelled = false;
    (async () => {
      try {
        const apiClient = (await import("@/lib/api")).default;
        const params = activeLeagueCtx?.id ? { league_id: activeLeagueCtx.id } : undefined;
        const { data } = await apiClient.get(`/players/${expandedPlayer.id}`, { params });
        if (cancelled || !data) return;
        // Merge real fields onto the existing object — preserves headshot
        // initials + adapted categoryBreakdown / statsByPeriod from the
        // mock so the modal renders even on partial data.
        setExpandedPlayer((prev: any) => ({
          ...prev,
          ...data,
          id: prev.id, // keep the original id so the modal's expand-link href stays valid
          // Refresh the structured maps with real numbers when available
          categoryBreakdown: {
            G:   data.goals ?? prev.categoryBreakdown?.G ?? 0,
            A:   data.assists ?? prev.categoryBreakdown?.A ?? 0,
            PTS: data.points ?? prev.categoryBreakdown?.PTS ?? 0,
            PPP: data.power_play_points ?? prev.categoryBreakdown?.PPP ?? 0,
            SOG: data.shots ?? prev.categoryBreakdown?.SOG ?? 0,
            HIT: data.hits ?? prev.categoryBreakdown?.HIT ?? 0,
            BLK: data.blocks ?? prev.categoryBreakdown?.BLK ?? 0,
            PIM: data.penalty_minutes ?? prev.categoryBreakdown?.PIM ?? 0,
          },
          statsByPeriod: {
            ...(prev.statsByPeriod || {}),
            season: data.fantasy_points ?? data.points ?? prev.statsByPeriod?.season ?? 0,
          },
          points: data.fantasy_points ?? data.points ?? prev.points ?? 0,
        }));
      } catch {
        /* silent — modal already has the fallback shape */
      }
    })();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [expandedPlayer?.id, activeLeagueCtx?.id]);
  const tradeBuilder = useTradeBuilder();
  const { user } = useAuth();
  const { league: activeLeagueCtx, leagueTeams: liveTeams } = useActiveLeague();
  const myTeam = useMemo(() => {
    if (!user || !liveTeams?.length) return null;
    const mine = liveTeams.find((t: any) => t.owner_id === user.id);
    if (!mine) return null;
    return {
      id: mine.id,
      name: mine.name,
      abbr: mine.logo_abbr || (mine.name || "").slice(0, 3).toUpperCase(),
      owner: user.username || user.email,
    };
  }, [user, liveTeams]);

  // Iter 149 — Fetch league trade-block listings so the overlay can paint
  // megaphone icons on player tiles + pick tiles that are publicly available.
  // Re-fetches every 20s while the overlay is on.
  useEffect(() => {
    if (!activeLeagueCtx?.id) return;
    let cancelled = false;
    const load = async () => {
      try {
        const api = (await import("@/lib/api")).default;
        const { data } = await api.get(`/trade-block?league_id=${activeLeagueCtx.id}`);
        if (!cancelled) setTradeBlockItems(Array.isArray(data) ? data : []);
      } catch { /* noop */ }
    };
    load();
    if (!tradeBlockMode) return; // poll only while overlay is on
    const id = setInterval(load, 20_000);
    return () => { cancelled = true; clearInterval(id); };
  }, [activeLeagueCtx?.id, tradeBlockMode]);

  const tradeBlockPlayerIds = useMemo(
    () => new Set((tradeBlockItems || []).filter((x) => x.item_type === "player" && x.player_id).map((x) => String(x.player_id))),
    [tradeBlockItems],
  );
  const tradeBlockPickIds = useMemo(
    () => new Set((tradeBlockItems || []).filter((x) => x.item_type === "pick" && x.pick_id).map((x) => String(x.pick_id))),
    [tradeBlockItems],
  );
  // Composite "round-team" key for picks not yet assigned a `pick_id`
  // (mock data uses overall#); lets us light up the overlay on placeholder picks.
  const tradeBlockOverallKeys = useMemo(
    () => new Set(
      (tradeBlockItems || [])
        .filter((x) => x.item_type === "pick")
        .map((x) => `${x.team_id || ""}|R${x.pick_round || ""}`)
    ),
    [tradeBlockItems],
  );

  const markAvailableForDraft = useCallback(
    async (kind: "player" | "pick", payload: any) => {
      if (!activeLeagueCtx?.id || !myTeam?.id) {
        toast.error("Join a team in this league to mark items available");
        return;
      }
      try {
        const api = (await import("@/lib/api")).default;
        const body: any = {
          item_type: kind,
          league_id: activeLeagueCtx.id,
          team_id: myTeam.id,
          draft_only: true,
        };
        if (kind === "player") body.player_id = payload.id;
        else { body.pick_year = payload.year; body.pick_round = String(payload.round); }
        const { data } = await api.post("/trade-block", body);
        toast.success(`Marked ${payload.name || `R${payload.round}`} available for draft`);
        setTradeBlockItems((prev) => [...prev, data]);
      } catch (e: any) {
        toast.error(e?.response?.data?.detail || "Could not mark available");
      }
    },
    [activeLeagueCtx?.id, myTeam],
  );

  // Iter 151 — Toggle a player on/off the LOGGED-IN user's team trade block.
  // Called from the TruncatedRosterPanel when the user clicks the megaphone
  // beside the propose-trade icon on one of their own players.
  const toggleMyTeamTradeBlock = useCallback(
    async (player: any) => {
      if (!activeLeagueCtx?.id || !myTeam?.id || !player?.id) return;
      const existing = (tradeBlockItems || []).find(
        (x) => x.item_type === "player" && x.team_id === myTeam.id && String(x.player_id) === String(player.id),
      );
      const api = (await import("@/lib/api")).default;
      try {
        if (existing) {
          await api.delete(`/trade-block/${existing._id || existing.id}`);
          setTradeBlockItems((prev) => prev.filter((x) => (x._id || x.id) !== (existing._id || existing.id)));
          toast.success(`Removed ${player.name} from your trade block`);
        } else {
          const { data } = await api.post("/trade-block", {
            item_type: "player",
            league_id: activeLeagueCtx.id,
            team_id: myTeam.id,
            player_id: String(player.id),
          });
          setTradeBlockItems((prev) => [...prev, data]);
          toast.success(`Added ${player.name} to your trade block`);
        }
      } catch (e: any) {
        toast.error(e?.response?.data?.detail || "Trade block update failed");
      }
    },
    [activeLeagueCtx?.id, myTeam, tradeBlockItems],
  );

  const handleAddDraftPickToTrade = (ownerAbbr: string, round: number, overall: number, player: any) => {
    if (!myTeam) { toast.error("Join a team in this league to propose trades"); return; }
    if (!activeLeagueCtx?.id) { toast.error("League context missing"); return; }
    tradeBuilder.openBuilder({ leagueId: activeLeagueCtx.id, myTeam });
    const ownerTeam = (liveTeams || []).find(
      (t: any) => (t.logo_abbr || (t.name || "").slice(0, 3).toUpperCase()) === ownerAbbr,
    );
    const year = new Date().getFullYear();
    tradeBuilder.addPick({
      id: `draft-room-pick-${overall}`,
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
  const currentRound = Math.ceil(draftConfig.currentPick / totalTeams);
  const currentPickInRound = ((draftConfig.currentPick - 1) % totalTeams) + 1;

  const positions = [
    { value: "all", label: "All Positions" },
    { value: "C", label: "Center" },
    { value: "LW", label: "Left Wing" },
    { value: "RW", label: "Right Wing" },
    { value: "D", label: "Defense" },
    { value: "G", label: "Goalie" },
  ];

  const currentCriteria = draftCriteria.find((c) => c.value === selectedCriteria);

  return (
    <AppLayout>
      <TooltipProvider>
        <div className="space-y-4">
          {/* ── Header row ─────────────────────────────────────────────── */}
          <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-4">
            <div className="flex-1 min-w-0 flex flex-col gap-3">
              <div className="flex items-start gap-4 flex-wrap">
              <div>
                <h1 className="text-2xl font-bold text-foreground flex items-center gap-2">
                  <LayoutGrid className="h-6 w-6 text-primary" />
                  Draft Room
                </h1>
                <p className="text-sm text-muted-foreground">
                  2026 NHL Entry Draft — League Rookie Draft
                </p>
              </div>

              {/* Iter 147 — Draft Criteria is now READ-ONLY. The value is set in
                  League Administration → Drafts and just displayed here. */}
              <Popover>
                <PopoverTrigger asChild>
                  <Button variant="outline" size="sm" className="gap-1.5" data-testid="draft-room-criteria-trigger">
                    <Info className="h-3.5 w-3.5" />
                    Draft Criteria: {currentCriteria?.label}
                  </Button>
                </PopoverTrigger>
                <PopoverContent className="w-80 bg-popover border-border z-50" align="start">
                  <div className="space-y-3">
                    <h4 className="font-semibold text-sm text-foreground">Eligible Player Criteria</h4>
                    <div
                      className="rounded-md border border-border px-3 py-2 text-sm bg-secondary/40"
                      data-testid="draft-room-criteria-display"
                    >
                      <span className="font-medium">{currentCriteria?.label}</span>
                    </div>
                    <div className="bg-secondary/50 rounded-md p-3">
                      <p className="text-xs text-muted-foreground leading-relaxed">
                        {currentCriteria?.description}
                      </p>
                    </div>
                    <p
                      className="text-[11px] italic text-muted-foreground"
                      data-testid="draft-room-criteria-readonly-note"
                    >
                      Configured in League Administration → Drafts.
                    </p>
                  </div>
                </PopoverContent>
              </Popover>

              {/* Iter 147 — Propose Trade toggle (mirrors Draft Board) */}
              <Button
                size="sm"
                variant={tradeMode ? "default" : "outline"}
                onClick={() => setTradeMode((v) => !v)}
                data-testid="draft-room-trade-toggle"
                aria-pressed={tradeMode}
                className={tradeMode ? "bg-emerald-500 hover:bg-emerald-600 text-white gap-1.5" : "gap-1.5"}
              >
                <Repeat className="h-3.5 w-3.5" />
                {tradeMode ? "Trade Mode: On" : "Trade Mode: Off"}
              </Button>

              {/* Iter 149 — Trading Block overlay toggle */}
              <Button
                size="sm"
                variant={tradeBlockMode ? "default" : "outline"}
                onClick={() => setTradeBlockMode((v) => !v)}
                data-testid="draft-room-trade-block-toggle"
                aria-pressed={tradeBlockMode}
                className={tradeBlockMode ? "bg-amber-500 hover:bg-amber-600 text-white gap-1.5" : "gap-1.5"}
              >
                <Megaphone className="h-3.5 w-3.5" />
                {tradeBlockMode ? "Trading Block: On" : "Trading Block: Off"}
                {tradeBlockItems.length > 0 && (
                  <span
                    className={cn(
                      "ml-0.5 inline-flex items-center justify-center h-4 min-w-4 px-1 rounded-full text-[9px] font-bold",
                      tradeBlockMode ? "bg-white/20 text-white" : "bg-amber-500/20 text-amber-300",
                    )}
                    data-testid="draft-room-trade-block-count"
                  >
                    {tradeBlockItems.length}
                  </span>
                )}
              </Button>
            </div>

            {/* Iter 153 — SelectedPlayerCard sits *inside* the left flex item so
                it ends where the draft clock begins (not under it) and can grow
                taller to fill the open space. */}
            <SelectedPlayerCard
              player={
                selectedPlayerId
                  ? players.find((p) => String(p.id) === String(selectedPlayerId)) || null
                  : null
              }
              isOnTheClock={draftConfig.draftStarted}
              isQueued={!!selectedPlayerId && queue.includes(Number(selectedPlayerId))}
              isShortlisted={!!selectedPlayerId && shortlist.has(Number(selectedPlayerId))}
              onDraftPlayer={(p) => {
                toast.success(`Draft ${p.name} — locked for current pick`);
                setSelectedPlayerId(null);
              }}
              onToggleQueue={(id) => toggleQueue(Number(id))}
              onToggleShortlist={(id) => toggleShortlist(Number(id))}
              onClose={() => setSelectedPlayerId(null)}
              onExpand={(p) => setExpandedPlayer(p)}
            />
            </div>

            {/* Draft Timer Card */}
            <Card className="border-border bg-card/80 min-w-[320px]">
              <CardContent className="p-4 space-y-3">
                {!draftConfig.draftStarted ? (
                  <>
                    <div className="flex items-center gap-2 text-sm text-muted-foreground">
                      <Clock className="h-4 w-4" />
                      <span>Draft starts in</span>
                    </div>
                    <div className="text-3xl font-mono font-bold text-primary tracking-widest text-center">
                      {formatCountdown(countdown)}
                    </div>
                    <p className="text-[11px] text-muted-foreground text-center">
                      Scheduled: {draftConfig.scheduledTime?.toLocaleString()}
                    </p>
                    <Button variant="ice" size="sm" className="w-full" onClick={handleEarlyStart}>
                      <Play className="h-3.5 w-3.5 mr-1" />
                      Start Draft Early (No Clock)
                    </Button>
                    <Button
                      variant="gold"
                      size="sm"
                      className="w-full"
                      onClick={() => setDraftConfig((prev) => ({ ...prev, draftStarted: true, earlyStart: false }))}
                    >
                      <Timer className="h-3.5 w-3.5 mr-1" />
                      Start Draft (With Timer)
                    </Button>
                  </>
                ) : (
                  <>
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <div className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
                        <span className="text-sm font-semibold text-foreground">Draft Live</span>
                      </div>
                      {draftConfig.earlyStart && countdown > 0 && (
                        <Badge variant="outline" className="text-[10px] text-amber-400 border-amber-400/30">
                          <AlertCircle className="h-3 w-3 mr-1" />
                          No Clock
                        </Badge>
                      )}
                    </div>
                    <div className="bg-secondary/50 rounded-lg p-3 text-center space-y-1">
                      <p className="text-[10px] uppercase tracking-wider text-muted-foreground">On the Clock</p>
                      <p className="text-lg font-bold text-foreground">{onTheClockTeamFull?.name}</p>
                      <p className="text-xs text-muted-foreground">
                        Round {currentRound}, Pick {currentPickInRound} (#{draftConfig.currentPick} overall)
                      </p>
                    </div>
                    {isClockActive && (
                      <div className="space-y-1.5">
                        <div className="flex items-center justify-between text-xs">
                          <span className="flex items-center gap-1 text-muted-foreground">
                            <Timer className="h-3 w-3" />
                            Pick Timer
                            {timerPaused && (
                              <Badge variant="outline" className="text-[10px] text-amber-400 border-amber-400/30 ml-1">
                                Paused
                              </Badge>
                            )}
                          </span>
                          <span className={cn("font-mono font-bold text-lg", timerPaused ? "text-muted-foreground" : pickTimeLeft <= 15 ? "text-destructive" : "text-primary")}>
                            {formatPickTimer(pickTimeLeft)}
                          </span>
                        </div>
                        <Progress value={(pickTimeLeft / draftConfig.pickTimerSeconds) * 100} className="h-1.5" />
                        {isLeagueManager && (
                          <Button
                            variant={timerPaused ? "gold" : "outline"}
                            size="sm"
                            className="w-full mt-1"
                            onClick={() => setTimerPaused((prev) => !prev)}
                          >
                            {timerPaused ? (
                              <>
                                <Play className="h-3.5 w-3.5 mr-1" />
                                Resume Timer
                              </>
                            ) : (
                              <>
                                <Pause className="h-3.5 w-3.5 mr-1" />
                                Pause Timer
                              </>
                            )}
                          </Button>
                        )}
                      </div>
                    )}
                    {draftConfig.earlyStart && countdown > 0 && (
                      <p className="text-[10px] text-muted-foreground text-center">
                        Clock activates in {formatCountdown(countdown)}
                      </p>
                    )}
                  </>
                )}
              </CardContent>
            </Card>
          </div>

          {/* ── Draft Board (full width, top) ──────────────────────────── */}
          <Card className="border-border">
            <CardHeader className="pb-2">
              <CardTitle className="text-base">Draft Board</CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              <ScrollArea className="w-full">
                <div className="min-w-[700px] p-4 pt-0">
                  <div
                    className="grid gap-1 mb-1 sticky top-0 bg-card z-10 pt-2"
                    style={{ gridTemplateColumns: `48px repeat(${totalTeams}, minmax(72px, 1fr))` }}
                  >
                    <div className="p-1.5 text-[10px] font-semibold text-muted-foreground uppercase">Rd</div>
                    {teamAbbrs.map((abbr) => (
                      <div
                        key={abbr}
                        className={cn(
                          "p-1.5 text-[10px] font-semibold text-center text-muted-foreground uppercase truncate rounded",
                          abbr === onTheClockTeam && draftConfig.draftStarted
                            ? "bg-primary/15 text-primary"
                            : abbr === myTeam?.abbr
                            ? "bg-accent/10 text-accent"
                            : "bg-secondary/50"
                        )}
                      >
                        {abbr}
                      </div>
                    ))}
                  </div>
                  {allPicks.map((roundPicks, rIdx) => {
                    const round = rIdx + 1;
                    return (
                      <div
                        key={round}
                        className="grid gap-1 mb-1"
                        style={{ gridTemplateColumns: `48px repeat(${totalTeams}, minmax(72px, 1fr))` }}
                      >
                        <div className="p-1.5 flex items-center justify-center text-[10px] font-bold text-muted-foreground bg-secondary/30 rounded">
                          {round}
                        </div>
                        {teamAbbrs.map((teamAbbr) => {
                          const pick = roundPicks.find((p) => p.team === teamAbbr);
                          const isCurrentPick = pick?.overall === draftConfig.currentPick && draftConfig.draftStarted;
                          // Iter 149 — Trade block overlay highlight
                          // Match by EITHER the team's stored abbr OR a 3-char slice of its name
                          // (mock draft uses abbrs like ICE which match the name fallback "Ice Breakers".slice(0,3) = "ICE")
                          const ownerTeam = (liveTeams || []).find((t: any) => {
                            const nameAbbr = (t.name || "").replace(/\s/g, "").slice(0, 3).toUpperCase();
                            const fullName = (t.name || "").split(" ").map((w: string) => w[0]).join("").toUpperCase();
                            return t.logo_abbr === teamAbbr || nameAbbr === teamAbbr || fullName === teamAbbr;
                          });
                          const isPlayerOnBlock = pick?.player && tradeBlockPlayerIds.has(String(pick.player.id));
                          const isPickOnBlock = ownerTeam?.id && tradeBlockOverallKeys.has(`${ownerTeam.id}|R${round}`);
                          // Iter 151 — on-block megaphone overlays are ALWAYS visible
                          // (no longer gated by tradeBlockMode). The toggle only controls
                          // the interactive "Mark available" quick-add buttons below.
                          const onBlock = isPlayerOnBlock || isPickOnBlock;
                          const isMyTile = ownerTeam?.id && ownerTeam.id === myTeam?.id;
                          return (
                            <div
                              key={`${round}-${teamAbbr}`}
                              className={cn(
                                "p-1.5 rounded border text-center min-h-[52px] flex flex-col items-center justify-center gap-0.5 transition-all relative",
                                isCurrentPick
                                  ? "bg-primary/10 border-primary/50 ring-1 ring-primary/30"
                                  : pick?.player
                                  ? "bg-secondary/60 border-border"
                                  : "bg-card/50 border-border/50",
                                onBlock && "ring-1 ring-amber-400/60 border-amber-400/40",
                              )}
                              data-testid={onBlock ? `draft-room-block-tile-${teamAbbr}-${pick?.overall ?? "x"}` : undefined}
                            >
                              <span className="text-[9px] text-muted-foreground">#{pick?.overall}</span>
                              {pick?.player ? (
                                <>
                                  <span className="text-[10px] font-medium text-foreground truncate w-full leading-tight">
                                    {pick.player.name.split(" ").map((n, i) => i === 0 ? n[0] + "." : n).join(" ")}
                                  </span>
                                  <Badge className={cn("text-[9px] px-1 py-0 h-3.5 border", positionColors[pick.player.position] || "bg-muted text-muted-foreground")}>
                                    {pick.player.position}
                                  </Badge>
                                </>
                              ) : (
                                <span className="text-[10px] text-muted-foreground/40">—</span>
                              )}
                              {/* Iter 149 — Megaphone icon overlay when the player or pick is on trade block */}
                              {onBlock && (
                                <Tooltip>
                                  <TooltipTrigger asChild>
                                    <span
                                      className="absolute top-0.5 left-0.5 inline-flex items-center justify-center h-4 w-4 rounded-sm bg-amber-500/25 text-amber-300"
                                      data-testid={`draft-room-block-icon-${teamAbbr}-${pick?.overall ?? "x"}`}
                                    >
                                      <Megaphone className="h-2.5 w-2.5" />
                                    </span>
                                  </TooltipTrigger>
                                  <TooltipContent>
                                    {isPlayerOnBlock ? "Player available — on trade block" : "Upcoming pick available — on trade block"}
                                  </TooltipContent>
                                </Tooltip>
                              )}
                              {/* Iter 149/150/152 — "Mark available for draft" quick-add.
                                  Iter 152: only own-team tiles render the add button. Other teams'
                                  on-block items remain visible at all times via the `onBlock` icon above. */}
                              {tradeBlockMode && !onBlock && isMyTile && (
                                <Tooltip>
                                  <TooltipTrigger asChild>
                                    <button
                                      type="button"
                                      onClick={(e) => {
                                        e.stopPropagation();
                                        if (pick?.player) {
                                          markAvailableForDraft("player", { id: pick.player.id, name: pick.player.name });
                                        } else {
                                          markAvailableForDraft("pick", { year: new Date().getFullYear(), round, name: `R${round}` });
                                        }
                                      }}
                                      data-testid={`draft-room-block-add-${teamAbbr}-${pick?.overall ?? "x"}`}
                                      aria-label="Mark available for draft"
                                      className="absolute top-0.5 left-0.5 h-4 w-4 inline-flex items-center justify-center rounded-sm bg-amber-500/20 text-amber-300 hover:bg-amber-500/35"
                                    >
                                      <Megaphone className="h-2.5 w-2.5" />
                                    </button>
                                  </TooltipTrigger>
                                  <TooltipContent>Mark available for draft</TooltipContent>
                                </Tooltip>
                              )}
                              {/* Iter 147 — Per-pick trade button (visible only in trade mode) */}
                              {tradeMode && pick && (
                                <button
                                  type="button"
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    handleAddDraftPickToTrade(pick.team, round, pick.overall, pick.player);
                                  }}
                                  data-testid={`draft-room-pick-trade-${pick.team}-${pick.overall}`}
                                  aria-label="Add pick to trade"
                                  className="absolute top-0.5 right-0.5 h-4 w-4 inline-flex items-center justify-center rounded-sm bg-emerald-500/15 text-emerald-300 hover:bg-emerald-500/30"
                                >
                                  <Repeat className="h-2.5 w-2.5" />
                                </button>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    );
                  })}
                  <div className="flex items-center gap-3 mt-3 pt-2 border-t border-border">
                    <span className="text-[10px] text-muted-foreground">Positions:</span>
                    {Object.entries(positionColors).map(([pos, colorClass]) => (
                      <Badge key={pos} className={cn("text-[9px] px-1.5 py-0 h-3.5 border", colorClass)}>{pos}</Badge>
                    ))}
                  </div>
                </div>
              </ScrollArea>
            </CardContent>
          </Card>

          {/* ── Bottom section: (LEFT) Player Search tabs · (CENTER) Truncated Roster · (RIGHT) Draft Chat ── */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
            {/* LEFT: Player Search (Iter 150 — Eligible | My Queue | Shortlist) */}
            <div className="lg:col-span-4">
              <Tabs defaultValue="eligible" className="w-full">
                <TabsList className="w-full grid grid-cols-3">
                  <TabsTrigger value="eligible" data-testid="draft-room-tab-eligible">Eligible</TabsTrigger>
                  <TabsTrigger value="queue" data-testid="draft-room-tab-queue">
                    <ListOrdered className="h-3.5 w-3.5 mr-1" />
                    Queue ({queue.length})
                  </TabsTrigger>
                  <TabsTrigger value="shortlist" data-testid="draft-room-tab-shortlist">
                    <Star className="h-3.5 w-3.5 mr-1" />
                    Shortlist ({shortlistedPlayers.length})
                  </TabsTrigger>
                </TabsList>

                <TabsContent value="eligible" className="mt-3 space-y-3">
                  <div className="flex gap-2">
                    <div className="relative flex-1">
                      <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
                      <Input
                        placeholder="Search players..."
                        className="pl-8 h-8 text-sm bg-secondary/50"
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                      />
                    </div>
                    <Select value={positionFilter} onValueChange={setPositionFilter}>
                      <SelectTrigger className="w-[100px] h-8 text-xs bg-secondary/50">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent className="bg-popover border-border z-50">
                        {positions.map((p) => (
                          <SelectItem key={p.value} value={p.value}>{p.label}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>

                  <Badge variant="secondary" className="text-[10px]">
                    {filteredPlayers.length} players available
                  </Badge>

                  <ScrollArea className="h-[400px]">
                    <div className="space-y-1">
                      {filteredPlayers.map((player) => {
                        // Iter 151 — on-block visibility no longer requires the toggle
                        const isOnBlock = tradeBlockPlayerIds.has(String(player.id));
                        const isQueued = queue.includes(player.id);
                        const isShortlisted = shortlist.has(player.id);
                        return (
                        <div
                          key={player.id}
                          className={cn(
                            "flex items-center gap-2 p-2 rounded-md hover:bg-secondary/40 transition-colors group cursor-pointer",
                            isOnBlock && "ring-1 ring-amber-400/40 bg-amber-500/5",
                            String(selectedPlayerId) === String(player.id) && "bg-primary/10 ring-1 ring-primary/40",
                          )}
                          onClick={() => setSelectedPlayerId(String(player.id))}
                          data-testid={isOnBlock ? `draft-room-eligible-block-${player.id}` : `draft-room-eligible-row-${player.id}`}
                        >
                          <span className="text-[10px] font-mono text-muted-foreground w-5 text-right shrink-0">
                            {player.ranking}
                          </span>
                          <Badge className={cn("text-[9px] px-1 py-0 h-3.5 border shrink-0", positionColors[player.position])}>
                            {player.position}
                          </Badge>
                          {/* Iter 150 — Status icons (shortlisted / queued) right beside the position chip */}
                          {isShortlisted && (
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <span className="inline-flex h-4 w-4 items-center justify-center rounded-sm bg-amber-500/20 text-amber-300 shrink-0"
                                      data-testid={`draft-room-status-shortlisted-${player.id}`}>
                                  <Star className="h-2.5 w-2.5 fill-current" />
                                </span>
                              </TooltipTrigger>
                              <TooltipContent>Shortlisted</TooltipContent>
                            </Tooltip>
                          )}
                          {isQueued && (
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <span className="inline-flex h-4 w-4 items-center justify-center rounded-sm bg-primary/20 text-primary shrink-0"
                                      data-testid={`draft-room-status-queued-${player.id}`}>
                                  <ListOrdered className="h-2.5 w-2.5" />
                                </span>
                              </TooltipTrigger>
                              <TooltipContent>In queue (#{queue.indexOf(player.id) + 1})</TooltipContent>
                            </Tooltip>
                          )}
                          {isOnBlock && (
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <span className="inline-flex h-4 w-4 items-center justify-center rounded-sm bg-amber-500/25 text-amber-300 shrink-0">
                                  <Megaphone className="h-2.5 w-2.5" />
                                </span>
                              </TooltipTrigger>
                              <TooltipContent>On trade block</TooltipContent>
                            </Tooltip>
                          )}
                          <div className="flex-1 min-w-0">
                            <p className="text-sm font-medium text-foreground truncate">{player.name}</p>
                            <p className="text-[10px] text-muted-foreground">
                              {player.league} · {player.age}y · {player.gp}GP {player.g}G {player.a}A {player.pts}P
                            </p>
                          </div>
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <Button
                                variant="ghost"
                                size="icon"
                                className={cn(
                                  "h-7 w-7 shrink-0 transition-colors",
                                  shortlist.has(player.id) ? "text-accent" : "text-muted-foreground/30 hover:text-accent"
                                )}
                                onClick={(e) => { e.stopPropagation(); toggleShortlist(player.id); }}
                              >
                                <Star className={cn("h-3.5 w-3.5", shortlist.has(player.id) && "fill-current")} />
                              </Button>
                            </TooltipTrigger>
                            <TooltipContent>{shortlist.has(player.id) ? "Remove from shortlist" : "Add to shortlist"}</TooltipContent>
                          </Tooltip>
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <Button
                                variant="ghost"
                                size="icon"
                                className={cn(
                                  "h-7 w-7 shrink-0 transition-colors",
                                  queue.includes(player.id) ? "text-primary" : "text-muted-foreground/30 hover:text-primary"
                                )}
                                onClick={(e) => { e.stopPropagation(); toggleQueue(player.id); }}
                              >
                                <ListOrdered className={cn("h-3.5 w-3.5")} />
                              </Button>
                            </TooltipTrigger>
                            <TooltipContent>{queue.includes(player.id) ? "Remove from queue" : "Add to queue"}</TooltipContent>
                          </Tooltip>
                        </div>
                        );
                      })}
                    </div>
                  </ScrollArea>
                </TabsContent>

                {/* Iter 150 — Queue moved into a tab (was the col-2 LEFT card) */}
                <TabsContent value="queue" className="mt-3">
                  <p className="text-[10px] text-muted-foreground px-1 pb-2">
                    Private — only you can see this
                  </p>
                  <ScrollArea className="h-[420px]" data-testid="draft-room-queue-list">
                    {queuedPlayers.length === 0 ? (
                      <div className="text-center py-12 space-y-2">
                        <ListOrdered className="h-8 w-8 text-muted-foreground/20 mx-auto" />
                        <p className="text-sm text-muted-foreground">Queue is empty</p>
                        <p className="text-xs text-muted-foreground/60">Use the queue icon in eligible players</p>
                      </div>
                    ) : (
                      <div className="space-y-1">
                        {queuedPlayers.map((player, idx) => (
                          <div key={player.id}
                               className="flex items-center gap-2 p-2 rounded-md bg-secondary/30 group"
                               data-testid={`draft-room-queue-row-${player.id}`}>
                            <span className="text-[10px] font-mono text-muted-foreground w-5 text-right shrink-0">{idx + 1}.</span>
                            <Badge className={cn("text-[9px] px-1 py-0 h-3.5 border shrink-0", positionColors[player.position])}>
                              {player.position}
                            </Badge>
                            <div className="flex-1 min-w-0">
                              <p className="text-sm font-medium text-foreground truncate">{player.name}</p>
                              <p className="text-[10px] text-muted-foreground">#{player.ranking} · {player.league}</p>
                            </div>
                            <Button
                              variant="ghost"
                              size="icon"
                              className="h-6 w-6 text-muted-foreground hover:text-destructive opacity-0 group-hover:opacity-100"
                              onClick={() => removeFromQueue(player.id)}
                            >
                              <X className="h-3 w-3" />
                            </Button>
                          </div>
                        ))}
                      </div>
                    )}
                  </ScrollArea>
                </TabsContent>

                <TabsContent value="shortlist" className="mt-3">
                  <ScrollArea className="h-[450px]">
                    {shortlistedPlayers.length === 0 ? (
                      <div className="text-center py-12 space-y-2">
                        <Star className="h-8 w-8 text-muted-foreground/20 mx-auto" />
                        <p className="text-sm text-muted-foreground">No players shortlisted yet</p>
                        <p className="text-xs text-muted-foreground/60">Star players to add them here</p>
                      </div>
                    ) : (
                      <div className="space-y-1">
                        {shortlistedPlayers.map((player, idx) => (
                          <div key={player.id} className="flex items-center gap-2 p-2 rounded-md bg-secondary/30 group">
                            <span className="text-[10px] font-medium text-muted-foreground w-4 shrink-0">{idx + 1}.</span>
                            <Badge className={cn("text-[9px] px-1 py-0 h-3.5 border shrink-0", positionColors[player.position])}>
                              {player.position}
                            </Badge>
                            <div className="flex-1 min-w-0">
                              <p className="text-sm font-medium text-foreground truncate">{player.name}</p>
                              <p className="text-[10px] text-muted-foreground">#{player.ranking} · {player.league} · {player.pts}P</p>
                            </div>
                            <Button
                              variant="ghost"
                              size="icon"
                              className="h-6 w-6 opacity-0 group-hover:opacity-100 text-muted-foreground hover:text-destructive"
                              onClick={() => toggleShortlist(player.id)}
                            >
                              <X className="h-3 w-3" />
                            </Button>
                          </div>
                        ))}
                      </div>
                    )}
                  </ScrollArea>
                </TabsContent>
              </Tabs>
            </div>

            {/* CENTER: Truncated Roster (Iter 150) */}
            <div className="lg:col-span-4">
              <TruncatedRosterPanel
                leagueId={activeLeagueCtx?.id}
                myTeamId={myTeam?.id}
                teams={(liveTeams || []).map((t: any) => ({
                  id: t.id,
                  name: t.name,
                }))}
                tradeBlockItems={tradeBlockItems}
                capEnabled={!!activeLeagueCtx?.cap_enabled}
                onToggleTradeBlock={toggleMyTeamTradeBlock}
                onPickPlayerForTrade={(team, player) => {
                  if (!team || !player) return;
                  if (!tradeBuilder.isOpen) {
                    tradeBuilder.openBuilder({ leagueId: activeLeagueCtx?.id, myTeam });
                  }
                  tradeBuilder.addAsset({
                    id: String(player.id),
                    name: player.name,
                    position: player.position,
                    ownerTeamId: team.id,
                    ownerTeamName: team.name,
                    capHit: player.cap_hit,
                  });
                  toast.success(`Added ${player.name} to trade — ${team.name}`);
                }}
              />
            </div>

            {/* RIGHT: Chat */}
            <div className="lg:col-span-4">
              <DraftChatPanel
                chatMessages={chatMessages}
                chatInput={chatInput}
                setChatInput={setChatInput}
                onSendChat={handleSendChat}
                mySender={myTeam?.name || "Team Frostbite"}
                leagueId={activeLeagueCtx?.id}
                myUserId={user?.id}
                isCommissioner={!!(activeLeagueCtx?.is_commissioner || activeLeagueCtx?.commissioner_id === user?.id)}
                league={activeLeagueCtx}
              />
            </div>
          </div>
        </div>

        {/* Iter 153 — Expanded Player Card (window-within-window via PlayerCardModal) */}
        {expandedPlayer && (
          <PlayerCardModal
            open={!!expandedPlayer}
            onOpenChange={(o) => !o && setExpandedPlayer(null)}
            player={{
              id: expandedPlayer.id,
              name: expandedPlayer.name,
              team: expandedPlayer.team || expandedPlayer.nhl_team || expandedPlayer.league || "—",
              position: expandedPlayer.position,
              age: expandedPlayer.age ?? 19,
              points: expandedPlayer.pts || 0,
              contract: { type: "Rookie", salary: 0, yearsRemaining: 0 },
              schedule: [],
              categoryBreakdown: {
                G:  expandedPlayer.g || 0,
                A:  expandedPlayer.a || 0,
                PTS: expandedPlayer.pts || 0,
                PPP: 0,
                SOG: expandedPlayer.shots || 0,
                HIT: 0,
                BLK: 0,
                PIM: expandedPlayer.pim || 0,
              },
              statsByPeriod: {
                "1d": 0, "7d": 0, "14d": 0, "30d": 0,
                "60d": 0, "100d": 0, season: expandedPlayer.pts || 0,
              },
            } as any}
          />
        )}
      </TooltipProvider>
    </AppLayout>
  );
}
