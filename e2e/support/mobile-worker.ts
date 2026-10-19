import type {Page} from '@playwright/test';
export async function controlledWorker(page:Page){
 return page.evaluate(async()=>{
  if(!window.isSecureContext||!('serviceWorker' in navigator))return false;
  await navigator.serviceWorker.ready;
  if(!navigator.serviceWorker.controller)await new Promise<void>(resolve=>navigator.serviceWorker.addEventListener('controllerchange',()=>resolve(),{once:true}));
  return !!navigator.serviceWorker.controller;
 });
}
export async function legacyPrivateCache(page:Page,url:string){
 await page.evaluate(async path=>{const cache=await caches.open('dd-api-v1');await cache.put(path,new Response(JSON.stringify({private_marker:'previous-account-data'}),{headers:{'Content-Type':'application/json'}}));},url);
}
export async function readFromPage(page:Page,url:string){return page.evaluate(async path=>{const response=await fetch(path,{credentials:'include'});return {status:response.status,body:await response.text(),type:response.headers.get('content-type')};},url);}
export async function purgePrivateCache(page:Page){await page.evaluate(()=>navigator.serviceWorker.controller!.postMessage({type:'PURGE_API_CACHE'}));}
export async function privateCacheNames(page:Page){return page.evaluate(async()=>(await caches.keys()).filter(name=>name.startsWith('dd-api-')));}
export async function staleHtml(page:Page){await page.evaluate(async()=>{const name=(await caches.keys()).find(name=>name.startsWith('dd-shell-'));if(!name)throw Error('Missing worker shell cache');await(await caches.open(name)).put('/',new Response('<!doctype html><title>stale cached build</title>',{headers:{'Content-Type':'text/html'}}));});}
