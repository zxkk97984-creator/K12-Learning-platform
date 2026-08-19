import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  fullyParallel: false,
  // 串行：E2E 共享同一 seed 账号 + 真实 DB（golden-path 出题 / memory-flow 操作记忆），
  // 并行会互相踩数据（.last() 卡片定位、FORGET 状态竞争）
  workers: 1,
  reporter: [['list']],
  use: {
    baseURL: 'http://localhost:5175',
    headless: true,
    trace: 'retain-on-failure',
  },
  webServer: {
    command: 'pnpm exec vite --port 5175 --strictPort',
    url: 'http://localhost:5175',
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
})
