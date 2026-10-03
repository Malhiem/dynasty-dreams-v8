// @ts-nocheck
/**
 * Iter 144 — Commissioner override panel.
 *
 * Lists each team in the league with a one-click "Auto-protect elites"
 * button. Triggers POST `/leagues/{id}/protection-list/auto-protect`
 * with `metric=salary` (top-N by salary cap hit) or `metric=fppg`.
 *
 * Visible only on Draft tabs that surface keeper / expansion mode.
 */
import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Shield, UserX } from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";

type Props = { leagueId?: string | null; draftType?: "keeper" | "expansion" };

export default function CommissionerProtectionOverridePanel({ leagueId, draftType = "expansion" }: Props) {
  const [teams, setTeams] = useState<any[]>([]);
  const [metric, setMetric] = useState<"salary" | "fppg">("salary");
  const [busy, setBusy] = useState<string | null>(null);

  const refresh = () => {
    if (!leagueId) return;
    api.get(`/teams?league_id=${leagueId}`)
      .then(({ data }) => setTeams(data || []))
      .catch(() => setTeams([]));
  };

  useEffect(() => { refresh(); }, [leagueId]);

  const autoProtect = async (teamId: string, teamName: string) => {
    if (!leagueId) return;
    setBusy(teamId);
    try {
      const { data } = await api.post(
        `/leagues/${leagueId}/protection-list/auto-protect`,
        { team_id: teamId, draft_type: draftType, metric },
      );
      toast.success(`Auto-protected ${data?.count || 0} player${data?.count === 1 ? "" : "s"} for ${teamName} (by ${metric})`);
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Auto-protect failed");
    } finally {
      setBusy(null);
    }
  };

  return (
    <Card className="bg-card border-border" data-testid="commish-protection-override-card">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <UserX className="h-4 w-4 text-amber-300" />
          Commissioner Override — Submit on Behalf of Inactive Team
        </CardTitle>
        <CardDescription>
          For managers who go AWOL: auto-protects the top-N players on their roster by the
          selected metric and marks the list as submitted on their behalf.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex items-center gap-3">
          <span className="text-xs text-muted-foreground">Default rule:</span>
          <Select value={metric} onValueChange={(v) => setMetric(v as any)}>
            <SelectTrigger className="w-[260px]" data-testid="commish-protection-metric">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="salary">Top-N by salary cap hit</SelectItem>
              <SelectItem value="fppg">Top-N by fantasy points / game</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="grid sm:grid-cols-2 gap-2" data-testid="commish-protection-teams">
          {teams.map((t) => (
            <div
              key={t.id}
              className="flex items-center justify-between gap-2 rounded-md border border-border px-2 py-1.5"
              data-testid={`commish-protection-team-${t.id}`}
            >
              <div className="text-sm">
                {t.name} <span className="text-muted-foreground">({t.logo_abbr || (t.name || "").slice(0, 3).toUpperCase()})</span>
              </div>
              <Button
                size="sm"
                variant="outline"
                onClick={() => autoProtect(t.id, t.name)}
                disabled={busy === t.id}
                data-testid={`commish-protection-auto-${t.id}`}
              >
                <Shield className="h-3.5 w-3.5 mr-1" />
                Auto-protect elites
              </Button>
            </div>
          ))}
          {teams.length === 0 && (
            <div className="text-xs italic text-muted-foreground col-span-2">No teams found.</div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
