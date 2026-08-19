import { useEffect, useRef, useState, type KeyboardEvent } from 'react'

import { useCompanionStore } from '@/features/companion'
import { useToastStore } from '@/features/feedback'
import { useScreenContext } from '@/features/screen-context'
import type { VoicePreference } from '@/entities/student/types'
import { studentService } from '@/mocks/services'
import { createVoiceClient, type VoiceClient, type VoiceState } from '@/shared/api/voice-client'

import { useConversationStore } from '../store/conversation-store'

function blobToBase64(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => {
      const result = String(reader.result ?? '')
      resolve(result.split(',')[1] ?? '')
    }
    reader.onerror = () => reject(reader.error)
    reader.readAsDataURL(blob)
  })
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

  const recorderRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<string[]>([])
  const voiceClientRef = useRef<VoiceClient | null>(null)

  useEffect(() => {
    void studentService
      .getPreferences()
      .then((prefs) => setVoicePrefs(prefs.voice_preference))
      .catch(() => undefined)
  }, [])

  useEffect(() => {
    return () => {
      voiceClientRef.current?.close()
      if (recorderRef.current && recorderRef.current.state !== 'inactive') {
        recorderRef.current.stop()
      }
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
        callbacks: {
          onState: applyVoiceState,
          onFinal: () => void refresh(),
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

      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const recorder = new MediaRecorder(stream)
      recorderRef.current = recorder
      chunksRef.current = []
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          void blobToBase64(event.data).then((base64) => chunksRef.current.push(base64))
        }
      }
      recorder.onstop = () => {
        stream.getTracks().forEach((track) => track.stop())
        for (const chunk of chunksRef.current) client.sendAudioChunk(chunk)
        client.sendAudioEnd()
      }
      recorder.start()
      setRecording(true)
      applyVoiceState('LISTENING')
    } catch {
      voiceClientRef.current?.close()
      voiceClientRef.current = null
      showToast('语音不可用，请使用文字输入')
      applyVoiceState('ERROR')
      window.setTimeout(() => setVoiceState('IDLE'), 1800)
    }
  }

  const stopVoice = () => {
    if (recorderRef.current && recorderRef.current.state !== 'inactive') {
      recorderRef.current.stop()
    }
    setRecording(false)
  }

  const toggleVoice = () => {
    if (recording) stopVoice()
    else void startVoice()
  }

  const submit = () => {
    if (!value.trim()) return
    void send(value, screenContext)
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
          placeholder="问问霜铃，比如：那它为什么会出错？"
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
