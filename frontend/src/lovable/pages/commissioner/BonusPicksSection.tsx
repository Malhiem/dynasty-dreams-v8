/**
 * Iter 232i — `<BonusPicksSection />`
 *
 * Commissioner-only UI for granting compensation / expansion picks
 * inside the Edit Draft dialog. Everything the section does is a
 * direct call to the `/api/drafts/{draft_id}/bonus-picks` router —
 * the parent form (`EditDraftForm`) doesn't own this state so
 * commissioners can add / remove picks mid-draft without triggering
 * the parent's "save changes" flow.
 *
 * Layout (single vertical column so it renders cleanly on mobile
 * inside the max-w-lg modal):
 *   1. List of existing bonus picks with a delete button per row.
 *   2. "Add bonus pick" form: kind (compensation / expansion),
 *      team dropdown, position mode radio (end-of-round vs overall),
 *      the corresponding number input, tradeable checkbox,
 *      optional note.
 *
 * Guardrail hints (server enforces authoritative rules; the UI just
 * makes them visible):
 *   • Position number field is bounded by the draft's `total_rounds`
 *     (end-of-round mode) or `total_picks + existing_bonus + 1`
 *     (overall mode).
 *   • Delete button is hidden for picks whose `overall` is already
 *     `<= draft.current_pick` — the backend would 409 anyway but the
 *     row visually clarifies "already used".
 */
import { useEffect, useState } from "react";
import { Plus, X, Gift } from "lucide-react";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import api from "@/lib/api";
import { toast } from "sonner";

interface BonusPick {
  id: string;
  team_id: string;
  team_name: string;
  team_abbr: string;
  bonus_kind: "compensation" | "expansion";
  position_mode: "end_of_round" | "overall";
  after_round: number | null;
  overall: number;
  tradeable: boolean;
  note: string | null;
}

interface Team {
  _id: string;
  name: string;
}

interface Props {
  draftId: string;
  totalRounds: number;
  teamCount: number;
  currentPick: number;
  draftStatus: string;
  teams: Team[];
}

export default function BonusPicksSection({
  draftId, totalRounds, teamCount, currentPick, draftStatus, teams,
}: Props) {
  const [picks, setPicks] = useState<BonusPick[]>([]);
  const [loading, setLoading] = useState(false);
  const [adding, setAdding] = useState(false);
  const [showForm, setShowForm] = useState(false);

  // Form state.
  const [teamId, setTeamId] = useState<string>("");
  const [kind, setKind] = useState<"compensation" | "expansion">("compensation");
  const [posMode, setPosMode] = useState<"end_of_round" | "overall">("end_of_round");
  const [afterRound, setAfterRound] = useState<number>(1);
  const [overallPos, setOverallPos] = useState<number>(teamCount + 1);
  const [tradeable, setTradeable] = useState<boolean>(true);
  const [note, setNote] = useState<string>("");

  useEffect(() => {
    if (!draftId) return;
    let cancelled = false;
    setLoading(true);
    api.get(`/drafts/${draftId}/bonus-picks`)
      .then(({ data }) => { if (!cancelled) setPicks(data.bonus_picks || []); })
      .catch(() => { if (!cancelled) setPicks([]); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [draftId]);

  const resetForm = () => {
    setTeamId("");
    setKind("compensation");
    setPosMode("end_of_round");
    setAfterRound(1);
    setOverallPos(teamCount + 1);
    setTradeable(true);
    setNote("");
    setShowForm(false);
  };

  const handleAdd = async () => {
    if (!teamId) {
      toast.error("Pick a team");
      return;
    }
    if (posMode === "end_of_round" && (afterRound < 1 || afterRound > totalRounds)) {
      toast.error(`After Round must be between 1 and ${totalRounds}`);
      return;
    }
    if (posMode === "overall" && overallPos < 1) {
      toast.error("Overall position must be >= 1");
      return;
    }
    setAdding(true);
    try {
      const payload: Record<string, unknown> = {
        team_id: teamId,
        bonus_kind: kind,
        position_mode: posMode,
        tradeable,
        note: note.trim() || null,
      };
      if (posMode === "end_of_round") payload.after_round = afterRound;
      else payload.overall_position = overallPos;
      const { data } = await api.post(`/drafts/${draftId}/bonus-picks`, payload);
      setPicks(data.bonus_picks || []);
      resetForm();
      toast.success(`${kind === "compensation" ? "Compensation" : "Expansion"} pick added`);
    } catch (e: any) {
      const msg = e?.response?.data?.detail || "Failed to add bonus pick";
      toast.error(typeof msg === "string" ? msg : "Failed to add bonus pick");
    } finally {
      setAdding(false);
    }
  };

  const handleDelete = async (id: string) => {
    try {
      const { data } = await api.delete(`/drafts/${draftId}/bonus-picks/${id}`);
      setPicks(data.bonus_picks || []);
      toast.success("Bonus pick removed");
    } catch (e: any) {
      const msg = e?.response?.data?.detail || "Failed to remove bonus pick";
      toast.error(typeof msg === "string" ? msg : "Failed to remove bonus pick");
    }
  };

  return (
    <div
      className="space-y-3 border-t border-border pt-4"
      data-testid="bonus-picks-section"
    >
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="flex items-center gap-2">
            <Gift className="h-4 w-4 text-primary" />
            <Label className="text-base">Bonus Picks</Label>
          </div>
          <p className="text-xs text-muted-foreground mt-1">
            Grant compensation or expansion picks. Insert at end of a specific round
            or at any overall pick position. Works pre- and mid-draft (only positions
            that haven&apos;t been reached yet).
          </p>
        </div>
        {!showForm && (
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={() => setShowForm(true)}
            data-testid="bonus-pick-add-btn"
          >
            <Plus className="h-3.5 w-3.5 mr-1" />
            Add
          </Button>
        )}
      </div>

      {/* ── Existing picks ─────────────────────────────────────── */}
      {loading && (
        <p className="text-xs text-muted-foreground">Loading…</p>
      )}
      {!loading && picks.length === 0 && !showForm && (
        <p className="text-xs text-muted-foreground italic" data-testid="bonus-picks-empty">
          No bonus picks yet.
        </p>
      )}
      {picks.length > 0 && (
        <ul className="space-y-1.5" data-testid="bonus-picks-list">
          {picks.map((p) => {
            const alreadyUsed = draftStatus === "active" && p.overall <= currentPick;
            return (
              <li
                key={p.id}
                className="flex items-center justify-between gap-2 rounded-md border border-border/60 bg-secondary/30 px-2.5 py-1.5"
                data-testid={`bonus-pick-row-${p.id}`}
              >
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-xs font-mono bg-primary/10 text-primary px-1.5 py-0.5 rounded">
                      #{p.overall}
                    </span>
                    <span
                      className={
                        p.bonus_kind === "compensation"
                          ? "text-[10px] uppercase tracking-wider bg-amber-500/15 text-amber-500 px-1.5 py-0.5 rounded"
                          : "text-[10px] uppercase tracking-wider bg-cyan-500/15 text-cyan-500 px-1.5 py-0.5 rounded"
                      }
                    >
                      {p.bonus_kind}
                    </span>
                    <span className="text-sm font-medium truncate">{p.team_name}</span>
                    {p.tradeable && (
                      <span className="text-[9px] uppercase tracking-wider text-muted-foreground">
                        tradeable
                      </span>
                    )}
                    {alreadyUsed && (
                      <span className="text-[9px] uppercase tracking-wider text-muted-foreground">
                        used
                      </span>
                    )}
                  </div>
                  {p.note && (
                    <p className="text-[11px] text-muted-foreground truncate mt-0.5">
                      {p.note}
                    </p>
                  )}
                </div>
                {!alreadyUsed && (
                  <button
                    type="button"
                    onClick={() => handleDelete(p.id)}
                    className="text-muted-foreground hover:text-destructive shrink-0"
                    data-testid={`bonus-pick-delete-${p.id}`}
                    aria-label="Remove bonus pick"
                  >
                    <X className="h-4 w-4" />
                  </button>
                )}
              </li>
            );
          })}
        </ul>
      )}

      {/* ── Add form ───────────────────────────────────────────── */}
      {showForm && (
        <div
          className="space-y-2 border border-border/80 rounded-md p-3 bg-secondary/20"
          data-testid="bonus-pick-form"
        >
          <div className="grid gap-2 sm:grid-cols-2">
            <div className="space-y-1">
              <Label className="text-xs">Kind</Label>
              <Select value={kind} onValueChange={(v) => setKind(v as any)}>
                <SelectTrigger data-testid="bonus-pick-kind-select">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="compensation" data-testid="bonus-pick-kind-compensation">Compensation</SelectItem>
                  <SelectItem value="expansion" data-testid="bonus-pick-kind-expansion">Expansion</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Team</Label>
              <Select value={teamId} onValueChange={setTeamId}>
                <SelectTrigger data-testid="bonus-pick-team-select">
                  <SelectValue placeholder="Choose team…" />
                </SelectTrigger>
                <SelectContent>
                  {teams.map((t) => (
                    <SelectItem key={t._id} value={t._id}>{t.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="space-y-1">
            <Label className="text-xs">Position</Label>
            <div className="flex items-center gap-3 text-xs">
              <label className="flex items-center gap-1.5 cursor-pointer">
                <input
                  type="radio"
                  name="pos-mode"
                  checked={posMode === "end_of_round"}
                  onChange={() => setPosMode("end_of_round")}
                  data-testid="bonus-pick-mode-end-of-round"
                />
                End of round
              </label>
              <label className="flex items-center gap-1.5 cursor-pointer">
                <input
                  type="radio"
                  name="pos-mode"
                  checked={posMode === "overall"}
                  onChange={() => setPosMode("overall")}
                  data-testid="bonus-pick-mode-overall"
                />
                Overall pick #
              </label>
            </div>
            {posMode === "end_of_round" ? (
              <Input
                type="number" min={1} max={totalRounds}
                value={afterRound}
                onChange={(e) => setAfterRound(parseInt(e.target.value || "1", 10))}
                placeholder="Round number"
                data-testid="bonus-pick-after-round-input"
              />
            ) : (
              <Input
                type="number" min={1}
                value={overallPos}
                onChange={(e) => setOverallPos(parseInt(e.target.value || "1", 10))}
                placeholder="Overall pick number"
                data-testid="bonus-pick-overall-input"
              />
            )}
          </div>

          <div className="flex items-center gap-2 pt-1">
            <Checkbox
              id="bonus-tradeable"
              checked={tradeable}
              onCheckedChange={(v) => setTradeable(!!v)}
              data-testid="bonus-pick-tradeable-checkbox"
            />
            <Label htmlFor="bonus-tradeable" className="text-xs cursor-pointer">
              Tradeable
            </Label>
          </div>

          <div className="space-y-1">
            <Label className="text-xs">Note (optional)</Label>
            <Input
              value={note}
              onChange={(e) => setNote(e.target.value)}
              maxLength={200}
              placeholder="e.g. Contract termination compensation"
              data-testid="bonus-pick-note-input"
            />
          </div>

          <div className="flex items-center justify-end gap-2 pt-2">
            <Button
              type="button"
              size="sm"
              variant="ghost"
              onClick={resetForm}
              disabled={adding}
              data-testid="bonus-pick-cancel-btn"
            >
              Cancel
            </Button>
            <Button
              type="button"
              size="sm"
              onClick={handleAdd}
              disabled={adding || !teamId}
              data-testid="bonus-pick-submit-btn"
            >
              {adding ? "Adding…" : "Add pick"}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
