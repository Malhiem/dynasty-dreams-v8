// @ts-nocheck
import { useEffect, useState } from "react";
import api from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";
import { Network, Plus, Trash2, Save, Lock, Unlock } from "lucide-react";
import { useActiveLeague } from "@/hooks/use-active-league";
import InfoHint from "@/components/ui/info-hint";
import {
  RegularSeasonScheduleCard,
  PlayoffsCard,
  ConsolationCard,
} from "@/lovable/pages/commissioner/PlayoffsScheduleCards";

/**
 * Commissioner UI for League Structure: divisions/conferences + schedule mix +
 * Playoffs & Schedule (regular-season length, opponents/period, playoff bracket).
 */
export default function DivisionsTab({ leagueId }: { leagueId: string | null | undefined }) {
  const { league: activeLeague, reloadLeague } = useActiveLeague();
  const [teams, setTeams] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  // Map<teamId, { division, conference }>
  const [assignments, setAssignments] = useState<Record<string, { division: string; conference: string }>>({});

  // Iter 232N.67 — Structure lock. When active, the (division→conference)
  // map on the league doc becomes a hard rule: any save that would
  // remap a division to a different conference is rejected by the API
  // with a 409 + per-team conflict list.
  const [structureLocked, setStructureLocked] = useState(false);
  const [lockedMap, setLockedMap] = useState<Record<string, string>>({});
  const [lockOnSave, setLockOnSave] = useState(false);
  // Per-team conflict IDs highlighted after a failed save.
  const [conflictTeamIds, setConflictTeamIds] = useState<Set<string>>(new Set());

  // Division/Conference name inputs (batch-create)
  const [newDivName, setNewDivName] = useState("");
  const [newConfName, setNewConfName] = useState("");

  // Schedule config
  const [scheduleCfg, setScheduleCfg] = useState({
    intra_division_games: 2,
    intra_conference_games: 1,
    inter_conference_games: 1,
    configured: false,
  });
  const [savingCfg, setSavingCfg] = useState(false);

  useEffect(() => {
    if (!leagueId) { setLoading(false); return; }
    let cancelled = false;
    setLoading(true);
    Promise.all([
      api.get(`/teams?league_id=${leagueId}`).catch(() => ({ data: [] })),
      api.get(`/leagues/${leagueId}/divisions`).catch(() => ({ data: { divisions: [], unassigned: [] } })),
      api.get(`/leagues/${leagueId}/schedule-config`).catch(() => ({ data: null })),
    ]).then(([teamsRes, divRes, cfgRes]) => {
      if (cancelled) return;
      const tlist = teamsRes.data || [];
      setTeams(tlist);
      const initMap: Record<string, { division: string; conference: string }> = {};
      tlist.forEach((t: any) => {
        initMap[t.id] = { division: t.division || "", conference: t.conference || "" };
      });
      // Overlay saved assignments
      (divRes.data?.divisions || []).forEach((d: any) => {
        (d.team_ids || []).forEach((tid: string) => {
          initMap[tid] = { division: d.division || "", conference: d.conference || "" };
        });
      });
      setAssignments(initMap);
      // Iter 232N.67 — hydrate lock state from the same divisions call.
      setStructureLocked(!!divRes.data?.structure_locked);
      setLockedMap((divRes.data?.division_conference_map as Record<string, string>) || {});
      if (cfgRes?.data) setScheduleCfg(cfgRes.data);
    }).finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [leagueId]);

  const updateTeam = (teamId: string, field: "division" | "conference", value: string) => {
    setAssignments(prev => {
      const next = {
        ...prev,
        [teamId]: { ...(prev[teamId] || { division: "", conference: "" }), [field]: value },
      };

      // Auto-fill conference when division changes.
      //
      // If the league structure is LOCKED, the locked map is the
      // source of truth (deterministic). If not locked, we infer the
      // conference from other teams already assigned to that division
      // (heuristic — only fills when exactly one non-empty sibling
      // conference exists).
      if (field === "division" && value) {
        let inferred: string | undefined;
        if (structureLocked && lockedMap[value]) {
          inferred = lockedMap[value];
        } else {
          const conferencesForDiv = new Set(
            Object.entries(next)
              .filter(([tid, a]) => tid !== teamId && a.division === value && a.conference)
              .map(([, a]) => a.conference),
          );
          if (conferencesForDiv.size === 1) {
            inferred = Array.from(conferencesForDiv)[0];
          }
        }
        if (inferred && next[teamId].conference !== inferred) {
          next[teamId] = { ...next[teamId], conference: inferred };
          toast.info(
            structureLocked
              ? `Conference auto-set to "${inferred}" (locked map for "${value}")`
              : `Conference auto-set to "${inferred}" (matches other teams in "${value}")`,
          );
        }
      }

      // Clear stale conflict highlights when the user starts editing.
      if (conflictTeamIds.size > 0) setConflictTeamIds(new Set());

      return next;
    });
  };

  const clearAll = () => {
    const cleared: Record<string, { division: string; conference: string }> = {};
    teams.forEach(t => { cleared[t.id] = { division: "", conference: "" }; });
    setAssignments(cleared);
  };

  const autoAssignNHL = () => {
    // Auto-assign using standard NHL Atlantic / Metropolitan / Central / Pacific, Eastern vs Western
    const divs = ["Atlantic", "Metropolitan", "Central", "Pacific"];
    const confOf = (d: string) => (d === "Atlantic" || d === "Metropolitan") ? "Eastern" : "Western";
    const next: Record<string, { division: string; conference: string }> = {};
    teams.forEach((t, idx) => {
      const div = divs[idx % 4];
      next[t.id] = { division: div, conference: confOf(div) };
    });
    setAssignments(next);
    toast.info("Auto-assigned: 4 divisions, 2 conferences (NHL-style)");
  };

  const save = async () => {
    if (!leagueId) return;
    setSaving(true);
    setConflictTeamIds(new Set());
    try {
      const payload = teams.map(t => ({
        team_id: t.id,
        division: assignments[t.id]?.division || null,
        conference: assignments[t.id]?.conference || null,
      }));
      const res = await api.put(`/leagues/${leagueId}/divisions`, {
        assignments: payload,
        lock: lockOnSave || undefined,
      });
      const wasLocked = structureLocked;
      setStructureLocked(!!res.data.structure_locked);
      setLockedMap(res.data.division_conference_map || {});
      if (lockOnSave && !wasLocked) {
        toast.success(`Saved · ${res.data.updated} teams · Structure LOCKED 🔒`);
        setLockOnSave(false);
      } else {
        toast.success(`Saved · ${res.data.updated} teams updated`);
      }
    } catch (e: any) {
      const detail = e?.response?.data?.detail;
      // Iter 232N.67 — structured 409 with per-team conflicts
      if (detail && typeof detail === "object" && detail.code === "division_conference_mapping_conflict") {
        const conflictIds = new Set<string>((detail.conflicts || []).map((c: any) => c.team_id));
        setConflictTeamIds(conflictIds);
        const first = (detail.conflicts || [])[0];
        toast.error(
          detail.structure_locked
            ? `Locked structure violation: "${first?.division}" is mapped to "${first?.expected_conference}", not "${first?.attempted_conference}". Unlock to remap.`
            : `Conflict: "${first?.division}" has teams in ${first?.expected_conference} AND ${first?.attempted_conference}. Align before saving.`,
        );
      } else {
        toast.error(typeof detail === "string" ? detail : (detail?.message || "Failed to save divisions"));
      }
    } finally {
      setSaving(false);
    }
  };

  const unlockStructure = async () => {
    if (!leagueId) return;
    if (!window.confirm("Unlock the (division → conference) structure? Future saves will allow remapping.")) return;
    try {
      await api.post(`/leagues/${leagueId}/divisions/unlock`);
      setStructureLocked(false);
      setLockedMap({});
      toast.success("Structure unlocked — remaps allowed");
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Unlock failed");
    }
  };

  // Unique division / conference names seen so far — fuel Select dropdowns
  const divNames = Array.from(new Set(Object.values(assignments).map(a => a.division).filter(Boolean)));
  const confNames = Array.from(new Set(Object.values(assignments).map(a => a.conference).filter(Boolean)));
  const hasMinDivisions = divNames.length >= 2;

  const saveScheduleCfg = async () => {
    if (!leagueId) return;
    setSavingCfg(true);
    try {
      const payload = {
        intra_division_games: scheduleCfg.intra_division_games,
        intra_conference_games: scheduleCfg.intra_conference_games,
        inter_conference_games: scheduleCfg.inter_conference_games,
      };
      await api.put(`/leagues/${leagueId}/schedule-config`, payload);
      setScheduleCfg(prev => ({ ...prev, configured: true }));
      toast.success("Schedule mix saved — applies next time schedule is generated");
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Failed to save schedule config");
    } finally {
      setSavingCfg(false);
    }
  };

  if (loading) {
    return (
      <Card className="bg-card border-border" data-testid="divisions-tab-loading">
        <CardContent className="py-10 text-center text-muted-foreground">Loading divisions...</CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-6" data-testid="divisions-tab">
      <Card className="bg-card border-border">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-lg">
            <Network className="h-5 w-5 text-primary" /> Divisions &amp; Conferences
            <InfoHint
              testId="info-divisions-conferences"
              text="Group teams into divisions and (optionally) conferences. Used for Standings subgroups, Games Back math, intra-/inter-division schedule weighting, and playoff bracket seeding."
            />
          </CardTitle>
          <p className="text-sm text-muted-foreground">
            Group teams into divisions and conferences. Powers the Standings subgroups, Games Back (GB), and playoff bracket seeding.
          </p>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap gap-2">
            <Button
              size="sm"
              variant="outline"
              onClick={autoAssignNHL}
              data-testid="divisions-auto-assign-btn"
              disabled={teams.length === 0}
            >
              <Plus className="h-4 w-4 mr-1" /> Auto-assign NHL style
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={clearAll}
              data-testid="divisions-clear-all-btn"
              disabled={teams.length === 0}
            >
              <Trash2 className="h-4 w-4 mr-1" /> Clear all
            </Button>
            <div className="flex-1" />
            {/* Iter 232N.67 — Lock state + toggle */}
            {structureLocked ? (
              <div className="flex items-center gap-2 rounded-md border border-emerald-500/40 bg-emerald-500/10 px-2 py-1 text-[11px] text-emerald-200"
                   data-testid="divisions-lock-status">
                <Lock className="h-3 w-3" />
                Locked ·{" "}
                <span className="font-mono">
                  {Object.keys(lockedMap).length} division{Object.keys(lockedMap).length === 1 ? "" : "s"} mapped
                </span>
                <Button
                  size="sm" variant="ghost"
                  onClick={unlockStructure}
                  className="h-5 px-1 text-[10px] text-emerald-100 hover:text-emerald-50"
                  data-testid="divisions-unlock-btn"
                >
                  <Unlock className="h-3 w-3 mr-0.5" /> Unlock
                </Button>
              </div>
            ) : (
              <label className="flex items-center gap-1.5 text-[11px] text-muted-foreground cursor-pointer"
                     data-testid="divisions-lock-toggle-label">
                <input
                  type="checkbox"
                  checked={lockOnSave}
                  onChange={e => setLockOnSave(e.target.checked)}
                  data-testid="divisions-lock-toggle"
                />
                <Lock className="h-3 w-3" /> Save &amp; lock structure
              </label>
            )}
            <Button
              size="sm"
              onClick={save}
              disabled={saving || !leagueId}
              data-testid="divisions-save-btn"
            >
              <Save className="h-4 w-4 mr-1" />{" "}
              {saving ? "Saving..." : (lockOnSave && !structureLocked ? "Save & Lock" : "Save")}
            </Button>
          </div>

          <div className="grid grid-cols-2 gap-3 max-w-xl">
            <div>
              <Label className="text-xs text-muted-foreground">Add division (free text)</Label>
              <div className="flex gap-1 mt-1">
                <Input
                  value={newDivName}
                  onChange={e => setNewDivName(e.target.value)}
                  placeholder="Atlantic"
                  className="h-8 text-sm"
                  data-testid="divisions-new-div-input"
                />
              </div>
            </div>
            <div>
              <Label className="text-xs text-muted-foreground">Add conference (free text)</Label>
              <div className="flex gap-1 mt-1">
                <Input
                  value={newConfName}
                  onChange={e => setNewConfName(e.target.value)}
                  placeholder="Eastern"
                  className="h-8 text-sm"
                  data-testid="divisions-new-conf-input"
                />
              </div>
            </div>
          </div>

          <div className="border border-border rounded-md overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-secondary/30">
                <tr className="text-xs font-medium text-muted-foreground">
                  <th className="py-2 pl-3 text-left">Team</th>
                  <th className="py-2 text-left">Division</th>
                  <th className="py-2 text-left pr-3">Conference</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/50">
                {teams.map(t => {
                  const isConflict = conflictTeamIds.has(t.id);
                  const teamDiv = assignments[t.id]?.division || "";
                  const conferenceLockedForTeam = structureLocked && !!lockedMap[teamDiv];
                  return (
                  <tr key={t.id} data-testid={`divisions-row-${t.id}`}
                      className={isConflict ? "bg-rose-500/10" : ""}>
                    <td className="py-2 pl-3 font-medium">
                      {t.name}
                      {isConflict && (
                        <span className="ml-2 text-[10px] rounded-sm border border-rose-500/40 bg-rose-500/10 text-rose-300 px-1"
                              data-testid={`divisions-row-conflict-${t.id}`}>
                          conflict
                        </span>
                      )}
                    </td>
                    <td className="py-2 pr-2">
                      <Select
                        value={assignments[t.id]?.division || "__none__"}
                        onValueChange={v => updateTeam(t.id, "division", v === "__none__" ? "" : v)}
                      >
                        <SelectTrigger className="h-8 text-xs w-[160px]" data-testid={`divisions-select-div-${t.id}`}>
                          <SelectValue placeholder="—" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="__none__">—</SelectItem>
                          {Array.from(new Set([...divNames, newDivName].filter(Boolean))).map(d => (
                            <SelectItem key={d} value={d}>{d}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </td>
                    <td className="py-2 pr-3">
                      <div className="flex items-center gap-1">
                        <Select
                          value={assignments[t.id]?.conference || "__none__"}
                          onValueChange={v => updateTeam(t.id, "conference", v === "__none__" ? "" : v)}
                          disabled={conferenceLockedForTeam}
                        >
                          <SelectTrigger
                            className={`h-8 text-xs w-[160px] ${conferenceLockedForTeam ? "opacity-70" : ""}`}
                            data-testid={`divisions-select-conf-${t.id}`}
                          >
                            <SelectValue placeholder="—" />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="__none__">—</SelectItem>
                            {Array.from(new Set([...confNames, newConfName].filter(Boolean))).map(c => (
                              <SelectItem key={c} value={c}>{c}</SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                        {conferenceLockedForTeam && (
                          <Lock className="h-3 w-3 text-emerald-400 shrink-0"
                                aria-label="Conference pinned by locked structure" />
                        )}
                      </div>
                    </td>
                  </tr>
                );})}
                {teams.length === 0 && (
                  <tr>
                    <td colSpan={3} className="py-6 text-center text-muted-foreground text-sm">No teams yet.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      {/* Schedule Mix Card */}
      <Card className="bg-card border-border" data-testid="schedule-mix-card">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-lg">
            <Network className="h-5 w-5 text-accent" /> Schedule Mix
          </CardTitle>
          <p className="text-sm text-muted-foreground">
            Control how many times each team plays its rivals. These counts take effect the
            next time the commissioner (re)generates the schedule.
            <span className="block mt-1 text-xs">
              Status:{" "}
              {scheduleCfg.configured ? (
                <span className="text-success font-semibold" data-testid="schedule-mix-status-configured">OPTED-IN · division-aware scheduling ACTIVE</span>
              ) : (
                <span className="text-muted-foreground italic" data-testid="schedule-mix-status-default">Using vanilla round-robin (default) · Save this card to opt into division-aware scheduling</span>
              )}
            </span>
          </p>
        </CardHeader>
        <CardContent className="space-y-4">
          {!hasMinDivisions && (
            <div
              className="rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-xs text-amber-200"
              data-testid="schedule-mix-need-divisions"
            >
              ⚠️ You need at least <strong>2 divisions</strong> configured above before
              division-aware scheduling can take effect. You can still save these numbers —
              they&apos;ll activate automatically once divisions are in place.
            </div>
          )}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 max-w-3xl">
            <div>
              <Label htmlFor="intra-div" className="text-xs font-semibold">
                Intra-division games
                <InfoHint
                  testId="info-intra-division"
                  text="How many times each team plays the OTHER teams in its own division across the regular season. Higher = more rivalry games. NHL uses ~4×; fantasy leagues usually 2×."
                />
              </Label>
              <Input
                id="intra-div"
                type="number"
                min={0}
                max={20}
                value={scheduleCfg.intra_division_games}
                onChange={e => setScheduleCfg(prev => ({ ...prev, intra_division_games: Math.max(0, Math.min(20, parseInt(e.target.value || "0", 10))) }))}
                className="mt-1"
                data-testid="schedule-mix-intra-div-input"
              />
              <p className="text-[10px] text-muted-foreground mt-1">
                Times you play each team in your OWN division. (NHL: ~4×, fantasy: 2×)
              </p>
            </div>
            <div>
              <Label htmlFor="intra-conf" className="text-xs font-semibold">
                Intra-conference games
                <InfoHint
                  testId="info-intra-conference"
                  text="How many times each team plays non-division teams in the same conference. Skipped automatically if your league only has divisions, no conferences."
                />
              </Label>
              <Input
                id="intra-conf"
                type="number"
                min={0}
                max={20}
                value={scheduleCfg.intra_conference_games}
                onChange={e => setScheduleCfg(prev => ({ ...prev, intra_conference_games: Math.max(0, Math.min(20, parseInt(e.target.value || "0", 10))) }))}
                className="mt-1"
                data-testid="schedule-mix-intra-conf-input"
              />
              <p className="text-[10px] text-muted-foreground mt-1">
                Times you play each non-division team in your OWN conference.
              </p>
            </div>
            <div>
              <Label htmlFor="inter-conf" className="text-xs font-semibold">
                Inter-conference games
                <InfoHint
                  testId="info-inter-conference"
                  text="How many times each team plays teams in the OTHER conference. Set to 0 for a strict East-vs-West split until the playoffs."
                />
              </Label>
              <Input
                id="inter-conf"
                type="number"
                min={0}
                max={20}
                value={scheduleCfg.inter_conference_games}
                onChange={e => setScheduleCfg(prev => ({ ...prev, inter_conference_games: Math.max(0, Math.min(20, parseInt(e.target.value || "0", 10))) }))}
                className="mt-1"
                data-testid="schedule-mix-inter-conf-input"
              />
              <p className="text-[10px] text-muted-foreground mt-1">
                Times you play each team in the OPPOSITE conference.
              </p>
            </div>
          </div>
          <div className="flex justify-end">
            <Button
              size="sm"
              onClick={saveScheduleCfg}
              disabled={savingCfg || !leagueId}
              data-testid="schedule-mix-save-btn"
            >
              <Save className="h-4 w-4 mr-1" /> {savingCfg ? "Saving..." : "Save Schedule Mix"}
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Regular Season + Playoffs + Consolation (moved here from Rules & Schedule) */}
      {activeLeague?.id && (
        <>
          <RegularSeasonScheduleCard league={activeLeague} reloadLeague={reloadLeague} />
          {activeLeague?.playoffs_enabled && (
            <>
              <PlayoffsCard league={activeLeague} reloadLeague={reloadLeague} teams={teams} />
              <ConsolationCard league={activeLeague} reloadLeague={reloadLeague} teams={teams} />
            </>
          )}
        </>
      )}
    </div>
  );
}
