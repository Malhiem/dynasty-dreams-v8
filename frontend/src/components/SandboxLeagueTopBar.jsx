/**
 * Iter 232N.60 / 79 — Sandbox League Top Bar (persistent + progression rail).
 *
 * Persistent sticky banner shown on EVERY page inside a sandbox league
 * for platform admins (not for impersonated test users).
 *
 * Derives the active league id from (in order):
 *   1. `leagueId` prop (League Detail page)
 *   2. `useParams()` `id` or `leagueId` (route params)
 *   3. `localStorage.dd_active_league_id` (active-league fallback)
 *
 * Fetches `/admin/test-sandbox/leagues/{id}/status` to render a
 * 4-step progression rail:
 *   1. Setup   (roster_spots > 0 + matchups_per_week > 0 + teams >= 2)
 *   2. Draft   (real draft with status="completed"; "Simulate draft" shortcut)
 *   3. Season  (Simulate Week N; only clickable once draft is complete)
 *   4. Playoffs (Seed & Sim Playoffs; only unlocks at Week 17+)
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import { toast } from 'sonner';
import {
  FlaskConical, UserCircle2, Rewind, RefreshCw, Trophy,
  Check, Circle, Users, ClipboardList, CalendarClock, Zap,
  FileDown, CalendarPlus,
} from 'lucide-react';
import api from '@/lib/api';
import { useAuth } from '@/contexts/AuthContext';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
// Iter 232N.81 — Bracket visualizer modal.
import SandboxPlayoffBracketModal from './SandboxPlayoffBracketModal';

function _readActiveLeagueId() {
  try {
    // Iter 232N.79 — Prefer the last-seen sandbox league id so the
    // banner keeps rendering when the admin navigates from a sandbox
    // League Detail page → Dashboard / Standings / etc. Falls back to
    // the normal active-league key for the non-sandbox case.
    return (
      localStorage.getItem('dd_last_sandbox_league_id') ||
      localStorage.getItem('dd_active_league_id') ||
      null
    );
  } catch { return null; }
}

function StepPill({ index, label, icon: Icon, state, testid }) {
  const isDone = state === 'done';
  const isActive = state === 'active';
  const isLocked = state === 'locked';
  const cls = isDone
    ? 'bg-emerald-500/15 text-emerald-100 border-emerald-500/40'
    : isActive
      ? 'bg-fuchsia-500/25 text-fuchsia-50 border-fuchsia-400/50 shadow-[0_0_0_1px_rgba(232,121,249,0.35)]'
      : 'bg-black/20 text-fuchsia-200/50 border-fuchsia-500/20';
  const Ico = isDone ? Check : (isLocked ? Circle : Icon);
  return (
    <div
      className={`flex items-center gap-1 rounded-full border pl-1.5 pr-2 py-0.5 text-[10px] ${cls}`}
      data-testid={testid}
      data-step-state={state}
    >
      <span className="rounded-full bg-black/30 h-4 w-4 flex items-center justify-center">
        <Ico className="h-2.5 w-2.5" />
      </span>
      <span className="font-medium">{index}. {label}</span>
    </div>
  );
}

export default function SandboxLeagueTopBar({ leagueId: leagueIdProp }) {
  const { user, refreshUser } = useAuth();
  const params = useParams();
  const routeLeagueId = params?.id || params?.leagueId || null;
  const [fallbackLeagueId, setFallbackLeagueId] = useState(_readActiveLeagueId);
  const leagueId = leagueIdProp || routeLeagueId || fallbackLeagueId;

  const [isSandbox, setIsSandbox] = useState(false);
  const [leagueName, setLeagueName] = useState('');
  const [testUsers, setTestUsers] = useState([]);
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState(null);   // 4-step progression payload
  const [simulating, setSimulating] = useState(false);
  const [drafting, setDrafting] = useState(false);
  const [targetWeek, setTargetWeek] = useState('');
  const [seedingPlayoffs, setSeedingPlayoffs] = useState(false);
  // Iter 232N.81 — Bracket modal state. Auto-opens after seed-playoffs
  // succeeds; reopenable via the champion badge.
  const [bracketOpen, setBracketOpen] = useState(false);
  const [bracketSeed, setBracketSeed] = useState(null);
  // Iter 232N.83 — Roll to next season + PDF download state.
  const [rolling, setRolling] = useState(false);
  const [downloadingRecap, setDownloadingRecap] = useState(false);

  const isAdmin =
    user?.role === 'admin' ||
    user?.permission_tier === 'admin' ||
    user?.permission_tier === 'senior_admin';
  const isImpersonating = Boolean(user?._impersonation_mode);

  // Keep the localStorage fallback fresh — it's set by the league
  // switcher and by LeagueDetailPage; re-read on route change.
  useEffect(() => {
    if (!leagueIdProp && !routeLeagueId) {
      setFallbackLeagueId(_readActiveLeagueId());
    }
  }, [leagueIdProp, routeLeagueId]);

  const load = useCallback(async () => {
    if (!isAdmin || isImpersonating || !leagueId) {
      setIsSandbox(false);
      return;
    }
    setLoading(true);
    try {
      const { data: lgData } = await api.get('/admin/test-sandbox/leagues');
      const match = (lgData?.leagues ?? []).find((l) => l.id === leagueId);
      if (!match) {
        setIsSandbox(false);
        // If the caller passed an explicit non-sandbox league via URL
        // params, clear the sticky memory so we stop trying to render.
        if (routeLeagueId && routeLeagueId === leagueId) {
          try { localStorage.removeItem('dd_last_sandbox_league_id'); }
          catch { /* noop */ }
        }
        return;
      }
      setIsSandbox(true);
      setLeagueName(match.name);
      // Iter 232N.79 — Remember the last-viewed sandbox so the banner
      // survives page navigation (Dashboard, Standings, etc.). Cleared
      // whenever the admin views a non-sandbox league (see below).
      try { localStorage.setItem('dd_last_sandbox_league_id', leagueId); }
      catch { /* noop */ }
      const [statusRes, usersRes] = await Promise.all([
        api.get(`/admin/test-sandbox/leagues/${leagueId}/status`).catch(() => null),
        api.get('/admin/test-sandbox/test-users', {
          params: { league_id: leagueId },
        }).catch(() => null),
      ]);
      if (statusRes?.data) setStatus(statusRes.data);
      setTestUsers(usersRes?.data?.users ?? []);
    } catch (_e) {
      setIsSandbox(false);
    } finally {
      setLoading(false);
    }
  }, [isAdmin, isImpersonating, leagueId, routeLeagueId]);

  useEffect(() => { load(); }, [load]);

  const sortedUsers = useMemo(
    () => [...testUsers].sort((a, b) => (a.name || '').localeCompare(b.name || '')),
    [testUsers],
  );

  const jumpIn = async (userId) => {
    const target = testUsers.find((u) => u.id === userId);
    if (!target) return;
    try {
      await api.post('/auth/impersonate-start', {
        target_user_id: target.id,
        reason: `Sandbox top-bar switch — ${leagueName} · ${target.team_name}`,
      });
      toast.success(`Now acting as ${target.name} (${target.team_name})`);
      await refreshUser?.();
      window.location.href = '/dashboard';
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Failed to enter test user');
    }
  };

  const simulateDraft = async () => {
    setDrafting(true);
    try {
      const { data } = await api.post(
        `/admin/test-sandbox/leagues/${leagueId}/simulate-draft`,
        {},
      );
      toast.success(
        `Draft simulated — ${data.total_picks} picks across ${data.teams_drafted} teams`,
        { duration: 5000 },
      );
      await load();
      window.dispatchEvent(new CustomEvent('sandbox:draft-simulated', { detail: data }));
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Simulate draft failed');
    } finally {
      setDrafting(false);
    }
  };

  const simulateWeek = async () => {
    setSimulating(true);
    try {
      const { data } = await api.post(
        `/admin/test-sandbox/leagues/${leagueId}/simulate-week`, {},
      );
      const matchupCount = (data.matchups || []).filter((m) => m.away !== 'BYE').length;
      toast.success(
        `Simulated Week ${data.week} — ${matchupCount} matchup${matchupCount === 1 ? '' : 's'} scored${data.replayed ? ' (replayed)' : ''}`,
      );
      await load();
      window.dispatchEvent(new CustomEvent('sandbox:sim-week', { detail: data }));
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Simulate failed');
    } finally {
      setSimulating(false);
    }
  };

  const simulateToWeek = async () => {
    const target = parseInt(targetWeek, 10);
    const lastSim = status?.last_sim_week || 0;
    if (!target || target <= lastSim) {
      toast.error(`Pick a week later than the last simulated week (${lastSim}).`);
      return;
    }
    setSimulating(true);
    try {
      const { data } = await api.post(
        `/admin/test-sandbox/leagues/${leagueId}/simulate-to-week`,
        { target_week: target },
      );
      const runCount = (data.weeks_run || []).length;
      toast.success(
        `Simulated ${runCount} week${runCount === 1 ? '' : 's'} · now through Week ${data.target_week}`,
      );
      setTargetWeek('');
      await load();
      window.dispatchEvent(new CustomEvent('sandbox:sim-week', { detail: data }));
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Simulate-to-week failed');
    } finally {
      setSimulating(false);
    }
  };

  const seedPlayoffs = async () => {
    setSeedingPlayoffs(true);
    try {
      const { data } = await api.post(
        `/admin/test-sandbox/leagues/${leagueId}/seed-playoffs`, {},
      );
      toast.success(
        `Playoffs seeded · ${data.num_playoff_teams} teams · ${data.rounds_played} rounds · Champion: ${data.champion}`,
        { duration: 6000 },
      );
      // Iter 232N.81 — Auto-open the bracket modal with the seed
      // response so admins immediately see QF → SF → Final matchups.
      setBracketSeed(data);
      setBracketOpen(true);
      await load();
      window.dispatchEvent(new CustomEvent('sandbox:playoffs-seeded', { detail: data }));
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Seed playoffs failed');
    } finally {
      setSeedingPlayoffs(false);
    }
  };

  // Iter 232N.83 — Download the one-page season recap PDF. Uses a
  // blob roundtrip so we can name the file and trigger a native
  // browser download without leaving the page.
  const downloadRecap = async () => {
    setDownloadingRecap(true);
    try {
      const res = await api.get(
        `/admin/test-sandbox/leagues/${leagueId}/season-recap.pdf`,
        { responseType: 'blob' },
      );
      const url = URL.createObjectURL(res.data);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${(leagueName || 'sandbox').toLowerCase().replace(/\s+/g, '_')}_recap.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      toast.success('Season recap downloaded');
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Failed to download recap');
    } finally {
      setDownloadingRecap(false);
    }
  };

  // Iter 232N.83 — Roll the sandbox to the next season. Preserves
  // rosters + structure; wipes matchups, champion, sim state;
  // increments current_season_year; ages players whose birthday has
  // passed since the previous roll.
  const rollToNextSeason = async () => {
    if (!window.confirm(
      `Roll "${leagueName}" to the next season?\n\n` +
      `• Rosters + structure preserved\n` +
      `• Matchups + champion cleared\n` +
      `• Players age up if their birthday has passed`,
    )) return;
    setRolling(true);
    try {
      const { data } = await api.post(
        `/admin/test-sandbox/leagues/${leagueId}/roll-to-next-season`,
        { age_players_by_birthday: true },
      );
      toast.success(
        `Season rolled: ${data.old_season_year} → ${data.new_season_year} · ${data.players_aged} player${data.players_aged === 1 ? '' : 's'} aged up`,
        { duration: 6000 },
      );
      await load();
      window.dispatchEvent(new CustomEvent('sandbox:rolled-season', { detail: data }));
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Roll failed');
    } finally {
      setRolling(false);
    }
  };


  const resetSimulation = async () => {
    if (!window.confirm(
      `Reset "${leagueName}"? This wipes rosters, matchups, and the champion — every step returns to Day 1.`,
    )) return;
    setSimulating(true);
    try {
      const { data } = await api.post(
        `/admin/test-sandbox/leagues/${leagueId}/reset-simulation`, {},
      );
      toast.success(`Sandbox reset — ${data.matchups_deleted} matchup(s) cleared`);
      setTargetWeek('');
      await load();
      window.dispatchEvent(new CustomEvent('sandbox:sim-week', { detail: null }));
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Reset failed');
    } finally {
      setSimulating(false);
    }
  };

  if (!isAdmin || isImpersonating || !isSandbox) return null;

  const s = status || {};
  const activeStep = s.active_step || 1;
  const stepState = (idx) => {
    if (idx < activeStep) return 'done';
    if (idx === activeStep) return 'active';
    return 'locked';
  };
  const lastSimWeek = s.last_sim_week || 0;
  const draftDone = Boolean(s.draft_done);
  const playoffsSeeded = Boolean(s.playoffs_seeded);
  const canSimulateWeek = draftDone && !playoffsSeeded;
  const canSeedPlayoffs = draftDone && lastSimWeek >= 17 && !playoffsSeeded;
  const showResetButton = draftDone || lastSimWeek > 0 || playoffsSeeded;

  return (
    <div
      className="sticky top-0 z-40 border-b border-fuchsia-500/40 bg-fuchsia-950/40 backdrop-blur-sm"
      data-testid="sandbox-league-top-bar"
    >
      <div className="max-w-7xl mx-auto px-4 py-2 flex flex-col gap-2">
        <div className="flex items-center gap-3 flex-wrap">
          <div className="flex items-center gap-2 min-w-0">
            <FlaskConical className="h-4 w-4 text-fuchsia-300 shrink-0" />
            <span className="text-xs font-semibold text-fuchsia-100 truncate">
              Sandbox mode
            </span>
            <Badge
              variant="outline"
              className="text-[10px] bg-fuchsia-500/15 text-fuchsia-200 border-fuchsia-500/40"
            >
              {leagueName}
            </Badge>
          </div>
          <div
            className="flex items-center gap-1 flex-wrap"
            data-testid="sandbox-progression-rail"
          >
            <StepPill index={1} label="Setup" icon={Users}
              state={stepState(1)} testid="sandbox-step-1-setup" />
            <span className="text-fuchsia-500/40 text-[10px]">→</span>
            <StepPill index={2} label="Draft" icon={ClipboardList}
              state={stepState(2)} testid="sandbox-step-2-draft" />
            <span className="text-fuchsia-500/40 text-[10px]">→</span>
            <StepPill index={3} label="Season" icon={CalendarClock}
              state={stepState(3)} testid="sandbox-step-3-season" />
            <span className="text-fuchsia-500/40 text-[10px]">→</span>
            <StepPill index={4} label="Playoffs" icon={Trophy}
              state={stepState(4)} testid="sandbox-step-4-playoffs" />
          </div>
          <div className="ml-auto flex items-center gap-2">
            <UserCircle2 className="h-3.5 w-3.5 text-fuchsia-300 shrink-0" />
            <Select onValueChange={jumpIn} disabled={loading || sortedUsers.length === 0}>
              <SelectTrigger
                className="h-8 text-xs min-w-[200px] bg-fuchsia-950/50 border-fuchsia-500/40 text-fuchsia-50"
                data-testid="sandbox-topbar-user-select"
              >
                <SelectValue placeholder={loading ? 'Loading…' : 'Jump in as test user…'} />
              </SelectTrigger>
              <SelectContent>
                {sortedUsers.map((u) => (
                  <SelectItem key={u.id} value={u.id} textValue={`${u.name} — ${u.team_name}`}>
                    <span className="text-xs">
                      {u.name}
                      <span className="text-muted-foreground ml-1">
                        · {u.team_name}
                      </span>
                    </span>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>

        {/* Contextual actions row — changes based on the active step */}
        <div className="flex items-center gap-2 flex-wrap">
          {/* Step 2 — Draft */}
          {!draftDone && (
            <>
              <span
                className="text-[11px] text-fuchsia-200/80"
                data-testid="sandbox-step-hint-draft"
              >
                Schedule a real draft, or shortcut here:
              </span>
              <Button
                size="sm"
                variant="outline"
                className="h-8 text-[11px] bg-fuchsia-500/20 border-fuchsia-500/40 text-fuchsia-50 hover:bg-fuchsia-500/30"
                onClick={simulateDraft}
                disabled={drafting}
                data-testid="sandbox-topbar-simulate-draft-btn"
                title="Auto-draft every team using the top players from the DB"
              >
                {drafting ? (
                  <RefreshCw className="h-3 w-3 mr-1 animate-spin" />
                ) : (
                  <Zap className="h-3 w-3 mr-1" />
                )}
                Simulate draft
              </Button>
            </>
          )}

          {/* Step 3 — Regular season (enabled once draft is complete) */}
          {canSimulateWeek && (
            <>
              <Button
                size="sm"
                variant="outline"
                className="h-8 text-[11px] bg-fuchsia-500/20 border-fuchsia-500/40 text-fuchsia-50 hover:bg-fuchsia-500/30"
                onClick={simulateWeek}
                disabled={simulating}
                data-testid="sandbox-topbar-simulate-btn"
              >
                {simulating ? (
                  <RefreshCw className="h-3 w-3 mr-1 animate-spin" />
                ) : null}
                Simulate Week&nbsp;{lastSimWeek + 1}
              </Button>
              <div className="flex items-center gap-1"
                   data-testid="sandbox-topbar-sim-to-week-group">
                <span className="text-[10px] text-fuchsia-200/80">to</span>
                <input
                  type="number"
                  min={Math.max(1, lastSimWeek + 1)}
                  max={30}
                  value={targetWeek}
                  onChange={(e) => setTargetWeek(e.target.value)}
                  placeholder="Wk"
                  className="h-8 w-14 rounded-md border border-fuchsia-500/40 bg-fuchsia-950/50 text-fuchsia-50 text-[11px] px-2 focus:outline-none focus:ring-1 focus:ring-fuchsia-400"
                  data-testid="sandbox-topbar-target-week"
                />
                <Button
                  size="sm"
                  variant="outline"
                  className="h-8 text-[11px] bg-fuchsia-500/10 border-fuchsia-500/40 text-fuchsia-50 hover:bg-fuchsia-500/30"
                  onClick={simulateToWeek}
                  disabled={simulating || !targetWeek}
                  data-testid="sandbox-topbar-simulate-to-week-btn"
                  title={`Simulate every week from ${lastSimWeek + 1} through the target in one shot`}
                >
                  Go
                </Button>
              </div>
            </>
          )}

          {/* Step 4 — Playoffs */}
          {canSeedPlayoffs && (
            <Button
              size="sm"
              variant="outline"
              className="h-8 text-[11px] bg-amber-500/20 border-amber-400/50 text-amber-50 hover:bg-amber-500/30"
              onClick={seedPlayoffs}
              disabled={seedingPlayoffs}
              data-testid="sandbox-topbar-seed-playoffs-btn"
              title="Auto-seed and simulate the entire single-elimination playoff bracket"
            >
              {seedingPlayoffs ? (
                <RefreshCw className="h-3 w-3 mr-1 animate-spin" />
              ) : (
                <Trophy className="h-3 w-3 mr-1" />
              )}
              Seed &amp; Sim Playoffs
            </Button>
          )}
          {playoffsSeeded && (
            <>
              <button
                type="button"
                onClick={() => { setBracketSeed(null); setBracketOpen(true); }}
                data-testid="sandbox-topbar-champion-badge"
                title="View the playoff bracket for this sandbox league"
                className="cursor-pointer focus:outline-none focus:ring-2 focus:ring-amber-400/50 rounded-full"
              >
                <Badge
                  variant="outline"
                  className="h-8 text-[11px] bg-amber-500/15 border-amber-400/50 text-amber-100 hover:bg-amber-500/25 flex items-center gap-1 px-2 transition-colors"
                >
                  <Trophy className="h-3 w-3" /> View bracket
                </Badge>
              </button>
              <Button
                size="sm"
                variant="outline"
                className="h-8 text-[11px] bg-cyan-500/15 border-cyan-500/40 text-cyan-50 hover:bg-cyan-500/25"
                onClick={downloadRecap}
                disabled={downloadingRecap}
                data-testid="sandbox-topbar-recap-btn"
                title="Download a one-page PDF recap of this season"
              >
                {downloadingRecap ? (
                  <RefreshCw className="h-3 w-3 mr-1 animate-spin" />
                ) : (
                  <FileDown className="h-3 w-3 mr-1" />
                )}
                Recap PDF
              </Button>
              <Button
                size="sm"
                variant="outline"
                className="h-8 text-[11px] bg-emerald-500/15 border-emerald-500/40 text-emerald-50 hover:bg-emerald-500/25"
                onClick={rollToNextSeason}
                disabled={rolling}
                data-testid="sandbox-topbar-roll-season-btn"
                title="Archive the current season, keep rosters, age players by birthdate, and reset sim state"
              >
                {rolling ? (
                  <RefreshCw className="h-3 w-3 mr-1 animate-spin" />
                ) : (
                  <CalendarPlus className="h-3 w-3 mr-1" />
                )}
                Roll to next season
              </Button>
            </>
          )}

          {/* Status tagline */}
          <span
            className="text-[11px] text-fuchsia-200/70 ml-auto"
            data-testid="sandbox-topbar-tagline"
          >
            {!s.has_settings
              ? 'Set roster + matchup schedule to begin.'
              : !draftDone
                ? 'Schedule a draft (or simulate one) to unlock weekly sim.'
                : playoffsSeeded
                  ? `Season complete · Champion crowned in Week ${lastSimWeek}`
                  : lastSimWeek === 0
                    ? 'Draft complete. Simulate a week to see live standings.'
                    : `Through Week ${lastSimWeek} — dashboards + standings live.`}
          </span>

          {showResetButton && (
            <Button
              size="sm"
              variant="ghost"
              className="h-8 text-[10px] text-fuchsia-200 hover:text-fuchsia-50"
              onClick={resetSimulation}
              disabled={simulating}
              data-testid="sandbox-topbar-reset-btn"
              title="Reset the sandbox back to Day 1 (empty rosters, no games, no champion)"
            >
              <Rewind className="h-3 w-3 mr-0.5" /> Reset
            </Button>
          )}
        </div>
      </div>
      {/* Iter 232N.81 — Bracket visualizer modal */}
      <SandboxPlayoffBracketModal
        open={bracketOpen}
        onClose={() => setBracketOpen(false)}
        leagueId={leagueId}
        initialData={bracketSeed}
      />
    </div>
  );
}
