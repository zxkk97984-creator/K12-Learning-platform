import { useEffect, useRef, useState, type KeyboardEvent } from 'react'

import { useCompanionStore, useTeacherName } from '@/features/companion'
import { useToastStore } from '@/features/feedback'
import { useScreenContext } from '@/features/screen-context'
import type { VoicePreference } from '@/entities/student/types'
import { learningService } from '@/shared/api/learning-service'
import {
  buildQuestionAskedEvent,
  buildVoiceSessionEvent,
  createVoiceEndedGuard,
  getCurrentLearningSessionId,
} from '@/features/learning/events'
import { studentService } from '@/shared/services'
import { createVoiceClient, type VoiceClient, type VoiceState } from '@/shared/api/voice-client'

import { useConversationStore } from '../store/conversation-store'
import { startAudioCapture, type AudioCapture } from '@/features/voice/audio-capture'

function arrayBufferToBase64(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer)
  let binary = ''
  for (const byte of bytes) binary += String.fromCharCode(byte)
  return btoa(binary)
}

const VOICE_LABEL: Record<VoiceState, string | null> = {
  IDLE: null,
  LISTENING: '正在聆听…',
  THINKING: '思考中…',
  SPEAKING: '正在说话…',
  ERROR: '语音暂时不可用，请使用文字输入',
}

export function ChatComposer() {
  const [value, setValue] = useState('')
  const teacherName = useTeacherName()
  const [voiceState, setVoiceState] = useState<VoiceState>('IDLE')
  const [recording, setRecording] = useState(false)
  const [voicePrefs, setVoicePrefs] = useState<VoicePreference>({
    input_enabled: true,
    tts_enabled: true,
    volume: 0.8,
    speed: 1,
  })
  const send = useConversationStore((state) => state.send)
  const ensureConversationId = useConversationStore((state) => state.ensureConversationId)
  const refresh = useConversationStore((state) => state.refresh)
  const setAiState = useCompanionStore((state) => state.setAiState)
  const showToast = useToastStore((state) => state.showToast)
  const { screenContext } = useScreenContext()

  const captureRef = useRef<AudioCapture | null>(null)
  const voiceClientRef = useRef<VoiceClient | null>(null)
  // 缺口 1d：语音结束事件恰好一次（stop 与卸载并发也不会双发）
  const voiceEndedGuardRef = useRef(createVoiceEndedGuard())

  useEffect(() => {
    void studentService
      .getPreferences()
      .then((prefs) => setVoicePrefs(prefs.voice_preference))
      .catch(() => undefined)
  }, [])

  // Phase 2 缺口 1：语音连接保持期间页面切换（如 Reader → 首页）时，
  // 把最新 ScreenContext 推给服务端，保证后续 utterance 不再携带旧章节。
  useEffect(() => {
    voiceClientRef.current?.sendScreenContext(
      screenContext as unknown as Record<string, unknown>,
    )
  }, [screenContext])

  useEffect(() => {
    return () => {
      const endedConversationId = voiceEndedGuardRef.current.consumeEnded()
      if (endedConversationId) {
        void learningService
          .createEvent(buildVoiceSessionEvent('VOICE_SESSION_ENDED', endedConversationId))
          .catch(() => undefined)
      }
      voiceClientRef.current?.close()
      captureRef.current?.stop()
      captureRef.current = null
    }
  }, [])

  const applyVoiceState = (state: VoiceState) => {
    setVoiceState(state)
    if (state === 'LISTENING') setAiState('listening')
    else if (state === 'THINKING') setAiState('thinking')
    else if (state === 'SPEAKING') setAiState('speaking')
    else setAiState('idle')
  }

  const startVoice = async () => {
    try {
      const conversationId = await ensureConversationId()
      const client = createVoiceClient({
        conversationId,
        // Phase 2-A4：连接后立即上报当前页面上下文，服务端在下一轮
        // utterance 时合并进 SendMessageRequest.screen_context。
        initialScreenContext: screenContext as unknown as Record<string, unknown>,
        callbacks: {
          onState: applyVoiceState,
          onReply: () => void refresh(),
          onAudio: (data) => {
            if (!voicePrefs.tts_enabled) return
            const audio = new Audio(`data:audio/wav;base64,${data}`)
            audio.volume = voicePrefs.volume
            audio.playbackRate = voicePrefs.speed
            void audio.play().catch(() => undefined)
          },
          onError: (code, message) => {
            showToast(`语音连接失败：${message}（${code}）`)
            applyVoiceState('ERROR')
            window.setTimeout(() => setVoiceState('IDLE'), 1800)
          },
          onClose: () => setVoiceState((current) => (current === 'IDLE' ? current : 'IDLE')),
        },
      })
      voiceClientRef.current = client
      await client.connect()

      const capture = await startAudioCapture((frame) => {
        client.sendAudioChunk(arrayBufferToBase64(frame))
      })
      captureRef.current = capture
      setRecording(true)
      applyVoiceState('LISTENING')
      // Phase 3 + 缺口 1d：语音会话开始 → 可追溯事件，并登记一次性结束守卫
      voiceEndedGuardRef.current.markStarted(conversationId)
      void learningService
        .createEvent(buildVoiceSessionEvent('VOICE_SESSION_STARTED', conversationId))
        .catch(() => undefined)
    } catch (error) {
      captureRef.current?.stop()
      captureRef.current = null
      voiceClientRef.current?.close()
      voiceClientRef.current = null
      const reason = error instanceof Error ? error.message : ''
      const message =
        reason === 'NO_MIC_PERMISSION'
          ? '浏览器没有麦克风权限，请在地址栏中允许麦克风后重试'
          : reason === 'WORKLET_UNSUPPORTED'
            ? '当前浏览器不支持实时音频采集，请使用最新版 Chrome'
            : reason === 'CAPTURE_FAILED'
              ? '麦克风初始化失败，请检查系统录音设备'
              : '语音连接失败，请检查后端是否已重启'
      showToast(message)
      applyVoiceState('ERROR')
      window.setTimeout(() => setVoiceState('IDLE'), 1800)
    }
  }

  const stopVoice = () => {
    captureRef.current?.stop()
    captureRef.current = null
    voiceClientRef.current?.sendAudioEnd()
    setRecording(false)
    // 只在仍有活跃语音会话时发一次 ENDED；与卸载清理并发时由守卫去重
    const endedConversationId = voiceEndedGuardRef.current.consumeEnded()
    if (endedConversationId) {
      void learningService
        .createEvent(buildVoiceSessionEvent('VOICE_SESSION_ENDED', endedConversationId))
        .catch(() => undefined)
    }
  }

  const toggleVoice = () => {
    if (recording) stopVoice()
    else void startVoice()
  }

  const submit = async () => {
    const text = value.trim()
    if (!text) return
    // 缺口 1c：自由输入提问同样产生可追溯的 QUESTION_ASKED；
    // 先确保真实会话，再携带 book/chapter/session 关联。
    let conversationId: string | null = null
    try {
      conversationId = await ensureConversationId()
    } catch {
      conversationId = null
    }
    const questionEvent = buildQuestionAskedEvent({
      screenContext,
      conversationId,
      sessionId: getCurrentLearningSessionId(),
      source: 'composer',
    })
    if (questionEvent) {
      void learningService.createEvent(questionEvent).catch(() => undefined)
    }
    send(text, screenContext)
    setValue('')
  }

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      submit()
    }
  }

  const overlayText = VOICE_LABEL[voiceState]

  return (
    <>
      {overlayText ? (
        <div
          role="status"
          aria-live="polite"
          className="flex items-center gap-2 border-t border-border px-4 py-2 text-[11px] text-muted"
        >
          <i
            className={`h-2 w-2 rounded-full ${
              voiceState === 'SPEAKING' ? 'animate-pulse bg-accent' : 'bg-accent'
            }`}
          />
          <span>{overlayText}</span>
          {voiceState === 'SPEAKING' ? (
            <span className="flex items-end gap-0.5" aria-hidden="true">
              {[0, 1, 2].map((index) => (
                <i
                  key={index}
                  className="h-2 w-0.5 animate-bounce rounded-full bg-accent"
                  style={{ animationDelay: `${index * 0.12}s` }}
                />
              ))}
            </span>
          ) : null}
        </div>
      ) : null}
      <form
        className="flex items-end gap-2 border-t border-border px-3 pt-2.5 pb-3"
        onSubmit={(event) => {
          event.preventDefault()
          submit()
        }}
      >
        <textarea
          value={value}
          onChange={(event) => setValue(event.target.value)}
          onKeyDown={handleKeyDown}
          rows={1}
          placeholder={`问问${teacherName}，比如：那它为什么会出错？`}
          aria-label="消息输入"
          className="min-h-[42px] max-h-[88px] flex-1 resize-none rounded-[10px] border border-border bg-bg px-3 py-2.5 text-[13px] text-fg outline-none focus:border-fg"
        />
        {voicePrefs.input_enabled ? (
          <button
            type="button"
            aria-label={recording ? '停止录音' : '语音输入'}
            className="relative grid h-[42px] w-[42px] shrink-0 place-items-center rounded-[10px] border border-border bg-surface text-fg hover:border-fg"
            onClick={toggleVoice}
          >
            🎤
            {recording ? (
              <span className="absolute top-1.5 right-1.5 h-2 w-2 animate-pulse rounded-full bg-red-500" />
            ) : null}
          </button>
        ) : null}
        <button
          type="submit"
          aria-label="发送消息"
          className="grid h-[42px] w-[42px] shrink-0 place-items-center rounded-[10px] border border-fg bg-fg text-surface hover:bg-fg/85"
        >
          ↑
        </button>
      </form>
    </>
  )
}
