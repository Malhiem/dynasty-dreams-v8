// @ts-nocheck
/**
 * Iter 155 — Player Pool tab extracted from CommissionerSettings.tsx.
 *
 * Two cards:
 *   • Player Inclusion (Include-Entire-NHL switch, per-team checklist, conference toggles)
 *   • Pool Settings (lock pool, include minors, include unsigned, duplicate-players select)
 * All state is owned by the parent so cross-tab interactions stay intact.
 */
import { allTeams, conferenceTeams, divisions } from "./playerPoolTeams";
import { useEffect, useState } from "react";
import { useActiveLeague } from "@/hooks/use-active-league";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Checkbox } from "@/components/ui/checkbox";
import { Separator } from "@/components/ui/separator";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";

interface PlayerPoolTabProps {
  nhlTeams: string[];
  selectedTeams: string[];
  toggleTeam: (team: string) => void;
  duplicatePlayers: string;
  setDuplicatePlayers: (v: string) => void;
}

export default function PlayerPoolTab({ nhlTeams }: PlayerPoolTabProps) {
  const { leagueId } = useActiveLeague();
  const defaults = { selection_mode: "all", include_entire_nhl: true, teams: [], eastern: true, western: true,
    locked: false, include_minors: true, include_unsigned: false, duplicate_players: "not-used" };
  const [pool, setPool] = useState(defaults);
  const [loadedId, setLoadedId] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let cancelled = false; setLoadedId(""); setError("");
    api.get(`/leagues/${leagueId}`).then(({data}) => {
      if (!cancelled) { const saved=data.player_pool_config || {};setPool({...defaults, ...saved,selection_mode:saved.selection_mode || (saved.include_entire_nhl===false ? "custom" : "all")}); setLoadedId(leagueId); }
    }).catch(e => { if (!cancelled) setError(e?.response?.data?.detail || "Failed to load player pool"); });
    return () => { cancelled = true; };
  }, [leagueId, attempt]);
  const set = (key, value) => setPool(prev => ({...prev, [key]:value}));
  const selectedTeams = pool.selection_mode === "custom" ? pool.teams : pool.selection_mode === "conference" ? [...(pool.eastern ? conferenceTeams("east") : []), ...(pool.western ? conferenceTeams("west") : [])] : allTeams;
  const chooseTeams = teams => setPool(prev => ({...prev, selection_mode: teams.length===32 ? "all" : "custom", include_entire_nhl: teams.length===32, teams}));
  const toggleTeam = team => chooseTeams(selectedTeams.includes(team) ? selectedTeams.filter(x => x !== team) : [...selectedTeams,team]);
  const chooseConference = (side,checked) => { const clubs=conferenceTeams(side);chooseTeams(checked ? [...new Set([...selectedTeams,...clubs])] : selectedTeams.filter(x=>!clubs.includes(x))); };
  const duplicatePlayers = pool.duplicate_players;
  const setDuplicatePlayers = value => set("duplicate_players",value);
  const save = async () => {
    if (saving || loadedId !== leagueId) return;
    setSaving(true);setError("");
    try { await api.put(`/leagues/${leagueId}`, {player_pool_config:pool}); }
    catch(e) {setError(e?.response?.data?.detail || "Failed to save player pool");}
    finally {setSaving(false);}
  };
  if (loadedId !== leagueId) return error ? <div role="alert">{error} <Button onClick={() => setAttempt(n => n+1)}>Retry loading player pool</Button></div> : <p role="status">Loading player pool…</p>;
  return (
    <div className="space-y-6" data-testid="commissioner-player-pool-tab">
      {error && <p role="alert">{error}</p>}
      <fieldset disabled={saving} className="space-y-6">
      <Card className="bg-card border-border">
        <CardHeader>
          <CardTitle>Player Inclusion</CardTitle>
          <CardDescription>Select which players are available in your league</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <label className="flex items-center gap-2"><Checkbox data-testid="pool-select-all" checked={selectedTeams.length===32 ? true : selectedTeams.length ? "indeterminate" : false} onCheckedChange={v=>chooseTeams(v===true ? allTeams : [])} />Select All Teams</label>
          <div className="flex flex-wrap gap-5">
            {[['east','Eastern Conference'],['west','Western Conference']].map(([side,label])=>{
              const clubs=conferenceTeams(side),count=clubs.filter(x=>selectedTeams.includes(x)).length;
              return <label key={side} className="flex items-center gap-2"><Checkbox checked={count===16 ? true : count ? "indeterminate" : false} onCheckedChange={v=>chooseConference(side,v===true)} />{label}</label>;
            })}
          </div>
          <div className="overflow-x-auto" data-testid="player-pool-team-grid">
            <table className="w-full text-sm border-collapse"><tbody>
              {divisions.map(d=><tr key={d.name} className="odd:bg-secondary/60"><th className="text-left p-2" scope="row">{d.name}</th>{d.teams.map(team=><td key={team} className="p-2"><label className="flex items-center gap-1.5"><Checkbox data-testid={`pool-team-${team}`} checked={selectedTeams.includes(team)} onCheckedChange={()=>toggleTeam(team)} />{team}</label></td>)}</tr>)}
            </tbody></table>
          </div>
        </CardContent>
      </Card>

      <Card className="bg-card border-border">
        <CardHeader>
          <CardTitle>Pool Settings</CardTitle>
          <CardDescription>Additional player pool configurations</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <Label>Lock Player Pool</Label>
              <p className="text-sm text-muted-foreground">Freeze the finalized eligible-player list. Managers can still add, drop and trade eligible players.</p>
            </div>
            <Checkbox aria-label="Lock Player Pool" checked={pool.locked} onCheckedChange={v => set("locked",v===true)} />
          </div>
          <Separator />
          <div className="flex items-center justify-between">
            <div>
              <Label>Include Minor League Players</Label>
              <p className="text-sm text-muted-foreground">Drafted players in the AHL, ECHL, juniors or elsewhere, filtered by the NHL club holding their rights.</p>
            </div>
            <Checkbox aria-label="Include Drafted Minor League Players" checked={pool.include_minors} onCheckedChange={v => set("include_minors",v===true)} />
          </div>
          <Separator />
          <div className="flex items-center justify-between">
            <div>
              <Label>Include Non-Signed Players</Label>
              <p className="text-sm text-muted-foreground">Include eligible players who are not signed to an NHL contract.</p>
            </div>
            <Checkbox aria-label="Include Non-Signed Players" checked={pool.include_unsigned} onCheckedChange={v => set("include_unsigned",v===true)} />
          </div>
          <Separator />
          <div className="space-y-2">
            <Label>Duplicate Players for Selection</Label>
            <p className="text-sm text-muted-foreground">Allow the same player to be owned by multiple teams</p>
            <Select value={duplicatePlayers} onValueChange={setDuplicatePlayers}>
              <SelectTrigger
                className="bg-secondary border-border w-full sm:w-[280px]"
                data-testid="player-pool-duplicate-select"
              >
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="not-used">Not Used</SelectItem>
                <SelectItem value="entire-league">Entire League</SelectItem>
                <SelectItem value="across-divisions">Across Different Divisions</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>
      <Button onClick={save} disabled={saving} data-testid="player-pool-save">{saving ? "Saving…" : "Save Player Pool Settings"}</Button>
      </fieldset>
    </div>
  );
}
