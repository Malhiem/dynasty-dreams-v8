import { useEffect, useState } from 'react';
import api from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

const groups = { division: 'Same division', conference: 'Same conference (including division)', conference_other: 'Same conference, other division', outside_conference: 'Outside conference', all: 'All opponents' };
function errorText(error: any) {
  const detail = error?.response?.data?.detail;
  return typeof detail === 'string' ? detail : 'Unable to complete this request. Check the settings and try again.';
}

export default function CombinedSchedule({ leagueId, onApplied }: { leagueId: string; onApplied?: () => void }) {
  const [data, setData] = useState<any>(null);
  const [settings, setSettings] = useState<any>(null);
  const [preview, setPreview] = useState<any>(null);
  const [feedback, setFeedback] = useState<any>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState('');
  const [reload, setReload] = useState(0);
  const base = `/leagues/${leagueId}/schedule`;
  useEffect(() => {
    let cancelled = false;
    setBusy('Loading'); setError(''); setPreview(null); setData(null); setFeedback(null);
    api.get(`${base}/rules`).then(({ data }) => { if (!cancelled) { setData(data); setSettings(data.settings); } })
      .catch(e => { if (!cancelled) setError(errorText(e)); }).finally(() => { if (!cancelled) setBusy(''); });
    return () => { cancelled = true; };
  }, [base, reload]);
  function change(next: any) { setSettings(next); setPreview(null); setFeedback(null); setError(''); }
  async function request(action: string) {
    if (busy) return;
    setBusy(action); setError('');
    try {
      const { data: result } = await api.post(`${base}/${action}`, action === 'apply' ? { preview_id: preview.preview_id } : settings);
      if (action === 'preview') { setPreview(result.status === 'feasible' ? result : null); setFeedback(result); }
      else if (action === 'apply') {
        setPreview(null); setFeedback({ message: `Schedule version ${result.version} applied. ${result.games} games; ${result.preserved_games} existing games preserved.` });
        setData((old: any) => ({ ...old, version: result.version }));
        onApplied?.();
      } else { setFeedback(result); setPreview(null); }
    } catch (e: any) { setError(errorText(e)); if (e?.response?.status === 409) setPreview(null); }
    finally { setBusy(''); }
  }
  const fieldClass = 'w-full rounded-md border border-border bg-secondary p-2 min-w-0';
  if (!data || !settings) return <div>{busy && <p role="status">Loading opponent schedule…</p>}{error && <p role="alert">{error}</p>}{!busy && <Button onClick={() => setReload(v => v + 1)}>Retry opponent schedule</Button>}</div>;
  return <Card data-testid="combined-scheduler"><CardHeader><CardTitle>Combined Opponent Schedule</CardTitle></CardHeader><CardContent className="space-y-4 min-w-0">
    <p>{data.team_count} teams · {data.season} · Version {data.version} · {data.locked_games} protected games</p>
    <p className="text-sm text-muted-foreground">Every team gets exactly the selected number of distinct opponents each week. Completed, in-progress and locked games stay fixed. Conference totals include division games.</p>
    {!data.can_apply && <p role="status">Preview is available. Applying requires MongoDB transaction support; your existing schedule stays unchanged until that is enabled.</p>}
    <fieldset disabled={Boolean(busy)} className="space-y-4">
      <legend className="sr-only">Opponent schedule settings</legend>
      <div className="grid gap-3 sm:grid-cols-2">
        <label>Scoring periods<input className={fieldClass} type="number" min={1} max={52} value={settings.weeks} onChange={e => change({ ...settings, weeks: Number(e.target.value) })} /></label>
        <label>Matchups per team per period<input className={fieldClass} type="number" min={1} max={data.team_count - 1} value={settings.games_per_week} onChange={e => change({ ...settings, games_per_week: Number(e.target.value) })} /></label>
      </div>
      <p>Each team: {settings.weeks * settings.games_per_week} games · League: {data.team_count * settings.weeks * settings.games_per_week / 2} matchups</p>
      {settings.rules.map((r: any, i: number) => <div key={i} className="grid gap-2 sm:grid-cols-2 lg:grid-cols-5 border border-border rounded p-3">
        <label>Rule {i + 1} opponent group<select className={fieldClass} value={r.group} onChange={e => change({ ...settings, rules: settings.rules.map((v: any, n: number) => n === i ? { ...v, group: e.target.value } : v) })}>{Object.entries(groups).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
        <label>Rule {i + 1} count type<select className={fieldClass} value={r.scope} onChange={e => change({ ...settings, rules: settings.rules.map((v: any, n: number) => n === i ? { ...v, scope: e.target.value } : v) })}><option value="total">Season total per team</option><option value="per_opponent">Games per opponent</option></select></label>
        <label>Rule {i + 1} requirement<select className={fieldClass} value={r.comparison} onChange={e => change({ ...settings, rules: settings.rules.map((v: any, n: number) => n === i ? { ...v, comparison: e.target.value } : v) })}><option value="minimum">Minimum</option><option value="exact">Exact</option><option value="maximum">Maximum</option></select></label>
        <label>Rule {i + 1} games<input className={fieldClass} type="number" min={0} max={5148} value={r.value} onChange={e => change({ ...settings, rules: settings.rules.map((v: any, n: number) => n === i ? { ...v, value: Number(e.target.value) } : v) })} /></label>
        <Button variant="outline" aria-label={`Remove opponent rule ${i + 1}`} onClick={() => change({ ...settings, rules: settings.rules.filter((_: any, n: number) => n !== i) })}>Remove rule</Button>
      </div>)}
      <Button variant="outline" disabled={settings.rules.length >= 20} onClick={() => change({ ...settings, rules: [...settings.rules, { group: 'division', scope: 'total', comparison: 'minimum', value: 0 }] })}>Add opponent rule</Button>
    </fieldset>
    <div className="flex flex-wrap gap-2"><Button disabled={Boolean(busy)} variant="outline" onClick={() => request('check')}>Check feasibility</Button><Button disabled={Boolean(busy)} onClick={() => request('preview')}>Generate preview</Button></div>
    {busy && <p role="status">{busy === 'preview' ? 'Finding a valid weekly arrangement…' : `${busy}…`}</p>}
    {feedback?.message && <p role="status">{feedback.message}</p>}
    {feedback?.errors?.length > 0 && <div role="alert">{feedback.errors.map((e: string, i: number) => <p key={i}>{e}</p>)}</div>}
    {error && <p role="alert">{error}</p>}
    {preview && <div className="space-y-4" data-testid="opponent-preview">
      <h3 className="font-semibold">Validated schedule preview · {preview.games.length} matchups</h3>
      <p>All mandatory requirements passed. {preview.optimization_complete ? 'Opponent repetition optimization completed.' : 'A valid schedule was found; preference optimization may improve with another preview.'}</p>
      <div className="overflow-x-auto max-h-96"><table className="w-full text-sm"><caption>Requested versus achieved by team</caption><thead><tr>{['Team', 'Games', 'Home', 'Away', 'Division', 'Conference total', 'Other conference teams', 'Outside conference', 'Requirements'].map(h => <th scope="col" key={h} className="p-2 text-left">{h}</th>)}</tr></thead><tbody>{preview.validation.teams.map((t: any) => <tr key={t.team_id}><th scope="row" className="p-2">{t.name}</th><td>{t.games}</td><td>{t.home_games}</td><td>{t.away_games}</td><td>{t.division}</td><td>{t.conference}</td><td>{t.conference_other}</td><td>{t.outside_conference}</td><td>{t.requirements.length ? t.requirements.map((r: any, i: number) => <p key={i}>{groups[r.group as keyof typeof groups]}: {r.comparison} {r.value} {r.scope === 'total' ? `total → ${r.achieved}` : `per opponent → ${r.per_opponent.join(', ')}`} ✓</p>) : 'All weekly limits passed'}</td></tr>)}</tbody></table></div>
      <div className="overflow-x-auto max-h-96"><table className="w-full text-sm"><caption>Weekly opponents</caption><thead><tr><th scope="col">Period</th><th scope="col">Home</th><th scope="col">Away</th><th scope="col">Protected</th></tr></thead><tbody>{preview.games.map((g: any, i: number) => <tr key={i}><td>{g.week}</td><td>{g.home_team_name}</td><td>{g.away_team_name}</td><td>{g.preserved_id ? 'Yes' : ''}</td></tr>)}</tbody></table></div>
      <Button disabled={Boolean(busy) || !data.can_apply} onClick={() => request('apply')}>Apply validated schedule</Button>
    </div>}
  </CardContent></Card>;
}
