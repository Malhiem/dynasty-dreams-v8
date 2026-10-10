import { request } from '@playwright/test';
import { ObjectId } from 'mongodb';
import { database, result } from './h2h';
export async function user() {
  const api=await request.newContext({baseURL:'http://web'});
  const username=`profile${crypto.randomUUID().replaceAll('-','').slice(0,16)}`;
  await result(await api.post('/api/auth/register',{data:{email:`${username}@e2e.dynastydreams.com`,username,password:'Profile-test-2026!'}}));
  const me=await result(await api.get('/api/auth/me'));
  return {api,username,id:me.id};
}
export async function seed(id:string,fields:any={}) {
  return database(async db=>{
    const lid=new ObjectId(),tid=new ObjectId();
    await db.collection('leagues').insertOne({_id:lid,name:'Profile Test League',is_private:false,format:'dynasty',sport:'nhl',current_season_status:'active'});
    await db.collection('teams').insertOne({_id:tid,owner_id:id,league_id:String(lid),name:'Profile Test Team',wins:0,losses:0,ties:0,points_for:0,live_points:0,roster:[],...fields});
    return {lid:String(lid),tid:String(tid)};
  });
}
export async function snapshots(u:any) {
  return {private:await result(await u.api.get('/api/users/me/level')),public:await result(await u.api.get(`/api/u/${u.username}`))};
}
export function publicXP(p:any) { return Array.from({length:p.level-1},(_,i)=>150+i*50).reduce((a,b)=>a+b,0)+p.xp_in_level; }
