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
// Iter 170k — drag-to-reorder queue.
import SortableQueue from "@/lovable/pages/draftroom/SortableQueue";
// Iter 171 — Player Search tabs (Eligible / Queue / Shortlist) extracted.
import PlayerSearchPanel from "@/lovable/pages/draftroom/PlayerSearchPanel";
// Iter 171 — Draft Live tile + Draft Board extracted into their own files.
import DraftLiveTile from "@/lovable/pages/draftroom/DraftLiveTile";
import DraftBoard from "@/lovable/pages/draftroom/DraftBoard";
import {
  positionColors,
  positionTints,
  formatCountdown,
  formatPickTimer,
} from "@/lovable/pages/draftroom/draftConstants";
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

// Iter 171 — formatCountdown / formatPickTimer / positionColors / positionTints
// extracted to /draftroom/draftConstants.ts and re-imported above.

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
  // Iter 170l — Shortlist is now an ordered string[] (was a Set) so
  // we can render it in a SortableQueue + persist the manager's manual
  // ranking. Has-checks become `.includes(...)`.
  const [shortlist, setShortlist] = useState<string[]>([]);
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
            auto_picked: !!p.auto_picked,
            auto_pick_via: p.auto_pick_via,
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
        // Iter 170m — hydrate historic chat (picks + system messages
        // including auto-pick badges) so a reload preserves the
        // narrative arc of the draft.
        if (Array.isArray(d.chat_messages) && d.chat_messages.length > 0) {
          setChatMessages(d.chat_messages.map((m: any) => ({
            ...m,
            timestamp: new Date(m.timestamp || Date.now()),
          })));
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
        auto_picked: !!p.auto_picked, auto_pick_via: p.auto_pick_via,
      })));
      setDraftConfig((prev) => ({ ...prev, currentPick: data.current_pick }));
      setRosterReloadTick((t) => t + 1);
      // Iter 170m — Keep chat in sync with backend on every refresh
      // (undo / swap / remote pick) so the Picks tab always reflects
      // the canonical message log.
      if (Array.isArray(data.chat_messages)) {
        setChatMessages(data.chat_messages.map((m: any) => ({
          ...m,
          timestamp: new Date(m.timestamp || Date.now()),
        })));
      }
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
    setShortlist((prev) =>
      prev.includes(playerId) ? prev.filter((id) => id !== playerId) : [...prev, playerId]
    );
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
    // Iter 170l — preserve the manager's drag-ordered shortlist (was
    // sorted by global ranking before, which made drag-to-reorder
    // visually no-op).
    return shortlist
      .map((id) => players.find((p) => p.id === id))
      .filter((p): p is DraftEligiblePlayer => !!p && !p.drafted);
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
    const text = chatInput.trim();
    setChatInput("");
    // Iter 170n — Persist outbound chat via backend so reload + every
    // other connected manager see the message. Falls back to a local
    // optimistic append when no backend draft exists (demo / pre-init).
    if (currentDraft?._id) {
      api.post(`/drafts/${currentDraft._id}/chat`, { text })
        .catch(() => {
          setChatMessages((prev) => [
            ...prev,
            { id: `chat-${Date.now()}`, type: "chat", sender: (myTeam as any)?.name || "You", text, timestamp: new Date() },
          ]);
        });
      return;
    }
    setChatMessages((prev) => [
      ...prev,
      { id: `chat-${Date.now()}`, type: "chat", sender: (myTeam as any)?.name || "You", text, timestamp: new Date() },
    ]);
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
          auto_picked: !!p.auto_picked, auto_pick_via: p.auto_pick_via,
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
  const hasHydratedShortlistRef = useRef(false);
  useEffect(() => {
    if (!(myTeam as any)?.id) return;
    hasHydratedQueueRef.current = false;
    hasHydratedShortlistRef.current = false;
    api.get(`/teams/${(myTeam as any).id}/draft-queue`)
      .then(({ data }) => {
        setQueue((data?.draft_queue || []).map(String));
        hasHydratedQueueRef.current = true;
      })
      .catch(() => { hasHydratedQueueRef.current = true; });
    // Iter 170m — hydrate persisted shortlist too.
    api.get(`/teams/${(myTeam as any).id}/shortlist`)
      .then(({ data }) => {
        setShortlist((data?.shortlist || []).map(String));
        hasHydratedShortlistRef.current = true;
      })
      .catch(() => { hasHydratedShortlistRef.current = true; });
  }, [(myTeam as any)?.id]);
  useEffect(() => {
    if (!(myTeam as any)?.id || !hasHydratedQueueRef.current) return;
    const t = setTimeout(() => {
      api.put(`/teams/${(myTeam as any).id}/draft-queue`, { player_ids: queue })
        .catch(() => {/* non-fatal */});
    }, 400); // debounce
    return () => clearTimeout(t);
  }, [queue, (myTeam as any)?.id]);
  // Iter 170m — debounced shortlist persist (same pattern).
  useEffect(() => {
    if (!(myTeam as any)?.id || !hasHydratedShortlistRef.current) return;
    const t = setTimeout(() => {
      api.put(`/teams/${(myTeam as any).id}/shortlist`, { player_ids: shortlist })
        .catch(() => {/* non-fatal */});
    }, 400);
    return () => clearTimeout(t);
  }, [shortlist, (myTeam as any)?.id]);

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

  // Iter 170o — Prefer the BACKEND draft criteria when a real draft
  // exists so the page badge tracks the actual format (Open / Entry /
  // …) instead of the stale local default.
  const effectiveCriteria = currentDraft?.player_criteria || selectedCriteria;
  const currentCriteria = draftCriteria.find((c) => c.value === effectiveCriteria)
    || { value: effectiveCriteria, label: effectiveCriteria === "open" ? "Open · NHL Players" : effectiveCriteria, description: "" };

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
                <p className="text-sm text-muted-foreground" data-testid="draft-room-subheader">
                  {currentDraft?.player_criteria === "entry"
                    ? "2026 NHL Entry Draft — League Rookie Draft"
                    : "League Draft — Open · all eligible NHL players"}
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
                    isShortlisted={!!previewId && shortlist.includes(String(previewId))}
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

            {/* Draft Live tile (Iter 171 extracted) */}
            <DraftLiveTile
              draftConfig={draftConfig}
              countdown={countdown}
              onEarlyStart={handleEarlyStart}
              onStartWithTimer={handleStartWithTimer}
              onTheClockTeamFull={onTheClockTeamFull}
              currentRound={currentRound}
              currentPickInRound={currentPickInRound}
              currentDraft={currentDraft}
              totalTeams={totalTeams}
              getTeamForPick={getTeamForPick}
              boardTeams={boardTeams}
              picksUntilMyTurn={picksUntilMyTurn}
              myTeam={myTeam}
              isClockActive={isClockActive}
              timerPaused={timerPaused}
              setTimerPaused={setTimerPaused}
              pickTimeLeft={pickTimeLeft}
              isLeagueManager={isLeagueManager}
              handleSimulatePick={handleSimulatePick}
              picks={picks}
              undoCount={undoCount}
              setUndoCount={setUndoCount}
              handleUndoPicks={handleUndoPicks}
            />
          </div>

          {/* ── Draft Board (Iter 171 extracted) ────────────────────────── */}
          <DraftBoard
            boardTeams={boardTeams}
            boardTeamAbbrs={boardTeamAbbrs}
            totalTeams={totalTeams}
            allPicks={allPicks}
            selectedOwnerAbbrs={selectedOwnerAbbrs}
            setSelectedOwnerAbbrs={setSelectedOwnerAbbrs}
            draftConfig={draftConfig}
            onTheClockTeam={onTheClockTeam}
            myTeam={myTeam}
            liveTeams={liveTeams}
            livePicksByOrigKey={livePicksByOrigKey}
            tradeBlockPlayerIds={tradeBlockPlayerIds}
            tradeBlockOverallKeys={tradeBlockOverallKeys}
            tradeBlockMode={tradeBlockMode}
            tradeMode={tradeMode}
            markAvailableForDraft={markAvailableForDraft}
            handleAddDraftPickToTrade={handleAddDraftPickToTrade}
            isLeagueManager={isLeagueManager}
            swapPickOverall={swapPickOverall}
            setSwapPickOverall={setSwapPickOverall}
            swapSearch={swapSearch}
            setSwapSearch={setSwapSearch}
            handleSwapPickPlayer={handleSwapPickPlayer}
            players={players}
          />

          {/* ── Bottom section: (LEFT) Player Search tabs · (CENTER) Truncated Roster · (RIGHT) Draft Chat ── */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
            {/* LEFT: Player Search (Iter 150 — Eligible | My Queue | Shortlist)
                Iter 171 — extracted into PlayerSearchPanel. */}
            <div className="lg:col-span-4">
              <PlayerSearchPanel
                filteredPlayers={filteredPlayers}
                searchQuery={searchQuery}
                setSearchQuery={setSearchQuery}
                positionFilter={positionFilter}
                setPositionFilter={setPositionFilter}
                positions={positions}
                positionColors={positionColors}
                selectedPlayerId={selectedPlayerId}
                setSelectedPlayerId={setSelectedPlayerId}
                tradeBlockPlayerIds={tradeBlockPlayerIds}
                queue={queue}
                shortlist={shortlist}
                queuedPlayers={queuedPlayers}
                shortlistedPlayers={shortlistedPlayers}
                setQueue={setQueue}
                setShortlist={setShortlist}
                toggleQueue={toggleQueue}
                toggleShortlist={toggleShortlist}
                removeFromQueue={removeFromQueue}
              />
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
