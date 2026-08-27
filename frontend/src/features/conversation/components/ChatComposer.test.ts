// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import React from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { VoiceClientCallbacks } from '@/shared/api/voice-client'

const mocks = vi.hoisted(() => ({
  setAiState: vi.fn(),
  showToast: vi.fn(),
  createVoiceClient: vi.fn(),
  callbacks: null as VoiceClientCallbacks | null,
  getConversations: vi.fn(),
  createConversation: vi.fn(),
  getMessages: vi.fn(),
  getPreferences: vi.fn(),
  startAudioCapture: vi.fn(),
  sendScreenContext: vi.fn(),
  createLearningEvent: vi.fn().mockResolvedValue({}),
  screenContextValue: {
    route: '/learn/b1/c1',
    pageType: 'chapter_reader',
    bookId: 'b1',
    chapterId: 'c1',
  } as Record<string, unknown>,
}))

vi.mock('@/features/companion', () => {
  const storeState = { setAiState: mocks.setAiState }
  const useCompanionStore = (selector: (state: unknown) => unknown) =>
    selector(storeState)
  ;(useCompanionStore as unknown as Record<string, unknown>).getState = () => storeState
  return { useCompanionStore, useTeacherName: () => '霜铃' }
})

vi.mock('@/features/feedback', () => ({
  useToastStore: (selector: (state: unknown) => unknown) =>
    selector({ showToast: mocks.showToast }),
}))

vi.mock('@/features/screen-context', () => ({
  useScreenContext: () => ({ screenContext: mocks.screenContextValue }),
}))

vi.mock('@/shared/api/voice-client', () => ({
  createVoiceClient: (options: { callbacks: VoiceClientCallbacks }) => {
    mocks.callbacks = options.callbacks
    return mocks.createVoiceClient(options)
  },
}))

vi.mock('@/shared/services', () => ({
  conversationService: {
    getConversations: mocks.getConversations,
    createConversation: mocks.createConversation,
    getMessages: mocks.getMessages,
    sendMessage: vi.fn(),
  },
  studentService: {
    getPreferences: mocks.getPreferences,
  },
}))

vi.mock('@/shared/api/learning-service', () => ({
  learningService: { createEvent: mocks.createLearningEvent },
}))

vi.mock('@/features/voice/audio-capture', () => ({
  startAudioCapture: (onFrame: (frame: ArrayBuffer) => void) =>
    mocks.startAudioCapture(onFrame),
}))

import { useConversationStore } from '../store/conversation-store'
import { ChatComposer } from './ChatComposer'

const audioInstances: FakeAudio[] = []

class FakeAudio {
  volume = 1
  playbackRate = 1
  play = vi.fn().mockResolvedValue(undefined)

  constructor() {
    audioInstances.push(this)
  }
}

describe('ChatComposer voice UI', () => {
  beforeEach(() => {
    audioInstances.length = 0
    vi.clearAllMocks()
    useConversationStore.setState({ messages: [], conversationId: null, loaded: false })
    mocks.getConversations.mockResolvedValue([])
    mocks.createConversation.mockResolvedValue({
      conversation_id: 'conversation-voice',
      student_id: 'student-1',
      teacher_role_id: null,
      title: null,
      status: 'ACTIVE',
      channel: 'TEXT',
      current_page_context: {},
      recent_messages: [],
      conversation_summary: null,
      created_at: '2026-08-19T00:00:00Z',
      updated_at: '2026-08-19T00:00:00Z',
      last_message_at: null,
    })
    mocks.getMessages.mockResolvedValue([])
    mocks.getPreferences.mockResolvedValue({
      voice_preference: {
        input_enabled: true,
        tts_enabled: true,
        volume: 0.8,
        speed: 1,
      },
    })
    mocks.startAudioCapture.mockRejectedValue(new Error('NO_MIC_PERMISSION'))
    mocks.screenContextValue = { route: '/home', pageType: 'home' }
    mocks.createVoiceClient.mockReturnValue({
      connect: vi.fn().mockResolvedValue(undefined),
      sendAudioChunk: vi.fn(),
      sendAudioEnd: vi.fn(),
      cancel: vi.fn(),
      ping: vi.fn(),
      close: vi.fn(),
      sendScreenContext: mocks.sendScreenContext,
    })
  })

  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
    audioInstances.length = 0
  })

  it('渲染麦克风按钮', () => {
    render(React.createElement(ChatComposer))
    expect(screen.getByRole('button', { name: '语音输入' })).toBeTruthy()
  })

  it('input_enabled=false 时隐藏麦克风按钮', async () => {
    mocks.getPreferences.mockResolvedValue({
      voice_preference: {
        input_enabled: false,
        tts_enabled: true,
        volume: 0.8,
        speed: 1,
      },
    })
    render(React.createElement(ChatComposer))

    await waitFor(() =>
      expect(screen.queryByRole('button', { name: '语音输入' })).toBeNull(),
    )
  })

  it('无麦克风权限时降级为文字输入并显示错误状态', async () => {
    render(React.createElement(ChatComposer))
    fireEvent.click(screen.getByRole('button', { name: '语音输入' }))

    await waitFor(() =>
      expect(mocks.showToast).toHaveBeenCalledWith(
        '浏览器没有麦克风权限，请在地址栏中允许麦克风后重试',
      ),
    )
    expect(screen.getByText('语音暂时不可用，请使用文字输入')).toBeTruthy()
  })

  it('收到 SPEAKING 状态后显示说话徽标并同步桌宠', async () => {
    render(React.createElement(ChatComposer))
    fireEvent.click(screen.getByRole('button', { name: '语音输入' }))

    await waitFor(() => expect(mocks.callbacks).not.toBeNull())
    act(() => mocks.callbacks?.onState?.('SPEAKING'))

    expect(screen.getByText('正在说话…')).toBeTruthy()
    expect(mocks.setAiState).toHaveBeenCalledWith('speaking')
  })

  it('将麦克风 PCM 帧编码后实时发送，并在停止时结束音频', async () => {
    let capturedFrame: ((frame: ArrayBuffer) => void) | null = null
    mocks.startAudioCapture.mockImplementation(async (onFrame: (frame: ArrayBuffer) => void) => {
      capturedFrame = onFrame
      onFrame(new Uint8Array([0, 1, 255]).buffer)
      return { stop: vi.fn() }
    })

    render(React.createElement(ChatComposer))
    fireEvent.click(screen.getByRole('button', { name: '语音输入' }))

    await waitFor(() => expect(mocks.callbacks).not.toBeNull())
    expect(capturedFrame).not.toBeNull()
    const client = mocks.createVoiceClient.mock.results[0]?.value
    expect(client.sendAudioChunk).toHaveBeenCalledWith('AAH/')

    fireEvent.click(screen.getByRole('button', { name: '停止录音' }))
    expect(client.sendAudioEnd).toHaveBeenCalled()
  })

  it('TTS 播放应用 volume/speed', async () => {
    mocks.getPreferences.mockResolvedValue({
      voice_preference: {
        input_enabled: true,
        tts_enabled: true,
        volume: 0.5,
        speed: 1.5,
      },
    })
    mocks.startAudioCapture.mockResolvedValue({ stop: vi.fn() })
    vi.stubGlobal('Audio', FakeAudio)
    vi.stubGlobal('navigator', {
      ...navigator,
      mediaDevices: {
        getUserMedia: vi.fn().mockResolvedValue({ getTracks: () => [] }),
      },
    })
    render(React.createElement(ChatComposer))
    await waitFor(() => expect(mocks.getPreferences).toHaveBeenCalled())
    await act(async () => undefined)
    fireEvent.click(screen.getByRole('button', { name: '语音输入' }))

    await waitFor(() => expect(mocks.callbacks).not.toBeNull())
    act(() => mocks.callbacks?.onAudio?.('QUJD'))

    expect(audioInstances[0].volume).toBe(0.5)
    expect(audioInstances[0].playbackRate).toBe(1.5)
    expect(audioInstances[0].play).toHaveBeenCalled()
  })

  it('收到 AI 文字回复后刷新聊天，不依赖 TTS 音频', async () => {
    mocks.startAudioCapture.mockResolvedValue({ stop: vi.fn() })
    vi.stubGlobal('navigator', {
      ...navigator,
      mediaDevices: {
        getUserMedia: vi.fn().mockResolvedValue({ getTracks: () => [] }),
      },
    })
    render(React.createElement(ChatComposer))
    fireEvent.click(screen.getByRole('button', { name: '语音输入' }))

    await waitFor(() => expect(mocks.callbacks).not.toBeNull())
    expect(mocks.getMessages).not.toHaveBeenCalled()

    act(() => mocks.callbacks?.onReply?.('这是文字回复', 'conversation-voice'))

    await waitFor(() =>
      expect(mocks.getMessages).toHaveBeenCalledWith('conversation-voice', { sort: 'asc' }),
    )
  })

  it('tts_enabled=false 时跳过音频播放', async () => {
    mocks.getPreferences.mockResolvedValue({
      voice_preference: {
        input_enabled: true,
        tts_enabled: false,
        volume: 0.8,
        speed: 1,
      },
    })
    mocks.startAudioCapture.mockResolvedValue({ stop: vi.fn() })
    vi.stubGlobal('Audio', FakeAudio)
    vi.stubGlobal('navigator', {
      ...navigator,
      mediaDevices: {
        getUserMedia: vi.fn().mockResolvedValue({ getTracks: () => [] }),
      },
    })
    render(React.createElement(ChatComposer))
    await waitFor(() => expect(mocks.getPreferences).toHaveBeenCalled())
    await act(async () => undefined)
    fireEvent.click(screen.getByRole('button', { name: '语音输入' }))

    await waitFor(() => expect(mocks.callbacks).not.toBeNull())
    act(() => mocks.callbacks?.onAudio?.('QUJD'))

    expect(audioInstances).toHaveLength(0)
  })
})

describe('ChatComposer 语音 ScreenContext 动态同步（Phase 2 缺口 1）', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useConversationStore.setState({ messages: [], conversationId: null, loaded: false })
    mocks.getConversations.mockResolvedValue([])
    mocks.createConversation.mockResolvedValue({
      conversation_id: 'conversation-voice-2',
      student_id: 'student-1',
      teacher_role_id: null,
      title: null,
      status: 'ACTIVE',
      channel: 'TEXT',
      current_page_context: {},
      recent_messages: [],
      conversation_summary: null,
      created_at: '2026-08-19T00:00:00Z',
      updated_at: '2026-08-19T00:00:00Z',
      last_message_at: null,
    })
    mocks.getMessages.mockResolvedValue([])
    mocks.getPreferences.mockResolvedValue({
      voice_preference: { input_enabled: true, tts_enabled: true, volume: 0.8, speed: 1 },
    })
  })

  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
  })

  it('语音连接中切换页面后，服务端收到清理后的新上下文', async () => {
    mocks.screenContextValue = {
      route: '/learn/b1/c1',
      pageType: 'chapter_reader',
      bookId: 'b1',
      chapterId: 'c1',
      chapterTitle: '训练数据',
    }
    render(React.createElement(ChatComposer))

    // 启动语音（采集成功）
    const captureStop = vi.fn()
    mocks.startAudioCapture.mockResolvedValue({ stop: captureStop })
    fireEvent.click(screen.getByRole('button', { name: '语音输入' }))
    await waitFor(() => expect(mocks.createVoiceClient).toHaveBeenCalledTimes(1))

    // 连接建立即发送最新上下文
    const options = mocks.createVoiceClient.mock.calls[0][0] as unknown as {
      initialScreenContext?: Record<string, unknown>
    }
    expect(options.initialScreenContext).toMatchObject({ bookId: 'b1', chapterId: 'c1' })

    // 模拟离开 Reader：上下文对象整体替换为干净快照，随后任一交互触发重渲染
    mocks.screenContextValue = { route: '/home', pageType: 'home' }
    fireEvent.change(screen.getByLabelText('消息输入'), { target: { value: 'x' } })

    await waitFor(() =>
      expect(mocks.sendScreenContext).toHaveBeenCalledWith(
        expect.objectContaining({ route: '/home', pageType: 'home' }),
      ),
    )
    const pushed = mocks.sendScreenContext.mock.calls.at(-1)![0] as Record<string, unknown>
    expect(pushed).not.toHaveProperty('bookId')
    expect(pushed).not.toHaveProperty('chapterId')
  })
})

describe('ChatComposer 提问事件与语音结束一次性（Phase 3 缺口修复）', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useConversationStore.setState({
      messages: [],
      conversationId: null,
      loaded: false,
      lastScreenContext: null,
    })
    mocks.getConversations.mockResolvedValue([])
    mocks.createConversation.mockResolvedValue({
      conversation_id: 'conversation-ask',
      student_id: 'student-1',
      teacher_role_id: null,
      title: null,
      status: 'ACTIVE',
      channel: 'TEXT',
      current_page_context: {},
      recent_messages: [],
      conversation_summary: null,
      created_at: '2026-08-19T00:00:00Z',
      updated_at: '2026-08-19T00:00:00Z',
      last_message_at: null,
    })
    mocks.getMessages.mockResolvedValue([])
    mocks.getPreferences.mockResolvedValue({
      voice_preference: { input_enabled: true, tts_enabled: true, volume: 0.8, speed: 1 },
    })
    mocks.startAudioCapture.mockResolvedValue({ stop: vi.fn() })
  })

  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
  })

  it('自由文本提问产生 QUESTION_ASKED，并关联真实会话与当前书/章', async () => {
    // 进入页面即处于 Reader 上下文
    mocks.screenContextValue = {
      route: '/learn/b1/c1',
      pageType: 'chapter_reader',
      bookId: 'b1',
      chapterId: 'c1',
    }
    render(React.createElement(ChatComposer))
    fireEvent.change(screen.getByLabelText('消息输入'), { target: { value: '为什么会这样？' } })
    fireEvent.click(screen.getByRole('button', { name: '发送消息' }))

    await waitFor(() => {
      const asked = mocks.createLearningEvent.mock.calls
        .map((call) => call[0] as Record<string, unknown>)
        .filter((event) => event.event_type === 'QUESTION_ASKED')
      expect(asked.length).toBeGreaterThan(0)
      const latest = asked.at(-1)!
      expect(latest.conversation_id).toBe('conversation-ask')
      expect(latest.book_id).toBe('b1')
      expect(latest.chapter_id).toBe('c1')
    })
  })

  it('录制中卸载组件：VOICE_SESSION_ENDED 恰好发送一次且含真实会话', async () => {
    const conversationId = await new Promise<string>((resolve) => {
      useConversationStore.setState({
        messages: [],
        conversationId: null,
        loaded: false,
      })
      mocks.getConversations.mockResolvedValue([])
      setTimeout(async () => {
        const store = useConversationStore.getState()
        const id = await store.ensureConversationId()
        resolve(id)
      }, 0)
    })

    const { unmount } = render(React.createElement(ChatComposer))
    fireEvent.click(screen.getByRole('button', { name: '语音输入' }))
    await waitFor(() =>
      expect(
        mocks.createLearningEvent.mock.calls.some(
          (call) => (call[0] as Record<string, unknown>).event_type === 'VOICE_SESSION_STARTED',
        ),
      ).toBe(true),
    )

    // 卸载（未手动 stop）：守卫应补发一次 ENDED
    unmount()
    await Promise.resolve()

    const endedCalls = mocks.createLearningEvent.mock.calls.filter(
      (call) =>
        (call[0] as Record<string, unknown>).event_type === 'VOICE_SESSION_ENDED',
    )
    expect(endedCalls).toHaveLength(1)
    expect((endedCalls[0][0] as Record<string, unknown>).conversation_id).toBe(conversationId)
  })

  it('先停止再卸载：ENDED 仍只发送一次', async () => {
    render(React.createElement(ChatComposer))
    fireEvent.click(screen.getByRole('button', { name: '语音输入' }))
    await waitFor(() =>
      expect(
        mocks.createLearningEvent.mock.calls.some(
          (call) => (call[0] as Record<string, unknown>).event_type === 'VOICE_SESSION_STARTED',
        ),
      ).toBe(true),
    )

    // 手动停止（stopVoice → ENDED 第一次）
    fireEvent.click(screen.getByRole('button', { name: '停止录音' }))
    await waitFor(() =>
      expect(
        mocks.createLearningEvent.mock.calls.filter(
          (call) =>
            (call[0] as Record<string, unknown>).event_type === 'VOICE_SESSION_ENDED',
        ),
      ).toHaveLength(1),
    )

    cleanup() // 卸载触发第二次消费尝试 → 守卫必须挡下
    await Promise.resolve()
    expect(
      mocks.createLearningEvent.mock.calls.filter(
        (call) => (call[0] as Record<string, unknown>).event_type === 'VOICE_SESSION_ENDED',
      ),
    ).toHaveLength(1)
  })

  it('TTS_UNAVAILABLE 错误时给出明确的不可用提示', async () => {
    render(React.createElement(ChatComposer))
    // 模拟服务端错误帧：TTS 未配置
    await waitFor(() => expect(mocks.callbacks).toBeTruthy())
    ;(mocks.callbacks as unknown as { onError: (c: string, m: string) => void }).onError(
      'TTS_UNAVAILABLE',
      'TTS 未配置：请设置 TTS_PROVIDER=openai_compatible',
    )
    await waitFor(() =>
      expect(mocks.showToast.mock.calls.some((call) => String(call[0]).includes('TTS_UNAVAILABLE'))).toBe(
        true,
      ),
    )
  })
})
