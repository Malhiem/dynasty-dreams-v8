// @ts-nocheck
import { useState, useMemo, useCallback, useEffect, useRef } from "react";
import { useLocation } from "react-router-dom";
import { TrendingUp, TrendingDown, Minus, ArrowUpDown, ChevronLeft, ChevronRight, MinusCircle, MoveVertical, AlertTriangle, Save, Undo2, Settings, Megaphone, Shield } from "lucide-react";
import { NewsSignalIcon } from "@/lovable/components/NewsSignalIcon";
import { MinorEligibleBadge } from "@/lovable/components/MinorEligibleBadge";
import { toast } from "sonner";
import api from "@/lib/api";
import { useActiveLeague } from "@/hooks/use-active-league";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { PlayerTradeModal } from "@/lovable/components/trade/PlayerTradeModal";
import PlayerCardModal from "@/lovable/components/dashboard/PlayerCardModal";
import { ScrollArea, ScrollBar } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Checkbox } from "@/components/ui/checkbox";
import { Separator } from "@/components/ui/separator";
// Iter 183 — sub-components extracted to ./player-roster/sub-components.tsx
// We import them locally so the PlayerRoster component body's JSX can
// reference them by name. (The bottom of this file ALSO re-exports
// them so external consumers of PlayerRoster keep working.)
import { DailyGoaliePicker } from "./player-roster/DailyGoaliePicker";
import { LineupLockBanner } from "./player-roster/LineupLockBanner";
import { EmergencyBudgetChip } from "./player-roster/EmergencyBudgetChip";
import { RosterColumnSettings } from "./player-roster/RosterColumnSettings";
import {
  StatsTable,
  CapHitTable,
  FantasyPointsTable,
  MatchupScheduleTable,
  FullScheduleTable,
  SectionGroup,
  EmptySlotRow,
  OpenSlotRow,
  PlayerRow,
  TradeButton,
  MegaphoneButton,
  DropButton,
  OwnershipCell,
} from "./player-roster/sub-components";
// Iter 183 — use the SAME RosterConfigContext that sub-components
// subscribe to (defined in internals.tsx) so the Provider in this
// file broadcasts to them. Without this both files would create
// distinct contexts and sub-tables would silently fall back to the
// static default 7-slot layout instead of the league's
// position_breakdown.active.
// Iter 185 — pull every shared type / constant / helper from
// internals.tsx so PlayerRoster.tsx stops carrying inline duplicates.
import {
  RosterConfigContext as SharedRosterConfigContext,
  // constants (module-level defaults; shadowed inside the component
  // by useMemo derivations that pull from the active league config)
  POSITION_ACQUISITION_THRESHOLD,
  ALL_POSITIONS,
  slotEligibility,
  LEAGUE_ROSTER_SLOTS,
  sectionConfig,
  sectionOrder,
  rosterStatCategories,
  trackedCategories,
  untrackedCategories,
  allStatCategories,
  filterLabels,
  categoryLabels,
  MINORS_MAX_AGE,
  MINORS_MAX_GAMES,
  // helpers
  buildLeagueRosterSlots,
  checkIneligibility,
  findHighlightedPlayer,
  formatSalary,
  // Iter 186 — relocated component-domain helpers
  getContractTypeColor,
  getRosterViolations,
  canOwnerFixViolations,
  // leaf components (real implementations live here too — iter185)
  TrendIndicator,
  PositionBadges,
  PositionButton,
  getSlotPositionColor,
  getPositionColor,
  getSlotDisplayLabel,
} from "./player-roster/internals";
// Iter 186 — mock data lives in a sibling file now.
import {
  generateSchedule,
  seededRand,
  frostbitePlayers,
  playerPool,
  slotLabels,
  generateTeamRoster,
  weeklyMatchups,
  currentWeek,
  type WeekMatchup,
} from "./player-roster/mock-data";
// Iter 186 — Re-export the relocated helpers so any downstream
// consumer that historically imported them off `PlayerRoster.tsx`
// keeps working with no source change.
export {
  getContractTypeColor,
  getRosterViolations,
  canOwnerFixViolations,
} from "./player-roster/internals";
export {
  generateSchedule,
  seededRand,
  frostbitePlayers,
  playerPool,
  slotLabels,
  generateTeamRoster,
  weeklyMatchups,
  currentWeek,
} from "./player-roster/mock-data";
export type { WeekMatchup } from "./player-roster/mock-data";
// Re-export public types/constants so external consumers (tests,
// other dashboard pieces) keep finding them on PlayerRoster.tsx.
export type {
  Player,
  RosterSection,
  RosterSlot,
  RosterSlotType,
  ViewFilter,
  IneligibilityInfo,
} from "./player-roster/internals";
export {
  POSITION_ACQUISITION_THRESHOLD,
  ALL_POSITIONS,
  slotEligibility,
  LEAGUE_ROSTER_SLOTS,
  sectionConfig,
  sectionOrder,
  rosterStatCategories,
  trackedCategories,
  untrackedCategories,
  allStatCategories,
  filterLabels,
  buildLeagueRosterSlots,
  checkIneligibility,
} from "./player-roster/internals";
// Local imports of the actual Player type for use in this file
import type {
  Player,
  RosterSection,
  RosterSlot,
} from "./player-roster/internals";
// ── Types ──────────────────────────────────────────────
// Iter 185 — Domain types now live in `./player-roster/internals`
// and are re-exported above for external consumers. The PlayerRoster
// file used to inline duplicates of Player, Contract, RosterSection,
// RosterSlot, ViewFilter, etc.; all removed.

// Iter 183/185 — RosterConfig context lives in internals.tsx; the
// Provider in PlayerRoster's render uses the `SharedRosterConfigContext`
// alias imported above to broadcast the dynamic league-driven config
// to the sub-tables in `./player-roster/sub-components.tsx`.

// ── Mock Data + roster-domain helpers ──────────────────
// Iter 186 — Extracted to `./player-roster/mock-data.ts` and
// `./player-roster/internals.tsx` to keep this file focused on
// render orchestration. All names are imported + re-exported
// at the top of the file for backwards compat.

// ── Component ──────────────────────────────────────────

interface PlayerRosterProps {
  isOwnTeam?: boolean;
  commissionerMode?: boolean;
  onTradePlayer?: (player: any) => void;
  onDropPlayer?: (player: any) => void;
  onAddToTradeBlock?: (player: any) => void;
  tradeBlockPlayerIds?: string[];
  /** Iter 144 — protection list integration */
  onToggleProtection?: (player: any) => void;
  protectedPlayerIds?: string[];
  protectionEnabled?: boolean;
  protectionDraftType?: "keeper" | "expansion" | null;
  isTradeBuilderOpen?: boolean;
  currentTeamContext?: string;
  teamId?: string;
  /** Bump this number to force a re-fetch of /roster/{teamId}/detail.
   * Used after drops, trade-block toggles, or other mutations so the table
   * reflects the latest server state without a full page reload. */
  refreshKey?: number;
  /** League ID — required for fetching per-league ownership. */
  leagueId?: string;
}
/* ───────── Iter 106: Daily Goalie Picker (per-day starter) ───────── */

const PlayerRoster = ({
  isOwnTeam = true,
  commissionerMode = false,
  onTradePlayer,
  onDropPlayer,
  onAddToTradeBlock,
  tradeBlockPlayerIds = [],
  // Iter 144 — protection list props
  onToggleProtection,
  protectedPlayerIds = [],
  protectionEnabled = false,
  protectionDraftType = null,
  isTradeBuilderOpen = false,
  currentTeamContext = "mine",
  teamId = "frostbite",
  refreshKey = 0,
  leagueId,
}: PlayerRosterProps) => {
  const location = useLocation();
  const isTeamRosterPage = location.pathname.startsWith("/team");

  // Iter 180 — Shadow the module-level LEAGUE_ROSTER_SLOTS with a
  // league-driven version derived from `position_breakdown.active`.
  // Falls back to the module default when no breakdown is configured
  // (e.g. legacy leagues, or before the league has loaded). The
  // shadow only takes effect inside this component scope; module-level
  // helpers (mock-data generation, etc.) continue to read the default.
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const { league: activeLeagueFromHook } = useActiveLeague();
  const LEAGUE_ROSTER_SLOTS = useMemo(
    () => buildLeagueRosterSlots((activeLeagueFromHook as any)?.position_breakdown?.active),
    [(activeLeagueFromHook as any)?.position_breakdown],
  );

  // Iter 180 — Section maxSlots also need to honor the active
  // league config (bench_spots / ir_slots / minors_spots). Shadow the
  // module-level `sectionConfig` so the move-validation logic and
  // section headers all read the right caps. Falls back to the
  // module defaults when a value isn't configured.
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const sectionConfig = useMemo(() => {
    const l: any = activeLeagueFromHook || {};
    // Iter 228m — When the league has split Minors enabled, the
    // "minors" pool reads `minors_skater_spots` and the
    // "goalies_minors" pool reads `minors_goalie_spots`. Otherwise
    // both fall back to the combined `minors_spots` value (which the
    // backend now auto-derives from the position-breakdown row sum).
    const splitOn = !!l.minors_split_enabled;
    const skaterMinorsMax = splitOn && typeof l.minors_skater_spots === "number"
      ? l.minors_skater_spots
      : (typeof l.minors_spots === "number" ? l.minors_spots : 0);
    const goalieMinorsMax = splitOn && typeof l.minors_goalie_spots === "number"
      ? l.minors_goalie_spots
      : (typeof l.minors_spots === "number" ? l.minors_spots : 0);
    const _modDefaults = ({
      starting: { label: "Starting Roster", color: "bg-primary/10", borderColor: "border-l-primary", maxSlots: LEAGUE_ROSTER_SLOTS.length },
      bench: { label: "Bench", color: "bg-accent/10", borderColor: "border-l-accent", maxSlots: typeof l.bench_spots === "number" ? l.bench_spots : 4 },
      ir: { label: "Injury Reserve", color: "bg-destructive/10", borderColor: "border-l-destructive", maxSlots: typeof l.ir_slots === "number" ? l.ir_slots : 3 },
      minors: { label: splitOn ? "Skater Minors" : "Minors Pool", color: "bg-purple-500/10", borderColor: "border-l-purple-500", maxSlots: skaterMinorsMax },
      goalies: { label: "Goalies", color: "bg-teal-500/10", borderColor: "border-l-teal-500", maxSlots: 4 },
      goalies_minors: { label: splitOn ? "Goalie Minors" : "Goalies — Minors Pool", color: "bg-teal-500/5", borderColor: "border-l-teal-700", maxSlots: goalieMinorsMax },
    });
    return _modDefaults;
  }, [activeLeagueFromHook, LEAGUE_ROSTER_SLOTS.length]);

  // Detect MongoDB ObjectId (24 hex) — if so, load the real roster from the backend.
  const isRealTeamId = useMemo(() => /^[a-f0-9]{24}$/i.test(teamId), [teamId]);
  const [livePlayers, setLivePlayers] = useState<Player[] | null>(null);
  const [liveLoading, setLiveLoading] = useState(false);

  useEffect(() => {
    if (!isRealTeamId) {
      setLivePlayers(null);
      return;
    }
    let cancelled = false;
    setLiveLoading(true);
    api.get(`/roster/${teamId}/detail`)
      .then(({ data }) => {
        if (cancelled) return;
        const raw = data?.players || [];
        const shaped: Player[] = raw.map((p: any, idx: number) => ({
          id: p.id,
          name: p.name,
          position: p.position,
          eligiblePositions: p.eligiblePositions || [p.position],
          secondaryPositions: [],
          team: p.team || "",
          points: Math.round(p.fantasy_points || 0),
          gamesPlayed: Number(p.games_played || p.gp || 0),
          dynastyValue: p.dynastyValue || 1000,
          trend: (p.trend || "stable") as "up" | "down" | "stable",
          age: p.age || 27,
          contract: {
            salary: p.contract?.salary || 950000,
            yearsRemaining: p.contract?.yearsRemaining || 1,
            type: (p.contract?.type || "Signed") as any,
          },
          rosterSection: (p.rosterSection || "bench") as RosterSection,
          rosterSlotId: p.rosterSlotId || undefined,
          statsByPeriod: p.statsByPeriod || { season: 0, "1d": 0, "7d": 0, "14d": 0, "30d": 0, "60d": 0, "100d": 0 },
          categoryBreakdown: p.categoryBreakdown || { G: 0, A: 0, PPP: 0, SHP: 0, SOG: 0, HIT: 0, BLK: 0, PIM: 0, "+/-": 0, FOW: 0, FOL: 0 },
          matchupGames: p.matchupGames || 0,
          schedule: generateSchedule(idx + 1),
          // Iter 181 — propagate minor_eligible + player_type so the
          // MinorEligibleBadge renders consistently on the team page.
          minor_eligible: !!p.minor_eligible,
          player_type: p.player_type || "skater",
        }));
        setLivePlayers(shaped);
      })
      .catch((e) => { console.error("roster detail load failed", e); setLivePlayers([]); })
      .finally(() => { if (!cancelled) setLiveLoading(false); });
    return () => { cancelled = true; };
  }, [teamId, isRealTeamId, refreshKey]);

  // ── Ownership map: { player_id: {league_pct, league_owned, ...} } ──
  // Fetched once we know every roster player; bumps with refreshKey so adds
  // and drops re-pull fresh ownership numbers.
  const [ownershipMap, setOwnershipMap] = useState<Record<string, any>>({});
  useEffect(() => {
    if (!livePlayers || livePlayers.length === 0) { setOwnershipMap({}); return; }
    const ids = Array.from(new Set(livePlayers.map((p: any) => String(p.id))));
    let cancelled = false;
    api.post("/players/ownership-bulk", { player_ids: ids, league_id: leagueId })
      .then(({ data }) => {
        if (cancelled) return;
        setOwnershipMap(data?.ownership || {});
      })
      .catch(() => { if (!cancelled) setOwnershipMap({}); });
    return () => { cancelled = true; };
  }, [livePlayers, leagueId, refreshKey]);

  // ── Scoring config (per-category fantasy point weights) ──
  // Used by the "Fantasy Points" filter to break down each player's FPTS
  // into per-category contribution (e.g. 10 goals × 3 = 30 pts).
  const [scoringConfig, setScoringConfig] = useState<any>(null);
  // ── Iter 103: Live lineup-lock status banner ───────────────────
  // Polls `/leagues/{id}/lock-status` every 60s so the manager sees a
  // warning BEFORE the save fails. Server-side gate in `save_team_lineup`
  // is still the source of truth — this is purely a friendly pre-warn.
  const [lockStatus, setLockStatus] = useState<any>(null);
  useEffect(() => {
    if (!leagueId) { setLockStatus(null); return; }
    let cancelled = false;
    const fetchOnce = () => {
      api.get(`/leagues/${leagueId}/lock-status`)
        .then(({ data }) => { if (!cancelled) setLockStatus(data); })
        .catch(() => { if (!cancelled) setLockStatus(null); });
    };
    fetchOnce();
    const t = setInterval(fetchOnce, 60_000);
    return () => { cancelled = true; clearInterval(t); };
  }, [leagueId]);

  // ── Iter 106: Emergency swap budget + per-day goalie lock map ──
  const [emergencyBudget, setEmergencyBudget] = useState<any>(null);
  const [goalieLockMap, setGoalieLockMap] = useState<Record<string, string>>({});
  const [savingDailyLock, setSavingDailyLock] = useState(false);
  useEffect(() => {
    if (!teamId || !isRealTeamId) { setEmergencyBudget(null); return; }
    api.get(`/teams/${teamId}/emergency-swap-budget`)
      .then(({ data }) => setEmergencyBudget(data))
      .catch(() => setEmergencyBudget(null));
  }, [teamId, isRealTeamId, lockStatus?.locked]);  // refetch when lock state changes

  useEffect(() => {
    if (!teamId || !isRealTeamId) { setGoalieLockMap({}); return; }
    api.get(`/teams/${teamId}`)
      .then(({ data }) => setGoalieLockMap(data?.goalie_daily_lock || {}))
      .catch(() => setGoalieLockMap({}));
  }, [teamId, isRealTeamId]);

  // Pull league goalie config so we know when to render the picker
  const [leagueGoalieCfg, setLeagueGoalieCfg] = useState<any>(null);
  useEffect(() => {
    if (!leagueId) { setLeagueGoalieCfg(null); return; }
    api.get(`/leagues/${leagueId}`)
      .then(({ data }) => setLeagueGoalieCfg({
        differentiate_goalie_scoring: !!data?.differentiate_goalie_scoring,
        goalie_scoring_method: data?.goalie_scoring_method,
        goalie_gp_limit_enabled: !!data?.goalie_gp_limit_enabled,
        goalie_gp_limit: data?.goalie_gp_limit,
      }))
      .catch(() => setLeagueGoalieCfg(null));
  }, [leagueId]);

  const saveGoalieLockMap = async (nextMap: Record<string, string>) => {
    if (!teamId || !isRealTeamId) return;
    setSavingDailyLock(true);
    try {
      const { data } = await api.put(`/teams/${teamId}/goalie-daily-lock`, { lock_map: nextMap });
      setGoalieLockMap(data?.lock_map || {});
      toast.success(`Daily goalie lock saved (${data?.count || 0} day${(data?.count || 0) === 1 ? "" : "s"})`);
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Failed to save goalie lock");
    } finally {
      setSavingDailyLock(false);
    }
  };
  // ── Lineup warnings (iter 84) ───────────────────────────────────
  // Backend returns `warnings: [{code, player_id, message, ...}]` after a
  // successful lineup save. Map them by player_id so the row can render
  // a yellow chip explaining why the player is flagged (e.g. below the
  // league's `min_games_played` threshold).
  const [lineupWarnings, setLineupWarnings] = useState<Record<string, any[]>>({});
  useEffect(() => {
    if (!leagueId) return;
    let cancelled = false;
    api.get(`/scoring/config?league_id=${leagueId}`)
      .then(({ data }) => { if (!cancelled) setScoringConfig(data); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [leagueId]);

  // ── News map: { player_id: {news_headline, news_summary, news_signal, ...} } ──
  // Powers the inline news icon next to each player's name. The icon opens
  // a small in-app modal (no external browser hop) from NewsSignalIcon.
  const [newsMap, setNewsMap] = useState<Record<string, any>>({});
  useEffect(() => {
    if (!livePlayers || livePlayers.length === 0) { setNewsMap({}); return; }
    const ids = Array.from(new Set(livePlayers.map((p: any) => String(p.id))));
    let cancelled = false;
    api.post("/players/news-bulk", { player_ids: ids })
      .then(({ data }) => {
        if (cancelled) return;
        setNewsMap(data?.news || {});
      })
      .catch(() => { if (!cancelled) setNewsMap({}); });
    return () => { cancelled = true; };
  }, [livePlayers, refreshKey]);

  const teamRoster = useMemo(() => {
    if (isRealTeamId) {
      // For real (DB) team IDs, NEVER fall back to the mock player pool
      // (that's why Vasilevskiy/Saros toasted as "ineligible" even though
      // they aren't on the user's roster). Wait until livePlayers resolves.
      return livePlayers || [];
    }
    // Use a numeric seed from teamId string (mock fallback for non-DB ids)
    let seed = 0;
    for (let i = 0; i < teamId.length; i++) seed += teamId.charCodeAt(i) * (i + 1);
    return generateTeamRoster(teamId, seed);
  }, [teamId, isRealTeamId, livePlayers]);

  // Load saved roster from localStorage if available
  const loadSavedRoster = useCallback((tid: string, fallback: Player[]): Player[] => {
    try {
      const stored = localStorage.getItem(`roster_${tid}`);
      if (stored) {
        const savedSections: Record<number, { rosterSection: RosterSection; rosterSlotId?: string }> = JSON.parse(stored);
        return fallback.map(p => {
          const override = savedSections[p.id];
          if (override) {
            return { ...p, rosterSection: override.rosterSection, rosterSlotId: override.rosterSlotId };
          }
          return p;
        });
      }
    } catch { /* ignore parse errors */ }
    return fallback;
  }, []);

  const persistRoster = useCallback((tid: string, roster: Player[]) => {
    const sections: Record<number, { rosterSection: RosterSection; rosterSlotId?: string }> = {};
    roster.forEach(p => {
      sections[p.id] = { rosterSection: p.rosterSection, rosterSlotId: p.rosterSlotId };
    });
    localStorage.setItem(`roster_${tid}`, JSON.stringify(sections));
  }, []);

  const [players, setPlayers] = useState<Player[]>(() => loadSavedRoster(teamId, teamRoster));
  const [savedPlayers, setSavedPlayers] = useState<Player[]>(() => loadSavedRoster(teamId, teamRoster));

  // Reset players when teamId changes
  useEffect(() => {
    const loaded = loadSavedRoster(teamId, teamRoster);
    setPlayers(loaded);
    setSavedPlayers(loaded);
    setHasUnsavedChanges(false);
    setHighlightedPlayerId(null);
    toastShownRef.current = false; // reset toast guard so new team's ineligibility re-evaluates
  }, [teamRoster, teamId, loadSavedRoster]);
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);
  const [emergencyChangesUsed, setEmergencyChangesUsed] = useState(() => {
    try {
      return parseInt(localStorage.getItem(`emergency_changes_${teamId}`) || "0", 10);
    } catch { return 0; }
  });
  const emergencyChangesAllowed = 2; // from league settings (mock)
  const emergencyChangesRemaining = Math.max(0, emergencyChangesAllowed - emergencyChangesUsed);
  const isRosterLocked = true; // mock: current week rosters are locked (weekly lock)
  const [tradeModalOpen, setTradeModalOpen] = useState(false);
  const [selectedPlayer, setSelectedPlayer] = useState<Player | null>(null);
  const [cardPlayer, setCardPlayer] = useState<Player | null>(null);
  const [cardOpen, setCardOpen] = useState(false);
  const [viewFilter, setViewFilter] = useState<ViewFilter>("season");
  // Iter 185 — Section-summary timeframe. Powers the per-section
  // "Avg X fpts/g · {timeframe}" + top/bottom performer pill in
  // every SectionGroup. Independent from `viewFilter` (which drives
  // the stat-table column selection) — owners often want to see
  // Cap-Hit / Season Stats columns while assessing Last 7 Days
  // trade upside per section.
  const [sectionTimeframe, setSectionTimeframe] = useState<string>("season");
  const [selectedWeek, setSelectedWeek] = useState<number>(currentWeek);
  const [highlightedPlayerId, setHighlightedPlayerId] = useState<number | null>(null);
  const [visibleColumns, setVisibleColumns] = useState<Set<string>>(() => new Set([...rosterStatCategories, "FPTS"]));
  const [showPositionEligibility, setShowPositionEligibility] = useState(true);
  const toastShownRef = useRef(false);
  const saveToastId = useRef<string | number | undefined>(undefined);

  // ── Roster violation state ──
  const currentViolations = useMemo(() => getRosterViolations(players), [players]);
  const hasIllegalRoster = currentViolations.length > 0;

  // ── Ineligibility toast notifications on mount ──
  useEffect(() => {
    if (toastShownRef.current) return;
    // For real teams, wait until livePlayers loads so we don't toast about
    // mock-pool players (e.g. Vasilevskiy/Saros) that aren't on the actual
    // roster.
    if (isRealTeamId && (liveLoading || livePlayers === null)) return;
    if (players.length === 0) return;
    const ineligible = players.filter(p => checkIneligibility(p).isIneligible);
    if (ineligible.length > 0) {
      ineligible.forEach(p => {
        const info = checkIneligibility(p);
        toast.error(`${p.name}: ${info.reason}`);
      });
      // Check if owner can fix
      if (isTeamRosterPage && !canOwnerFixViolations(players)) {
        toast.error("No available roster move can resolve violations", {
          description: "Please contact League Administration for assistance.",
          icon: <AlertTriangle className="h-4 w-4" />,
          duration: Infinity,
        });
      }
      toastShownRef.current = true;
    }
  }, [livePlayers, liveLoading, isRealTeamId, players, isTeamRosterPage]);

  // ── Show save/undo toast when unsaved changes exist ──
  useEffect(() => {
    if (hasUnsavedChanges) {
      // Dismiss previous save toast if any
      if (saveToastId.current) toast.dismiss(saveToastId.current);
      
      const violations = getRosterViolations(players);
      const isLegal = violations.length === 0;

      saveToastId.current = toast(
        isLegal ? "Roster changes pending" : "⚠️ Illegal roster — fix required before saving",
        {
          description: isLegal
            ? "Save your roster changes or undo to revert."
            : violations.map(v => `${v.player.name}: ${v.reason}`).join(" · "),
          duration: Infinity,
          action: isLegal
            ? {
                label: "Save Roster",
                onClick: async () => {
                  setSavedPlayers([...players]);
                  persistRoster(teamId, players);
                  // Persist active lineup to backend so % Start reflects this team.
                  // We map each player's local rosterSection (forward/defense/
                  // goalie/bench/ir/minors) to the team's lineup map.
                  let saveOk = !isRealTeamId; // demo teams always succeed
                  if (isRealTeamId) {
                    try {
                      const lineup: Record<string, { section: string; slot: string }> = {};
                      players.forEach((p: any) => {
                        const section = (p.rosterSection || "bench").toString();
                        lineup[String(p.id)] = { section, slot: p.position || section.toUpperCase().slice(0, 3) };
                      });
                      const { data } = await api.post(`/teams/${teamId}/lineup`, { lineup });
                      saveOk = true;
                      // ── Lineup warnings (iter 84) ─────────────────────
                      // Backend returns `warnings: [{code, player_id, ...}]`
                      // for things like `min_games_played` violations. Cache
                      // them per player so the card can render a yellow chip
                      // and toast a top-level summary so the user knows the
                      // save succeeded WITH caveats.
                      const warns = Array.isArray(data?.warnings) ? data.warnings : [];
                      const byPlayer: Record<string, any[]> = {};
                      warns.forEach((w: any) => {
                        const pid = String(w.player_id || "__league__");
                        (byPlayer[pid] ||= []).push(w);
                      });
                      setLineupWarnings(byPlayer);
                      if (warns.length > 0) {
                        toast.warning(
                          `Saved with ${warns.length} warning${warns.length === 1 ? "" : "s"}`,
                          {
                            description: warns
                              .slice(0, 3)
                              .map((w: any) => w.message)
                              .join(" · "),
                            duration: 8000,
                          },
                        );
                      }
                    } catch (e: any) {
                      const detail = e?.response?.data?.detail;
                      // ── Iter 108: Polished emergency-eligibility denial toast ──
                      if (typeof detail === "string" && detail.startsWith("Emergency swap denied for ")) {
                        // Parse "Emergency swap denied for <name>: player status doesn't match any allowed criteria (a, b, c)."
                        const nameMatch = detail.match(/Emergency swap denied for ([^:]+):/);
                        const critMatch = detail.match(/\(([^)]+)\)/);
                        const name = nameMatch?.[1]?.trim() || "Player";
                        const crits = (critMatch?.[1] || "")
                          .split(",")
                          .map((s: string) => s.trim())
                          .filter((s: string) => s && s !== "any");
                        const allowedHuman = crits.length
                          ? crits.map((c: string) => ({
                              scratched: "healthy scratch",
                              injured: "injured / IR",
                              minors: "in minors",
                              suspended: "suspended",
                              personal: "personal leave",
                            } as Record<string, string>)[c] || c).join(", ")
                          : "any eligible status";
                        toast.error(
                          `${name} isn't eligible for an emergency swap`,
                          {
                            description: `Allowed only for players who are: ${allowedHuman}. Pick a different starter or wait for the lock to release.`,
                            duration: 10000,
                            icon: <AlertTriangle className="h-4 w-4" />,
                          },
                        );
                      } else if (detail) {
                        toast.error(`Lineup save blocked: ${detail}`, { duration: 8000 });
                      } else {
                        console.warn("lineup save failed", e);
                        toast.error("Lineup save failed. Please try again.", { duration: 6000 });
                      }
                    }
                  }
                  if (saveOk) {
                    setHasUnsavedChanges(false);
                    toast.success("Roster saved successfully!");
                  }
                },
              }
            : undefined,
          cancel: {
            label: "Undo",
            onClick: () => {
              setPlayers([...savedPlayers]);
              setHasUnsavedChanges(false);
              toast.info("Roster changes reverted.");
            },
          },
        }
      );
    } else {
      if (saveToastId.current) {
        toast.dismiss(saveToastId.current);
        saveToastId.current = undefined;
      }
    }
  }, [hasUnsavedChanges, players, savedPlayers]);

  const handleOpenTrade = (player: Player) => {
    if (onTradePlayer) {
      // Use the new TradeBuilder flow
      const tradePlayer = {
        id: player.id,
        name: player.name,
        position: player.position,
        eligiblePositions: player.eligiblePositions,
        team: player.team,
        points: player.points,
        dynastyValue: player.dynastyValue,
        trend: player.trend,
        age: player.age,
        contract: player.contract,
        categoryBreakdown: player.categoryBreakdown,
        statsByPeriod: player.statsByPeriod,
        fromTeam: currentTeamContext,
      };
      onTradePlayer(tradePlayer);
    } else {
      setSelectedPlayer(player);
      setTradeModalOpen(true);
    }
  };

  const handleOpenCard = (player: Player) => {
    setCardPlayer(player);
    setCardOpen(true);
  };

  const handleToggleHighlight = useCallback((playerId: number) => {
    setHighlightedPlayerId(prev => {
      if (prev === null || prev === playerId) {
        return prev === playerId ? null : playerId;
      }

      // Attempt roster spot swap
      setPlayers(currentPlayers => {
        const source = currentPlayers.find(p => p.id === prev);
        const target = currentPlayers.find(p => p.id === playerId);
        if (!source || !target) return currentPlayers;

        const sourceSlot = source.rosterSlotId ? LEAGUE_ROSTER_SLOTS.find(s => s.id === source.rosterSlotId) : null;
        const targetSlot = target.rosterSlotId ? LEAGUE_ROSTER_SLOTS.find(s => s.id === target.rosterSlotId) : null;

        const targetCanFillSourceSlot = sourceSlot
          ? sourceSlot.eligiblePositions.some(ep => target.eligiblePositions.includes(ep))
          : true;
        const sourceCanFillTargetSlot = targetSlot
          ? targetSlot.eligiblePositions.some(ep => source.eligiblePositions.includes(ep))
          : true;

        if (!targetCanFillSourceSlot || !sourceCanFillTargetSlot) {
          const reasons: string[] = [];
          if (!targetCanFillSourceSlot) reasons.push(`${target.name} is not eligible for the ${getSlotDisplayLabel(source)} slot`);
          if (!sourceCanFillTargetSlot) reasons.push(`${source.name} is not eligible for the ${getSlotDisplayLabel(target)} slot`);
          toast.error("Swap denied", { description: reasons.join(". ") });
          return currentPlayers;
        }

        // Simulate the swap
        const updated = currentPlayers.map(p => {
          if (p.id === source.id) return { ...p, rosterSection: target.rosterSection, rosterSlotId: target.rosterSlotId };
          if (p.id === target.id) return { ...p, rosterSection: source.rosterSection, rosterSlotId: source.rosterSlotId };
          return p;
        });

        // If roster is currently illegal, only allow moves that reduce violations
        const currentViolationCount = getRosterViolations(currentPlayers).length;
        const newViolationCount = getRosterViolations(updated).length;

        if (currentViolationCount > 0 && newViolationCount >= currentViolationCount) {
          // This move doesn't fix anything — deny it
          const violations = getRosterViolations(currentPlayers);
          const violationReasons = violations.map(v => `${v.player.name}: ${v.reason}`).join(". ");
          
          toast.error("Move denied — illegal roster must be corrected first", {
            description: violationReasons,
          });

          // Check if ANY move can fix it
          if (isTeamRosterPage && !canOwnerFixViolations(currentPlayers)) {
            toast.error("No available roster move can resolve violations", {
              description: "Please contact League Administration for assistance.",
              icon: <AlertTriangle className="h-4 w-4" />,
              duration: 8000,
            });
          }
          return currentPlayers;
        }

        const sourceLabel = getSlotDisplayLabel(source);
        const targetLabel = getSlotDisplayLabel(target);
        toast.success(`Roster swap: ${target.name} → ${sourceLabel}, ${source.name} → ${targetLabel}`);
        setHasUnsavedChanges(true);
        return updated;
      });

      return null;
    });
  }, []);

  // ── Move highlighted player to a section (bench/IR) ──
  const handleMoveToSection = useCallback((targetSection: RosterSection) => {
    setHighlightedPlayerId(prev => {
      if (!prev) return null;

      setPlayers(currentPlayers => {
        const source = currentPlayers.find(p => p.id === prev);
        if (!source) return currentPlayers;

        // Check section capacity
        const sectionCount = currentPlayers.filter(p => p.rosterSection === targetSection).length;
        if (sectionCount >= sectionConfig[targetSection].maxSlots) {
          toast.error(`Cannot move to ${sectionConfig[targetSection].label}`, {
            description: `Section is full (${sectionCount}/${sectionConfig[targetSection].maxSlots})`,
          });
          return currentPlayers;
        }

        // IR eligibility: player must have no recent stats (injured)
        if (targetSection === "ir") {
          const hasRecentStats = source.statsByPeriod["7d"] > 0 || source.statsByPeriod["1d"] > 0;
          if (hasRecentStats) {
            toast.error("Cannot place on Injury Reserve", {
              description: `${source.name} is healthy and not eligible for IR`,
            });
            return currentPlayers;
          }
        }

        // Simulate the move
        const updated = currentPlayers.map(p => {
          if (p.id === source.id) return { ...p, rosterSection: targetSection as RosterSection, rosterSlotId: undefined };
          return p;
        });

        const newViolations = getRosterViolations(updated);

        const targetLabel = sectionConfig[targetSection].label;
        toast.success(`${source.name} moved to ${targetLabel}`);
        
        // Warn about any violations in the new roster state
        if (newViolations.length > 0) {
          const emptySlotViolations = newViolations.filter(v => v.reason.startsWith("Empty starting position"));
          const otherViolations = newViolations.filter(v => !v.reason.startsWith("Empty starting position"));
          if (emptySlotViolations.length > 0) {
            toast.warning("Roster is now illegal", {
              description: emptySlotViolations.map(v => v.reason).join(". "),
            });
          }
          if (otherViolations.length > 0) {
            toast.warning("Roster violations remain", {
              description: otherViolations.map(v => `${v.player.name}: ${v.reason}`).join(". "),
            });
          }
        }
        
        setHasUnsavedChanges(true);
        return updated;
      });

      return null;
    });
  }, []);

  // Get the highlighted player's eligible positions
  const highlightedPlayer = highlightedPlayerId
    ? players.find(p => p.id === highlightedPlayerId)
    : null;
  const highlightedPositions = highlightedPlayer?.eligiblePositions ?? [];

  const matchup = weeklyMatchups.find(w => w.week === selectedWeek);
  const isPastWeek = selectedWeek < currentWeek;

  const grouped = sectionOrder.reduce((acc, section) => {
    const sectionPlayers = players.filter(p => p.rosterSection === section);
    // Sort starting players by their slot order
    if (section === "starting") {
      const slotOrder = LEAGUE_ROSTER_SLOTS.map(s => s.id);
      sectionPlayers.sort((a, b) => {
        const aIdx = a.rosterSlotId ? slotOrder.indexOf(a.rosterSlotId) : 999;
        const bIdx = b.rosterSlotId ? slotOrder.indexOf(b.rosterSlotId) : 999;
        return aIdx - bIdx;
      });
    }
    acc[section] = sectionPlayers;
    return acc;
  }, {} as Record<RosterSection, Player[]>);

  // Section counts for open slot logic
  const currentSectionCounts = useMemo(() => {
    const counts: Record<RosterSection, number> = { starting: 0, bench: 0, ir: 0, minors: 0 };
    players.forEach(p => { counts[p.rosterSection]++; });
    return counts;
  }, [players]);

  const effectiveFilter = isPastWeek && viewFilter === "season" ? "7d" : viewFilter;

  const getPlayerPoints = (player: Player): number => {
    if (effectiveFilter === "fantasy-points" || effectiveFilter === "matchup-schedule" || effectiveFilter === "full-schedule") {
      return player.points;
    }
    return player.statsByPeriod[effectiveFilter] ?? player.points;
  };

  const getSectionTotal = (section: RosterSection): number => {
    return grouped[section].reduce((sum, p) => sum + getPlayerPoints(p), 0);
  };

  const filteredStatCategories = useMemo(() =>
    allStatCategories.filter(cat => visibleColumns.has(cat)),
    [visibleColumns]
  );
  const showFpts = visibleColumns.has("FPTS");

  return (
    <SharedRosterConfigContext.Provider
      value={useMemo(
        () => ({ slots: LEAGUE_ROSTER_SLOTS, sections: sectionConfig as any }),
        [LEAGUE_ROSTER_SLOTS, sectionConfig],
      )}
    >
    <>
      <div className="stat-card p-0 overflow-hidden">
        {/* ── Iter 103/187: Lineup Lock Status Banner ── */}
        <LineupLockBanner lockStatus={lockStatus} />
        {/* ── Iter 106/187: Emergency Swaps chip ── */}
        <EmergencyBudgetChip emergencyBudget={emergencyBudget} />
        {/* ── Iter 106: Per-Day Goalie Picker ── */}
        {leagueGoalieCfg?.differentiate_goalie_scoring && leagueGoalieCfg?.goalie_scoring_method === "daily_lock" && (
          <DailyGoaliePicker
            roster={teamRoster}
            lockMap={goalieLockMap}
            onSave={saveGoalieLockMap}
            saving={savingDailyLock}
            gpLimit={leagueGoalieCfg.goalie_gp_limit_enabled ? leagueGoalieCfg.goalie_gp_limit : null}
            week={selectedWeek}
          />
        )}
        {/* ── Matchup Bar ── */}
        <div className="p-4 border-b border-border bg-secondary/20">
          <div className="flex flex-wrap items-center gap-3">
            <div className="flex items-center gap-1">
              <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => setSelectedWeek(w => Math.max(1, w - 1))} disabled={selectedWeek <= 1}>
                <ChevronLeft className="h-4 w-4" />
              </Button>
              <span className="text-sm font-semibold min-w-[60px] text-center">Week {selectedWeek}</span>
              <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => setSelectedWeek(w => Math.min(weeklyMatchups.length, w + 1))} disabled={selectedWeek >= weeklyMatchups.length}>
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>

            {matchup && (
              <div className="flex items-center gap-2">
                <span className="text-xs text-muted-foreground">vs</span>
                <TooltipProvider>
                  <Tooltip>
                    <TooltipTrigger>
                      <span className="text-sm font-bold">{matchup.opponent}</span>
                    </TooltipTrigger>
                    <TooltipContent><p>{matchup.opponentFull}</p></TooltipContent>
                  </Tooltip>
                </TooltipProvider>
                {isPastWeek || selectedWeek === currentWeek ? (
                  <div className="flex items-center gap-2">
                    <span className="text-sm text-muted-foreground">{matchup.score.mine} – {matchup.score.theirs}</span>
                    <Badge variant="outline" className={`text-xs font-bold px-2 py-0.5 ${matchup.result === "W" ? "border-success text-success bg-success/10" : "border-destructive text-destructive bg-destructive/10"}`}>
                      {matchup.result}
                    </Badge>
                  </div>
                ) : (
                  <span className="text-xs text-muted-foreground">Upcoming</span>
                )}
              </div>
            )}

            <div className="flex-1" />

            {/* Highlight indicator */}
            {highlightedPlayer && (
              <div className="flex items-center gap-2 px-3 py-1 rounded-lg bg-success/10 border border-success/30">
                <span className="text-[10px] font-semibold text-success">
                  {highlightedPlayer.name} selected — click another player's position to swap
                </span>
                <button
                  onClick={() => setHighlightedPlayerId(null)}
                  className="text-success hover:text-success/70 text-xs font-bold"
                >
                  ✕
                </button>
              </div>
            )}

            <Select value={viewFilter} onValueChange={(v) => setViewFilter(v as ViewFilter)}>
              <SelectTrigger className="w-[180px] h-8 text-xs bg-secondary border-border">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="season">Season Stats</SelectItem>
                <SelectItem value="cap-hit">Cap Hit</SelectItem>
                <SelectItem value="1d">Last 1 Day</SelectItem>
                <SelectItem value="7d">Last 7 Days</SelectItem>
                <SelectItem value="14d">Last 14 Days</SelectItem>
                <SelectItem value="30d">Last 30 Days</SelectItem>
                <SelectItem value="60d">Last 60 Days</SelectItem>
                <SelectItem value="100d">Last 100 Days</SelectItem>
                <SelectItem value="fantasy-points">Fantasy Points</SelectItem>
                <SelectItem value="matchup-schedule">Matchup Schedule</SelectItem>
                <SelectItem value="full-schedule">Full Schedule</SelectItem>
              </SelectContent>
            </Select>

            {/* Iter 185 — Global timeframe for the per-section
                "Avg fpts/g" summary. Independent from the table
                column filter above so owners can mix Cap Hit /
                Season Stats columns with Last 7 Days section
                analytics. Per-section overrides live inside each
                SectionGroup's expanded summary row. */}
            <Select value={sectionTimeframe} onValueChange={(v) => setSectionTimeframe(v)}>
              <SelectTrigger
                className="w-[170px] h-8 text-xs bg-secondary border-border"
                data-testid="section-summary-timeframe-select"
              >
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="season">Summary: Season</SelectItem>
                <SelectItem value="7d">Summary: Last 7 Days</SelectItem>
                <SelectItem value="14d">Summary: Last 14 Days</SelectItem>
                <SelectItem value="30d">Summary: Last 30 Days</SelectItem>
                <SelectItem value="60d">Summary: Last 60 Days</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>

        {/* ── Header ── */}
        <div className="p-6 pb-0 border-b border-border">
          <div className="flex items-center justify-between pb-4">
            <div className="flex items-center gap-3">
              <h3 className="text-lg font-semibold">Team Roster</h3>
              {commissionerMode && (
                <Badge variant="outline" className="border-primary text-primary bg-primary/10 text-[10px] font-bold">
                  COMMISSIONER EDIT MODE
                </Badge>
              )}
              {isOwnTeam && isRosterLocked && emergencyChangesAllowed > 0 && (
                <TooltipProvider>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Badge
                        variant="outline"
                        className={`text-[10px] font-bold ${
                          emergencyChangesRemaining > 0
                            ? "border-amber-500/50 text-amber-400 bg-amber-500/10"
                            : "border-destructive/50 text-destructive bg-destructive/10"
                        }`}
                      >
                        <AlertTriangle className="h-3 w-3 mr-1" />
                        {emergencyChangesRemaining} / {emergencyChangesAllowed} Emergency Changes
                      </Badge>
                    </TooltipTrigger>
                    <TooltipContent className="max-w-[240px]">
                      <p className="text-xs">
                        {emergencyChangesRemaining > 0
                          ? "Roster is locked. You can use an emergency change to swap a starting player with a bench player. Points already earned by the swapped-out player still count."
                          : "No emergency roster changes remaining this season."}
                      </p>
                    </TooltipContent>
                  </Tooltip>
                </TooltipProvider>
              )}

              {/* Iter 187 — Column Settings Cog extracted */}
              <RosterColumnSettings
                visibleColumns={visibleColumns}
                setVisibleColumns={setVisibleColumns}
                showPositionEligibility={showPositionEligibility}
                setShowPositionEligibility={setShowPositionEligibility}
              />
            </div>
            <span className="text-xs text-muted-foreground bg-secondary px-2 py-1 rounded-full">
              {players.length} Players
            </span>
          </div>
        </div>

        {/* ── Table ── */}
        {effectiveFilter === "full-schedule" ? (
          <FullScheduleTable sectionTimeframe={sectionTimeframe} grouped={grouped} onTrade={handleOpenTrade} onPlayerClick={handleOpenCard} isOwnTeam={isOwnTeam} commissionerMode={commissionerMode} highlightedPlayerId={highlightedPlayerId} highlightedPositions={highlightedPositions} onToggleHighlight={handleToggleHighlight} onMoveToSection={handleMoveToSection} sectionCounts={currentSectionCounts} showPositionEligibility={showPositionEligibility} />
        ) : effectiveFilter === "matchup-schedule" ? (
          <MatchupScheduleTable sectionTimeframe={sectionTimeframe} grouped={grouped} onTrade={handleOpenTrade} onPlayerClick={handleOpenCard} isOwnTeam={isOwnTeam} commissionerMode={commissionerMode} highlightedPlayerId={highlightedPlayerId} highlightedPositions={highlightedPositions} onToggleHighlight={handleToggleHighlight} onMoveToSection={handleMoveToSection} sectionCounts={currentSectionCounts} showPositionEligibility={showPositionEligibility} />
        ) : effectiveFilter === "fantasy-points" ? (
          <FantasyPointsTable sectionTimeframe={sectionTimeframe} grouped={grouped} onTrade={handleOpenTrade} getSectionTotal={getSectionTotal} onPlayerClick={handleOpenCard} isOwnTeam={isOwnTeam} commissionerMode={commissionerMode} highlightedPlayerId={highlightedPlayerId} highlightedPositions={highlightedPositions} onToggleHighlight={handleToggleHighlight} onMoveToSection={handleMoveToSection} sectionCounts={currentSectionCounts} visibleCategories={filteredStatCategories} showFpts={showFpts} showPositionEligibility={showPositionEligibility} scoringConfig={scoringConfig} />
        ) : effectiveFilter === "cap-hit" ? (
          <CapHitTable sectionTimeframe={sectionTimeframe} grouped={grouped} onPlayerClick={handleOpenCard} />
        ) : (
          <StatsTable
            grouped={grouped}
            onTrade={handleOpenTrade}
            onDrop={onDropPlayer}
            onMegaphone={onAddToTradeBlock}
            tradeBlockPlayerIds={tradeBlockPlayerIds}
            onToggleProtection={onToggleProtection}
            protectedPlayerIds={protectedPlayerIds}
            protectionEnabled={protectionEnabled}
            protectionDraftType={protectionDraftType}
            ownershipMap={ownershipMap}
            newsMap={newsMap}
            onPlayerClick={handleOpenCard}
            getPlayerPoints={getPlayerPoints}
            getSectionTotal={getSectionTotal}
            filterLabel={filterLabels[effectiveFilter]}
            isOwnTeam={isOwnTeam}
            commissionerMode={commissionerMode}
            highlightedPlayerId={highlightedPlayerId}
            highlightedPositions={highlightedPositions}
            onToggleHighlight={handleToggleHighlight}
            onMoveToSection={handleMoveToSection}
            sectionCounts={currentSectionCounts}
            visibleCategories={filteredStatCategories}
            showFpts={showFpts}
            showPositionEligibility={showPositionEligibility}
            lineupWarnings={lineupWarnings}
            sectionTimeframe={sectionTimeframe}
          />
        )}
      </div>

      {selectedPlayer && (
        <PlayerTradeModal
          open={tradeModalOpen}
          onOpenChange={setTradeModalOpen}
          initialPlayer={selectedPlayer}
          allPlayers={players}
        />
      )}

      {cardPlayer && (
        <PlayerCardModal
          open={cardOpen}
          onOpenChange={setCardOpen}
          player={cardPlayer}
          scoringConfig={scoringConfig}
        />
      )}
    </>
    </SharedRosterConfigContext.Provider>
  );
};

// ── Highlight props shared across tables ───────────────

// ── HighlightProps + helpers moved to internals.tsx ────
// Iter 185 — `HighlightProps`, `isPositionHighlighted`,
// `findHighlightedPlayer`, `shouldShowOpenSlotForSection` all live
// in `./player-roster/internals` now. Re-exported below so any
// downstream consumer that historically imported them off
// PlayerRoster.tsx keeps working.
export type { HighlightProps } from "./player-roster/internals";
export { isPositionHighlighted, findHighlightedPlayer, shouldShowOpenSlotForSection } from "./player-roster/internals";

// ── Stats Table (default, season, time-range) ──────────

// ── Iter 183 — Sub-components moved to ./player-roster/sub-components.tsx
//    Re-exported here so existing imports of these from PlayerRoster.tsx
//    keep working (the file's surface area is unchanged from a consumer
//    perspective). Risks noted: cross-file cycle is deliberate and safe
//    because module-init never dereferences these names — only the
//    React render tree does.
export {
  StatsTable,
  CapHitTable,
  FantasyPointsTable,
  MatchupScheduleTable,
  FullScheduleTable,
  SectionGroup,
  EmptySlotRow,
  OpenSlotRow,
  PlayerRow,
  TradeButton,
  MegaphoneButton,
  DropButton,
  OwnershipCell,
} from "./player-roster/sub-components";

export default PlayerRoster;
