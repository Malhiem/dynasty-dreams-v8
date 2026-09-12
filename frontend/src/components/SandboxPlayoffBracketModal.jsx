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
import { Trophy, X, RefreshCw } from 'lucide-react';
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

function MatchupCard({ m, isFinal }) {
  const homeWon = m.winner === m.home;
  return (
    <div
      className={`rounded border ${isFinal ? 'border-amber-400/60 bg-amber-500/10' : 'border-border bg-background/60'} p-2 text-xs space-y-1 shadow-sm`}
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
    </div>
  );
}

export default function SandboxPlayoffBracketModal({
  open, onClose, leagueId, initialData,
}) {
  const [data, setData] = useState(initialData || null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

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

        {!loading && !error && totalRounds > 0 && (
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
                      />
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
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
