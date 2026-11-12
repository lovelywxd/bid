import {defineConfig} from '@playwright/test';
export default defineConfig({
  testDir:'./tests', fullyParallel:false, workers:1, timeout:30000,
  expect:{timeout:15000}, reporter:[['list'],['json',{outputFile:'../evals/results/stage1/browser-results.json'}]],
  use:{baseURL:'http://127.0.0.1:8765', headless:true, viewport:{width:1440,height:1000},
    launchOptions:{executablePath:process.env.BID_CHROME_PATH??'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'},
    trace:'retain-on-failure', screenshot:'only-on-failure'},
});
