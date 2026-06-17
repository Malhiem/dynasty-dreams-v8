// @ts-nocheck
import { useState, useMemo, useEffect, useCallback, useRef } from "react";
// Iter 170h — Socket.IO subscription for live draft updates.
import { useSocket } from "@/hooks/use-socket";
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
  ArrowRightLeft,
  RotateCcw,
  Activity,
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
import PickProvenance from "@/lovable/pages/draftroom/PickProvenance";
import api from "@/lib/api";

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

// ─── League teams (mock fallback — used only when no league is active) ──────

const mockLeagueTeams = [
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

// ─── Position colors ─────────────────────────────────────────────────────────

const positionColors: Record<string, string> = {
  C: "bg-blue-600/80 text-blue-100 border-blue-500/50",
  LW: "bg-emerald-600/80 text-emerald-100 border-emerald-500/50",
  RW: "bg-teal-600/80 text-teal-100 border-teal-500/50",
  D: "bg-amber-600/80 text-amber-100 border-amber-500/50",
  G: "bg-purple-600/80 text-purple-100 border-purple-500/50",
};

// Iter 170e — softer position tints used to wash the drafted-pick tile
// background so a manager can scan position distribution at a glance.
const positionTints: Record<string, string> = {
  C: "bg-blue-500/15 border-blue-500/40",
  LW: "bg-emerald-500/15 border-emerald-500/40",
  RW: "bg-teal-500/15 border-teal-500/40",
  D: "bg-amber-500/15 border-amber-500/40",
  G: "bg-purple-500/15 border-purple-500/40",
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
  // Iter 170b — League context hooks lifted to the top so the
  // derived `boardTeams` / `boardTeamAbbrs` / `totalTeams` can
  // depend on liveTeams + so the existing useEffects that consume
  // activeLeagueCtx still satisfy Rules of Hooks ordering.
  const tradeBuilder = useTradeBuilder();
  const { user } = useAuth();
  const { league: activeLeagueCtx, leagueTeams: liveTeams } = useActiveLeague();

  // Iter 170b — Real-league wiring for the Draft Board. When the
  // active league has teams loaded, use those for column headers,
  // snake-draft order, and the "picks until your turn" counter.
  // Falls back to the mock 12-team roster ONLY when the user isn't
  // attached to a league yet (e.g. Storybook / standalone demo).
  // Iter 170e — Use the backend-computed `logo_abbr` (which already
  // honours `logo_abbr_override` and splits on `-` like " ") and
  // dedupe collisions (e.g. two CC teams in the same league) by
  // appending a suffix to the second occurrence so each board column
  // gets a stable, unique key.
  const boardTeams = useMemo<Array<{ id?: string; name: string; abbr: string }>>(() => {
    if (Array.isArray(liveTeams) && liveTeams.length > 0) {
      const seen = new Map<string, number>();
      return liveTeams.map((t: any) => {
        let abbr =
          t.logo_abbr ||
          (t.name || "").replace(/-/g, " ").split(" ").map((w: string) => w[0] || "").join("").toUpperCase().slice(0, 4) ||
          (t.name || "").slice(0, 3).toUpperCase();
        const count = seen.get(abbr) || 0;
        seen.set(abbr, count + 1);
        if (count > 0) abbr = `${abbr}${count + 1}`;
        return { id: t.id || t._id, name: t.name, abbr };
      });
    }
    return mockLeagueTeams as Array<{ id?: string; name: string; abbr: string }>;
  }, [liveTeams]);

  const boardTeamAbbrs = useMemo(() => boardTeams.map((t) => t.abbr), [boardTeams]);
  const totalTeams = boardTeams.length;

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
  // Iter 170f — Last picked player id. The SelectedPlayerCard tile
  // defaults to this when the user isn't actively previewing a player.
  // "Live View" button reverts to this default after a preview click.
  const [lastPickedPlayerId, setLastPickedPlayerId] = useState<string | null>(null);
  // Iter 170i — Commissioner undo + swap-popover UI state.
  const [undoCount, setUndoCount] = useState<number>(1);
  const [swapPickOverall, setSwapPickOverall] = useState<number | null>(null);
  const [swapSearch, setSwapSearch] = useState<string>("");
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
  // (Iter 170h — isLeagueManager moved down to derive from the active
  // league context; see below.)

  // Iter 170f — Persistence. The Draft Room is currently a mock and
  // the real `POST /api/drafts/{id}/pick` wiring is queued as P3.
  // Until then, mirror `picks`, `currentPick`, `draftStarted` and
  // `lastPickedPlayerId` into localStorage keyed by the active league
  // id so a manager doesn't lose progress on page reload.
  const draftStorageKey = activeLeagueCtx?.id
    ? `draftroom-state-v1:${activeLeagueCtx.id}`
    : null;
  const hasHydratedRef = useRef(false);
  useEffect(() => {
    if (!draftStorageKey || hasHydratedRef.current) return;
    try {
      const raw = localStorage.getItem(draftStorageKey);
      if (!raw) { hasHydratedRef.current = true; return; }
      const data = JSON.parse(raw);
      if (Array.isArray(data.picks) && data.picks.length > 0) {
        setPicks(data.picks);
        // Mark drafted players so the eligible list reflects history.
        const draftedIds = new Set(
          data.picks
            .map((p: any) => p.player?.id)
            .filter((id: any) => id !== undefined && id !== null)
            .map(String),
        );
        if (draftedIds.size > 0) {
          setPlayers((prev) =>
            prev.map((p) =>
              draftedIds.has(String(p.id))
                ? { ...p, drafted: true }
                : p,
            ),
          );
        }
      }
      if (typeof data.currentPick === "number") {
        setDraftConfig((prev) => ({
          ...prev,
          currentPick: data.currentPick,
          draftStarted: !!data.draftStarted,
        }));
      }
      if (data.lastPickedPlayerId) {
        setLastPickedPlayerId(String(data.lastPickedPlayerId));
      }
    } catch {
      /* ignore parse errors */
    }
    hasHydratedRef.current = true;
  }, [draftStorageKey]);
  useEffect(() => {
    if (!draftStorageKey || !hasHydratedRef.current) return;
    try {
      localStorage.setItem(
        draftStorageKey,
        JSON.stringify({
          picks,
          currentPick: draftConfig.currentPick,
          draftStarted: draftConfig.draftStarted,
          lastPickedPlayerId,
        }),
      );
    } catch {
      /* storage quota — non-fatal */
    }
  }, [draftStorageKey, picks, draftConfig.currentPick, draftConfig.draftStarted, lastPickedPlayerId]);

  // Iter 170g — Backend draft wiring. On mount with an active league
  // context, auto-init (or fetch) the draft so we can POST picks +
  // hydrate state from the source of truth instead of relying solely
  // on localStorage. Commissioner-only; non-commish viewers just read.
  const [currentDraft, setCurrentDraft] = useState<any>(null);
  const isDraftActive = currentDraft?.status === "active";
  // Iter 170h — bumped after every backend pick so the My Roster tile
  // (TruncatedRosterPanel) refetches the active team and shows the
  // newly drafted player without a full page reload.
  const [rosterReloadTick, setRosterReloadTick] = useState(0);
  useEffect(() => {
    if (!activeLeagueCtx?.id) { setCurrentDraft(null); return; }
    let cancelled = false;
    (async () => {
      try {
        const { data } = await api.post(`/drafts/auto-init/${activeLeagueCtx.id}`);
        if (cancelled) return;
        const d = data?.draft;
        if (!d) return;
        setCurrentDraft(d);
        // Hydrate picks + currentPick from backend if any picks exist
        if (Array.isArray(d.picks) && d.picks.length > 0) {
          setPicks(d.picks.map((p: any) => ({
            round: p.round,
            pickInRound: p.pick_in_round,
            overall: p.overall,
            team: p.team,
            player: p.player,
          })));
          const lastPlayerId = d.picks[d.picks.length - 1]?.player_id;
          if (lastPlayerId) setLastPickedPlayerId(String(lastPlayerId));
        }
        if (typeof d.current_pick === "number") {
          setDraftConfig((prev) => ({
            ...prev,
            currentPick: d.current_pick,
            draftStarted: d.status === "active",
            totalRounds: d.total_rounds || prev.totalRounds,
            pickTimerSeconds: d.time_per_pick || prev.pickTimerSeconds,
          }));
        }
      } catch (e) {
        // Non-commissioners get 403 → fall back to mock/local-only flow
        if (!cancelled) setCurrentDraft(null);
      }
    })();
    return () => { cancelled = true; };
  }, [activeLeagueCtx?.id]);

  // Iter 170g — Fetch real eligible players for the active draft.
  // Replaces the mock list when a draft exists; the SelectedPlayerCard
  // will then render real NHL stats + headshot.
  useEffect(() => {
    if (!currentDraft?._id) return;
    let cancelled = false;
    api.get(`/drafts/${currentDraft._id}/eligible-players?limit=100`)
      .then((res) => {
        if (cancelled) return;
        const real = (res.data?.players || []) as any[];
        if (real.length === 0) return;
        // Mark already-drafted players based on backend picks
        const draftedIds = new Set(
          (currentDraft.picks || [])
            .map((p: any) => p.player_id)
            .filter(Boolean)
            .map(String),
        );
        setPlayers(real.map((p) => ({
          id: p.id,
          name: p.name,
          position: p.position,
          nhlTeam: p.nhlTeam || "—",
          age: p.age || 0,
          league: p.league || "NHL",
          gp: p.gp || 0,
          g: p.g || 0,
          a: p.a || 0,
          pts: p.pts || 0,
          ranking: p.ranking || 0,
          drafted: draftedIds.has(String(p.id)),
          headshot: p.headshot,
          // SelectedPlayerCard reads headshot_url; alias for compatibility.
          headshot_url: p.headshot,
          nhl_id: p.nhl_id,
        }) as any));
      })
      .catch(() => { /* keep mock players */ });
    return () => { cancelled = true; };
  }, [currentDraft?._id]);

  // Iter 170h — Commissioner check (drives undo/swap UI + ability to
  // pick for any team). `isLeagueManager` is kept for backward-compat
  // but is now derived from the active league context. Handles both
  // shapes: `{is_commissioner: true}` (computed by useActiveLeague) and
  // raw `{commissioner_id: ...}`.
  const userId = (user as any)?.id || (user as any)?._id;
  const isLeagueManager = !!(
    activeLeagueCtx?.is_commissioner ||
    activeLeagueCtx?.is_co_commissioner ||
    (userId && activeLeagueCtx?.commissioner_id === userId) ||
    (userId && Array.isArray(activeLeagueCtx?.co_commissioners) && activeLeagueCtx.co_commissioners.includes(userId))
  );

  // (Iter 170h — onTheClockBoardEntry + canPickForCurrentTurn moved
  // below `onTheClockTeam` declaration to avoid TDZ; see below.)

  // Iter 170h — Refetch the canonical draft state + bump roster reload
  // tick. Called from the Socket.IO `draft_pick` / `draft_undo` /
  // `draft_pick_swapped` handlers so every connected manager sees the
  // board update in real time without polling.
  const refreshDraftState = useCallback(async () => {
    if (!currentDraft?._id) return;
    try {
      const { data } = await api.get(`/drafts/${currentDraft._id}`);
      setCurrentDraft(data);
      setPicks((data.picks || []).map((p: any) => ({
        round: p.round, pickInRound: p.pick_in_round, overall: p.overall,
        team: p.team, player: p.player,
      })));
      setDraftConfig((prev) => ({ ...prev, currentPick: data.current_pick }));
      setRosterReloadTick((t) => t + 1);
    } catch { /* ignore — will retry on next event */ }
  }, [currentDraft?._id]);

  // Iter 170h — Subscribe to the draft's Socket.IO room. Listeners fire
  // for every pick / undo / swap broadcast by the backend.
  // Iter 170i — Surface a toast to other managers when a remote event
  // lands. We dedupe self-originated events by stamping a
  // `_selfActionId` ref on local actions and skipping the toast for
  // the matching incoming event.
  const lastSelfPickRef = useRef<string | null>(null);
  const draftRoomId = currentDraft?._id ? `draft_${currentDraft._id}` : null;
  useSocket(
    draftRoomId,
    {
      draft_pick: (p: any) => {
        refreshDraftState();
        // Skip the toast if this is the echo of OUR pick (we already
        // toasted locally in handleDraftPlayer).
        const sig = `${p?.overall}-${p?.player_id}`;
        if (sig && sig !== lastSelfPickRef.current) {
          const team = (boardTeams.find((t) => t.abbr === p?.team)?.name) || p?.team || "A team";
          toast.info(`${team} drafted ${p?.player?.name || "a player"}`, {
            description: `Pick #${p?.overall} · ${p?.player?.position || ""} ${p?.player?.nhlTeam || ""}`.trim(),
          });
        }
      },
      draft_undo: (p: any) => {
        refreshDraftState();
        const count = p?.count || 1;
        const onClk = p?.on_the_clock
          ? (boardTeams.find((t) => t.abbr === p.on_the_clock)?.name || p.on_the_clock)
          : null;
        toast.warning(`Commissioner undid ${count} pick${count === 1 ? "" : "s"}`, {
          description: onClk ? `Now on the clock: ${onClk}` : undefined,
        });
      },
      draft_pick_swapped: (p: any) => {
        refreshDraftState();
        toast.warning(`Commissioner swapped pick #${p?.overall}`, {
          description: p?.pick?.player?.name ? `Now: ${p.pick.player.name}` : undefined,
        });
      },
      draft_chat: (msg: any) => {
        if (!msg?.id) return;
        setChatMessages((prev) =>
          prev.find((m: any) => m.id === msg.id) ? prev : [
            ...prev,
            { ...msg, timestamp: new Date(msg.timestamp || Date.now()) },
          ],
        );
      },
    },
    userId,
  );

  // Iter 170h — Commissioner: undo the last N picks.
  const handleUndoPicks = async (count: number = 1) => {
    if (!currentDraft?._id) {
      // Local-only fallback when no backend draft exists.
      setPicks((prev) => prev.slice(0, Math.max(0, prev.length - count)));
      setDraftConfig((prev) => ({ ...prev, currentPick: Math.max(1, prev.currentPick - count) }));
      return;
    }
    try {
      await api.post(`/drafts/${currentDraft._id}/undo`, { count });
      await refreshDraftState();
      toast.success(`Undid ${count} pick${count === 1 ? "" : "s"}`);
    } catch (e: any) {
      toast.error("Undo failed", { description: e?.response?.data?.detail || e?.message });
    }
  };

  // Iter 170h — Commissioner: replace an existing pick's player.
  const handleSwapPickPlayer = async (overall: number, newPlayerId: string) => {
    if (!currentDraft?._id) {
      toast.info("Swap requires an active backend draft.");
      return;
    }
    try {
      await api.patch(`/drafts/${currentDraft._id}/picks/${overall}`, { new_player_id: newPlayerId });
      await refreshDraftState();
      toast.success(`Pick #${overall} swapped`);
    } catch (e: any) {
      toast.error("Swap failed", { description: e?.response?.data?.detail || e?.message });
    }
  };

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

  // Iter 170j — Auto-pick on timeout. When the pick clock expires
  // (and there's a backend draft + we're not paused), the frontend
  // fires `/drafts/{id}/auto-pick` which picks from the on-clock
  // team's draft_queue (first undrafted) before falling back to the
  // top-ranked eligible player. We only fire once per pick using a
  // ref guard keyed by `currentPick`.
  const lastAutoFireRef = useRef<number | null>(null);
  useEffect(() => { lastAutoFireRef.current = null; }, [draftConfig.currentPick]);
  useEffect(() => {
    if (!isClockActive || timerPaused) return;
    const interval = setInterval(() => {
      setPickTimeLeft((prev) => {
        if (prev <= 1) {
          // Backend-driven auto-pick when a real draft is active.
          if (currentDraft?._id && isDraftActive && lastAutoFireRef.current !== draftConfig.currentPick) {
            lastAutoFireRef.current = draftConfig.currentPick;
            api.post(`/drafts/${currentDraft._id}/auto-pick`)
              .then(() => refreshDraftState())
              .catch(() => {/* ignore — next tick will retry */});
          }
          return draftConfig.pickTimerSeconds;
        }
        return prev - 1;
      });
    }, 1000);
    return () => clearInterval(interval);
  }, [isClockActive, timerPaused, draftConfig.pickTimerSeconds, draftConfig.currentPick, currentDraft?._id, isDraftActive, refreshDraftState]);

  // ─── Draft order ────────────────────────────────────────────────────────────

  const getDraftOrder = useCallback(
    (round: number): string[] => {
      if (draftConfig.snakeDraft && round % 2 === 0) return [...boardTeamAbbrs].reverse();
      return boardTeamAbbrs;
    },
    [draftConfig.snakeDraft, boardTeamAbbrs]
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

  // (Iter 170j — queue hydrate/persist effects moved below `myTeam`
  // declaration to avoid TDZ; see below.)

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

  const handleEarlyStart = async () => {
    // Iter 170g — Backend-aware start: if a draft exists, transition
    // it to active via /drafts/{id}/start so picks can be POSTed.
    if (currentDraft?._id && currentDraft.status !== "active") {
      try {
        await api.post(`/drafts/${currentDraft._id}/start?early_start=true`);
        const { data } = await api.get(`/drafts/${currentDraft._id}`);
        setCurrentDraft(data);
        setDraftConfig((prev) => ({ ...prev, draftStarted: true, earlyStart: true, currentPick: data.current_pick }));
        return;
      } catch (e: any) {
        toast.error("Couldn't start draft", { description: e?.response?.data?.detail || e?.message });
      }
    }
    setDraftConfig((prev) => ({ ...prev, draftStarted: true, earlyStart: true }));
  };

  const handleStartWithTimer = async () => {
    if (currentDraft?._id && currentDraft.status !== "active") {
      try {
        await api.post(`/drafts/${currentDraft._id}/start?early_start=false`);
        const { data } = await api.get(`/drafts/${currentDraft._id}`);
        setCurrentDraft(data);
        setDraftConfig((prev) => ({ ...prev, draftStarted: true, earlyStart: false, currentPick: data.current_pick }));
        return;
      } catch (e: any) {
        toast.error("Couldn't start draft", { description: e?.response?.data?.detail || e?.message });
      }
    }
    setDraftConfig((prev) => ({ ...prev, draftStarted: true, earlyStart: false }));
  };

  const handleSendChat = () => {
    if (!chatInput.trim()) return;
    setChatMessages((prev) => [
      ...prev,
      { id: `chat-${Date.now()}`, type: "chat", sender: "Team Frostbite", text: chatInput.trim(), timestamp: new Date() },
    ]);
    setChatInput("");
  };

  // Iter 170f — Draft a player. If `chosen` is provided, that player is
  // taken (used when a manager clicks Draft on the SelectedPlayerCard).
  // Otherwise the top-ranked undrafted player is auto-picked (Simulate
  // Pick). In both cases we:
  //   • advance `currentPick` (clock + on-the-clock recompute)
  //   • mark the player as drafted
  //   • push to `picks` array + chat
  //   • set `lastPickedPlayerId` so the Selected Player card defaults
  //     to "live view" of the most-recent pick
  // Iter 170g — When a backend draft exists and is active, POST the
  // pick to `/drafts/{id}/pick` so it persists, broadcasts to other
  // managers, and adds the player to the team's roster. Falls back to
  // pure local state when no backend draft is available (Storybook /
  // pre-draft demo mode).
  const handleDraftPlayer = async (chosen?: DraftEligiblePlayer | null) => {
    const totalPicks = totalTeams * draftConfig.totalRounds;
    if (draftConfig.currentPick > totalPicks) {
      toast.info("Draft is complete.");
      return;
    }
    const teamAbbr = getTeamForPick(draftConfig.currentPick);
    const teamFull = boardTeams.find((t) => t.abbr === teamAbbr);
    const nextPlayer = chosen && !chosen.drafted
      ? chosen
      : players.find((p) => !p.drafted);
    if (!nextPlayer) {
      toast.warning("No eligible players left to draft.");
      return;
    }
    const round = Math.ceil(draftConfig.currentPick / totalTeams);
    const pickInRound = ((draftConfig.currentPick - 1) % totalTeams) + 1;

    // Iter 170g — Backend round-trip when a real draft is active.
    if (currentDraft?._id && isDraftActive && /^[0-9a-fA-F]{24}$/.test(String(nextPlayer.id))) {
      try {
        // Stamp the self-action so our own Socket.IO echo doesn't
        // double-toast (Iter 170i).
        lastSelfPickRef.current = `${draftConfig.currentPick}-${nextPlayer.id}`;
        await api.post(`/drafts/${currentDraft._id}/pick`, { player_id: nextPlayer.id });
        // Refetch the canonical state so picks + on-clock stay in sync.
        const { data } = await api.get(`/drafts/${currentDraft._id}`);
        setCurrentDraft(data);
        setPicks((data.picks || []).map((p: any) => ({
          round: p.round, pickInRound: p.pick_in_round, overall: p.overall,
          team: p.team, player: p.player,
        })));
        setDraftConfig((prev) => ({ ...prev, currentPick: data.current_pick }));
        setPlayers((prev) =>
          prev.map((p) => p.id === nextPlayer.id ? { ...p, drafted: true } : p),
        );
        setLastPickedPlayerId(String(nextPlayer.id));
        setSelectedPlayerId(null);
        setRosterReloadTick((t) => t + 1);
        toast.success(`${teamFull?.name || teamAbbr} drafted ${nextPlayer.name}`);
        return;
      } catch (e: any) {
        toast.error("Pick failed", { description: e?.response?.data?.detail || e?.message });
        return;
      }
    }

    // Fallback: local-only mock progression (used when no backend draft
    // exists yet, e.g. before commissioner starts the draft).
    setPlayers((prev) =>
      prev.map((p) =>
        p.id === nextPlayer.id
          ? { ...p, drafted: true, draftedBy: teamAbbr, draftedRound: round, draftedPick: pickInRound }
          : p,
      ),
    );
    setPicks((prev) => [
      ...prev,
      {
        round,
        pickInRound,
        overall: draftConfig.currentPick,
        team: teamAbbr,
        player: { ...nextPlayer, drafted: true, draftedBy: teamAbbr, draftedRound: round, draftedPick: pickInRound },
      } as DraftPick,
    ]);
    setChatMessages((prev) => [
      ...prev,
      {
        id: `pick-${Date.now()}`,
        type: "pick",
        sender: "System",
        text: `${teamFull?.name || teamAbbr} selects ${nextPlayer.name} (${nextPlayer.position}) at #${draftConfig.currentPick}`,
        timestamp: new Date(),
      },
    ]);
    setLastPickedPlayerId(String(nextPlayer.id));
    setSelectedPlayerId(null);
    setDraftConfig((prev) => ({ ...prev, currentPick: prev.currentPick + 1 }));
  };

  // Kept the old name for the Simulate Pick button binding.
  const handleSimulatePick = () => handleDraftPlayer();

  // ─── Derived values ────────────────────────────────────────────────────────

  const onTheClockTeam = getTeamForPick(draftConfig.currentPick);
  const onTheClockTeamFull = boardTeams.find((t) => t.abbr === onTheClockTeam);
  // (Iter 170h — canPickForCurrentTurn declared below `myTeam` to
  // avoid TDZ.)

  // Iter 147 — Propose-trade mode (mirrors Draft Board)
  const [tradeMode, setTradeMode] = useState(false);
  // Iter 149 — Trading Block overlay mode
  const [tradeBlockMode, setTradeBlockMode] = useState(false);
  const [tradeBlockItems, setTradeBlockItems] = useState<any[]>([]);
  // Iter 152 — Selected player for the inline card above the Draft Board
  const [selectedPlayerId, setSelectedPlayerId] = useState<string | null>(null);
  // Iter 153 — Window-within-window expanded player card (PlayerCardModal)
  const [expandedPlayer, setExpandedPlayer] = useState<any>(null);
  // Iter 164 — Draft Board team-ownership filter chips. When ≥1 team is
  // selected, tiles owned by un-selected teams dim out so commissioners
  // can quickly see which picks each team controls. Multi-select via
  // toggle. Empty set = "show all" (default).
  const [selectedOwnerAbbrs, setSelectedOwnerAbbrs] = useState<Set<string>>(new Set());
  // Iter 165 — Live draft picks (with trade_history) for provenance overlays.
  // Keyed by `${round}|${original_team_id}` so the Draft Board's column-by-
  // original-slot rendering can look up provenance per tile.
  const [livePicksByOrigKey, setLivePicksByOrigKey] = useState<Record<string, any>>({});
  // Iter 161 — pull the league context BEFORE any effect that references
  // it. The expanded-player fetch hook below uses activeLeagueCtx in its
  // dep array, so it MUST be declared first (TDZ error otherwise).
  // (Iter 170b — hooks moved to component top; see header.)
  // Iter 165 — Fetch real draft picks (with trade_history) for the active
  // league + current draft year so provenance tooltips can populate.
  useEffect(() => {
    if (!activeLeagueCtx?.id) { setLivePicksByOrigKey({}); return; }
    const year = new Date().getFullYear();
    api.get(`/drafts/${activeLeagueCtx.id}/picks?year=${year}`)
      .then((res) => {
        const picks = (res.data?.picks || []) as any[];
        const map: Record<string, any> = {};
        // Compute all the abbr fallbacks the Draft Board's column header
        // matcher uses, so picks resolve even when `ownerTeam` doesn't.
        // Iter 170e — also include backend-derived `logo_abbr` from
        // liveTeams (which honours `logo_abbr_override` + hyphen-splits)
        // so chips like BAD (Ice Breakers) or FHF (Five-Hole Fighters)
        // light up the right picks under the filter.
        const computeAbbrs = (name: string, teamId?: string): string[] => {
          if (!name && !teamId) return [];
          const out: string[] = [];
          if (teamId && Array.isArray(liveTeams)) {
            const lt = liveTeams.find((t: any) => (t.id || t._id) === teamId);
            if (lt?.logo_abbr) out.push(String(lt.logo_abbr).toUpperCase());
          }
          if (name) {
            out.push(name.replace(/\s/g, "").slice(0, 3).toUpperCase());
            out.push(name.split(" ").map((w) => w[0] || "").join("").toUpperCase());
            out.push(name.replace(/-/g, " ").split(" ").map((w) => w[0] || "").join("").toUpperCase().slice(0, 4));
          }
          return Array.from(new Set(out.filter(Boolean)));
        };
        for (const p of picks) {
          // Iter 166 — annotate each pick with its CURRENT owner's
          // abbr list so the filter can highlight traded picks under
          // the new owner.
          const currentAbbrs = computeAbbrs(p.current_team_name || p.original_team_name || "", p.current_team_id || p.original_team_id);
          const entry = { ...p, _currentOwnerAbbrs: currentAbbrs };
          // Primary key — original_team_id
          map[`${p.round}|${p.original_team_id}`] = entry;
          // Secondary keys — every column-abbr derivation we might see
          for (const ab of computeAbbrs(p.original_team_name || "", p.original_team_id)) {
            map[`${p.round}|abbr:${ab}`] = entry;
          }
        }
        setLivePicksByOrigKey(map);
      })
      .catch(() => setLivePicksByOrigKey({}));
  }, [activeLeagueCtx?.id, liveTeams]);
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

  // Iter 170h — Whose pick is it? When the on-clock board column maps
  // back to the user's own team, the manual Draft Player button is
  // enabled. Commissioners can pick for anyone.
  const onTheClockBoardEntry = onTheClockTeamFull;
  const canPickForCurrentTurn =
    isLeagueManager ||
    (!!myTeam && !!onTheClockBoardEntry && onTheClockBoardEntry.id === (myTeam as any).id);

  // Iter 170j — Hydrate the persisted queue for the user's team on
  // mount + persist back via PUT whenever the queue changes. Falls
  // back silently when the user has no team (Storybook / demo).
  const hasHydratedQueueRef = useRef(false);
  useEffect(() => {
    if (!(myTeam as any)?.id) return;
    hasHydratedQueueRef.current = false;
    api.get(`/teams/${(myTeam as any).id}/draft-queue`)
      .then(({ data }) => {
        setQueue((data?.draft_queue || []).map(String));
        hasHydratedQueueRef.current = true;
      })
      .catch(() => { hasHydratedQueueRef.current = true; });
  }, [(myTeam as any)?.id]);
  useEffect(() => {
    if (!(myTeam as any)?.id || !hasHydratedQueueRef.current) return;
    const t = setTimeout(() => {
      api.put(`/teams/${(myTeam as any).id}/draft-queue`, { player_ids: queue })
        .catch(() => {/* non-fatal */});
    }, 400); // debounce
    return () => clearTimeout(t);
  }, [queue, (myTeam as any)?.id]);

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
  // Iter 170b — Picks-until-my-turn counter. With real-league wiring
  // (Iter 170b), `boardTeams` carries the real team `id`s when the
  // user is attached to a league, so we can match `myTeam.id` directly
  // against the board team for each pick. The legacy abbr/index
  // fallback only kicks in when the board is running on mock data
  // (no liveTeams) — used by Storybook / standalone demo.
  const picksUntilMyTurn: number | null = useMemo(() => {
    if (!myTeam) return null;
    // Fast path: real-league mode — match by team id.
    const myBoardEntry = boardTeams.find((t) => t.id && t.id === (myTeam as any).id);
    const myAbbrCandidates = new Set<string>();
    if (myBoardEntry) {
      myAbbrCandidates.add(myBoardEntry.abbr);
    } else {
      // Mock-data fallback path
      [
        (myTeam as any).abbr,
        (myTeam as any).logo_abbr,
        myTeam.name?.replace(/\s/g, "").slice(0, 3).toUpperCase(),
        myTeam.name?.split(" ").map((w: string) => w[0] || "").join("").toUpperCase(),
      ]
        .filter(Boolean)
        .forEach((a: string) => {
          if (boardTeamAbbrs.includes(a)) myAbbrCandidates.add(a);
        });
      if (myAbbrCandidates.size === 0) {
        const firstLetter = myTeam.name?.charAt(0).toUpperCase();
        const fallback = boardTeamAbbrs.find((a) => a.startsWith(firstLetter || ""));
        if (fallback) myAbbrCandidates.add(fallback);
        else if (boardTeamAbbrs.length > 0) myAbbrCandidates.add(boardTeamAbbrs[boardTeamAbbrs.length - 1]);
      }
    }
    const totalPicks = totalTeams * draftConfig.totalRounds;
    for (let n = draftConfig.currentPick; n <= totalPicks; n++) {
      if (myAbbrCandidates.has(getTeamForPick(n))) {
        return n - draftConfig.currentPick;
      }
    }
    return null;
  }, [myTeam, boardTeams, boardTeamAbbrs, draftConfig.currentPick, draftConfig.totalRounds, totalTeams, getTeamForPick]);

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
                taller to fill the open space.
                Iter 170f — Default to the LAST DRAFTED player when nothing
                else is being previewed. A small "Live View" pill above
                the card reverts back to that default after a manager
                clicks a player's card to preview them. */}
            {(() => {
              const previewId = selectedPlayerId ?? lastPickedPlayerId;
              const isCustomPreview = !!selectedPlayerId && selectedPlayerId !== lastPickedPlayerId;
              const previewPlayer = previewId
                ? players.find((p) => String(p.id) === String(previewId)) || null
                : null;
              return (
                <>
                  <div className="flex items-center justify-between mb-1 px-1">
                    <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
                      {isCustomPreview
                        ? "Previewing"
                        : lastPickedPlayerId
                        ? "Live View · Last Pick"
                        : "Player Preview"}
                    </span>
                    {isCustomPreview && lastPickedPlayerId && (
                      <Button
                        size="sm"
                        variant="outline"
                        className="h-5 px-2 text-[10px] gap-1"
                        onClick={() => setSelectedPlayerId(null)}
                        data-testid="draft-room-live-view-btn"
                      >
                        <Activity className="h-3 w-3" />
                        Live View
                      </Button>
                    )}
                  </div>
                  <SelectedPlayerCard
                    player={previewPlayer}
                    isOnTheClock={draftConfig.draftStarted}
                    isQueued={!!previewId && queue.includes(String(previewId))}
                    isShortlisted={!!previewId && shortlist.has(String(previewId))}
                    canPick={canPickForCurrentTurn}
                    onDraftPlayer={(p) => {
                      handleDraftPlayer(p as DraftEligiblePlayer);
                    }}
                    onToggleQueue={(id) => toggleQueue(String(id))}
                    onToggleShortlist={(id) => toggleShortlist(String(id))}
                    onClose={() => setSelectedPlayerId(null)}
                    onExpand={(p) => setExpandedPlayer(p)}
                  />
                </>
              );
            })()}
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
                      onClick={handleStartWithTimer}
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
                      <p className="text-lg font-bold text-foreground" data-testid="draft-room-on-the-clock-team">{onTheClockTeamFull?.name}</p>
                      <p className="text-xs text-muted-foreground">
                        Round {currentRound}, Pick {currentPickInRound} (#{draftConfig.currentPick} overall)
                      </p>
                      {/* Iter 170e — Next team up to pick. Helps managers
                          mentally queue while the clock is running on the
                          current team. */}
                      {(() => {
                        const nextOverall = draftConfig.currentPick + 1;
                        const nextAbbr = nextOverall <= totalTeams * draftConfig.totalRounds
                          ? getTeamForPick(nextOverall)
                          : null;
                        const nextTeam = nextAbbr ? boardTeams.find((t) => t.abbr === nextAbbr) : null;
                        if (!nextTeam) return null;
                        return (
                          <p
                            className="text-[11px] text-muted-foreground/90 mt-1 pt-1 border-t border-border/40"
                            data-testid="draft-room-next-on-clock"
                          >
                            <span className="uppercase tracking-wider text-muted-foreground/60 mr-1">Next:</span>
                            <span className="font-medium text-foreground/85">{nextTeam.name}</span>
                            <span className="text-muted-foreground/60"> (#{nextOverall})</span>
                          </p>
                        );
                      })()}
                      {/* Iter 170 — Picks-until-my-turn counter (always visible) */}
                      <p
                        className={cn(
                          "text-[11px] font-medium mt-1.5 pt-1.5 border-t border-border/40",
                          picksUntilMyTurn === 0 ? "text-emerald-400" : "text-primary",
                        )}
                        data-testid="draft-picks-until-my-turn"
                      >
                        {picksUntilMyTurn === null
                          ? "Picks until your turn: —"
                          : picksUntilMyTurn === 0
                          ? "You're on the clock!"
                          : `${picksUntilMyTurn} ${picksUntilMyTurn === 1 ? "pick" : "picks"} until ${myTeam?.name || "your team"}`}
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
                        {isLeagueManager && (
                          <Button
                            variant="secondary"
                            size="sm"
                            className="w-full mt-1"
                            onClick={handleSimulatePick}
                            data-testid="draft-room-simulate-pick"
                          >
                            <Play className="h-3.5 w-3.5 mr-1" />
                            Simulate Pick
                          </Button>
                        )}
                        {/* Iter 170i — Commissioner-only Undo with
                            count picker. Default 1; up to last N picks. */}
                        {isLeagueManager && picks.length > 0 && (
                          <div className="flex items-stretch gap-1 mt-1" data-testid="draft-room-undo-bar">
                            <Input
                              type="number"
                              min={1}
                              max={picks.length}
                              value={undoCount}
                              onChange={(e) => setUndoCount(Math.max(1, Math.min(picks.length, parseInt(e.target.value || "1", 10))))}
                              data-testid="draft-room-undo-count"
                              className="h-9 w-14 text-center text-sm"
                            />
                            <Button
                              variant="outline"
                              size="sm"
                              className="flex-1 gap-1.5 text-amber-400 border-amber-400/30 hover:bg-amber-400/10"
                              onClick={() => handleUndoPicks(undoCount)}
                              data-testid="draft-room-undo-pick"
                            >
                              <RotateCcw className="h-3.5 w-3.5" />
                              {undoCount === 1 ? "Undo Last Pick" : `Undo ${undoCount} Picks`}
                            </Button>
                          </div>
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
            <CardHeader className="pb-2 space-y-2">
              <div className="flex items-center justify-between gap-2 flex-wrap">
                <CardTitle className="text-base">Draft Board</CardTitle>
                <div className="flex items-center gap-1 flex-wrap" data-testid="draft-board-owner-filter">
                  <span className="text-[10px] uppercase text-muted-foreground tracking-wider mr-1">
                    {selectedOwnerAbbrs.size === 0 ? "Filter by owner" : `Showing ${selectedOwnerAbbrs.size} team${selectedOwnerAbbrs.size === 1 ? "" : "s"}`}
                  </span>
                  {boardTeamAbbrs.map((abbr) => {
                    const isOn = selectedOwnerAbbrs.has(abbr);
                    return (
                      <button
                        key={abbr}
                        type="button"
                        onClick={() => {
                          setSelectedOwnerAbbrs((prev) => {
                            const next = new Set(prev);
                            if (next.has(abbr)) next.delete(abbr);
                            else next.add(abbr);
                            return next;
                          });
                        }}
                        className={cn(
                          "px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase border transition-colors",
                          isOn
                            ? "bg-primary/25 border-primary/60 text-primary"
                            : "bg-secondary/30 border-border/40 text-muted-foreground hover:border-primary/40 hover:text-foreground",
                        )}
                        data-testid={`draft-board-owner-chip-${abbr}`}
                        aria-pressed={isOn}
                      >
                        {abbr}
                      </button>
                    );
                  })}
                  {selectedOwnerAbbrs.size > 0 && (
                    <button
                      type="button"
                      onClick={() => setSelectedOwnerAbbrs(new Set())}
                      className="px-1.5 py-0.5 rounded text-[10px] uppercase text-muted-foreground hover:text-foreground border border-transparent"
                      data-testid="draft-board-owner-clear"
                    >
                      Clear
                    </button>
                  )}
                </div>
              </div>
            </CardHeader>
            <CardContent className="p-0">
              <ScrollArea className="w-full">
                <div className="min-w-[700px] p-4 pt-0">
                  <div
                    className="grid gap-1 mb-1 sticky top-0 bg-card z-10 pt-2"
                    style={{ gridTemplateColumns: `48px repeat(${totalTeams}, minmax(72px, 1fr))` }}
                  >
                    <div className="p-1.5 text-[10px] font-semibold text-muted-foreground uppercase">Rd</div>
                    {boardTeamAbbrs.map((abbr) => (
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
                        {boardTeamAbbrs.map((teamAbbr) => {
                          const pick = roundPicks.find((p) => p.team === teamAbbr);
                          const isCurrentPick = pick?.overall === draftConfig.currentPick && draftConfig.draftStarted;
                          // Iter 170b — prefer the exact board-team entry
                          // (carries real id when liveTeams is present).
                          const boardEntry = boardTeams.find((t) => t.abbr === teamAbbr);
                          const ownerTeam = (liveTeams || []).find((t: any) => {
                            if (boardEntry?.id && (t.id || t._id) === boardEntry.id) return true;
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
                          // Iter 164 — owner-filter highlight/dim.
                          // The column abbr is the team that currently
                          // displays in this column header. When the
                          // commissioner toggles 1+ owner chips, tiles
                          // owned by un-selected teams dim out so the
                          // selected teams' picks pop. Empty selection
                          // = "show all" (no dimming).
                          const ownerFilterActive = selectedOwnerAbbrs.size > 0;
                          // Iter 165 — pick provenance lookup. Strict
                          // ID match preferred (avoids the abbr-collision
                          // false positive bug); abbr fallback only when
                          // ownerTeam.id genuinely doesn't resolve.
                          const livePick =
                            (ownerTeam?.id ? livePicksByOrigKey[`${round}|${ownerTeam.id}`] : null)
                            || (!ownerTeam?.id ? livePicksByOrigKey[`${round}|abbr:${teamAbbr}`] : null);
                          const tradeHistory = (livePick?.trade_history || []) as any[];
                          const isTradedPick = tradeHistory.length > 0;
                          // Iter 166 — filter resolves against the CURRENT
                          // owner, not the original column. For traded
                          // picks the live pick payload carries the new
                          // owner's abbr list; for untraded picks the
                          // column header IS the current owner.
                          // Iter 170e — always include the column's own
                          // (deduped) abbr so a chip click on this column
                          // highlights it even when livePick carries a
                          // different abbr derivation.
                          const currentOwnerAbbrs: string[] = Array.from(new Set([
                            ...(livePick?._currentOwnerAbbrs || []),
                            teamAbbr,
                          ]));
                          const isOwnedBySelected = ownerFilterActive && currentOwnerAbbrs.some((a: string) => selectedOwnerAbbrs.has(a));
                          const isDimmedByFilter = ownerFilterActive && !isOwnedBySelected;
                          // Iter 167 — conditional-pick asterisk. Backend
                          // surfaces `pending_protections` per pick (set
                          // when a trade contains an unresolved upgrade
                          // clause). Mark the tile with an `*` and a
                          // tooltip; the original team can't re-trade.
                          const conditionalProtections = (livePick?.pending_protections || []) as any[];
                          const isConditional = conditionalProtections.length > 0;
                          return (
                            <div
                              key={`${round}-${teamAbbr}`}
                              data-testid={`draft-board-tile-${teamAbbr}-${round}`}
                              className={cn(
                                "p-1.5 rounded border text-center min-h-[64px] flex flex-col items-center justify-center gap-0.5 transition-all relative",
                                isCurrentPick
                                  ? "bg-primary/10 border-primary/50 ring-1 ring-primary/30"
                                  : pick?.player
                                  ? (positionTints[pick.player.position] || "bg-secondary/60 border-border")
                                  : "bg-card/50 border-border/50",
                                onBlock && "ring-1 ring-amber-400/60 border-amber-400/40",
                                isOwnedBySelected && "ring-2 ring-primary/70 border-primary/50",
                                isDimmedByFilter && "opacity-30",
                              )}
                              data-testid={onBlock ? `draft-room-block-tile-${teamAbbr}-${pick?.overall ?? "x"}` : undefined}
                            >
                              <span className="text-[9px] text-muted-foreground">
                                #{pick?.overall}
                                {isConditional && (
                                  <Tooltip>
                                    <TooltipTrigger asChild>
                                      <span
                                        className="ml-0.5 text-amber-400 font-bold cursor-help"
                                        data-testid={`draft-board-pick-conditional-${teamAbbr}-${round}`}
                                      >*</span>
                                    </TooltipTrigger>
                                    <TooltipContent className="max-w-sm">
                                      <div className="space-y-1 text-xs">
                                        <p className="font-semibold">Conditional protection — locked from re-trade</p>
                                        {conditionalProtections.map((c: any, idx: number) => (
                                          <p key={idx} className="text-muted-foreground">
                                            {c.description || `${c.subject_type} ${c.metric} ${c.operator} ${c.threshold}`}
                                          </p>
                                        ))}
                                      </div>
                                    </TooltipContent>
                                  </Tooltip>
                                )}
                              </span>
                              {pick?.player ? (
                                <>
                                  {/* Iter 170e — Headshot (or initial circle) +
                                      richer line for league · pts so a tile
                                      reads as a mini player card. */}
                                  {pick.player.photo || pick.player.headshot ? (
                                    <img
                                      src={pick.player.photo || pick.player.headshot}
                                      alt={pick.player.name}
                                      className="h-6 w-6 rounded-full object-cover border border-border/60"
                                      data-testid={`draft-board-tile-photo-${teamAbbr}-${round}`}
                                    />
                                  ) : (
                                    <span
                                      className="h-6 w-6 rounded-full bg-card/70 border border-border/60 flex items-center justify-center text-[10px] font-bold text-foreground/80"
                                      data-testid={`draft-board-tile-initial-${teamAbbr}-${round}`}
                                    >
                                      {pick.player.name.charAt(0)}
                                    </span>
                                  )}
                                  <span className="text-[10px] font-medium text-foreground truncate w-full leading-tight">
                                    {pick.player.name.split(" ").map((n, i) => i === 0 ? n[0] + "." : n).join(" ")}
                                  </span>
                                  <div className="flex items-center gap-1 justify-center">
                                    <Badge className={cn("text-[9px] px-1 py-0 h-3.5 border", positionColors[pick.player.position] || "bg-muted text-muted-foreground")}>
                                      {pick.player.position}
                                    </Badge>
                                    {(pick.player.league || pick.player.nhlTeam) && (
                                      <span className="text-[8px] text-muted-foreground truncate">
                                        {pick.player.league || pick.player.nhlTeam}
                                      </span>
                                    )}
                                  </div>
                                  {typeof pick.player.pts === "number" && (
                                    <span className="text-[8px] text-muted-foreground/80">{pick.player.pts} pts</span>
                                  )}
                                  {/* Iter 170i — Commissioner-only Swap
                                      affordance on every drafted tile.
                                      Opens a popover with a quick search
                                      to replace this pick's player. */}
                                  {isLeagueManager && (
                                    <Popover
                                      open={swapPickOverall === pick.overall}
                                      onOpenChange={(open) => {
                                        setSwapPickOverall(open ? pick.overall : null);
                                        if (!open) setSwapSearch("");
                                      }}
                                    >
                                      <PopoverTrigger asChild>
                                        <button
                                          type="button"
                                          className="absolute bottom-0.5 right-0.5 h-4 w-4 rounded-sm bg-card/70 border border-border/60 flex items-center justify-center text-foreground/70 hover:bg-primary/20 hover:text-primary"
                                          data-testid={`draft-board-swap-btn-${pick.overall}`}
                                          aria-label="Swap player"
                                          onClick={(e) => e.stopPropagation()}
                                        >
                                          <ArrowRightLeft className="h-2.5 w-2.5" />
                                        </button>
                                      </PopoverTrigger>
                                      <PopoverContent
                                        align="end"
                                        className="w-72 p-2 space-y-2"
                                        onClick={(e) => e.stopPropagation()}
                                      >
                                        <div className="text-xs font-semibold text-foreground">
                                          Swap pick #{pick.overall} ({pick.team})
                                        </div>
                                        <div className="text-[10px] text-muted-foreground">
                                          Currently: <span className="text-foreground">{pick.player.name}</span> ({pick.player.position})
                                        </div>
                                        <Input
                                          autoFocus
                                          value={swapSearch}
                                          onChange={(e) => setSwapSearch(e.target.value)}
                                          placeholder="Search for replacement player…"
                                          className="h-8 text-xs"
                                          data-testid="draft-board-swap-search"
                                        />
                                        <div className="max-h-48 overflow-y-auto space-y-0.5">
                                          {players
                                            .filter((p) => !p.drafted && (!swapSearch || p.name.toLowerCase().includes(swapSearch.toLowerCase()) || p.position.toLowerCase().includes(swapSearch.toLowerCase())))
                                            .slice(0, 12)
                                            .map((p) => (
                                              <button
                                                key={p.id}
                                                type="button"
                                                onClick={async () => {
                                                  await handleSwapPickPlayer(pick.overall, String(p.id));
                                                  setSwapPickOverall(null);
                                                  setSwapSearch("");
                                                }}
                                                className="flex items-center justify-between w-full px-2 py-1 rounded hover:bg-secondary/60 text-left"
                                                data-testid={`draft-board-swap-option-${p.id}`}
                                              >
                                                <span className="text-xs text-foreground truncate">{p.name}</span>
                                                <span className="text-[10px] text-muted-foreground ml-2">{p.position}</span>
                                              </button>
                                            ))}
                                          {players.filter((p) => !p.drafted).length === 0 && (
                                            <p className="text-[11px] text-muted-foreground text-center py-2">No eligible players</p>
                                          )}
                                        </div>
                                      </PopoverContent>
                                    </Popover>
                                  )}
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
                              {/* Iter 165 — Traded-pick provenance chip */}
                              {isTradedPick && (
                                <Tooltip>
                                  <TooltipTrigger asChild>
                                    <span
                                      className="absolute top-0.5 right-0.5 inline-flex items-center justify-center h-4 w-4 rounded-sm bg-sky-500/25 text-sky-300 cursor-help"
                                      data-testid={`draft-board-pick-traded-${teamAbbr}-${round}`}
                                    >
                                      <ArrowRightLeft className="h-2.5 w-2.5" />
                                    </span>
                                  </TooltipTrigger>
                                  <TooltipContent className="max-w-sm">
                                    <PickProvenance tradeHistory={tradeHistory} />
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
                reloadTrigger={rosterReloadTick}
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
