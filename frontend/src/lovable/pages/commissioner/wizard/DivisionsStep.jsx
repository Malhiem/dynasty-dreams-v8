// @ts-nocheck
/**
 * Iter 228 — Divisions / League Structure step extracted from SetupWizard.jsx
 * Iter 232N.83 — Inline preset-name editor (click a placeholder chip
 * to rename "Division A" / "Conference 1" without going through the
 * dropdown again).
 */
import { useState } from "react";
import { Plus, X, Wand2, Pencil } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import HelpTooltip from "@/components/ui/help-tooltip";

// Iter 232N.83 — Inline-editable name chip. Click text → input.
// Enter commits, Escape cancels, blur commits (drop-in for Badge chips).
function RenamableChip({ label, onRename, onRemove, testId }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(label);
  if (editing) {
    return (
      <span className="inline-flex items-center gap-1 rounded-md border border-accent/50 bg-accent/10 pl-1.5 pr-1 py-0.5 text-xs">
        <Input
          autoFocus
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") { onRename(draft); setEditing(false); }
            else if (e.key === "Escape") { setDraft(label); setEditing(false); }
          }}
          onBlur={() => {
            if (draft !== label) onRename(draft);
            setEditing(false);
          }}
          className="h-6 text-xs px-1.5 py-0 min-w-[90px] w-auto"
          data-testid={`${testId}-input`}
        />
      </span>
    );
  }
  return (
    <Badge variant="secondary" className="gap-1 pl-2 pr-1" data-testid={testId}>
      <button
        type="button"
        onClick={() => { setDraft(label); setEditing(true); }}
        className="inline-flex items-center gap-1 hover:text-accent group focus:outline-none"
        title="Click to rename"
        data-testid={`${testId}-rename-btn`}
      >
        {label}
        <Pencil className="h-2.5 w-2.5 opacity-0 group-hover:opacity-70 transition-opacity" />
      </button>
      <button
        type="button"
        onClick={onRemove}
        className="hover:text-destructive"
        aria-label={`Remove ${label}`}
      >
        <X className="h-3 w-3" />
      </button>
    </Badge>
  );
}

export default function DivisionsStep({ ctx }) {
  const {
    HELP,
    teams,
    divisionList, conferenceList,
    newDivisionName, setNewDivisionName,
    newConferenceName, setNewConferenceName,
    divisionAssignments, setDivisionAssignments,
    divisionToConference, setDivisionToConference,
    addDivision, removeDivision,
    addConference, removeConference,
    renameDivision, renameConference,
    autoAssignNHL,
    autoAssignStructure,
    divSet,
  } = ctx;

  // Iter 232N.80 — Preset options driven by team count. The "smart"
  // recommendation is bolded so admins can one-click a sensible layout.
  const teamCount = teams.length;
  const smartLabel = (
    teamCount < 6 ? "1 division · no conferences"
      : teamCount < 12 ? "2 divisions · no conferences"
        : teamCount < 24 ? "4 divisions · 2 conferences (NHL-style)"
          : "6 divisions · 3 conferences"
  );
  const presetOptions = [
    { mode: "smart", label: `✨ Smart — ${smartLabel}`, hint: "Recommended based on your team count" },
    { mode: "1x0",   label: "1 division · no conferences" },
    { mode: "2x0",   label: "2 divisions · no conferences" },
    { mode: "3x0",   label: "3 divisions · no conferences" },
    { mode: "4x2",   label: "4 divisions · 2 conferences" },
    { mode: "nhl",   label: "NHL layout (Atlantic / Metro / Central / Pacific)" },
    { mode: "6x2",   label: "6 divisions · 2 conferences" },
    { mode: "6x3",   label: "6 divisions · 3 conferences" },
    { mode: "8x2",   label: "8 divisions · 2 conferences" },
  ];

  return (
    <div className="space-y-3" data-testid="wizard-body-divisions">
      <div className="flex items-center gap-2 flex-wrap">
        <h3 className="text-sm font-semibold text-white flex items-center">
          League Structure
          <HelpTooltip text={HELP.divisions} testId="help-divisions" />
        </h3>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              size="sm"
              variant="outline"
              data-testid="wizard-auto-assign-menu"
              className="gap-1.5"
            >
              <Wand2 className="h-3.5 w-3.5" /> Auto-assign…
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" className="min-w-[320px]">
            <DropdownMenuLabel className="text-[11px]">
              Pick a layout for {teamCount} team{teamCount === 1 ? "" : "s"}
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            {presetOptions.map((opt) => (
              <DropdownMenuItem
                key={opt.mode}
                onSelect={() => (opt.mode === "nhl" ? autoAssignNHL() : autoAssignStructure(opt.mode))}
                data-testid={`wizard-auto-assign-option-${opt.mode}`}
                className="flex flex-col items-start gap-0.5 py-2"
              >
                <span className="text-xs font-medium">{opt.label}</span>
                {opt.hint && (
                  <span className="text-[10px] text-muted-foreground">{opt.hint}</span>
                )}
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
        {/* Kept for backwards-compat with existing selenium tests */}
        <Button
          size="sm"
          variant="ghost"
          className="text-[11px]"
          onClick={autoAssignNHL}
          data-testid="wizard-auto-assign-nhl"
          title="Shortcut: apply the classic Atlantic/Metropolitan/Central/Pacific layout"
        >
          NHL preset
        </Button>
      </div>

      {/* Step A: Create divisions + conferences */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div className="space-y-2 border border-border rounded p-3" data-testid="wizard-division-list">
          <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Divisions ({divisionList.length})</h4>
          <div className="flex gap-2">
            <Input
              placeholder="e.g. Atlantic"
              value={newDivisionName}
              onChange={(e) => setNewDivisionName(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && addDivision()}
              className="h-8 text-xs"
              data-testid="wizard-new-division-input"
            />
            <Button size="sm" variant="outline" onClick={addDivision} data-testid="wizard-add-division-btn">
              <Plus className="h-3.5 w-3.5" />
            </Button>
          </div>
          <div className="flex flex-wrap gap-1.5 min-h-[28px]">
            {divisionList.map((d) => (
              <RenamableChip
                key={d}
                label={d}
                onRename={(next) => renameDivision(d, next)}
                onRemove={() => removeDivision(d)}
                testId={`wizard-division-chip-${d}`}
              />
            ))}
            {divisionList.length === 0 && <span className="text-xs text-muted-foreground italic">No divisions yet</span>}
          </div>
        </div>

        <div className="space-y-2 border border-border rounded p-3" data-testid="wizard-conference-list">
          <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Conferences ({conferenceList.length})</h4>
          <div className="flex gap-2">
            <Input
              placeholder="e.g. Eastern"
              value={newConferenceName}
              onChange={(e) => setNewConferenceName(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && addConference()}
              className="h-8 text-xs"
              data-testid="wizard-new-conference-input"
            />
            <Button size="sm" variant="outline" onClick={addConference} data-testid="wizard-add-conference-btn">
              <Plus className="h-3.5 w-3.5" />
            </Button>
          </div>
          <div className="flex flex-wrap gap-1.5 min-h-[28px]">
            {conferenceList.map((c) => (
              <RenamableChip
                key={c}
                label={c}
                onRename={(next) => renameConference(c, next)}
                onRemove={() => removeConference(c)}
                testId={`wizard-conference-chip-${c}`}
              />
            ))}
            {conferenceList.length === 0 && <span className="text-xs text-muted-foreground italic">No conferences yet</span>}
          </div>
        </div>
      </div>

      {/* Iter 226 — Division → Conference mapping (mandatory when both
            are configured). Each division gets one conference. */}
      {divisionList.length > 0 && conferenceList.length > 0 && (
        <div className="border border-amber-500/40 bg-amber-500/5 rounded p-3 space-y-2" data-testid="wizard-div-conf-mapping">
          <h4 className="text-xs font-semibold uppercase tracking-wide text-amber-200">
            Map each division to a conference
          </h4>
          <p className="text-[11px] text-muted-foreground">
            Required — each division belongs to exactly one conference. Teams in that
            division will inherit the conference automatically.
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {divisionList.map((d) => (
              <div
                key={d}
                className="flex items-center justify-between gap-2 border border-border bg-background/40 rounded px-2 py-1.5"
                data-testid={`wizard-div-conf-row-${d}`}
              >
                <span className="text-sm font-medium truncate">{d}</span>
                <div className="flex gap-1 flex-wrap justify-end">
                  {conferenceList.map((c) => {
                    const selected = divisionToConference[d] === c;
                    return (
                      <button
                        key={c}
                        type="button"
                        onClick={() => setDivisionToConference((prev) => ({ ...prev, [d]: c }))}
                        className={`text-[10px] px-2 py-0.5 rounded-full border transition-colors ${
                          selected
                            ? "bg-accent text-accent-foreground border-accent"
                            : "border-border text-muted-foreground hover:border-accent/60"
                        }`}
                        data-testid={`wizard-div-conf-btn-${d}-${c}`}
                      >
                        {c}
                      </button>
                    );
                  })}
                  {!divisionToConference[d] && (
                    <span className="text-[10px] text-rose-400 self-center ml-1">unassigned</span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Step B: Assign each team via dropdown */}
      <div className="border border-border rounded max-h-[280px] overflow-y-auto">
        <table className="w-full text-sm">
          <thead className="bg-secondary/30 sticky top-0">
            <tr className="text-xs font-medium text-muted-foreground">
              <th className="py-2 pl-3 text-left">Team</th>
              <th className="py-2 text-left">Division</th>
              <th className="py-2 pr-3 text-left">Conference</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border/50">
            {teams.map((t) => (
              <tr key={t.id}>
                <td className="py-1.5 pl-3 font-medium">{t.name}</td>
                <td className="py-1.5 pr-2">
                  <Select
                    value={divisionAssignments[t.id]?.division || ""}
                    onValueChange={(v) => setDivisionAssignments((prev) => ({
                      ...prev,
                      [t.id]: { ...(prev[t.id] || {}), division: v === "__none__" ? "" : v },
                    }))}
                  >
                    <SelectTrigger className="h-7 text-xs" data-testid={`wizard-team-division-${t.id}`}>
                      <SelectValue placeholder="—" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="__none__">—</SelectItem>
                      {divisionList.map((d) => <SelectItem key={d} value={d}>{d}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </td>
                <td className="py-1.5 pr-3">
                  <Select
                    value={divisionAssignments[t.id]?.conference || ""}
                    onValueChange={(v) => setDivisionAssignments((prev) => ({
                      ...prev,
                      [t.id]: { ...(prev[t.id] || {}), conference: v === "__none__" ? "" : v },
                    }))}
                  >
                    <SelectTrigger className="h-7 text-xs" data-testid={`wizard-team-conference-${t.id}`}>
                      <SelectValue placeholder="—" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="__none__">—</SelectItem>
                      {conferenceList.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-muted-foreground">
        {divSet.size < 2
          ? "⚠️ Configure at least 2 divisions to unlock division-aware scheduling in the next step."
          : `✓ ${divSet.size} divisions configured.`}
      </p>
    </div>
  );
}
