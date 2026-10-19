/** Draft-scoped eligible pool. Exact searches use the server while the full pool loads. */
import {useCallback,useEffect,useRef,useState} from "react";
import api from "@/lib/api";
import type {DraftEligiblePlayer} from "@/lovable/pages/draftroom/types";

type ApiPlayer = Partial<DraftEligiblePlayer> & {headshot?:string;nhl_id?:string;team_name?:string;player_type?:string;minor_eligible?:boolean};
interface DraftLike {_id?:string;picks?:Array<{player_id?:string}>}
const PAGE_SIZE=200;

function player(p:ApiPlayer,drafted:Set<string>):DraftEligiblePlayer{
 return {id:String(p.id??""),name:String(p.name??""),position:String(p.position??""),nhlTeam:p.nhlTeam||"—",age:p.age||0,
  league:p.league||"NHL",gp:p.gp||0,g:p.g||0,a:p.a||0,pts:p.pts||0,ranking:p.ranking||0,drafted:drafted.has(String(p.id)),
  ...(p.headshot?{headshot:p.headshot,headshot_url:p.headshot}:{}),...(p.nhl_id?{nhl_id:p.nhl_id}:{}),
  ...(p.team_name?{team_name:p.team_name}:{}),...(p.player_type?{player_type:p.player_type}:{}),
  minor_eligible:!!p.minor_eligible,status_flags:(p as any).status_flags||null,
 } as unknown as DraftEligiblePlayer;
}

export function useDraftEligiblePlayers(currentDraft:DraftLike|null,setPlayers:(players:DraftEligiblePlayer[])=>void,searchQuery=""){
 const latest=useRef(currentDraft);latest.current=currentDraft;
 const pool=useRef<{id?:string;rows:Map<string,ApiPlayer>}>({rows:new Map()});
 const [loading,setLoading]=useState(false),[error,setError]=useState(""),[revision,setRevision]=useState(0);
 const retry=useCallback(()=>setRevision(value=>value+1),[]);
 useEffect(()=>{
  const id=currentDraft?._id;if(!id){setLoading(false);setError("");return;}
  if(pool.current.id!==id){pool.current={id,rows:new Map()};setPlayers([]);}
  let cancelled=false;const controller=new AbortController();setLoading(true);setError("");
  const publish=()=>{
   if(cancelled||latest.current?._id!==id||pool.current.id!==id)return;
   const drafted=new Set((latest.current.picks||[]).map(p=>String(p.player_id||"")));
   setPlayers([...pool.current.rows.values()].map(p=>player(p,drafted)));
  };
  async function load(){
   const seen=new Set<string>();let page=1,totalPages=1;
   try{
    while(page<=totalPages){
     const params=new URLSearchParams({limit:String(PAGE_SIZE),page:String(page)});
     if(searchQuery.trim())params.set("search",searchQuery.trim());
     const {data}=await api.get(`/drafts/${id}/eligible-players?${params}`,{signal:controller.signal});
     if(cancelled||latest.current?._id!==id)return;
     const rows:ApiPlayer[]=data?.players||[];totalPages=Number(data?.pages||1);
     if(!Number.isSafeInteger(totalPages)||totalPages<1)throw Error("Invalid player pagination");
     if(!rows.length)break;
     let added=0;
     for(const p of rows){
      const pid=String(p.id||"");if(!pid||seen.has(pid))continue;seen.add(pid);added++;
      const previous=pool.current.rows.get(pid);
      // Search-local ranks must not reorder the full pool after clearing search.
      const ranking=searchQuery.trim()?previous?.ranking??Number.MAX_SAFE_INTEGER:p.ranking;
      pool.current.rows.set(pid,{...p,ranking});
     }
     if(!added)throw Error("Player pagination did not advance");
     if(page===1)publish();
     if(rows.length<PAGE_SIZE)break;page++;
    }
    publish();
   }catch(e:any){
    if(cancelled||latest.current?._id!==id)return;
    if(e.response?.status===401||e.response?.status===403){pool.current.rows.clear();setPlayers([]);}
    setError("Unable to load eligible players. Retry to refresh the player pool.");
   }finally{if(!cancelled&&latest.current?._id===id)setLoading(false);}
  }
  const timer=window.setTimeout(()=>void load(),searchQuery.trim()?250:0);
  return()=>{cancelled=true;window.clearTimeout(timer);controller.abort();};
 },[currentDraft?._id,searchQuery,revision]);
 return {loading,error,retry};
}
export default useDraftEligiblePlayers;
