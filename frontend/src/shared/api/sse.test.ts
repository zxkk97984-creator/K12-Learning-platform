import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { fetchSSE, parseSSEFrame } from './sse'

function streamResponse(chunks: Uint8Array[]): Response {
  return {
    ok: true,
    status: 200,
    body: new ReadableStream<Uint8Array>({
      start(controller) {
        for (const chunk of chunks) controller.enqueue(chunk)
        controller.close()
      },
    }),
  } as Response
}

describe('fetchSSE', () => {
  beforeEach(() => {
    vi.stubGlobal('window', { localStorage: { getItem: () => 'token-1' } })
    vi.stubGlobal('fetch', vi.fn())
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('按帧解析 JSON data、保留 UTF-8 中文，并忽略 ping 注释', async () => {
    const source = [
      ': ping\n\n',
      'id: message-1\n',
      'event: message.start\n',
      'data: {"message_id":"message-1","role":"TEACHER"}\n\n',
      'id: message-1\r\n',
      'event: text.delta\r\n',
      'data: {"delta":"训练数据"}\r\n\r\n',
    ].join('')
    const encoder = new TextEncoder()
    const encoded = encoder.encode(source)
    const utf8Prefix = encoder.encode(
      'id: message-1\n' + 'event: text.delta\n' + 'data: {"delta":"',
    )
    const splitAt = encoded.indexOf(utf8Prefix[utf8Prefix.length - 1]) + 1
    const fetchMock = vi.mocked(fetch).mockResolvedValue(
      streamResponse([encoded.slice(0, splitAt), encoded.slice(splitAt)]),
    )
    const events: Array<[string, unknown]> = []

    await fetchSSE('/api/v1/conversations/c1/messages', {
      method: 'POST',
      body: JSON.stringify({ content: '解释训练数据' }),
      onEvent: (eventType, data) => {
        events.push([eventType, data])
      },
    })

    expect(events).toEqual([
      ['message.start', { message_id: 'message-1', role: 'TEACHER' }],
      ['text.delta', { delta: '训练数据' }],
    ])
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/conversations/c1/messages',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ content: '解释训练数据' }),
        headers: expect.objectContaining({
          authorization: 'Bearer token-1',
          accept: 'text/event-stream',
        }),
      }),
    )
  })

  it('把 AbortSignal 传给 fetch，并将网络错误抛给调用方', async () => {
    const controller = new AbortController()
    const networkError = new Error('stream disconnected')
    const fetchMock = vi.mocked(fetch).mockRejectedValue(networkError)

    await expect(
      fetchSSE('/api/v1/conversations/c1/messages', {
        signal: controller.signal,
        onEvent: vi.fn(),
      }),
    ).rejects.toBe(networkError)
    expect(fetchMock.mock.calls[0][1]).toEqual(
      expect.objectContaining({ signal: controller.signal }),
    )
  })

  it('支持 CRLF 帧、多个 data 行，并在 JSON 失败时保留原文', () => {
    const event = parseSSEFrame(
      'id: plain-1\r\n' +
        'event: text.delta\r\n' +
        'data: 第一行\r\n' +
        'data: 第二行\r\n',
    )

    expect(event).toEqual({
      id: 'plain-1',
      event: 'text.delta',
      data: '第一行\n第二行',
      rawData: '第一行\n第二行',
    })
  })

  it('忽略单独的心跳注释帧', () => {
    expect(parseSSEFrame(': ping\r\n')).toBeNull()
  })

  it('在 UTF-8 中文字符被拆到不同 chunk 时仍能解析完整事件', async () => {
    const source = 'event: text.delta\ndata: {"delta":"霜铃"}\n\n'
    const encoder = new TextEncoder()
    const encoded = encoder.encode(source)
    const prefixLength = encoder.encode('event: text.delta\ndata: {"delta":"').length
    const fetchMock = vi.mocked(fetch).mockResolvedValue(
      streamResponse([encoded.slice(0, prefixLength + 1), encoded.slice(prefixLength + 1)]),
    )
    const events: unknown[] = []

    await fetchSSE('/api/v1/conversations/c1/messages', {
      onEvent: (_eventType, data) => {
        events.push(data)
      },
    })

    expect(events).toEqual([{ delta: '霜铃' }])
    expect(fetchMock).toHaveBeenCalledOnce()
  })

  it('将非 2xx SSE 响应映射为 ApiError，并通知 onError', async () => {
    const error = { status: 401, code: 'UNAUTHENTICATED', message: '登录已过期' }
    const onError = vi.fn()
    vi.mocked(fetch).mockResolvedValue({
      ok: false,
      status: 401,
      json: async () => ({ error: { code: error.code, message: error.message } }),
    } as Response)

    await expect(
      fetchSSE('/api/v1/conversations/c1/messages', {
        onEvent: vi.fn(),
        onError,
      }),
    ).rejects.toMatchObject(error)
    expect(onError).toHaveBeenCalledWith(expect.objectContaining(error))
  })
})
