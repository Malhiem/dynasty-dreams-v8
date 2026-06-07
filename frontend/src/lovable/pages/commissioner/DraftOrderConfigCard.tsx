// @ts-nocheck
/**
 * Iter 139 — Reusable Draft Order Configuration card.
 *
 * Owned by League Administration → Drafts (commissioner-only). The
 * DraftBoard page now READS the saved configuration via the
 * /draft-order endpoint and renders a read-only summary instead.
 *
 * Three formats are supported:
 *   • nhl_lottery — globally scheduled by the system admin (`role==admin`)
 *   • lottery_generator — commissioner schedules the run date
 *   • manual_entry — commissioner sets an optional date, blank = TBD
 */
import { useEffect, useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { CalendarDays, Save } from "lucide-react";
import { cn } from "@/lib/utils";
import { toast } from "sonner";
import api from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";

export const DRAFT_ORDER_METHOD_META: Record<string, { label: string; description: string }> = {
  nhl_lottery: {
    label: "NHL team draft lottery",
    description:
      "Pick order will mirror the official NHL Draft Lottery — date set by the system administrator and applies to every league using this format.",
  },
  lottery_generator: {
    label: "Draft Lottery Generator",
    description:
      "League will run its own weighted lottery — commissioner schedules the date when the lottery generator runs.",
  },
  manual_entry: {
    label: "Manual Entry",
    description:
      "Commissioner enters the draft order manually after the regular season — date is optional (blank = TBD).",
  },
};

type Props = {
  leagueId?: string | null;
  isCommish?: boolean;
  onSaved?: () => void;
  embedded?: boolean;
};

export default function DraftOrderConfigCard({ leagueId, isCommish, onSaved, embedded }: Props) {
  const { user } = useAuth();
  const isSystemAdmin = user?.role === "admin";

  const [loaded, setLoaded] = useState(false);
  const [method, setMethod] = useState<string>("manual_entry");
  const [scheduledAt, setScheduledAt] = useState<string>(""); // datetime-local
  const [systemDate, setSystemDate] = useState<string>("");
  const [saving, setSaving] = useState(false);

  // Load the current saved config from the draft-order endpoint
  useEffect(() => {
    if (!leagueId) return;
    let cancelled = false;
    api.get(`/leagues/${leagueId}/draft-order`).then(({ data }) => {
      if (cancelled) return;
      setMethod(data?.method || "manual_entry");
      if (data?.scheduled_at && data?.schedule_source === "league") {
        setScheduledAt(data.scheduled_at.slice(0, 16));
      }
      setLoaded(true);
    }).catch(() => setLoaded(true));
    return () => { cancelled = true; };
  }, [leagueId]);

  // System admins also load + edit the global NHL lottery date
  useEffect(() => {
    if (!isSystemAdmin) return;
    api.get("/admin/draft-lottery-date").then(({ data }) => {
      if (data?.nhl_lottery_date) setSystemDate(data.nhl_lottery_date.slice(0, 16));
    }).catch(() => {});
  }, [isSystemAdmin]);

  const saveLeagueConfig = async () => {
    if (!leagueId) return;
    setSaving(true);
    try {
      const body: any = { method };
      if (method === "lottery_generator" || method === "manual_entry") {
        body.scheduled_at = scheduledAt ? new Date(scheduledAt).toISOString() : "";
      }
      await api.put(`/leagues/${leagueId}/draft-order/config`, body);
      toast.success("Draft order configuration saved");
      onSaved?.();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Failed to save");
    } finally {
      setSaving(false);
    }
  };

  const saveSystemDate = async () => {
    setSaving(true);
    try {
      await api.put("/admin/draft-lottery-date", {
        nhl_lottery_date: systemDate ? new Date(systemDate).toISOString() : "",
      });
      toast.success("NHL lottery date saved (applies to all leagues)");
      onSaved?.();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Failed to save");
    } finally {
      setSaving(false);
    }
  };

  const body = (
    <>
      <div className="space-y-2">
        <Label className="text-sm">Draft Order &amp; Schedule</Label>
        <RadioGroup
          value={method}
          onValueChange={(v) => isCommish && setMethod(v)}
          className="space-y-2"
          data-testid="draft-order-method-radio"
        >
          {(["nhl_lottery", "lottery_generator", "manual_entry"] as const).map((m) => {
            const meta = DRAFT_ORDER_METHOD_META[m];
            return (
              <label
                key={m}
                htmlFor={`draft-order-method-${m}`}
                className={cn(
                  "flex items-start gap-2 rounded-md border p-2 cursor-pointer text-sm",
                  method === m ? "border-primary/50 bg-primary/5" : "border-border",
                  !isCommish && "opacity-70 cursor-not-allowed",
                )}
              >
                <RadioGroupItem id={`draft-order-method-${m}`} value={m} disabled={!isCommish} className="mt-0.5" />
                <div>
                  <div className="font-medium">{meta.label}</div>
                  <div className="text-xs text-muted-foreground">{meta.description}</div>
                </div>
              </label>
            );
          })}
        </RadioGroup>
      </div>

      {method === "nhl_lottery" && (
        <div className="rounded-md border border-border p-3 space-y-2" data-testid="draft-order-nhl-block">
          <Label className="text-xs uppercase tracking-wider text-muted-foreground">
            Scheduled NHL Lottery Date (global)
          </Label>
          {isSystemAdmin ? (
            <div className="flex items-center gap-2">
              <Input
                type="datetime-local"
                value={systemDate}
                onChange={(e) => setSystemDate(e.target.value)}
                className="max-w-xs"
                data-testid="draft-order-system-date-input"
              />
              <Button size="sm" onClick={saveSystemDate} disabled={saving} data-testid="draft-order-save-system-date">
                Save (all leagues)
              </Button>
            </div>
          ) : (
            <div className="text-sm" data-testid="draft-order-nhl-display">
              <span className="font-mono">
                {systemDate
                  ? new Date(systemDate).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })
                  : "TBD"}
              </span>
              <span className="ml-2 text-xs italic text-muted-foreground">
                Date set by the system administrator across all leagues.
              </span>
            </div>
          )}
        </div>
      )}

      {(method === "lottery_generator" || method === "manual_entry") && (
        <div className="rounded-md border border-border p-3 space-y-2" data-testid="draft-order-league-block">
          <Label className="text-xs uppercase tracking-wider text-muted-foreground">
            {method === "lottery_generator" ? "Lottery Run Date" : "Pick Order Entry Date (optional)"}
          </Label>
          <div className="flex items-center gap-2">
            <Input
              type="datetime-local"
              value={scheduledAt}
              onChange={(e) => setScheduledAt(e.target.value)}
              disabled={!isCommish}
              className="max-w-xs"
              data-testid="draft-order-league-date-input"
            />
            <span className="text-xs text-muted-foreground">Leave blank for TBD.</span>
          </div>
        </div>
      )}

      {isCommish ? (
        <div className="flex justify-end">
          <Button size="sm" onClick={saveLeagueConfig} disabled={saving || !loaded} data-testid="draft-order-save-config">
            <Save className="h-4 w-4 mr-1" /> Save configuration
          </Button>
        </div>
      ) : (
        <div className="text-xs italic text-muted-foreground">
          Only commissioners may change the draft order configuration.
        </div>
      )}
    </>
  );

  if (embedded) {
    return (
      <div className="space-y-4" data-testid="draft-order-config-card">
        {body}
      </div>
    );
  }

  return (
    <Card className="bg-card border-border" data-testid="draft-order-config-card">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <CalendarDays className="h-4 w-4 text-cyan-300" />
          Draft Order &amp; Schedule
        </CardTitle>
        <CardDescription>
          Choose how this league determines the pick order and when it will be set. The
          Draft Board reads from this configuration to render the status banner + results.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">{body}</CardContent>
    </Card>
  );
}
