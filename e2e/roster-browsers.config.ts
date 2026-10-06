const {defineConfig,devices}=require("@playwright/test");module.exports=defineConfig({testDir:"./tests",workers:1,retries:0,timeout:45000,use:{baseURL:"http://web"},projects:[{name:"firefox",use:{...devices["Desktop Firefox"]}},{name:"webkit",use:{...devices["Desktop Safari"]}}]});

export {};
