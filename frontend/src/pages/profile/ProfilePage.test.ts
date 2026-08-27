// @vitest-environment jsdom
import React from 'react'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { ProfileInsight, StudentEpisode } from '@/entities/memory/types'
import type { Stage, StudentPreference } from '@/entities/student/types'

const runIntent = vi.fn()

vi.mock('@/shared/services', () => ({
  studentService: {
    getPreferences: vi.fn(),
    getMe: vi.fn(),
    updateMe: vi.fn(),
    login: vi.fn(),
    logout: vi.fn(),
    updatePreferences: vi.fn(),
  },
  memoryService: {
    getMemories: vi.fn(),
    getInsights: vi.fn(),
    getInsightDetail: vi.fn(),
    getEpisodes: vi.fn(),
    getEpisodeDetail: vi.fn(),
    getEvidence: vi.fn(),
    updateMemory: vi.fn(),
    getInsight: vi.fn(),
  },
}))

vi.mock('@/features/auth', () => {
  const currentUser = {
      student_id: 'student-1',
      nickname: '小明',
      avatar_url: null,
      grade: 8,
      stage: 'JUNIOR' as Stage,
      language: 'zh-CN',
      learning_goal: '期末 AI 成绩提升',
      current_teacher_role_id: null,
      learning_days: 1,
      total_learning_minutes: 30,
      completed_books: 0,
      completed_chapters: 0,
      quiz_count: 0,
      created_at: '2026-08-01T00:00:00Z',
      updated_at: '2026-08-19T00:00:00Z',
  }
  return {
    useAuth: () => ({ currentUser }),
  }
})

vi.mock('@/features/companion', () => ({
  useCompanionStore: () => ({
    setAiState: vi.fn(),
    setOpen: vi.fn(),
  }),
  useTeacherName: () => '霜铃',
}))

vi.mock('@/features/conversation', () => ({
  useConversationStore: (selector: (state: unknown) => unknown) =>
    selector({ runIntent }),
}))

const feedbackMocks = vi.hoisted(() => ({ showToast: vi.fn() }))
vi.mock('@/features/feedback', () => ({
  useToastStore: (selector: (state: { showToast: unknown }) => unknown) =>
    selector({ showToast: feedbackMocks.showToast }),
}))

import { memoryService, studentService } from '@/shared/services'
import ProfilePage from './ProfilePage'
import { ScreenContextProvider } from '@/features/screen-context'

const preference: StudentPreference = {
  preference_id: 'pref-1',
  student_id: 'student-1',
  preferred_explanation_style: 'EXAMPLE_BASED',
  preferred_difficulty: 'MEDIUM',
  preferred_session_length: 'SHORT',
  voice_preference: { input_enabled: false, tts_enabled: false, volume: 1, speed: 1 },
  active_questioning_enabled: true,
  daily_learning_minutes: 30,
  evidence_ids: [],
  updated_at: '2026-08-19T00:00:00Z',
}

const insight: ProfileInsight = {
  insight_id: 'insight-1',
  student_id: 'student-1',
  insight_type: 'UNDERSTANDING',
  dimension: 'concept_understanding',
  level: '较强',
  description: '在多次练习中能稳定答对。',
  evidence_ids: ['evidence-1'],
  status: 'ACTIVE',
  valid_from: '2026-08-19T00:00:00Z',
  valid_until: null,
  rule_version: 'profile-rule-v1',
  model_info: { provider: 'rule', model: 'profile-rule-v1' },
  created_at: '2026-08-19T00:00:00Z',
  updated_at: '2026-08-19T00:00:00Z',
}

const episode: StudentEpisode = {
  episode_id: 'episode-1',
  student_id: 'student-1',
  title: '完成了一组随堂练习',
  summary: '在随堂练习中多次作答。',
  occurred_at: '2026-08-19T00:00:00Z',
  event_ids: ['event-1'],
  book_id: null,
  chapter_id: null,
  knowledge_point_ids: [],
  importance: 'MEDIUM',
  tags: ['quiz'],
  created_at: '2026-08-19T00:00:00Z',
}

function renderProfile() {
  return render(
    React.createElement(
      ScreenContextProvider,
      null,
      React.createElement(MemoryRouter, null, React.createElement(ProfilePage)),
    ),
  )
}

describe('ProfilePage insights/episodes rendering', () => {
  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  beforeEach(() => {
    vi.mocked(studentService.getPreferences).mockResolvedValue(preference)
    vi.mocked(memoryService.getMemories).mockResolvedValue([])
    vi.mocked(memoryService.getInsights).mockImplementation(async (params) =>
      params?.status === 'SUPERSEDED' ? [] : [insight],
    )
    vi.mocked(memoryService.getEpisodes).mockResolvedValue([episode])
    vi.mocked(memoryService.getEpisodeDetail).mockResolvedValue(episode)
  })

  it('展示 5 档定性 level，且页面不出现百分比', async () => {
    renderProfile()

    await waitFor(() =>
      expect(screen.getByRole('heading', { name: '霜铃眼中的你。' })).toBeTruthy(),
    )
    expect(screen.getByText('较强')).toBeTruthy()
    expect(screen.queryByText(/%/)).toBeNull()
  })

  it('点击「为什么？」展开真实证据', async () => {
    vi.mocked(memoryService.getInsightDetail).mockResolvedValue({
      insight,
      evidence: [
        {
          evidence_id: 'evidence-1',
          student_id: 'student-1',
          source_type: 'QUIZ',
          event_ids: ['event-1'],
          payload: { correct_count: 2, dimension: 'quiz_performance' },
          count: 2,
          first_occurred_at: '2026-08-19T00:00:00Z',
          last_occurred_at: '2026-08-19T00:00:00Z',
          derived_at: '2026-08-19T00:00:00Z',
          rule_version: 'memory-rule-v1',
        },
      ],
    })
    renderProfile()

    await waitFor(() => expect(screen.getByRole('button', { name: '为什么？' })).toBeTruthy())
    fireEvent.click(screen.getByRole('button', { name: '为什么？' }))

    await waitFor(() =>
      expect(screen.getByText('判断依据（真实学习记录）：')).toBeTruthy(),
    )
    expect(screen.getByText('测验记录')).toBeTruthy()
    expect(memoryService.getInsightDetail).toHaveBeenCalledWith('insight-1')
  })

  it('changelog 无历史版本时展示空态，episodes 展示列表', async () => {
    vi.mocked(memoryService.getInsights).mockImplementation(async (params) => {
      if (params?.status === 'SUPERSEDED') return []
      return [insight]
    })
    renderProfile()

    await waitFor(() =>
      expect(screen.getByText('还没有被新判断替代的历史版本。')).toBeTruthy(),
    )
    expect(screen.getByText('学习情节')).toBeTruthy()
    expect(screen.getByText('完成了一组随堂练习')).toBeTruthy()
  })
})

describe('ProfilePage 学习目标持久化（Phase 4 整改 3）', () => {
  const currentUser = {
    student_id: 'student-1',
    nickname: '小明',
    avatar_url: null,
    grade: 8,
    stage: 'JUNIOR' as Stage,
    language: 'zh-CN',
    learning_goal: '期末 AI 成绩提升',
    current_teacher_role_id: null,
    learning_days: 1,
    total_learning_minutes: 30,
    completed_books: 0,
    completed_chapters: 0,
    quiz_count: 0,
    created_at: '2026-08-01T00:00:00Z',
    updated_at: '2026-08-19T00:00:00Z',
  }

  beforeEach(() => {
    cleanup()
    vi.clearAllMocks()
    vi.mocked(studentService.getPreferences).mockResolvedValue(preference)
    vi.mocked(memoryService.getMemories).mockResolvedValue([])
    vi.mocked(memoryService.getInsights).mockResolvedValue([])
    vi.mocked(memoryService.getInsights).mockResolvedValue([])
    vi.mocked(memoryService.getEpisodes).mockResolvedValue([])
    vi.mocked(studentService.updateMe).mockResolvedValue({
      ...currentUser,
      learning_goal: '期末 AI 成绩提升',
      grade: 9,
    })
    vi.mocked(studentService.updatePreferences).mockResolvedValue(preference)
  })

  it('当前用户 learning_goal 非空时，编辑草稿首次加载即显示', async () => {
    const withGoal = { ...currentUser, learning_goal: '期末 AI 成绩提升' }
    vi.mocked(studentService.updateMe).mockResolvedValue(withGoal)
    // getMe 由 AuthProvider 提供 currentUser；此处直接断言渲染输入框取值逻辑：
    renderProfile()
    // 切到「AI 档案」视图并进入编辑模式
    fireEvent.click(screen.getByRole('tab', { name: 'AI 档案' }))
    fireEvent.click(await screen.findByRole('button', { name: '编辑' }))
    const input = await screen.findByLabelText(/学习目标/)
    // load() 后 profile 来自 currentUser（learning_goal 已设置）
    await waitFor(() => expect((input as HTMLInputElement).value).toBe('期末 AI 成绩提升'))
  })

  it('保存成功后以 updateMe 返回值刷新档案（输入框显示返回的新目标）', async () => {
    const savedProfile = { ...currentUser, learning_goal: '冲刺省级竞赛', grade: 9 }
    vi.mocked(studentService.updateMe).mockResolvedValue(savedProfile)

    renderProfile()
    // 切到「AI 档案」→ 编辑
    fireEvent.click(screen.getByRole('tab', { name: 'AI 档案' }))
    fireEvent.click(await screen.findByRole('button', { name: '编辑' }))
    const input = (await screen.findByLabelText(/学习目标/)) as HTMLInputElement

    // 输入一个与初始值不同的目标并保存
    fireEvent.change(input, { target: { value: '冲刺省级竞赛' } })
    fireEvent.click(await screen.findByRole('button', { name: '保存修改' }))

    await waitFor(() =>
      expect(vi.mocked(studentService.updateMe)).toHaveBeenCalledWith(
        expect.objectContaining({ learning_goal: '冲刺省级竞赛' }),
      ),
    )
    // 保存后组件切回预览；预览 frontmatter 显示 updateMe 返回的最新档案值
    const previewLine = await screen.findByText(/learning_goal:/)
    expect(previewLine.parentElement?.textContent).toContain('冲刺省级竞赛')
    // 本用例未修改偏好 frontmatter，故不触发偏好接口（真实条件持久化）
    expect(vi.mocked(studentService.updateMe)).toHaveBeenCalledTimes(1)
  })
})
