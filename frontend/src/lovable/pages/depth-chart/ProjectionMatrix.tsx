import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Tooltip, TooltipTrigger, TooltipContent, TooltipProvider } from '@/components/ui/tooltip';
import { PlanningPlayerBadges } from '@/lovable/components/PlanningPlayerBadges';
import { FantasyPointInputs } from './FantasyPointInputs';
import { money, planValues, points, seasonLabel, seasonTotals } from './model';

function PointLabel({ children, description }: { children: string; description: string }) {
  return <Tooltip><TooltipTrigger asChild><button type="button" className="text-[10px] text-muted-foreground cursor-help border-b border-dotted focus-visible:ring-2 focus-visible:ring-ring">{children}</button></TooltipTrigger><TooltipContent>{description}</TooltipContent></Tooltip>;
}

export function ProjectionMatrix({ data, rows, year, display, sort, onSort, selectedId, onSelectPlayer, onSelectYear, updateSeason }: any) {
  const setValue = (y: number, pid: string, field: string, value: number) => updateSeason(y, (old: any) => ({
    ...old, [field]: { ...old[field], [pid]: value }, ...(field === 'pf' ? { sources: { ...old.sources, [pid]: 'Manual' } } : {}),
  }));
  const showSalary = display !== 'points';
  const showPoints = display !== 'salary';
  const sortOrder = (field: string, y = 0): 'ascending' | 'descending' | 'none' => sort.field === field && sort.year === y ? sort.direction === 'asc' ? 'ascending' : 'descending' : 'none';
  const arrow = (field: string, y = 0) => sortOrder(field, y) === 'none' ? '↕' : sortOrder(field, y) === 'ascending' ? '↑' : '↓';
  const seasons = data.seasons || [];
  const totals = seasons.map((s: any) => seasonTotals(data.players, s.year, data.plan.seasons[String(s.year)] || {}, s.dead || 0));
  return <TooltipProvider><div className="overflow-auto max-h-[60dvh] sm:max-h-[70vh] rounded-md border border-border" data-testid="depth-matrix" tabIndex={0} aria-label="All-season roster projections">
    <table className="w-full text-sm border-separate border-spacing-0">
      <thead className="sticky top-0 z-30"><tr>
        <th className="sm:sticky sm:left-0 z-40 bg-card border-b border-r border-border p-2 text-left min-w-[80px] w-[80px]" aria-sort={sortOrder('position')}><button type="button" data-testid="depth-sort-position" className="w-full whitespace-nowrap text-xs text-left focus-visible:ring-2 focus-visible:ring-ring" onClick={() => onSort('position')}>Position {arrow('position')}</button></th>
        <th className="sticky left-0 sm:left-[80px] z-40 bg-card border-b border-border p-3 text-left min-w-[120px] w-[120px] max-w-[120px] sm:max-w-none sm:min-w-[190px] sm:w-[190px]" aria-sort={sortOrder('name')}><button type="button" data-testid="depth-sort-name" className="w-full text-left focus-visible:ring-2 focus-visible:ring-ring" onClick={() => onSort('name')}>Player {arrow('name')}</button></th>
        {seasons.map((s: any) => <th key={s.year} aria-sort={sortOrder(showSalary ? 'salary' : 'pf', s.year)} className={`bg-card border-b p-3 min-w-[184px] ${s.year === year ? 'border-primary bg-muted' : 'border-border'}`}>
          <button type="button" data-testid={`depth-season-${s.year}`} aria-pressed={s.year === year} className="w-full rounded px-2 py-1 focus-visible:ring-2 focus-visible:ring-ring" onClick={() => { onSelectYear(s.year); onSort(showSalary ? 'salary' : 'pf', s.year); }}>{seasonLabel(s.year)} {arrow(showSalary ? 'salary' : 'pf', s.year)}{s.year === year && <span className="block text-[10px] font-normal text-primary">Summary &amp; history target</span>}</button>
          <span className="block text-[10px] font-normal text-muted-foreground">{sortOrder(showSalary ? 'salary' : 'pf', s.year) === 'none' ? `Sort ${showSalary ? 'salary' : 'Total FP'}` : sort.direction === 'desc' ? 'Highest to lowest' : 'Lowest to highest'}</span>
          {s.tentative && <span className="text-[10px] font-normal text-muted-foreground">Tentative cap</span>}
        </th>)}
      </tr></thead>
      <tbody>{rows.map((player: any, index: number) => <tr key={player.id} data-testid={`depth-row-${player.id}`} className={index % 2 ? 'bg-muted/30' : 'bg-card'}>
        <td className={`sm:sticky sm:left-0 z-20 border-b border-r border-border p-2 align-top ${index % 2 ? 'bg-muted' : 'bg-card'}`}><Badge variant="outline" className="text-[10px] whitespace-nowrap">{player.position || '—'}</Badge></td>
        <th scope="row" className={`sticky left-0 sm:left-[80px] z-20 max-w-[120px] sm:max-w-none text-left border-b border-r border-border p-3 align-top ${index % 2 ? 'bg-muted' : 'bg-card'}`}>
          <div className="flex flex-wrap items-center gap-1.5"><Button variant="link" className={`p-0 h-auto text-foreground text-left whitespace-normal ${selectedId === player.id ? 'font-bold underline decoration-primary decoration-2' : ''}`} onClick={() => onSelectPlayer(player.id)} aria-pressed={selectedId === player.id}>{player.name}</Button><PlanningPlayerBadges player={player} /></div>
          {showSalary && <p className="text-[10px] font-normal text-muted-foreground mt-1">AAV {money(player.aav)}</p>}
        </th>
        {seasons.map((s: any) => {
          const season = data.plan.seasons[String(s.year)] || {}, value = planValues(player, s.year, season);
          const suffix = s.year === year ? '' : `-${s.year}`;
          return <td key={s.year} className={`p-3 align-top border-b border-l border-border ${s.year === year ? 'bg-primary/5' : ''}`} data-testid={`depth-cell-${player.id}-${s.year}`}>
            {!value.projected ? <p className="text-xs text-muted-foreground">NHL assumption starts {seasonLabel(player.nhl_start_year)}</p> : <>
            {showSalary && (value.pending ? <div className="h-12"><p className="font-mono">{money(0)}</p><p className="text-[10px] text-muted-foreground">Starts {seasonLabel(player.contract.start_year)}</p></div> : value.signed ? <div className="h-12"><p className="font-mono whitespace-nowrap" data-testid={`depth-salary-${player.id}${suffix}`}>{money(value.salary)}</p><p className="text-[10px] text-muted-foreground">Contract · locked</p></div> : <div className="h-12 flex items-start gap-1">
              <Badge variant="outline" className={`text-[10px] mt-1 ${player.contract.end_status === 'RFA' ? 'text-primary border-primary/40' : 'text-amber-500 border-amber-500/40'}`}>{player.contract.end_status || 'UFA'}</Badge>
              <Input type="number" min="0" max="1000000000" step="100000" className="h-8 w-full min-w-0 text-xs px-2" disabled={!data.can_edit}
                aria-label={`${player.name} ${seasonLabel(s.year)} salary estimate`} data-testid={`depth-estimate-${player.id}${suffix}`} value={value.entered ? season.estimates[player.id] : ''} placeholder="Estimate $"
                onChange={event => { if (event.target.value === '') updateSeason(s.year, (old: any) => { const estimates = { ...old.estimates }; delete estimates[player.id]; return { ...old, estimates }; });
                  else { const n = Number(event.target.value); if (Number.isFinite(n)) setValue(s.year, player.id, 'estimates', Math.max(0, Math.min(1e9, n))); } }} />
            </div>)}
            {showPoints && <><div className="grid grid-cols-2 gap-x-2 gap-y-1">
              <div><PointLabel description="Fantasy Points per Game">FP/G</PointLabel></div><div><PointLabel description="Total Fantasy Points">Total FP</PointLabel></div>
              <FantasyPointInputs compact testSuffix={suffix} seasonLabel={seasonLabel(s.year)} player={player} total={value.pf} disabled={!data.can_edit} onChange={(total: number) => setValue(s.year, player.id, 'pf', total)} />
            </div><p className="text-[10px] text-muted-foreground mt-1">{value.source}</p></>}</>}
          </td>;
        })}
      </tr>)}
      {!rows.length && <tr><td colSpan={seasons.length + 2} className="p-4">No projected players match the current filters.</td></tr>}
      </tbody><tfoot>{['Planned cap', 'Available cap', 'Team Total FP'].map((label, i) => (i === 2 ? showPoints : showSalary) && <tr key={label} className="font-semibold bg-muted/30">
        <td className="sm:sticky sm:left-0 z-20 bg-card border-t border-border" /><th className="sticky left-0 sm:left-[80px] z-20 bg-card text-left p-3 border-t border-border">{label}<span className="block text-[10px] font-normal text-muted-foreground">Entire roster</span></th>
        {seasons.map((s: any, n: number) => { const t = totals[n], room = s.cap - t.locked - t.estimated;
          return <td key={s.year} className={`p-3 border-t border-l border-border font-mono ${i === 1 && room < 0 && data.cap_enabled ? 'text-destructive' : ''}`}>
            <span data-testid={i === 2 ? (s.year === year ? 'depth-team-pf' : `depth-team-pf-${s.year}`) : `depth-matrix-${i === 0 ? 'cap' : 'room'}-${s.year}`}>{i === 0 ? money(t.locked + t.estimated) : i === 1 ? data.cap_enabled ? money(room) : 'Disabled' : points(t.pf)}</span>
            {i === 0 && <span className="block text-[10px] font-sans font-normal text-muted-foreground">{money(s.dead || 0)} dead cap{t.missing ? ` · ${t.missing} unestimated` : ''}</span>}
          </td>;
        })}
      </tr>)}</tfoot>
    </table>
  </div></TooltipProvider>;
}
