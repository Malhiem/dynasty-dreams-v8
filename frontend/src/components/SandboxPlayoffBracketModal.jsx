/**
 * Iter 232N.81 — Sandbox playoff bracket visualizer modal.
 *
 * Groups the flat `bracket` array (from POST seed-playoffs or the new
 * GET playoff-bracket endpoint) into round columns and renders a
 * classic single-elim tournament tree:
 *
 *    QF          SF          F
 *   ────────    ────────    ────────
 *   1 vs 8 →   winA vs …   final
 *   2 vs 7 →       …       ──────
 *   3 vs 6 →   winB vs …    champ
 *   4 vs 5 →       …
 *
 * Auto-opens when the "sandbox:playoffs-seeded" event fires and can be
 * reopened from the top-bar champion badge.
 */
import { useEffect, useMemo, useState } from 'react';
import { Trophy, X, RefreshCw, ChevronLeft } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import api from '@/lib/api';

const ROUND_LABEL = {
  1: 'Round 1',
  2: 'Quarterfinals',
  3: 'Semifinals',
  4: 'Finals',
};

function roundLabel(round, totalRounds) {
  // Show classic labels for the last 3 rounds (Finals/Semis/QF) and
  // "Round N" for any earlier ones (e.g. 16-team bracket → R1, R2, SF, F).
  const distFromFinal = totalRounds - round;
  if (distFromFinal === 0) return 'Finals';
  if (distFromFinal === 1) return 'Semifinals';
  if (distFromFinal === 2) return 'Quarterfinals';
  return `Round ${round}`;
}

function MatchupCard({ m, isFinal, onOpen }) {
  const homeWon = m.winner === m.home;
  return (
    <button
      type="button"
      onClick={() => onOpen?.(m)}
      className={`w-full text-left rounded border ${isFinal ? 'border-amber-400/60 bg-amber-500/10' : 'border-border bg-background/60'} p-2 text-xs space-y-1 shadow-sm hover:border-accent/70 hover:bg-accent/5 transition-colors`}
      data-testid={`bracket-matchup-r${m.round}`}
    >
      <div
        className={`flex items-center justify-between gap-2 ${homeWon ? 'text-emerald-300 font-semibold' : 'text-muted-foreground'}`}
      >
        <span className="truncate">{m.home}</span>
        <span className="tabular-nums">{m.home_score}</span>
      </div>
      <div
        className={`flex items-center justify-between gap-2 ${!homeWon ? 'text-emerald-300 font-semibold' : 'text-muted-foreground'}`}
      >
        <span className="truncate">{m.away}</span>
        <span className="tabular-nums">{m.away_score}</span>
      </div>
    </button>
  );
}

// Iter 232N.83 — Simple box-score panel shown when the admin clicks
// a matchup card in the bracket. Fetches both team rosters lazily so
// the bracket modal stays snappy.
function BoxScorePanel({ m, onBack }) {
  const [homeRoster, setHomeRoster] = useState([]);
  const [awayRoster, setAwayRoster] = useState([]);
  const [loading, setLoading] = useState(false);
  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const [h, a] = await Promise.all([
          api.get(`/teams/${m.home_team_id}/roster-truncated`).catch(() => null),
          api.get(`/teams/${m.away_team_id}/roster-truncated`).catch(() => null),
        ]);
        if (cancelled) return;
        const _players = (t) => (t?.data?.players || []).slice(0, 8);
        setHomeRoster(_players(h));
        setAwayRoster(_players(a));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [m.home_team_id, m.away_team_id]);

  const homeWon = m.winner === m.home;
  const row = (p) => {
    if (!p) return null;
    const name = typeof p === 'string' ? p : (p.name || p.player_name || 'Player');
    const pos = typeof p === 'string' ? '' : (p.position || '');
    return (
      <li className="text-[11px] flex justify-between gap-2 py-0.5 border-b border-border/40 last:border-0">
        <span className="truncate">{name}</span>
        {pos && <span className="text-muted-foreground">{pos}</span>}
      </li>
    );
  };
  return (
    <div data-testid="bracket-boxscore-panel" className="space-y-3">
      <div className="flex items-center gap-2">
        <Button
          size="sm"
          variant="ghost"
          onClick={onBack}
          data-testid="bracket-boxscore-back-btn"
        >
          <ChevronLeft className="h-3.5 w-3.5 mr-1" /> Back to bracket
        </Button>
        <Badge variant="outline" className="text-[10px]">
          Round {m.round}
        </Badge>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div
          className={`rounded border p-3 ${homeWon ? 'border-emerald-400/60 bg-emerald-500/10' : 'border-border bg-background/60'}`}
          data-testid="bracket-boxscore-home"
        >
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-semibold">{m.home}</span>
            <span className="text-lg font-bold tabular-nums">{m.home_score}</span>
          </div>
          <p className="text-[10px] uppercase tracking-wide text-muted-foreground mb-1">Roster (top 8)</p>
          <ul>{homeRoster.length ? homeRoster.map((p, i) => (
            <li key={i}>{row(p)}</li>
          )) : (
            <li className="text-[11px] text-muted-foreground italic">
              {loading ? 'Loading…' : 'No roster on file'}
            </li>
          )}</ul>
        </div>
        <div
          className={`rounded border p-3 ${!homeWon ? 'border-emerald-400/60 bg-emerald-500/10' : 'border-border bg-background/60'}`}
          data-testid="bracket-boxscore-away"
        >
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-semibold">{m.away}</span>
            <span className="text-lg font-bold tabular-nums">{m.away_score}</span>
          </div>
          <p className="text-[10px] uppercase tracking-wide text-muted-foreground mb-1">Roster (top 8)</p>
          <ul>{awayRoster.length ? awayRoster.map((p, i) => (
            <li key={i}>{row(p)}</li>
          )) : (
            <li className="text-[11px] text-muted-foreground italic">
              {loading ? 'Loading…' : 'No roster on file'}
            </li>
          )}</ul>
        </div>
      </div>
      <p className="text-[10px] text-muted-foreground">
        Winner:&nbsp;<strong className="text-emerald-300">{m.winner}</strong>
        &nbsp;· Loser:&nbsp;<span className="text-muted-foreground">{m.loser}</span>
      </p>
    </div>
  );
}

export default function SandboxPlayoffBracketModal({
  open, onClose, leagueId, initialData,
}) {
  const [data, setData] = useState(initialData || null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  // Iter 232N.83 — Selected matchup for the "click a card → box score"
  // drill-in flow. null → grid view, object → box-score panel.
  const [openMatchup, setOpenMatchup] = useState(null);

  // Reset the drill-in view whenever the modal reopens.
  useEffect(() => { if (!open) setOpenMatchup(null); }, [open]);

  // Fetch on open unless the caller pre-supplied the seed response.
  useEffect(() => {
    if (!open || !leagueId) return;
    if (initialData?.bracket?.length) {
      setData(initialData);
      return;
    }
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const { data: res } = await api.get(
          `/admin/test-sandbox/leagues/${leagueId}/playoff-bracket`,
        );
        if (!cancelled) setData(res);
      } catch (e) {
        if (!cancelled) setError(e?.response?.data?.detail || 'Failed to load bracket');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [open, leagueId, initialData]);

  const rounds = useMemo(() => {
    if (!data?.bracket?.length) return [];
    const byRound = new Map();
    data.bracket.forEach((m) => {
      if (!byRound.has(m.round)) byRound.set(m.round, []);
      byRound.get(m.round).push(m);
    });
    return [...byRound.entries()]
      .sort(([a], [b]) => a - b)
      .map(([round, matchups]) => ({ round, matchups }));
  }, [data]);

  const totalRounds = rounds.length;
  const champion = data?.champion;

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent
        className="max-w-4xl"
        data-testid="sandbox-playoff-bracket-modal"
      >
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-lg">
            <Trophy className="h-5 w-5 text-amber-400" />
            Playoff Bracket
            {champion && (
              <Badge
                variant="outline"
                className="ml-2 bg-amber-500/15 border-amber-400/50 text-amber-100 gap-1"
                data-testid="bracket-modal-champion-badge"
              >
                <Trophy className="h-3 w-3" /> Champion: {champion}
              </Badge>
            )}
          </DialogTitle>
          <DialogDescription>
            {loading
              ? 'Loading the bracket…'
              : totalRounds === 0
                ? 'No playoff bracket has been seeded for this sandbox yet.'
                : `Single-elimination · ${totalRounds} round${totalRounds === 1 ? '' : 's'} played`}
          </DialogDescription>
        </DialogHeader>

        {loading && (
          <div className="flex items-center justify-center py-10 text-muted-foreground text-sm gap-2">
            <RefreshCw className="h-4 w-4 animate-spin" /> Loading…
          </div>
        )}

        {error && (
          <div
            className="rounded-md border border-rose-500/40 bg-rose-500/10 p-3 text-xs text-rose-200"
            data-testid="bracket-modal-error"
          >
            {error}
          </div>
        )}

        {!loading && !error && totalRounds === 0 && (
          <div className="rounded-md border border-dashed border-muted-foreground/40 p-6 text-center text-sm text-muted-foreground">
            Seed the playoffs from the sandbox banner to populate this bracket.
          </div>
        )}

        {!loading && !error && totalRounds > 0 && !openMatchup && (
          <div
            className="grid gap-4 overflow-auto pb-2 max-h-[65vh]"
            style={{ gridTemplateColumns: `repeat(${totalRounds}, minmax(180px, 1fr))` }}
            data-testid="bracket-modal-grid"
          >
            {rounds.map(({ round, matchups }) => {
              const isFinal = round === totalRounds;
              return (
                <div
                  key={round}
                  className="space-y-3"
                  data-testid={`bracket-column-round-${round}`}
                >
                  <div className="flex items-center justify-between text-[11px] uppercase tracking-wide text-muted-foreground">
                    <span>{roundLabel(round, totalRounds)}</span>
                    <span className="tabular-nums">{matchups.length} game{matchups.length === 1 ? '' : 's'}</span>
                  </div>
                  <div
                    className="space-y-2 h-full"
                    style={{
                      display: 'flex',
                      flexDirection: 'column',
                      justifyContent: 'space-around',
                    }}
                  >
                    {matchups.map((m, idx) => (
                      <MatchupCard
                        key={`${m.round}-${idx}-${m.home}-${m.away}`}
                        m={m}
                        isFinal={isFinal}
                        onOpen={setOpenMatchup}
                      />
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {openMatchup && (
          <BoxScorePanel
            m={openMatchup}
            onBack={() => setOpenMatchup(null)}
          />
        )}

        <div className="flex justify-end pt-2">
          <Button
            variant="outline"
            size="sm"
            onClick={onClose}
            data-testid="bracket-modal-close-btn"
          >
            <X className="h-3.5 w-3.5 mr-1" /> Close
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
