/**
 * Iter 228s — Edit Draft Dialog extracted from DraftTab.tsx.
 *
 * Goal: shrink DraftTab.tsx (1575 lines + `@ts-nocheck`) by lifting the
 * Edit Dialog into its own properly-typed file. With TypeScript fully
 * enabled here, regressions like iter 228r's "useEffect is not defined"
 * crash get caught at compile time instead of runtime.
 *
 * The parent (DraftTab) still owns the open/close + save lifecycle so
 * we don't churn the existing reload-scheduled-drafts wiring. This
 * dialog just renders the form, surfaces the "What if?" preview, and
 * fires onSave / onClose callbacks.
 */
import { Plus, X } from "lucide-react";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
// Iter 232i — Commissioner bonus draft picks section.
import BonusPicksSection from "@/lovable/pages/commissioner/BonusPicksSection";

export interface RoundTimeRange {
  from: number;
  to: number;
  seconds: number;
}

export interface EditDraftForm {
  name: string;
  scheduledDate: string;
  scheduledTime: string;
  totalRounds: number;
  timePerPick: number;
  draftType: string;
  snakeDraft: boolean;
  playerCriteria: string;
  missedPickAction: string;
  deferUserOptions: string[];
  roundTimeRanges: RoundTimeRange[];
  excludePreviouslyDrafted: boolean;
  minorsEligibilityRequired: boolean;
}

export interface EditDraftPreview {
  team_count: number;
  original_rounds: number;
  new_rounds: number;
  picks_added: number;
  picks_added_per_team: number;
  picks_removed: number;
  picks_removed_per_team: number;
  traded_picks_preserved: number;
}

export interface PlayerCriteriaOption {
  value: string;
  label: string;
}

export interface EditDraftDialogProps {
  open: boolean;
  form: EditDraftForm | null;
  onFormChange: (next: EditDraftForm) => void;
  preview: EditDraftPreview | null;
  previewLoading: boolean;
  saving: boolean;
  onSave: () => void;
  onClose: () => void;
  playerCriteriaOptions: PlayerCriteriaOption[];
  activeLeagueName?: string;
  // Iter 232i — Bonus picks context. Optional so the dialog still
  // works from any legacy call sites; when supplied, the bonus-picks
  // section renders at the bottom of the form.
  draftId?: string;
  currentPick?: number;
  draftStatus?: string;
  leagueTeams?: Array<{ _id: string; name: string }>;
}

const TIME_PRESETS: Array<{ value: string; label: string }> = [
  { value: "60", label: "1 minute" },
  { value: "120", label: "2 minutes" },
  { value: "300", label: "5 minutes" },
  { value: "600", label: "10 minutes" },
  { value: "900", label: "15 minutes" },
  { value: "1800", label: "30 minutes" },
  { value: "2700", label: "45 minutes" },
  { value: "3600", label: "1 hour" },
  { value: "5400", label: "1.5 hours" },
  { value: "7200", label: "2 hours" },
  { value: "10800", label: "3 hours" },
  { value: "14400", label: "4 hours" },
  { value: "21600", label: "6 hours" },
  { value: "43200", label: "12 hours" },
  { value: "86400", label: "24 hours" },
];

export default function EditDraftDialog(props: EditDraftDialogProps) {
  const {
    open, form, onFormChange, preview, previewLoading,
    saving, onSave, onClose, playerCriteriaOptions, activeLeagueName,
    draftId, currentPick, draftStatus, leagueTeams,
  } = props;

  if (!open || !form) return null;
  const update = (patch: Partial<EditDraftForm>) =>
    onFormChange({ ...form, ...patch });

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
      data-testid="edit-draft-dialog"
    >
      <div className="bg-card border border-border rounded-lg shadow-xl w-full max-w-lg max-h-[90vh] overflow-y-auto m-4">
        <div className="p-4 border-b border-border flex items-center justify-between">
          <h3 className="font-semibold">Edit Draft</h3>
          <button
            onClick={onClose}
            className="text-muted-foreground hover:text-foreground"
            data-testid="edit-draft-close-btn"
            aria-label="Close edit dialog"
          ><X className="h-4 w-4" /></button>
        </div>
        <div className="p-4 space-y-4">
          <div className="space-y-2">
            <Label>Draft Name</Label>
            <Input
              value={form.name}
              onChange={(e) => update({ name: e.target.value })}
              data-testid="edit-draft-name-input"
              placeholder="e.g. TFHL Mid-Season Supplemental"
            />
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-2">
              <Label>Scheduled Date</Label>
              <Input
                type="date"
                value={form.scheduledDate}
                onChange={(e) => update({ scheduledDate: e.target.value })}
                data-testid="edit-draft-date-input"
              />
            </div>
            <div className="space-y-2">
              <Label>Start Time</Label>
              <Input
                type="time"
                value={form.scheduledTime}
                onChange={(e) => update({ scheduledTime: e.target.value })}
                data-testid="edit-draft-time-input"
              />
            </div>
            <div className="space-y-2 col-span-2">
              <Label>Rounds</Label>
              <Input
                type="number" min={1} max={100}
                value={form.totalRounds}
                onChange={(e) => update({ totalRounds: parseInt(e.target.value || "1", 10) })}
                data-testid="edit-draft-rounds-input"
              />
              {preview && (preview.new_rounds !== preview.original_rounds) && (
                <div
                  className={`rounded-md border px-3 py-2 text-xs ${
                    preview.picks_added > 0
                      ? "bg-emerald-500/10 border-emerald-500/40 text-emerald-200"
                      : "bg-rose-500/10 border-rose-500/40 text-rose-200"
                  }`}
                  data-testid="edit-draft-rounds-preview"
                >
                  {preview.picks_added > 0 ? (
                    <>
                      <span className="font-semibold">
                        This will add {preview.picks_added_per_team} pick
                        {preview.picks_added_per_team === 1 ? "" : "s"} per team
                        {" "}({preview.picks_added} total)
                      </span>
                      {" "}across {preview.team_count} team{preview.team_count === 1 ? "" : "s"}.
                      New rounds will be appended to every roster on Save.
                    </>
                  ) : (
                    <>
                      <span className="font-semibold">
                        This will remove {preview.picks_removed_per_team} pick
                        {preview.picks_removed_per_team === 1 ? "" : "s"} per team
                        {" "}({preview.picks_removed} total)
                      </span>
                      {" "}across {preview.team_count} team{preview.team_count === 1 ? "" : "s"}.
                      {preview.traded_picks_preserved > 0 && (
                        <>
                          {" "}
                          <span className="text-amber-300 font-semibold">
                            {preview.traded_picks_preserved} traded pick
                            {preview.traded_picks_preserved === 1 ? "" : "s"} will be preserved.
                          </span>
                        </>
                      )}
                    </>
                  )}
                </div>
              )}
              {previewLoading && (
                <p className="text-[10px] text-muted-foreground italic">Computing impact…</p>
              )}
            </div>
            <div className="space-y-2">
              <Label>Default Time/Pick</Label>
              <Select
                value={String(form.timePerPick)}
                onValueChange={(v) => update({ timePerPick: parseInt(v, 10) })}
              >
                <SelectTrigger
                  className="bg-secondary border-border"
                  data-testid="edit-draft-time-per-pick-select"
                ><SelectValue /></SelectTrigger>
                <SelectContent>
                  {TIME_PRESETS.map((p) => (
                    <SelectItem key={p.value} value={p.value}>{p.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>Draft Type</Label>
              <Select
                value={form.draftType}
                onValueChange={(v) => update({ draftType: v })}
              >
                <SelectTrigger
                  className="bg-secondary border-border"
                  data-testid="edit-draft-type-select"
                ><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="entry">Entry / Inaugural</SelectItem>
                  <SelectItem value="keeper">Keeper</SelectItem>
                  <SelectItem value="expansion">Expansion</SelectItem>
                  <SelectItem value="snake">Snake (one-shot)</SelectItem>
                  <SelectItem value="auction">Auction</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>Format</Label>
              <Select
                value={form.snakeDraft ? "snake" : "linear"}
                onValueChange={(v) => update({ snakeDraft: v === "snake" })}
              >
                <SelectTrigger
                  className="bg-secondary border-border"
                  data-testid="edit-draft-format-select"
                ><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="snake">Snake Draft</SelectItem>
                  <SelectItem value="linear">Linear Draft</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>Player Criteria</Label>
              <Select
                value={form.playerCriteria}
                onValueChange={(v) => update({ playerCriteria: v })}
              >
                <SelectTrigger
                  className="bg-secondary border-border"
                  data-testid="edit-draft-criteria-select"
                ><SelectValue /></SelectTrigger>
                <SelectContent>
                  {playerCriteriaOptions.map((o) => (
                    <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>Missed Pick Action</Label>
              <Select
                value={form.missedPickAction}
                onValueChange={(v) => update({ missedPickAction: v })}
              >
                <SelectTrigger
                  className="bg-secondary border-border"
                  data-testid="edit-draft-missed-pick-select"
                ><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="auto-select">Auto-select Best Available</SelectItem>
                  <SelectItem value="skip">Skip Pick</SelectItem>
                  <SelectItem value="defer-to-user">Defer to User</SelectItem>
                  <SelectItem value="pause">Pause Draft</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          {form.missedPickAction === "defer-to-user" && (
            <div className="space-y-2 border-l-2 border-amber-500/40 pl-3">
              <Label className="text-xs">Defer-to-User Options</Label>
              <p className="text-[11px] text-muted-foreground">
                Choose which fallback actions the manager can select when their pick window expires.
              </p>
              {["auto-best", "auto-queue", "pick-anytime"].map((opt) => (
                <label key={opt} className="flex items-center gap-2 text-sm cursor-pointer">
                  <Checkbox
                    checked={form.deferUserOptions.includes(opt)}
                    onCheckedChange={(v) => {
                      const next = v
                        ? Array.from(new Set([...form.deferUserOptions, opt]))
                        : form.deferUserOptions.filter((o) => o !== opt);
                      update({ deferUserOptions: next });
                    }}
                    data-testid={`edit-draft-defer-option-${opt}`}
                  />
                  <span className="text-xs">{
                    opt === "auto-best" ? "Auto-select best available player" :
                    opt === "auto-queue" ? "Auto-pick from manager's queue" :
                    "Pick anytime (skip until manually picked)"
                  }</span>
                </label>
              ))}
            </div>
          )}
          <div className="space-y-2" data-testid="edit-draft-round-ranges">
            <div className="flex items-center justify-between">
              <Label className="text-xs">Round Time Ranges</Label>
              <Button
                type="button"
                size="sm" variant="outline"
                onClick={() => update({
                  roundTimeRanges: [
                    ...form.roundTimeRanges,
                    { from: 1, to: Math.min(form.totalRounds, 5), seconds: 3600 },
                  ],
                })}
                data-testid="edit-draft-round-range-add"
              ><Plus className="h-3 w-3 mr-1" />Add range</Button>
            </div>
            <p className="text-[11px] text-muted-foreground">
              Optional. Override the default for specific round spans (e.g. R1–R5 = 1 hour, R6–R30 = 5 min). Empty list inherits the default.
            </p>
            {form.roundTimeRanges.length === 0 && (
              <p className="text-[11px] text-muted-foreground italic px-2 py-1">
                No range overrides — every round uses the default time above.
              </p>
            )}
            {form.roundTimeRanges.map((r, idx) => (
              <div
                key={idx}
                className="grid grid-cols-12 gap-2 items-end"
                data-testid={`edit-draft-round-range-row-${idx}`}
              >
                <div className="col-span-3 space-y-1">
                  <Label className="text-[10px] text-muted-foreground">From Rd</Label>
                  <Input
                    type="number" min={1} max={form.totalRounds}
                    value={r.from}
                    onChange={(e) => {
                      const ranges = [...form.roundTimeRanges];
                      ranges[idx] = { ...r, from: parseInt(e.target.value || "1", 10) };
                      update({ roundTimeRanges: ranges });
                    }}
                    data-testid={`edit-draft-round-range-from-${idx}`}
                    className="h-8 text-sm"
                  />
                </div>
                <div className="col-span-3 space-y-1">
                  <Label className="text-[10px] text-muted-foreground">To Rd</Label>
                  <Input
                    type="number" min={r.from} max={form.totalRounds}
                    value={r.to}
                    onChange={(e) => {
                      const ranges = [...form.roundTimeRanges];
                      ranges[idx] = { ...r, to: parseInt(e.target.value || "1", 10) };
                      update({ roundTimeRanges: ranges });
                    }}
                    data-testid={`edit-draft-round-range-to-${idx}`}
                    className="h-8 text-sm"
                  />
                </div>
                <div className="col-span-5 space-y-1">
                  <Label className="text-[10px] text-muted-foreground">Time</Label>
                  <Select
                    value={String(r.seconds)}
                    onValueChange={(v) => {
                      const ranges = [...form.roundTimeRanges];
                      ranges[idx] = { ...r, seconds: parseInt(v, 10) };
                      update({ roundTimeRanges: ranges });
                    }}
                  >
                    <SelectTrigger
                      className="h-8 text-sm bg-secondary border-border"
                      data-testid={`edit-draft-round-range-time-${idx}`}
                    ><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {TIME_PRESETS.map((p) => (
                        <SelectItem key={p.value} value={p.value}>{p.label}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="col-span-1 flex justify-end">
                  <Button
                    type="button" size="icon" variant="ghost"
                    className="h-8 w-8 text-muted-foreground hover:text-rose-400"
                    onClick={() => {
                      const ranges = form.roundTimeRanges.filter((_, i) => i !== idx);
                      update({ roundTimeRanges: ranges });
                    }}
                    data-testid={`edit-draft-round-range-remove-${idx}`}
                    aria-label="Remove this range"
                  ><X className="h-3.5 w-3.5" /></Button>
                </div>
              </div>
            ))}
          </div>
          <div className="space-y-2">
            <Label>Eligibility Filters</Label>
            <label className="flex items-start gap-2 cursor-pointer text-sm rounded-md border border-border/60 p-2 hover:bg-muted/20">
              <Checkbox
                checked={form.excludePreviouslyDrafted}
                onCheckedChange={(v) => update({ excludePreviouslyDrafted: !!v })}
                data-testid="edit-draft-exclude-previously-drafted"
              />
              <span>Exclude players previously drafted in {activeLeagueName || "this league"}</span>
            </label>
            <label className="flex items-start gap-2 cursor-pointer text-sm rounded-md border border-border/60 p-2 hover:bg-muted/20">
              <Checkbox
                checked={form.minorsEligibilityRequired}
                onCheckedChange={(v) => update({ minorsEligibilityRequired: !!v })}
                data-testid="edit-draft-minors-eligibility-required"
              />
              <span>Meets minors eligibility</span>
            </label>
          </div>
          {/* Iter 232i — Commissioner bonus picks (compensation / expansion).
              Only renders when the parent supplies the required draft
              context, so legacy call sites remain unaffected. */}
          {draftId && leagueTeams && Array.isArray(leagueTeams) && (
            <BonusPicksSection
              draftId={draftId}
              totalRounds={form.totalRounds || 1}
              teamCount={leagueTeams.length}
              currentPick={currentPick || 1}
              draftStatus={draftStatus || "scheduled"}
              teams={leagueTeams}
            />
          )}
        </div>
        <div className="p-4 border-t border-border flex items-center justify-end gap-2">
          <Button
            variant="outline" onClick={onClose}
            data-testid="edit-draft-cancel-btn"
          >Cancel</Button>
          <Button
            onClick={onSave}
            disabled={saving}
            data-testid="edit-draft-save-btn"
          >{saving ? "Saving…" : "Save Changes"}</Button>
        </div>
      </div>
    </div>
  );
}
