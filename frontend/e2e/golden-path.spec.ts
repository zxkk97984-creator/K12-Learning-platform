import { expect, test } from '@playwright/test'

import {
  archiveAllActiveConversations,
  completeQuizOnPage,
  loginStudent,
  prepareContinueLearning,
} from './helpers'

test.describe.configure({ mode: 'serial' })

// Phase 5-B-II：黄金路径真实化——不假设任何原型专属内容（书名/章节/题目文案）。
test.describe('黄金路径', () => {
  test('继续学习 → 阅读 → 对话 → 多题测验完成 → 历史/画像', async ({
    page,
    request,
  }) => {
    test.setTimeout(120_000)

    const session = await loginStudent(request)
    await archiveAllActiveConversations(request, session.token)
    // 真实 API 准备继续学习目标（grade 8 覆盖的书 + 第一章 + READING 55%）
    const target = await prepareContinueLearning(request, session.token)

    await page.addInitScript((token) => {
      window.localStorage.setItem('shuangling-access-token', token)
    }, session.token)

    // 1. 首页：昵称来自登录用户；继续学习卡指向准备好的书
    await page.goto('/home')
    await expect(page.getByRole('heading', { name: /晚上好，/ })).toBeVisible()
    await expect(page.getByText(target.bookTitle).first()).toBeVisible()

    // 2. 继续学习 → 真实 UUID Reader；断言 URL 与非空章节标题
    await page.getByRole('button', { name: /继续第 \d+ 章 →|开始学习 →/ }).first().click()
    await expect(page).toHaveURL(new RegExp(`/learn/${target.bookId}/${target.chapterId}`))
    const chapterHeading = page.locator('h1, h2').filter({ hasText: /\S/ }).first()
    await expect(chapterHeading).toBeVisible()

    // 3. 打开 companion 面板（动态教师名，不硬编码）
    await page.getByRole('button', { name: /打开.*AI 教师/ }).click()
    const panel = page.getByRole('dialog', { name: /对话面板/ })
    await expect(panel).toBeVisible()
    await expect(page.getByRole('button', { name: '语音输入' })).toBeVisible()

    // 4. 发送通用问题 → 教师消息落库（API 轮询确认）→ 刷新恢复
    await page.getByLabel('消息输入').fill('请用简单的例子解释当前这一节的核心概念。')
    await page.getByRole('button', { name: '发送消息' }).click()

    let teacherReply = ''
    await expect
      .poll(async () => {
        const messagesResponse = await request.get(
          `/api/v1/conversations?limit=1&status=ACTIVE`,
          { headers: { Authorization: `Bearer ${session.token}` } },
        )
        if (!messagesResponse.ok()) return false
        const list = (await messagesResponse.json()).data
        if (list.length === 0) return false
        const messagesResponse2 = await request.get(
          `/api/v1/conversations/${list[0].conversation_id}/messages?sort=desc&limit=5`,
          { headers: { Authorization: `Bearer ${session.token}` } },
        )
        if (!messagesResponse2.ok()) return false
        const messages = (await messagesResponse2.json()).data
        const reply = messages.find(
          (message: { role: string; content: string }) =>
            message.role === 'TEACHER' && message.content.trim(),
        )
        teacherReply = reply?.content.trim() ?? ''
        return Boolean(teacherReply)
      })
      .toBe(true)

    await page.reload()
    await expect(chapterHeading.first()).toBeVisible()
    await page.getByRole('button', { name: /打开.*AI 教师/ }).click()
    const visibleReplyPrefix = teacherReply.replace(/(\*\*|__|`)/g, '').slice(0, 12)
    await expect(panel).toContainText(visibleReplyPrefix)

    // 5. 触发「给我出题」→ 等待 quiz 卡出现（不假设题目内容）
    await panel.getByRole('button', { name: '给我出题' }).first().click().catch(() => undefined)
    await page.getByLabel('消息输入').fill('给我出题')
    await page.getByRole('button', { name: '发送消息' }).click()
    await expect(
      page.getByText(/Quiz Skill 已创建|正式测验已记录/).last(),
    ).toBeVisible({ timeout: 20_000 })

    // 6. 通用答题循环：多题、多题型、服务端判定推进，最终显示真实汇总
    await completeQuizOnPage(page)

    // 7. 测验历史：使用通用入口与标题断言（导航项现为「练习」→ /quizzes）
    await page.keyboard.press('Escape')
    await page.getByRole('link', { name: '练习' }).click()
    await expect(page.getByRole('heading', { name: /每一次答题/ })).toBeVisible()
    await expect(page.getByText(/随堂测验/).first()).toBeVisible()

    // 8. 画像页：通用入口断言
    await page.getByRole('link', { name: '成长' }).click()
    await expect(page.getByRole('heading', { name: /眼中的你。/ })).toBeVisible()
  })
})
