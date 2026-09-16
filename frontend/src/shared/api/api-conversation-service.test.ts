import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError } from './http'
import { ApiConversationService } from './api-conversation-service'

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response
}

function streamResponse(source: string): Response {
  return {
    ok: true,
    status: 200,
    body: new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(new TextEncoder().encode(source))
        controller.close()
      },
    }),
  } as Response
}

const listItem = {
  conversation_id: 'conversation-1',
  title: '课程对话',
  status: 'ACTIVE',
  channel: 'TEXT',
  teacher_role_id: null,
  teacher_role: null,
  last_message_at: null,
  updated_at: '2026-08-19T08:00:00Z',
}

const message = {
  message_id: 'message-1',
  conversation_id: 'conversation-1',
  role: 'STUDENT',
  type: 'TEXT',
  content: '你好',
  metadata: {},
  sequence: 1,
  model_info: null,
  created_at: '2026-08-19T08:00:00Z',
}

describe('ApiConversationService', () => {
  let service: ApiConversationService

  beforeEach(() => {
    vi.stubGlobal('window', { localStorage: { getItem: () => 'token-1' } })
    vi.stubGlobal('fetch', vi.fn())
    service = new ApiConversationService()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('读取会话列表并带分页/状态/频道参数', async () => {
    const fetchMock = vi.mocked(fetch).mockResolvedValue(
      jsonResponse(200, { data: [listItem], meta: { next_cursor: null, has_more: false } }),
    )

    await expect(
      service.getConversations({ status: 'ACTIVE', channel: 'TEXT', limit: 20 }),
    ).resolves.toEqual([listItem])
    expect(fetchMock.mock.calls[0][0]).toBe(
      '/api/v1/conversations?limit=20&status=ACTIVE&channel=TEXT',
    )
  })

  it('创建/更新会话并读取消息历史与摘要', async () => {
    const conversation = {
      ...listItem,
      student_id: 'student-1',
      current_page_context: {},
      recent_messages: [],
      conversation_summary: null,
      created_at: '2026-08-19T08:00:00Z',
    }
    const fetchMock = vi.mocked(fetch)
      .mockResolvedValueOnce(jsonResponse(201, { data: conversation, meta: {} }))
      .mockResolvedValueOnce(jsonResponse(200, { data: conversation, meta: {} }))
      .mockResolvedValueOnce(jsonResponse(200, { data: [message], meta: {} }))
      .mockResolvedValueOnce(jsonResponse(200, { data: null, meta: {} }))

    await expect(service.createConversation()).resolves.toEqual(conversation)
    await expect(
      service.updateConversation('conversation-1', { status: 'ARCHIVED' }),
    ).resolves.toEqual(conversation)
    await expect(
      service.getMessages('conversation-1', { sort: 'desc', limit: 10 }),
    ).resolves.toEqual([message])
    await expect(service.getSummary('conversation-1')).resolves.toBeNull()

    expect(fetchMock.mock.calls.map(([url, init]) => [url, init?.method, init?.body])).toEqual([
      ['/api/v1/conversations', 'POST', JSON.stringify({})],
      ['/api/v1/conversations/conversation-1', 'PATCH', JSON.stringify({ status: 'ARCHIVED' })],
      ['/api/v1/conversations/conversation-1/messages?limit=10&sort=desc', 'GET', undefined],
      ['/api/v1/conversations/conversation-1/summary', 'GET', undefined],
    ])
    const firstInit = fetchMock.mock.calls[0][1] as
      | { headers?: Record<string, string> }
      | undefined
    expect(firstInit?.headers?.['Idempotency-Key']).toBeTruthy()
  })

  it('发送 screen_context 并按 SSE 顺序回调消息事件', async () => {
    const source = [
      'id: teacher-1\n',
      'event: message.start\n',
      'data: {"message_id":"teacher-1","conversation_id":"conversation-1","sequence":2}\n\n',
      'event: text.delta\n',
      'data: {"message_id":"teacher-1","delta":"训练数据"}\n\n',
      'event: text.done\n',
      'data: {"message_id":"teacher-1","content":"训练数据","model_info":{"provider":"mock","model":"mock-model"}}\n\n',
      'event: message.done\n',
      'data: {"message_id":"teacher-1","conversation_id":"conversation-1","sequence":2}\n\n',
    ].join('')
    const fetchMock = vi.mocked(fetch).mockResolvedValueOnce(streamResponse(source))
    const events: string[] = []
    const deltas: string[] = []

    await service.sendMessage(
      'conversation-1',
      '解释训练数据',
      {
        route: '/learn/book-1/chapter-3',
        pageType: 'chapter_reader',
        chapterId: 'chapter-3',
        visibleSection: '训练数据 · 定义',
      },
      {
        onStart: (data) => events.push(`start:${data.message_id}`),
        onDelta: (data) => deltas.push(data.delta),
        onTextDone: (data) => events.push(`text.done:${data.content}`),
        onDone: (data) => events.push(`done:${data.sequence}`),
      },
    )

    expect(events).toEqual(['start:teacher-1', 'text.done:训练数据', 'done:2'])
    expect(deltas).toEqual(['训练数据'])
    expect(fetchMock.mock.calls[0][0]).toBe(
      '/api/v1/conversations/conversation-1/messages',
    )
    expect(fetchMock.mock.calls[0][1]).toEqual(
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({
          content: '解释训练数据',
          type: 'TEXT',
          screen_context: {
            route: '/learn/book-1/chapter-3',
            page_type: 'chapter_reader',
            chapter_id: 'chapter-3',
            visible_section: '训练数据 · 定义',
          },
        }),
        headers: expect.objectContaining({ authorization: 'Bearer token-1' }),
      }),
    )
  })

  it('把 quizSessionId/questionId 序列化为 quiz_session_id/question_id', async () => {
    const source = 'event: message.done\ndata: {"message_id":"teacher-2","conversation_id":"conversation-1","sequence":2}\n\n'
    vi.mocked(fetch).mockResolvedValueOnce(streamResponse(source))

    await service.sendMessage(
      'conversation-1',
      '讲解这道题',
      {
        route: '/quizzes/quiz-9',
        pageType: 'quiz_history',
        quizSessionId: 'quiz-9',
        questionId: 'question-17',
      },
      { onDone: () => undefined },
    )

    expect(vi.mocked(fetch).mock.calls[0][1]).toEqual(
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({
          content: '讲解这道题',
          type: 'TEXT',
          screen_context: {
            route: '/quizzes/quiz-9',
            page_type: 'quiz_history',
            quiz_session_id: 'quiz-9',
            question_id: 'question-17',
          },
        }),
      }),
    )
  })

  it('把 SSE error 事件交给 onError，并把 HTTP 401 转成 ApiError', async () => {    const source = [
      'event: error\n',
      'data: {"request_id":"request-1","code":"AI_PROVIDER_ERROR","message":"provider unavailable","fatal":true}\n\n',
    ].join('')
    vi.mocked(fetch).mockResolvedValueOnce(streamResponse(source))
    const onError = vi.fn()

    await service.sendMessage('conversation-1', '解释训练数据', undefined, { onError })
    expect(onError).toHaveBeenCalledWith(
      expect.objectContaining({ code: 'AI_PROVIDER_ERROR', fatal: true }),
    )

    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse(401, { error: { code: 'UNAUTHENTICATED', message: 'missing bearer token' } }),
    )
    const error = await service.getConversation('conversation-1').catch((value: unknown) => value)
    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({ status: 401, code: 'UNAUTHENTICATED' })
  })
})
