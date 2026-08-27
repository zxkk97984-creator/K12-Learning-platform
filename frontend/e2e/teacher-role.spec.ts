import { expect, test } from '@playwright/test'

import { loginStudent } from './helpers'

// Phase 5-B-II：使用 seed 真实风格名「温暖鼓励」「严谨清晰」；
// 断言切换后刷新保持，并可切回。
test('设置页切换教师风格并刷新保持，可切回', async ({ page, request }) => {
  const { token } = await loginStudent(request)
  await page.addInitScript((t) => {
    window.localStorage.setItem('shuangling-access-token', t)
  }, token)

  await page.goto('/settings')
  await expect(page.getByRole('heading', { name: 'AI 教师风格' })).toBeVisible()

  const warmCard = page.locator('button').filter({ hasText: '温暖鼓励' }).first()
  const strictCard = page.locator('button').filter({ hasText: '严谨清晰' }).first()
  await expect(warmCard).toBeVisible()
  await expect(strictCard).toBeVisible()

  // 切到「严谨清晰」→ aria-pressed 生效 → 刷新后保持
  await strictCard.click()
  await expect(strictCard).toHaveAttribute('aria-pressed', 'true', { timeout: 10_000 })
  await page.reload()
  const strictAfterReload = page.locator('button').filter({ hasText: '严谨清晰' }).first()
  await expect(strictAfterReload).toHaveAttribute('aria-pressed', 'true')

  // 切回「温暖鼓励」→ 刷新保持
  const warmAfterReload = page.locator('button').filter({ hasText: '温暖鼓励' }).first()
  await warmAfterReload.click()
  await expect(warmAfterReload).toHaveAttribute('aria-pressed', 'true')
  await page.reload()
  await expect(
    page.locator('button').filter({ hasText: '温暖鼓励' }).first(),
  ).toHaveAttribute('aria-pressed', 'true')
})
