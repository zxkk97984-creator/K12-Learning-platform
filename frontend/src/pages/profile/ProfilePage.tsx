import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import type { ProfileInsight, StudentMemory } from '@/entities/memory/types'
import type { StudentPreference, StudentProfile } from '@/entities/student/types'
import { useAuth } from '@/features/auth'
import { useCompanionStore } from '@/features/companion'
import { useConversationStore } from '@/features/conversation'
import { useToastStore } from '@/features/feedback'
import { MemoryList } from '@/features/memory'
import { memoryService, studentService } from '@/mocks/services'

type ProfileView = 'student' | 'archive'
type DocMode = 'preview' | 'edit'

const STYLE_LABEL: Record<string, string> = {
  EXAMPLE_BASED: '例子优先',
  VISUAL: '图解优先',
  STORY: '故事优先',
  DIRECT_DEFINITION: '直接定义',
  STEP_BY_STEP: '分步骤',
  CODE: '代码示例',
  INTERACTIVE: '互动提问',
}

const DIFFICULTY_LABEL: Record<string, string> = { EASY: '简单', MEDIUM: '中等', HARD: '较难' }
const LENGTH_LABEL: Record<string, string> = { SHORT: '短时、多轮', MEDIUM: '中等时长', LONG: '较长连续' }

function buildMarkdown(profile: StudentProfile, prefs: StudentPreference, insights: ProfileInsight[]): string {
  const lines = [
    '---',
    `name: ${profile.nickname}`,
    `grade: 初二 · 8 年级`,
    `updated: ${profile.updated_at.slice(0, 10)}`,
    `preferred_explanation_style: example_based   # ${STYLE_LABEL[prefs.preferred_explanation_style] ?? prefs.preferred_explanation_style}`,
    `preferred_difficulty: ${prefs.preferred_difficulty.toLowerCase()}   # ${DIFFICULTY_LABEL[prefs.preferred_difficulty] ?? ''}`,
    `preferred_session_length: ${prefs.preferred_session_length.toLowerCase()}   # ${LENGTH_LABEL[prefs.preferred_session_length] ?? ''}`,
    '---',
    '',
    '## AI 对我的认识',
    '',
    '你更喜欢先从生活里的例子出发，再回到抽象概念。遇到较长理论时，你有时会失去耐心；但一旦把概念放进具体情境，你会很快追问“为什么”。',
    '',
    '## 当前表现',
    ...insights.map(
      (insight) => `- ${insight.dimension} —— ${insight.level}：${insight.description}`,
    ),
    '',
    '## 最近变化',
    '',
    '> 你的问题从“这是什么”走到了“为什么会这样”。',
  ]
  return lines.join('\n')
}

export default function ProfilePage() {
  const runIntent = useConversationStore((state) => state.runIntent)
  const showToast = useToastStore((state) => state.showToast)
  const { currentUser } = useAuth()
  const [profile, setProfile] = useState<StudentProfile | null>(null)
  const [prefs, setPrefs] = useState<StudentPreference | null>(null)
  const [insights, setInsights] = useState<ProfileInsight[]>([])
  const [memories, setMemories] = useState<StudentMemory[]>([])
  const [view, setView] = useState<ProfileView>('student')
  const [docMode, setDocMode] = useState<DocMode>('preview')
  const [mdDraft, setMdDraft] = useState('')
  const [userEdited, setUserEdited] = useState(false)

  const load = useCallback(async () => {
    try {
      const [preference, insightList, memoryList] = await Promise.all([
        studentService.getPreferences(),
        memoryService.getInsights(),
        memoryService.getMemories(),
      ])
      setPrefs(preference)
      setInsights(insightList)
      setMemories(memoryList)
    } catch {
      // 后端不可用时降级为空态
    }
  }, [])

  useEffect(() => {
    setProfile(currentUser)
    if (currentUser) void load()
  }, [currentUser, load])

  const openArchive = () => {
    setView('archive')
    setDocMode('preview')
  }

  const triggerIntent = (intent: Parameters<typeof runIntent>[0]) => {
    runIntent(intent)
    useCompanionStore.getState().setOpen(true)
  }

  const saveDoc = () => {
    if (!mdDraft.trim()) {
      showToast('文件不能为空')
      return
    }
    setUserEdited(true)
    setDocMode('preview')
    showToast('已保存，霜铃下次讲解会参考新画像')
  }

  if (!profile || !prefs) {
    return (
      <section className="py-10">
        <p className="font-mono text-xs uppercase tracking-widest text-accent">成长 · AI 学习画像</p>
        <h1 className="mt-3 font-display text-4xl text-fg">霜铃眼中的你。</h1>
        <p className="mt-4 text-sm text-muted">
          学习画像暂不可用
          {!currentUser ? (
            <Link to="/login" className="ml-2 text-accent hover:underline">
              去登录 →
            </Link>
          ) : null}
        </p>
      </section>
    )
  }

  const overview = insights.find((item) => item.dimension === 'explanation_preference')
  const concept = insights.find((item) => item.dimension === 'concept')
  const transfer = insights.find((item) => item.dimension === 'application_transfer')
  const question = insights.find((item) => item.dimension === 'questioning_habit')
  const change = insights.find((item) => item.dimension === 'questioning_habit' && item.insight_type === 'CHANGE')

  return (
    <section className="py-10">
      <p className="font-mono text-xs uppercase tracking-widest text-accent">成长 · AI 学习画像</p>
      <h1 className="mt-3 font-display text-4xl text-fg">霜铃眼中的你。</h1>

      <div className="mt-6 grid grid-cols-[minmax(0,1fr)_260px] items-start gap-4 max-md:grid-cols-1">
        <div className="grid gap-4">
          {view === 'student' ? (
            <>
              <article className="rounded-[14px] border border-border bg-surface p-6">
                <span className="font-mono text-[10px] text-muted">AI 对我的认识</span>
                <blockquote className="mt-3 max-w-[24ch] font-display text-2xl leading-snug text-fg">
                  你更喜欢从生活中的例子开始，再回到抽象概念。
                </blockquote>
                <p className="mt-3 max-w-[60ch] text-sm leading-relaxed text-muted">
                  遇到较长理论时，你有时会失去耐心；但一旦把概念放进具体情境，你会很快追问“为什么”。
                </p>
                <p className="mt-2 font-mono text-[11px] text-muted">
                  {overview ? `依据：${overview.description}` : '依据：最近 3 次课程对话、2 次测验和 1 次章节学习记录'}
                </p>
              </article>

              <article className="rounded-[14px] border border-border bg-surface p-6">
                <h2 className="border-b border-border pb-3 font-display text-xl text-fg">学习方式</h2>
                <div className="mt-3 grid grid-cols-3 gap-3 max-sm:grid-cols-1">
                  {[
                    ['讲解偏好', STYLE_LABEL[prefs.preferred_explanation_style] ?? prefs.preferred_explanation_style],
                    ['学习节奏', LENGTH_LABEL[prefs.preferred_session_length] ?? prefs.preferred_session_length],
                    ['难度偏好', DIFFICULTY_LABEL[prefs.preferred_difficulty] ?? prefs.preferred_difficulty],
                  ].map(([label, value]) => (
                    <div key={label} className="rounded-[10px] border border-border p-3">
                      <span className="font-mono text-[9px] tracking-wider text-muted">{label}</span>
                      <p className="mt-1.5 text-sm font-semibold text-fg">{value}</p>
                    </div>
                  ))}
                </div>
              </article>

              <article className="rounded-[14px] border border-border bg-surface p-6">
                <h2 className="border-b border-border pb-3 font-display text-xl text-fg">当前表现</h2>
                <ul className="mt-3 overflow-hidden rounded-[10px] border border-border">
                  {[
                    { insight: concept, label: '概念理解', intent: 'profile-why-transfer' },
                    { insight: transfer, label: '应用迁移', intent: 'profile-why-transfer' },
                    { insight: question, label: '提问习惯', intent: 'profile-why-question' },
                  ].map(({ insight, label, intent }) => (
                    <li key={label} className="border-t border-border p-4 first:border-t-0">
                      <div className="flex items-center gap-2.5">
                        <strong className="text-sm text-fg">{label}</strong>
                        <span className="rounded-full border border-border px-2 py-0.5 font-mono text-[10px] text-muted">
                          {insight?.level ?? '—'}
                        </span>
                        <button
                          type="button"
                          className="ml-auto text-[11px] text-muted hover:text-fg hover:underline"
                          onClick={() => triggerIntent(intent as Parameters<typeof runIntent>[0])}
                        >
                          问霜铃 →
                        </button>
                      </div>
                      <p className="mt-1.5 text-[13px] text-muted">{insight?.description ?? '暂无判断'}</p>
                    </li>
                  ))}
                </ul>
              </article>

              <article className="rounded-[14px] border border-border bg-surface p-6">
                <h2 className="border-b border-border pb-3 font-display text-xl text-fg">最近变化</h2>
                <blockquote className="mt-3 border-l-2 border-fg pl-4 font-display text-lg leading-relaxed text-fg">
                  你的问题从“这是什么”走到了“为什么会这样”。
                </blockquote>
                <p className="mt-2 font-mono text-[11px] text-muted">
                  依据：{change?.description ?? '最近 3 次对话记录'}
                </p>
              </article>
            </>
          ) : (
            <article className="overflow-hidden rounded-[14px] border border-border bg-surface">
              <div className="flex min-h-[56px] flex-wrap items-center justify-between gap-3 border-b border-border px-4 py-2.5">
                <div>
                  <span className="font-mono text-xs font-semibold text-fg">xiaoming.agent.md</span>
                  {userEdited ? (
                    <span className="ml-2 rounded-full border border-border bg-fg-soft px-2 py-0.5 font-mono text-[9px] text-fg">
                      用户修改
                    </span>
                  ) : null}
                  <span className="ml-2 text-[11px] text-muted">
                    {userEdited ? '最近更新 刚刚 · 你修改过' : `由霜铃维护 · 最近更新 ${profile.updated_at.slice(5, 10)}`}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    className="rounded-md px-2 py-1 text-[11px] text-muted hover:bg-fg-soft hover:text-fg"
                    onClick={() => showToast('已导出 xiaoming.agent.md（演示）')}
                  >
                    导出
                  </button>
                  <div className="flex gap-0.5 rounded-[10px] bg-fg-soft p-0.5">
                    {(['preview', 'edit'] as const).map((mode) => (
                      <button
                        key={mode}
                        type="button"
                        aria-selected={docMode === mode}
                        onClick={() => setDocMode(mode)}
                        className={`rounded-lg px-3 py-1 text-xs ${
                          docMode === mode ? 'bg-surface text-fg shadow-sm' : 'text-muted hover:text-fg'
                        }`}
                      >
                        {mode === 'preview' ? '预览' : '编辑'}
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              {docMode === 'preview' ? (
                <div className="px-6 py-4 font-mono text-xs leading-relaxed text-fg">
                  <span className="block text-muted opacity-55">---</span>
                  {[
                    ['name', profile.nickname],
                    ['grade', '初二 · 8 年级'],
                    ['updated', profile.updated_at.slice(0, 10)],
                    ['preferred_explanation_style', 'example_based'],
                    ['preferred_difficulty', 'medium'],
                    ['preferred_session_length', 'short'],
                  ].map(([key, value]) => (
                    <span key={key} className="block">
                      {key}: <span className="text-fg">{value}</span>
                    </span>
                  ))}
                  <span className="block text-muted opacity-55">---</span>
                  <div className="mt-4 space-y-4">
                    <section>
                      <h3 className="font-display text-lg text-fg">## AI 对我的认识</h3>
                      <p className="mt-2 text-[13px] text-muted">你更喜欢先从生活里的例子出发，再回到抽象概念。</p>
                    </section>
                    <section>
                      <h3 className="font-display text-lg text-fg">## 当前表现</h3>
                      <ul className="mt-2 space-y-2">
                        {insights.map((insight) => (
                          <li key={insight.insight_id} className="text-[13px] text-muted">
                            <span className="text-fg">{insight.dimension}</span> —— {insight.level}：{insight.description}
                          </li>
                        ))}
                      </ul>
                    </section>
                    <section>
                      <h3 className="font-display text-lg text-fg">## 最近变化</h3>
                      <blockquote className="mt-2 border-l-2 border-fg pl-3 text-sm text-fg">
                        你的问题从“这是什么”走到了“为什么会这样”。
                      </blockquote>
                    </section>
                  </div>
                </div>
              ) : (
                <div className="p-4">
                  <textarea
                    value={mdDraft || buildMarkdown(profile, prefs, insights)}
                    onChange={(event) => setMdDraft(event.target.value)}
                    rows={16}
                    spellCheck={false}
                    aria-label="画像文件源码"
                    className="w-full resize-y rounded-[10px] border border-border bg-surface p-3 font-mono text-xs leading-relaxed text-fg outline-none focus:border-fg"
                  />
                  <div className="mt-3 flex justify-end gap-2">
                    <button
                      type="button"
                      className="rounded-[10px] px-3 py-1.5 text-xs text-muted hover:bg-fg-soft hover:text-fg"
                      onClick={() => {
                        setMdDraft('')
                        setDocMode('preview')
                      }}
                    >
                      放弃修改
                    </button>
                    <button
                      type="button"
                      className="rounded-[10px] border border-border bg-surface px-3 py-1.5 text-xs text-fg hover:border-fg"
                      onClick={saveDoc}
                    >
                      保存修改
                    </button>
                  </div>
                </div>
              )}

              <div className="border-t border-border px-4 py-3">
                <p className="font-mono text-[10px] text-muted">修改记录</p>
                <ul className="mt-2 grid gap-2 text-xs">
                  <li><time className="font-mono text-[10px] text-muted">08-18</time><span className="ml-2">依据 3 次对话更新「最近变化」</span></li>
                  <li><time className="font-mono text-[10px] text-muted">08-15</time><span className="ml-2">确认「提问习惯」越来越具体</span></li>
                  <li><time className="font-mono text-[10px] text-muted">08-12</time><span className="ml-2">新增「应用迁移」· 仍需观察</span></li>
                </ul>
                <button
                  type="button"
                  className="mt-3 text-[11px] text-muted hover:text-fg hover:underline"
                  onClick={() => setView('student')}
                >
                  ← 返回学生视图
                </button>
              </div>
            </article>
          )}
        </div>

        <aside className="grid content-start gap-4 rounded-[14px] border border-border bg-surface p-4">
          <div>
            <p className="font-mono text-[10px] text-muted">证据覆盖</p>
            <p className="mt-2 text-xs leading-relaxed text-muted">
              所有结论来自真实学习记录：3 次课程对话 · 2 次测验 · 1 次章节学习。没有分数。
            </p>
          </div>
          <div>
            <p className="font-mono text-[10px] text-muted">霜铃记得这些</p>
            <div className="mt-2">
              <MemoryList memories={memories} onChanged={() => void load()} />
            </div>
          </div>
          <div className="grid gap-2">
            <button
              type="button"
              className="rounded-[10px] bg-accent px-3 py-2 text-xs text-surface"
              onClick={() => triggerIntent('profile-question')}
            >
              问霜铃：为什么这样判断？
            </button>
            <button
              type="button"
              className="rounded-[10px] px-3 py-2 text-xs text-muted hover:bg-fg-soft hover:text-fg"
              onClick={openArchive}
            >
              查看原始 AI 档案
            </button>
          </div>
        </aside>
      </div>
    </section>
  )
}
