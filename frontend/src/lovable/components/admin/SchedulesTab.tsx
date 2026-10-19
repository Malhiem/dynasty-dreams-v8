import RotisserieSeason from './scheduler/RotisserieSeason';
import { useEffect, useRef, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import api from '@/lib/api';
import CombinedSchedule from './scheduler/CombinedSchedule';
import { toast } from 'sonner';
import { defaults, generatePeriods, validate, days } from './scheduler/calendar';

const intervalOptions = ['daily', 'weekly', 'biweekly', 'monthly'];
const weekdays = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
const message = (error: any) => typeof error?.response?.data?.detail === 'string' ? error.response.data.detail : 'Unable to save schedule. Check the calendar and try again.';

function Field({ label, name, value, onChange, type = 'date', options, disabled = false }: any) {
  const id = `scheduler-${name}`;
  const classes = 'w-full min-w-0 rounded-md border border-border bg-secondary text-secondary-foreground min-h-11 p-2 text-sm';
  return <div className="space-y-1 min-w-0"><label htmlFor={id} className="text-sm">{label}</label>
    {options ? <select id={id} data-testid={id} className={classes} value={value} disabled={disabled} onChange={e => onChange(e.target.value)}>
      {options.map((option: any) => <option key={option.value ?? option} value={option.value ?? option}>{option.label ?? option}</option>)}
    </select> : <input id={id} data-testid={id} className={classes} type={type} value={value} disabled={disabled} onChange={e => onChange(e.target.value)} />}
  </div>;
}

// Keying by league and season prevents old drafts and delayed responses crossing contexts.
export default function SchedulesTab({ league, reloadLeague }: { league: any; reloadLeague?: () => void }) {
  if (!league?.id) return <p role="status">Select a league to configure its schedule.</p>;
  const season = Number(league.current_season_year || String(league.season_start_date || new Date().toISOString()).slice(0, 4));
  return <CalendarEditor key={`${league.id}:${season}`} league={league} season={season} reloadLeague={reloadLeague} />;
}

function CalendarEditor({ league, season, reloadLeague }: any) {
  const [config, setConfig] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');
  const [saveError, setSaveError] = useState('');
  const [saving, setSaving] = useState(false);
  const [editable, setEditable] = useState(false);
  const [maximum, setMaximum] = useState(Number(league.max_teams || 12));
  const [retry, setRetry] = useState(0);
  const editTrigger = useRef<HTMLButtonElement | null>(null);
  const [editing, setEditing] = useState<any>(null);
  const [tab, setTab] = useState('regular');
  const url = `/leagues/${league.id}/scheduler/${season}`;

  useEffect(() => {
    let cancelled = false;
    setLoading(true); setLoadError('');
    api.get(url).then(({ data }) => {
      if (cancelled) return;
      setConfig(data.calendar || defaults(league)); setEditable(data.can_edit); setMaximum(data.max_teams);
    }).catch(() => { if (!cancelled) setLoadError('Unable to load this season’s schedule. Try again.'); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [url, retry]);

  if (loading) return <p role="status">Loading schedule…</p>;
  if (loadError) return <div role="alert">{loadError} <Button onClick={() => setRetry(v => v + 1)}>Retry</Button></div>;
  if (!config) return null;
  const roto = league.scoring_format === "rotisserie";
  const disabled = saving || !editable;
  const { errors, warnings } = validate(config, maximum);
  const change = (field: string, value: any) => { setConfig((c: any) => ({ ...c, [field]: value })); setSaveError(''); };
  const regenerate = (kind: string) => {
    try {
      const regular = kind === 'regular';
      change(regular ? 'regularPeriods' : 'playoffPeriods', generatePeriods(
        regular ? config.seasonStart : config.playoffStart, regular ? config.seasonEnd : config.playoffEnd,
        regular ? config.scoringInterval : config.playoffInterval, kind, config.startDay, regular ? config.mergeWeeks : 1));
    } catch (error: any) { setSaveError(error.message); }
  };
  const save = async () => {
    if (disabled || errors.length) return;
    setSaving(true); setSaveError('');
    try { await api.put(url, config); toast.success('Schedule saved'); }
    catch (error: any) { setSaveError(message(error)); }
    finally { setSaving(false); }
  };
  const periods = (items: any[]) => <div className="overflow-x-auto">
    {items.length === 0 ? <p role="status">No scoring periods. Regenerate periods to get started.</p> :
      <table className="w-full text-sm" data-testid="scheduler-periods"><caption className="sr-only">Scoring periods</caption>
        <thead><tr>{['Period', 'Start Date', 'End Date', 'Days', 'Actions'].map(h => <th scope="col" key={h} className="p-2 text-left">{h}</th>)}</tr></thead>
        <tbody>{items.map(p => <tr key={`${p.type}-${p.id}`} className="border-t border-border">
          <th scope="row" className="p-2 text-left">{p.type} {p.id}</th><td className="p-2 whitespace-nowrap">{p.startDate}</td><td className="p-2 whitespace-nowrap">{p.endDate}</td><td className="p-2">{days(p.startDate, p.endDate)}</td>
          <td><Button variant="ghost" disabled={disabled} aria-label={`Edit ${p.type} period ${p.id}`} onClick={event => { editTrigger.current = event.currentTarget; setEditing({ ...p }); }}>Edit</Button></td>
        </tr>)}</tbody></table>}
  </div>;
  const field = (label: string, name: string, type = 'date', options?: any[]) => <Field label={label} name={name} type={type} options={options} value={config[name]} disabled={disabled} onChange={(v: any) => change(name, type === 'number' ? Number(v) : v)} />;
  const editError = editing && (!editing.startDate || !editing.endDate || editing.endDate < editing.startDate) ? 'Choose both dates, with end on or after start.' : '';
  const applyEdit = () => {
    if (!editing || editError) return;
    const key = editing.type === 'regular' ? 'regularPeriods' : 'playoffPeriods';
    const next = { ...config, [key]: config[key].map((p: any) => p.id === editing.id ? editing : p) };
    const validation = validate(next, maximum);
    if (validation.errors.length) { setSaveError(validation.errors[0]); return; }
    setConfig(next); setEditing(null); setSaveError('');
  };
  return <section className="space-y-4 min-w-0" data-testid="scheduler">
    <h2 className="text-lg font-semibold">{league.name} · {season} season calendar</h2>
    <p className="text-sm text-muted-foreground">{roto ? "Save calendar dates, then use Rotisserie Season to generate scoring periods and enabled playoffs." : "Save scoring period dates and bracket plans for this season. Use Opponent Schedule below to generate and apply live weekly matchups."}</p>
    {!editable && <p role="status">Only league administrators can edit this calendar.</p>}
    <Tabs value={tab} onValueChange={setTab}>
      <TabsList className="flex flex-wrap h-auto justify-start gap-1">
        <TabsTrigger value="regular">Regular Season</TabsTrigger><TabsTrigger value="playoffs">Playoffs</TabsTrigger><TabsTrigger value="projection">Full Schedule Projection</TabsTrigger><TabsTrigger value="opponents">{roto ? "Rotisserie Season" : "Opponent Schedule"}</TabsTrigger>
      </TabsList>
      <TabsContent value="regular"><Card><CardHeader><CardTitle>Regular Season Dates</CardTitle></CardHeader><CardContent className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-2">{field('Beginning Scoring Period', 'seasonStart')}{field('Ending Scoring Period', 'seasonEnd')}
          {field('Scoring Period Interval', 'scoringInterval', 'text', intervalOptions)}
          <Field label="Scoring Period Start Day" name="startDay" value={config.startDay} options={weekdays.map((label, value) => ({ label, value }))} disabled={disabled} onChange={(v: string) => change('startDay', Number(v))} />
          <Field label="Merge First N Periods" name="mergeWeeks" value={config.mergeWeeks} options={[1, 2, 3]} disabled={disabled} onChange={(v: string) => change('mergeWeeks', Number(v))} />
          {!roto && field(`Opponents per scoring period (1–${maximum - 1})`, 'matchupsPerPeriod', 'number')}
        </div><Button disabled={disabled} onClick={() => regenerate('regular')}>Regenerate Regular Periods</Button>
        {periods(config.regularPeriods)}
      </CardContent></Card></TabsContent>
      <TabsContent value="playoffs"><Card><CardHeader><CardTitle>Playoff Dates and Brackets</CardTitle></CardHeader><CardContent className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-2">{field('Playoff Start Date', 'playoffStart')}{field('Playoff End Date', 'playoffEnd')}{field('Playoff Scoring Interval', 'playoffInterval', 'text', intervalOptions)}</div>
        <Button disabled={disabled} onClick={() => regenerate('playoff')}>Regenerate Playoff Periods</Button>{periods(config.playoffPeriods)}
        {!config.brackets.length && <p>No brackets configured. Add one to get started.</p>}
        {config.brackets.map((b: any, i: number) => <div className="grid gap-3 sm:grid-cols-3 border border-border rounded p-3" key={b.id}>
          {[['Name', 'name', 'text'], ['Teams', 'teams', 'number'], ['Rounds', 'rounds', 'number']].map(([label, key, type]) => <Field key={key} label={`Bracket ${i + 1} ${label}`} name={`bracket-${i}-${key}`} type={type} value={b[key]} disabled={disabled} onChange={(v: string) => change('brackets', config.brackets.map((item: any, idx: number) => idx === i ? { ...item, [key]: type === 'number' ? Number(v) : v } : item))} />)}
          <Button variant="outline" disabled={disabled} aria-label={`Remove bracket ${i + 1}`} onClick={() => change('brackets', config.brackets.filter((_: any, idx: number) => idx !== i))}>Remove Bracket</Button>
        </div>)}
        <Button disabled={disabled || config.brackets.length >= 50} onClick={() => change('brackets', [...config.brackets, { id: String(Date.now()) + Math.random().toString(36).slice(2), name: 'New Bracket', teams: 2, rounds: 1 }])}>Add Bracket</Button>
      </CardContent></Card></TabsContent>
      <TabsContent value="projection"><Card><CardHeader><CardTitle>Full Season Schedule Projection</CardTitle></CardHeader><CardContent>{periods([...config.regularPeriods, ...config.playoffPeriods])}</CardContent></Card></TabsContent>
      <TabsContent value="opponents">{roto ? <RotisserieSeason key={url} leagueId={league.id} onApplied={reloadLeague} readOnly={!editable} /> : <CombinedSchedule key={url} leagueId={league.id} onApplied={reloadLeague} />}</TabsContent>
    </Tabs>
    {errors.length > 0 && <div role="alert" className="text-destructive">{errors.map((e: string) => <p key={e}>{e}</p>)}</div>}
    {warnings.length > 0 && <div role="status" className="text-amber-400">{warnings.map((w: string, i: number) => <p key={i}>{w}</p>)}</div>}
    {saveError && <p role="alert">{saveError}</p>}
    <div className="flex flex-wrap justify-end gap-3"><Button variant="outline" disabled={disabled} onClick={() => { setConfig(defaults(league)); setSaveError(''); }}>Reset to Defaults</Button>
      <Button disabled={disabled || errors.length > 0} onClick={save}>{saving ? 'Saving…' : 'Save Schedule'}</Button></div>
    <Dialog open={Boolean(editing)} onOpenChange={open => !open && setEditing(null)}><DialogContent onCloseAutoFocus={event => { event.preventDefault(); editTrigger.current?.focus(); }}>
      <DialogHeader><DialogTitle>Edit {editing?.type} Period {editing?.id}</DialogTitle><DialogDescription>Adjust this period within the season. Overlapping dates are rejected.</DialogDescription></DialogHeader>
      {editing && <><Field label="Start Date" name="edit-start" value={editing.startDate} onChange={(v: string) => { setEditing({ ...editing, startDate: v }); setSaveError(''); }} /><Field label="End Date" name="edit-end" value={editing.endDate} onChange={(v: string) => { setEditing({ ...editing, endDate: v }); setSaveError(''); }} /></>}
      {(editError || saveError) && <p role="alert">{editError || saveError}</p>}
      <DialogFooter><Button variant="outline" onClick={() => setEditing(null)}>Cancel</Button><Button disabled={Boolean(editError) || disabled} onClick={applyEdit}>Save Changes</Button></DialogFooter>
    </DialogContent></Dialog>
  </section>;
}
