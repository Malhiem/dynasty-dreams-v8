// @ts-nocheck
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { Checkbox } from "@/components/ui/checkbox";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { LockKeyhole, Save, Loader2 } from "lucide-react";
import api from "@/lib/api";
import { DAY_OPTIONS, LOCK_TIME_OPTIONS } from "./_shared";

export function RosterLockCard({ league, reloadLeague }: any) {
  const [lockType, setLockType] = useState<string>(league?.roster_lock_type || "daily");
  const [lockDay, setLockDay] = useState<string>(league?.roster_lock_day || "monday");
  const [lockSecondDay, setLockSecondDay] = useState<string>(league?.roster_lock_second_day || "thursday");
  const [lineupLockMins, setLineupLockMins] = useState<string>(
    String(league?.lineup_lock_minutes_before ?? 5),
  );
  const [playoffOverride, setPlayoffOverride] = useState<boolean>(!!league?.playoff_roster_lock_override);
  const [pLockType, setPLockType] = useState<string>(league?.playoff_roster_lock_type || "weekly");
  const [pLockDay, setPLockDay] = useState<string>(league?.playoff_roster_lock_day || "monday");
  const [pLockSecondDay, setPLockSecondDay] = useState<string>(league?.playoff_roster_lock_second_day || "thursday");
  const [pLineupLockMins, setPLineupLockMins] = useState<string>(
    String(league?.playoff_lineup_lock_minutes_before ?? 5),
  );
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setLockType(league?.roster_lock_type || "daily");
    setLockDay(league?.roster_lock_day || "monday");
    setLockSecondDay(league?.roster_lock_second_day || "thursday");
    setLineupLockMins(String(league?.lineup_lock_minutes_before ?? 5));
    setPlayoffOverride(!!league?.playoff_roster_lock_override);
    setPLockType(league?.playoff_roster_lock_type || "weekly");
    setPLockDay(league?.playoff_roster_lock_day || "monday");
    setPLockSecondDay(league?.playoff_roster_lock_second_day || "thursday");
    setPLineupLockMins(String(league?.playoff_lineup_lock_minutes_before ?? 5));
  }, [
    league?.id,
    league?.roster_lock_type,
    league?.roster_lock_day,
    league?.roster_lock_second_day,
    league?.lineup_lock_minutes_before,
    league?.playoff_roster_lock_override,
    league?.playoff_roster_lock_type,
    league?.playoff_roster_lock_day,
    league?.playoff_roster_lock_second_day,
    league?.playoff_lineup_lock_minutes_before,
  ]);

  const save = async () => {
    setSaving(true);
    try {
      await api.put(`/leagues/${league.id}`, {
        roster_lock_type: lockType,
        roster_lock_day: lockType === "daily" ? null : lockDay,
        roster_lock_second_day: lockType === "semi_weekly" ? lockSecondDay : null,
        lineup_lock_minutes_before: parseInt(lineupLockMins, 10) || 0,
        playoff_roster_lock_override: playoffOverride,
        playoff_roster_lock_type: playoffOverride ? pLockType : null,
        playoff_roster_lock_day: playoffOverride && pLockType !== "daily" ? pLockDay : null,
        playoff_roster_lock_second_day: playoffOverride && pLockType === "semi_weekly" ? pLockSecondDay : null,
        playoff_lineup_lock_minutes_before: playoffOverride ? (parseInt(pLineupLockMins, 10) || 0) : null,
      });
      toast.success("Roster lock rules saved");
      reloadLeague?.();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Failed to save roster lock rules");
    } finally {
      setSaving(false);
    }
  };

  const renderLockBlock = (
    prefix: string,
    type: string,
    setType: (v: string) => void,
    day: string,
    setDay: (v: string) => void,
    secondDay: string,
    setSecondDay: (v: string) => void,
    lockMins: string,
    setLockMins: (v: string) => void,
  ) => (
    <div className="space-y-4">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <div className="space-y-2">
          <Label className="text-xs">Lock cadence</Label>
          <Select value={type} onValueChange={setType}>
            <SelectTrigger className="bg-secondary border-border" data-testid={`${prefix}-lock-type`}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent className="bg-popover border-border z-50">
              <SelectItem value="daily">Daily Lock</SelectItem>
              <SelectItem value="semi_weekly">Semi-Weekly Lock</SelectItem>
              <SelectItem value="weekly">Weekly Lock</SelectItem>
            </SelectContent>
          </Select>
        </div>
        {type !== "daily" && (
          <div className="space-y-2">
            <Label className="text-xs">Primary lock day</Label>
            <Select value={day} onValueChange={setDay}>
              <SelectTrigger className="bg-secondary border-border" data-testid={`${prefix}-lock-day`}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent className="bg-popover border-border z-50">
                {DAY_OPTIONS.map((d) => (
                  <SelectItem key={d.value} value={d.value}>
                    {d.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        )}
        {type === "semi_weekly" && (
          <div className="space-y-2">
            <Label className="text-xs">Second lock day</Label>
            <Select value={secondDay} onValueChange={setSecondDay}>
              <SelectTrigger className="bg-secondary border-border" data-testid={`${prefix}-lock-second-day`}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent className="bg-popover border-border z-50">
                {DAY_OPTIONS.map((d) => (
                  <SelectItem key={d.value} value={d.value}>
                    {d.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        )}
      </div>
      <div className="space-y-2 max-w-md">
        <Label className="text-xs">Lineup lock time (5-min increments)</Label>
        <Select value={lockMins} onValueChange={setLockMins}>
          <SelectTrigger className="bg-secondary border-border" data-testid={`${prefix}-lineup-lock-mins`}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent className="bg-popover border-border z-50 max-h-72">
            {LOCK_TIME_OPTIONS.map((o) => (
              <SelectItem key={o.value} value={o.value}>
                {o.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <p className="text-[11px] text-muted-foreground">
          Lineup slots freeze this many minutes before the first NHL game of the scoring period.
        </p>
      </div>
    </div>
  );

  return (
    <Card className="bg-card border-border" data-testid="rules-schedule-roster-lock-card">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-lg">
          <LockKeyhole className="h-5 w-5 text-violet-400" />
          Roster Lock &amp; Lineup Lock
        </CardTitle>
        <CardDescription>
          Cadence of when transactions/lineups freeze for the scoring period.
          Optionally override the lock rules for playoff weeks only.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        <div>
          <div className="text-sm font-semibold mb-3 text-cyan-300">Regular Season Lock</div>
          {renderLockBlock(
            "regular",
            lockType,
            setLockType,
            lockDay,
            setLockDay,
            lockSecondDay,
            setLockSecondDay,
            lineupLockMins,
            setLineupLockMins,
          )}
        </div>

        <Separator />

        <div className="flex items-center gap-3">
          <Checkbox
            checked={playoffOverride}
            onCheckedChange={(c) => setPlayoffOverride(!!c)}
            id="rs-playoff-lock-override"
            data-testid="rules-schedule-playoff-lock-override"
          />
          <Label htmlFor="rs-playoff-lock-override" className="cursor-pointer text-sm">
            Change roster lock type for playoffs
          </Label>
        </div>

        {playoffOverride && (
          <div className="pl-1 border-l-2 border-amber-500/30 pl-4">
            <div className="text-sm font-semibold mb-3 text-amber-300">Playoff Lock Override</div>
            {renderLockBlock(
              "playoff",
              pLockType,
              setPLockType,
              pLockDay,
              setPLockDay,
              pLockSecondDay,
              setPLockSecondDay,
              pLineupLockMins,
              setPLineupLockMins,
            )}
          </div>
        )}

        <div className="flex justify-end">
          <Button size="sm" onClick={save} disabled={saving} data-testid="rules-schedule-roster-lock-save">
            {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4 mr-1" />}
            Save Lock Rules
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

