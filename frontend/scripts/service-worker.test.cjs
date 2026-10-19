const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const source=fs.readFileSync(process.argv[2]||path.join(__dirname,'../public/service-worker.js'),'utf8');
const origin='https://mobile.example.test';
function harness(){
 const stores=new Map(),listeners={},pending=[];
 const version=source.match(/const SW_VERSION = "([^"]+)"/)[1];
 const normalize=r=>typeof r==='string'?new URL(r,origin).href:r.url;
 const caches={async keys(){return [...stores.keys()];},async delete(k){return stores.delete(k);},async open(name){
  if(!stores.has(name))stores.set(name,new Map());const store=stores.get(name);
  return {async match(r){return store.get(normalize(r))?.clone();},async put(r,v){store.set(normalize(r),v.clone());},async addAll(urls){for(const u of urls)store.set(normalize(u),new Response('preload'));}};
 }};
 const h={listeners,caches,version,fetch:async()=>new Response('fresh',{headers:{'content-type':'text/html'}})};
 const self={location:new URL(origin),clients:{claim:async()=>{}},skipWaiting:async()=>{},addEventListener:(name,callback)=>listeners[name]=callback};
 vm.runInNewContext(source,{self,caches,URL,Response,fetch:(r,options)=>h.fetch(r,options)});
 h.dispatch=(name,extra={})=>{let response;listeners[name]({waitUntil:p=>pending.push(p),respondWith:p=>response=Promise.resolve(p),...extra});return response;};
 h.settle=async()=>{while(pending.length)await Promise.all(pending.splice(0));};
 return h;
}
test('private API reads and writes always reach the network',async()=>{
 const h=harness();
 for(const [url,method] of [['/api/teams/alpha','GET'],['/api/leagues/alpha/standings','GET'],['/api/matchups/alpha','GET'],['/api/players','GET'],['/api/chat/messages','GET'],['/api/drafts/alpha/pick','POST']]){
  assert.equal(h.dispatch('fetch',{request:{url:origin+url,method,mode:'cors'}}),undefined,`${method} ${url} must not use a worker cache`);
 }
});
test('navigation fetches current HTML instead of returning a stale build',async()=>{
 const h=harness();await(await h.caches.open(`dd-shell-${h.version}`)).put('/',new Response('old build'));
 const response=await h.dispatch('fetch',{request:{url:origin+'/',method:'GET',mode:'navigate',destination:'document'}});
 assert.equal(await response.text(),'fresh');await h.settle();
});
test('offline navigation can use the shell but missing assets never receive HTML',async()=>{
 const h=harness();h.fetch=async()=>{throw Error('offline');};
 await(await h.caches.open(`dd-shell-${h.version}`)).put('/',new Response('<html>shell</html>',{headers:{'content-type':'text/html'}}));
 const nav=await h.dispatch('fetch',{request:{url:origin+'/dashboard',method:'GET',mode:'navigate',destination:'document'}});
 assert.equal(await nav.text(),'<html>shell</html>');
 const asset=await h.dispatch('fetch',{request:{url:origin+'/static/js/missing.js',method:'GET',mode:'cors',destination:'script'}});
 assert.equal(asset.status,504);assert.doesNotMatch(asset.headers.get('content-type')||'',/html/);
});
test('activation removes legacy private caches and preserves unrelated origin caches',async()=>{
 const h=harness();for(const name of ['dd-api-v1','dd-api-v2','dd-shell-v1','other-application-cache',`dd-shell-${h.version}`])await h.caches.open(name);
 h.dispatch('activate');await h.settle();
 assert.deepEqual((await h.caches.keys()).sort(),[`dd-shell-${h.version}`,'other-application-cache'].sort());
});
test('hashed assets remain available offline after being cached',async()=>{
 const h=harness();const request={url:origin+'/static/js/main.abc123.js',method:'GET',mode:'cors',destination:'script'};
 h.fetch=async()=>new Response('bundle',{headers:{'content-type':'application/javascript'}});
 const first=await h.dispatch('fetch',{request});assert.equal(await first.text(),'bundle');await h.settle();
 h.fetch=async()=>{throw Error('offline');};
 const cached=await h.dispatch('fetch',{request});assert.equal(await cached.text(),'bundle');
});
