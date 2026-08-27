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
  // Phase 5-B-II：AdminLayout 导航现为 总览/书籍/知识库/教师风格/章节内容
  await expect(page.getByRole('link', { name: '总览' })).toBeVisible()
  await expect(page.getByText('书籍总数')).toBeVisible()

  await page.getByRole('link', { name: '书籍' }).click()
  await expect(page.getByRole('heading', { name: '新建书籍' })).toBeVisible()
  await expect(page.getByLabel('书名')).toBeVisible()

  await page.getByRole('link', { name: '知识库' }).click()
  await expect(page.getByRole('heading', { name: /上传知识资源/ })).toBeVisible()
  const fileInput = page.locator('input[type="file"]')
  await expect(fileInput).toHaveAttribute('accept', /.pdf/)
  await expect(page.getByLabel('来源名称')).toBeVisible()
})
