import { getToken } from './auth'

export type VoiceState = 'IDLE' | 'LISTENING' | 'THINKING' | 'SPEAKING' | 'ERROR'

export interface VoiceClientCallbacks {
  onState?: (state: VoiceState) => void
  onPartial?: (text: string, transcriptId: string) => void
  onFinal?: (text: string, conversationId: string) => void
  onReply?: (text: string, conversationId: string) => void
  onAudio?: (base64Audio: string) => void
  onError?: (code: string, message: string) => void
  onClose?: () => void
}

export interface VoiceClientOptions {
  conversationId: string
  token?: string
  callbacks: VoiceClientCallbacks
  /** 连接建立后立即发送的结构化页面上下文（Phase 2-A4；可选，向后兼容）。 */
  initialScreenContext?: Record<string, unknown>
  /** Test seam: default builds ws(s):// from location. */
  createSocket?: (url: string) => WebSocket
}

export interface VoiceClient {
  connect: () => Promise<void>
  sendAudioChunk: (base64: string) => void
  sendAudioEnd: () => void
  cancel: () => void
  ping: () => void
  close: () => void
  /** 显式更新服务端使用的页面上下文（下一轮 utterance 生效）。 */
  sendScreenContext: (context: Record<string, unknown>) => void
}

function wsUrl(conversationId: string, token: string): string {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const params = new URLSearchParams({ conversation_id: conversationId, token })
  return `${protocol}//${window.location.host}/api/v1/voice/ws?${params.toString()}`
}

export function createVoiceClient(options: VoiceClientOptions): VoiceClient {
  const token = options.token ?? getToken() ?? ''
  const callbacks = options.callbacks
  const url = wsUrl(options.conversationId, token)
  let socket: WebSocket | null = null
  let heartbeat: number | undefined
  let closed = false
  let reconnectAttempted = false

  const send = (payload: Record<string, unknown>) => {
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify(payload))
    }
  }

  const handleMessage = (event: MessageEvent) => {
    try {
      const frame = JSON.parse(String(event.data)) as Record<string, unknown>
      switch (frame.type) {
        case 'state':
          callbacks.onState?.(String(frame.state) as VoiceState)
          break
        case 'partial':
          callbacks.onPartial?.(String(frame.text ?? ''), String(frame.transcript_id ?? ''))
          break
        case 'final':
          callbacks.onFinal?.(String(frame.text ?? ''), String(frame.conversation_id ?? ''))
          break
        case 'reply':
          callbacks.onReply?.(String(frame.text ?? ''), String(frame.conversation_id ?? ''))
          break
        case 'audio':
          callbacks.onAudio?.(String(frame.data ?? ''))
          break
        case 'error':
          callbacks.onError?.(String(frame.code ?? 'VOICE_ERROR'), String(frame.message ?? 'voice error'))
          break
        default:
          break
      }
    } catch {
      // 非 JSON/坏帧忽略，保持连接可用。
    }
  }

  const stopHeartbeat = () => {
    if (heartbeat !== undefined) {
      window.clearInterval(heartbeat)
      heartbeat = undefined
    }
  }

  const startHeartbeat = () => {
    stopHeartbeat()
    heartbeat = window.setInterval(() => send({ type: 'ping' }), 30_000)
  }

  const connect = () =>
    new Promise<void>((resolve, reject) => {
      const createSocket = options.createSocket ?? ((socketUrl: string) => new WebSocket(socketUrl))
      socket = createSocket(url)
      socket.onopen = () => {
        startHeartbeat()
        if (options.initialScreenContext) {
          send({ type: 'context', screen_context: options.initialScreenContext })
        }
        resolve()
      }
      socket.onmessage = handleMessage
      socket.onerror = () => {
        reject(new Error('voice websocket error'))
      }
      socket.onclose = () => {
        stopHeartbeat()
        callbacks.onClose?.()
        if (!closed && !reconnectAttempted) {
          reconnectAttempted = true
          void connect().catch(() => undefined)
        }
      }
    })

  return {
    connect,
    sendAudioChunk: (base64: string) => send({ type: 'audio_chunk', data: base64 }),
    sendAudioEnd: () => send({ type: 'audio_end' }),
    cancel: () => send({ type: 'cancel' }),
    ping: () => send({ type: 'ping' }),
    sendScreenContext: (context: Record<string, unknown>) =>
      send({ type: 'context', screen_context: context }),
    close: () => {
      closed = true
      stopHeartbeat()
      socket?.close()
      socket = null
    },
  }
}
