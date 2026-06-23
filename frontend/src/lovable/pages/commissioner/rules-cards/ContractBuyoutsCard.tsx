// @ts-nocheck
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { ArrowRightLeft, Save, Loader2 } from "lucide-react";
import InfoHint from "@/components/ui/info-hint";
import api from "@/lib/api";

export function ContractBuyoutsCard({ league, reloadLeague }: any) {
  const [enabled, setEnabled] = useState(!!league?.contract_buyouts_enabled);
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    setEnabled(!!league?.contract_buyouts_enabled);
  }, [league?.id, league?.contract_buyouts_enabled]);

  const save = async () => {
    setSaving(true);
    try {
      await api.put(`/leagues/${league.id}/admin/cap-settings`, {
        contract_buyouts_enabled: enabled,
      });
      toast.success(enabled ? "Contract buyouts enabled" : "Contract buyouts disabled");
      reloadLeague?.();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Failed to update buyouts setting");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card className="bg-card border-border" data-testid="rules-schedule-contract-buyouts-card">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-lg">
          <ArrowRightLeft className="h-5 w-5 text-amber-400" />
          Contract Buyouts
          <InfoHint
            testId="info-contract-buyouts"
            text="Per NHL CBA: a bought-out contract creates a dead-cap charge spread over 2× the remaining term, at roughly 1/3 of the AAV. Useful escape hatch for albatross contracts in dynasty leagues."
          />
        </CardTitle>
        <CardDescription>
          When enabled, teams may buy out a player&apos;s remaining contract. Buyouts
          create dead-cap charges spread over subsequent seasons (per NHL CBA
          convention — typically 2× the remaining term).
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex items-center gap-3">
          <Switch
            checked={enabled}
            onCheckedChange={setEnabled}
            id="rs-buyouts-enabled"
            data-testid="rules-schedule-contract-buyouts-toggle"
          />
          <Label htmlFor="rs-buyouts-enabled" className="cursor-pointer">
            Allow contract buyouts (creates dead cap)
          </Label>
        </div>
        <div className="flex justify-end">
          <Button size="sm" onClick={save} disabled={saving} data-testid="rules-schedule-contract-buyouts-save">
            {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4 mr-1" />}
            Save Buyouts
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
