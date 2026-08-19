import { expect, test } from '@playwright/test'

// 黄金路径（总控 §10.8）：Home → Reader → Companion → 对话 → Mock Quiz → 答题 → History → Profile
test.describe('黄金路径', () => {
  let accessToken = ''

  test.beforeAll(async ({ request }) => {
    // 2-E：受保护路由需登录；用后端 seed 账号换取 token 注入（需后端 + vite proxy 可用）
    const response = await request.post('/api/v1/auth/login', {
      data: { username: 'xiaoming', password: 'demo123' },
    })
    expect(response.ok()).toBeTruthy()
    accessToken = (await response.json()).data.access_token
  })

  test('完整学习闭环', async ({ page }) => {
    await page.addInitScript((token) => {
      window.localStorage.setItem('shuangling-access-token', token)
    }, accessToken)

    // 1. 首页加载
    await page.goto('/home')
    await expect(page.getByRole('heading', { name: '晚上好，小明。' })).toBeVisible()
    await expect(page.getByRole('button', { name: '继续学习 →' }).first()).toBeVisible()

    // 2. 继续学习 → reader
    await page.getByRole('button', { name: '继续学习 →' }).first().click()
    await expect(page).toHaveURL(/\/learn\/b1\/ch3/)
    await expect(page.getByRole('heading', { name: '训练数据', level: 1 })).toBeVisible()

    // 3. 打开 companion
    await page.getByRole('button', { name: '打开霜铃 AI 教师' }).click()
    await expect(page.getByRole('complementary', { name: '霜铃对话面板' })).toBeVisible()

    // 4. 发送消息 → 流式 AI 回复
    await page.getByLabel('消息输入').fill('那它为什么会出错？')
    await page.getByRole('button', { name: '发送消息' }).click()
    await expect(page.getByText(/因为当前这节内容会影响机器之后看到的新情况/)).toBeVisible({
      timeout: 10_000,
    })

    // 5. 触发 quiz → tool 状态 → quiz 卡
    await page.getByRole('button', { name: '给我出题' }).first().click()
    await expect(page.getByText('Quiz Skill 已创建 · 正式测验已记录')).toBeVisible({
      timeout: 10_000,
    })
    await expect(page.getByRole('button', { name: /让机器从例子中发现可重复的规律/ })).toBeVisible({
      timeout: 10_000,
    })

    // 6. 答题：选 B + 提交 → ✓ 已完成
    await page.getByRole('button', { name: /让机器从例子中发现可重复的规律/ }).click()
    await page.getByRole('button', { name: '提交答案' }).click()
    await expect(page.getByText('✓ 已完成')).toBeVisible({ timeout: 10_000 })

    // 7. 去 quizzes：历史列表含随堂测验（q-live）
    await page.keyboard.press('Escape')
    await page.getByRole('link', { name: '测验' }).click()
    await expect(page.getByRole('heading', { name: '每一次答题，都会留下线索。' })).toBeVisible()
    await expect(page.getByText('训练数据 · 随堂测验')).toBeVisible()

    // 8. 去 profile：画像页
    await page.getByRole('link', { name: '成长' }).click()
    await expect(page.getByRole('heading', { name: '霜铃眼中的你。' })).toBeVisible()
  })
})
