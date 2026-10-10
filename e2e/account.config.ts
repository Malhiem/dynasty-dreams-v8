import { defineConfig, devices } from '@playwright/test';
export default defineConfig({testDir:'./tests',testMatch:'account-management.spec.ts',workers:1,fullyParallel:false,retries:0,timeout:45000,
  use:{baseURL:'http://web',trace:'on',screenshot:'only-on-failure'},
  projects:[{name:'chromium',use:{...devices['Desktop Chrome']}},{name:'firefox',use:{...devices['Desktop Firefox']}},{name:'webkit',use:{...devices['Desktop Safari']}}]});
