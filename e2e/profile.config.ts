import { defineConfig, devices } from '@playwright/test';
export default defineConfig({testDir:'./tests',testMatch:'profile-*.spec.ts',fullyParallel:false,
  workers:1,retries:0,timeout:45000,reporter:'list',
  use:{baseURL:process.env.E2E_BASE_URL || 'http://web',trace:'on',screenshot:'only-on-failure'},
  projects:[{name:'chromium',use:{...devices['Desktop Chrome']}},
    {name:'firefox',use:{...devices['Desktop Firefox']}},{name:'webkit',use:{...devices['Desktop Safari']}}]});
