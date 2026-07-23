/**
 * Iter 232N.60 — Sandbox League Top Bar.
 *
 * When a platform admin is viewing a sandbox league (`is_test_sandbox=true`),
 * this sticky top strip announces the sandbox context AND exposes a
 * one-click "Jump in as any test user" dropdown so the admin can hop
 * between users without leaving the league page.
 *
 * The strip is admin-only + sandbox-only:
 *   • Fetches `/admin/test-sandbox/leagues` (403 for non-admin → renders
 *     nothing quietly)
 *   • Only mounts if the current league_id is on that list
 *   • Fetches `/admin/test-sandbox/test-users?league_id=X` for the picker
 *
 * On selection: fires `/auth/impersonate-start` and reloads /dashboard so
 * every context / hook picks up the new cookie identity, mirroring the
 * behaviour of the Admin > Test Sandbox panel.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { toast } from 'sonner';
import { FlaskConical, UserCircle2, Rewind, RefreshCw } from 'lucide-react';
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

export default function SandboxLeagueTopBar({ leagueId }) {
  const { user, refreshUser } = useAuth();
  const [isSandbox, setIsSandbox] = useState(false);
  const [leagueName, setLeagueName] = useState('');
  const [testUsers, setTestUsers] = useState([]);
  const [loading, setLoading] = useState(false);
  // Iter 232N.69 — Simulate-week state
  const [lastSimWeek, setLastSimWeek] = useState(0);
  const [simulating, setSimulating] = useState(false);

  const isAdmin =
    user?.role === 'admin' ||
    user?.permission_tier === 'admin' ||
    user?.permission_tier === 'senior_admin';
  // While impersonating, don't render (the impersonated identity is a
  // regular user role — no admin endpoints available).
  const isImpersonating = Boolean(user?._impersonation_mode);

  const load = useCallback(async () => {
    if (!isAdmin || isImpersonating || !leagueId) return;
    setLoading(true);
    try {
      // Discovery — is this league a sandbox?
      const { data: lgData } = await api.get('/admin/test-sandbox/leagues');
      const match = (lgData?.leagues ?? []).find((l) => l.id === leagueId);
      if (!match) {
        setIsSandbox(false);
        return;
      }
      setIsSandbox(true);
      setLeagueName(match.name);
      setLastSimWeek(match.sandbox_last_sim_week || 0);
      const { data: uData } = await api.get('/admin/test-sandbox/test-users', {
        params: { league_id: leagueId },
      });
      setTestUsers(uData?.users ?? []);
    } catch (_e) {
      // Silently ignore — non-admin or league not in sandbox
      setIsSandbox(false);
    } finally {
      setLoading(false);
    }
  }, [isAdmin, isImpersonating, leagueId]);

  useEffect(() => {
    load();
  }, [load]);

  const sortedUsers = useMemo(() => {
    return [...testUsers].sort((a, b) => (a.name || '').localeCompare(b.name || ''));
  }, [testUsers]);

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
      // Hard reload to /dashboard so every context picks up the new
      // cookie identity — mirrors the Admin > Test Sandbox panel.
      window.location.href = '/dashboard';
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Failed to enter test user');
    }
  };

  // Iter 232N.69 — Fires a single-week simulation on the backend.
  // Successive clicks build up a season (Week 1, Week 2, …) so the
  // admin can populate multi-week trophies and streak widgets.
  const simulateWeek = async () => {
    setSimulating(true);
    try {
      const { data } = await api.post(
        `/admin/test-sandbox/leagues/${leagueId}/simulate-week`,
        {},
      );
      const matchupCount = (data.matchups || []).filter((m) => m.away !== 'BYE').length;
      toast.success(
        `Simulated Week ${data.week} — ${matchupCount} matchup${matchupCount === 1 ? '' : 's'} scored${data.replayed ? ' (replayed)' : ''}`,
      );
      setLastSimWeek(data.week);
      // Nudge every page that renders standings/dashboards to refetch.
      window.dispatchEvent(new CustomEvent('sandbox:sim-week', { detail: data }));
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Simulate failed');
    } finally {
      setSimulating(false);
    }
  };

  const resetSimulation = async () => {
    if (!window.confirm(
      `Reset all simulated results for "${leagueName}"? Every team's W-L-T + points return to zero.`,
    )) return;
    setSimulating(true);
    try {
      const { data } = await api.post(
        `/admin/test-sandbox/leagues/${leagueId}/reset-simulation`,
        {},
      );
      toast.success(`Simulation reset — ${data.matchups_deleted} matchup(s) cleared`);
      setLastSimWeek(0);
      window.dispatchEvent(new CustomEvent('sandbox:sim-week', { detail: null }));
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Reset failed');
    } finally {
      setSimulating(false);
    }
  };

  if (!isAdmin || isImpersonating || !isSandbox) return null;

  return (
    <div
      className="sticky top-0 z-40 border-b border-fuchsia-500/40 bg-fuchsia-950/40 backdrop-blur-sm"
      data-testid="sandbox-league-top-bar"
    >
      <div className="max-w-7xl mx-auto px-4 py-2 flex items-center gap-3 flex-wrap">
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
          <span
            className="text-[11px] text-fuchsia-200/70 hidden md:inline"
            data-testid="sandbox-topbar-tagline"
          >
            {lastSimWeek === 0 ? (
              <>This is a test league. Simulate a week of matchups to see live standings.</>
            ) : (
              <>Through Week&nbsp;{lastSimWeek} — dashboards + standings are populated with fake data.</>
            )}
          </span>
        </div>
        <div className="ml-auto flex items-center gap-2 flex-wrap">
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
          {lastSimWeek > 0 && (
            <Button
              size="sm"
              variant="ghost"
              className="h-8 text-[10px] text-fuchsia-200 hover:text-fuchsia-50"
              onClick={resetSimulation}
              disabled={simulating}
              data-testid="sandbox-topbar-reset-btn"
              title="Reset every team back to 0-0-0"
            >
              <Rewind className="h-3 w-3 mr-0.5" /> Reset
            </Button>
          )}
          <UserCircle2 className="h-3.5 w-3.5 text-fuchsia-300 shrink-0" />
          <Select onValueChange={jumpIn} disabled={loading || sortedUsers.length === 0}>
            <SelectTrigger
              className="h-8 text-xs min-w-[220px] bg-fuchsia-950/50 border-fuchsia-500/40 text-fuchsia-50"
              data-testid="sandbox-topbar-user-select"
            >
              <SelectValue
                placeholder={
                  loading ? 'Loading test users…' : 'Jump in as a test user…'
                }
              />
            </SelectTrigger>
            <SelectContent>
              {sortedUsers.map((u) => (
                <SelectItem
                  key={u.id}
                  value={u.id}
                  textValue={`${u.name} — ${u.team_name}`}
                >
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
    </div>
  );
}
