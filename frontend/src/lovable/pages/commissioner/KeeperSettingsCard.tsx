// @ts-nocheck
/**
 * Iter 141 — Keeper Draft configuration card.
 *
 * Visible only when draft_type === "keeper". Renders all settings the
 * league admin needs to lock in the keeper rules for the season:
 *   • Number of keepers
 *   • Max seasons a player can be kept
 *   • Keeper declaration deadline (days)
 *   • Keeper cost method (previous_round_drafted | fixed_round_penalty
 *                        | salary_cap | none)
 *   • Round-cost offset (if method needs one)
 *   • Allow rookie exceptions + late-round cost
 *   • Waiver pickups keepable + default round cost
 */
import { useEffect, useState } from "react";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Save } from "lucide-react";
import InfoHint from "@/components/ui/info-hint";
import { toast } from "sonner";
import api from "@/lib/api";

type Props = {
  leagueId?: string | null;
  isCommish?: boolean;
};

const DEFAULTS = {
  enabled: true,
  num_keepers: 3,
  max_seasons: 3,
  declaration_deadline_days: 30,
  cost_method: "previous_round_drafted",
  round_offset: 1,
  allow_rookie_exception: true,
  rookie_late_round: 10,
  waiver_pickups_keepable: false,
  waiver_default_round: 10,
};

export default function KeeperSettingsCard({ leagueId, isCommish }: Props) {
  const [cfg, setCfg] = useState<any>(DEFAULTS);
  const [loaded, setLoaded] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!leagueId) return;
    let cancelled = false;
    api.get(`/leagues/${leagueId}/keeper-config`)
      .then(({ data }) => {
        if (cancelled) return;
        setCfg({ ...DEFAULTS, ...(data?.config || {}) });
        setLoaded(true);
      })
      .catch(() => setLoaded(true));
    return () => { cancelled = true; };
  }, [leagueId]);

  const set = (k: string) => (v: any) => setCfg((p: any) => ({ ...p, [k]: v }));

  const save = async () => {
    if (!leagueId) return;
    setSaving(true);
    try {
      await api.put(`/leagues/${leagueId}/keeper-config`, { config: cfg });
      toast.success("Keeper configuration saved");
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Failed to save keeper config");
    } finally {
      setSaving(false);
    }
  };

  const showOffset =
    cfg.cost_method === "previous_round_drafted" ||
    cfg.cost_method === "fixed_round_penalty";

  return (
    <div className="space-y-4" data-testid="keeper-settings-card">
      <div>
        <Label className="text-sm">Keeper Draft Settings</Label>
        <p className="text-xs text-muted-foreground">
          Configure how keepers are retained, costed, and declared each season.
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label className="text-xs" htmlFor="keeper-num">
            Number of keepers
            <InfoHint testId="info-keeper-num" text="Total players each team may retain into the next season." />
          </Label>
          <Input
            id="keeper-num"
            type="number"
            min={0}
            max={50}
            value={cfg.num_keepers}
            onChange={(e) => set("num_keepers")(Number(e.target.value || 0))}
            disabled={!isCommish}
            data-testid="keeper-num-input"
          />
        </div>

        <div className="space-y-1.5">
          <Label className="text-xs" htmlFor="keeper-max-seasons">
            Max seasons a player can be kept
            <InfoHint testId="info-keeper-max-seasons" text="Limit on how many consecutive seasons the same player may be retained before they must re-enter the player pool." />
          </Label>
          <Input
            id="keeper-max-seasons"
            type="number"
            min={1}
            max={20}
            value={cfg.max_seasons}
            onChange={(e) => set("max_seasons")(Number(e.target.value || 0))}
            disabled={!isCommish}
            data-testid="keeper-max-seasons-input"
          />
        </div>

        <div className="space-y-1.5">
          <Label className="text-xs" htmlFor="keeper-deadline">
            Declaration Deadline (days)
            <InfoHint testId="info-keeper-deadline" text="Days before the draft by which teams must lock in their keeper selections." />
          </Label>
          <Input
            id="keeper-deadline"
            type="number"
            min={0}
            max={365}
            value={cfg.declaration_deadline_days}
            onChange={(e) => set("declaration_deadline_days")(Number(e.target.value || 0))}
            disabled={!isCommish}
            data-testid="keeper-deadline-input"
          />
        </div>

        <div className="space-y-1.5">
          <Label className="text-xs">
            Keeper Cost Method
            <InfoHint
              testId="info-keeper-cost-method"
              text="How a keeper's cost is determined: by the round they were drafted, a flat round penalty, salary cap impact, or no cost at all."
            />
          </Label>
          <Select
            value={cfg.cost_method}
            onValueChange={set("cost_method")}
            disabled={!isCommish}
          >
            <SelectTrigger data-testid="keeper-cost-method-trigger">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="previous_round_drafted" data-testid="keeper-cost-method-previous_round_drafted">
                Previous round drafted
              </SelectItem>
              <SelectItem value="fixed_round_penalty" data-testid="keeper-cost-method-fixed_round_penalty">
                Fixed round penalty
              </SelectItem>
              <SelectItem value="salary_cap" data-testid="keeper-cost-method-salary_cap">
                Salary cap
              </SelectItem>
              <SelectItem value="none" data-testid="keeper-cost-method-none">
                None
              </SelectItem>
            </SelectContent>
          </Select>
        </div>

        {showOffset && (
          <div className="space-y-1.5 sm:col-span-2">
            <Label className="text-xs" htmlFor="keeper-offset">
              Rounds earlier than original pick
              <InfoHint
                testId="info-keeper-offset"
                text="Rounds earlier than the original pick you would pay. e.g. 1 = 1 round higher, 2 = 2 rounds higher. This discourages keeping anyone but elite talent since mid-round picks can get expensive fast."
              />
            </Label>
            <Input
              id="keeper-offset"
              type="number"
              min={0}
              max={15}
              value={cfg.round_offset}
              onChange={(e) => set("round_offset")(Number(e.target.value || 0))}
              disabled={!isCommish}
              className="max-w-[160px]"
              data-testid="keeper-offset-input"
            />
          </div>
        )}
      </div>

      {/* Rookie exceptions */}
      <div className="rounded-md border border-border p-3 space-y-3" data-testid="keeper-rookie-block">
        <div className="flex items-center justify-between">
          <div>
            <Label className="text-sm" htmlFor="keeper-rookie-switch">
              Allow Rookie Exceptions
              <InfoHint
                testId="info-keeper-rookie"
                text="Allows first-year players to be kept at a fixed late round cost (e.g. 10th round or later) regardless of where they were drafted."
              />
            </Label>
          </div>
          <Switch
            id="keeper-rookie-switch"
            checked={!!cfg.allow_rookie_exception}
            onCheckedChange={set("allow_rookie_exception")}
            disabled={!isCommish}
            data-testid="keeper-rookie-switch"
          />
        </div>
        {cfg.allow_rookie_exception && (
          <div className="space-y-1.5">
            <Label className="text-xs" htmlFor="keeper-rookie-round">
              Rookie keep round (round or later)
            </Label>
            <Input
              id="keeper-rookie-round"
              type="number"
              min={1}
              max={30}
              value={cfg.rookie_late_round}
              onChange={(e) => set("rookie_late_round")(Number(e.target.value || 0))}
              disabled={!isCommish}
              className="max-w-[160px]"
              data-testid="keeper-rookie-round-input"
            />
          </div>
        )}
      </div>

      {/* Waiver pickups */}
      <div className="rounded-md border border-border p-3 space-y-3" data-testid="keeper-waiver-block">
        <div className="flex items-center justify-between">
          <div>
            <Label className="text-sm" htmlFor="keeper-waiver-switch">
              Waiver pickups keepable
              <InfoHint
                testId="info-keeper-waiver"
                text="Decides whether a player you added off the waiver wire mid-season can be kept the following year. If enabled, a player you picked up for free (i.e. with no draft round attached) is typically assigned a default round cost."
              />
            </Label>
          </div>
          <Switch
            id="keeper-waiver-switch"
            checked={!!cfg.waiver_pickups_keepable}
            onCheckedChange={set("waiver_pickups_keepable")}
            disabled={!isCommish}
            data-testid="keeper-waiver-switch"
          />
        </div>
        {cfg.waiver_pickups_keepable && (
          <div className="space-y-1.5">
            <Label className="text-xs" htmlFor="keeper-waiver-round">
              Default round cost for waiver keepers
            </Label>
            <Input
              id="keeper-waiver-round"
              type="number"
              min={1}
              max={30}
              value={cfg.waiver_default_round}
              onChange={(e) => set("waiver_default_round")(Number(e.target.value || 0))}
              disabled={!isCommish}
              className="max-w-[160px]"
              data-testid="keeper-waiver-round-input"
            />
          </div>
        )}
      </div>

      {isCommish ? (
        <div className="flex justify-end">
          <Button size="sm" onClick={save} disabled={saving || !loaded} data-testid="keeper-save">
            <Save className="h-4 w-4 mr-1" /> Save keeper settings
          </Button>
        </div>
      ) : (
        <div className="text-xs italic text-muted-foreground">
          Only commissioners may change keeper settings.
        </div>
      )}
    </div>
  );
}
