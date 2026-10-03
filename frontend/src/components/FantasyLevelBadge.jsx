import { useEffect, useState } from 'react';
import api from '@/lib/api';
import { Badge } from '@/components/ui/badge';
import { Shield, Crown, Medal, Flame, Trophy, Star } from 'lucide-react';

const LEVEL_ICONS = {
  'Bench Warmer': Shield,
  'Rink Regular': Medal,
  'Line Captain': Star,
  'Hat Trick Hero': Flame,
  'Playoff Contender': Trophy,
  'Stanley Cup Dynasty': Crown,
};

const LEVEL_COLORS = {
  'Bench Warmer': 'from-zinc-500/30 to-zinc-700/30 border-zinc-500/40 text-zinc-300',
  'Rink Regular': 'from-sky-500/20 to-sky-800/20 border-sky-500/40 text-sky-300',
  'Line Captain': 'from-cyan-400/20 to-cyan-700/20 border-cyan-400/40 text-cyan-300',
  'Hat Trick Hero': 'from-orange-500/20 to-amber-700/20 border-orange-500/40 text-orange-300',
  'Playoff Contender': 'from-purple-500/20 to-fuchsia-700/20 border-purple-500/40 text-purple-300',
  'Stanley Cup Dynasty': 'from-yellow-400/30 to-amber-700/30 border-yellow-400/50 text-yellow-300',
};

export default function FantasyLevelBadge({ compact = false, extraStats }) {
  const [data, setData] = useState(null);

  useEffect(() => {
    let cancelled = false;
    api
      .get('/users/me/level')
      .then(({ data }) => !cancelled && setData(data))
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  if (!data) return null;

  const Icon = LEVEL_ICONS[data.title] || Shield;
  const palette =
    LEVEL_COLORS[data.title] ||
    'from-zinc-500/30 to-zinc-700/30 border-zinc-500/40 text-zinc-300';

  if (compact) {
    return (
      <div
        data-testid="fantasy-level-compact"
        className={`flex items-center gap-2 px-2 py-1 rounded-full bg-gradient-to-r ${palette} border`}
        title={`Level ${data.level} · ${data.title} · ${data.xp_in_level}/${data.xp_required_for_next} XP`}
      >
        <Icon size={12} />
        <span className="text-[10px] font-bold tracking-wider">LVL {data.level}</span>
      </div>
    );
  }

  return (
    <div
      data-testid="fantasy-level-card"
      className={`rounded-xl p-3 sm:p-4 bg-gradient-to-br ${palette} border`}
    >
      <div className="flex items-center justify-between mb-2 gap-2 min-w-0">
        <div className="flex items-center gap-2 min-w-0">
          <Icon size={18} className="shrink-0" />
          <span className="text-[10px] uppercase tracking-wider opacity-70 truncate">
            Fantasy Level
          </span>
        </div>
        <Badge className="bg-black/40 text-white border-white/10 text-[10px] shrink-0 max-w-[55%] truncate">
          {data.title}
        </Badge>
      </div>

      <div className="flex items-baseline gap-2 mb-3 flex-wrap">
        <div className="text-3xl sm:text-4xl font-black tabular-nums">{data.level}</div>
        <div className="text-[11px] sm:text-xs opacity-70">
          {data.xp_in_level}/{data.xp_required_for_next} XP
        </div>
      </div>

      <div className="h-2 bg-black/40 rounded-full overflow-hidden">
        <div
          className="h-full bg-current rounded-full transition-all duration-500"
          style={{ width: `${Math.min(100, data.progress_pct)}%` }}
        />
      </div>

      {/* Iter 232N.21 — Mobile-tight stat row. Reduced label text to
          9px + condensed leading so all three stats sit on one line
          on a 320px viewport (previously wrapped/overflowed at ≤360px).
          Iter 232N.22 — Baked the dashboard stat cards (My Leagues,
          Upcoming Drafts, Win Rate) into the badge and dropped the
          separate "Total Teams" tile — 5-up grid on desktop, 3-up on
          mobile with the account-lifetime stats wrapping below. */}
      <div className="grid grid-cols-3 sm:grid-cols-5 gap-1.5 sm:gap-2 mt-3 text-[9px] sm:text-[10px] uppercase tracking-wider opacity-70">
        {extraStats && (
          <>
            <div className="min-w-0" data-testid="badge-stat-leagues">
              <div className="opacity-60 truncate">Leagues</div>
              <div className="text-sm sm:text-base font-bold text-white tabular-nums">
                {extraStats.leagues ?? "--"}
              </div>
            </div>
            <div className="min-w-0" data-testid="badge-stat-upcoming">
              <div className="opacity-60 truncate">Upcoming</div>
              <div className="text-sm sm:text-base font-bold text-white tabular-nums">
                {extraStats.upcoming ?? "--"}
              </div>
            </div>
            <div className="min-w-0" data-testid="badge-stat-win-rate">
              <div className="opacity-60 truncate">Win Rate</div>
              <div className="text-sm sm:text-base font-bold text-white tabular-nums">
                {extraStats.winRate ?? "--"}
              </div>
            </div>
          </>
        )}
        <div className="min-w-0" data-testid="badge-stat-wins">
          <div className="opacity-60 truncate">Wins</div>
          <div className="text-sm sm:text-base font-bold text-white tabular-nums">{data.stats.total_wins}</div>
        </div>
        <div className="min-w-0" data-testid="badge-stat-trades">
          <div className="opacity-60 truncate">Trades</div>
          <div className="text-sm sm:text-base font-bold text-white tabular-nums">{data.stats.trades_accepted}</div>
        </div>
        {/* Iter 232N.22 — Drafts + Trades still exposed side-by-side on
            desktop (5 cols total); mobile shows Leagues/Upcoming/WinRate
            on row 1 and Wins/Trades/Drafts on row 2 via `grid-cols-3`. */}
        <div className="min-w-0" data-testid="badge-stat-drafts">
          <div className="opacity-60 truncate">Drafts</div>
          <div className="text-sm sm:text-base font-bold text-white tabular-nums">{data.stats.drafts_completed}</div>
        </div>
      </div>
    </div>
  );
}
