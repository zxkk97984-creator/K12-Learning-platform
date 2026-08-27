// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { createVoiceClient, type VoiceClientCallbacks } from './voice-client'

class FakeWebSocket {
  static OPEN = 1
  static instances: FakeWebSocket[] = []

  url: string
  readyState = 0
  sent: string[] = []
  onopen: (() => void) | null = null
  onmessage: ((event: { data: string }) => void) | null = null
  onclose: (() => void) | null = null
  onerror: (() => void) | null = null

  constructor(url: string) {
    this.url = url
    FakeWebSocket.instances.push(this)
  }

  send(data: string) {
    this.sent.push(data)
  }

  close() {
    this.readyState = 3
    this.onclose?.()
  }

  open() {
    this.readyState = 1
    this.onopen?.()
  }

  receive(frame: Record<string, unknown>) {
    this.onmessage?.({ data: JSON.stringify(frame) })
  }
}

describe('createVoiceClient', () => {
  let callbacks: VoiceClientCallbacks

  beforeEach(() => {
    FakeWebSocket.instances = []
    callbacks = {
      onState: vi.fn(),
    onPartial: vi.fn(),
    onFinal: vi.fn(),
    onReply: vi.fn(),
    onAudio: vi.fn(),
      onError: vi.fn(),
    }
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('连接后解析 state/partial/final/audio 帧', async () => {
    const client = createVoiceClient({
      conversationId: 'conversation-1',
      token: 'token-1',
      callbacks,
      createSocket: (url) => new FakeWebSocket(url) as unknown as WebSocket,
    })
    const connectPromise = client.connect()
    const socket = FakeWebSocket.instances[0]
    socket.open()
    await connectPromise
    expect(socket.url).toContain('/api/v1/voice/ws?conversation_id=conversation-1&token=token-1')

    socket.receive({ type: 'state', state: 'LISTENING' })
    socket.receive({ type: 'partial', text: '这里是什么意思', transcript_id: 't-1' })
    socket.receive({ type: 'final', text: '这里是什么意思', conversation_id: 'conversation-1' })
    socket.receive({ type: 'reply', text: '这是文字回复', conversation_id: 'conversation-1' })
    socket.receive({ type: 'audio', data: 'QUJD' })

    expect(callbacks.onState).toHaveBeenCalledWith('LISTENING')
    expect(callbacks.onPartial).toHaveBeenCalledWith('这里是什么意思', 't-1')
    expect(callbacks.onFinal).toHaveBeenCalledWith('这里是什么意思', 'conversation-1')
    expect(callbacks.onReply).toHaveBeenCalledWith('这是文字回复', 'conversation-1')
    expect(callbacks.onAudio).toHaveBeenCalledWith('QUJD')
  })

  it('sendAudioChunk/End/ping 发送正确帧', async () => {
    const client = createVoiceClient({
      conversationId: 'conversation-1',
      token: 'token-1',
      callbacks,
      createSocket: (url) => new FakeWebSocket(url) as unknown as WebSocket,
    })
    const connectPromise = client.connect()
    const socket = FakeWebSocket.instances[0]
    socket.open()
    await connectPromise

    client.sendAudioChunk('QUJD')
    client.sendAudioEnd()
    client.ping()

    expect(socket.sent).toEqual([
      JSON.stringify({ type: 'audio_chunk', data: 'QUJD' }),
      JSON.stringify({ type: 'audio_end' }),
      JSON.stringify({ type: 'ping' }),
    ])
  })

  it('30 秒心跳发送 ping', async () => {
    vi.useFakeTimers()
    const client = createVoiceClient({
      conversationId: 'conversation-1',
      token: 'token-1',
      callbacks,
      createSocket: (url) => new FakeWebSocket(url) as unknown as WebSocket,
    })
    const connectPromise = client.connect()
    const socket = FakeWebSocket.instances[0]
    socket.open()
    await connectPromise

    vi.advanceTimersByTime(30_000)

    expect(socket.sent).toContain(JSON.stringify({ type: 'ping' }))
    client.close()
  })
})

describe('createVoiceClient screen-context frames (Phase 2-A4)', () => {
  beforeEach(() => {
    FakeWebSocket.instances = []
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('initialScreenContext 在连接建立后立即发送 context 帧', async () => {
    const client = createVoiceClient({
      conversationId: 'conversation-1',
      callbacks: {},
      initialScreenContext: { route: '/learn/b1/c1', pageType: 'chapter_reader' },
      createSocket: (url) => new FakeWebSocket(url) as unknown as WebSocket,
    })
    const connectPromise = client.connect()
    const socket = FakeWebSocket.instances[0]
    socket.open()
    await connectPromise
    const frames = socket.sent.map((raw) => JSON.parse(raw) as Record<string, unknown>)
    expect(frames[0]).toEqual({
      type: 'context',
      screen_context: { route: '/learn/b1/c1', pageType: 'chapter_reader' },
    })
    client.close()
  })

  it('sendScreenContext 可在任意时刻更新服务端上下文；未配置时不发送额外帧', async () => {
    const client = createVoiceClient({
      conversationId: 'conversation-1',
      callbacks: {},
      createSocket: (url) => new FakeWebSocket(url) as unknown as WebSocket,
    })
    const connectPromise = client.connect()
    const socket = FakeWebSocket.instances[0]
    socket.open()
    await connectPromise
    client.sendScreenContext({ route: '/home', pageType: 'home' })
    const frames = socket.sent.map((raw) => JSON.parse(raw) as Record<string, unknown>)
    expect(frames.at(-1)).toEqual({
      type: 'context',
      screen_context: { route: '/home', pageType: 'home' },
    })
    expect(frames.filter((frame) => frame.type === 'context')).toHaveLength(1)
    client.close()
  })
})
