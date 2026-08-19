import { expect, test } from '@playwright/test'

// Phase 2 验收「Grade 修改持久」：设置页改 grade → 保存 → 刷新后仍生效（真实后端）
test('设置页 grade 修改持久化', async ({ page, request }) => {
  const loginResponse = await request.post('/api/v1/auth/login', {
    data: { username: 'xiaoming', password: 'demo123' },
  })
  expect(loginResponse.ok()).toBeTruthy()
  const accessToken = (await loginResponse.json()).data.access_token
  await page.addInitScript((token) => {
    window.localStorage.setItem('shuangling-access-token', token)
  }, accessToken)

  await page.goto('/settings')
  const gradeSelect = page.getByLabel('年级（1~12）')
  await expect(gradeSelect).toHaveValue('8')

  // 改为 9 → 保存 → toast
  await gradeSelect.selectOption('9')
  await page.getByRole('button', { name: '保存设置' }).click()
  await expect(page.getByText('设置已保存')).toBeVisible()

  // 刷新持久
  await page.reload()
  await expect(page.getByLabel('年级（1~12）')).toHaveValue('9')

  // 还原为 8，保持 seed 数据干净
  await page.getByLabel('年级（1~12）').selectOption('8')
  await page.getByRole('button', { name: '保存设置' }).click()
  await expect(page.getByText('设置已保存')).toBeVisible()
  await page.reload()
  await expect(page.getByLabel('年级（1~12）')).toHaveValue('8')
})
