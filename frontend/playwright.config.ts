import { defineConfig } from '@playwright/test';
import { existsSync } from 'node:fs';
const chrome = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
export default defineConfig({
  testDir: './tests',
  metadata: { atlasTest: process.env.BAYFLOW_TEST_ATLAS === '1' || process.argv.some(argument => argument.includes('official Atlas')) },
  timeout: 120000,
  expect: { timeout: 30000 },
  workers: 1,
  reporter: 'list',
  use: {
    baseURL: process.env.BAYFLOW_UI_URL || 'http://127.0.0.1:5175',
    headless: true,
    viewport: { width: 1440, height: 1100 },
    launchOptions: existsSync(chrome) ? { executablePath: chrome } : {},
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
});
