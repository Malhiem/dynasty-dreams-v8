import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import api from '@/lib/api';
import { Badge } from '@/components/ui/badge';
import { useGlobalSocketEvent } from '@/hooks/use-global-socket';
import { Radio, Flame, ArrowRight } from 'lucide-react';

export default function LiveScoringWidget() {
  const [summary, setSummary] = useState(null);

  useEffect(() => {
    api.get('/live-scoring').then(({ data }) => setSummary(data)).catch(() => {});
  }, []);

  useGlobalSocketEvent('live_scoring_update', (payload) => setSummary(payload));

  if (!summary) return null;

  const games = summary.games || [];
  const live = games.filter(g => g.state === 'LIVE' || g.state === 'CRIT');
  const playoffs = games.filter(g => g.is_playoff);
  const anyLive = live.length > 0;

  return (
    <Link
      to="/live"
      data-testid="live-scoring-widget"
      className="block surface p-5 mb-8 border border-white/5 hover:border-[#00D2FF]/40 transition-colors"
    >
      <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <Radio size={18} className={anyLive ? 'text-red-400 animate-pulse' : 'text-[#00D2FF]'} />
          <span className="font-heading text-sm font-bold text-white tracking-wider">
            LIVE SCORING
          </span>
          {anyLive && (
            <Badge className="bg-red-500/20 text-red-400 border-red-500/40 animate-pulse text-[10px]">
              {live.length} ON AIR
            </Badge>
          )}
          {playoffs.length > 0 && (
            <Badge className="bg-amber-500/20 text-amber-400 border-amber-500/40 text-[10px]">
              <Flame size={10} className="mr-1" /> {playoffs.length} PLAYOFF
            </Badge>
          )}
        </div>
        <span className="text-[#00D2FF] text-xs flex items-center gap-1">
          Open live scores <ArrowRight size={12} />
        </span>
      </div>
      <div className="flex items-baseline gap-3 flex-wrap">
        <span className="text-3xl font-bold text-white tabular-nums">{games.length}</span>
        <span className="text-[#A1A1AA] text-sm">
          NHL games{summary.date ? ` for ${summary.date}` : ''} · {summary.players_updated || 0} players tracked
        </span>
      </div>
      {live.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-2">
          {live.slice(0, 4).map((g) => (
            <span
              key={g.id}
              className="text-[11px] bg-white/5 border border-white/10 px-2 py-1 rounded-full text-white tabular-nums"
            >
              <span className="text-[#A1A1AA]">{g.away}</span>{' '}
              <strong>{g.away_score ?? 0}</strong>{' @ '}
              <strong>{g.home_score ?? 0}</strong>{' '}
              <span className="text-[#A1A1AA]">{g.home}</span>
            </span>
          ))}
        </div>
      )}
    </Link>
  );
}
