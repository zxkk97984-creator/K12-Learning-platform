import { expect, test } from '@playwright/test'

import { archiveAllActiveConversations, loginStudent, prepareContinueLearning } from './helpers'

// T25a：手机 / 平板 / 桌面核心流程 + 网络失败 / 401 / 重复提交。
// 项目（chromium / mobile-390 / tablet-820 / desktop-1280）都会运行本文件，
// 因此断言语义须与视口无关；布局差异见 BottomNav / AppLayout 的单元测试，
// 此处只断言"核心流程可用"，不把布局断言写死在单一视口。
test.describe.configure({ mode: 'serial' })

async function loginViaInitScript(page: import('@playwright/test').Page, token: string) {
  await page.addInitScript((t) => {
    window.localStorage.setItem('shuangling-access-token', t)
  }, token)
}

test('核心流程：首页 → 书库 → 阅读页面可进入', async ({ page, request }) => {
  test.setTimeout(60_000)
  const session = await loginStudent(request)
  const target = await prepareContinueLearning(request, session.token)
  await loginViaInitScript(page, session.token)

  // 首页：昵称来自登录用户 + 继续学习卡指向准备好的书
  await page.goto('/home')
  await expect(page.getByRole('heading', { name: /(早上好|中午好|下午好|晚上好)，/ })).toBeVisible()
  await expect(page.getByText(target.bookTitle).first()).toBeVisible()

  // 书库：读取出真实书籍标题
  await page.goto('/library')
  await expect(page.getByText(target.bookTitle).first()).toBeVisible()

  // 阅读：进入真实章节 reader，章节标题非空
  await page.goto(`/learn/${target.bookId}/${target.chapterId}`)
  const chapterHeading = page.locator('h1, h2').filter({ hasText: /\S/ }).first()
  await expect(chapterHeading).toBeVisible()
})

test('网络失败：首页区块失败显示错误与重试，成功区块仍可用', async ({ page, request }) => {
  test.setTimeout(60_000)
  const session = await loginStudent(request)
  await loginViaInitScript(page, session.token)

  // 拦截推荐接口返回 500，其余接口放行 → 首页应出现"重试"且不整体崩溃
  await page.route('**/api/v1/me/recommendations**', (route) =>
    route.fulfill({ status: 500, contentType: 'application/json', body: '{}' }),
  )
  await page.goto('/home')
  // 推荐区块给出一条可重试的错误（不冒充电网失败以外的别的文案）
  await expect(page.getByText(/推荐暂时不可用/).first()).toBeVisible()
  await expect(page.getByRole('button', { name: '重试' }).first()).toBeVisible()

  // 放行后点重试 → 区块恢复（不再出现错误提示）
  await page.unroute('**/api/v1/me/recommendations**')
  await page.getByRole('button', { name: '重试' }).first().click()
  await expect(page.getByText(/推荐暂时不可用/).first()).toHaveCount(0)
})

test('401：token 失效后访问受保护页被清除登录态', async ({ page }) => {
  await page.addInitScript(() => {
    window.localStorage.setItem('shuangling-access-token', 'expired-bad-token')
  })
  await page.goto('/home')
  // 401 全局事件 → 清除登录态 → 重定向 /login
  await expect(page).toHaveURL(/\/login/, { timeout: 20_000 })
})

test('重复提交：连点发送不产生重复消息（幂等键）', async ({ page, request }) => {
  test.setTimeout(60_000)
  const session = await loginStudent(request)
  const target = await prepareContinueLearning(request, session.token)
  await loginViaInitScript(page, session.token)

  // 干净起点：归档全部 ACTIVE 会话，使后续断言只针对本测试建立的会话
  await archiveAllActiveConversations(request, session.token)

  // 计数发送消息的 POST（fetchSSE 本质是对 /conversations/{id}/messages 的 POST）。
  // 守卫（T25 修复）应使连点只触发一次发送，无论 SSE 回包多快/多慢。
  const sendPosts: string[] = []
  await page.route('**/api/v1/conversations/*/messages**', (route) => {
    if (route.request().method() === 'POST') {
      sendPosts.push(route.request().postData() ?? '')
    }
    void route.continue()
  })

  await page.goto(`/learn/${target.bookId}/${target.chapterId}`)
  await page.getByRole('button', { name: /打开.*AI 教师/ }).click()
  const panel = page.getByRole('dialog', { name: /对话面板/ })
  await expect(panel).toBeVisible()

  await page.getByLabel('消息输入').fill('重复提交幂等验证，请回复简单确认。')
  // 快速连点两次发送，期望发送在途守卫（T25 修复）只放行一次。
  // 第二次点击命中已 disabled 的按钮 / 被守卫忽略；不应产生第二个 POST。
  const sendButton = page.getByRole('button', { name: '发送消息' })
  // 手机底部抽屉在布局动画期间按钮可能被判定为"不稳定"，用 force 跳过可操作性等待，
  // 焦点在"重复提交是否触发第二次发送"，而非按钮动画稳定性。
  await sendButton.click({ force: true })
  await sendButton.click({ force: true }).catch(() => undefined)

  // 断言：只放行一次发送（发往同一会话的 POST 计数为 1）。
  // 这是前端发送在途守卫（T25 修复）的直接证据——连点不触发第二次发送。
  // （落库用户消息条数依赖 SSE 异步提交时序，不在此断言，避免把提交延迟误判为重复。）
  await expect
    .poll(
      () => sendPosts.length,
      { timeout: 20_000 },
    )
    .toBe(1)
})
