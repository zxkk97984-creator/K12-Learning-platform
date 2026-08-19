import { expect, test } from '@playwright/test'

// Phase 9 验收：语音偏好可保存并在刷新后回填。
test('设置页保存语音偏好并刷新保持', async ({ page, request }) => {
  const loginResponse = await request.post('/api/v1/auth/login', {
    data: { username: 'xiaoming', password: 'demo123' },
  })
  expect(loginResponse.ok()).toBeTruthy()
  const accessToken = (await loginResponse.json()).data.access_token
  await page.addInitScript((token) => {
    window.localStorage.setItem('shuangling-access-token', token)
  }, accessToken)

  await page.goto('/settings')
  const ttsSwitch = page.getByLabel('语音朗读开关')
  await expect(ttsSwitch).toBeVisible()

  await ttsSwitch.uncheck()
  await page.getByLabel('语音音量').fill('50')
  await page.getByLabel('语音语速').selectOption('1.5')
  await page.getByRole('button', { name: '保存设置' }).click()
  await expect(page.getByText('设置已保存')).toBeVisible()

  await page.reload()
  await expect(page.getByLabel('语音朗读开关')).not.toBeChecked()
  await expect(page.getByLabel('语音音量')).toHaveValue('50')
  await expect(page.getByLabel('语音语速')).toHaveValue('1.5')

  // 还原默认，避免影响其他 E2E（golden-path 需要语音输入按钮）。
  await page.getByLabel('语音输入开关').check()
  await page.getByLabel('语音朗读开关').check()
  await page.getByLabel('语音音量').fill('80')
  await page.getByLabel('语音语速').selectOption('1')
  await page.getByRole('button', { name: '保存设置' }).click()
  await expect(page.getByText('设置已保存')).toBeVisible()
})
