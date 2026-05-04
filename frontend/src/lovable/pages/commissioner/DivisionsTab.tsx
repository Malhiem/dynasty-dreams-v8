// @ts-nocheck
import { useEffect, useState } from "react";
import api from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";
import { Network, Plus, Trash2, Save } from "lucide-react";

/**
 * Commissioner UI for assigning teams to divisions + conferences.
 * POSTs batch to PUT /api/leagues/{id}/divisions
 * Backend shape: {assignments: [{team_id, division, conference}]}
 */
export default function DivisionsTab({ leagueId }: { leagueId: string | null | undefined }) {
  const [teams, setTeams] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  // Map<teamId, { division, conference }>
  const [assignments, setAssignments] = useState<Record<string, { division: string; conference: string }>>({});

  // Division/Conference name inputs (batch-create)
  const [newDivName, setNewDivName] = useState("");
  const [newConfName, setNewConfName] = useState("");

  useEffect(() => {
    if (!leagueId) { setLoading(false); return; }
    let cancelled = false;
    setLoading(true);
    Promise.all([
      api.get(`/teams?league_id=${leagueId}`).catch(() => ({ data: [] })),
      api.get(`/leagues/${leagueId}/divisions`).catch(() => ({ data: { divisions: [], unassigned: [] } })),
    ]).then(([teamsRes, divRes]) => {
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
    }).finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [leagueId]);

  const updateTeam = (teamId: string, field: "division" | "conference", value: string) => {
    setAssignments(prev => ({
      ...prev,
      [teamId]: { ...(prev[teamId] || { division: "", conference: "" }), [field]: value },
    }));
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
    try {
      const payload = teams.map(t => ({
        team_id: t.id,
        division: assignments[t.id]?.division || null,
        conference: assignments[t.id]?.conference || null,
      }));
      const res = await api.put(`/leagues/${leagueId}/divisions`, { assignments: payload });
      toast.success(`Saved · ${res.data.updated} teams updated`);
    } catch (e: any) {
      const msg = e?.response?.data?.detail || "Failed to save divisions";
      toast.error(msg);
    } finally {
      setSaving(false);
    }
  };

  // Unique division / conference names seen so far — fuel Select dropdowns
  const divNames = Array.from(new Set(Object.values(assignments).map(a => a.division).filter(Boolean)));
  const confNames = Array.from(new Set(Object.values(assignments).map(a => a.conference).filter(Boolean)));

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
            <Button
              size="sm"
              onClick={save}
              disabled={saving || !leagueId}
              data-testid="divisions-save-btn"
            >
              <Save className="h-4 w-4 mr-1" /> {saving ? "Saving..." : "Save"}
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
                {teams.map(t => (
                  <tr key={t.id} data-testid={`divisions-row-${t.id}`}>
                    <td className="py-2 pl-3 font-medium">{t.name}</td>
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
                      <Select
                        value={assignments[t.id]?.conference || "__none__"}
                        onValueChange={v => updateTeam(t.id, "conference", v === "__none__" ? "" : v)}
                      >
                        <SelectTrigger className="h-8 text-xs w-[160px]" data-testid={`divisions-select-conf-${t.id}`}>
                          <SelectValue placeholder="—" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="__none__">—</SelectItem>
                          {Array.from(new Set([...confNames, newConfName].filter(Boolean))).map(c => (
                            <SelectItem key={c} value={c}>{c}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </td>
                  </tr>
                ))}
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
    </div>
  );
}
