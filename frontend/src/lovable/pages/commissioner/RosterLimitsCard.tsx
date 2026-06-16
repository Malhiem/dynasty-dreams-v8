// @ts-nocheck
// Iter 170c — Commissioner-editable per-section roster caps.
// Persists to `league.roster_limits` via the new PUT endpoint so the
// Roster Monitor (backend) and the frontend settings panel share one
// source of truth.

import { useEffect, useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import api from "@/lib/api";
import { Users } from "lucide-react";

const FIELDS: Array<{ key: string; label: string; help: string }> = [
  { key: "starting_skaters", label: "Starting Skaters", help: "Active skaters in the lineup each game" },
  { key: "starting_goalies", label: "Starting Goalies", help: "Active goalies in the lineup" },
  { key: "bench", label: "Bench", help: "Inactive skaters/goalies available for promotion" },
  { key: "ir", label: "Injured Reserve", help: "Slots reserved for IR-designated players" },
  { key: "minors", label: "Minors", help: "Development / farm slots (off active roster)" },
];

interface Props {
  leagueId?: string;
  isCommissioner?: boolean;
}

export default function RosterLimitsCard({ leagueId, isCommissioner = true }: Props) {
  const [limits, setLimits] = useState<Record<string, number> | null>(null);
  const [defaults, setDefaults] = useState<Record<string, number> | null>(null);
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!leagueId) return;
    let cancelled = false;
    setLoading(true);
    api.get(`/leagues/${leagueId}/roster-limits`)
      .then(({ data }) => {
        if (cancelled) return;
        setLimits(data?.roster_limits || {});
        setDefaults(data?.defaults || {});
      })
      .catch(() => { if (!cancelled) toast.error("Couldn't load roster limits"); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [leagueId]);

  const handleChange = (key: string, val: string) => {
    const n = parseInt(val, 10);
    setLimits((prev) => ({ ...(prev || {}), [key]: Number.isFinite(n) ? n : 0 }));
  };

  const handleSave = async () => {
    if (!leagueId || !limits) return;
    setSaving(true);
    try {
      const { data } = await api.put(`/leagues/${leagueId}/roster-limits`, limits);
      setLimits(data?.roster_limits || limits);
      toast.success(data?.changed ? "Roster limits saved" : "No changes to save");
    } catch (e: any) {
      toast.error("Couldn't save roster limits", {
        description: e?.response?.data?.detail || e?.message,
      });
    } finally {
      setSaving(false);
    }
  };

  const handleReset = () => {
    if (!defaults) return;
    setLimits({ ...defaults });
  };

  if (!leagueId) {
    return (
      <Card data-testid="roster-limits-card-empty">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Users className="h-4 w-4 text-primary" />
            Roster Limits
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">Select an active league to configure roster limits.</p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card data-testid="roster-limits-card">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Users className="h-4 w-4 text-primary" />
          Roster Limits
        </CardTitle>
        <CardDescription>
          Per-section caps used by the Roster Monitor and lineup enforcement. Defaults to a standard NHL fantasy template.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {loading || !limits ? (
          <p className="text-sm text-muted-foreground" data-testid="roster-limits-loading">Loading…</p>
        ) : (
          <>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {FIELDS.map((f) => (
                <div key={f.key} className="flex flex-col gap-1">
                  <Label htmlFor={`roster-limit-${f.key}`} className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
                    {f.label}
                  </Label>
                  <Input
                    id={`roster-limit-${f.key}`}
                    type="number"
                    min={0}
                    max={50}
                    value={limits[f.key] ?? 0}
                    disabled={!isCommissioner}
                    onChange={(e) => handleChange(f.key, e.target.value)}
                    data-testid={`roster-limit-input-${f.key}`}
                    className="h-9"
                  />
                  <p className="text-[10px] text-muted-foreground leading-tight">{f.help}</p>
                </div>
              ))}
            </div>
            {isCommissioner && (
              <div className="flex items-center justify-end gap-2 pt-2 border-t border-border/40">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={handleReset}
                  data-testid="roster-limits-reset"
                  disabled={saving}
                >
                  Reset to defaults
                </Button>
                <Button
                  variant="default"
                  size="sm"
                  onClick={handleSave}
                  data-testid="roster-limits-save"
                  disabled={saving}
                >
                  {saving ? "Saving…" : "Save Limits"}
                </Button>
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
