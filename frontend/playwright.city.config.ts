import { defineConfig } from '@playwright/test';
import { fileURLToPath } from 'node:url';
import base from './playwright.config';
const projectRoot=fileURLToPath(new URL('..',import.meta.url));
const frontendRoot=fileURLToPath(new URL('.',import.meta.url));
export default defineConfig({
 ...base,
 metadata:{atlasTest:false},
 timeout:180000,
 use:{...base.use,baseURL:'http://127.0.0.1:5180'},
 webServer:[
  {command:'./.venv/bin/python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8010',cwd:projectRoot,url:'http://127.0.0.1:8010/scenarios',env:{BAYFLOW_OFFLINE:'1'},reuseExistingServer:false,timeout:60000},
  {command:'npm run dev -- --port 5180 --strictPort',cwd:frontendRoot,url:'http://127.0.0.1:5180',env:{BAYFLOW_API_URL:'http://127.0.0.1:8010'},reuseExistingServer:false,timeout:60000},
 ],
});
