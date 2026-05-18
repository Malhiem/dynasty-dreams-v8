// @ts-nocheck
/**
 * League Structure — Playoffs & Consolation sub-cards.
 *
 * Three cards now live inside `DivisionsTab.tsx`:
 *   1. <RegularSeasonScheduleCard>  — season length, opponents/period, stats window
 *   2. <PlayoffsCard>               — bracket size, weeks, rounds, format, seeding, custom
 *   3. <ConsolationCard>            — N teams (≤ non-playoff count), seeding, custom
 *
 * Cross-card validation lives on the shared draft state so the Save buttons
 * stay disabled until the configuration can actually crown a champion.
 */
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Save, Loader2, Trophy, Calendar, AlertTriangle, Plus, Trash2 } from "lucide-react";
import api from "@/lib/api";

type NhlWeek = { number: number; start_date: string; end_date: string; label: string };

const SEEDING_OPTIONS = [
  { value: "high_vs_low", label: "1 vs N, 2 vs N-1, … (high vs low)" },
  { value: "adjacent", label: "1 vs 2, 3 vs 4, … (adjacent)" },
  { value: "custom", label: "Custom (commissioner builds the ladder)" },
];

/* ───────────────────────── Regular Season Card ──────────────────────── */
export function RegularSeasonScheduleCard({ league, reloadLeague }: any) {
  const [nhlWeeks, setNhlWeeks] = useState<NhlWeek[]>([]);
  useEffect(() => {
    api.get(`/nhl-season-bounds`).then(({ data }) => setNhlWeeks(data?.weeks || [])).catch(() => {});
  }, []);

  const [regSeasonWeeks, setRegSeasonWeeks] = useState<string>(String(league?.regular_season_weeks ?? 18));
  const [matchupLen, setMatchupLen] = useState<string>(String(league?.matchup_length_days ?? 7));
  const [opponentsPerPeriod, setOpponentsPerPeriod] = useState<string>(String(league?.opponents_per_matchup_period ?? 1));
  const [statsStart, setStatsStart] = useState<string>(league?.stats_count_start_date || "");
  const [statsEnd, setStatsEnd] = useState<string>(league?.stats_count_end_date || "");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setRegSeasonWeeks(String(league?.regular_season_weeks ?? 18));
    setMatchupLen(String(league?.matchup_length_days ?? 7));
    setOpponentsPerPeriod(String(league?.opponents_per_matchup_period ?? 1));
    setStatsStart(league?.stats_count_start_date || "");
    setStatsEnd(league?.stats_count_end_date || "");
  }, [
    league?.id, league?.regular_season_weeks, league?.matchup_length_days,
    league?.opponents_per_matchup_period, league?.stats_count_start_date, league?.stats_count_end_date,
  ]);

  const teamCount = Number(league?.current_teams ?? league?.max_teams ?? 12);
  const maxOpponents = Math.max(1, teamCount - 1);

  const errors = useMemo(() => {
    const e: string[] = [];
    if (statsStart && statsEnd && statsStart > statsEnd) e.push("Stats end must be on or after the start date.");
    return e;
  }, [statsStart, statsEnd]);

  const save = async () => {
    if (errors.length) {
      toast.error(errors[0]);
      return;
    }
    setSaving(true);
    try {
      await api.put(`/leagues/${league.id}`, {
        regular_season_weeks: parseInt(regSeasonWeeks, 10),
        matchup_length_days: parseInt(matchupLen, 10),
        opponents_per_matchup_period: Math.min(maxOpponents, parseInt(opponentsPerPeriod, 10) || 1),
        stats_count_start_date: statsStart || null,
        stats_count_end_date: statsEnd || null,
      });
      toast.success("Regular Season Schedule saved");
      reloadLeague?.();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Failed to save");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card className="bg-card border-border" data-testid="regular-season-schedule-card">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-lg">
          <Calendar className="h-5 w-5 text-cyan-400" />
          Regular Season Schedule
        </CardTitle>
        <p className="text-sm text-muted-foreground">
          Season length, matchup period, opponents per period, and the NHL stats counting window.
        </p>
      </CardHeader>
      <CardContent className="space-y-5">
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <div className="space-y-1">
            <Label className="text-xs">Regular Season Weeks</Label>
            <Input type="number" min={4} max={30} value={regSeasonWeeks}
              onChange={(e) => setRegSeasonWeeks(e.target.value)} data-testid="rs-regular-season-weeks" />
          </div>
          <div className="space-y-1">
            <Label className="text-xs">Matchup Length (days)</Label>
            <Input type="number" min={1} max={30} value={matchupLen}
              onChange={(e) => setMatchupLen(e.target.value)} data-testid="rs-matchup-length" />
          </div>
          <div className="space-y-1">
            <Label className="text-xs">Opponents / Scoring Period (1–{maxOpponents})</Label>
            <Input type="number" min={1} max={maxOpponents} value={opponentsPerPeriod}
              onChange={(e) => setOpponentsPerPeriod(e.target.value)} data-testid="rs-opponents-per-period" />
            <p className="text-[10px] text-muted-foreground">
              {parseInt(opponentsPerPeriod, 10) > 1
                ? `Each team plays ${opponentsPerPeriod} separate H2H matchups every period.`
                : "Each team plays 1 opponent per period (standard H2H)."}
            </p>
          </div>
        </div>

        <div>
          <div className="text-xs font-semibold mb-2 text-emerald-300">League Stats Counting Window</div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 max-w-2xl">
            <div className="space-y-1">
              <Label className="text-xs">Stats start counting on</Label>
              <Select value={statsStart} onValueChange={setStatsStart}>
                <SelectTrigger className="bg-secondary border-border" data-testid="rs-stats-start">
                  <SelectValue placeholder="Select an NHL week…" />
                </SelectTrigger>
                <SelectContent className="bg-popover border-border z-50 max-h-72">
                  {nhlWeeks.map((w) => (
                    <SelectItem key={w.start_date} value={w.start_date}>{w.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Stats end counting on</Label>
              <Select value={statsEnd} onValueChange={setStatsEnd}>
                <SelectTrigger className="bg-secondary border-border" data-testid="rs-stats-end">
                  <SelectValue placeholder="Select an NHL week…" />
                </SelectTrigger>
                <SelectContent className="bg-popover border-border z-50 max-h-72">
                  {nhlWeeks.map((w) => (
                    <SelectItem key={w.end_date} value={w.end_date}>{w.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
        </div>

        {errors.length > 0 && (
          <div className="rounded-md border border-destructive/40 bg-destructive/10 p-3 space-y-1"
            data-testid="rs-validation-errors">
            {errors.map((err, i) => (
              <div key={i} className="flex items-start gap-2 text-xs text-destructive-foreground">
                <AlertTriangle className="h-3.5 w-3.5 text-destructive mt-0.5 shrink-0" />
                <span>{err}</span>
              </div>
            ))}
          </div>
        )}

        <div className="flex justify-end">
          <Button size="sm" onClick={save} disabled={saving || !league?.id || errors.length > 0}
            data-testid="rs-save-btn">
            {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4 mr-1" />}
            Save Regular Season
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

/* ───────────────────────── Custom Matchup Builder ───────────────────── */
function CustomMatchupBuilder({
  weeks, teams, value, onChange, testidPrefix,
}: {
  weeks: number[];
  teams: { id: string; name: string }[];
  value: any[];
  onChange: (next: any[]) => void;
  testidPrefix: string;
}) {
  const getWeekEntry = (wk: number) => value.find((v: any) => v.week === wk) || { week: wk, matchups: [] };

  const addMatchup = (wk: number) => {
    const entry = { ...getWeekEntry(wk) };
    entry.matchups = [...(entry.matchups || []), { home: "tbd", away: "tbd" }];
    const next = value.filter((v: any) => v.week !== wk).concat(entry);
    onChange(next);
  };

  const removeMatchup = (wk: number, idx: number) => {
    const entry = { ...getWeekEntry(wk) };
    entry.matchups = (entry.matchups || []).filter((_: any, i: number) => i !== idx);
    const next = value.filter((v: any) => v.week !== wk);
    if (entry.matchups.length) next.push(entry);
    onChange(next);
  };

  const setSlot = (wk: number, idx: number, side: "home" | "away", val: string) => {
    const entry = { ...getWeekEntry(wk) };
    entry.matchups = (entry.matchups || []).map((m: any, i: number) =>
      i === idx ? { ...m, [side]: val } : m,
    );
    const next = value.filter((v: any) => v.week !== wk).concat(entry);
    onChange(next);
  };

  if (!weeks.length) {
    return (
      <p className="text-xs text-muted-foreground italic">
        Set the start/end weeks above to enable the matchup builder.
      </p>
    );
  }

  return (
    <div className="space-y-3" data-testid={`${testidPrefix}-builder`}>
      {weeks.map((wk) => {
        const entry = getWeekEntry(wk);
        return (
          <div key={wk} className="rounded-md border border-border bg-secondary/30 p-3 space-y-2"
            data-testid={`${testidPrefix}-week-${wk}`}>
            <div className="flex items-center justify-between">
              <div className="text-xs font-semibold text-cyan-300">Week {wk}</div>
              <Button size="sm" variant="outline" onClick={() => addMatchup(wk)}
                data-testid={`${testidPrefix}-week-${wk}-add`}>
                <Plus className="h-3 w-3 mr-1" /> Add matchup
              </Button>
            </div>
            {(entry.matchups || []).length === 0 && (
              <p className="text-[11px] text-muted-foreground italic">
                No matchups yet — click <strong>Add matchup</strong> to create one (or leave TBD).
              </p>
            )}
            {(entry.matchups || []).map((m: any, idx: number) => (
              <div key={idx} className="grid grid-cols-[1fr_auto_1fr_auto] items-center gap-2"
                data-testid={`${testidPrefix}-week-${wk}-row-${idx}`}>
                <Select value={m.home || "tbd"} onValueChange={(v) => setSlot(wk, idx, "home", v)}>
                  <SelectTrigger className="h-8 text-xs bg-secondary border-border">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className="bg-popover border-border z-50 max-h-72">
                    <SelectItem value="tbd">TBD (Winner / Loser)</SelectItem>
                    {teams.map((t) => (
                      <SelectItem key={t.id} value={t.id}>{t.name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <span className="text-[10px] text-muted-foreground">vs</span>
                <Select value={m.away || "tbd"} onValueChange={(v) => setSlot(wk, idx, "away", v)}>
                  <SelectTrigger className="h-8 text-xs bg-secondary border-border">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className="bg-popover border-border z-50 max-h-72">
                    <SelectItem value="tbd">TBD (Winner / Loser)</SelectItem>
                    {teams.map((t) => (
                      <SelectItem key={t.id} value={t.id}>{t.name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Button size="icon" variant="ghost" onClick={() => removeMatchup(wk, idx)}
                  data-testid={`${testidPrefix}-week-${wk}-remove-${idx}`}>
                  <Trash2 className="h-3.5 w-3.5 text-destructive" />
                </Button>
              </div>
            ))}
          </div>
        );
      })}
    </div>
  );
}

/* ───────────────────────── Playoffs Card ───────────────────────────── */
export function PlayoffsCard({ league, reloadLeague, teams }: any) {
  const [playoffTeams, setPlayoffTeams] = useState<string>(String(league?.playoff_teams ?? 6));
  const [playoffStart, setPlayoffStart] = useState<string>(String(league?.playoff_start_week ?? 19));
  const [playoffEnd, setPlayoffEnd] = useState<string>(String(league?.playoff_end_week ?? 21));
  const [playoffRounds, setPlayoffRounds] = useState<string>(String(league?.playoff_rounds ?? 3));
  const regularScoring = String(league?.scoring_format || "h2h-points");
  const defaultFormat = regularScoring.startsWith("h2h") ? "h2h_matchup" : "h2h_matchup";
  const [format, setFormat] = useState<string>(league?.playoff_format || defaultFormat);
  const [seedingMethod, setSeedingMethod] = useState<string>(league?.playoff_seeding_method || "high_vs_low");
  const [customMatchups, setCustomMatchups] = useState<any[]>(league?.playoff_custom_matchups || []);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setPlayoffTeams(String(league?.playoff_teams ?? 6));
    setPlayoffStart(String(league?.playoff_start_week ?? 19));
    setPlayoffEnd(String(league?.playoff_end_week ?? 21));
    setPlayoffRounds(String(league?.playoff_rounds ?? 3));
    setFormat(league?.playoff_format || defaultFormat);
    setSeedingMethod(league?.playoff_seeding_method || "high_vs_low");
    setCustomMatchups(league?.playoff_custom_matchups || []);
  }, [
    league?.id, league?.playoff_teams, league?.playoff_start_week,
    league?.playoff_end_week, league?.playoff_rounds, league?.playoff_format,
    league?.playoff_seeding_method, league?.playoff_custom_matchups,
  ]);

  const reg = Number(league?.regular_season_weeks ?? 18);
  const startWeekOptions = Array.from({ length: 20 }, (_, i) => reg + 1 + i);
  const pStartNum = parseInt(playoffStart, 10) || (reg + 1);
  const endWeekOptions = Array.from({ length: 20 }, (_, i) => pStartNum + i);
  const playoffWeeks = (parseInt(playoffEnd, 10) || 0) - (parseInt(playoffStart, 10) || 0) + 1;
  const maxRounds = Math.max(1, Math.min(5, playoffWeeks));

  const errors = useMemo(() => {
    const e: string[] = [];
    const ps = parseInt(playoffStart, 10) || 0;
    const pe = parseInt(playoffEnd, 10) || 0;
    const rounds = parseInt(playoffRounds, 10) || 0;
    const tms = parseInt(playoffTeams, 10) || 0;
    if (ps <= reg) e.push(`Playoffs must start AFTER the regular season ends (week ${reg}).`);
    if (pe < ps) e.push(`Playoff end week (${pe}) cannot be before start week (${ps}).`);
    if (rounds > 0 && playoffWeeks < rounds) {
      e.push(`Cannot award a champion: ${rounds} rounds need ≥${rounds} weeks, only ${playoffWeeks} configured.`);
    }
    if (rounds > 0 && tms < 2 ** rounds) {
      e.push(`With ${rounds} round${rounds !== 1 ? "s" : ""}, you need at least ${2 ** rounds} playoff teams.`);
    }
    return e;
  }, [playoffStart, playoffEnd, playoffRounds, playoffTeams, playoffWeeks, reg]);

  const weeksList = useMemo(() => {
    const ps = parseInt(playoffStart, 10);
    const pe = parseInt(playoffEnd, 10);
    if (!ps || !pe || pe < ps) return [];
    const arr: number[] = [];
    for (let w = ps; w <= pe; w++) arr.push(w);
    return arr;
  }, [playoffStart, playoffEnd]);

  const save = async () => {
    if (errors.length) { toast.error(errors[0]); return; }
    setSaving(true);
    try {
      await api.put(`/leagues/${league.id}`, {
        playoff_teams: parseInt(playoffTeams, 10),
        playoff_start_week: parseInt(playoffStart, 10),
        playoff_end_week: parseInt(playoffEnd, 10),
        playoff_rounds: parseInt(playoffRounds, 10),
        playoff_format: format,
        playoff_seeding_method: format === "playoff_tree" ? seedingMethod : null,
        playoff_custom_matchups: format === "playoff_tree" && seedingMethod === "custom" ? customMatchups : null,
      });
      toast.success("Playoffs saved");
      reloadLeague?.();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Failed to save");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card className="bg-card border-border" data-testid="playoffs-card">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-lg">
          <Trophy className="h-5 w-5 text-amber-400" /> Playoffs
        </CardTitle>
        <p className="text-sm text-muted-foreground">
          Bracket size, weeks, rounds, format, and seeding method.
        </p>
      </CardHeader>
      <CardContent className="space-y-5">
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <div className="space-y-1">
            <Label className="text-xs">Playoff Teams</Label>
            <Input type="number" min={2} max={16} value={playoffTeams}
              onChange={(e) => setPlayoffTeams(e.target.value)} data-testid="po-teams" />
          </div>
          <div className="space-y-1">
            <Label className="text-xs">Start Week</Label>
            <Select value={playoffStart} onValueChange={setPlayoffStart}>
              <SelectTrigger className="bg-secondary border-border" data-testid="po-start-week">
                <SelectValue />
              </SelectTrigger>
              <SelectContent className="bg-popover border-border z-50 max-h-72">
                {startWeekOptions.map((w) => <SelectItem key={w} value={String(w)}>Week {w}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label className="text-xs">End Week</Label>
            <Select value={playoffEnd} onValueChange={setPlayoffEnd}>
              <SelectTrigger className="bg-secondary border-border" data-testid="po-end-week">
                <SelectValue />
              </SelectTrigger>
              <SelectContent className="bg-popover border-border z-50 max-h-72">
                {endWeekOptions.map((w) => <SelectItem key={w} value={String(w)}>Week {w}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label className="text-xs">Rounds (max {maxRounds})</Label>
            <Select value={playoffRounds} onValueChange={setPlayoffRounds}>
              <SelectTrigger className="bg-secondary border-border" data-testid="po-rounds">
                <SelectValue />
              </SelectTrigger>
              <SelectContent className="bg-popover border-border z-50">
                {[1, 2, 3, 4, 5].filter((n) => n <= maxRounds).map((n) => (
                  <SelectItem key={n} value={String(n)}>{n} Round{n > 1 ? "s" : ""}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div className="space-y-1">
            <Label className="text-xs">Playoff Format</Label>
            <Select value={format} onValueChange={setFormat}>
              <SelectTrigger className="bg-secondary border-border" data-testid="po-format">
                <SelectValue />
              </SelectTrigger>
              <SelectContent className="bg-popover border-border z-50">
                <SelectItem value="h2h_matchup">H2H Matchup (same as regular season)</SelectItem>
                <SelectItem value="playoff_tree">Playoff Tree (elimination bracket)</SelectItem>
              </SelectContent>
            </Select>
            <p className="text-[10px] text-muted-foreground">
              Defaults to your regular-season format. Choose Playoff Tree for a knockout bracket.
            </p>
          </div>
          {format === "playoff_tree" && (
            <div className="space-y-1">
              <Label className="text-xs">Seeding Method</Label>
              <Select value={seedingMethod} onValueChange={setSeedingMethod}>
                <SelectTrigger className="bg-secondary border-border" data-testid="po-seeding">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="bg-popover border-border z-50">
                  {SEEDING_OPTIONS.map((o) => (
                    <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}
        </div>

        {format === "playoff_tree" && seedingMethod === "custom" && (
          <div className="border-l-2 border-amber-500/40 pl-3 space-y-2">
            <div className="text-xs font-semibold text-amber-300">Custom Playoff Ladder</div>
            <p className="text-[11px] text-muted-foreground">
              Build each playoff week's matchups. Leave a slot as <strong>TBD</strong> for
              "Winner of …" / "Loser of …" — you'll get a top-bell notification 2 days
              before each week starts to finalize it.
            </p>
            <CustomMatchupBuilder
              weeks={weeksList}
              teams={teams || []}
              value={customMatchups}
              onChange={setCustomMatchups}
              testidPrefix="po-custom"
            />
          </div>
        )}

        {errors.length > 0 && (
          <div className="rounded-md border border-destructive/40 bg-destructive/10 p-3 space-y-1"
            data-testid="po-validation-errors">
            {errors.map((err, i) => (
              <div key={i} className="flex items-start gap-2 text-xs text-destructive-foreground">
                <AlertTriangle className="h-3.5 w-3.5 text-destructive mt-0.5 shrink-0" />
                <span>{err}</span>
              </div>
            ))}
          </div>
        )}

        <div className="flex justify-end">
          <Button size="sm" onClick={save} disabled={saving || !league?.id || errors.length > 0}
            data-testid="po-save-btn">
            {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4 mr-1" />}
            Save Playoffs
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

/* ───────────────────────── Consolation Card ─────────────────────────── */
export function ConsolationCard({ league, reloadLeague, teams }: any) {
  const [enabled, setEnabled] = useState<boolean>(!!league?.consolation_enabled);
  const totalTeams = Number(league?.current_teams ?? league?.max_teams ?? 12);
  const playoffTeams = Number(league?.playoff_teams ?? 6);
  const maxConsolation = Math.max(0, totalTeams - playoffTeams);

  const [consolationTeams, setConsolationTeams] = useState<string>(
    String(league?.consolation_teams ?? Math.min(maxConsolation, 4)),
  );
  const [seedingMethod, setSeedingMethod] = useState<string>(
    league?.consolation_seeding_method || "high_vs_low",
  );
  const [customMatchups, setCustomMatchups] = useState<any[]>(league?.consolation_custom_matchups || []);
  const [consolationAlong, setConsolationAlong] = useState<boolean>(
    league?.consolation_uses_playoff_schedule !== false,
  );
  const [consolationStart, setConsolationStart] = useState<string>(String(league?.consolation_start_week ?? ""));
  const [consolationEnd, setConsolationEnd] = useState<string>(String(league?.consolation_end_week ?? ""));
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setEnabled(!!league?.consolation_enabled);
    setConsolationTeams(String(league?.consolation_teams ?? Math.min(maxConsolation, 4)));
    setSeedingMethod(league?.consolation_seeding_method || "high_vs_low");
    setCustomMatchups(league?.consolation_custom_matchups || []);
    setConsolationAlong(league?.consolation_uses_playoff_schedule !== false);
    setConsolationStart(String(league?.consolation_start_week ?? ""));
    setConsolationEnd(String(league?.consolation_end_week ?? ""));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    league?.id, league?.consolation_enabled, league?.consolation_teams,
    league?.consolation_seeding_method, league?.consolation_custom_matchups,
    league?.consolation_uses_playoff_schedule, league?.consolation_start_week, league?.consolation_end_week,
  ]);

  const errors = useMemo(() => {
    const e: string[] = [];
    if (enabled) {
      const ct = parseInt(consolationTeams, 10) || 0;
      if (ct < 2) e.push("Consolation bracket needs at least 2 teams.");
      if (ct > maxConsolation) e.push(`Only ${maxConsolation} teams are outside the playoffs — can't have more than that in consolation.`);
      if (!consolationAlong) {
        const cs = parseInt(consolationStart, 10);
        const ce = parseInt(consolationEnd, 10);
        if (cs && ce && ce < cs) e.push("Consolation end week cannot be before start week.");
      }
    }
    return e;
  }, [enabled, consolationTeams, consolationAlong, consolationStart, consolationEnd, maxConsolation]);

  const startWk = consolationAlong
    ? Number(league?.playoff_start_week ?? 19)
    : parseInt(consolationStart, 10) || Number(league?.playoff_start_week ?? 19);
  const endWk = consolationAlong
    ? Number(league?.playoff_end_week ?? 21)
    : parseInt(consolationEnd, 10) || Number(league?.playoff_end_week ?? 21);
  const weeksList = useMemo(() => {
    if (!startWk || !endWk || endWk < startWk) return [];
    const arr: number[] = [];
    for (let w = startWk; w <= endWk; w++) arr.push(w);
    return arr;
  }, [startWk, endWk]);

  const save = async () => {
    if (errors.length) { toast.error(errors[0]); return; }
    setSaving(true);
    try {
      const payload: any = {
        consolation_enabled: enabled,
        consolation_uses_playoff_schedule: consolationAlong,
        consolation_start_week:
          enabled && !consolationAlong && consolationStart ? parseInt(consolationStart, 10) :
          enabled && consolationAlong ? Number(league?.playoff_start_week ?? 19) : null,
        consolation_end_week:
          enabled && !consolationAlong && consolationEnd ? parseInt(consolationEnd, 10) :
          enabled && consolationAlong ? Number(league?.playoff_end_week ?? 21) : null,
        consolation_teams: enabled ? (parseInt(consolationTeams, 10) || 0) : null,
        consolation_seeding_method: enabled ? seedingMethod : null,
        consolation_custom_matchups: enabled && seedingMethod === "custom" ? customMatchups : null,
      };
      await api.put(`/leagues/${league.id}`, payload);
      toast.success("Consolation bracket saved");
      reloadLeague?.();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Failed to save");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card className="bg-card border-border" data-testid="consolation-card">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-lg">
          <Trophy className="h-5 w-5 text-violet-400" /> Consolation Bracket
        </CardTitle>
        <p className="text-sm text-muted-foreground">
          For the {maxConsolation} team{maxConsolation !== 1 ? "s" : ""} not in the playoffs.
        </p>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-center gap-3">
          <Switch checked={enabled} onCheckedChange={setEnabled}
            id="co-enabled" data-testid="co-enabled" />
          <Label htmlFor="co-enabled" className="cursor-pointer font-semibold">
            Enable consolation playoff bracket
          </Label>
        </div>

        {enabled && (
          <>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <div className="space-y-1">
                <Label className="text-xs">Number of Teams (max {maxConsolation})</Label>
                <Input type="number" min={2} max={maxConsolation} value={consolationTeams}
                  onChange={(e) => setConsolationTeams(e.target.value)} data-testid="co-teams" />
              </div>
              <div className="space-y-1 sm:col-span-2">
                <Label className="text-xs">Seeding Method</Label>
                <Select value={seedingMethod} onValueChange={setSeedingMethod}>
                  <SelectTrigger className="bg-secondary border-border" data-testid="co-seeding">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className="bg-popover border-border z-50">
                    {SEEDING_OPTIONS.map((o) => (
                      <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <Switch checked={consolationAlong} onCheckedChange={setConsolationAlong}
                  id="co-along" data-testid="co-along" />
                <Label htmlFor="co-along" className="cursor-pointer text-sm">
                  Schedule along with the main playoffs
                </Label>
              </div>
              {!consolationAlong && (
                <div className="grid grid-cols-2 gap-3 max-w-lg">
                  <div>
                    <Label className="text-xs">Consolation start (week)</Label>
                    <Input type="number" min={1} max={40} value={consolationStart}
                      onChange={(e) => setConsolationStart(e.target.value)}
                      data-testid="co-start-week" />
                  </div>
                  <div>
                    <Label className="text-xs">Consolation end (week)</Label>
                    <Input type="number" min={1} max={40} value={consolationEnd}
                      onChange={(e) => setConsolationEnd(e.target.value)}
                      data-testid="co-end-week" />
                  </div>
                </div>
              )}
            </div>

            {seedingMethod === "custom" && (
              <div className="border-l-2 border-violet-500/40 pl-3 space-y-2">
                <div className="text-xs font-semibold text-violet-300">Custom Consolation Ladder</div>
                <p className="text-[11px] text-muted-foreground">
                  Build each week's matchups. Leave any slot as <strong>TBD</strong> for "Winner of …"
                  — you'll get a notification 2 days before to finalize.
                </p>
                <CustomMatchupBuilder
                  weeks={weeksList}
                  teams={teams || []}
                  value={customMatchups}
                  onChange={setCustomMatchups}
                  testidPrefix="co-custom"
                />
              </div>
            )}
          </>
        )}

        {errors.length > 0 && (
          <div className="rounded-md border border-destructive/40 bg-destructive/10 p-3 space-y-1"
            data-testid="co-validation-errors">
            {errors.map((err, i) => (
              <div key={i} className="flex items-start gap-2 text-xs text-destructive-foreground">
                <AlertTriangle className="h-3.5 w-3.5 text-destructive mt-0.5 shrink-0" />
                <span>{err}</span>
              </div>
            ))}
          </div>
        )}

        <div className="flex justify-end">
          <Button size="sm" onClick={save} disabled={saving || !league?.id || errors.length > 0}
            data-testid="co-save-btn">
            {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4 mr-1" />}
            Save Consolation
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
