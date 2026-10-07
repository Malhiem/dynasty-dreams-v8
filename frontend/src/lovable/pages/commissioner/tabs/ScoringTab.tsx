// @ts-nocheck
/**
 * Iter 155 — Scoring tab extracted from CommissionerSettings.tsx.
 *
 * Three cards:
 *   • Skater Scoring Categories — enable/disable + points per category
 *   • Goalie Scoring Categories — same controls for goalies
 *   • Scoring Summary — read-only chips of enabled categories + their weights
 * Action footer: "Reset to Defaults" + "Save Settings" buttons.
 */
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";

interface ScoringCategory {
  id: string;
  name: string;
  abbr: string;
  description: string;
  type: "skater" | "goalie" | "both";
}
interface ScoringSetting {
  enabled: boolean;
  points: number;
}

interface ScoringTabProps {
  skaterCategories: ScoringCategory[];
  goalieCategories: ScoringCategory[];
  scoringSettings: Record<string, ScoringSetting>;
  toggleScoringCategory: (id: string) => void;
  updateScoringPoints: (id: string, pts: number) => void;
  onReset: () => void;
  onSave: () => void;
  GoalieScoringCard?: React.ComponentType<any>;
  activeLeague?: any;
  reloadLeague?: () => void;
}

function CategoryRow({ cat, prefix, enabled, points, accentClass, onToggle, onChangePoints }: any) {
  return (
    <div
      className={`flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 p-3 rounded-lg border transition-colors ${
        enabled ? accentClass : "bg-secondary/30 border-border"
      }`}
      data-testid={`scoring-row-${cat.id}`}
    >
      <div className="flex items-start sm:items-center gap-3 flex-1 min-w-0">
        <Checkbox id={`${prefix}${cat.id}`} checked={enabled} onCheckedChange={onToggle} className="mt-0.5 sm:mt-0 shrink-0" />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <label htmlFor={`${prefix}${cat.id}`} className="font-medium cursor-pointer">
              {cat.name}
            </label>
            <Badge variant="outline" className="bg-secondary/50 text-xs">{cat.abbr}</Badge>
          </div>
          <p className="text-xs text-muted-foreground">{cat.description}</p>
        </div>
      </div>
      {/* Iter 231ao — Points input drops below the name/description on
          mobile so it never gets clipped off-screen by the parent card's
          overflow. On `sm+` we keep the original right-aligned layout. */}
      <div className="flex items-center justify-end gap-2 pl-9 sm:pl-0 shrink-0">
        <Label className="text-xs text-muted-foreground">Points:</Label>
        <Input
          type="number"
          step="0.1"
          inputMode="decimal"
          value={Number.isFinite(points) ? points : ""}
          onChange={(e) => onChangePoints(e.target.value === "" ? NaN : Number(e.target.value))}
          className="w-20 h-9 bg-secondary border-border text-center"
          disabled={!enabled}
          data-testid={`scoring-points-${cat.id}`}
        />
      </div>
    </div>
  );
}

export default function ScoringTab({
  skaterCategories,
  goalieCategories,
  scoringSettings,
  toggleScoringCategory,
  updateScoringPoints,
  onReset,
  onSave,
  GoalieScoringCard,
  activeLeague,
  reloadLeague,
}: ScoringTabProps) {
  const enabledSkaters = skaterCategories.filter((c) => scoringSettings[c.id]?.enabled);
  const enabledGoalies = goalieCategories.filter((c) => scoringSettings[c.id]?.enabled);
  return (
    <div className="space-y-6" data-testid="commissioner-scoring-tab">
      <Card className="bg-card border-border">
        <CardHeader>
          <CardTitle>Skater Scoring Categories</CardTitle>
          <CardDescription>Enable categories and set point values for skaters</CardDescription>
        </CardHeader>
        <CardContent>
          <ScrollArea className="h-[500px] pr-4">
            <div className="space-y-3">
              {skaterCategories.map((cat) => (
                <CategoryRow
                  key={cat.id}
                  cat={cat}
                  prefix=""
                  enabled={scoringSettings[cat.id]?.enabled}
                  points={scoringSettings[cat.id]?.points}
                  accentClass="bg-primary/5 border-primary/30"
                  onToggle={() => toggleScoringCategory(cat.id)}
                  onChangePoints={(v: number) => updateScoringPoints(cat.id, v)}
                />
              ))}
            </div>
          </ScrollArea>
        </CardContent>
      </Card>

      <Card className="bg-card border-border">
        <CardHeader>
          <CardTitle>Goalie Scoring Categories</CardTitle>
          <CardDescription>Enable categories and set point values for goalies</CardDescription>
        </CardHeader>
        <CardContent>
          <ScrollArea className="h-[350px] pr-4">
            <div className="space-y-3">
              {goalieCategories.map((cat) => (
                <CategoryRow
                  key={cat.id}
                  cat={cat}
                  prefix="goalie-"
                  enabled={scoringSettings[cat.id]?.enabled}
                  points={scoringSettings[cat.id]?.points}
                  accentClass="bg-accent/5 border-accent/30"
                  onToggle={() => toggleScoringCategory(cat.id)}
                  onChangePoints={(v: number) => updateScoringPoints(cat.id, v)}
                />
              ))}
            </div>
          </ScrollArea>
        </CardContent>
      </Card>

      <Card className="bg-card border-border">
        <CardHeader>
          <CardTitle>Scoring Summary</CardTitle>
          <CardDescription>Overview of enabled scoring categories</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid gap-4 md:grid-cols-2">
            <div>
              <Label className="text-sm font-medium">Enabled Skater Categories</Label>
              <div className="flex flex-wrap gap-1 mt-2" data-testid="scoring-summary-skaters">
                {enabledSkaters.map((cat) => (
                  <Badge key={cat.id} variant="secondary" className="text-xs">
                    {cat.abbr}: {(scoringSettings[cat.id]?.points || 0) > 0 ? "+" : ""}{scoringSettings[cat.id]?.points}
                  </Badge>
                ))}
              </div>
            </div>
            <div>
              <Label className="text-sm font-medium">Enabled Goalie Categories</Label>
              <div className="flex flex-wrap gap-1 mt-2" data-testid="scoring-summary-goalies">
                {enabledGoalies.map((cat) => (
                  <Badge key={cat.id} variant="secondary" className="text-xs">
                    {cat.abbr}: {(scoringSettings[cat.id]?.points || 0) > 0 ? "+" : ""}{scoringSettings[cat.id]?.points}
                  </Badge>
                ))}
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Goalie Scoring — method, caps, daily lock */}
      {GoalieScoringCard && activeLeague?.id && (
        <GoalieScoringCard league={activeLeague} reloadLeague={reloadLeague} />
      )}

      <div className="flex justify-end gap-3">
        <Button variant="outline" onClick={onReset} data-testid="scoring-reset-btn">Reset to Defaults</Button>
        <Button onClick={onSave} data-testid="scoring-save-btn">Save Settings</Button>
      </div>
    </div>
  );
}
