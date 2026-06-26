// @ts-nocheck
import { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/lib/api";
import TeamLogo from "@/lovable/components/TeamLogo";
import { Trophy, Crown, ChevronRight, Award } from "lucide-react";
import { useActiveLeague } from "@/hooks/use-active-league";
import { useAuth } from "@/contexts/AuthContext";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";

interface BracketTeam {
  team_id: string;
  team_name: string;
  team_abbr?: string | null;
  team_logo_url?: string | null;
  owner_name?: string;
  seed: number;
  wins?: number;
  losses?: number;
  ties?: number;
  points_for?: number;
  games_back?: number;
}

interface Matchup {
  matchup_id?: string | null;
  high_seed: BracketTeam | null;
  low_seed: BracketTeam | null;
  projected_winner?: string | null;
  status?: string;
  home_score?: number;
  away_score?: number;
  week?: number;
  home_team_id?: string | null;
  away_team_id?: string | null;
  is_synthetic?: boolean;
}

interface Round {
  name: string;
  matchups: Matchup[];
  byes?: BracketTeam[];
  length_weeks?: number;
}

interface ConsolationBracket {
  size: number;
  seeding_method?: string;
  seeds: BracketTeam[];
  rounds: Round[];
}

interface ChampionBlock {
  decided: boolean;
  champion?: { team_id: string; team_name?: string; team_abbr?: string | null; owner_name?: string } | null;
  runner_up?: { team_id: string; team_name?: string; team_abbr?: string | null; owner_name?: string } | null;
  final_matchup_id?: string | null;
  distributed?: boolean;
  champion_prize?: number;
  runner_up_prize?: number;
  consolation_prize?: number;
  currency?: string;
  distributed_at?: string;
  note?: string;
  consolation_champion?: { team_id: string; team_name?: string; team_abbr?: string | null } | null;
}

interface BracketData {
  league_id: string;
  playoff_size: number;
  playoff_teams: BracketTeam[];
  bye_teams: BracketTeam[];
  rounds: Round[];
  status: string;
  playoff_week_lengths?: Record<string, { length_weeks: number }>;
  consolation_enabled?: boolean;
  consolation_bracket?: ConsolationBracket | null;
  champion?: ChampionBlock | null;
}

const SEED_COLOR = [
  "text-accent",
  "text-primary",
  "text-success",
  "text-foreground",
  "text-muted-foreground",
  "text-muted-foreground",
  "text-muted-foreground",
  "text-muted-foreground",
];

/**
 * Iter 198 — Base vertical slot height for round 0 matchups. Subsequent
 * rounds double this so each higher-round matchup is centered between
 * the two feeders below it (classic single-elimination bracket layout).
 * Tuned to comfortably fit a 2-team card (h-[56px] × 2 + gap + scores +
 * mark-winner buttons ≈ 175px) without forcing visual overlap.
 */
const BRACKET_SLOT_H = 180;

const TeamCard = ({ team, isWinner, isLoser, tbdLabel }: { team: BracketTeam | null; isWinner?: boolean; isLoser?: boolean; tbdLabel?: string }) => {
  if (!team) {
    return (
      <div
        className="border border-dashed border-border rounded-md p-3 h-[56px] flex items-center gap-2 text-muted-foreground/60 text-xs italic"
        data-testid="bracket-tbd-slot"
      >
        {tbdLabel ? (
          <span className="truncate text-foreground/70 not-italic">{tbdLabel}</span>
        ) : (
          <span>TBD</span>
        )}
      </div>
    );
  }
  return (
    <div
      className={`flex items-center gap-2 rounded-md px-2.5 py-2 border transition-colors h-[56px] ${
        isWinner
          ? "border-accent/60 bg-accent/10"
          : isLoser
          ? "border-border/40 bg-secondary/10 opacity-60"
          : "border-border bg-secondary/30"
      }`}
      data-testid={`bracket-team-${team.team_id}`}
    >
      <span className={`text-xs font-bold w-5 text-center ${SEED_COLOR[team.seed - 1] || "text-muted-foreground"}`}>
        {team.seed}
      </span>
      <TeamLogo logo={team.team_logo_url} name={team.team_name} abbr={team.team_abbr} size="xs" />
      <div className="flex-1 min-w-0">
        <div className={`text-sm truncate ${isWinner ? "font-semibold text-foreground" : "text-foreground"}`}>
          {team.team_name}
          {isWinner && <Crown className="inline-block h-3.5 w-3.5 ml-1 text-accent" />}
        </div>
        <div className="text-[10px] text-muted-foreground leading-tight">
          {team.wins ?? 0}-{team.losses ?? 0}{team.ties ? `-${team.ties}` : ""} · {team.points_for ?? 0} PF
        </div>
      </div>
    </div>
  );
};

const MatchupCard = ({ mu, status, canMark, onMarkWinner }: {
  mu: Matchup;
  status: string;
  canMark?: boolean;
  onMarkWinner?: (matchupId: string, teamId: string) => void;
}) => {
  const hs = mu.high_seed;
  const ls = mu.low_seed;
  const winnerId = mu.projected_winner;
  const isFinal = mu.status === "completed" || mu.status === "final";
  const hsWin = hs && winnerId === hs.team_id && isFinal;
  const lsWin = ls && winnerId === ls.team_id && isFinal;
  const hasScore = typeof mu.home_score === "number" && typeof mu.away_score === "number" && (mu.home_score || mu.away_score);
  // Iter 107: surface "Winner of X vs Y" auto-labels for TBD slots
  const hsLabel = (mu as any).high_seed_label;
  const lsLabel = (mu as any).low_seed_label;
  const showMarkAction = !!canMark && !!mu.matchup_id && hs && ls && !isFinal && !mu.is_synthetic;
  return (
    <div className="stat-card p-2.5 space-y-1.5" data-testid="bracket-matchup">
      <TeamCard
        team={hs}
        isWinner={!!hsWin || (status === "projected" && hs && winnerId === hs.team_id)}
        isLoser={!!lsWin}
        tbdLabel={hsLabel}
      />
      <TeamCard
        team={ls}
        isWinner={!!lsWin}
        isLoser={!!hsWin || (status === "projected" && hs && winnerId === hs.team_id)}
        tbdLabel={lsLabel}
      />
      {hasScore && (
        <div className="text-[10px] text-center text-muted-foreground pt-0.5">
          {mu.home_score} - {mu.away_score}
          {mu.week && <span className="ml-1.5 opacity-70">· Wk {mu.week}</span>}
        </div>
      )}
      {!hasScore && status === "projected" && hs && ls && (
        <div className="text-[10px] text-center text-muted-foreground pt-0.5 italic">
          Projected: {hs.team_abbr || hs.team_name.slice(0, 3).toUpperCase()} advances
        </div>
      )}
      {showMarkAction && (
        <div
          className="flex items-center gap-1 pt-1 border-t border-border/40"
          data-testid={`mark-winner-actions-${mu.matchup_id}`}
        >
          <button
            type="button"
            onClick={() => onMarkWinner!(mu.matchup_id!, hs!.team_id)}
            className="flex-1 text-[10px] font-semibold uppercase tracking-wider py-1 rounded-md bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 hover:bg-emerald-500/25 transition-colors"
            data-testid={`mark-winner-high-${mu.matchup_id}`}
          >
            ✓ {hs!.team_abbr || hs!.team_name.slice(0, 6)}
          </button>
          <button
            type="button"
            onClick={() => onMarkWinner!(mu.matchup_id!, ls!.team_id)}
            className="flex-1 text-[10px] font-semibold uppercase tracking-wider py-1 rounded-md bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 hover:bg-emerald-500/25 transition-colors"
            data-testid={`mark-winner-low-${mu.matchup_id}`}
          >
            ✓ {ls!.team_abbr || ls!.team_name.slice(0, 6)}
          </button>
        </div>
      )}
    </div>
  );
};

const RoundsGrid = ({ rounds, status, testidPrefix = "bracket", canMark, onMarkWinner }: {
  rounds: Round[];
  status: string;
  testidPrefix?: string;
  canMark?: boolean;
  onMarkWinner?: (matchupId: string, teamId: string) => void;
}) => (
  <div className="overflow-x-auto" data-testid={`${testidPrefix}-rounds`}>
    <div className="flex gap-4 min-w-max items-stretch">
      {rounds.map((rd, rdx) => (
        <div
          key={`${rd.name}-${rdx}`}
          className="flex-1 min-w-[260px] space-y-3"
          data-testid={`${testidPrefix}-round-${rdx}`}
        >
          <div className="flex items-center gap-2 flex-wrap">
            <h3 className="text-sm font-bold text-foreground uppercase tracking-wide">
              {rd.name}
            </h3>
            {rd.length_weeks && rd.length_weeks > 1 && (
              <span
                className="text-[10px] font-semibold px-1.5 py-0.5 rounded-full bg-cyan-500/15 text-cyan-300 border border-cyan-500/30"
                data-testid={`${testidPrefix}-round-${rdx}-length`}
              >
                {rd.length_weeks} weeks
              </span>
            )}
            {rdx < rounds.length - 1 && (
              <ChevronRight className="h-4 w-4 text-muted-foreground/40" />
            )}
          </div>
          {rd.byes && rd.byes.length > 0 && (
            <div className="space-y-1.5">
              <div className="text-[10px] uppercase tracking-wider text-muted-foreground/70 font-semibold">
                Byes to Semis
              </div>
              {rd.byes.map((t) => (
                <div
                  key={t.team_id}
                  className="flex items-center gap-2 rounded-md px-2.5 py-1.5 bg-accent/10 border border-accent/30"
                  data-testid={`${testidPrefix}-bye-${t.team_id}`}
                >
                  <span className="text-xs font-bold text-accent w-5 text-center">{t.seed}</span>
                  <TeamLogo logo={t.team_logo_url} name={t.team_name} abbr={t.team_abbr} size="xs" />
                  <span className="text-xs font-medium truncate">{t.team_name}</span>
                </div>
              ))}
            </div>
          )}
          <div className="flex flex-col">
            {rd.matchups.map((mu, i) => (
              <div
                key={i}
                className="flex items-center justify-center"
                style={{ height: `${BRACKET_SLOT_H * Math.pow(2, rdx)}px` }}
              >
                <div className="w-full">
                  <MatchupCard
                    mu={mu}
                    status={status}
                    canMark={canMark}
                    onMarkWinner={onMarkWinner}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  </div>
);

/**
 * Embeddable playoff tree view (no page chrome).
 * Used inside Standings → Playoffs tab.
 */
export const PlayoffBracketView = ({ leagueId }: { leagueId?: string | null }) => {
  const navigate = useNavigate();
  const { league: activeLeague } = useActiveLeague();
  const { user: currentUser } = useAuth();
  const [bracket, setBracket] = useState<BracketData | null>(null);
  const [loading, setLoading] = useState(true);
  const [showPrizeModal, setShowPrizeModal] = useState(false);

  const isCommish = (() => {
    if (!activeLeague || !currentUser) return false;
    const uid = String((currentUser as any)?.id || (currentUser as any)?._id || "");
    const ids = [
      activeLeague.commissioner_id,
      activeLeague.created_by,
      ...(activeLeague.co_commissioners || []),
      ...(activeLeague.commissioner_ids || []),
    ].filter(Boolean).map(String);
    return ids.includes(uid);
  })();

  const reload = useCallback(() => {
    if (!leagueId) return;
    api.get(`/leagues/${leagueId}/playoff-bracket`)
      .then(({ data }) => setBracket(data))
      .catch(() => {});
  }, [leagueId]);

  useEffect(() => {
    if (!leagueId) { setLoading(false); return; }
    let cancelled = false;
    setLoading(true);
    api.get(`/leagues/${leagueId}/playoff-bracket`)
      .then(({ data }) => { if (!cancelled) setBracket(data); })
      .catch(() => {})
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [leagueId]);

  const onMarkWinner = useCallback(async (matchupId: string, teamId: string) => {
    try {
      await api.post(`/leagues/${leagueId}/playoffs/mark-winner`, {
        matchup_id: matchupId,
        winner_team_id: teamId,
      });
      toast.success("Winner marked");
      reload();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Failed to mark winner");
    }
  }, [leagueId, reload]);

  if (loading) {
    return <div className="p-4 text-muted-foreground text-sm">Loading playoff tree...</div>;
  }

  if (!bracket || (bracket.rounds?.length || 0) === 0) {
    return (
      <div className="stat-card p-6 text-center" data-testid="playoff-bracket-empty">
        <Trophy className="h-8 w-8 text-muted-foreground/40 mx-auto mb-2" />
        <p className="text-sm text-muted-foreground">
          Not enough teams to generate a playoff bracket yet.
        </p>
      </div>
    );
  }

  const badgeColor = bracket.status === "actual"
    ? "bg-success/20 text-success border-success/30"
    : "bg-primary/15 text-primary border-primary/30";

  return (
    <div className="space-y-5" data-testid="playoff-bracket-page">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-2 flex-wrap">
          <Trophy className="h-5 w-5 text-accent" />
          <h2 className="text-lg font-bold text-foreground">
            Playoff Tree <span className="text-sm font-normal text-muted-foreground">· {bracket.playoff_size}-team bracket</span>
          </h2>
          {/* Iter 105: Surface seeding_method + playoff_format from the backend */}
          {bracket.playoff_format === "playoff_tree" && bracket.seeding_method && (
            <span
              className="text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded-full bg-violet-500/15 text-violet-300 border border-violet-500/30"
              data-testid="playoff-bracket-seeding-badge"
            >
              {bracket.seeding_method === "high_vs_low" && "1 vs N seeding"}
              {bracket.seeding_method === "adjacent" && "1 v 2 / 3 v 4 seeding"}
              {bracket.seeding_method === "custom" && "Custom ladder"}
            </span>
          )}
          {bracket.playoff_format === "h2h_matchup" && (
            <span
              className="text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded-full bg-cyan-500/15 text-cyan-300 border border-cyan-500/30"
              data-testid="playoff-bracket-format-badge"
            >
              H2H matchup mode
            </span>
          )}
        </div>
        <span
          className={`text-xs font-semibold px-2.5 py-1 rounded-full border ${badgeColor}`}
          data-testid="playoff-bracket-status"
        >
          {bracket.status === "actual" ? "LIVE · Actual Playoffs" : "PROJECTED · If season ended today"}
        </span>
      </div>

      <RoundsGrid
        rounds={bracket.rounds}
        status={bracket.status}
        testidPrefix="bracket"
        canMark={isCommish}
        onMarkWinner={onMarkWinner}
      />

      {/* Iter 197 — Champion banner + Distribute Prize CTA */}
      {bracket.champion?.decided && (
        <div
          className="rounded-lg border border-amber-500/40 bg-gradient-to-r from-amber-500/10 via-amber-400/10 to-yellow-500/10 p-4 flex items-center justify-between flex-wrap gap-3"
          data-testid="playoff-champion-banner"
        >
          <div className="flex items-center gap-3">
            <Crown className="h-8 w-8 text-amber-400" />
            <div>
              <div className="text-xs font-semibold uppercase tracking-widest text-amber-300/80">
                Champion
              </div>
              <div className="text-lg font-bold text-foreground" data-testid="playoff-champion-name">
                {bracket.champion.champion?.team_name}
              </div>
              {bracket.champion.runner_up && (
                <div className="text-xs text-muted-foreground">
                  Runner-up: <span className="font-medium text-foreground/80" data-testid="playoff-runner-up-name">{bracket.champion.runner_up.team_name}</span>
                </div>
              )}
            </div>
          </div>
          {bracket.champion.distributed ? (
            <div className="text-right" data-testid="playoff-prize-distributed-pill">
              <div className="text-[10px] uppercase tracking-wider font-semibold text-emerald-300/80">
                Prizes Distributed
              </div>
              <div className="text-sm font-bold text-foreground">
                {bracket.champion.currency || "USD"} {(bracket.champion.champion_prize || 0).toLocaleString()}
                {(bracket.champion.runner_up_prize || 0) > 0 && (
                  <span className="text-muted-foreground"> + {(bracket.champion.runner_up_prize || 0).toLocaleString()}</span>
                )}
              </div>
              {isCommish && (
                <button
                  className="text-[10px] underline text-muted-foreground hover:text-foreground"
                  onClick={() => setShowPrizeModal(true)}
                  data-testid="playoff-prize-edit-btn"
                >
                  Edit
                </button>
              )}
            </div>
          ) : isCommish ? (
            <Button
              onClick={() => setShowPrizeModal(true)}
              className="bg-amber-500 hover:bg-amber-400 text-amber-950 font-semibold"
              data-testid="playoff-distribute-prize-btn"
            >
              <Award className="h-4 w-4 mr-1.5" />
              Distribute Prize
            </Button>
          ) : null}
        </div>
      )}

      {/* Distribute Prize modal */}
      {showPrizeModal && bracket.champion?.decided && (
        <DistributePrizeModal
          leagueId={leagueId!}
          champion={bracket.champion}
          consolationEnabled={!!bracket.consolation_enabled}
          consolationSeeds={bracket.consolation_bracket?.seeds || []}
          onClose={() => setShowPrizeModal(false)}
          onSaved={() => { setShowPrizeModal(false); reload(); }}
        />
      )}

      {bracket.consolation_enabled && bracket.consolation_bracket && bracket.consolation_bracket.rounds?.length > 0 && (
        <div
          className="pt-4 mt-4 border-t border-border/60 space-y-4"
          data-testid="playoff-consolation-section"
        >
          <div className="flex items-center gap-2 flex-wrap">
            <Trophy className="h-4 w-4 text-violet-400" />
            <h2 className="text-base font-bold text-foreground">
              Consolation Bracket{" "}
              <span className="text-xs font-normal text-muted-foreground">
                · {bracket.consolation_bracket.size}-team
              </span>
            </h2>
            {bracket.consolation_bracket.seeding_method && (
              <span
                className="text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded-full bg-violet-500/15 text-violet-300 border border-violet-500/30"
                data-testid="playoff-consolation-seeding-badge"
              >
                {bracket.consolation_bracket.seeding_method === "high_vs_low" && "1 vs N seeding"}
                {bracket.consolation_bracket.seeding_method === "adjacent" && "1 v 2 / 3 v 4 seeding"}
                {bracket.consolation_bracket.seeding_method === "custom" && "Custom ladder"}
              </span>
            )}
          </div>
          <RoundsGrid
            rounds={bracket.consolation_bracket.rounds}
            status="projected"
            testidPrefix="consolation"
          />
          <div className="stat-card p-3 space-y-2" data-testid="playoff-consolation-seeds">
            <h3 className="text-xs font-bold text-muted-foreground uppercase tracking-wide">
              Consolation Seeds
            </h3>
            <div className="flex flex-wrap gap-2">
              {bracket.consolation_bracket.seeds.map((t) => (
                <button
                  key={t.team_id}
                  onClick={() => navigate(`/roster?team_id=${t.team_id}`)}
                  className="flex items-center gap-2 rounded-md px-2.5 py-1.5 bg-secondary/30 border border-border hover:bg-secondary/50 transition-colors text-xs"
                  data-testid={`consolation-seed-chip-${t.seed}`}
                >
                  <span className="font-bold text-violet-300">#{t.seed}</span>
                  <TeamLogo logo={t.team_logo_url} name={t.team_name} abbr={t.team_abbr} size="xs" />
                  <span className="font-medium">{t.team_name}</span>
                  <span className="text-muted-foreground">({t.wins}-{t.losses}{t.ties ? `-${t.ties}` : ""})</span>
                </button>
              ))}
            </div>
          </div>
        </div>
      )}

      <div className="stat-card p-4 space-y-2">
        <h3 className="text-sm font-bold text-foreground">Playoff Seeds</h3>
        <div className="flex flex-wrap gap-2">
          {bracket.playoff_teams.map((t) => (
            <button
              key={t.team_id}
              onClick={() => navigate(`/teams/${t.team_id}`)}
              className="flex items-center gap-2 rounded-md px-2.5 py-1.5 bg-secondary/30 border border-border hover:bg-secondary/50 transition-colors text-xs"
              data-testid={`bracket-seed-chip-${t.seed}`}
            >
              <span className={`font-bold ${SEED_COLOR[t.seed - 1] || "text-muted-foreground"}`}>#{t.seed}</span>
              <TeamLogo logo={t.team_logo_url} name={t.team_name} abbr={t.team_abbr} size="xs" />
              <span className="font-medium">{t.team_name}</span>
              <span className="text-muted-foreground">({t.wins}-{t.losses}{t.ties ? `-${t.ties}` : ""})</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
};

export default PlayoffBracketView;

/* ────────────────────────────────────────────────────────────────
 * Iter 197 — DistributePrizeModal
 * Commissioner one-tap prize distribution: champion + runner-up
 * + (optional) consolation champion. Persists via POST
 * /api/leagues/{id}/playoffs/distribute-prize. Idempotent — opening
 * the modal again pre-fills with the prior values for editing.
 * ──────────────────────────────────────────────────────────────── */
function DistributePrizeModal({
  leagueId, champion, consolationEnabled, consolationSeeds, onClose, onSaved,
}: {
  leagueId: string;
  champion: ChampionBlock;
  consolationEnabled: boolean;
  consolationSeeds: BracketTeam[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const [championPrize, setChampionPrize] = useState<string>(String(champion.champion_prize ?? 0));
  const [runnerUpPrize, setRunnerUpPrize] = useState<string>(String(champion.runner_up_prize ?? 0));
  const [consolationPrize, setConsolationPrize] = useState<string>(String(champion.consolation_prize ?? 0));
  const [consolationWinnerId, setConsolationWinnerId] = useState<string>(
    (champion as any)?.consolation_champion?.team_id || "",
  );
  const [currency, setCurrency] = useState<string>(champion.currency || "USD");
  const [note, setNote] = useState<string>(champion.note || "");
  const [saving, setSaving] = useState(false);

  const handleSave = async () => {
    setSaving(true);
    try {
      await api.post(`/leagues/${leagueId}/playoffs/distribute-prize`, {
        champion_team_id: champion.champion?.team_id,
        runner_up_team_id: champion.runner_up?.team_id,
        consolation_champion_team_id: consolationWinnerId || null,
        champion_prize: parseFloat(championPrize) || 0,
        runner_up_prize: parseFloat(runnerUpPrize) || 0,
        consolation_prize: parseFloat(consolationPrize) || 0,
        currency,
        note: note || null,
      });
      toast.success("Prize distributed");
      onSaved();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Failed to distribute prize");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-md" data-testid="distribute-prize-modal">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Award className="h-5 w-5 text-amber-400" />
            Distribute Playoff Prize
          </DialogTitle>
        </DialogHeader>
        <div className="space-y-4 py-2">
          {/* Champion */}
          <div className="space-y-1.5">
            <Label className="text-xs flex items-center gap-1.5">
              <Crown className="h-3.5 w-3.5 text-amber-400" /> Champion · {champion.champion?.team_name}
            </Label>
            <div className="flex gap-2">
              <Input
                type="number"
                min="0"
                step="0.01"
                value={championPrize}
                onChange={(e) => setChampionPrize(e.target.value)}
                className="bg-secondary border-border"
                data-testid="prize-champion-input"
              />
              <Input
                value={currency}
                onChange={(e) => setCurrency(e.target.value.toUpperCase().slice(0, 3))}
                className="bg-secondary border-border w-20"
                data-testid="prize-currency-input"
              />
            </div>
          </div>
          {/* Runner-up */}
          {champion.runner_up && (
            <div className="space-y-1.5">
              <Label className="text-xs">Runner-up · {champion.runner_up.team_name}</Label>
              <Input
                type="number"
                min="0"
                step="0.01"
                value={runnerUpPrize}
                onChange={(e) => setRunnerUpPrize(e.target.value)}
                className="bg-secondary border-border"
                data-testid="prize-runner-up-input"
              />
            </div>
          )}
          {/* Consolation winner picker */}
          {consolationEnabled && consolationSeeds.length > 0 && (
            <>
              <div className="space-y-1.5">
                <Label className="text-xs">Consolation Champion</Label>
                <select
                  value={consolationWinnerId}
                  onChange={(e) => setConsolationWinnerId(e.target.value)}
                  className="w-full h-9 rounded-md bg-secondary border border-border text-sm px-3"
                  data-testid="prize-consolation-team-select"
                >
                  <option value="">— None —</option>
                  {consolationSeeds.map((t) => (
                    <option key={t.team_id} value={t.team_id}>
                      #{t.seed} {t.team_name}
                    </option>
                  ))}
                </select>
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">Consolation Prize</Label>
                <Input
                  type="number"
                  min="0"
                  step="0.01"
                  value={consolationPrize}
                  onChange={(e) => setConsolationPrize(e.target.value)}
                  className="bg-secondary border-border"
                  data-testid="prize-consolation-input"
                />
              </div>
            </>
          )}
          {/* Optional note */}
          <div className="space-y-1.5">
            <Label className="text-xs">Note (optional)</Label>
            <Input
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="e.g. 'Paid via Venmo Feb 21'"
              className="bg-secondary border-border"
              data-testid="prize-note-input"
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={saving} data-testid="prize-cancel-btn">
            Cancel
          </Button>
          <Button
            onClick={handleSave}
            disabled={saving}
            className="bg-amber-500 hover:bg-amber-400 text-amber-950 font-semibold"
            data-testid="prize-confirm-btn"
          >
            {saving ? "Saving…" : "Confirm & Distribute"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

