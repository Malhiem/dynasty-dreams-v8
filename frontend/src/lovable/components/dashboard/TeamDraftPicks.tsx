// @ts-nocheck
import { useMemo, useState, useEffect } from "react";
import { ArrowRightLeft, Plus, ArrowUpDown } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import type { TradeDraftPick } from "@/lovable/components/trade/TradeBuilder";
import api from "@/lib/api";
import PickProvenance from "@/lovable/pages/draftroom/PickProvenance";
// Iter 170j — Live refresh on draft undo / swap. The Roster page mounts
// this card; subscribing to the active draft room means commissioner
// rollbacks/swaps reflect on the Future Draft Picks card instantly.
import { useSocket } from "@/hooks/use-socket";
import { useAuth } from "@/contexts/AuthContext";

interface TradeContext {
  date: string;
  sentPlayers: string[];
  receivedPlayers: string[];
  summary: string;
}

interface DraftPick {
  year: number;
  round: number;
  originalTeam: string | null; // null = own pick
  originalTeamFull: string | null;
  tradeContext?: TradeContext;
}

const frostbitePicks: DraftPick[] = [
  { year: 2025, round: 1, originalTeam: null, originalTeamFull: null },
  { year: 2025, round: 1, originalTeam: "IB", originalTeamFull: "Ice Breakers", tradeContext: { date: "Nov 12, 2024", sentPlayers: ["M. Tkachuk"], receivedPlayers: ["J. Huberdeau", "2025 1st (IB)"], summary: "Traded M. Tkachuk for J. Huberdeau and a 1st round pick" } },
  { year: 2025, round: 2, originalTeam: null, originalTeamFull: null },
  { year: 2025, round: 3, originalTeam: null, originalTeamFull: null },
  { year: 2025, round: 4, originalTeam: "FZ", originalTeamFull: "Frost Zone", tradeContext: { date: "Jan 3, 2025", sentPlayers: ["D. Strome"], receivedPlayers: ["2025 4th (FZ)"], summary: "Traded D. Strome for a 4th round pick" } },
  { year: 2026, round: 1, originalTeam: null, originalTeamFull: null },
  { year: 2026, round: 2, originalTeam: null, originalTeamFull: null },
  { year: 2026, round: 3, originalTeam: null, originalTeamFull: null },
  { year: 2027, round: 1, originalTeam: null, originalTeamFull: null },
  { year: 2027, round: 2, originalTeam: "WC", originalTeamFull: "Winter Capitals", tradeContext: { date: "Oct 28, 2024", sentPlayers: ["B. Marchand"], receivedPlayers: ["A. Svechnikov", "2027 2nd (WC)"], summary: "Traded B. Marchand for A. Svechnikov and a 2nd round pick" } },
  { year: 2027, round: 3, originalTeam: null, originalTeamFull: null },
];

const tradedFromTeams = [
  { abbr: "IB", full: "Ice Breakers" },
  { abbr: "FZ", full: "Frost Zone" },
  { abbr: "WC", full: "Winter Capitals" },
  { abbr: "SC", full: "Snow Cats" },
  { abbr: "FB", full: "Frostbite" },
  { abbr: "AW", full: "Arctic Wolves" },
];

const seededRand = (seed: number) => {
  let s = seed;
  return () => {
    s = (s * 1103515245 + 12345) & 0x7fffffff;
    return s / 0x7fffffff;
  };
};

const generateTeamPicks = (teamId: string): DraftPick[] => {
  if (teamId === "frostbite") return frostbitePicks;

  let seed = 0;
  for (let i = 0; i < teamId.length; i++) seed += teamId.charCodeAt(i) * (i + 1);
  const rand = seededRand(seed);

  const picks: DraftPick[] = [];
  const years = [2025, 2026, 2027];

  for (const year of years) {
    const numRounds = Math.floor(rand() * 3) + 2; // 2-4 rounds
    for (let round = 1; round <= numRounds; round++) {
      const hasTraded = rand() > 0.7;
      if (hasTraded) {
        const from = tradedFromTeams[Math.floor(rand() * tradedFromTeams.length)];
        picks.push({ year, round, originalTeam: from.abbr, originalTeamFull: from.full });
      } else {
        picks.push({ year, round, originalTeam: null, originalTeamFull: null });
      }
    }
  }
  return picks;
};

const pickValues: Record<number, number> = { 1: 3500, 2: 2000, 3: 1200, 4: 800 };

interface TeamDraftPicksProps {
  onTradePick?: (pick: TradeDraftPick) => void;
  isOwnTeam?: boolean;
  currentTeamContext?: string;
  teamId?: string;
  // Iter 170j — Optional league id; when present, this card subscribes
  // to the active draft socket room and refetches itself on every
  // commissioner undo / swap broadcast.
  leagueId?: string;
}

const TeamDraftPicks = ({ onTradePick, isOwnTeam = true, currentTeamContext = "mine", teamId = "frostbite", leagueId }: TeamDraftPicksProps) => {
  // Iter 166 — when `teamId` looks like a real Mongo ObjectId (24 hex
  // chars) fetch the live `/api/teams/{id}/draft-picks` payload and
  // hydrate `draftPicks` from that. Falls back to the seeded mock
  // generator when no live data is available (e.g. demo / story mode).
  const looksLikeObjectId = typeof teamId === "string" && /^[a-f0-9]{24}$/.test(teamId);
  const [livePicks, setLivePicks] = useState<DraftPick[] | null>(null);
  const [liveRawByKey, setLiveRawByKey] = useState<Record<string, any>>({});
  // Iter 170j — bump to force a refetch (driven by socket events).
  const [reloadTick, setReloadTick] = useState(0);
  const { user } = useAuth();

  // Iter 170j — Resolve the active draft id for the league so we can
  // subscribe to its socket room (commissioner undo/swap broadcasts).
  const [activeDraftId, setActiveDraftId] = useState<string | null>(null);
  useEffect(() => {
    if (!leagueId) { setActiveDraftId(null); return; }
    let cancelled = false;
    api.get(`/drafts?league_id=${leagueId}`)
      .then(({ data }) => {
        if (cancelled) return;
        const drafts = Array.isArray(data) ? data : (data?.drafts || []);
        if (drafts.length === 0) { setActiveDraftId(null); return; }
        const sorted = [...drafts].sort((a: any, b: any) => (b.created_at || "").localeCompare(a.created_at || ""));
        setActiveDraftId(String(sorted[0]._id || sorted[0].id));
      })
      .catch(() => { if (!cancelled) setActiveDraftId(null); });
    return () => { cancelled = true; };
  }, [leagueId]);

  useSocket(
    activeDraftId ? `draft_${activeDraftId}` : null,
    {
      draft_undo: () => setReloadTick((t) => t + 1),
      draft_pick_swapped: () => setReloadTick((t) => t + 1),
      draft_pick: () => setReloadTick((t) => t + 1),
      // Iter 228q — Also refresh when a commissioner edits the draft
      // (e.g. changes total_rounds) so the per-team pick count + the
      // section labels stay in sync with the Draft Board.
      draft_edited: () => setReloadTick((t) => t + 1),
    },
    user?.id || user?._id,
  );

  // Iter 228q — Subscribe to the league-wide channel too so edits to
  // ANY draft in the league (not just the most-recent one resolved
  // above) refresh the Roster Draft Picks card. Backend mirrors every
  // `draft_edited` emission to both `draft_{id}` and `league_{id}`.
  useSocket(
    leagueId ? `league_${leagueId}` : null,
    {
      draft_edited: () => setReloadTick((t) => t + 1),
      draft_picks_seeded: () => setReloadTick((t) => t + 1),
    },
    user?.id || user?._id,
  );

  useEffect(() => {
    if (!looksLikeObjectId) { setLivePicks(null); setLiveRawByKey({}); return; }
    api.get(`/teams/${teamId}/draft-picks`)
      .then((res) => {
        const picks = (res.data?.picks || []) as any[];
        // Map raw picks for provenance lookup
        const raw: Record<string, any> = {};
        const hydrated: DraftPick[] = picks.map((p) => {
          const traded = (p.trade_history || []).length > 0;
          const key = `${p.year}-${p.round}-${p._id || p.id}`;
          raw[key] = p;
          return {
            year: p.year,
            round: p.round,
            originalTeam: traded
              ? (p.original_team_name || "").split(" ").map((w: string) => w[0] || "").join("").toUpperCase().slice(0, 3)
              : null,
            originalTeamFull: traded ? p.original_team_name : null,
            _liveKey: key,
            _isConditional: (p.pending_protections || []).length > 0,
            // Iter 228o — Parent draft metadata so the Roster page can
            // section picks by draft (e.g. "TFHL Inaugural Draft") not
            // just by calendar year. Iter 228s — also carry the
            // scheduled_time so groups sort chronologically.
            _draftId: p.draft_id || null,
            _draftName: p.draft_name || null,
            _draftScheduledTime: p.draft_scheduled_time || null,
          } as any;
        });
        setLivePicks(hydrated);
        setLiveRawByKey(raw);
      })
      .catch(() => { setLivePicks(null); setLiveRawByKey({}); });
  }, [teamId, looksLikeObjectId, reloadTick]);

  const draftPicks = useMemo(() => {
    if (livePicks !== null) return livePicks;
    return generateTeamPicks(teamId);
  }, [livePicks, teamId]);

  // Iter 228t — Toggle "trade-add mode" per section. Default OFF: only
  // the section's trade icon is visible. Click the icon → all per-pick
  // "+ Add" buttons in THAT section appear so users can add picks one
  // at a time. Click again to exit. Tracked by group key so each
  // section toggles independently.
  const [tradeModeKeys, setTradeModeKeys] = useState<Record<string, boolean>>({});
  const toggleTradeMode = (key: string) =>
    setTradeModeKeys((prev) => ({ ...prev, [key]: !prev[key] }));

  // Iter 228o — Build the ordered list of section groups. Live picks
  // section by parent draft (preferring an explicit `_draftId` / `_draftName`
  // from the backend); mocked/seeded picks fall back to year groupings.
  // Iter 228s — Sort chronologically by the parent draft's
  // `scheduled_time` (soonest first) so a 55-pick Inaugural in May
  // shows above a 4-pick Summer Entry in July and a 2-pick Winter
  // draft in December.
  const sectionGroups = useMemo(() => {
    type Group = { key: string; label: string; picks: DraftPick[]; year: number; scheduledTime: string | null };
    const groups: Group[] = [];
    const indexByKey: Record<string, number> = {};
    for (const p of draftPicks) {
      const draftId = (p as any)._draftId as string | null;
      const draftName = (p as any)._draftName as string | null;
      const draftSched = (p as any)._draftScheduledTime as string | null;
      const key = draftId || draftName || `year-${p.year}`;
      const label = draftName || `${p.year} Draft`;
      let idx = indexByKey[key];
      if (idx === undefined) {
        idx = groups.length;
        indexByKey[key] = idx;
        groups.push({ key, label, picks: [], year: p.year, scheduledTime: draftSched });
      }
      groups[idx].picks.push(p);
    }
    groups.sort((a, b) => {
      const ta = a.scheduledTime ? new Date(a.scheduledTime).getTime() : Number.POSITIVE_INFINITY;
      const tb = b.scheduledTime ? new Date(b.scheduledTime).getTime() : Number.POSITIVE_INFINITY;
      if (ta !== tb) return ta - tb;          // soonest first
      if (a.year !== b.year) return a.year - b.year;
      return a.label.localeCompare(b.label);  // stable
    });
    return groups;
  }, [draftPicks]);

  const handleTradePick = (pick: DraftPick, index: number) => {
    if (!onTradePick) return;
    const tradePick: TradeDraftPick = {
      id: `${teamId}-${pick.year}-${pick.round}-${index}`,
      year: pick.year,
      round: pick.round,
      originalTeam: pick.originalTeam,
      originalTeamFull: pick.originalTeamFull,
      fromTeam: currentTeamContext,
      value: pickValues[pick.round] ?? 500,
      // Iter 228u — Differentiator so the Trade Builder can label a
      // "2026 Rd 2 (Inaugural)" pick differently from a "2026 Rd 2
      // (Entry)" pick when both come from the same year but different
      // parent drafts. Falls back to `_draftId` when no human name.
      draftId: (pick as any)._draftId ?? undefined,
      draftName: (pick as any)._draftName ?? undefined,
    };
    onTradePick(tradePick);
  };

  return (
    <div className="stat-card p-0 overflow-hidden">
      <div className="p-6 border-b border-border">
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-semibold">Draft Picks</h3>
          <span className="text-xs bg-accent/20 text-accent font-medium px-2 py-1 rounded-full">
            {draftPicks.length} Picks
          </span>
        </div>
      </div>

      <div className="p-6 space-y-5">
        {sectionGroups.map((group, gi) => {
          const picks = group.picks;
          return (
            <div key={group.key} className="animate-slide-up" style={{ animationDelay: `${gi * 80}ms` }}>
              <div className="flex items-center gap-2 mb-3">
                <div className="flex items-baseline gap-2">
                  <span
                    className="text-sm font-semibold text-foreground"
                    data-testid={`roster-draft-section-${group.key}`}
                  >{group.label}</span>
                  {/* Iter 228t — Date/time beside the title in smaller
                      muted font so users can identify the draft by its
                      schedule at a glance. */}
                  {group.scheduledTime && (
                    <span
                      className="text-[10px] text-muted-foreground"
                      data-testid={`roster-draft-section-when-${group.key}`}
                    >
                      {(() => {
                        try {
                          return new Date(group.scheduledTime).toLocaleString(undefined, {
                            month: "short", day: "numeric", year: "numeric",
                            hour: "numeric", minute: "2-digit",
                          });
                        } catch { return group.scheduledTime; }
                      })()}
                    </span>
                  )}
                </div>
                <span
                  className="text-[10px] uppercase tracking-wider bg-secondary/70 text-muted-foreground px-1.5 py-0.5 rounded"
                  data-testid={`roster-draft-section-count-${group.key}`}
                >{picks.length} pick{picks.length === 1 ? "" : "s"}</span>
                <div className="flex-1 h-px bg-border" />
                {/* Iter 228t — Trade-mode toggle icon. Off by default
                    (per-pick "+ Add" buttons hidden); clicking enters
                    "selecting picks" mode and reveals the per-pick
                    Add buttons in this section only. */}
                {onTradePick && (
                  <TooltipProvider>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <button
                          type="button"
                          onClick={() => toggleTradeMode(group.key)}
                          className={`inline-flex items-center justify-center h-6 w-6 rounded transition-colors ${
                            tradeModeKeys[group.key]
                              ? "bg-primary/20 text-primary border border-primary/50"
                              : "text-muted-foreground hover:text-primary hover:bg-primary/10"
                          }`}
                          data-testid={`roster-draft-section-trade-toggle-${group.key}`}
                          aria-pressed={!!tradeModeKeys[group.key]}
                          aria-label={tradeModeKeys[group.key]
                            ? `Done selecting picks from ${group.label}`
                            : `Select picks from ${group.label} to trade`
                          }
                        >
                          <ArrowUpDown className="h-3.5 w-3.5" />
                        </button>
                      </TooltipTrigger>
                      <TooltipContent>
                        <p className="text-xs">{tradeModeKeys[group.key]
                          ? "Done — collapse Add buttons"
                          : "Select picks from this draft to trade"
                        }</p>
                      </TooltipContent>
                    </Tooltip>
                  </TooltipProvider>
                )}
              </div>
              <div className="flex flex-wrap gap-2">
                {picks.map((pick, pi) => (
                  <div
                    key={`${group.key}-${pick.round}-${pi}`}
                    className={`group flex items-center gap-1 px-3 py-2 rounded-lg border text-sm transition-all hover:border-primary/30 ${
                      pick.round === 1
                        ? "bg-accent/10 border-accent/30"
                        : "bg-secondary/50 border-border"
                    }`}
                  >
                    <span className={`font-semibold ${pick.round === 1 ? "text-accent" : "text-foreground"}`}>
                      Rd {pick.round}
                    </span>
                    {/* Iter 169 — conditional-pick asterisk on the Roster page */}
                    {(pick as any)._isConditional && (() => {
                      const live = (pick as any)._liveKey ? liveRawByKey[(pick as any)._liveKey] : null;
                      const protections = (live?.pending_protections || []) as any[];
                      return (
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <span
                              className="text-amber-400 font-bold cursor-help ml-0.5"
                              data-testid={`roster-pick-conditional-${pick.year}-${pick.round}`}
                            >*</span>
                          </TooltipTrigger>
                          <TooltipContent className="max-w-sm">
                            <div className="space-y-1 text-xs">
                              <p className="font-semibold">Conditional protection — locked from re-trade</p>
                              {protections.map((c: any, idx: number) => (
                                <p key={idx} className="text-muted-foreground">
                                  {c.description || `${c.subject_type} ${c.metric} ${c.operator} ${c.threshold}`}
                                </p>
                              ))}
                            </div>
                          </TooltipContent>
                        </Tooltip>
                      );
                    })()}
                    {pick.originalTeam && (
                      <ArrowRightLeft className="h-3 w-3 text-sky-400 ml-0.5" data-testid={`roster-pick-traded-${pick.year}-${pick.round}`} />
                    )}
                    {pick.originalTeam && (
                      <TooltipProvider>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <span className="ml-1 text-xs text-primary cursor-help font-medium">
                              ({pick.originalTeam})
                            </span>
                          </TooltipTrigger>
                          <TooltipContent side="top" className="max-w-[320px] p-3 space-y-2">
                            <p className="font-semibold text-sm">via {pick.originalTeamFull}</p>
                            {(() => {
                              const live = (pick as any)._liveKey ? liveRawByKey[(pick as any)._liveKey] : null;
                              const history = live?.trade_history || [];
                              if (history.length > 0) {
                                return (
                                  <>
                                    <div className="h-px bg-border" />
                                    <PickProvenance tradeHistory={history} />
                                  </>
                                );
                              }
                              if (pick.tradeContext) {
                                return (
                                  <>
                                    <div className="h-px bg-border" />
                                    <p className="text-xs text-muted-foreground">{pick.tradeContext.summary}</p>
                                    <div className="flex flex-col gap-1 text-xs">
                                      <div>
                                        <span className="text-destructive font-medium">Sent: </span>
                                        <span className="text-foreground">{pick.tradeContext.sentPlayers.join(", ")}</span>
                                      </div>
                                      <div>
                                        <span className="text-accent font-medium">Received: </span>
                                        <span className="text-foreground">{pick.tradeContext.receivedPlayers.join(", ")}</span>
                                      </div>
                                    </div>
                                    <div className="h-px bg-border" />
                                    <p className="text-[11px] text-muted-foreground">Trade date: {pick.tradeContext.date}</p>
                                  </>
                                );
                              }
                              return <p className="text-xs text-muted-foreground">Acquired via trade</p>;
                            })()}
                          </TooltipContent>
                        </Tooltip>
                      </TooltipProvider>
                    )}
                    {onTradePick && tradeModeKeys[group.key] && (
                      <TooltipProvider>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <button
                              className="ml-1.5 inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wider border border-primary/40 text-primary hover:bg-primary/10 transition-colors"
                              onClick={() => handleTradePick(pick, gi * 100 + pi)}
                              data-testid={`roster-pick-add-${pick.year}-${pick.round}-${pi}`}
                              aria-label={`Add ${group.label} round ${pick.round} pick to trade`}
                            >
                              <Plus className="h-3 w-3" />
                              Add
                            </button>
                          </TooltipTrigger>
                          <TooltipContent>
                            <p className="text-xs">Add this pick to the pending trade</p>
                          </TooltipContent>
                        </Tooltip>
                      </TooltipProvider>
                    )}
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default TeamDraftPicks;