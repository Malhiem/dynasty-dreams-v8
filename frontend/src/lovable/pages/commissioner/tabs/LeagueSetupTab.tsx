// @ts-nocheck
/**
 * Iter 156 — LeagueSetupTab extracted from CommissionerSettings.tsx.
 *
 * Contains every card that previously lived under the "league-setup"
 * TabsContent block (Privacy + Recalc Stats, Scoring System, League Logo,
 * League Structure, Salary Cap, Roster Lock/Lineup Lock cards, and the
 * legacy "Lock Style Preset" panel). All state remains parent-owned;
 * we just lift the JSX into a focused presentational component.
 */
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Separator } from "@/components/ui/separator";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Image as ImageIcon, Upload, Sliders, Loader2, Check, AlertCircle } from "lucide-react";
import { useState } from "react";

interface LeagueSetupTabProps {
  // Privacy + stats
  isPrivate: boolean;
  togglePrivacy: () => void;
  privacyLoading: boolean;
  activeLeague: any;
  recalcStats: () => void;
  recalcing: boolean;
  // Scoring format
  scoringFormat: string;
  setScoringFormat: (v: string) => void;
  savingScoringFormat?: boolean;
  scoringFormatError?: boolean;
  // Playoffs toggle
  playoffsEnabled: boolean;
  savingPlayoffsEnabled?: boolean;
  onPlayoffsEnabledChange: (v: boolean) => void;
  // Max teams
  onMaxTeamsChange?: (v: number) => void;
  // League logo
  leagueLogo: string | null;
  leagueLogoName: string | null;
  logoInputRef: React.MutableRefObject<HTMLInputElement | null>;
  handleLogoUpload: (e: React.ChangeEvent<HTMLInputElement>) => void;
  setLeagueLogo: (v: string | null) => void;
  setLeagueLogoName: (v: string | null) => void;
  // Lock cards
  RosterLockCard: React.ComponentType<any>;
  EmergencyRosterChangesCard: React.ComponentType<any>;
  GoalieScoringCard: React.ComponentType<any>;
  reloadLeague: () => void;
  // Lock-style preset
  isH2H: boolean;
  rosterLockType: string;
  setRosterLockType: (v: string) => void;
  scoringPeriodStartDay: string;
  setScoringPeriodStartDay: (v: string) => void;
  semiWeeklySplitDay: string;
  setSemiWeeklySplitDay: (v: string) => void;
}

const SCORING_FORMATS = [
  { value: "rotisserie",     label: "Rotisserie",                  desc: "Team scores based on their rank compared to all other fantasy teams in selected scoring categories" },
  { value: "points",         label: "Points-Based",                desc: "Team scores points based on scoring criteria for selected scoring categories" },
  { value: "h2h-points",     label: "Head-to-Head Points",         desc: "Teams compete against one opponent per matchup and score points based on scoring criteria for selected scoring categories" },
  { value: "h2h-categories", label: "Head-to-Head Most Categories", desc: "Teams compete against one opponent per matchup based on selected scoring categories and will win/lose/tie based on the outcome of the scoring period against the opponent" },
  { value: "h2h-each",       label: "Head-to-Head Each Category",   desc: "Teams compete against one opponent per matchup based on selected scoring categories and will win/lose/tie in each category per scoring period" },
];
const LOCK_STYLE_OPTIONS = [
  { value: "daily",        label: "Daily Lock",          desc: "Adjust lineups every day." },
  { value: "weekly",       label: "Weekly Lock",         desc: "One lock at period start." },
  { value: "semi-weekly",  label: "Semi-Weekly Lock",    desc: "Mid-period adjustment window." },
  { value: "first-game",   label: "First Game of Matchup", desc: "Each player locks on their own first game." },
];
const DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"];
const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

export default function LeagueSetupTab(p: LeagueSetupTabProps) {
  return (
    <div className="space-y-6" data-testid="commissioner-league-setup-tab">
      {/* ─── Privacy + Recalc Stats ────────────────────────── */}
      <Card className="bg-card border-border" data-testid="league-privacy-card">
        <CardHeader>
          <div className="flex items-start justify-between gap-4 flex-wrap">
            <div>
              <CardTitle className="flex items-center gap-2">
                {p.isPrivate ? "🔒 Private League" : "🌐 Public League"}
              </CardTitle>
              <CardDescription className="mt-1">
                {p.isPrivate
                  ? "Hidden from League Search — owners can only join via invite link/code."
                  : "Listed in League Search — any account can browse and self-join while spots remain."}
              </CardDescription>
            </div>
            <div className="flex items-center gap-3">
              <span className="text-xs text-muted-foreground">Public</span>
              <Switch
                checked={p.isPrivate}
                onCheckedChange={p.togglePrivacy}
                disabled={p.privacyLoading || !p.activeLeague?.id}
                data-testid="league-privacy-toggle"
              />
              <span className="text-xs text-muted-foreground">Private</span>
            </div>
          </div>
        </CardHeader>
        <CardContent className="pt-0 pb-4 flex items-center justify-between gap-3 border-t border-border/50">
          <div className="text-xs text-muted-foreground">
            <strong className="text-foreground">Stats out of sync?</strong> Recompute every team's wins / losses / PF / PA from completed matchups.
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={p.recalcStats}
            disabled={p.recalcing || !p.activeLeague?.id}
            data-testid="league-recalc-stats"
          >
            {p.recalcing ? "Recalculating…" : "Recalculate Stats"}
          </Button>
        </CardContent>
      </Card>

      {/* Scoring System */}
      <Card className="bg-card border-border" data-testid="scoring-system-card">
        <CardHeader>
          <CardTitle>Scoring System</CardTitle>
          <CardDescription>Choose how teams earn points and compete</CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="space-y-3">
            <Label>Scoring Format</Label>
            {p.scoringFormatError && (
              <div className="flex items-center gap-2 text-destructive text-xs" data-testid="scoring-format-error">
                <AlertCircle className="h-3.5 w-3.5" />
                Save failed — your selection is not yet saved. Click again to retry.
              </div>
            )}
            <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
              {SCORING_FORMATS.map((option) => {
                const isSelected = p.scoringFormat === option.value;
                const isSaving = isSelected && p.savingScoringFormat;
                return (
                  <button
                    key={option.value}
                    type="button"
                    onClick={() => p.setScoringFormat(option.value)}
                    disabled={p.savingScoringFormat}
                    data-testid={`scoring-format-${option.value}`}
                    className={`relative flex flex-col gap-1.5 rounded-lg border p-4 text-left transition-all hover:border-primary/50 disabled:opacity-60 disabled:cursor-wait ${
                      isSelected
                        ? p.scoringFormatError
                          ? "border-destructive bg-destructive/10 ring-1 ring-destructive/30"
                          : "border-primary bg-primary/10 ring-1 ring-primary/30"
                        : "border-border bg-secondary/50 hover:bg-secondary"
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      <div className={`h-3 w-3 rounded-full border-2 flex items-center justify-center ${
                        isSelected
                          ? p.scoringFormatError ? "border-destructive" : "border-primary"
                          : "border-muted-foreground/40"
                      }`}>
                        {isSelected && !isSaving && (
                          <div className={`h-1.5 w-1.5 rounded-full ${p.scoringFormatError ? "bg-destructive" : "bg-primary"}`} />
                        )}
                      </div>
                      <span className="font-medium text-sm">{option.label}</span>
                      {isSaving && <Loader2 className="h-3.5 w-3.5 animate-spin text-primary ml-auto" />}
                      {isSelected && !isSaving && !p.scoringFormatError && (
                        <Check className="h-3.5 w-3.5 text-primary ml-auto" />
                      )}
                      {isSelected && !isSaving && p.scoringFormatError && (
                        <AlertCircle className="h-3.5 w-3.5 text-destructive ml-auto" />
                      )}
                    </div>
                    <p className="text-xs text-muted-foreground leading-relaxed pl-5">{option.desc}</p>
                  </button>
                );
              })}
            </div>
          </div>
          <Separator />
          <div className="space-y-2 max-w-xs">
            <Label>Scoring Period</Label>
            <Select defaultValue="weekly">
              <SelectTrigger className="bg-secondary border-border"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="daily">Daily</SelectItem>
                <SelectItem value="weekly">Weekly</SelectItem>
                <SelectItem value="biweekly">Bi-Weekly</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      {/* League Logo */}
      <Card className="bg-card border-border">
        <CardHeader>
          <CardTitle>League Logo</CardTitle>
          <CardDescription>Upload a custom logo for your league (max 2MB, image files only)</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center gap-4">
            <div className="h-20 w-20 rounded-lg border-2 border-dashed border-border flex items-center justify-center bg-secondary/50 overflow-hidden shrink-0">
              {p.leagueLogo ? (
                <img src={p.leagueLogo} alt="League logo" className="h-full w-full object-contain" />
              ) : (
                <ImageIcon className="h-8 w-8 text-muted-foreground/40" />
              )}
            </div>
            <div className="space-y-2">
              <input
                ref={p.logoInputRef}
                type="file"
                accept="image/*"
                onChange={p.handleLogoUpload}
                className="hidden"
              />
              <div className="flex items-center gap-2">
                <Button variant="outline" size="sm" onClick={() => p.logoInputRef.current?.click()} className="gap-1.5">
                  <Upload className="h-3.5 w-3.5" /> Browse
                </Button>
                {p.leagueLogo && (
                  <Button variant="ghost" size="sm" onClick={() => { p.setLeagueLogo(null); p.setLeagueLogoName(null); }} className="text-destructive hover:text-destructive">
                    Remove
                  </Button>
                )}
              </div>
              {p.leagueLogoName && <p className="text-xs text-muted-foreground">{p.leagueLogoName}</p>}
              <p className="text-xs text-muted-foreground">PNG, JPG, or SVG. Maximum file size: 2MB.</p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* League Structure */}
      <Card className="bg-card border-border" data-testid="league-structure-card">
        <CardHeader>
          <CardTitle>League Structure</CardTitle>
          <CardDescription>Configure divisions, conferences, and playoffs</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 md:grid-cols-3">
            <div className="space-y-2">
              <Label>Number of Teams</Label>
              <Input
                type="number"
                min={2}
                max={p.activeLeague?.allow_duplicate_players ? 100 : 32}
                step={1}
                value={p.activeLeague?.max_teams ?? 12}
                onChange={(e) => {
                  const cap = p.activeLeague?.allow_duplicate_players ? 100 : 32;
                  const v = Math.max(2, Math.min(cap, parseInt(e.target.value || "0", 10)));
                  if (!p.activeLeague?.id || v === p.activeLeague?.max_teams) return;
                  p.onMaxTeamsChange?.(v);
                }}
                className="bg-secondary border-border"
                data-testid="league-structure-max-teams"
              />
              <p className="text-[10px] text-muted-foreground">
                {p.activeLeague?.allow_duplicate_players
                  ? "Up to 100 (duplicate players enabled)"
                  : "Up to 32 · enable duplicate players for more"}
              </p>
            </div>
            <div className="space-y-2">
              <Label>Number of Divisions</Label>
              <Select defaultValue="2">
                <SelectTrigger className="bg-secondary border-border"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="0">No Divisions</SelectItem>
                  <SelectItem value="2">2 Divisions</SelectItem>
                  <SelectItem value="4">4 Divisions</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label className={!p.playoffsEnabled ? "text-muted-foreground" : ""}>
                Playoff Teams
              </Label>
              <Select
                defaultValue="6"
                disabled={!p.playoffsEnabled}
              >
                <SelectTrigger
                  className={`bg-secondary border-border ${!p.playoffsEnabled ? "opacity-50 cursor-not-allowed" : ""}`}
                  data-testid="league-structure-playoff-teams"
                >
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {[4, 6, 8, 10, 12].map((n) => (
                    <SelectItem key={n} value={n.toString()}>{n} Teams</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <Separator />

          {/* Playoffs toggle */}
          <div className="flex items-center justify-between">
            <div>
              <Label htmlFor="playoffs-enabled-toggle">Enable Playoffs</Label>
              <p className="text-sm text-muted-foreground">
                {p.playoffsEnabled
                  ? "Top teams compete in a postseason bracket"
                  : "Season standings determine the winner"}
              </p>
            </div>
            <Switch
              id="playoffs-enabled-toggle"
              checked={p.playoffsEnabled}
              onCheckedChange={p.onPlayoffsEnabledChange}
              disabled={p.savingPlayoffsEnabled}
              data-testid="playoffs-enabled-toggle"
            />
          </div>
        </CardContent>
      </Card>

      {/* Salary Cap Settings */}
      <Card className="bg-card border-border">
        <CardHeader>
          <CardTitle>Salary Cap Settings</CardTitle>
          <CardDescription>Enable and configure salary cap rules</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <Label>Enable Salary Cap</Label>
              <p className="text-sm text-muted-foreground">Teams must stay under the cap</p>
            </div>
            <Switch defaultChecked />
          </div>
          <Separator />
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label>Cap Calculation Method</Label>
              <Select defaultValue="cap-hit">
                <SelectTrigger className="bg-secondary border-border"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="cap-hit">NHL Cap Hit</SelectItem>
                  <SelectItem value="aav">Average Annual Value (AAV)</SelectItem>
                  <SelectItem value="real-salary">Real Salary</SelectItem>
                  <SelectItem value="custom">Custom League Settings</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>Salary Cap Amount</Label>
              <div className="relative">
                <span className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground">$</span>
                <Input type="number" defaultValue="88000000" className="pl-7 bg-secondary border-border" />
              </div>
            </div>
          </div>
          <div className="flex items-center justify-between">
            <div>
              <Label>Cap Floor</Label>
              <p className="text-sm text-muted-foreground">Minimum spending requirement</p>
            </div>
            <Switch />
          </div>
        </CardContent>
      </Card>

      {/* Iter 103: Roster Lock & Lineup Lock + Iter 105: Emergency Roster + Goalie Scoring */}
      {p.activeLeague?.id && (
        <>
          <p.RosterLockCard league={p.activeLeague} reloadLeague={p.reloadLeague} />
          <p.EmergencyRosterChangesCard league={p.activeLeague} reloadLeague={p.reloadLeague} />
          <p.GoalieScoringCard league={p.activeLeague} reloadLeague={p.reloadLeague} />
          {/* Iter 228i — Roster Limits removed from League Setup. The canonical
               source of truth is now League Administration → Rosters →
               Roster Size and Position Breakdown. */}
        </>
      )}

      {/* Iter 104: Legacy Lock Style Preset */}
      <Card className={`bg-card border-border ${!p.isH2H ? "opacity-50 pointer-events-none" : ""}`} data-testid="legacy-roster-lock-rules-card">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-lg">
            <Sliders className="h-5 w-5 text-primary" /> Lock Style Preset
          </CardTitle>
          <CardDescription>
            Choose a high-level lock style. The detailed cadence + lock day + lineup lock time
            are configured in the <span className="text-foreground font-medium">Roster Lock &amp; Lineup Lock</span> card above.
          </CardDescription>
          {!p.isH2H && (
            <Badge variant="outline" className="bg-muted/90 backdrop-blur-sm text-muted-foreground border-border text-xs px-3 py-1.5 mt-2 self-start">
              Head-to-Head format required
            </Badge>
          )}
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-4">
            {LOCK_STYLE_OPTIONS.map((option) => (
              <button
                key={option.value}
                type="button"
                onClick={() => p.setRosterLockType(option.value)}
                className={`relative flex flex-col gap-1.5 rounded-lg border p-3 text-left transition-all hover:border-primary/50 ${
                  p.rosterLockType === option.value
                    ? "border-primary bg-primary/10 ring-1 ring-primary/30"
                    : "border-border bg-secondary/40 hover:bg-secondary"
                }`}
                data-testid={`lock-style-${option.value}`}
              >
                <div className="flex items-center gap-2">
                  <div className={`h-3 w-3 rounded-full border-2 flex items-center justify-center ${
                    p.rosterLockType === option.value ? "border-primary" : "border-muted-foreground/40"
                  }`}>
                    {p.rosterLockType === option.value && (
                      <div className="h-1.5 w-1.5 rounded-full bg-primary" />
                    )}
                  </div>
                  <span className="font-medium text-sm">{option.label}</span>
                </div>
                <p className="text-[11px] text-muted-foreground leading-snug pl-5">{option.desc}</p>
              </button>
            ))}
          </div>
          {(p.rosterLockType === "weekly" || p.rosterLockType === "semi-weekly") && (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 max-w-xl">
              <div className="space-y-1">
                <Label className="text-xs">Scoring Period Start Day</Label>
                <Select value={p.scoringPeriodStartDay} onValueChange={p.setScoringPeriodStartDay}>
                  <SelectTrigger className="bg-secondary border-border"><SelectValue /></SelectTrigger>
                  <SelectContent className="bg-popover border-border z-50">
                    {DAYS.map((day) => (
                      <SelectItem key={day} value={day}>{cap(day)}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              {p.rosterLockType === "semi-weekly" && (
                <div className="space-y-1">
                  <Label className="text-xs">Mid-Period Adjustment Day</Label>
                  <Select value={p.semiWeeklySplitDay} onValueChange={p.setSemiWeeklySplitDay}>
                    <SelectTrigger className="bg-secondary border-border"><SelectValue /></SelectTrigger>
                    <SelectContent className="bg-popover border-border z-50">
                      {DAYS.filter((d) => d !== p.scoringPeriodStartDay).map((day) => (
                        <SelectItem key={day} value={day}>{cap(day)}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              )}
            </div>
          )}
          <p className="text-[11px] text-muted-foreground italic">
            Emergency Roster Changes and Goalie Scoring rules now live under{" "}
            <span className="font-medium text-foreground">League Structure</span>.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
