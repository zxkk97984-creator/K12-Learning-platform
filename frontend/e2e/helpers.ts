import { expect, type Page, type APIRequestContext } from '@playwright/test'

export interface StudentSession {
  token: string
  studentId: string
}

export interface ContinueTarget {
  bookId: string
  bookTitle: string
  chapterId: string
  chapterTitle: string
}

/** 登录学生（seed 账号）并返回 token + student_id。 */
export async function loginStudent(
  request: APIRequestContext,
  username = 'xiaoming',
  password = 'demo123',
): Promise<StudentSession> {
  const resp = await request.post('/api/v1/auth/login', {
    data: { username, password },
  })
  expect(resp.ok()).toBeTruthy()
  const body = (await resp.json()).data
  return { token: body.access_token as string, studentId: body.user.user_id as string }
}

/** 归档学生全部 ACTIVE 会话，保证面板从干净状态开始。 */
export async function archiveAllActiveConversations(
  request: APIRequestContext,
  token: string,
): Promise<void> {
  const resp = await request.get('/api/v1/conversations?status=ACTIVE&limit=100', {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!resp.ok()) return
  const conversations = (await resp.json()).data as Array<{
    conversation_id: string
    status: string
  }>
  for (const conversation of conversations) {
    if (conversation.status === 'ACTIVE') {
      await request.patch(`/api/v1/conversations/${conversation.conversation_id}`, {
        headers: { Authorization: `Bearer ${token}` },
        data: { status: 'ARCHIVED' },
      })
    }
  }
}

/**
 * 从真实书库选择一本覆盖 grade 且已发布、有章节的书，
 * 取第一章并通过 PUT /me/progress 写入 READING 进度，
 * 让首页「继续学习」卡进入稳定可用状态。
 */
export async function prepareContinueLearning(
  request: APIRequestContext,
  token: string,
  grade = 8,
): Promise<ContinueTarget> {
  const booksResp = await request.get('/api/v1/books?limit=100', {
    headers: { Authorization: `Bearer ${token}` },
  })
  expect(booksResp.ok()).toBeTruthy()
  const booksPayload = (await booksResp.json()).data as Array<{
    book_id: string
    title: string
    grade_min?: number | null
    grade_max?: number | null
  }>
  const candidates = booksPayload.filter((book) => {
    const min = book.grade_min ?? 1
    const max = book.grade_max ?? 12
    return grade >= min && grade <= max
  })
  expect(candidates.length).toBeGreaterThan(0)

  let target = null as null | { bookId: string; bookTitle: string; chapterId: string; chapterTitle: string }
  for (const book of candidates) {
    const chaptersResp = await request.get(
      `/api/v1/books/${book.book_id}/chapters`,
      { headers: { Authorization: `Bearer ${token}` } },
    )
    if (!chaptersResp.ok()) continue
    const chapters = (await chaptersResp.json()).data as Array<{
      chapter_id: string
      title: string
    }>
    if (chapters.length === 0) continue
    // 优先选"确有内容"的章节：跳过审计/测试章节（"本章暂无内容"这类空 content_blocks），
    // 否则后续测验生成会因章节无内容而 QUIZ_SKILL_ERROR（不应凭空出与章节无关的题）。
    for (const chapter of chapters) {
      const detailResp = await request.get(
        `/api/v1/chapters/${chapter.chapter_id}`,
        { headers: { Authorization: `Bearer ${token}` } },
      )
      if (!detailResp.ok()) continue
      const detail = (await detailResp.json()).data as {
        content_blocks?: unknown[]
      }
      if ((detail.content_blocks?.length ?? 0) === 0) continue
      target = {
        bookId: book.book_id,
        bookTitle: book.title,
        chapterId: chapter.chapter_id,
        chapterTitle: chapter.title,
      }
      break
    }
    if (target) break
  }
  expect(target).not.toBeNull()

  const put = await request.put(`/api/v1/me/progress/${target!.bookId}`, {
    headers: { Authorization: `Bearer ${token}` },
    data: {
      chapter_id: target!.chapterId,
      status: 'READING',
      position_percent: 55,
    },
  })
  expect(put.ok()).toBeTruthy()
  return target!
}

/** 在当前 QuizCard 上按题型作答当前题并点击提交。 */
async function answerAndSubmit(page: Page): Promise<void> {
  const card = page.locator('[data-od-id="chat-quiz-card"]').last()
  const headerText = (await card.locator('span').nth(1).textContent()) ?? ''

  if (headerText.includes('填空')) {
    await card.getByLabel('填空答案').fill('E2E 答案')
  } else {
    // 单选/多选/判断：选项按钮带 aria-pressed（唯一标识，避免命中提示/提交等）
    await card.locator('button[aria-pressed]').first().click()
  }
  await card.getByRole('button', { name: '提交答案' }).click()
}

/**
 * 通用答题循环：不假设题目内容与正确答案，依靠服务端判定推进；
 * 未最终作答时重复提交（最多 MAX_ATTEMPTS），最终后点击下一题/查看结果。
 */
export async function completeQuizOnPage(page: Page): Promise<void> {
  const card = page.locator('[data-od-id="chat-quiz-card"]').last()
  await expect(card.getByText(/共 \d+ 题/)).toBeVisible({ timeout: 20_000 })

  let finalizedCount = 0
  // 最多处理 10 道题（后端上限 10）；每题最多 3 次尝试
  for (let guard = 0; guard < 30 && finalizedCount < 10; guard += 1) {
    await answerAndSubmit(page)
    const feedback = card.getByText(/✓ 答对了|✗ 这次不对|尝试次数用完了/).first()
    const failedNotice = card.getByText('提交失败，请重试')
    try {
      await expect(feedback.or(failedNotice)).toBeVisible({ timeout: 15_000 })
    } catch {
      return // 页面已切换（如导航），交由调用方断言收尾
    }
    if (await failedNotice.count()) {
      continue // 网络/服务瞬时失败：直接再次提交
    }

    const nextButton = card.getByRole('button', { name: /下一题 →|查看结果/ })
    if ((await nextButton.count()) > 0) {
      finalizedCount += 1
      const isLast = (await nextButton.textContent())?.includes('查看结果')
      await nextButton.click()
      if (isLast) break
      // 等待进入下一题（题号递增）
      await expect(card.getByText(new RegExp(`第 ${finalizedCount + 1} 题 /`))).toBeVisible({
        timeout: 10_000,
      })
    }
    // 非 final 反馈（还有尝试机会）→ 循环继续对同一题重新作答
  }

  // 全部完成后展示真实结果汇总（correct/total 来自服务端）
  await expect(card.getByText(/测验完成 · 最终正确 \d+\/\d+/)).toBeVisible({
    timeout: 20_000,
  })
}
