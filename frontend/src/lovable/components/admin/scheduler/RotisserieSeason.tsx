import {useEffect,useRef,useState} from 'react';
import api,{invalidateApiCache} from '@/lib/api';
import {Button} from '@/components/ui/button';

export default function RotisserieSeason({leagueId,onApplied,readOnly=false}: {leagueId:string;onApplied?:()=>void;readOnly?:boolean}){
 const [periods,setPeriods]=useState<any[]>([]),[busy,setBusy]=useState(false),[error,setError]=useState(''),[message,setMessage]=useState('');
 const pending=useRef(false),active=useRef(true);
 const load=async()=>{const {data}=await api.get(`/leagues/${leagueId}/roto/schedule`);if(active.current)setPeriods(data.periods);};
 useEffect(()=>{active.current=true;load().catch(()=>{if(active.current)setError('Unable to load Rotisserie periods. Retry to reload.');});return()=>{active.current=false;};},[leagueId]);
 async function act(period?:number){
  if(pending.current||readOnly)return;pending.current=true;setBusy(true);setError('');setMessage('');
  try{
   await api.post(period===undefined?`/leagues/${leagueId}/roto/generate`:`/leagues/${leagueId}/roto/recompute`,period===undefined?{}:{period,close:true});
   invalidateApiCache(/roto|matchups|leagues/);await load();if(active.current){setMessage(period===undefined?'Rotisserie calendar and enabled playoffs generated.':'Scoring period finalized.');onApplied?.();}
  }catch(e:any){if(active.current)setError(typeof e.response?.data?.detail==='string'?e.response.data.detail:'The outcome could not be confirmed. Reload periods before retrying; completed operations are safe to repeat.');}
  finally{pending.current=false;if(active.current)setBusy(false);}
 }
 return <section className="space-y-4 min-w-0" aria-label="Rotisserie season">
  <h3 className="font-semibold">Rotisserie scoring and playoffs</h3>
  <p>Save calendar dates above, then generate live scoring periods. Regular-season periods have no opponents. Enabled elimination playoffs use category points; tied games advance the higher original seed. Finalize all regular periods before the first playoff round.</p>
  <p className="text-sm text-muted-foreground">Periods can be finalized after their ending date. Historical ownership must be available. Finalized results cannot be regenerated or reopened.</p>
  <div className="flex flex-wrap gap-2"><Button className="min-h-11" disabled={busy||readOnly} onClick={()=>act()}>Generate Rotisserie season</Button><Button className="min-h-11" variant="outline" disabled={busy} onClick={()=>{setError('');load().catch(()=>setError('Unable to reload periods.'));}}>Reload periods</Button></div>
  {error&&<p role="alert">{error}</p>}{message&&<p role="status">{message}</p>}
  <ul className="space-y-2">{periods.map(p=><li key={p.id} className="flex flex-wrap items-center justify-between gap-3 rounded border border-border p-3"><span>{p.type} {p.id}: {p.startDate} – {p.endDate}{p.closed?' · Finalized':''}</span><Button className="min-h-11" variant="outline" disabled={busy||readOnly||p.closed} aria-label={`Finalize ${p.type} period ${p.id}`} onClick={()=>act(p.id)}>Finalize period</Button></li>)}</ul>
 </section>;
}
