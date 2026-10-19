import {ObjectId} from 'mongodb';
import {database} from './h2h';
export async function draftListCandidates(lastSalary = 1_000_000,count = 120){
 const prefix=`Paged ${crypto.randomUUID()}`;
 const players=Array.from({length:count},(_,i)=>({_id:new ObjectId(),name:`${prefix} ${String(i).padStart(String(count-1).length,'0')}`,position:'RW',salary:i===count-1?lastSalary:1000000,points:0,status:'healthy'}));
 await database(db=>db.collection('players').insertMany(players));
 return {prefix,players,cleanup:()=>database(db=>db.collection('players').deleteMany({_id:{$in:players.map(p=>p._id)}}))};
}
