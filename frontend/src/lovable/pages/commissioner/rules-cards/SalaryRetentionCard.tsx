// @ts-nocheck
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { ArrowRightLeft, Save, Loader2 } from "lucide-react";
import CBABadge from "@/lovable/components/CBABadge";
import InfoHint from "@/components/ui/info-hint";
import api from "@/lib/api";

export function SalaryRetentionCard({ league, reloadLeague }: any) {
  const [enabled, setEnabled] = useState(!!league?.salary_retention_enabled);
  const [slots, setSlots] = useState<string>(String(league?.salary_retention_slots ?? 3));
  const [maxPct, setMaxPct] = useState<string>(String(league?.salary_retention_max_pct ?? 50));
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    setEnabled(!!league?.salary_retention_enabled);
    setSlots(String(league?.salary_retention_slots ?? 3));
    setMaxPct(String(league?.salary_retention_max_pct ?? 50));
  }, [league?.id, league?.salary_retention_enabled, league?.salary_retention_slots, league?.salary_retention_max_pct]);

  const save = async () => {
    const slotsN = parseInt(slots, 10);
    const pctN = parseInt(maxPct, 10);
    if (enabled) {
      if (Number.isNaN(slotsN) || slotsN < 1 || slotsN > 10) {
        toast.error("Retention slots must be between 1 and 10");
        return;
      }
      if (Number.isNaN(pctN) || pctN < 1 || pctN > 100) {
        toast.error("Max retention % must be between 1 and 100");
        return;
      }
    }
    setSaving(true);
    try {
      await api.put(`/leagues/${league.id}`, {
        salary_retention_enabled: enabled,
        salary_retention_slots: enabled ? slotsN : 0,
        salary_retention_max_pct: enabled ? pctN : 50,
      });
      toast.success(enabled ? `Retention: ${slotsN} slots @ ${pctN}% max` : "Retention disabled");
      reloadLeague?.();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Failed to save retention");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card className="bg-card border-border" data-testid="rules-schedule-retention-card">
      <CardHeader>
        <div className="flex items-center justify-between gap-4 flex-wrap">
          <div>
            <CardTitle className="flex items-center gap-2 text-lg">
              <ArrowRightLeft className="h-5 w-5 text-amber-400" />
              Salary Retention in Trades
            </CardTitle>
            <CardDescription>
              Toggle whether teams can keep paying part of a traded player&apos;s salary.
            </CardDescription>
          </div>
          {enabled && (
            <CBABadge
              slots={parseInt(slots, 10) || 0}
              maxPct={parseInt(maxPct, 10) || 0}
              testId="rules-schedule-retention-cba-badge"
            />
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-center gap-3">
          <Switch
            checked={enabled}
            onCheckedChange={setEnabled}
            id="rs-retention-enabled"
            data-testid="rules-schedule-retention-enabled"
          />
          <Label htmlFor="rs-retention-enabled" className="cursor-pointer font-semibold">
            Allow salary retention in trades?
            <InfoHint
              testId="info-retention-enabled"
              text="Mirrors the NHL CBA: when ON, the trading team can keep a % of a player's cap hit on their books to make the deal work. Configure the per-team slot count and max retained % below."
            />
          </Label>
        </div>
        {enabled && (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 max-w-xl">
            <div>
              <Label className="text-xs">Retention slots per team (1–10)</Label>
              <Input
                type="number"
                min={1}
                max={10}
                value={slots}
                onChange={(e) => setSlots(e.target.value)}
                data-testid="rules-schedule-retention-slots-input"
              />
            </div>
            <div>
              <Label className="text-xs">Max % of contract (1–100)</Label>
              <Input
                type="number"
                min={1}
                max={100}
                value={maxPct}
                onChange={(e) => setMaxPct(e.target.value)}
                data-testid="rules-schedule-retention-max-pct-input"
              />
            </div>
          </div>
        )}
        {!enabled && (
          <p className="text-xs text-muted-foreground italic">
            Retention is OFF — trades transfer the full contract value to the new team.
          </p>
        )}
        <div className="flex justify-end">
          <Button size="sm" onClick={save} disabled={saving} data-testid="rules-schedule-retention-save">
            {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4 mr-1" />}
            Save Retention
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}


