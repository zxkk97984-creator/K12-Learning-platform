import { expect, test } from '@playwright/test'

import { loginStudent } from './helpers'

/**
 * CodeLab 真实浏览器闭环：
 *   进入 CodeLab → 查看任务 → 编辑代码 → 运行 → 查看输出 → 请求 AI 评价 → 查看反馈
 *
 * 这条 spec 走真实后端（含真实 Docker 沙箱）。AI 部分在 E2E 中固定使用
 * `AI_PROVIDER=mock`（见 scripts/ci-e2e.sh），因此不消耗真实模型额度，
 * 但**除模型本身之外的链路全部是真实的**：真实登录、真实任务、真实沙箱执行、
 * 真实确定性判题、真实校验与合并逻辑。
 */

/**
 * 刻意使用「无缩进」写法。
 *
 * CodeMirror 的 Python 语言支持会在回车时自动缩进（这是学生真正需要的功能），
 * 而 Playwright 的逐字符输入会在自动缩进之上再叠加我们自己输入的缩进，
 * 产生缩进错误。用单行函数体即可绕开这一点 —— 这与学生手动敲代码的体验无关，
 * 纯粹是自动化输入的产物。
 */
const CORRECT_CODE = [
  'def celsius_to_fahrenheit(celsius): return celsius * 9 / 5 + 32',
  'print(celsius_to_fahrenheit(100))',
].join('\n')

const TASK_TITLE = '温度换算：摄氏度转华氏度'

test.beforeEach(async ({ page, request }) => {
  // 与 golden-path 同一约定：先用真实 API 拿 token，再注入 localStorage
  const session = await loginStudent(request)
  await page.addInitScript((token) => {
    window.localStorage.setItem('shuangling-access-token', token)
  }, session.token)
})

/** 打开温度换算任务并返回编辑器可编辑区域。 */
async function openTask(page: import('@playwright/test').Page) {
  await page.goto('/codelab')
  await page.getByRole('link').filter({ hasText: TASK_TITLE }).click()
  await expect(page.getByRole('button', { name: '运行' })).toBeVisible()
}

/** 用键盘全选替换编辑器内容，并确认内容真的写进去了。 */
async function replaceCode(page: import('@playwright/test').Page, code: string) {
  await openTask(page)
  const editor = page.getByRole('textbox', { name: '代码编辑器' })
  await editor.click()
  await page.keyboard.press('ControlOrMeta+A')
  await page.keyboard.press('Backspace')
  await page.keyboard.type(code, { delay: 5 })
  // CodeMirror 是内容可编辑的，必须断言内容已就位，否则运行的是残留的初始代码
  await expect(editor).toContainText(code.split('\n')[0])
}

test.describe('CodeLab 编程练习', () => {
  test('从任务列表进入工作台', async ({ page }) => {
    await page.goto('/codelab')

    await expect(page.getByRole('heading', { name: '编程练习' })).toBeVisible()
    const cards = page.getByTestId('codelab-task-list').getByRole('link')
    await expect(cards.first()).toBeVisible()

    await cards.first().click()
    // 工作台应同时出现题目、编辑器容器与运行按钮
    await expect(page.getByRole('button', { name: '运行' })).toBeVisible()
    await expect(page.getByTestId('codelab-editor')).toBeVisible()
  })

  test('编辑代码 → 运行 → 看到真实沙箱输出', async ({ page }) => {
    test.setTimeout(90_000)
    await replaceCode(page, CORRECT_CODE)

    await page.getByRole('button', { name: '运行' }).click()

    // 真实沙箱输出：print 的结果必须出现在运行结果区
    await expect(page.getByTestId('codelab-output-panel')).toBeVisible({ timeout: 30_000 })
    await expect(page.getByTestId('codelab-output-stdout')).toContainText('212', {
      timeout: 30_000,
    })
    await expect(page.getByTestId('codelab-output-panel')).toContainText('运行成功')
  })

  test('语法错误给出可读的报错，而不是崩溃', async ({ page }) => {
    test.setTimeout(90_000)
    // 单行语法错误，同样避免自动缩进干扰
    await replaceCode(page, 'def f(x) return x')

    await page.getByRole('button', { name: '运行' }).click()

    // 一次性沙箱把 Python 的 traceback 作为 stderr 流返回（不是独立的 error 帧），
    // 这与后端契约一致；面板把这行 stderr 用警示样式渲染，并在状态行标注「运行出错」。
    await expect(page.getByTestId('codelab-output-stderr')).toContainText('SyntaxError', {
      timeout: 30_000,
    })
    await expect(page.getByTestId('codelab-output-panel')).toContainText('运行出错')
  })

  test('运行后可请求 AI 评价并看到分维度反馈', async ({ page }) => {
    test.setTimeout(180_000)
    await replaceCode(page, CORRECT_CODE)

    await page.getByRole('button', { name: '运行' }).click()
    await expect(page.getByTestId('codelab-output-stdout')).toContainText('212', {
      timeout: 30_000,
    })

    // AI 评价按钮在运行前禁用，运行后可用
    const reviewButton = page.getByRole('button', { name: /请 AI 评价/ })
    await expect(reviewButton).toBeEnabled()
    await reviewButton.click()

    const panel = page.getByTestId('codelab-review-panel')
    await expect(panel).toBeVisible({ timeout: 120_000 })
    // 正确性由自动测试决定
    await expect(panel).toContainText('已通过自动测试')
    // 四个维度都要出现
    await expect(panel).toContainText('功能正确性（自动测试）')
    await expect(panel).toContainText('算法思路（AI 评价）')
    await expect(panel).toContainText('代码质量（AI 评价）')
    // 测试组明细与总分
    await expect(page.getByTestId('codelab-review-groups')).toBeVisible()
    await expect(panel).toContainText('/ 100')
  })

  test('运行前不能请求评价（按钮禁用）', async ({ page }) => {
    await openTask(page)
    await expect(page.getByRole('button', { name: /请 AI 评价/ })).toBeDisabled()
  })
})
