import { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import axios from 'axios';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';
import {
  Trophy, Shield, Crown, Medal, Star, Flame, Link as LinkIcon,
  Check, Calendar, ArrowRight, Loader2, Award, Lock, Activity,
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

const TIER_STYLE = {
  'Rookie':        { bg: 'from-zinc-500/15 to-zinc-900/15', border: 'border-zinc-500/40', text: 'text-zinc-300' },
  'Contender':     { bg: 'from-sky-500/15 to-sky-900/15', border: 'border-sky-500/40', text: 'text-sky-300' },
  'Veteran':       { bg: 'from-emerald-500/15 to-emerald-900/15', border: 'border-emerald-500/40', text: 'text-emerald-300' },
  'All-Star':      { bg: 'from-cyan-500/20 to-cyan-900/20', border: 'border-cyan-400/50', text: 'text-cyan-300' },
  'Hall of Famer': { bg: 'from-violet-500/25 to-violet-900/25', border: 'border-violet-400/55', text: 'text-violet-300' },
  'Elite':         { bg: 'from-orange-500/25 to-orange-900/25', border: 'border-orange-400/55', text: 'text-orange-300' },
  'Legend':        { bg: 'from-amber-400/35 to-yellow-800/35', border: 'border-amber-300/70', text: 'text-amber-200' },
};

export default function ProfilePage() {
  const { username } = useParams();
  const [profile, setProfile] = useState(null);
  const [rating, setRating] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setRating(null);
    axios
      .get(`${BACKEND_URL}/api/u/${username}`)
      .then(async ({ data }) => {
        if (cancelled) return;
        setProfile(data);
        // Best-effort rating fetch — public endpoint so no auth required
        try {
          // Fetch user_id via the lookup (the profile API doesn't return id)
          // The /api/u/{username} response has no user_id — fetch via teams[0].owner if any.
          // Fallback: skip rating if we can't resolve.
          const usersLookup = await axios
            .get(`${BACKEND_URL}/api/u/${username}/rating`)
            .catch(() => null);
          if (usersLookup?.data) setRating(usersLookup.data);
        } catch (e) {
          /* noop */
        }
      })
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
        <div className="max-w-6xl mx-auto px-4 sm:px-6 py-4 flex items-center justify-between gap-3 flex-wrap">
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
          <div className="w-full min-w-0 sm:flex-1 sm:w-auto">
            <div className="text-white/70 text-sm mb-1 [overflow-wrap:anywhere]">@{profile.username}</div>
            <h1 className="font-heading text-3xl sm:text-5xl font-black tracking-tight text-white mb-2 [overflow-wrap:anywhere]">
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
            {profile.xp_breakdown && (
              <div className="text-white/70 text-xs mt-2 max-w-xs" data-testid="profile-xp-breakdown">
                Competitive XP: {profile.xp_breakdown.competitive_awarded_xp} of {profile.xp_breakdown.competitive_base_xp} base
                <br />Participation XP: {profile.xp_breakdown.participation_xp}
              </div>
            )}
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

        {/* Career championships row */}
        {(profile.stats.championships_won > 0
          || profile.stats.conference_titles > 0
          || profile.stats.division_titles > 0
          || profile.stats.consolations_won > 0
          || profile.stats.playoff_appearances > 0) && (
          <div className="grid gap-4 grid-cols-2 md:grid-cols-5" data-testid="profile-career-championships">
            {[
              { label: 'Championships', value: profile.stats.championships_won || 0, color: 'from-amber-500/20 to-amber-900/20 border-amber-500/40', text: 'text-amber-400', icon: '🏆', testId: 'stat-championships' },
              { label: 'Conference Titles', value: profile.stats.conference_titles || 0, color: 'from-violet-500/20 to-violet-900/20 border-violet-500/40', text: 'text-violet-300', icon: '🥇', testId: 'stat-conferences' },
              { label: 'Division Titles', value: profile.stats.division_titles || 0, color: 'from-sky-500/15 to-sky-900/15 border-sky-500/30', text: 'text-sky-300', icon: '🏅', testId: 'stat-divisions' },
              { label: 'Consolations', value: profile.stats.consolations_won || 0, color: 'from-emerald-500/15 to-emerald-900/15 border-emerald-500/30', text: 'text-emerald-300', icon: '🎖', testId: 'stat-consolations' },
              { label: 'Playoff Apps', value: profile.stats.playoff_appearances || 0, color: 'from-slate-500/10 to-slate-900/10 border-slate-500/30', text: 'text-slate-300', icon: '⭐', testId: 'stat-playoffs' },
            ].map((s) => (
              <div
                key={s.label}
                data-testid={s.testId}
                className={`rounded-xl p-4 bg-gradient-to-br ${s.color} border`}
              >
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-lg leading-none">{s.icon}</span>
                  <div className="text-[10px] uppercase text-white/60 tracking-wider">{s.label}</div>
                </div>
                <div className={`text-3xl font-black tabular-nums ${s.text}`}>{s.value}</div>
              </div>
            ))}
          </div>
        )}

        {/* Rating tier card */}
        {rating && (
          <section data-testid="profile-rating-card">
            <div className="flex items-center gap-2 mb-4">
              <Activity size={18} className="text-cyan-300" />
              <h2 className="font-heading text-xl font-bold text-white tracking-wide">
                SKILL RATING
              </h2>
            </div>
            <div
              className={`rounded-2xl p-6 bg-gradient-to-br ${TIER_STYLE[rating.tier]?.bg || 'from-zinc-500/10 to-zinc-900/10'} border ${TIER_STYLE[rating.tier]?.border || 'border-white/10'} flex items-center justify-between gap-4 flex-wrap`}
              data-testid="profile-rating-tile"
            >
              <div className="flex items-center gap-4">
                <div className={`text-5xl font-black tabular-nums ${TIER_STYLE[rating.tier]?.text || 'text-white'}`}>
                  {Math.round(rating.rating)}
                </div>
                <div>
                  <div className="text-[10px] uppercase text-white/60 tracking-wider mb-1">
                    Lifetime ELO ({rating.teams_count} team{rating.teams_count === 1 ? '' : 's'})
                  </div>
                  <Badge
                    className={`text-base px-3 py-1 ${TIER_STYLE[rating.tier]?.bg ? 'bg-black/30' : 'bg-white/10'} ${TIER_STYLE[rating.tier]?.text || 'text-white'} ${TIER_STYLE[rating.tier]?.border || 'border-white/20'} border`}
                    data-testid="profile-rating-tier"
                  >
                    {rating.tier}
                  </Badge>
                  <div className="text-xs text-white/60 mt-1">
                    Top {Math.max(0.1, (100 - rating.percentile).toFixed(1))}% across all players
                  </div>
                </div>
              </div>
              <div className="text-right">
                <div className="text-[10px] uppercase text-white/60 tracking-wider">Peak Rating</div>
                <div className="text-3xl font-black text-white tabular-nums">
                  {Math.round(rating.peak_rating)}
                </div>
              </div>
            </div>
          </section>
        )}

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
              {profile.trophies.map((t, idx) => {
                const palette = (() => {
                  switch (t.type) {
                    case 'championship':
                      return { bg: 'from-amber-500/30 to-amber-900/30 border-amber-400/60', icon: 'text-amber-400', emoji: '🏆' };
                    case 'runner_up':
                      return { bg: 'from-slate-400/25 to-slate-800/25 border-slate-300/50', icon: 'text-slate-200', emoji: '🥈' };
                    case 'conference':
                      return { bg: 'from-violet-500/25 to-violet-900/25 border-violet-400/50', icon: 'text-violet-300', emoji: '🥇' };
                    case 'division':
                      return { bg: 'from-sky-500/20 to-sky-900/20 border-sky-400/40', icon: 'text-sky-300', emoji: '🏅' };
                    case 'consolation':
                      return { bg: 'from-emerald-500/20 to-emerald-900/20 border-emerald-400/40', icon: 'text-emerald-300', emoji: '🎖' };
                    case 'regular_season_first':
                      return { bg: 'from-yellow-500/25 to-yellow-900/25 border-yellow-400/55', icon: 'text-yellow-300', emoji: '🥇' };
                    case 'regular_season_second':
                      return { bg: 'from-zinc-400/25 to-zinc-800/25 border-zinc-300/50', icon: 'text-zinc-200', emoji: '🥈' };
                    case 'regular_season_third':
                      return { bg: 'from-orange-600/25 to-orange-900/25 border-orange-400/50', icon: 'text-orange-300', emoji: '🥉' };
                    default:
                      return { bg: 'from-sky-500/15 to-sky-900/15 border-sky-500/30', icon: 'text-sky-400', emoji: '🏆' };
                  }
                })();
                const labelPrefix = palette.emoji;
                // Private league entries: render name as plain text (no link)
                const teamInner = (
                  <>
                    <div className="text-white font-bold">{t.team_name}</div>
                    <div className="text-[#A1A1AA] text-xs mt-0.5 flex items-center gap-1.5">
                      {t.league_is_private && <Lock size={10} className="text-[#A1A1AA]" />}
                      {t.league_name}
                    </div>
                  </>
                );
                return (
                  <div
                    key={`${t.earned_by_user_id || 'current'}-${t.league_id || 'private'}-${t.type}-${t.season_year || idx}`}
                    data-testid={`trophy-${t.type}-${idx}`}
                    className={`rounded-xl p-4 bg-gradient-to-br ${palette.bg} border`}
                  >
                    <div className="flex items-start gap-2 mb-2">
                      <span className="text-xl leading-none">{labelPrefix}</span>
                      <div className="text-xs uppercase text-white/70 tracking-wider">
                        {t.label}
                      </div>
                    </div>
                    {!t.league_is_private && t.league_id ? (
                      <Link
                        to={`/leagues/${t.league_id}`}
                        className="hover:text-[#00D2FF] block"
                        data-testid={`trophy-team-link-${idx}`}
                      >
                        {teamInner}
                      </Link>
                    ) : (
                      <div data-testid={`trophy-team-static-${idx}`}>{teamInner}</div>
                    )}
                    {t.xp_award && t.xp_award.base_xp > 0 && (
                      <div className="text-white/70 text-xs mt-2">
                        {t.xp_award.base_xp} XP × {t.xp_award.multiplier} = {t.xp_award.awarded_xp} XP
                        <div>{t.xp_award.reason}</div>
                      </div>
                    )}
                    {t.earned_at && (
                      <div className="text-[#52525B] text-[10px] mt-1">
                        {new Date(t.earned_at).toLocaleDateString()}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </section>
        )}

        {/* Active Leagues */}
        {profile.active_leagues?.length > 0 && (
          <section data-testid="profile-active-leagues">
            <div className="flex items-center gap-2 mb-4">
              <Shield size={18} className="text-[#00D2FF]" />
              <h2 className="font-heading text-xl font-bold text-white tracking-wide">
                ACTIVE LEAGUES
              </h2>
              <Badge className="bg-[#00D2FF]/20 text-[#00D2FF] border-[#00D2FF]/40">
                {profile.active_leagues.length}
              </Badge>
            </div>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {profile.active_leagues.map((t) => {
                const inner = (
                  <>
                    <div className="flex items-center justify-between mb-2">
                      <Badge className="bg-white/5 text-[#A1A1AA] border-white/10 text-[10px]">
                        {(t.league_format || 'redraft').toUpperCase()}
                      </Badge>
                      <span className="text-xs text-[#52525B] tabular-nums">
                        #{t.rank ?? '—'}/{t.total_teams}
                      </span>
                    </div>
                    <div className="text-white font-bold text-base mb-0.5">{t.team_name}</div>
                    <div className="text-[#A1A1AA] text-xs mb-3 flex items-center gap-1.5">
                      {t.league_is_private && <Lock size={10} className="text-[#A1A1AA]" />}
                      {t.league_name}
                    </div>
                    <div className="flex items-baseline justify-between">
                      <div className="text-[#00D2FF] font-bold text-xl tabular-nums">
                        {t.points_for.toFixed(1)}
                        <span className="text-[10px] text-[#52525B] font-normal"> PF</span>
                      </div>
                      <span className="text-[#A1A1AA] text-xs">
                        {t.wins}–{t.losses}–{t.ties}
                      </span>
                    </div>
                  </>
                );
                // Private leagues: render as static (non-linkable) card
                if (t.league_is_private) {
                  return (
                    <div
                      key={t.team_id}
                      data-testid={`profile-active-league-private-${t.team_id}`}
                      className="block bg-white/5 border border-white/10 rounded-xl p-4 opacity-90 cursor-default"
                    >
                      {inner}
                    </div>
                  );
                }
                return (
                  <Link
                    key={t.team_id}
                    to={`/roster?team_id=${t.team_id}`}
                    data-testid={`profile-active-league-link-${t.team_id}`}
                    className="block bg-white/5 border border-white/10 rounded-xl p-4 hover:border-[#00D2FF]/40 transition-colors"
                  >
                    {inner}
                  </Link>
                );
              })}
            </div>
          </section>
        )}

        {/* All Teams (full history including archived) */}
        <section data-testid="profile-all-teams">
          <div className="flex items-center gap-2 mb-4">
            <Award size={18} className="text-[#A1A1AA]" />
            <h2 className="font-heading text-xl font-bold text-white tracking-wide">
              ALL TEAMS
            </h2>
          </div>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {profile.teams.map((t) => {
              const inner = (
                <>
                  <div className="flex items-center justify-between mb-2">
                    <Badge className="bg-white/5 text-[#A1A1AA] border-white/10 text-[10px]">
                      {(t.league_format || 'redraft').toUpperCase()}
                    </Badge>
                    <span className="text-xs text-[#52525B] tabular-nums">
                      #{t.rank ?? '—'}/{t.total_teams}
                    </span>
                  </div>
                  <div className="text-white font-bold text-base mb-0.5">{t.team_name}</div>
                  <div className="text-[#A1A1AA] text-xs mb-3 flex items-center gap-1.5">
                    {t.league_is_private && <Lock size={10} className="text-[#A1A1AA]" />}
                    {t.league_name}
                  </div>
                  <div className="flex items-baseline justify-between">
                    <div className="text-[#00D2FF] font-bold text-xl tabular-nums">
                      {t.points_for.toFixed(1)}
                      <span className="text-[10px] text-[#52525B] font-normal"> PF</span>
                    </div>
                    <span className="text-[#A1A1AA] text-xs">
                      {t.wins}–{t.losses}–{t.ties}
                    </span>
                  </div>
                </>
              );
              if (t.league_is_private) {
                return (
                  <div
                    key={t.team_id}
                    data-testid={`profile-team-private-${t.team_id}`}
                    className="block bg-white/5 border border-white/10 rounded-xl p-4 opacity-90 cursor-default"
                  >
                    {inner}
                  </div>
                );
              }
              return (
                <Link
                  key={t.team_id}
                  to={`/roster?team_id=${t.team_id}`}
                  data-testid={`profile-team-link-${t.team_id}`}
                  className="block bg-white/5 border border-white/10 rounded-xl p-4 hover:border-[#00D2FF]/40 transition-colors"
                >
                  {inner}
                </Link>
              );
            })}
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
