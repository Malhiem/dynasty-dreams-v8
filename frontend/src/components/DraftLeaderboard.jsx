/**
 * Iter 232N.27 — Draft leaderboard sidebar tile.
 *
 * Lives in the Draft Chat sidebar (`DraftRoomPage.jsx`). Pulls
 * `GET /api/drafts/{id}/leaderboard` on mount + whenever a
 * `draft_pick` WebSocket event fires so the running stats stay live.
 *
 * Categories:
 *   • Speed Demon    — fastest avg pick time  (hidden until final)
 *   • Slow-poke      — slowest avg pick time  (hidden until final)
 *   • Auto-pilot     — most auto-picks fired  (hidden until final)
 *   • Wheeler-Dealer — most trades this draft (live)
 *   • Iron Man       — most picks made        (live)
 *   • Queue Master   — best queue-hit-rate    (live)
 *
 * Post-draft the "hidden" trio reveals with a small trophy icon +
 * "+50 XP awarded" callout on the speed demon card.
 */
import { useCallback, useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Trophy, TurtleIcon, Zap, RefreshCw, Handshake, ListChecks, Star } from 'lucide-react';
import api from '@/lib/api';

const CATEGORY_META = {
  speed_demon: {
    label: 'Speed Demon',
    icon: Zap,
    color: 'text-emerald-300 border-emerald-500/40 bg-emerald-500/10',
    valueLabel: 'avg',
    format: (v) => `${Math.round(v)}s`,
    caption: '+50 XP for the fastest average pick time',
    hiddenCaption: 'Revealed when the draft ends',
  },
  slow_poke: {
    label: 'Slow-Poke',
    icon: TurtleIcon,
    color: 'text-amber-300 border-amber-500/40 bg-amber-500/10',
    valueLabel: 'avg',
    format: (v) => `${Math.round(v)}s`,
    caption: 'Slowest average pick time — trash-talk starts here',
    hiddenCaption: 'Revealed when the draft ends',
  },
  autopilot: {
    label: 'Auto-Pilot',
    icon: RefreshCw,
    color: 'text-rose-300 border-rose-500/40 bg-rose-500/10',
    valueLabel: 'auto',
    format: (v) => `${v}`,
    caption: 'Most auto-picks fired against them',
    hiddenCaption: 'Revealed when the draft ends',
  },
  wheeler_dealer: {
    label: 'Wheeler-Dealer',
    icon: Handshake,
    color: 'text-indigo-300 border-indigo-500/40 bg-indigo-500/10',
    valueLabel: 'trades',
    format: (v) => `${v}`,
    caption: 'Most accepted trades during the draft window',
  },
  iron_man: {
    label: 'Iron Man',
    icon: ListChecks,
    color: 'text-cyan-300 border-cyan-500/40 bg-cyan-500/10',
    valueLabel: 'picks',
    format: (v) => `${v}`,
    caption: 'Most picks made (helpful in expansion / bonus drafts)',
  },
  queue_master: {
    label: 'Queue Master',
    icon: Star,
    color: 'text-fuchsia-300 border-fuchsia-500/40 bg-fuchsia-500/10',
    valueLabel: 'queue hits',
    format: (v) => `${v}%`,
    caption: 'Best queue-hit-rate on auto-picks — nobody plans harder',
  },
};

function AwardTile({ id, winner, isFinal }) {
  const meta = CATEGORY_META[id];
  if (!meta) return null;
  const hidden = !isFinal && ['speed_demon', 'slow_poke', 'autopilot'].includes(id);
  const Icon = meta.icon;
  return (
    <div
      className={`rounded-lg border ${meta.color} p-2.5 flex items-start gap-2 transition-opacity ${hidden ? 'opacity-40' : ''}`}
      data-testid={`draft-leaderboard-tile-${id}`}
    >
      <Icon className="h-4 w-4 shrink-0 mt-0.5" />
      <div className="min-w-0 flex-1">
        <div className="flex items-center justify-between gap-2">
          <span className="text-[11px] font-bold uppercase tracking-wider">
            {meta.label}
          </span>
          {winner ? (
            <Badge variant="outline" className="text-[10px] h-4 border-white/15 text-white">
              {meta.format(winner.value)} {meta.valueLabel}
            </Badge>
          ) : (
            <span className="text-[10px] text-[#52525B]">—</span>
          )}
        </div>
        {hidden ? (
          <p className="text-[10px] text-[#A1A1AA] italic mt-0.5">
            {meta.hiddenCaption}
          </p>
        ) : winner ? (
          <>
            <p className="text-sm font-semibold text-white truncate" data-testid={`draft-leaderboard-winner-${id}`}>
              {winner.team_name}
            </p>
            <p className="text-[10px] text-[#A1A1AA] leading-tight mt-0.5">
              {meta.caption}
            </p>
          </>
        ) : (
          <p className="text-[10px] text-[#A1A1AA] italic mt-0.5">
            No qualifying data yet
          </p>
        )}
      </div>
    </div>
  );
}

export default function DraftLeaderboard({ draftId, refreshTick = 0 }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const fetchData = useCallback(async () => {
    if (!draftId) return;
    setLoading(true);
    try {
      const res = await api.get(`/drafts/${draftId}/leaderboard`);
      setData(res.data);
      setError(null);
    } catch (e) {
      setError(e?.response?.data?.detail || 'Leaderboard unavailable');
    } finally {
      setLoading(false);
    }
  }, [draftId]);

  useEffect(() => { fetchData(); }, [fetchData, refreshTick]);

  const isFinal = !!data?.is_final;
  const awards = data?.awards || {};

  return (
    <Card className="border-white/10" data-testid="draft-leaderboard-card">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm flex items-center gap-2 text-white">
          <Trophy className="h-4 w-4 text-amber-400" />
          Draft Leaderboard
          {isFinal ? (
            <Badge className="ml-1 bg-amber-500/20 text-amber-200 border border-amber-500/40 h-4 text-[9px]">
              FINAL REVEAL
            </Badge>
          ) : (
            <Badge className="ml-1 bg-white/5 text-[#A1A1AA] border border-white/10 h-4 text-[9px]">
              LIVE
            </Badge>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent className="p-2 space-y-2">
        {error && (
          <p className="text-[11px] text-rose-300 px-1" data-testid="draft-leaderboard-error">
            {error}
          </p>
        )}
        {loading && !data ? (
          <p className="text-[11px] text-[#A1A1AA] italic px-1">
            Crunching pick timings…
          </p>
        ) : (
          <>
            <AwardTile id="iron_man" winner={awards.iron_man} isFinal={isFinal} />
            <AwardTile id="wheeler_dealer" winner={awards.wheeler_dealer} isFinal={isFinal} />
            <AwardTile id="queue_master" winner={awards.queue_master} isFinal={isFinal} />
            <div className="h-px bg-white/5 my-1" />
            <AwardTile id="speed_demon" winner={awards.speed_demon} isFinal={isFinal} />
            <AwardTile id="slow_poke" winner={awards.slow_poke} isFinal={isFinal} />
            <AwardTile id="autopilot" winner={awards.autopilot} isFinal={isFinal} />
            {isFinal && awards.speed_demon && (
              <p className="text-[10px] text-emerald-300 text-center pt-1" data-testid="draft-leaderboard-xp-note">
                +50 XP Speed Demon bonus awarded
              </p>
            )}
            {data?.total_picks > 0 && (
              <p className="text-[10px] text-[#52525B] text-center pt-1">
                {data.total_picks} picks • {data.auto_picks_total} auto
              </p>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
