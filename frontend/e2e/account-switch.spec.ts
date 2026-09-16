import { expect, test, type Page } from '@playwright/test'

// T25a：跨账号切换清理与异步隔离（E2E 层）。
// 使用两个独立 seed 账号：xiaoming（STUDENT）+ admin（ADMIN）。
// 通过真实登录表单在两个账号间切换（addInitScript 是粘性的——每次导航都会重放，
// 无法用于中途切换身份），验证无跨账号状态残留。断言与视口无关。
test.describe.configure({ mode: 'serial' })

async function loginViaForm(page: Page, username: string, password: string) {
  await page.goto('/login')
  await page.getByLabel('用户名').fill(username)
  await page.getByLabel('密码').fill(password)
  await page.getByRole('button', { name: '登录' }).click()
  await expect(page).toHaveURL(/\/home/)
}

// 昵称在 <768px 按 T17 §5.2 隐藏（md:inline），≥768px 显示。
// 断言"是否可见"按视口宽度分支，避免把响应式隐藏误判为泄漏。
function expectNickname(page: Page, nickname: string, visible: boolean) {
  const el = page.getByText(nickname).first()
  return expect(el)[visible ? 'toBeVisible' : 'toBeHidden']()
}

// 管理入口在顶部导航 <768px 隐藏（md:flex 主导航）；学生永远无此入口（count 0）。
// 管理员：桌面可见；手机隐藏（但仍可从 /admin 直达）。断言按视口分支。
function expectAdminNav(page: Page, isAdmin: boolean) {
  const el = page.getByRole('link', { name: '管理' })
  if (!isAdmin) return expect(el).toHaveCount(0)
  const mobile = (page.viewportSize()?.width ?? 1280) < 768
  return expect(el)[mobile ? 'toBeHidden' : 'toBeVisible']()
}

test('学生→管理员切换：无跨账号状态残留', async ({ page }) => {
  test.setTimeout(90_000)
  const mobile = (page.viewportSize()?.width ?? 1280) < 768

  // 1. 学生真实登录：首页显示学生昵称"小明"，不出现"管理"入口
  await loginViaForm(page, 'xiaoming', 'demo123')
  await expect(page.getByRole('heading', { name: /(早上好|中午好|下午好|晚上好)，/ })).toBeVisible()
  await expectNickname(page, '小明', !mobile)
  await expectAdminNav(page, false)

  // 2. 通过 UI 退出（触发 reset 清理 store / 异步隔离）
  await page.getByRole('button', { name: '退出登录' }).click()
  await expect(page).toHaveURL(/\/login/)

  // 3. 管理员真实登录：显示管理员身份，不泄漏学生昵称"小明"
  await loginViaForm(page, 'admin', 'admin123')
  await expect(page.getByRole('heading', { name: /(早上好|中午好|下午好|晚上好)，/ })).toBeVisible()
  await expectAdminNav(page, true)
  // 管理员身份不应出现学生昵称"小明"（任何视口都不得泄漏）
  await expect(page.getByText('小明').first()).toHaveCount(0)

  // 4. 管理员可进入后台（权限属管理员）
  await page.goto('/admin')
  await expect(page.getByRole('heading', { name: '平台维护' })).toBeVisible()
})

test('管理员→学生切换：管理导航消失，学生主界面恢复', async ({ page }) => {
  test.setTimeout(90_000)
  const mobile = (page.viewportSize()?.width ?? 1280) < 768

  // 1. 管理员登录：可见"管理"入口（桌面）或隐藏（手机导航）
  await loginViaForm(page, 'admin', 'admin123')
  await expectAdminNav(page, true)

  // 2. 退出 → 切换学生
  await page.getByRole('button', { name: '退出登录' }).click()
  await expect(page).toHaveURL(/\/login/)
  await loginViaForm(page, 'xiaoming', 'demo123')

  // 3. 学生身份：不再有"管理"入口，能看到学生昵称
  await expect(page.getByRole('heading', { name: /(早上好|中午好|下午好|晚上好)，/ })).toBeVisible()
  await expectAdminNav(page, false)
  await expectNickname(page, '小明', !mobile)

  // 4. 学生访问 /admin 被拒绝（403 守卫，不显示后台）
  await page.goto('/admin')
  await expect(page.getByText(/仅管理员可访问/)).toBeVisible()
})
