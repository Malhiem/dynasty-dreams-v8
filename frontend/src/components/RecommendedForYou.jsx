import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Sparkles, ArrowRight, Loader2 } from 'lucide-react';
import api from '@/lib/api';

const COMMITMENT_OPTIONS = [
  { key: 'any', label: 'Any Commitment' },
  { key: 'casual', label: 'Casual' },
  { key: 'serious', label: 'Serious' },
  { key: 'hardcore', label: 'Hardcore Dynasty' },
];
const SCORING_OPTIONS = [
  { key: 'any', label: 'Any Scoring' },
  { key: 'head_to_head', label: 'Head-to-Head' },
  { key: 'rotisserie', label: 'Rotisserie' },
  { key: 'total_points', label: 'Total Points' },
];
const DRAFT_OPTIONS = [
  { key: 'any', label: 'Any Draft' },
  { key: 'snake', label: 'Snake' },
  { key: 'auction', label: 'Auction' },
];

function Chips({ value, onChange, options, testPrefix }) {
  return (
    <div className="flex flex-wrap gap-2">
      {options.map((o) => (
        <button
          key={o.key}
          type="button"
          data-testid={`${testPrefix}-${o.key}`}
          onClick={() => onChange(o.key)}
          className={`px-3 py-1.5 rounded-full text-xs font-semibold transition-colors ${
            value === o.key
              ? 'bg-[#00D2FF] text-black'
              : 'bg-white/5 text-[#A1A1AA] hover:bg-white/10'
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export default function RecommendedForYou() {
  const navigate = useNavigate();
  const [commitment, setCommitment] = useState('any');
  const [scoring, setScoring] = useState('any');
  const [draftStyle, setDraftStyle] = useState('any');
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState(null);

  const query = useMemo(
    () => `?commitment=${commitment}&scoring=${scoring}&draft_style=${draftStyle}&limit=3`,
    [commitment, scoring, draftStyle]
  );

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    api
      .get(`/recommendations/leagues${query}`)
      .then(({ data }) => {
        if (!cancelled) setData(data);
      })
      .catch((e) => console.error('recommendation fetch failed', e))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [query]);

  const recs = data?.recommendations || [];
  const topPick = recs[0];

  return (
    <div
      data-testid="recommended-for-you"
      className="surface p-6 mb-8 border border-white/5"
    >
      <div className="flex items-center gap-2 mb-1">
        <Sparkles size={18} className="text-[#00D2FF]" />
        <h2 className="font-heading text-xl font-bold text-white tracking-wide">
          RECOMMENDED FOR YOU
        </h2>
      </div>
      <p className="text-[#A1A1AA] text-sm mb-5">
        {data?.has_active_leagues
          ? "We've prioritized your active leagues — tweak the filters to explore more."
          : 'Pick your style and we\'ll line up the best leagues to join.'}
      </p>

      <div className="grid gap-4 md:grid-cols-3 mb-5">
        <div>
          <div className="text-[#52525B] text-xs uppercase mb-2 tracking-wider">
            Commitment
          </div>
          <Chips
            value={commitment}
            onChange={setCommitment}
            options={COMMITMENT_OPTIONS}
            testPrefix="rec-commitment"
          />
        </div>
        <div>
          <div className="text-[#52525B] text-xs uppercase mb-2 tracking-wider">
            Scoring
          </div>
          <Chips
            value={scoring}
            onChange={setScoring}
            options={SCORING_OPTIONS}
            testPrefix="rec-scoring"
          />
        </div>
        <div>
          <div className="text-[#52525B] text-xs uppercase mb-2 tracking-wider">
            Draft Style
          </div>
          <Chips
            value={draftStyle}
            onChange={setDraftStyle}
            options={DRAFT_OPTIONS}
            testPrefix="rec-draft"
          />
        </div>
      </div>

      {loading ? (
        <div className="flex items-center gap-2 text-[#A1A1AA] text-sm py-6">
          <Loader2 size={16} className="animate-spin" />
          Scoring matches…
        </div>
      ) : recs.length === 0 ? (
        <div className="text-[#A1A1AA] text-sm py-6">
          No open leagues match those filters yet. Try widening a preference.
        </div>
      ) : (
        <div className="space-y-3">
          {topPick && (
            <div
              data-testid="recommended-top-pick"
              className="p-5 rounded-xl border-2 border-[#00D2FF]/40 bg-gradient-to-br from-[#00D2FF]/5 to-transparent"
            >
              <div className="flex items-start justify-between gap-4 flex-wrap">
                <div className="flex-1 min-w-[200px]">
                  <div className="flex items-center gap-2 mb-1 flex-wrap">
                    <Badge className="bg-[#00D2FF]/20 text-[#00D2FF] border-[#00D2FF]/40">
                      TOP PICK
                    </Badge>
                    {topPick.is_own && (
                      <Badge className="bg-emerald-500/20 text-emerald-400 border-emerald-500/40">
                        YOUR LEAGUE
                      </Badge>
                    )}
                    {topPick.premium && (
                      <Badge className="bg-amber-500/20 text-amber-400 border-amber-500/40">
                        PREMIUM
                      </Badge>
                    )}
                  </div>
                  <div className="text-white font-bold text-lg">{topPick.name}</div>
                  <div className="text-[#A1A1AA] text-sm mt-1">
                    {topPick.format?.replace('_', ' ').toUpperCase()} ·{' '}
                    {topPick.scoring_format?.replace('_', ' ').toUpperCase()} ·{' '}
                    {topPick.current_teams}/{topPick.max_teams} teams
                    {topPick.entry_fee ? ` · $${topPick.entry_fee} entry` : ''}
                  </div>
                  <div className="text-[#00D2FF] text-xs mt-2 italic">
                    {topPick.match_reason}
                  </div>
                </div>
                <Button
                  data-testid="recommended-join-top-btn"
                  onClick={() =>
                    navigate(
                      topPick.is_own
                        ? `/leagues/${topPick.id}`
                        : `/join/${topPick.invite_code}`
                    )
                  }
                  className="bg-[#00D2FF] text-black hover:bg-[#33DBFF]"
                >
                  {topPick.is_own ? 'Open League' : 'Join League'}
                  <ArrowRight size={16} className="ml-1" />
                </Button>
              </div>
            </div>
          )}

          {recs.slice(1).map((lg) => (
            <div
              key={lg.id}
              data-testid={`recommended-item-${lg.id}`}
              className="p-4 rounded-lg bg-white/5 border border-white/5 flex items-center justify-between gap-4 flex-wrap hover:bg-white/10 transition-colors"
            >
              <div className="flex-1 min-w-[200px]">
                <div className="text-white font-semibold text-sm">{lg.name}</div>
                <div className="text-[#A1A1AA] text-xs mt-0.5">
                  {lg.format?.replace('_', ' ').toUpperCase()} ·{' '}
                  {lg.scoring_format?.replace('_', ' ').toUpperCase()} ·{' '}
                  {lg.current_teams}/{lg.max_teams} teams
                </div>
                <div className="text-[#52525B] text-xs mt-1">{lg.match_reason}</div>
              </div>
              <Button
                variant="outline"
                size="sm"
                data-testid={`recommended-join-${lg.id}-btn`}
                onClick={() =>
                  navigate(lg.is_own ? `/leagues/${lg.id}` : `/join/${lg.invite_code}`)
                }
                className="border-white/10 text-white hover:bg-white/5"
              >
                {lg.is_own ? 'Open' : 'Join'}
              </Button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
