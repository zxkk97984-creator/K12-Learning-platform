import { expect, test } from '@playwright/test'

test('管理员可进入管理后台并看到统计/书籍/知识库', async ({ page, request }) => {
  const loginResponse = await request.post('/api/v1/auth/login', {
    data: { username: 'admin', password: 'admin123' },
  })
  expect(loginResponse.ok()).toBeTruthy()
  const accessToken = (await loginResponse.json()).data.access_token
  await page.addInitScript((token) => {
    window.localStorage.setItem('shuangling-access-token', token)
  }, accessToken)

  await page.goto('/admin')
  await expect(page.getByRole('heading', { name: '平台维护' })).toBeVisible()
  await expect(page.getByRole('link', { name: '管理' })).toBeVisible()
  await expect(page.getByText('书籍总数')).toBeVisible()

  await page.getByRole('link', { name: '书籍' }).click()
  await expect(page.getByRole('heading', { name: '新建书籍' })).toBeVisible()
  await expect(page.getByLabel('书名')).toBeVisible()

  await page.getByRole('link', { name: '知识库' }).click()
  await expect(page.getByRole('heading', { name: '上传知识资源' })).toBeVisible()
  await expect(page.getByLabel('选择文件')).toBeVisible()
  await expect(page.getByLabel('来源名称')).toBeVisible()
})
