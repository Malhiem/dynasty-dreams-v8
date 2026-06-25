// @ts-nocheck
import { useState, useMemo, useEffect, useCallback, useRef } from "react";
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
// Iter 174 — Header strip (title + criteria popover + Trade Mode +
// Trading Block toggles) extracted into its own component.
import DraftHeaderActions from "@/lovable/pages/draftroom/DraftHeaderActions";
// Iter 172 — Audio alerts for "next up" + "on the clock" transitions.
import useDraftSounds, { useTabTitleAlert } from "@/hooks/use-draft-sounds";
// Iter 174 — trade-block state-blob + polling extracted into a hook.
import useDraftLiveState from "@/hooks/use-draft-live-state";
// Iter 229d — three small effect-hooks extracted from DraftRoom to
// keep this component focused on rendering + commissioner actions.
import useUpcomingDrafts from "@/hooks/use-upcoming-drafts";
import useDraftEligiblePlayers from "@/hooks/use-draft-eligible-players";
import usePendingPickTrade from "@/hooks/use-pending-pick-trade";
import useDraftCommissionerActions from "@/hooks/use-draft-commissioner-actions";
import useDraftPickHandler from "@/hooks/use-draft-pick-handler";
import PlayerCardModal from "@/lovable/components/dashboard/PlayerCardModal";
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

  // Iter 228n — Upcoming-drafts dropdown: list the next 30 days of
  // scheduled drafts for this league so commissioners + league
  // managers can switch (e.g. mid-season trade deadline draft vs.
  // off-season rookie draft). Defaults to the soonest.
  // Iter 229d — extracted into a dedicated hook.
  const { upcomingDrafts, selectedDraftId, setSelectedDraftId } =
    useUpcomingDrafts(activeLeagueCtx?.id);
  useEffect(() => {
    if (!activeLeagueCtx?.id) { setCurrentDraft(null); return; }
    let cancelled = false;
    (async () => {
      try {
        // Iter 228n — When the user picked a specific draft from the
        // upcoming-drafts dropdown, load that one directly instead of
        // auto-init (which always returns the most-recent draft).
        let data;
        if (selectedDraftId) {
          const r = await api.get(`/drafts/${selectedDraftId}`);
          data = { draft: r.data, created: false };
        } else {
          const r = await api.post(`/drafts/auto-init/${activeLeagueCtx.id}`);
          data = r.data;
        }
        if (cancelled) return;
        const d = data?.draft;
        if (!d) return;
        setCurrentDraft(d);
        // Hydrate picks + currentPick from backend if any picks exist
        if (Array.isArray(d.picks) && d.picks.length > 0) {
          setPicks(d.picks.map((p: any) => ({
            // Iter 228i — Stable unique key per pick. Was previously
            // derived from `pick-${Date.now()}` shared across rapid hydrates,
            // causing duplicate React keys when re-render fired twice.
            id: p.id || p._id || `pick-${p.round}-${p.pick_in_round || p.overall}`,
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
        // Iter 228j — Always hydrate totalRounds / pickTimerSeconds from
        // the backend even when current_pick is absent (scheduled drafts
        // pre-iter228 may not carry a numeric current_pick). Previously
        // this guard caused the Draft Board to stay stuck on the React
        // default of 5 rounds for legacy drafts.
        setDraftConfig((prev) => ({
          ...prev,
          currentPick: typeof d.current_pick === "number" ? d.current_pick : prev.currentPick,
          draftStarted: d.status === "active",
          totalRounds: d.total_rounds || prev.totalRounds,
          pickTimerSeconds: d.time_per_pick || prev.pickTimerSeconds,
          // Iter 228n — Anchor the "Draft starts in" countdown to the
          // backend's scheduled_time (set in League Admin > Drafts).
          // Previously this stayed pinned to the React default of
          // `Date.now() + 2h`, so the countdown showed the wrong ETA.
          scheduledTime: d.scheduled_time
            ? new Date(d.scheduled_time)
            : prev.scheduledTime,
        }));
        // Iter 228f — Hydrate missed_pick_action + defer_user_options
        // so the timer hook can decide whether to surface the dialog.
        if (d.missed_pick_action) setMissedPickAction(d.missed_pick_action);
        if (Array.isArray(d.defer_user_options) && d.defer_user_options.length) {
          setDeferAvailable(d.defer_user_options);
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
  }, [activeLeagueCtx?.id, selectedDraftId]);

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

  // Iter 228f — Defer-to-User missed-pick dialog state
  const [missedPickAction, setMissedPickAction] = useState<string>("auto-select");
  const [deferDialogOpen, setDeferDialogOpen] = useState(false);
  const [deferAvailable, setDeferAvailable] = useState<string[]>([
    "auto-best", "auto-queue", "pick-anytime",
  ]);
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

  // ── Iter 172 — Draft Room audio alerts ───────────────────────────────────
  // Two distinct synthesized tones so a manager who's tabbed away still
  // hears their turn coming:
  //   • picksUntilMyTurn transitions to 1 → soft "Next Up" chime
  //   • picksUntilMyTurn transitions to 0 → urgent "On the Clock" arpeggio
  // Plus a flashing browser-tab title while the user is on the clock.
  const draftSounds = useDraftSounds();
  const prevPicksUntilRef = useRef<number | null>(null);
  useEffect(() => {
    const prev = prevPicksUntilRef.current;
    const curr = picksUntilMyTurn;
    // Only react to actual transitions and only once a draft is live, so
    // hydration + initial mount don't blast the user with a chime.
    if (
      draftConfig.draftStarted
      && prev !== null
      && curr !== null
      && prev !== curr
    ) {
      if (curr === 1 && prev > 1) {
        draftSounds.playNextUp();
        try {
          toast.info("You're next up", {
            description: "Your team is on the clock after this pick. Get your queue ready.",
          });
        } catch { /* toast lib missing — non-critical */ }
      } else if (curr === 0 && prev > 0) {
        draftSounds.playOnTheClock();
        try {
          toast.success("You're on the clock!", {
            description: "Make your pick before the timer expires.",
          });
        } catch { /* toast lib missing — non-critical */ }
      }
    }
    prevPicksUntilRef.current = curr;
  }, [picksUntilMyTurn, draftConfig.draftStarted, draftSounds]);
  // Flash the browser tab title while the user is on the clock and not
  // currently viewing the page.
  useTabTitleAlert(draftConfig.draftStarted && picksUntilMyTurn === 0);

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
          {/* Iter 228n — Upcoming-drafts dropdown. Renders only when the
              league has 2+ scheduled drafts within the next 30 days.
              Defaults to the soonest; switching reloads the room. */}
          {upcomingDrafts.length > 1 && (
            <div
              className="flex flex-col sm:flex-row sm:items-center gap-2 rounded-md border border-border/60 bg-muted/20 px-3 py-2"
              data-testid="draft-room-upcoming-picker"
            >
              <span className="text-xs uppercase tracking-wider text-muted-foreground">
                Upcoming drafts ({upcomingDrafts.length})
              </span>
              <select
                className="bg-background border border-border rounded px-2 py-1 text-sm flex-1"
                value={selectedDraftId || ""}
                onChange={(e) => setSelectedDraftId(e.target.value)}
                data-testid="draft-room-upcoming-select"
              >
                {upcomingDrafts.map((d: any) => {
                  const id = d._id || d.id;
                  const when = d.scheduled_time
                    ? new Date(d.scheduled_time).toLocaleString(undefined, {
                        month: "short", day: "numeric",
                        hour: "numeric", minute: "2-digit",
                      })
                    : "TBD";
                  return (
                    <option key={id} value={id}>
                      {d.name || "Untitled Draft"} · {when}
                    </option>
                  );
                })}
              </select>
            </div>
          )}

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
                    minorsEnabled={!!(currentDraft as any)?.league_minors_enabled}
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
