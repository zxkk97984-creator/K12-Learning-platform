import { defineConfig, devices } from '@playwright/test'

// T25a：手机视口项目（390/820/1280）+ 桌面。失败保留 trace/screenshot。
// E2E 共享同一 seed 账号 + 真实 DB（golden-path 出题 / memory-flow 操作记忆），
// 并行会互相踩数据（.last() 卡片定位、FORGET 状态竞争），故限制并发为串行。
export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  fullyParallel: false,
  workers: 1,
  reporter: [['list']],
  // T25a：trace/screenshot 在失败时保留，配合 CI 上传 artifact 便于定位。
  use: {
    baseURL: 'http://localhost:5175',
    headless: true,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  webServer: {
    command: 'pnpm exec vite --port 5175 --strictPort',
    url: 'http://localhost:5175',
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
  },
  projects: [
    // 桌面（既有 golden-path / admin / memory 等项目）——跑全部 specs。
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
    // T25a：手机 / 平板核心流程在 390 / 820 / 1280 下回归。
    // 390 ≤ <820：底部四项导航（首页/学习/练习/成长）。
    // 820–1099：保留四项导航，隐藏非必要昵称长文本；课程左目录 180px。
    // ≥1280：桌面布局。
    // 视口敏感断言集中在 viewport-portable specs（mobile-learning / account-switch），
    // 既有桌面 specs（golden-path 依赖顶部导航"测验"等）只在 chromium 项目跑，
    // 避免手机视口下因顶部导航隐藏而误报。
    // 全部基于 chromium（CI 只装 chromium），因此显式 browserName + isMobile/hasTouch，
    // 不依赖 device 描述符（其 defaultBrowserType 可能指向未安装的 webkit）。
    {
      name: 'mobile-390',
      testMatch: /(mobile-learning|account-switch)\.spec\.ts/,
      use: {
        ...devices['iPhone 12'],
        browserName: 'chromium',
        viewport: { width: 390, height: 844 },
      },
    },
    {
      name: 'tablet-820',
      testMatch: /(mobile-learning|account-switch)\.spec\.ts/,
      use: {
        ...devices['iPad Mini'],
        browserName: 'chromium',
        viewport: { width: 820, height: 1180 },
      },
    },
    {
      name: 'desktop-1280',
      testMatch: /(mobile-learning|account-switch)\.spec\.ts/,
      use: {
        ...devices['Desktop Chrome'],
        viewport: { width: 1280, height: 800 },
      },
    },
  ],
})
