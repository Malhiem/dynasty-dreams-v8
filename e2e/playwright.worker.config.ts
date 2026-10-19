import {defineConfig,devices} from '@playwright/test';
if(process.env.E2E_BASE_URL!=='http://web'||process.env.H2H_ISOLATED!=='1')throw Error('Worker checks require disposable E2E Compose stack');
process.env.MOBILE_WORKER_BROWSER_ISOLATED='1';
export default defineConfig({testDir:'./tests',testMatch:'mobile-worker-browser.spec.ts',workers:1,retries:0,timeout:90000,
 use:{baseURL:'http://localhost:8080',trace:'retain-on-failure',screenshot:'only-on-failure'},
 projects:[{name:'chromium-controlled-worker',use:{...devices['Pixel 7']}}],
 webServer:{command:'node scripts/service-worker-loopback.cjs',cwd:__dirname,url:'http://localhost:8080/health',reuseExistingServer:false,timeout:30000},
});
