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
  const gradeSelect = page.getByLabel('年级', { exact: true })
  const initialValue = await gradeSelect.inputValue()
  const targetValue = initialValue === '9' ? '8' : '9'

  // 改为另一档 → 保存 → toast
  await gradeSelect.selectOption(targetValue)
  await page.getByRole('button', { name: '保存设置' }).click()
  await expect(page.getByText('设置已保存')).toBeVisible()

  // 刷新持久：值切换为目标档位
  await page.reload()
  await expect(page.getByLabel('年级', { exact: true })).toHaveValue(targetValue)

  // 刷新持久断言完成后，统一还原为 8（seed 基线），避免影响后端单测
  if (targetValue !== '8') {
    await page.getByLabel('年级', { exact: true }).selectOption('8')
    await page.getByRole('button', { name: '保存设置' }).click()
    await expect(page.getByText('设置已保存')).toBeVisible()
  }
  await page.reload()
  await expect(page.getByLabel('年级', { exact: true })).toHaveValue('8')
})
