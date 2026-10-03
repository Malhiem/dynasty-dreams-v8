// @ts-nocheck
import { useEffect, useState } from "react";
import api from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";
import {
  CheckCircle2, Circle, Trophy, Crown, RefreshCw,
  ChevronRight, Clock,
} from "lucide-react";

const SECTION_ICON: Record<string, any> = {
  basics: Trophy, cap: Crown, divisions: Trophy,
  schedule: Clock, playoffs: Crown, draft: Trophy,
};

const SECTION_TAB_HINT: Record<string, string> = {
  basics: "league-setup",
  cap: "league-setup",
  divisions: "divisions",
  schedule: "divisions",
  playoffs: "league-setup",
  draft: "draft",
};

interface HealthSection {
  key: string;
  label: string;
  complete: boolean;
  weight: number;
  detail: string;
}

interface HealthData {
  league_id: string;
  current_season_year: number;
  current_season_status: "in_progress" | "complete" | "renewed";
  score: number;
  sections: HealthSection[];
  missing: string[];
}

interface SeasonSummary {
  id: string;
  season_year: number;
  status: string;
  champion_team_name?: string | null;
  snapshot_at?: string;
  completed_by?: string;
}

export default function LeagueHealthCard({
  leagueId,
  onJumpToTab,
  onReopenWizard,
}: {
  leagueId?: string | null;
  onJumpToTab?: (tabId: string) => void;
  onReopenWizard?: () => void;
}) {
  const [health, setHealth] = useState<HealthData | null>(null);
  const [seasons, setSeasons] = useState<SeasonSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [completing, setCompleting] = useState(false);
  const [renewing, setRenewing] = useState(false);
  const [showRenewForm, setShowRenewForm] = useState(false);
  const [newYear, setNewYear] = useState<number>(new Date().getFullYear() + 1);
  const [carryOver, setCarryOver] = useState(true);
  const [resetRecords, setResetRecords] = useState(true);

  const refresh = async () => {
    if (!leagueId) return;
    setLoading(true);
    try {
      const [h, s] = await Promise.all([
        api.get(`/leagues/${leagueId}/health-score`),
        api.get(`/leagues/${leagueId}/seasons`),
      ]);
      setHealth(h.data);
      setSeasons(s.data?.seasons || []);
    } catch (e) {
      // best-effort
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { refresh(); }, [leagueId]);

  const completeSeason = async () => {
    if (!leagueId || !health) return;
    setCompleting(true);
    try {
      const res = await api.post(`/leagues/${leagueId}/complete-season`, {
        season_year: health.current_season_year,
      });
      const champion = res.data?.champion;
      toast.success(
        champion
          ? `🏆 Season ${health.current_season_year} archived — ${champion} wins!`
          : `Season ${health.current_season_year} archived (${res.data?.teams_snapshotted} teams)`,
      );
      await refresh();
      // After completion, prefill the renew form with next year
      setNewYear(health.current_season_year + 1);
      setShowRenewForm(true);
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Failed to complete season");
    } finally {
      setCompleting(false);
    }
  };

  const renewSeason = async () => {
    if (!leagueId || !health) return;
    if (newYear <= health.current_season_year) {
      toast.error(`New year must be greater than ${health.current_season_year}`);
      return;
    }
    setRenewing(true);
    try {
      const res = await api.post(`/leagues/${leagueId}/renew-season`, {
        new_season_year: newYear,
        carry_over_settings: carryOver,
        reset_records: resetRecords,
      });
      toast.success(`Season ${res.data?.to_year} started — ready to set up!`);
      setShowRenewForm(false);
      await refresh();
      // Auto-reopen the wizard so commissioner can finalize new season config
      onReopenWizard && onReopenWizard();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Failed to renew season");
    } finally {
      setRenewing(false);
    }
  };

  if (loading || !health) {
    return (
      <Card className="bg-card border-border" data-testid="health-card-loading">
        <CardContent className="py-8 text-center text-muted-foreground">Loading league health...</CardContent>
      </Card>
    );
  }

  const score = health.score;
  const isComplete = score >= 100;
  const seasonStatus = health.current_season_status;
  const lastSeason = seasons[0];

  // Color tint by score
  const scoreColor =
    score >= 90 ? "text-success" :
    score >= 60 ? "text-primary" :
    score >= 30 ? "text-amber-400" :
    "text-destructive";

  const ringColor =
    score >= 90 ? "stroke-success" :
    score >= 60 ? "stroke-primary" :
    score >= 30 ? "stroke-amber-400" :
    "stroke-destructive";

  // SVG ring math
  const RADIUS = 38;
  const CIRC = 2 * Math.PI * RADIUS;
  const offset = CIRC * (1 - score / 100);

  return (
    <Card className="bg-card border-border" data-testid="health-card">
      <CardHeader>
        <CardTitle className="flex items-center justify-between">
          <span className="flex items-center gap-2">
            <Trophy className="h-5 w-5 text-accent" />
            League Health Score
            <span className="text-xs font-normal text-muted-foreground ml-2">
              · {health.current_season_year} season ({seasonStatus.replace("_", " ")})
            </span>
          </span>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-5">
        {/* Score ring + summary */}
        <div className="flex items-center gap-5 flex-wrap">
          <div className="relative shrink-0" data-testid="health-score-ring">
            <svg width="100" height="100" className="-rotate-90">
              <circle cx="50" cy="50" r={RADIUS} className="fill-none stroke-secondary/40" strokeWidth="8" />
              <circle
                cx="50" cy="50" r={RADIUS}
                className={`fill-none ${ringColor} transition-all duration-500`}
                strokeWidth="8"
                strokeDasharray={CIRC}
                strokeDashoffset={offset}
                strokeLinecap="round"
              />
            </svg>
            <div className="absolute inset-0 flex flex-col items-center justify-center">
              <span className={`text-2xl font-bold ${scoreColor}`} data-testid="health-score-value">{score}</span>
              <span className="text-[10px] text-muted-foreground">/ 100</span>
            </div>
          </div>
          <div className="flex-1 space-y-2 min-w-[200px]">
            <p className="text-sm">
              {isComplete ? (
                <span className="text-success font-semibold">✓ All-systems-go — your league is fully configured!</span>
              ) : (
                <>
                  <span className="font-semibold">{health.missing.length}</span> setup item
                  {health.missing.length === 1 ? "" : "s"} remaining for the {health.current_season_year} season.
                </>
              )}
            </p>
            <div className="flex flex-wrap gap-2">
              {!isComplete && (
                <Button size="sm" variant="outline" onClick={onReopenWizard} data-testid="health-reopen-wizard-btn">
                  Re-run Setup Wizard
                </Button>
              )}
              <Button
                size="sm"
                variant="outline"
                onClick={refresh}
                data-testid="health-refresh-btn"
              >
                <RefreshCw className="h-3.5 w-3.5 mr-1" /> Refresh
              </Button>
            </div>
          </div>
        </div>

        {/* Section breakdown */}
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-2.5" data-testid="health-sections">
          {health.sections.map((s) => {
            const Icon = s.complete ? CheckCircle2 : Circle;
            const tab = SECTION_TAB_HINT[s.key];
            return (
              <button
                key={s.key}
                onClick={() => tab && onJumpToTab && onJumpToTab(tab)}
                className={`text-left p-3 rounded-md border transition-colors ${
                  s.complete
                    ? "border-success/30 bg-success/5 hover:bg-success/10"
                    : "border-border bg-secondary/20 hover:bg-secondary/30"
                }`}
                data-testid={`health-section-${s.key}`}
              >
                <div className="flex items-center gap-2 mb-1">
                  <Icon className={`h-4 w-4 ${s.complete ? "text-success" : "text-muted-foreground"}`} />
                  <span className="font-semibold text-sm">{s.label}</span>
                  <span className="text-[10px] text-muted-foreground ml-auto">+{s.weight}</span>
                </div>
                <p className="text-[11px] text-muted-foreground leading-tight">{s.detail}</p>
              </button>
            );
          })}
        </div>

        {/* Season lifecycle controls */}
        <div className="border-t border-border pt-4 space-y-3">
          <h3 className="text-sm font-bold text-foreground">Season Lifecycle</h3>

          {seasonStatus !== "complete" && (
            <div className="flex flex-wrap items-center gap-3">
              <Button
                size="sm"
                onClick={completeSeason}
                disabled={completing}
                data-testid="health-complete-season-btn"
              >
                <Crown className="h-4 w-4 mr-1.5" />
                {completing ? "Archiving..." : `Mark ${health.current_season_year} season complete`}
              </Button>
              <p className="text-xs text-muted-foreground flex-1 min-w-[200px]">
                Snapshots awards, records, rosters, and points → feeds analytics, league history, trophy room, and player career stats.
              </p>
            </div>
          )}

          {seasonStatus === "complete" && !showRenewForm && (
            <div className="flex flex-wrap items-center gap-3 rounded-md bg-success/10 border border-success/30 p-3" data-testid="health-season-archived">
              <Crown className="h-5 w-5 text-success shrink-0" />
              <div className="flex-1 min-w-[200px]">
                <p className="text-sm font-semibold text-success">Season {health.current_season_year} archived</p>
                <p className="text-xs text-muted-foreground">Ready to start the next season — settings can be carried over.</p>
              </div>
              <Button size="sm" onClick={() => setShowRenewForm(true)} data-testid="health-show-renew-form-btn">
                Renew for {health.current_season_year + 1} <ChevronRight className="h-4 w-4 ml-1" />
              </Button>
            </div>
          )}

          {showRenewForm && (
            <div className="rounded-md border border-border p-3 space-y-3" data-testid="health-renew-form">
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div>
                  <Label htmlFor="renew-year" className="text-xs">New season year</Label>
                  <Input
                    id="renew-year"
                    type="number"
                    min={health.current_season_year + 1}
                    value={newYear}
                    onChange={(e) => setNewYear(parseInt(e.target.value || "0", 10))}
                    data-testid="health-renew-year-input"
                  />
                </div>
                <div className="flex items-center gap-2 sm:pt-5">
                  <Switch checked={carryOver} onCheckedChange={setCarryOver} id="carry-over" />
                  <Label htmlFor="carry-over" className="text-xs cursor-pointer">Carry over settings</Label>
                </div>
                <div className="flex items-center gap-2 sm:pt-5">
                  <Switch checked={resetRecords} onCheckedChange={setResetRecords} id="reset-records" />
                  <Label htmlFor="reset-records" className="text-xs cursor-pointer">Reset team records</Label>
                </div>
              </div>
              <div className="flex justify-end gap-2">
                <Button size="sm" variant="ghost" onClick={() => setShowRenewForm(false)} disabled={renewing}>Cancel</Button>
                <Button size="sm" onClick={renewSeason} disabled={renewing} data-testid="health-renew-btn">
                  {renewing ? "Renewing..." : `Start ${newYear} season`}
                </Button>
              </div>
            </div>
          )}

          {/* Past seasons */}
          {seasons.length > 0 && (
            <div className="space-y-1.5" data-testid="health-past-seasons">
              <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Past seasons ({seasons.length})</p>
              <div className="flex flex-wrap gap-1.5">
                {seasons.slice(0, 8).map((s) => (
                  <span
                    key={s.id}
                    className="text-[11px] px-2 py-0.5 rounded-full bg-secondary/30 border border-border"
                    title={s.champion_team_name ? `Champion: ${s.champion_team_name}` : ""}
                  >
                    {s.season_year}{s.champion_team_name ? ` 🏆` : ""}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
