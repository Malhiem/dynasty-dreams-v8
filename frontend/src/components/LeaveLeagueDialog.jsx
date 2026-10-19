import {useAuth} from '@/contexts/AuthContext';
import {useEffect,useRef,useState} from 'react';
import api,{invalidateApiCache} from '@/lib/api';
import {Button} from '@/components/ui/button';
import {Dialog,DialogContent,DialogDescription,DialogFooter,DialogHeader,DialogTitle} from '@/components/ui/dialog';

export default function LeaveLeagueDialog({league,onClose,onLeft,returnFocus}){
 const {user}=useAuth();const currentIdentity=String(user?.id||user?._id||'');const identity=useRef(currentIdentity);const liveIdentity=useRef(currentIdentity);liveIdentity.current=currentIdentity;
 useEffect(()=>{if(league){identity.current=currentIdentity;setError('');}},[league?.id]);
 const [busy,setBusy]=useState(false);const [error,setError]=useState('');const pending=useRef(false);
 async function leave(){
  if(pending.current||!league||!identity.current||identity.current!==liveIdentity.current)return;pending.current=true;setBusy(true);setError('');
  try{
   let response;
   try{response=await api.post(`/leagues/${league.id}/leave`,{expected_user_id:identity.current});}
   catch(e){if(!e.response||e.response.status>=500)response=await api.post(`/leagues/${league.id}/leave`,{expected_user_id:identity.current});else throw e;}
   if(response.data.status!=='left')throw new Error('Leaving was not confirmed. Please try again.');
   if(identity.current!==liveIdentity.current)return;
   invalidateApiCache(/./);
   try{
    if(localStorage.getItem('dd_active_league_id')===league.id)localStorage.removeItem('dd_active_league_id');
    const order=JSON.parse(localStorage.getItem('dd_league_order_v1')||'[]');
    if(Array.isArray(order))localStorage.setItem('dd_league_order_v1',JSON.stringify(order.filter(id=>id!==league.id)));
    localStorage.setItem('dd_leagues_revision',`${Date.now()}:${league.id}`);
   }catch{/* Server membership is authoritative even if local storage is unavailable. */}
   window.dispatchEvent(new Event('dd:leagues-changed'));onLeft(league.id);window.location.assign('/dashboard');
  }catch(e){const detail=e.response?.data?.detail;setError(typeof detail==='string'?detail:'Leaving could not be confirmed. Please retry; another attempt will not duplicate the exit.');}
  finally{pending.current=false;setBusy(false);}
 }
 return <Dialog open={!!league} onOpenChange={open=>!open&&!pending.current&&onClose()}>
  <DialogContent className="max-h-[calc(100dvh-2rem)] overflow-y-auto" onCloseAutoFocus={event=>{event.preventDefault();returnFocus.current?.focus();}}>
   <DialogHeader><DialogTitle>Leave {league?.name}?</DialogTitle>
    <DialogDescription>You can leave immediately, without approval or a replacement. Your team, roster and league history remain. Any ownership or commissioner role you leave behind becomes vacant. Rejoining may require an invitation.</DialogDescription>
   </DialogHeader>
   {error&&<p role="alert">{error}</p>}
   <DialogFooter><Button variant="outline" className="min-h-11" disabled={busy} onClick={onClose}>Stay in league</Button>
    <Button variant="destructive" className="min-h-11" disabled={busy||!identity.current||identity.current!==currentIdentity} aria-busy={busy} onClick={leave}>{busy?'Leaving…':'Leave league'}</Button></DialogFooter>
  </DialogContent>
 </Dialog>;
}
