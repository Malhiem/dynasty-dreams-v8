// @ts-nocheck
import { useState, useMemo, useRef } from "react";
// Iter 170h — Socket.IO subscription for live draft updates.
// Iter 203 — extracted into a dedicated hook.
import useDraftRoomSocket from "@/hooks/use-draft-room-socket";
// Iter 204 — pick timer extracted into a dedicated hook.
import usePickTimer from "@/hooks/use-pick-timer";
// Iter 205 — localStorage persistence + chat composer extracted.
import useDraftRoomPersistence from "@/hooks/use-draft-room-persistence";
import useDraftChat from "@/hooks/use-draft-chat";
// Iter 228f — Defer-to-User missed-pick dialog
import DeferPickDialog from "@/lovable/components/DeferPickDialog";
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
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useTradeBuilder } from "@/lovable/state/TradeBuilderContext";
import { useAuth } from "@/contexts/AuthContext";
import { useActiveLeague } from "@/hooks/use-active-league";
import { toast } from "sonner";
// Iter 170k — drag-to-reorder queue.
import SortableQueue from "@/lovable/pages/draftroom/SortableQueue";
// Iter 171 — Draft Live tile + Draft Board extracted into their own files.
import DraftLiveTile from "@/lovable/pages/draftroom/DraftLiveTile";
import DraftBoard from "@/lovable/pages/draftroom/DraftBoard";
import {
  positionColors,
  positionTints,
  formatCountdown,
  formatPickTimer,
} from "@/lovable/pages/draftroom/draftConstants";
// Iter 174 — Header strip (title + criteria popover + Trade Mode +
// Trading Block toggles) extracted into its own component.
import DraftHeaderActions from "@/lovable/pages/draftroom/DraftHeaderActions";
// Iter 174 — trade-block state-blob + polling extracted into a hook.
import useDraftLiveState from "@/hooks/use-draft-live-state";
// Iter 229d — three small effect-hooks extracted from DraftRoom to
// keep this component focused on rendering + commissioner actions.
import useUpcomingDrafts from "@/hooks/use-upcoming-drafts";
import useDraftEligiblePlayers from "@/hooks/use-draft-eligible-players";
import usePendingPickTrade from "@/hooks/use-pending-pick-trade";
import useDraftCommissionerActions from "@/hooks/use-draft-commissioner-actions";
import useDraftPickHandler from "@/hooks/use-draft-pick-handler";
// Iter 229L — Additional extractions further trimming DraftRoom.tsx
import useLivePicksByOrigKey from "@/hooks/use-live-picks-by-orig-key";
import useExpandedPlayerFetch from "@/hooks/use-expanded-player-fetch";
import useDraftQueueShortlistPersistence from "@/hooks/use-draft-queue-shortlist-persistence";
import useDraftAudioAlerts from "@/hooks/use-draft-audio-alerts";
// Iter 230i — Auto-init + state-refresh hook + picks-until-my-turn memo.
import useDraftAutoInit from "@/hooks/use-draft-auto-init";
import useDraftPicksUntilMyTurn from "@/hooks/use-draft-picks-until-my-turn";
// Iter 230j — Trade-pick handler hook + expanded-player modal wrapper.
import useAddDraftPickToTrade from "@/hooks/use-add-draft-pick-to-trade";
import ExpandedPlayerModal from "@/lovable/pages/draftroom/ExpandedPlayerModal";
// Iter 230v — Countdown ticker + pick-grid + player-filter derivation hooks.
import useDraftCountdown from "@/hooks/use-draft-countdown";
import useDraftPickGrid from "@/hooks/use-draft-pick-grid";
import useDraftPlayerFilters from "@/hooks/use-draft-player-filters";
// Iter 229j — Two more JSX bodies extracted from DraftRoom.tsx.
import UpcomingDraftsPicker from "@/lovable/pages/draftroom/UpcomingDraftsPicker";
import DraftRoomBottomGrid from "@/lovable/pages/draftroom/DraftRoomBottomGrid";
// Iter 230c — Player preview panel extracted.
import DraftPreviewPanel from "@/lovable/pages/draftroom/DraftPreviewPanel";
// Iter 230j — PlayerCardModal now consumed via ExpandedPlayerModal wrapper.
import PickProvenance from "@/lovable/pages/draftroom/PickProvenance";
// Iter 194c — floating "Pick Trade Pending" review pill.
import PickTradeReviewPill from "@/lovable/pages/draftroom/PickTradeReviewPill";
import api from "@/lib/api";

// ─── Types ───────────────────────────────────────────────────────────────────
// Iter 229 — extracted to draftroom/types.ts for reuse + import discipline.

import type {
  DraftEligiblePlayer,
  DraftPick,
  DraftConfig,
  ChatMessage,
} from "@/lovable/pages/draftroom/types";

// ─── Mocks ───────────────────────────────────────────────────────────────────
// Iter 229 — extracted to draftroom/mocks.ts. Used only as a fallback
// when no live league context is available.

import {
  mockLeagueTeams,
  draftCriteria,
  mockEligiblePlayers,
  myRoster,
} from "@/lovable/pages/draftroom/mocks";

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
  const boardTeams = useMemo<Array<{ id?: string; name: string; abbr: string; theme_color?: string | null }>>(() => {
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
        return { id: t.id || t._id, name: t.name, abbr, theme_color: t.theme_color || null };
      });
    }
    return mockLeagueTeams as Array<{ id?: string; name: string; abbr: string; theme_color?: string | null }>;
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
  // Iter 230v — Countdown ticker extracted into `useDraftCountdown`.
  // Iter 204 — `pickTimeLeft`/`timerPaused` moved into `usePickTimer`
  // hook (declared further down after currentDraft is available).
  const [selectedCriteria, setSelectedCriteria] = useState("entry");
  // Chat state
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([
    { id: "sys1", type: "pick", sender: "System", text: "Draft room is open. Good luck!", timestamp: new Date(Date.now() - 120000) },
    { id: "c1", type: "chat", sender: "Arctic Wolves", text: "Let's get this draft going 🏒", timestamp: new Date(Date.now() - 90000) },
    { id: "c2", type: "chat", sender: "Blizzard Kings", text: "Who's everyone eyeing at #1?", timestamp: new Date(Date.now() - 60000) },
  ]);
  // Iter 205 — `chatInput` + `handleSendChat` extracted to useDraftChat
  // hook (declared further down once currentDraft + myTeam are resolved).
  // (Iter 170h — isLeagueManager moved down to derive from the active
  // league context; see below.)

  // Iter 170f — localStorage persistence (extracted to hook in iter 205).
  useDraftRoomPersistence({
    leagueId: activeLeagueCtx?.id,
    picks,
    currentPick: draftConfig.currentPick,
    draftStarted: draftConfig.draftStarted,
    lastPickedPlayerId,
    setPicks,
    setPlayers,
    setDraftConfig,
    setLastPickedPlayerId,
  });

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

  // Iter 228f — Defer-to-User missed-pick dialog state. Iter 230i —
  // hoisted above useDraftAutoInit so the auto-init hook can read the
  // setters without a TDZ.
  const [missedPickAction, setMissedPickAction] = useState<string>("auto-select");
  const [deferDialogOpen, setDeferDialogOpen] = useState(false);
  const [deferAvailable, setDeferAvailable] = useState<string[]>([
    "auto-best", "auto-queue", "pick-anytime",
  ]);

  // Iter 228n — Upcoming-drafts dropdown: list the next 30 days of
  // scheduled drafts for this league so commissioners + league
  // managers can switch (e.g. mid-season trade deadline draft vs.
  // off-season rookie draft). Defaults to the soonest.
  // Iter 229d — extracted into a dedicated hook.
  const { upcomingDrafts, selectedDraftId, setSelectedDraftId } =
    useUpcomingDrafts(activeLeagueCtx?.id);

  // Iter 230i — Auto-init + state refresh extracted. The 79-line
  // hydration useEffect + 23-line refreshDraftState callback now live
  // in `use-draft-auto-init.ts`.
  const { refreshDraftState } = useDraftAutoInit({
    leagueId: activeLeagueCtx?.id,
    selectedDraftId,
    currentDraftId: currentDraft?._id,
    setCurrentDraft,
    setPicks,
    setDraftConfig,
    setLastPickedPlayerId,
    setMissedPickAction: (s) => setMissedPickAction(s),
    setDeferAvailable: (a) => setDeferAvailable(a),
    setChatMessages,
    setRosterReloadTick,
  });

  // Iter 194c — On mount / league change, hydrate any pick trade
  // already in `pending_draft_review` so a refreshed Draft Room still
  // shows the floating review pill. Simulates a freshly-received
  // `pick_trade_proposed` WS event for the pill.
  // Iter 229d — extracted into a dedicated hook (moved BELOW
  // `useDraftRoomSocket` so the destructured `setLastChatEvent` is
  // initialized before this hook reads it).
  // Iter 170g — Fetch real eligible players for the active draft.
  // Replaces the mock list when a draft exists; the SelectedPlayerCard
  // will then render real NHL stats + headshot.
  // Iter 229d — extracted into a dedicated hook.
  useDraftEligiblePlayers(currentDraft, setPlayers);

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

  // Iter 230i — refreshDraftState extracted into useDraftAutoInit; the
  // hook returns the canonical refetcher consumed by Socket.IO events
  // below.

  // Iter 170h — Subscribe to the draft's Socket.IO room. Listeners fire
  // for every pick / undo / swap broadcast by the backend.
  // Iter 170i — Surface a toast to other managers when a remote event
  // lands. We dedupe self-originated events by stamping a
  // `_selfActionId` ref on local actions and skipping the toast for
  // the matching incoming event.
  // Iter 203 — moved into `useDraftRoomSocket` hook (-45 lines).
  const lastSelfPickRef = useRef<string | null>(null);
  const draftRoomId = currentDraft?._id ? `draft_${currentDraft._id}` : null;
  const { lastChatEvent, setLastChatEvent } = useDraftRoomSocket({
    roomId: draftRoomId,
    userId,
    refreshDraftState,
    setChatMessages,
    boardTeams,
    lastSelfPickRef,
  });

  // Iter 229d — Pending pick-trade hydration must run AFTER
  // `useDraftRoomSocket` initializes `setLastChatEvent`.
  usePendingPickTrade(activeLeagueCtx?.id, setLastChatEvent);

  // Iter 229g — Four backend-touching commissioner actions extracted
  // into a dedicated hook: undo, swap, start-early, start-with-timer.
  const {
    handleUndoPicks,
    handleSwapPickPlayer,
    handleEarlyStart,
    handleStartWithTimer,
  } = useDraftCommissionerActions({
    currentDraft,
    setCurrentDraft,
    refreshDraftState,
    setPicks,
    setDraftConfig,
  });

  // ─── Countdown ──────────────────────────────────────────────────────────────
  // Iter 230v — Extracted to `useDraftCountdown` hook.
  const countdown = useDraftCountdown({
    scheduledTime: draftConfig.scheduledTime,
    draftStarted: draftConfig.draftStarted,
    setDraftConfig,
  });

  // ─── Pick timer ─────────────────────────────────────────────────────────────

  const isClockActive = draftConfig.draftStarted && !draftConfig.earlyStart;

  // Iter 228f — missedPickAction / deferDialogOpen / deferAvailable
  // state hoisted above useDraftAutoInit; see top of component.

  // ─── Draft order + pick grid ───────────────────────────────────────────────
  // Iter 230v — `getDraftOrder` / `getTeamForPick` / `allPicks` /
  // `currentRound` / `currentPickInRound` extracted to
  // `useDraftPickGrid`. Hoisted above the `isMyPickActive` IIFE below
  // so the hook's `getTeamForPick` is initialised before the IIFE
  // reads it (avoids a TDZ "can't access lexical declaration
  // 'getTeamForPick' before initialization" runtime error).
  const {
    getDraftOrder: _getDraftOrder,
    getTeamForPick,
    allPicks,
    currentRound,
    currentPickInRound,
  } = useDraftPickGrid({
    boardTeamAbbrs,
    totalTeams,
    snakeDraft: draftConfig.snakeDraft,
    totalRounds: draftConfig.totalRounds,
    currentPick: draftConfig.currentPick,
    picks,
  });
  void _getDraftOrder; // exported only for future use; not consumed here.

  // Iter 228i — Determine whether the active pick belongs to the local
  // user's team WITHOUT referencing the `myTeam` useMemo (which is
  // declared further down the file → would trigger a Temporal Dead
  // Zone "can't access lexical declaration 'myTeam' before
  // initialization" error in production builds).
  const isMyPickActive = (() => {
    if (!user || !liveTeams?.length || !draftConfig.draftStarted) return false;
    const teamAbbr = getTeamForPick(draftConfig.currentPick);
    if (!teamAbbr) return false;
    const mine: any = liveTeams.find((t: any) => t.owner_id === user.id);
    const myAbbr = mine?.logo_abbr || (mine?.name || "").slice(0, 3).toUpperCase();
    return myAbbr === teamAbbr;
  })();
  const shouldDefer = missedPickAction === "defer-to-user" && isMyPickActive;

  // Iter 204 — pick timer extracted to `usePickTimer` hook (-30 lines).
  const { pickTimeLeft, setPickTimeLeft, timerPaused, setTimerPaused } = usePickTimer({
    isClockActive,
    pickTimerSeconds: draftConfig.pickTimerSeconds,
    currentPick: draftConfig.currentPick,
    currentDraftId: currentDraft?._id,
    isDraftActive,
    refreshDraftState,
    // Iter 228f — Only defer when the current pick is owned by the
    // local user AND the draft uses defer-to-user mode.
    deferOnExpiry: shouldDefer,
    onTimerExpired: (_pickNo: number) => setDeferDialogOpen(true),
  });

  // ─── Shortlist & Queue ─────────────────────────────────────────────────────
  // Iter 230v — toggle handlers + memoised collections extracted to
  // `useDraftPlayerFilters`.
  const {
    filteredPlayers,
    shortlistedPlayers,
    queuedPlayers,
    toggleShortlist,
    toggleQueue,
    removeFromQueue,
  } = useDraftPlayerFilters({
    players,
    searchQuery,
    positionFilter,
    shortlist,
    setShortlist,
    queue,
    setQueue,
  });

  // ─── Draft actions ─────────────────────────────────────────────────────────
  // Iter 229g — handleEarlyStart + handleStartWithTimer were extracted
  // into `useDraftCommissionerActions` (above) alongside undo/swap.

  // Iter 170f — Draft a player. (See useDraftPickHandler call below
  // — moved AFTER the `selectedPlayerId` + roster-reload-tick state
  // are initialized so the hook's deps don't hit a TDZ.)

  // ─── Derived values ────────────────────────────────────────────────────────

  const onTheClockTeam = getTeamForPick(draftConfig.currentPick);
  const onTheClockTeamFull = boardTeams.find((t) => t.abbr === onTheClockTeam);
  // (Iter 170h — canPickForCurrentTurn declared below `myTeam` to
  // avoid TDZ.)

  // Iter 147 — Propose-trade mode (mirrors Draft Board)
  const [tradeMode, setTradeMode] = useState(false);
  // Iter 149 — Trading Block overlay mode
  const [tradeBlockMode, setTradeBlockMode] = useState(false);
  // Iter 152 — Selected player for the inline card above the Draft Board
  const [selectedPlayerId, setSelectedPlayerId] = useState<string | null>(null);

  // Iter 229h — `handleDraftPlayer` extracted into `useDraftPickHandler`.
  // Located here (post-state-init) so all setters are defined.
  const { handleDraftPlayer, handleSimulatePick } = useDraftPickHandler({
    currentDraft,
    isDraftActive,
    draftConfig,
    totalTeams,
    players,
    boardTeams,
    getTeamForPick,
    lastSelfPickRef,
    setCurrentDraft,
    setPicks,
    setDraftConfig,
    setPlayers,
    setChatMessages,
    setLastPickedPlayerId,
    setSelectedPlayerId,
    setRosterReloadTick,
  });
  // Iter 153 — Window-within-window expanded player card (PlayerCardModal)
  const [expandedPlayer, setExpandedPlayer] = useState<any>(null);
  // Iter 164 — Draft Board team-ownership filter chips. When ≥1 team is
  // selected, tiles owned by un-selected teams dim out so commissioners
  // can quickly see which picks each team controls. Multi-select via
  // toggle. Empty set = "show all" (default).
  const [selectedOwnerAbbrs, setSelectedOwnerAbbrs] = useState<Set<string>>(new Set());
  // Iter 165 — Live draft picks (with trade_history) for provenance overlays.
  // Iter 229L — Extracted to `useLivePicksByOrigKey` hook.
  const livePicksByOrigKey = useLivePicksByOrigKey(activeLeagueCtx?.id, liveTeams);
  // Iter 161 — pull the league context BEFORE any effect that references
  // it. The expanded-player fetch hook below uses activeLeagueCtx in its
  // dep array, so it MUST be declared first (TDZ error otherwise).
  // (Iter 170b — hooks moved to component top; see header.)
  // Iter 154 — When the expanded player has a Mongo ObjectId, fetch the real
  // record (NHL stats, contract, schedule) and merge over the lean fallback.
  // Iter 229L — Extracted to `useExpandedPlayerFetch` hook.
  useExpandedPlayerFetch(expandedPlayer, setExpandedPlayer, activeLeagueCtx?.id);
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

  // Iter 205 — chat composer extracted to `useDraftChat` hook.
  // Must be called AFTER `myTeam` since it reads `myTeam.name`.
  const { chatInput, setChatInput, handleSendChat } = useDraftChat({
    currentDraftId: currentDraft?._id,
    myTeamName: (myTeam as any)?.name,
    appendLocalMessage: (msg: any) =>
      setChatMessages((prev) => [...prev, msg]),
  });

  // Iter 174 — Trade-block state-blob + polling lifted into a hook.
  // Must be called AFTER myTeam is computed since the hook depends on
  // (myTeam as any)?.id for ownership-scoped mutations.
  const {
    tradeBlockItems,
    tradeBlockPlayerIds,
    tradeBlockOverallKeys,
    markAvailableForDraft,
    toggleMyTeamTradeBlock,
  } = useDraftLiveState({
    leagueId: (activeLeagueCtx as any)?.id,
    myTeamId: (myTeam as any)?.id,
    overlayActive: tradeBlockMode,
  });

  // Iter 170h — Whose pick is it? When the on-clock board column maps
  // back to the user's own team, the manual Draft Player button is
  // enabled. Commissioners can pick for anyone.
  const onTheClockBoardEntry = onTheClockTeamFull;
  const canPickForCurrentTurn =
    isLeagueManager ||
    (!!myTeam && !!onTheClockBoardEntry && onTheClockBoardEntry.id === (myTeam as any).id);

  // Iter 170j — Hydrate the persisted queue + shortlist for the user's
  // team on mount + debounce-persist on changes.
  // Iter 229L — Extracted to `useDraftQueueShortlistPersistence` hook.
  useDraftQueueShortlistPersistence({
    myTeamId: (myTeam as any)?.id,
    queue,
    setQueue,
    shortlist,
    setShortlist,
  });

  // Iter 230j — `handleAddDraftPickToTrade` extracted to
  // `useAddDraftPickToTrade` hook.
  const handleAddDraftPickToTrade = useAddDraftPickToTrade({
    myTeam,
    leagueId: activeLeagueCtx?.id,
    liveTeams,
    tradeBuilder,
  });
  // Iter 170b — Picks-until-my-turn counter. Iter 230i — extracted to
  // `useDraftPicksUntilMyTurn` hook (34-line memo + mock fallback).
  // `currentRound` / `currentPickInRound` are now provided by
  // `useDraftPickGrid` (iter 230v).
  const picksUntilMyTurn: number | null = useDraftPicksUntilMyTurn({
    myTeam,
    boardTeams,
    boardTeamAbbrs,
    currentPick: draftConfig.currentPick,
    totalRounds: draftConfig.totalRounds,
    totalTeams,
    getTeamForPick,
  });

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

  // ── Iter 172 — Draft Room audio alerts ───────────────────────────────────
  // Iter 229L — Extracted to `useDraftAudioAlerts` hook.
  const draftSounds = useDraftAudioAlerts(draftConfig.draftStarted, picksUntilMyTurn);

  return (
    <AppLayout>
      <TooltipProvider>
        {/* Iter 228f — Defer-to-User missed-pick dialog */}
        <DeferPickDialog
          open={deferDialogOpen}
          onClose={() => setDeferDialogOpen(false)}
          draftId={currentDraft?._id || ""}
          pickNo={draftConfig.currentPick}
          availableOptions={deferAvailable}
          onResolved={() => {
            // After resolving, refresh draft state to pick up the engine's
            // auto-pick (auto-best/auto-queue) or skip-anytime advancement.
            refreshDraftState();
          }}
        />
        <div className="space-y-4">
          {/* Iter 228n — Upcoming-drafts dropdown. Iter 229j — extracted. */}
          <UpcomingDraftsPicker
            upcomingDrafts={upcomingDrafts}
            selectedDraftId={selectedDraftId}
            setSelectedDraftId={setSelectedDraftId}
          />

          {/* ── Header row ─────────────────────────────────────────────── */}
          <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-4">
            <div className="flex-1 min-w-0 flex flex-col gap-3">
              <DraftHeaderActions
                currentDraft={currentDraft}
                currentCriteria={currentCriteria}
                tradeMode={tradeMode}
                setTradeMode={setTradeMode}
                tradeBlockMode={tradeBlockMode}
                setTradeBlockMode={setTradeBlockMode}
                tradeBlockItems={tradeBlockItems}
              />

            {/* Iter 153 / 170f — Player preview tile. Iter 230c — extracted. */}
            <DraftPreviewPanel
              players={players}
              selectedPlayerId={selectedPlayerId}
              setSelectedPlayerId={setSelectedPlayerId}
              lastPickedPlayerId={lastPickedPlayerId}
              draftStarted={draftConfig.draftStarted}
              queue={queue}
              shortlist={shortlist}
              canPickForCurrentTurn={canPickForCurrentTurn}
              minorsEnabled={!!(currentDraft as any)?.league_minors_enabled}
              onDraftPlayer={(p) => handleDraftPlayer(p as DraftEligiblePlayer)}
              toggleQueue={toggleQueue}
              toggleShortlist={toggleShortlist}
              setExpandedPlayer={setExpandedPlayer}
            />
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
              soundsEnabled={draftSounds.enabled}
              onToggleSounds={() => {
                const next = !draftSounds.enabled;
                draftSounds.setEnabled(next);
                // Preview tones the moment a manager flips the toggle on
                // — this also primes the AudioContext inside the user
                // gesture so the next real alert can fire when hidden.
                if (next) {
                  draftSounds.playNextUp();
                  toast.success("Draft alerts enabled", {
                    description: "You'll hear a chime when you're next up, and an alert when you're on the clock.",
                  });
                } else {
                  toast.info("Draft alerts muted");
                }
              }}
              onPreviewOnTheClock={draftSounds.playOnTheClock}
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

          {/* ── Bottom section: PlayerSearch · TruncatedRoster · DraftChat ──
              Iter 229j — extracted to DraftRoomBottomGrid. */}
          <DraftRoomBottomGrid
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
            minorsEnabled={!!(currentDraft as any)?.league_minors_enabled}
            queue={queue}
            shortlist={shortlist}
            queuedPlayers={queuedPlayers}
            shortlistedPlayers={shortlistedPlayers}
            setQueue={setQueue}
            setShortlist={setShortlist}
            toggleQueue={toggleQueue}
            toggleShortlist={toggleShortlist}
            removeFromQueue={removeFromQueue}
            activeLeagueCtx={activeLeagueCtx}
            myTeam={myTeam}
            rosterReloadTick={rosterReloadTick}
            liveTeams={liveTeams}
            tradeBlockItems={tradeBlockItems}
            toggleMyTeamTradeBlock={toggleMyTeamTradeBlock}
            tradeBuilder={tradeBuilder}
            chatMessages={chatMessages}
            chatInput={chatInput}
            setChatInput={setChatInput}
            handleSendChat={handleSendChat}
            user={user}
          />
        </div>

        {/* Iter 153 — Expanded Player Card. Iter 230j — extracted. */}
        <ExpandedPlayerModal player={expandedPlayer} onClose={() => setExpandedPlayer(null)} />
        {/* Iter 194c — floating pick-trade review pill (top-right). */}
        {activeLeagueCtx?.id && (
          <PickTradeReviewPill
            leagueId={activeLeagueCtx.id}
            lastChatEvent={lastChatEvent}
            currentUserId={userId}
          />
        )}
      </TooltipProvider>
    </AppLayout>
  );
}
