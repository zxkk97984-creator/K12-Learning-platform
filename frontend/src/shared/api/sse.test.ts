import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { fetchSSE } from './sse'

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
})
