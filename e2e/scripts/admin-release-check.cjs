const {chromium}=require('playwright');
const fs=require('fs');
const path=require('path');
const output=process.env.ADMIN_CHECK_OUTPUT||'/results';fs.mkdirSync(output,{recursive:true});
if(process.env.E2E_BASE_URL!=='http://web'||process.env.H2H_ISOLATED!=='1')throw Error('Requires disposable Compose environment');
(async()=>{
 console.log('Launching headed zoom acceptance');
 const profile='/tmp/admin-followup-zoom';fs.mkdirSync(profile+'/Default',{recursive:true});
 fs.writeFileSync(profile+'/Default/Preferences',JSON.stringify({partition:{default_zoom_level:Math.log(2)/Math.log(1.2)}}));
 const extension='/tmp/admin-zoom-extension';fs.mkdirSync(extension,{recursive:true});
 fs.writeFileSync(extension+'/manifest.json',JSON.stringify({manifest_version:3,name:'Admin acceptance zoom',version:'1.0',permissions:['tabs'],background:{service_worker:'zoom.js'}}));
 fs.writeFileSync(extension+'/zoom.js','chrome.tabs.onUpdated.addListener((id,info,tab)=>{if(tab.url && tab.url.startsWith("http://web"))chrome.tabs.setZoom(id,2);});');
 const context=await chromium.launchPersistentContext(profile,{headless:false,viewport:null,ignoreDefaultArgs:['--disable-extensions'],args:['--window-size=1440,1000','--disable-extensions-except='+extension,'--load-extension='+extension],baseURL:'http://web'});
 const page=await context.newPage();const findings=[];
 console.log('Browser launched');page.setDefaultTimeout(10000);
 await context.request.post('/api/auth/login',{data:{email:process.env.E2E_ADMIN_EMAIL,password:process.env.E2E_ADMIN_PASSWORD}}).then(r=>{if(!r.ok())throw Error('Login failed '+r.status());});
 await page.goto('/admin');await page.getByTestId('admin-dashboard-page').waitFor();
 const worker=context.serviceWorkers()[0]||await context.waitForEvent('serviceworker',{timeout:5000});
 await worker.evaluate(async()=>{const tabs=await chrome.tabs.query({url:'http://web/*'});for(const tab of tabs)await chrome.tabs.setZoom(tab.id,2);});
 await page.waitForFunction(()=>devicePixelRatio>=1.9,null,{timeout:5000});
 const zoom=await page.evaluate(()=>({innerWidth,outerWidth,devicePixelRatio}));
 console.log('Zoom geometry '+JSON.stringify(zoom));
 if(zoom.devicePixelRatio<1.9||zoom.innerWidth>800)throw Error('Real browser 200% zoom was not applied: '+JSON.stringify(zoom));
 const tabs=await page.getByTestId('admin-sidebar-nav').getByRole('tab').evaluateAll(ns=>ns.map(n=>n.getAttribute('data-testid')));
 for(const tab of tabs){
  await page.getByTestId(tab).click();const panel=page.locator('[role="tabpanel"][data-state="active"]');await panel.waitFor();
  const geometry=await page.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth}));
  const buttons=panel.getByRole('button');const total=await buttons.count(),named=await panel.getByRole('button',{name:/\S/}).count(),unnamed=await panel.getByRole('button',{name:'',exact:true}).count();
  const unnamedMarkup=total===named?[]:await buttons.evaluateAll(ns=>ns.filter(n=>!n.textContent.trim()&&!n.getAttribute('aria-label')&&!n.getAttribute('aria-labelledby')).map(n=>n.outerHTML));
  findings.push({tab,zoom:200,geometry,overflow:geometry.scroll>geometry.width+1,buttons:total,namedButtons:named,unnamedButtons:unnamed,unnamedMarkup});
  console.log(tab+' checked');
 }
 await page.getByTestId('admin-tab-users').click();const opener=page.getByRole('button',{name:/^View details for/}).first();await opener.click();
 const drawer=page.getByRole('dialog',{name:'User detail',exact:true});await drawer.waitFor();
 await page.screenshot({path:path.join(output,'zoom-200-user-dialog.png'),fullPage:true});
 const dialogBounds=await drawer.boundingBox();await page.keyboard.press('Escape');await opener.waitFor();
 await page.waitForFunction(element=>element===document.activeElement,await opener.elementHandle(),{timeout:5000});
 const focusReturned=await opener.evaluate(n=>n===document.activeElement);
 fs.writeFileSync(path.join(output,'zoom-accessibility.json'),JSON.stringify({zoom,findings,dialogBounds,focusReturned,manualScreenReader:'Pending'},null,2));
 const endpoints=['/api/admin/platform/metrics','/api/admin/platform/users?page=1&limit=25','/api/admin/platform/keyword-filters'];
 const performance=[];
 for(const endpoint of endpoints){
  const warm=await context.request.get(endpoint);if(!warm.ok()){performance.push({endpoint,status:warm.status(),error:'Warmup rejected'});continue;}
  const samples=[];const statuses=[];const start=performanceNow();
  await Promise.all(Array.from({length:4},async()=>{for(let i=0;i<10;i++){const t=performanceNow();const r=await context.request.get(endpoint);samples.push(performanceNow()-t);statuses.push(r.status());await r.body();}}));
  samples.sort((a,b)=>a-b);performance.push({endpoint,requests:samples.length,concurrency:4,p50_ms:samples[19],p95_ms:samples[37],max_ms:samples.at(-1),elapsed_ms:performanceNow()-start,statuses:[...new Set(statuses)]});
 }
 fs.writeFileSync(path.join(output,'local-performance.json'),JSON.stringify({environment:'Disposable local Compose; newly seeded admin, no representative production dataset',method:'One warmup per endpoint; 40 requests each, four workers; headers latency includes local API path, not browser rendering',results:performance},null,2));
 if(findings.some(x=>x.overflow||x.unnamedButtons>0)||!focusReturned)throw Error('Zoom/accessibility acceptance failed; inspect zoom-accessibility.json');
 console.log(JSON.stringify({zoom,layoutFailures:findings.filter(x=>x.overflow),unnamed:findings.filter(x=>x.unnamedButtons>0),focusReturned,performance},null,2));await context.close();
})().catch(e=>{console.error(e);process.exit(1)});
function performanceNow(){return Number(process.hrtime.bigint())/1e6;}
