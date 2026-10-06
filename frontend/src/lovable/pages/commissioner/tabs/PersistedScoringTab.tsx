import { useEffect, useState } from "react";
import { toast } from "sonner";
import api, { formatApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { scoringCategories } from "../data/commissionerData";
import ScoringTab from "./ScoringTab";

type Setting = { enabled: boolean; points: number };
type Config = { skater_scoring: Record<string, number>; goalie_scoring: Record<string, number>; roto_categories: string[] };
const aliases: Record<string, string> = {
  shots_on_goal: "shots", shorthanded_goals: "short_handed_goals",
  shorthanded_points: "short_handed_points", shorthanded_assists: "short_handed_assists",
};
const skaters = scoringCategories.filter(c => c.type !== "goalie");
// Shared categories need independent skater and goalie values.
const goalies = scoringCategories.filter(c => c.type !== "skater").map(c =>
  c.type === "both" ? { ...c, id: `goalie_${c.id}` } : c);
const groups = [["skater_scoring", skaters], ["goalie_scoring", goalies]] as const;
const originalId = (id: string) => id.startsWith("goalie_") ? id.slice(7) : id;
const apiKey = (id: string) => aliases[originalId(id)] || originalId(id);

function settingsFrom(config: Config): Record<string, Setting> {
  return Object.fromEntries(groups.flatMap(([group, categories]) => categories.map(c => {
    const weights = config[group] || {};
    const value = weights[apiKey(c.id)] ?? weights[originalId(c.id)];
    return [c.id, { enabled: value !== undefined, points: value ?? c.defaultPoints }];
  })));
}

export default function PersistedScoringTab({ activeLeague, reloadLeague, GoalieScoringCard }: any) {
  const leagueId = activeLeague.id;
  const [loaded, setLoaded] = useState<{ leagueId: string; config: Config } | null>(null);
  const [settings, setSettings] = useState<Record<string, Setting>>({});
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let cancelled = false;
    setLoaded(null); setError("");
    api.get(`/scoring/config?league_id=${leagueId}`).then(({ data }) => {
      if (cancelled) return;
      setSettings(settingsFrom(data));
      setLoaded({ leagueId, config: data });
    }).catch(e => { if (!cancelled) setError(formatApiError(e)); });
    return () => { cancelled = true; };
  }, [leagueId, attempt]);

  const save = async () => {
    if (saving || loaded?.leagueId !== leagueId) return;
    const config: Config = { ...loaded.config,
      skater_scoring: { ...loaded.config.skater_scoring },
      goalie_scoring: { ...loaded.config.goalie_scoring } };
    for (const [group, categories] of groups) {
      for (const c of categories) {
        const setting = settings[c.id];
        if (!Number.isFinite(setting.points)) { setError("Enter a valid number for every scoring category."); return; }
        delete config[group][originalId(c.id)];
        delete config[group][apiKey(c.id)];
        if (setting.enabled) config[group][apiKey(c.id)] = setting.points;
      }
    }
    setSaving(true); setError("");
    try {
      await api.post("/scoring/config", { league_id: leagueId,
        skater_scoring: config.skater_scoring, goalie_scoring: config.goalie_scoring,
        roto_categories: config.roto_categories || [] });
      setLoaded({ leagueId, config });
      toast.success("Scoring settings saved");
    } catch (e) { setError(formatApiError(e)); }
    finally { setSaving(false); }
  };

  if (loaded?.leagueId !== leagueId) return error ? <div role="alert">
    {error} <Button onClick={() => setAttempt(n => n + 1)}>Retry loading scoring</Button>
  </div> : <p role="status">Loading scoring settings…</p>;
  return <>
    {error && <p role="alert">{error}</p>}
    <fieldset disabled={saving} aria-busy={saving}>
      <ScoringTab skaterCategories={skaters} goalieCategories={goalies}
        scoringSettings={settings}
        toggleScoringCategory={id => setSettings(prev => ({ ...prev, [id]: { ...prev[id], enabled: !prev[id].enabled } }))}
        updateScoringPoints={(id, points) => setSettings(prev => ({ ...prev, [id]: { ...prev[id], points } }))}
        onSave={save}
        onReset={() => setSettings(Object.fromEntries([...skaters, ...goalies].map(c =>
          [c.id, { enabled: c.defaultPoints !== 0, points: c.defaultPoints }]))) }
        activeLeague={activeLeague} reloadLeague={reloadLeague} GoalieScoringCard={GoalieScoringCard} />
    </fieldset>
  </>;
}
