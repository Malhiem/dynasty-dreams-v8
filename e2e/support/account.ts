import { request } from '@playwright/test';
import { MongoClient,ObjectId } from 'mongodb';
import { randomUUID } from 'node:crypto';
import type { Account } from '../pages/account/account.actions';
export function account():Account{const id=randomUUID().replaceAll('-','').slice(0,12);return {username:`account.${id}`,email:`account.${id}@example.com`,password:'AccountPassword2026!'};}
export async function seedAccount(){const user=account();const client=await request.newContext({baseURL:'http://web'});try{const response=await client.post('/api/auth/register',{data:user});if(!response.ok())throw new Error(await response.text());return {...user,...await response.json()};}finally{await client.dispose();}}
export async function database<T>(fn:(db:ReturnType<MongoClient['db']>)=>Promise<T>){
  if(process.env.ACCOUNT_ISOLATED!=='1' || process.env.E2E_BASE_URL!=='http://web')throw new Error('Account fixtures require the isolated Compose network');
  const client=new MongoClient('mongodb://mongo:27017');try{await client.connect();return await fn(client.db('account_20261009'));}finally{await client.close();}}
export async function mail(email:string,subject:string){return database(async db=>{const value=await db.collection('account_test_mail').findOne({to:email,subject},{sort:{created_at:-1}});if(!value?.link)throw new Error('Generated account mail missing');return new URL(value.link as string);});}
export async function expireVerification(id:string){await database(async db=>{await db.collection('users').updateOne({_id:new ObjectId(id)},{$set:{verification_expires:new Date(Date.now()-1000)}});});}
export async function allowVerification(id:string){await database(async db=>{await db.collection('users').updateOne({_id:new ObjectId(id)},{$unset:{verification_sent_at:''}});});}
