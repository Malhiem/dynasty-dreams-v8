/**
 * Iter 232N.59 — Admin Test Sandbox panel.
 *
 * A single-screen dashboard for admins to:
 *   1. Spin up a throwaway test league (1-click presets or a custom
 *      form up to the format's max supported teams).
 *   2. See every existing test-sandbox league at a glance.
 *   3. Jump into any test user's account via the existing cookie-swap
 *      impersonation endpoint (`POST /auth/impersonate-start`).
 *   4. Delete a sandbox league (cascades to teams, test users, and
 *      every league_id-keyed dependent doc).
 *
 * Auth: rendered inside the Platform Admin dashboard which is already
 * admin-gated. Every backend endpoint independently re-checks admin.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  FlaskConical,
  UserCircle2,
  Trash2,
  Plus,
  RefreshCw,
  Beaker,
  LogIn,
  Copy,
  Users,
  AlertTriangle,
} from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";

interface Preset {
  key: string;
  label: string;
  description: string;
  sport: string;
  format: string;
  scoring_format: string;
  default_teams: number;
  max_teams_supported: number;
  roster_spots: number;
  keepers_allowed: number;
  salary_cap_enabled: boolean;
  salary_cap?: number;
}

interface SandboxLeague {
  id: string;
  name: string;
  preset_key: string;
  format: string;
  scoring_format: string;
  max_teams: number;
  current_teams: number;
  status: string;
  sandbox_created_by: string;
  created_at: string;
}

interface TestUser {
  id: string;
  email: string;
  name: string;
  team_id: string;
  team_name: string;
  league_id: string;
  league_name: string;
}

function humanizeKey(k: string): string {
  return k.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export default function TestSandboxPanel() {
  const { refreshUser } = useAuth();

  const [presets, setPresets] = useState<Preset[]>([]);
  const [sharedPassword, setSharedPassword] = useState<string>("");
  const [leagues, setLeagues] = useState<SandboxLeague[]>([]);
  const [testUsers, setTestUsers] = useState<TestUser[]>([]);
  const [loading, setLoading] = useState(false);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Create form
  const [selectedPresetKey, setSelectedPresetKey] = useState<string>("");
  const [customName, setCustomName] = useState<string>("");
  const [numTeams, setNumTeams] = useState<number>(0);

  const activePreset = useMemo(
    () => presets.find((p) => p.key === selectedPresetKey) ?? null,
    [presets, selectedPresetKey],
  );

  // ── Load everything ────────────────────────────────────────────
  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [pRes, lRes, uRes] = await Promise.all([
        api.get("/admin/test-sandbox/presets"),
        api.get("/admin/test-sandbox/leagues"),
        api.get("/admin/test-sandbox/test-users"),
      ]);
      const ps: Preset[] = pRes.data?.presets ?? [];
      setPresets(ps);
      setSharedPassword(pRes.data?.shared_password ?? "");
      setLeagues(lRes.data?.leagues ?? []);
      setTestUsers(uRes.data?.users ?? []);
    } catch (e: any) {
      const detail =
        e?.response?.data?.detail || e?.message || "Failed to load test sandbox";
      setError(detail);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // Auto-select first preset once presets land.
  useEffect(() => {
    if (presets.length === 0 || selectedPresetKey) return;
    setSelectedPresetKey(presets[0].key);
    setNumTeams(presets[0].default_teams);
  }, [presets, selectedPresetKey]);

  // When preset switches, snap num teams to preset default (only if
  // untouched at zero, or clamp to preset cap).
  useEffect(() => {
    if (!activePreset) return;
    setNumTeams((prev) => {
      if (prev === 0) return activePreset.default_teams;
      if (prev > activePreset.max_teams_supported)
        return activePreset.max_teams_supported;
      return prev;
    });
  }, [activePreset]);

  // ── Create league ──────────────────────────────────────────────
  const createLeague = async (opts?: { maxTeams?: boolean }) => {
    if (!activePreset) return;
    setCreating(true);
    try {
      const teamsToSeed = opts?.maxTeams
        ? activePreset.max_teams_supported
        : numTeams || activePreset.default_teams;
      const { data } = await api.post("/admin/test-sandbox/leagues", {
        preset_key: activePreset.key,
        name: customName.trim() || undefined,
        num_teams: teamsToSeed,
      });
      toast.success(
        `Sandbox '${data.league_name}' created with ${data.num_teams} test users`,
      );
      setCustomName("");
      await load();
    } catch (e: any) {
      const detail = e?.response?.data?.detail || e?.message || "Create failed";
      toast.error(detail);
    } finally {
      setCreating(false);
    }
  };

  // ── Delete league ──────────────────────────────────────────────
  const deleteLeague = async (league: SandboxLeague) => {
    const ok = window.confirm(
      `Delete "${league.name}" and its ${league.current_teams} test users? This cannot be undone.`,
    );
    if (!ok) return;
    try {
      const { data } = await api.delete(
        `/admin/test-sandbox/leagues/${league.id}`,
      );
      toast.success(
        `Deleted "${league.name}" (${data.teams_deleted} teams, ${data.test_users_deleted} users)`,
      );
      await load();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Delete failed");
    }
  };

  // ── Add extra test user ────────────────────────────────────────
  const addExtraUser = async (leagueId: string) => {
    try {
      const { data } = await api.post(
        `/admin/test-sandbox/leagues/${leagueId}/add-test-user`,
        {},
      );
      toast.success(`Added ${data.name} to sandbox`);
      await load();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Failed to add test user");
    }
  };

  // ── Impersonate a test user ────────────────────────────────────
  const impersonate = async (user: TestUser) => {
    try {
      await api.post("/auth/impersonate-start", {
        target_user_id: user.id,
        reason: `Test sandbox — ${user.league_name} · ${user.team_name}`,
      });
      toast.success(`Now acting as ${user.name} (${user.league_name})`);
      // Refresh user so the ImpersonationBanner appears + navigate to
      // the target's dashboard.
      await refreshUser?.();
      // Full page reload guarantees every context / hook picks up the
      // new cookie identity cleanly.
      window.location.href = "/dashboard";
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Failed to enter test user");
    }
  };

  const copyPassword = () => {
    if (!sharedPassword) return;
    try {
      navigator.clipboard.writeText(sharedPassword);
      toast.success("Password copied");
    } catch {
      toast.error("Clipboard access denied");
    }
  };

  // ── Group test users by league for the impersonation dropdowns ─
  const usersByLeague = useMemo(() => {
    const m: Record<string, TestUser[]> = {};
    for (const u of testUsers) {
      if (!u.league_id) continue;
      (m[u.league_id] ||= []).push(u);
    }
    return m;
  }, [testUsers]);

  return (
    <Card className="bg-card border-border" data-testid="test-sandbox-panel">
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-3 flex-wrap">
          <div>
            <CardTitle className="flex items-center gap-2 text-base">
              <FlaskConical className="h-4 w-4 text-fuchsia-400" />
              Admin Test Sandbox
              {leagues.length > 0 && (
                <Badge
                  variant="outline"
                  className="text-[10px] bg-fuchsia-500/10 text-fuchsia-300 border-fuchsia-500/30"
                  data-testid="sandbox-league-count"
                >
                  {leagues.length} sandbox{leagues.length === 1 ? "" : "es"}
                </Badge>
              )}
            </CardTitle>
            <CardDescription className="text-[11px]">
              Spin up throwaway leagues + test users and hop between them to
              simulate managers, commissioners, waivers, drafts &amp; trades.
              Test users are auto-flagged so impersonation is scoped to them.
            </CardDescription>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={load}
            disabled={loading}
            data-testid="test-sandbox-refresh"
            className="h-8"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
          </Button>
        </div>
      </CardHeader>

      <CardContent className="space-y-5">
        {error && (
          <div
            className="flex items-center gap-2 text-xs text-rose-400 rounded-md border border-rose-500/30 bg-rose-500/5 p-2"
            data-testid="test-sandbox-error"
          >
            <AlertTriangle className="h-3.5 w-3.5" />
            {error}
          </div>
        )}

        {sharedPassword && (
          <div
            className="flex items-center justify-between gap-2 text-[11px] rounded-md border border-border/60 bg-secondary/30 p-2.5"
            data-testid="test-sandbox-shared-password"
          >
            <div>
              <span className="text-muted-foreground">Shared test password:</span>{" "}
              <code className="font-mono font-semibold text-foreground">
                {sharedPassword}
              </code>
              <span className="text-muted-foreground ml-1">
                (all sandbox users share this — you can also skip login and use
                Impersonate)
              </span>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={copyPassword}
              className="h-6 shrink-0"
              data-testid="test-sandbox-copy-password"
            >
              <Copy className="h-3 w-3" />
            </Button>
          </div>
        )}

        {/* ── Preset picker + create form ─────────────────────── */}
        <section className="space-y-3">
          <div className="text-[10px] uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
            <Beaker className="h-3 w-3" />
            Create a new sandbox
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
            {presets.map((p) => (
              <button
                type="button"
                key={p.key}
                onClick={() => {
                  setSelectedPresetKey(p.key);
                  setNumTeams(p.default_teams);
                }}
                className={`rounded-lg border p-3 text-left transition-colors ${
                  selectedPresetKey === p.key
                    ? "border-fuchsia-500/60 bg-fuchsia-500/5"
                    : "border-border/60 bg-card/40 hover:bg-secondary/40"
                }`}
                data-testid={`test-sandbox-preset-${p.key}`}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="text-xs font-semibold truncate">{p.label}</span>
                  <Badge variant="outline" className="text-[9px] shrink-0">
                    {humanizeKey(p.format)}
                  </Badge>
                </div>
                <div className="text-[10px] text-muted-foreground mt-1 leading-snug">
                  {p.description}
                </div>
                <div className="text-[10px] text-muted-foreground mt-1">
                  <span className="text-foreground font-medium">
                    {p.default_teams}
                  </span>{" "}
                  teams default · max{" "}
                  <span className="text-foreground font-medium">
                    {p.max_teams_supported}
                  </span>
                </div>
              </button>
            ))}
          </div>

          {activePreset && (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-2 items-end">
              <div className="space-y-1">
                <Label className="text-[10px] uppercase tracking-wider text-muted-foreground">
                  League name (optional)
                </Label>
                <Input
                  value={customName}
                  onChange={(e) => setCustomName(e.target.value)}
                  placeholder={`${activePreset.label} Sandbox`}
                  className="h-9 text-xs"
                  data-testid="test-sandbox-name-input"
                />
              </div>
              <div className="space-y-1">
                <Label className="text-[10px] uppercase tracking-wider text-muted-foreground">
                  Number of teams (4 –{" "}
                  <span className="text-foreground">
                    {activePreset.max_teams_supported}
                  </span>
                  )
                </Label>
                <Input
                  type="number"
                  min={4}
                  max={activePreset.max_teams_supported}
                  value={numTeams || ""}
                  onChange={(e) => setNumTeams(Number(e.target.value) || 0)}
                  className="h-9 text-xs"
                  data-testid="test-sandbox-num-teams-input"
                />
              </div>
              <div className="flex gap-2">
                <Button
                  variant="default"
                  size="sm"
                  onClick={() => createLeague()}
                  disabled={creating || !activePreset}
                  className="flex-1 h-9"
                  data-testid="test-sandbox-create-btn"
                >
                  <Plus className="h-3.5 w-3.5 mr-1" />
                  {creating ? "Seeding…" : "Create sandbox"}
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => createLeague({ maxTeams: true })}
                  disabled={creating}
                  className="h-9 shrink-0"
                  title={`Instantly seed ${activePreset.max_teams_supported} teams`}
                  data-testid="test-sandbox-create-max-btn"
                >
                  Max
                </Button>
              </div>
            </div>
          )}
        </section>

        {/* ── Existing sandbox leagues ─────────────────────────── */}
        <section className="space-y-2">
          <div className="text-[10px] uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
            <FlaskConical className="h-3 w-3" />
            Existing sandbox leagues
          </div>
          {leagues.length === 0 ? (
            <div
              className="text-xs text-muted-foreground italic rounded-md border border-border/60 bg-secondary/20 p-3"
              data-testid="test-sandbox-empty"
            >
              No sandbox leagues yet. Pick a preset above and hit &ldquo;Create
              sandbox&rdquo;.
            </div>
          ) : (
            <div className="space-y-2">
              {leagues.map((lg) => {
                const users = usersByLeague[lg.id] ?? [];
                return (
                  <div
                    key={lg.id}
                    className="rounded-md border border-border/60 bg-card/40 p-3 space-y-2"
                    data-testid={`sandbox-league-row-${lg.id}`}
                  >
                    <div className="flex items-center justify-between gap-2 flex-wrap">
                      <div className="min-w-0">
                        <div className="text-sm font-semibold truncate">
                          {lg.name}
                        </div>
                        <div className="text-[10px] text-muted-foreground">
                          <Badge variant="outline" className="text-[9px] mr-1">
                            {humanizeKey(lg.preset_key ?? lg.format)}
                          </Badge>
                          <span className="font-mono">
                            {lg.current_teams}/{lg.max_teams}
                          </span>{" "}
                          teams · status{" "}
                          <span className="font-mono">{lg.status}</span>
                        </div>
                      </div>
                      <div className="flex items-center gap-1.5">
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => addExtraUser(lg.id)}
                          className="h-7"
                          data-testid={`sandbox-add-user-${lg.id}`}
                          title="Add an extra test user + team"
                        >
                          <Plus className="h-3 w-3 mr-1" /> User
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() =>
                            (window.location.href = `/leagues/${lg.id}`)
                          }
                          className="h-7"
                          data-testid={`sandbox-open-league-${lg.id}`}
                          title="Open the league as your admin identity"
                        >
                          <LogIn className="h-3 w-3 mr-1" /> Open
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => deleteLeague(lg)}
                          className="h-7 text-rose-300 border-rose-500/40 hover:bg-rose-500/10"
                          data-testid={`sandbox-delete-${lg.id}`}
                          title="Cascade-delete this sandbox"
                        >
                          <Trash2 className="h-3 w-3" />
                        </Button>
                      </div>
                    </div>

                    {/* Impersonate dropdown */}
                    {users.length > 0 && (
                      <div className="flex items-center gap-2">
                        <UserCircle2 className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                        <Select
                          onValueChange={(v) => {
                            const u = users.find((x) => x.id === v);
                            if (u) impersonate(u);
                          }}
                        >
                          <SelectTrigger
                            className="h-8 text-xs flex-1"
                            data-testid={`sandbox-impersonate-select-${lg.id}`}
                          >
                            <SelectValue placeholder="Jump in as a test user…" />
                          </SelectTrigger>
                          <SelectContent>
                            {users.map((u) => (
                              <SelectItem
                                key={u.id}
                                value={u.id}
                                textValue={`${u.name} (${u.team_name})`}
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
                        <Badge
                          variant="outline"
                          className="text-[9px] shrink-0"
                          title="Test users attached to this league"
                        >
                          <Users className="h-2.5 w-2.5 mr-0.5" />
                          {users.length}
                        </Badge>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </section>
      </CardContent>
    </Card>
  );
}
