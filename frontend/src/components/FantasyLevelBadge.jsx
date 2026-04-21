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

export default function FantasyLevelBadge({ compact = false }) {
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
      className={`rounded-xl p-4 bg-gradient-to-br ${palette} border`}
    >
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <Icon size={18} />
          <span className="text-[10px] uppercase tracking-wider opacity-70">
            Fantasy Level
          </span>
        </div>
        <Badge className="bg-black/40 text-white border-white/10 text-[10px]">
          {data.title}
        </Badge>
      </div>

      <div className="flex items-baseline gap-2 mb-3">
        <div className="text-4xl font-black tabular-nums">{data.level}</div>
        <div className="text-xs opacity-70">
          {data.xp_in_level}/{data.xp_required_for_next} XP
        </div>
      </div>

      <div className="h-2 bg-black/40 rounded-full overflow-hidden">
        <div
          className="h-full bg-current rounded-full transition-all duration-500"
          style={{ width: `${Math.min(100, data.progress_pct)}%` }}
        />
      </div>

      <div className="grid grid-cols-3 gap-2 mt-3 text-[10px] uppercase tracking-wider opacity-70">
        <div>
          <div className="opacity-60">Wins</div>
          <div className="text-base font-bold text-white">{data.stats.total_wins}</div>
        </div>
        <div>
          <div className="opacity-60">Trades</div>
          <div className="text-base font-bold text-white">{data.stats.trades_accepted}</div>
        </div>
        <div>
          <div className="opacity-60">Drafts</div>
          <div className="text-base font-bold text-white">{data.stats.drafts_completed}</div>
        </div>
      </div>
    </div>
  );
}
