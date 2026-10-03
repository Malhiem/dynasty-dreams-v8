// @ts-nocheck
/* CommishActions — extracted from AdminDashboard.tsx during Iter 224 refactor. */
import { Filter, RotateCcw, User } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

const COMMISH_EVENT_TYPES = [
  "playoff_winner_marked",
  "playoff_prize_distributed",
  "ops_force_lineup_set",
  "ops_force_roster_move",
  "ops_force_trade_approve",
  "ops_force_trade_reject",
  "ops_force_pause_draft",
  "ops_force_resume_draft",
  "ops_violation_notified",
  "ops_violation_force_fixed",
  "lineup_override",
  "trade_override",
  "waiver_override",
  "team_owner_changed",
  "team_renamed",
  "draft_pick_traded",
  "schedule_regenerated",
  "playoff_format_changed",
  "setup_wizard_completed",
];

export function CommishActions({ actions, loading, filters, setFilters, revert, reverting }) {
  return (
    <section className="space-y-3" data-testid="commish-actions-section">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
          Commissioner Action Log <span className="text-foreground/70">· cross-league</span>
        </h2>
        <div className="flex items-center gap-2 flex-wrap">
          <Filter className="h-3.5 w-3.5 text-muted-foreground" />
          <Select
            value={filters.event_type || "_all"}
            onValueChange={(v) => setFilters((f) => ({ ...f, event_type: v === "_all" ? "" : v }))}
          >
            <SelectTrigger className="h-8 w-[230px] text-xs" data-testid="commish-filter-event-type">
              <SelectValue placeholder="All event types" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="_all">All event types</SelectItem>
              {COMMISH_EVENT_TYPES.map((t) => (
                <SelectItem key={t} value={t}>{t}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Input
            placeholder="League id"
            value={filters.league_id}
            onChange={(e) => setFilters((f) => ({ ...f, league_id: e.target.value }))}
            className="h-8 w-[180px] text-xs"
            data-testid="commish-filter-league-id"
          />
          <Input
            placeholder="User id"
            value={filters.user_id}
            onChange={(e) => setFilters((f) => ({ ...f, user_id: e.target.value }))}
            className="h-8 w-[180px] text-xs"
            data-testid="commish-filter-user-id"
          />
        </div>
      </div>

      <div className="rounded-lg border border-border overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-secondary/50 text-xs uppercase tracking-wider text-muted-foreground">
            <tr>
              <th className="text-left px-3 py-2">When</th>
              <th className="text-left px-3 py-2">Event</th>
              <th className="text-left px-3 py-2">League</th>
              <th className="text-left px-3 py-2">Actor</th>
              <th className="text-left px-3 py-2">Detail</th>
              <th className="text-right px-3 py-2">Action</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={6} className="text-center text-muted-foreground py-6">Loading…</td></tr>
            ) : actions.length === 0 ? (
              <tr><td colSpan={6} className="text-center text-muted-foreground py-6">No actions logged.</td></tr>
            ) : actions.map((a) => (
              <tr key={a.id} className="border-t border-border hover:bg-secondary/20" data-testid={`commish-action-row-${a.id}`}>
                <td className="px-3 py-2 text-xs text-muted-foreground whitespace-nowrap">{(a.created_at || "").slice(0, 19).replace("T", " ")}</td>
                <td className="px-3 py-2 text-xs">
                  <span className="inline-block rounded-md px-1.5 py-0.5 bg-cyan-500/15 text-cyan-300 border border-cyan-500/30 font-mono">
                    {a.event_type}
                  </span>
                </td>
                <td className="px-3 py-2 text-xs">{a.league_name || (a.league_id ? a.league_id.slice(0, 8) : "—")}</td>
                <td className="px-3 py-2 text-xs">{a.user?.email || a.user_id?.slice(0, 8) || "—"}</td>
                <td className="px-3 py-2 text-xs max-w-[280px] truncate" title={a.message}>{a.message || "—"}</td>
                <td className="px-3 py-2 text-right">
                  {a.reverted ? (
                    <span className="text-[10px] uppercase tracking-wider font-semibold text-rose-300" data-testid={`commish-reverted-pill-${a.id}`}>
                      Reverted
                    </span>
                  ) : (
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => revert(a.id)}
                      disabled={reverting === a.id}
                      className="text-xs h-7"
                      data-testid={`commish-revert-btn-${a.id}`}
                    >
                      <RotateCcw className="h-3 w-3 mr-1" />
                      Revert
                    </Button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

