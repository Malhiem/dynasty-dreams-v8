// @ts-nocheck
import { useEffect, useState } from "react";
import { Trophy, Medal, Star, Loader2, Save } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { toast } from "sonner";
import api from "@/lib/api";
import { useActiveLeague } from "@/hooks/use-active-league";

type TeamAwards = {
  championship_won_at?: string | null;
  division_winner_at?: string | null;
  playoffs_reached_at?: string | null;
};

export function SeasonAwardsTab() {
  const { league, leagueTeams } = useActiveLeague();
  const [awards, setAwards] = useState<Record<string, TeamAwards>>({});
  const [loading, setLoading] = useState(false);
  const [savingId, setSavingId] = useState<string | null>(null);

  // Initialize from leagueTeams (contains award fields if present)
  useEffect(() => {
    const map: Record<string, TeamAwards> = {};
    (leagueTeams || []).forEach((t: any) => {
      map[t.id] = {
        championship_won_at: t.championship_won_at || null,
        division_winner_at: t.division_winner_at || null,
        playoffs_reached_at: t.playoffs_reached_at || null,
      };
    });
    setAwards(map);
  }, [leagueTeams]);

  // Fallback: fetch freshly from /teams endpoint to pick up awards fields even if
  // useActiveLeague doesn't expose them.
  useEffect(() => {
    if (!league?.id) return;
    let cancelled = false;
    setLoading(true);
    api.get(`/teams?league_id=${league.id}`).then(({ data }) => {
      if (cancelled) return;
      const map: Record<string, TeamAwards> = {};
      (data || []).forEach((t: any) => {
        map[t.id] = {
          championship_won_at: t.championship_won_at || null,
          division_winner_at: t.division_winner_at || null,
          playoffs_reached_at: t.playoffs_reached_at || null,
        };
      });
      setAwards(map);
    }).catch(() => {}).finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [league?.id]);

  const toggle = async (teamId: string, field: keyof TeamAwards, value: boolean) => {
    if (!league?.id) return;
    setSavingId(teamId + ":" + field);
    const body: any = {};
    if (field === "championship_won_at") body.championship_won = value;
    if (field === "division_winner_at") body.division_winner = value;
    if (field === "playoffs_reached_at") body.playoffs_reached = value;
    try {
      const { data } = await api.put(`/leagues/${league.id}/teams/${teamId}/awards`, body);
      setAwards((prev) => ({
        ...prev,
        [teamId]: {
          championship_won_at: data.championship_won_at,
          division_winner_at: data.division_winner_at,
          playoffs_reached_at: data.playoffs_reached_at,
        },
      }));
      let msg = value ? `Awarded ${field.replace("_at", "").replace(/_/g, " ")}` : `Cleared ${field.replace("_at", "").replace(/_/g, " ")}`;
      if (data.unlocked_trades > 0) msg += ` · ${data.unlocked_trades} conditional trade(s) unlocked`;
      toast.success(msg);
    } catch (e: any) {
      toast.error("Failed to update", { description: e?.response?.data?.detail || e?.message });
    } finally {
      setSavingId(null);
    }
  };

  return (
    <Card className="bg-card border-border">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Trophy className="h-5 w-5 text-primary" />
          Season Awards
        </CardTitle>
        <p className="text-xs text-muted-foreground">
          Mark teams with season-end awards. Flipping these triggers re-evaluation of any
          pending conditional trades with matching team conditions (e.g. "trade executes if my team
          wins the championship").
        </p>
      </CardHeader>
      <CardContent className="space-y-3">
        {loading && (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" /> Loading teams…
          </div>
        )}
        {!loading && (leagueTeams || []).map((t: any) => {
          const a = awards[t.id] || {};
          return (
            <div
              key={t.id}
              data-testid={`season-awards-row-${t.id}`}
              className="flex items-center gap-3 p-3 rounded-lg border border-border bg-secondary/30 hover:bg-secondary/50 transition-colors"
            >
              <div className="h-8 w-8 rounded bg-primary/10 flex items-center justify-center text-xs font-bold text-primary shrink-0">
                {t.logo_abbr || (t.name || "").slice(0, 3).toUpperCase()}
              </div>
              <div className="min-w-0 flex-1">
                <p className="font-semibold text-sm truncate">{t.name}</p>
                <p className="text-[11px] text-muted-foreground">
                  {t.owner_name} · {t.wins || 0}-{t.losses || 0}-{t.ties || 0}
                </p>
              </div>

              <AwardToggle
                label="Playoffs"
                icon={<Star className="h-3.5 w-3.5" />}
                active={!!a.playoffs_reached_at}
                onChange={(v) => toggle(t.id, "playoffs_reached_at", v)}
                saving={savingId === `${t.id}:playoffs_reached_at`}
                testId={`season-awards-playoffs-${t.id}`}
              />
              <AwardToggle
                label="Division"
                icon={<Medal className="h-3.5 w-3.5" />}
                active={!!a.division_winner_at}
                onChange={(v) => toggle(t.id, "division_winner_at", v)}
                saving={savingId === `${t.id}:division_winner_at`}
                testId={`season-awards-division-${t.id}`}
              />
              <AwardToggle
                label="Champion"
                icon={<Trophy className="h-3.5 w-3.5" />}
                active={!!a.championship_won_at}
                onChange={(v) => toggle(t.id, "championship_won_at", v)}
                saving={savingId === `${t.id}:championship_won_at`}
                testId={`season-awards-champion-${t.id}`}
                highlight
              />
            </div>
          );
        })}
        {!loading && (leagueTeams || []).length === 0 && (
          <p className="text-sm text-muted-foreground text-center py-6">
            No teams in this league yet.
          </p>
        )}
      </CardContent>
    </Card>
  );
}

function AwardToggle({ label, icon, active, onChange, saving, testId, highlight }: any) {
  return (
    <div className="flex flex-col items-center gap-1 min-w-[76px]">
      <Badge
        variant={active ? "default" : "outline"}
        className={`text-[10px] flex items-center gap-1 ${
          active
            ? highlight
              ? "bg-amber-500/20 text-amber-400 border-amber-500/50"
              : "bg-primary/20 text-primary border-primary/40"
            : "bg-transparent text-muted-foreground"
        }`}
      >
        {icon} {label}
      </Badge>
      <Switch
        checked={active}
        onCheckedChange={onChange}
        disabled={saving}
        className="scale-75"
        data-testid={testId}
      />
    </div>
  );
}

export default SeasonAwardsTab;
