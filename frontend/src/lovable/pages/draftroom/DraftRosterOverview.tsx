// @ts-nocheck
import { useState } from "react";
import api from "@/lib/api";
import { toast } from "sonner";
const dollars = (value) => value == null ? "Disabled" : new Intl.NumberFormat("en-US", {style: "currency", currency: "USD", maximumFractionDigits: 0}).format(value);

export default function DraftRosterOverview({ draftId, status, error, refresh }) {
  const [teamId, setTeamId] = useState("");
  const [saving, setSaving] = useState(false);
  const team = status?.teams?.find(t => t.team_id === teamId) || status?.teams?.find(t => t.team_id === status.my_team_id) || status?.teams?.[0];
  const move = async (playerId, destination) => {
    setSaving(true);
    try {
      const { data } = await api.post(`/drafts/${draftId}/roster-move`, {team_id: team.team_id, player_id: playerId, destination});
      if (!data.salary_validation.feasible) toast.warning(data.salary_validation.message);
      await refresh();
    } catch (e) { toast.error(e?.response?.data?.detail?.message || e?.response?.data?.detail || "Roster move failed"); }
    finally { setSaving(false); }
  };
  return <section className="rounded-md border border-border p-4 space-y-3" aria-label="Team salary and roster totals" data-testid="draft-roster-overview">
    <div className="flex flex-wrap items-center justify-between gap-2">
      <h3 className="font-semibold">Team salary and roster totals</h3>
      <span>Salary adherence: {status?.mode || "Loading"}</span>
      <label>View team <select aria-label="View team totals" value={team?.team_id || ""} onChange={e => setTeamId(e.target.value)} className="bg-secondary rounded p-1">
        {status?.teams?.map(t => <option key={t.team_id} value={t.team_id}>{t.name}{t.team_id === status.my_team_id ? " (Your team)" : ""}</option>)}
      </select></label>
    </div>
    {error && <p role="alert">Totals may be stale. Reconnecting…</p>}
    {!team ? <p>Loading team totals…</p> : <>
      <div className="flex flex-wrap gap-4" data-testid="draft-team-payroll">
        <span>Payroll {dollars(team.salary_used)}</span><span>Cap {dollars(team.salary_cap)}</span>
        <span>{team.remaining < 0 ? "Cap excess" : "Cap space"} {dollars(team.remaining == null ? null : Math.abs(team.remaining))}</span>
        <span>Floor {dollars(team.salary_floor)}</span><span>Needed for floor {dollars(team.floor_shortfall)}</span>
        <span>Required vacancies {team.remaining_slots}</span>
      </div>
      <div className="flex flex-wrap gap-3" data-testid="draft-team-positions">
        {Object.entries(team.positions).filter(([,v]) => v.capacity > 0).map(([slot,v]) => <span key={slot}>{({MIN:"Minors", BN:"Bench", ACT:"Active"})[slot] || slot} {v.filled}/{v.capacity}</span>)}
      </div>
      {team.over_cap && <p role="status" className="text-amber-400">Over cap. {status.mode === "informal" ? "Make roster adjustments after the draft." : "Adjust the roster before the next selection."}</p>}
      {!!team.floor_shortfall && <p>Additional salary needed to reach the floor: {dollars(team.floor_shortfall)}</p>}
      <details><summary>Roster assignments and salary charges</summary>
        <p>Retained salary {dollars(team.retained_total)} · Buyout charges {dollars(team.buyout_total)}</p>
        {team.players.map(p => <div key={p.id} className="flex gap-3 items-center py-1">
          <span>{p.name} ({p.position}) — {dollars(team.charges[p.id])}</span>
          {team.can_edit ? <label className="ml-auto">Destination for {p.name} <select aria-label={`Destination for ${p.name}`} disabled={saving} value={team.lineup[p.id]?.slot || ""} onChange={e => move(p.id,e.target.value)} className="bg-secondary rounded p-1">
            <option value="" disabled>Unassigned</option>{p.destinations.map(s => <option key={s} value={s}>{s}</option>)}
          </select></label> : <span>{team.lineup[p.id]?.slot || "Unassigned"}</span>}
        </div>)}
      </details>
    </>}
  </section>;
}
