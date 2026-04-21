import { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import axios from 'axios';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';
import {
  Trophy, Shield, Crown, Medal, Star, Flame, Link as LinkIcon,
  Check, Calendar, ArrowRight, Loader2,
} from 'lucide-react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;

const LEVEL_ICONS = {
  'Bench Warmer': Shield,
  'Rink Regular': Medal,
  'Line Captain': Star,
  'Hat Trick Hero': Flame,
  'Playoff Contender': Trophy,
  'Stanley Cup Dynasty': Crown,
};

const LEVEL_GRADIENTS = {
  'Bench Warmer': 'from-zinc-600 to-zinc-800',
  'Rink Regular': 'from-sky-600 to-sky-900',
  'Line Captain': 'from-cyan-500 to-cyan-800',
  'Hat Trick Hero': 'from-orange-500 to-amber-800',
  'Playoff Contender': 'from-purple-600 to-fuchsia-900',
  'Stanley Cup Dynasty': 'from-yellow-500 to-amber-900',
};

export default function ProfilePage() {
  const { username } = useParams();
  const [profile, setProfile] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    axios
      .get(`${BACKEND_URL}/api/u/${username}`)
      .then(({ data }) => !cancelled && setProfile(data))
      .catch((e) => !cancelled && setError(e.response?.status === 404 ? 'User not found' : 'Could not load profile'))
      .finally(() => !cancelled && setLoading(false));
    return () => { cancelled = true; };
  }, [username]);

  const copyLink = async () => {
    try {
      await navigator.clipboard.writeText(window.location.href);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (e) { /* noop */ }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-[#0A0A0A] flex items-center justify-center">
        <div className="flex items-center gap-2 text-[#A1A1AA]">
          <Loader2 size={16} className="animate-spin" /> Loading @{username}…
        </div>
      </div>
    );
  }

  if (error || !profile) {
    return (
      <div className="min-h-screen bg-[#0A0A0A] flex flex-col items-center justify-center p-8">
        <h1 className="font-heading text-3xl font-bold text-white mb-3">@{username}</h1>
        <p className="text-[#A1A1AA] mb-6">{error || 'Could not load profile'}</p>
        <Link to="/" className="text-[#00D2FF] hover:underline">
          Go to Dynasty Dreams
        </Link>
      </div>
    );
  }

  const LvlIcon = LEVEL_ICONS[profile.title] || Shield;
  const gradient = LEVEL_GRADIENTS[profile.title] || 'from-zinc-600 to-zinc-800';
  const winRate =
    profile.stats.total_wins + profile.stats.total_losses > 0
      ? Math.round(
          (profile.stats.total_wins /
            (profile.stats.total_wins + profile.stats.total_losses)) *
            100
        )
      : 0;

  return (
    <div data-testid="profile-page" className="min-h-screen bg-[#0A0A0A]">
      {/* Top header */}
      <div className="border-b border-white/5">
        <div className="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between">
          <Link to="/" className="flex items-center gap-2">
            <Trophy size={22} className="text-[#00D2FF]" />
            <span className="font-heading font-bold tracking-tight text-white">DYNASTY DREAMS</span>
          </Link>
          <Button
            data-testid="profile-copy-link-btn"
            onClick={copyLink}
            variant="outline"
            className="border-white/10 text-white hover:bg-white/5"
          >
            {copied ? <Check size={14} className="mr-2" /> : <LinkIcon size={14} className="mr-2" />}
            {copied ? 'Copied!' : 'Copy profile link'}
          </Button>
        </div>
      </div>

      {/* Hero */}
      <div className={`relative bg-gradient-to-br ${gradient} border-b border-white/10`}>
        <div className="absolute inset-0 bg-black/30" />
        <div className="relative max-w-6xl mx-auto px-6 py-12 flex items-center gap-6 flex-wrap">
          <div className="h-24 w-24 rounded-full bg-black/40 border-4 border-white/20 flex items-center justify-center text-4xl font-black text-white">
            {profile.username?.[0]?.toUpperCase()}
          </div>
          <div className="flex-1 min-w-[220px]">
            <div className="text-white/70 text-sm mb-1">@{profile.username}</div>
            <h1 className="font-heading text-4xl sm:text-5xl font-black tracking-tight text-white mb-2">
              {profile.display_name.toUpperCase()}
            </h1>
            <div className="flex items-center gap-2 flex-wrap">
              <Badge className="bg-black/50 text-white border-white/20">
                <LvlIcon size={12} className="mr-1" /> LEVEL {profile.level}
              </Badge>
              <Badge className="bg-white/10 text-white border-white/20">{profile.title}</Badge>
              {profile.member_since && (
                <Badge className="bg-transparent text-white/70 border-white/10">
                  <Calendar size={12} className="mr-1" />
                  Joined {new Date(profile.member_since).toLocaleDateString()}
                </Badge>
              )}
            </div>
          </div>
          <div className="min-w-[180px]">
            <div className="text-white/70 text-xs uppercase tracking-wider mb-1">XP Progress</div>
            <div className="h-3 bg-black/40 rounded-full overflow-hidden mb-1">
              <div
                className="h-full bg-white transition-all"
                style={{ width: `${Math.min(100, profile.progress_pct)}%` }}
              />
            </div>
            <div className="text-white/90 text-xs">
              {profile.xp_in_level} / {profile.xp_required_for_next} XP to next level
            </div>
          </div>
        </div>
      </div>

      <div className="max-w-6xl mx-auto px-6 py-10 space-y-10">
        {/* Stats grid */}
        <div className="grid gap-4 grid-cols-2 md:grid-cols-4">
          {[
            { label: 'Leagues', value: profile.stats.leagues_joined },
            { label: 'Record', value: `${profile.stats.total_wins}–${profile.stats.total_losses}–${profile.stats.total_ties}`, sub: `${winRate}% win rate` },
            { label: 'Points For', value: profile.stats.total_points.toFixed(1) },
            { label: 'Trades', value: profile.stats.trades_accepted, sub: `${profile.stats.drafts_completed} drafts` },
          ].map((s) => (
            <Card key={s.label} className="bg-white/5 border-white/10">
              <CardContent className="p-5">
                <div className="text-[10px] uppercase text-[#52525B] tracking-wider mb-1">{s.label}</div>
                <div className="text-3xl font-black text-white tabular-nums">{s.value}</div>
                {s.sub && <div className="text-[#A1A1AA] text-xs mt-1">{s.sub}</div>}
              </CardContent>
            </Card>
          ))}
        </div>

        {/* Trophy case */}
        {profile.trophies.length > 0 && (
          <section data-testid="profile-trophy-case">
            <div className="flex items-center gap-2 mb-4">
              <Trophy size={18} className="text-amber-400" />
              <h2 className="font-heading text-xl font-bold text-white tracking-wide">
                TROPHY CASE
              </h2>
              <Badge className="bg-amber-500/20 text-amber-300 border-amber-500/40">
                {profile.trophies.length}
              </Badge>
            </div>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {profile.trophies.map((t, idx) => (
                <div
                  key={`${t.league_id}-${idx}`}
                  className={`rounded-xl p-4 bg-gradient-to-br ${
                    t.type === 'lead'
                      ? 'from-amber-500/20 to-amber-900/20 border-amber-500/40'
                      : 'from-sky-500/15 to-sky-900/15 border-sky-500/30'
                  } border`}
                >
                  <Trophy
                    size={20}
                    className={t.type === 'lead' ? 'text-amber-400 mb-2' : 'text-sky-400 mb-2'}
                  />
                  <div className="text-xs uppercase text-white/70 tracking-wider mb-1">
                    {t.label}
                  </div>
                  <Link
                    to={`/leagues/${t.league_id}`}
                    className="text-white font-bold hover:text-[#00D2FF] block"
                  >
                    {t.team_name}
                  </Link>
                  <div className="text-[#A1A1AA] text-xs mt-0.5">{t.league_name}</div>
                </div>
              ))}
            </div>
          </section>
        )}

        {/* Teams */}
        <section>
          <div className="flex items-center gap-2 mb-4">
            <Shield size={18} className="text-[#00D2FF]" />
            <h2 className="font-heading text-xl font-bold text-white tracking-wide">
              TEAMS & LEAGUES
            </h2>
          </div>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {profile.teams.map((t) => (
              <Link
                key={t.team_id}
                to={`/teams/${t.team_id}`}
                data-testid={`profile-team-link-${t.team_id}`}
                className="block bg-white/5 border border-white/10 rounded-xl p-4 hover:border-[#00D2FF]/40 transition-colors"
              >
                <div className="flex items-center justify-between mb-2">
                  <Badge className="bg-white/5 text-[#A1A1AA] border-white/10 text-[10px]">
                    {(t.league_format || 'redraft').toUpperCase()}
                  </Badge>
                  <span className="text-xs text-[#52525B] tabular-nums">
                    #{t.rank ?? '—'}/{t.total_teams}
                  </span>
                </div>
                <div className="text-white font-bold text-base mb-0.5">{t.team_name}</div>
                <div className="text-[#A1A1AA] text-xs mb-3">{t.league_name}</div>
                <div className="flex items-baseline justify-between">
                  <div className="text-[#00D2FF] font-bold text-xl tabular-nums">
                    {t.points_for.toFixed(1)}
                    <span className="text-[10px] text-[#52525B] font-normal"> PF</span>
                  </div>
                  <span className="text-[#A1A1AA] text-xs">
                    {t.wins}–{t.losses}–{t.ties}
                  </span>
                </div>
              </Link>
            ))}
            {profile.teams.length === 0 && (
              <div className="col-span-full text-center text-[#A1A1AA] py-8">
                No teams yet. This user is just getting started.
              </div>
            )}
          </div>
        </section>

        {/* Lifetime top performer */}
        {profile.lifetime_top_performer && (
          <section>
            <div className="flex items-center gap-2 mb-4">
              <Flame size={18} className="text-orange-400" />
              <h2 className="font-heading text-xl font-bold text-white tracking-wide">
                LIFETIME BEST GAME
              </h2>
            </div>
            <Link
              to={`/players/${profile.lifetime_top_performer.id}`}
              className="block bg-gradient-to-br from-orange-500/10 to-transparent border border-orange-500/30 rounded-xl p-5 hover:border-orange-500/60 transition-colors"
            >
              <div className="flex items-center justify-between gap-4 flex-wrap">
                <div>
                  <div className="text-[10px] uppercase text-[#A1A1AA] tracking-wider mb-1">
                    Single-game high
                  </div>
                  <div className="text-white font-bold text-xl">
                    {profile.lifetime_top_performer.name}
                  </div>
                  <div className="text-[#A1A1AA] text-xs mt-1">
                    {profile.lifetime_top_performer.team} ·{' '}
                    {profile.lifetime_top_performer.position}
                    {profile.lifetime_top_performer.is_goalie ? (
                      <>
                        {' · '}
                        {profile.lifetime_top_performer.saves} SV /{' '}
                        {profile.lifetime_top_performer.goals_against} GA
                      </>
                    ) : (
                      <>
                        {' · '}
                        {profile.lifetime_top_performer.goals}G{' '}
                        {profile.lifetime_top_performer.assists}A{' '}
                        {profile.lifetime_top_performer.shots}SOG
                      </>
                    )}
                  </div>
                </div>
                <div className="text-5xl font-black text-orange-300 tabular-nums">
                  {profile.lifetime_top_performer.fpts.toFixed(1)}
                </div>
              </div>
              <div className="mt-3 text-[#00D2FF] text-xs flex items-center gap-1">
                View player <ArrowRight size={12} />
              </div>
            </Link>
          </section>
        )}

        <div className="text-center pt-6 border-t border-white/5">
          <Link to="/" className="text-[#A1A1AA] text-xs hover:text-white">
            Built on{' '}
            <span className="text-[#00D2FF] font-semibold">dynastydreams.app</span> — join
            your own dynasty.
          </Link>
        </div>
      </div>
    </div>
  );
}
