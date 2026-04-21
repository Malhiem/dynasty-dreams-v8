// @ts-nocheck
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Checkbox } from "@/components/ui/checkbox";
import { Badge } from "@/components/ui/badge";
import { Settings2, X } from "lucide-react";

const PLAYER_CRITERIA_OPTIONS = [
  { value: "all", label: "All Players" },
  { value: "rookies", label: "Rookies Only" },
  { value: "prospects", label: "Prospects Only" },
  { value: "nhl", label: "NHL Rostered Only" },
  { value: "unsigned", label: "Unsigned / Draft Eligible" },
];

const TIME_PER_PICK_OPTIONS = [
  { value: 120, label: "2 minutes" },
  { value: 150, label: "2.5 minutes" },
  { value: 300, label: "5 minutes" },
  { value: 600, label: "10 minutes" },
  { value: 900, label: "15 minutes" },
  { value: 1200, label: "20 minutes" },
  { value: 1800, label: "30 minutes" },
  { value: 2700, label: "45 minutes" },
  { value: 3600, label: "1 hour" },
  { value: 5400, label: "1.5 hours" },
  { value: 7200, label: "2 hours" },
  { value: 9000, label: "2.5 hours" },
  { value: 10800, label: "3 hours" },
  { value: 12600, label: "3.5 hours" },
  { value: 14400, label: "4 hours" },
  { value: 18000, label: "5 hours" },
  { value: 21600, label: "6 hours" },
];

export interface DraftConfig {
  draftType: string;
  rounds: number;
  timePerPick: number;
  snakeDraft: boolean;
  playerCriteria: string[];
  missedPickAction: string;
}

interface DraftSettingsProps {
  config: DraftConfig;
  onConfigChange: (config: DraftConfig) => void;
}

export function DraftSettings({ config, onConfigChange }: DraftSettingsProps) {
  const update = (partial: Partial<DraftConfig>) =>
    onConfigChange({ ...config, ...partial });

  const toggleCriteria = (value: string) => {
    const current = config.playerCriteria || [];
    if (value === "all") {
      update({ playerCriteria: ["all"] });
      return;
    }
    const withoutAll = current.filter((c) => c !== "all");
    const updated = withoutAll.includes(value)
      ? withoutAll.filter((c) => c !== value)
      : [...withoutAll, value];
    update({ playerCriteria: updated.length > 0 ? updated : ["all"] });
  };

  const removeCriteria = (value: string) => {
    const updated = (config.playerCriteria || []).filter((c) => c !== value);
    update({ playerCriteria: updated.length > 0 ? updated : ["all"] });
  };

  const criteriaList = config.playerCriteria || ["all"];

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-sm flex items-center gap-2">
          <Settings2 className="h-4 w-4 text-primary" />
          Draft Settings
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-2">
          <Label className="text-xs">Draft Type</Label>
          <Select value={config.draftType} onValueChange={(v) => update({ draftType: v })}>
            <SelectTrigger className="h-8 text-sm">
              <SelectValue />
            </SelectTrigger>
            <SelectContent className="bg-popover border-border z-50">
              <SelectItem value="startup">First-Time Team Draft</SelectItem>
              <SelectItem value="entry">NHL Entry Draft</SelectItem>
              <SelectItem value="supplemental">Supplemental Draft</SelectItem>
              <SelectItem value="expansion">Expansion Draft</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-2">
          <Label className="text-xs">Player Criteria</Label>
          {criteriaList.length > 0 && (
            <div className="flex flex-wrap gap-1 mb-2">
              {criteriaList.map((c) => {
                const opt = PLAYER_CRITERIA_OPTIONS.find((o) => o.value === c);
                return (
                  <Badge key={c} variant="secondary" className="text-xs gap-1 pr-1">
                    {opt?.label || c}
                    <button
                      onClick={() => removeCriteria(c)}
                      className="ml-0.5 rounded-full hover:bg-muted p-0.5"
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </Badge>
                );
              })}
            </div>
          )}
          <div className="space-y-2 rounded-md border border-border p-2">
            {PLAYER_CRITERIA_OPTIONS.map((opt) => (
              <div key={opt.value} className="flex items-center gap-2">
                <Checkbox
                  id={`criteria-${opt.value}`}
                  checked={criteriaList.includes(opt.value)}
                  onCheckedChange={() => toggleCriteria(opt.value)}
                />
                <label htmlFor={`criteria-${opt.value}`} className="text-sm cursor-pointer">
                  {opt.label}
                </label>
              </div>
            ))}
          </div>
        </div>

        <div className="space-y-2">
          <Label className="text-xs">Number of Rounds</Label>
          <Input
            type="number"
            min={1}
            max={30}
            className="h-8 text-sm"
            value={config.rounds}
            onChange={(e) => update({ rounds: parseInt(e.target.value) || 1 })}
          />
        </div>

        <div className="space-y-2">
          <Label className="text-xs">Time Per Pick</Label>
          <Select
            value={String(config.timePerPick)}
            onValueChange={(v) => update({ timePerPick: parseInt(v) })}
          >
            <SelectTrigger className="h-8 text-sm">
              <SelectValue />
            </SelectTrigger>
            <SelectContent className="bg-popover border-border z-50">
              {TIME_PER_PICK_OPTIONS.map((opt) => (
                <SelectItem key={opt.value} value={String(opt.value)}>
                  {opt.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-2">
          <Label className="text-xs">If a Team Misses Their Pick</Label>
          <Select
            value={config.missedPickAction || "auto-select"}
            onValueChange={(v) => update({ missedPickAction: v })}
          >
            <SelectTrigger className="h-8 text-sm">
              <SelectValue />
            </SelectTrigger>
            <SelectContent className="bg-popover border-border z-50">
              <SelectItem value="auto-select">Auto-select best available when timer expires</SelectItem>
              <SelectItem value="pick-anytime">Allow pick anytime when they return</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div className="flex items-center justify-between">
          <Label className="text-xs">Snake Draft Order</Label>
          <Switch
            checked={config.snakeDraft}
            onCheckedChange={(v) => update({ snakeDraft: v })}
          />
        </div>
      </CardContent>
    </Card>
  );
}
