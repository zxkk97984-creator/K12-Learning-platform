import { expect, test } from '@playwright/test'

// Phase 2 验收：登录 / 跳回 / 刷新保持 / 退出（需后端 + vite proxy）
test('登录流完整闭环', async ({ page }) => {
  // 干净状态：清 token 后刷新
  await page.goto('/login')
  await page.evaluate(() => window.localStorage.removeItem('shuangling-access-token'))
  await page.reload()

  // 1. 访问受保护页 → 重定向 /login（记住原目标）
  await page.goto('/profile')
  await expect(page).toHaveURL(/\/login/)

  // 2. 登录 → 跳回原目标
  await page.getByLabel('用户名').fill('xiaoming')
  await page.getByLabel('密码').fill('demo123')
  await page.getByRole('button', { name: '登录' }).click()
  await expect(page).toHaveURL(/\/profile/)
  await expect(page.getByRole('heading', { name: '霜铃眼中的你。' })).toBeVisible()

  // 3. 刷新保持登录
  await page.reload()
  await expect(page.getByRole('heading', { name: '霜铃眼中的你。' })).toBeVisible()

  // 4. 退出 → /login；再访问受保护页仍跳 /login
  await page.getByRole('button', { name: '退出登录' }).click()
  await expect(page).toHaveURL(/\/login/)
  await page.goto('/settings')
  await expect(page).toHaveURL(/\/login/)
})
