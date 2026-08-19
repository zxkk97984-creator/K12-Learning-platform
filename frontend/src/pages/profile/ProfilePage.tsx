import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import type {
  MemoryEvidence,
  ProfileInsight,
  ProfileInsightType,
  StudentEpisode,
  StudentMemory,
} from '@/entities/memory/types'
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

const INSIGHT_TYPE_LABEL: Record<ProfileInsightType, string> = {
  STRENGTH: '优势',
  WEAKNESS: '薄弱',
  UNDERSTANDING: '理解力',
  HABIT: '习惯',
  CHANGE: '变化',
  INTEREST: '兴趣',
}

const SOURCE_LABEL: Record<MemoryEvidence['source_type'], string> = {
  QUIZ: '测验记录',
  LEARNING_SESSION: '学习时段',
  CONVERSATION: '课程对话',
  BOOK_PROGRESS: '阅读进度',
}

const IMPORTANCE_LABEL: Record<StudentEpisode['importance'], string> = {
  LOW: 'LOW',
  MEDIUM: 'MEDIUM',
  HIGH: 'HIGH',
}

function payloadSummary(payload: Record<string, unknown>): string {
  return Object.entries(payload)
    .filter(([key]) => key !== 'dimension')
    .map(([key, value]) => `${key}: ${typeof value === 'string' ? value : JSON.stringify(value)}`)
    .join(' · ')
}

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
  const [historyInsights, setHistoryInsights] = useState<ProfileInsight[]>([])
  const [episodes, setEpisodes] = useState<StudentEpisode[]>([])
  const [memories, setMemories] = useState<StudentMemory[]>([])
  const [expandedInsightId, setExpandedInsightId] = useState<string | null>(null)
  const [insightEvidence, setInsightEvidence] = useState<Record<string, MemoryEvidence[]>>({})
  const [evidenceLoadingId, setEvidenceLoadingId] = useState<string | null>(null)
  const [expandedEpisodeId, setExpandedEpisodeId] = useState<string | null>(null)
  const [episodeDetail, setEpisodeDetail] = useState<Record<string, StudentEpisode>>({})
  const [episodeLoadingId, setEpisodeLoadingId] = useState<string | null>(null)
  const [view, setView] = useState<ProfileView>('student')
  const [docMode, setDocMode] = useState<DocMode>('preview')
  const [mdDraft, setMdDraft] = useState('')
  const [userEdited, setUserEdited] = useState(false)

  const load = useCallback(async () => {
    try {
      const [preference, insightList, historyList, memoryList, episodeList] = await Promise.all([
        studentService.getPreferences(),
        memoryService.getInsights(),
        memoryService.getInsights({ status: 'SUPERSEDED' }),
        memoryService.getMemories(),
        memoryService.getEpisodes(),
      ])
      setPrefs(preference)
      setInsights(insightList)
      setHistoryInsights(historyList)
      setMemories(memoryList)
      setEpisodes(episodeList)
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

  const toggleInsightEvidence = async (insight: ProfileInsight) => {
    if (expandedInsightId === insight.insight_id) {
      setExpandedInsightId(null)
      return
    }
    setExpandedInsightId(insight.insight_id)
    if (insightEvidence[insight.insight_id] || insight.evidence_ids.length === 0) return
    setEvidenceLoadingId(insight.insight_id)
    try {
      const detail = await memoryService.getInsightDetail(insight.insight_id)
      setInsightEvidence((current) => ({
        ...current,
        [insight.insight_id]: detail.evidence,
      }))
    } catch {
      showToast('证据详情暂时不可用')
    } finally {
      setEvidenceLoadingId(null)
    }
  }

  const toggleEpisode = async (episode: StudentEpisode) => {
    if (expandedEpisodeId === episode.episode_id) {
      setExpandedEpisodeId(null)
      return
    }
    setExpandedEpisodeId(episode.episode_id)
    if (episodeDetail[episode.episode_id]) return
    setEpisodeLoadingId(episode.episode_id)
    try {
      const detail = await memoryService.getEpisodeDetail(episode.episode_id)
      setEpisodeDetail((current) => ({ ...current, [episode.episode_id]: detail }))
    } catch {
      showToast('情节详情暂时不可用')
    } finally {
      setEpisodeLoadingId(null)
    }
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
                  {insights.length === 0 ? (
                    <li className="p-4 text-sm text-muted">
                      暂无画像判断。持续学习后，霜铃会在这里给出定性观察。
                    </li>
                  ) : (
                    insights.map((insight) => {
                      const evidence = insightEvidence[insight.insight_id] ?? []
                      const expanded = expandedInsightId === insight.insight_id
                      return (
                        <li key={insight.insight_id} className="border-t border-border p-4 first:border-t-0">
                          <div className="flex flex-wrap items-center gap-2.5">
                            <span className="rounded-full bg-fg-soft px-2 py-0.5 font-mono text-[10px] text-fg">
                              {INSIGHT_TYPE_LABEL[insight.insight_type] ?? insight.insight_type}
                            </span>
                            <strong className="text-sm text-fg">{insight.dimension}</strong>
                            <span className="rounded-full border border-border px-2 py-0.5 font-mono text-[10px] text-muted">
                              {insight.level}
                            </span>
                            <button
                              type="button"
                              aria-expanded={expanded}
                              className="ml-auto text-[11px] text-muted hover:text-fg hover:underline"
                              onClick={() => void toggleInsightEvidence(insight)}
                            >
                              {expanded ? '收起' : '为什么？'}
                            </button>
                          </div>
                          <p className="mt-1.5 text-[13px] text-muted">{insight.description}</p>
                          {expanded ? (
                            <div className="mt-3 border-t border-border pt-3">
                              <p className="font-mono text-[10px] text-muted">判断依据（真实学习记录）：</p>
                              {evidenceLoadingId === insight.insight_id ? (
                                <p className="mt-2 text-[11px] text-muted">正在读取依据…</p>
                              ) : evidence.length === 0 ? (
                                <p className="mt-2 text-[11px] text-muted">暂无证据记录。</p>
                              ) : (
                                <div className="mt-2 grid gap-2">
                                  {evidence.map((item) => (
                                    <div key={item.evidence_id} className="rounded-lg bg-fg-soft p-2 text-[11px] text-muted">
                                      <strong className="text-fg">{SOURCE_LABEL[item.source_type] ?? item.source_type}</strong>
                                      <p className="mt-1">{payloadSummary(item.payload)}</p>
                                      <p className="mt-1 font-mono text-[9px]">
                                        {item.count} 条事件 · {item.last_occurred_at?.slice(0, 10) ?? '时间未知'}
                                      </p>
                                    </div>
                                  ))}
                                </div>
                              )}
                            </div>
                          ) : null}
                        </li>
                      )
                    })
                  )}
                </ul>
              </article>

              <article className="rounded-[14px] border border-border bg-surface p-6">
                <h2 className="border-b border-border pb-3 font-display text-xl text-fg">最近变化</h2>
                <blockquote className="mt-3 border-l-2 border-fg pl-4 font-display text-lg leading-relaxed text-fg">
                  {change?.description ?? '你的问题从“这是什么”走到了“为什么会这样”。'}
                </blockquote>
                <p className="mt-2 font-mono text-[11px] text-muted">
                  依据：{change?.description ?? '最近 3 次对话记录'}
                </p>
              </article>

              <article className="rounded-[14px] border border-border bg-surface p-6">
                <h2 className="border-b border-border pb-3 font-display text-xl text-fg">画像版本记录</h2>
                {historyInsights.length === 0 ? (
                  <p className="mt-3 text-sm text-muted">
                    还没有被新判断替代的历史版本。
                  </p>
                ) : (
                  <ul className="mt-3 grid gap-2">
                    {[...historyInsights]
                      .sort((a, b) => b.valid_from.localeCompare(a.valid_from))
                      .map((insight) => (
                        <li key={insight.insight_id} className="rounded-[10px] bg-fg-soft p-3">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="font-mono text-[10px] text-fg">
                              {INSIGHT_TYPE_LABEL[insight.insight_type] ?? insight.insight_type} · {insight.dimension}
                            </span>
                            <span className="rounded-full border border-border px-2 py-0.5 font-mono text-[9px] text-muted">
                              {insight.level}
                            </span>
                            <time className="ml-auto font-mono text-[10px] text-muted">
                              {insight.valid_until?.slice(0, 10) ?? insight.valid_from.slice(0, 10)}
                            </time>
                          </div>
                          <p className="mt-1.5 text-xs leading-relaxed text-muted">{insight.description}</p>
                        </li>
                      ))}
                  </ul>
                )}
              </article>

              <article className="rounded-[14px] border border-border bg-surface p-6">
                <h2 className="border-b border-border pb-3 font-display text-xl text-fg">学习情节</h2>
                {episodes.length === 0 ? (
                  <p className="mt-3 text-sm text-muted">
                    还没有沉淀出值得记住的学习情节。
                  </p>
                ) : (
                  <ul className="mt-3 grid gap-2">
                    {episodes.map((episode) => {
                      const expanded = expandedEpisodeId === episode.episode_id
                      const detail = episodeDetail[episode.episode_id]
                      return (
                        <li key={episode.episode_id} className="rounded-[10px] border border-border p-3">
                          <div className="flex items-center gap-2">
                            <strong className="text-sm text-fg">{episode.title}</strong>
                            <span
                              className={`rounded-full border px-2 py-0.5 font-mono text-[9px] ${
                                episode.importance === 'HIGH'
                                  ? 'border-fg text-fg'
                                  : episode.importance === 'MEDIUM'
                                    ? 'border-accent text-accent'
                                    : 'border-border text-muted'
                              }`}
                            >
                              {IMPORTANCE_LABEL[episode.importance]}
                            </span>
                            <button
                              type="button"
                              aria-expanded={expanded}
                              className="ml-auto text-[11px] text-muted hover:text-fg hover:underline"
                              onClick={() => void toggleEpisode(episode)}
                            >
                              {expanded ? '收起详情' : '详情'}
                            </button>
                          </div>
                          <p className="mt-1.5 text-[13px] leading-relaxed text-muted">{episode.summary}</p>
                          {expanded ? (
                            <div className="mt-3 border-t border-border pt-3 text-[11px] text-muted">
                              {episodeLoadingId === episode.episode_id ? (
                                <p>正在读取情节详情…</p>
                              ) : (
                                <div className="grid gap-1.5">
                                  <p>
                                    发生时间：<time>{detail?.occurred_at.slice(0, 10) ?? episode.occurred_at.slice(0, 10)}</time>
                                  </p>
                                  <p>关联事件：{detail?.event_ids.length ?? episode.event_ids.length} 条</p>
                                  {detail?.tags.length ? (
                                    <p>标签：{detail.tags.join(' · ')}</p>
                                  ) : null}
                                </div>
                              )}
                            </div>
                          ) : null}
                        </li>
                      )
                    })}
                  </ul>
                )}
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
