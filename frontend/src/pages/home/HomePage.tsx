import { useCallback, useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'

import { useAuth } from '@/features/auth'
import { useScreenContext } from '@/features/screen-context'
import { formatNow } from './home-time'

import type { Book, BookProgress, Chapter } from '@/entities/book/types'
import type { StudentEpisode, StudentMemory } from '@/entities/memory/types'
import type { QuizSession } from '@/entities/quiz/types'
import { CompanionSprite, useCompanionStore, useTeacherName } from '@/features/companion'
import type { ConversationIntent } from '@/features/conversation'
import { useConversationStore } from '@/features/conversation'
import type { Recommendation } from '@/shared/api/recommendation-service'
import {
  contentService,
  memoryService,
  quizService,
  recommendationService,
  studentService,
} from '@/shared/services'

export default function HomePage() {
  const { currentUser } = useAuth()
  const { screenContext } = useScreenContext()
  const teacherName = useTeacherName()
  const navigate = useNavigate()
  const runIntent = useConversationStore((state) => state.runIntent)
    // Phase 4 整改：昵称来自真实登录用户；加载失败显示通用占位
  const [nickname, setNickname] = useState(() => currentUser?.nickname ?? '同学')
  const [progress, setProgress] = useState<BookProgress | null>(null)
  // Phase 4 验收恢复：继续学习卡加载/空态/真实进度三态
  const [progressLoading, setProgressLoading] = useState(true)
  const [continueBook, setContinueBook] = useState<Book | null>(null)
  const [continueChapter, setContinueChapter] = useState<Chapter | null>(null)
  const [episodes, setEpisodes] = useState<StudentEpisode[]>([])
  const [memories, setMemories] = useState<StudentMemory[]>([])
  const [quizzes, setQuizzes] = useState<QuizSession[]>([])
  const [recommendations, setRecommendations] = useState<Recommendation[]>([])
  const [recommendationsLoading, setRecommendationsLoading] = useState(true)
  const [recommendationsError, setRecommendationsError] = useState(false)
  const [stats, setStats] = useState<{
    learning_days: number
    total_learning_minutes: number
    completed_books: number
    completed_chapters: number
    quiz_count: number
  } | null>(null)

  useEffect(() => {
    void (async () => {
      // 2-D：studentService 已走真实后端；单调用容错，保证其余 Mock 数据在断网/后端未起时仍可展示
      try {
        const me = await studentService.getMe()
        setNickname(me.nickname)
        setStats({
          learning_days: me.learning_days,
          total_learning_minutes: me.total_learning_minutes,
          completed_books: me.completed_books,
          completed_chapters: me.completed_chapters,
          quiz_count: me.quiz_count,
        })
      } catch {
        // 保持占位昵称与空统计（不得伪造）
      }
      try {
        const progressItems = await contentService.getProgress()
        const latest = progressItems
          .filter((item) => item.chapter_id)
          .sort((left, right) => {
            const leftTime = left.last_read_at ? Date.parse(left.last_read_at) : 0
            const rightTime = right.last_read_at ? Date.parse(right.last_read_at) : 0
            return rightTime - leftTime
          })[0] ?? null
        setProgress(latest)
        if (latest?.chapter_id) {
          const [book, chapter] = await Promise.all([
            contentService.getBook(latest.book_id),
            contentService.getChapter(latest.chapter_id),
          ])
          setContinueBook(book)
          setContinueChapter(chapter)
        } else {
          setContinueBook(null)
          setContinueChapter(null)
        }
      } catch {
        setProgress(null)
        setContinueBook(null)
        setContinueChapter(null)
      } finally {
        setProgressLoading(false)
      }
      try {
        setEpisodes(await memoryService.getEpisodes())
      } catch {
        setEpisodes([])
      }
      try {
        setMemories(await memoryService.getMemories())
      } catch {
        setMemories([])
      }
      try {
        setQuizzes(await quizService.getQuizSessions())
      } catch {
        setQuizzes([])
      }
    })()
  }, [])

  const loadRecommendationList = useCallback(async () => {
    setRecommendationsLoading(true)
    try {
      const items = await recommendationService.getRecommendations()
      setRecommendations(items.filter((item) => item.status === 'ACTIVE').slice(0, 3))
      setRecommendationsError(false)
    } catch {
      setRecommendations([])
      setRecommendationsError(true)
    } finally {
      setRecommendationsLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadRecommendationList()
  }, [loadRecommendationList])

  // Phase 3/4：真实忽略——dismiss 后重新拉取列表，被忽略卡片即从首页移除
  const dismissHomeRecommendation = useCallback(
    async (recommendationId: string) => {
      try {
        await recommendationService.dismissRecommendation(recommendationId)
      } catch {
        // 失败静默，下次刷新重试
      }
      await loadRecommendationList()
    },
    [loadRecommendationList],
  )

  const triggerIntent = async (intent: ConversationIntent) => {
    runIntent(intent, undefined, screenContext)
    useCompanionStore.getState().setOpen(true)
  }

  const continuePath =
    progress?.chapter_id ? `/learn/${progress.book_id}/${progress.chapter_id}` : '/library'
  // Phase 4 验收恢复：按钮文案与最近阅读时间
  const continueLabel = continueChapter
    ? `继续第 ${continueChapter.chapter_order} 章 →`
    : '去书库开始学习 →'
  const progressTime = progress?.last_read_at
    ? new Date(progress.last_read_at).toLocaleString('zh-CN', {
        month: 'numeric',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      })
    : null

  return (
    <section className="py-10">

      <div className="flex flex-wrap items-end justify-between gap-6 border-b border-border pb-6">
        <div>
          <p className="font-mono text-xs text-accent">{formatNow(new Date())}</p>
          <h1 className="mt-2 max-w-[15ch] font-display text-5xl leading-none text-fg">
            晚上好，{nickname}。
          </h1>
          <p className="mt-4 max-w-[52ch] text-[15px] leading-relaxed text-muted">
            <strong className="text-fg">
              {continueChapter ? `上次停在「${continueChapter.title}」。` : '还没有继续学习记录。'}
            </strong>{' '}
            {continueChapter
              ? '今天从这里继续，把这个难点讲明白。'
              : `去书库选一本书，${teacherName}会记住你的阅读位置。`}
          </p>
          <div className="mt-5 flex flex-wrap gap-2.5">
            <button
              type="button"
              className="rounded-[10px] bg-accent px-4 py-2.5 text-sm text-surface hover:bg-accent/85"
              onClick={() => navigate(continuePath)}
            >
              {continueChapter ? '继续学习 →' : '开始学习 →'}
            </button>
            <button
              type="button"
              className="rounded-[10px] border border-border bg-surface px-4 py-2.5 text-sm text-fg hover:border-fg"
              onClick={() => void triggerIntent('check-in')}
            >
              和{teacherName}聊两句
            </button>
          </div>
        </div>

        <aside className="w-[318px] max-w-full rounded-[14px] border border-border bg-surface p-4">
          <div className="flex items-center gap-3">
            <div className="grid h-14 w-14 shrink-0 place-items-center overflow-hidden rounded-full bg-fg-soft">
              <CompanionSprite
                state="idle"
                cellWidth={53}
                label={`${teacherName}在线`}
                className="pointer-events-none -translate-x-2 -translate-y-1"
              />
            </div>
            <div>
              <p className="font-mono text-[10px] text-muted">AI 教师 · 在线</p>
              <strong className="font-display text-lg leading-tight text-fg">{teacherName}正在陪你学习</strong>
            </div>
          </div>
          <dl className="mt-3 border-t border-border">
            {[
              ['当前关注', continueChapter?.title ?? '等待你的第一节课'],
              ['最近发现', continueBook?.title ?? '学习记录会在这里出现。'],
              ['状态', '正在参考最近学习记录'],
            ].map(([label, value]) => (
              <div key={label} className="grid grid-cols-[62px_1fr] items-baseline gap-2.5 border-b border-border py-2 last:border-b-0">
                <dt className="font-mono text-[9px] tracking-wide text-muted">{label}</dt>
                <dd className="m-0 text-[13px] leading-snug text-fg">{value}</dd>
              </div>
            ))}
          </dl>
          <button
            type="button"
            className="mt-3 rounded-[10px] border border-border bg-surface px-3 py-2 text-xs text-fg hover:border-fg"
            onClick={() => void triggerIntent('presence-ask')}
          >
            问问{teacherName}
          </button>
        </aside>
      </div>

      {stats ? (
        <div
          className="mb-6 flex flex-wrap gap-2"
          data-testid="learning-stats"
          aria-label="学习统计（来自数据库）"
        >
          {[
            ['学习天数', stats.learning_days],
            ['累计分钟', stats.total_learning_minutes],
            ['读完章节', stats.completed_chapters],
            ['完成书籍', stats.completed_books],
            ['测验次数', stats.quiz_count],
          ].map(([label, value]) => (
            <span key={label} className="rounded-full border border-border bg-surface px-2.5 py-1 text-[10px] text-muted">
              {label} · <strong className="font-mono text-fg">{value}</strong>
            </span>
          ))}
        </div>
      ) : null}

      <div className="mt-6 grid grid-cols-[minmax(0,1.4fr)_minmax(290px,0.6fr)] gap-4 max-md:grid-cols-1">
        <article className="overflow-hidden rounded-[22px] border border-border bg-surface">
          {progressLoading ? (
            // 加载中：不闪空态
            <div className="grid min-h-[232px] place-items-center p-8 text-center" data-testid="continue-loading">
              <p className="text-sm text-muted">正在恢复继续学习记录…</p>
            </div>
          ) : progress && continueBook && continueChapter ? (
            <>
              {/* 书封 */}
              <div
                className="grid min-h-[132px] place-items-center bg-fg p-5 text-center"
                style={{ backgroundColor: 'var(--color-fg)' }}
              >
                <strong className="font-display text-2xl leading-tight text-surface">
                  {continueBook.title}
                </strong>
                {continueBook.description ? (
                  <span className="mt-1 block max-w-[42ch] text-[11px] text-surface/70">
                    {continueBook.description}
                  </span>
                ) : null}
              </div>
              {/* 章节进度 */}
              <div className="p-5">
                <div className="flex items-baseline justify-between gap-3">
                  <h2 className="font-display text-xl leading-snug text-fg">
                    第 {continueChapter.chapter_order} 章 · {continueChapter.title}
                  </h2>
                  {progress?.position_percent !== undefined ? (
                    <span className="shrink-0 font-mono text-[10px] text-muted">
                      {progress.position_percent}%
                    </span>
                  ) : null}
                </div>
                {continueChapter.summary ? (
                  <p className="mt-2 max-w-[64ch] text-[13px] leading-relaxed text-muted">
                    {continueChapter.summary}
                  </p>
                ) : null}
                <p className="mt-3 font-mono text-[10px] text-muted">
                  {progressTime ? `最近阅读 ${progressTime}` : '暂无阅读时间'}
                </p>
                <div className="mt-4 flex flex-wrap gap-2.5">
                  <button
                    type="button"
                    data-testid="continue-learning"
                    className="rounded-[10px] bg-accent px-4 py-2.5 text-sm text-surface hover:bg-accent/85"
                    onClick={() => navigate(continuePath)}
                  >
                    {continueLabel}
                  </button>
                  <button
                    type="button"
                    aria-label={`和${teacherName}聊两句`}
                    className="rounded-[10px] border border-border bg-surface px-4 py-2.5 text-sm text-fg hover:border-fg"
                    onClick={() => void triggerIntent('check-in')}
                  >
                    和{teacherName}聊两句
                  </button>
                </div>
              </div>
            </>
          ) : (
            // 空态：无进度或加载失败
            <div className="grid min-h-[232px] place-items-center p-8 text-center" data-testid="continue-empty">
              <div>
                <p className="font-mono text-[10px] text-muted">还没有开始学习</p>
                <h3 className="mt-2 font-display text-xl text-fg">从书库选一本书开始</h3>
                <p className="mt-2 max-w-[40ch] text-[13px] text-muted">
                  阅读器会自动保存你最近停下来的章节。
                </p>
                <button
                  type="button"
                  className="mt-4 rounded-[10px] bg-accent px-4 py-2 text-xs text-surface"
                  onClick={() => navigate('/library')}
                >
                  去书库看看
                </button>
              </div>
            </div>
          )}
        </article>

        <RecommendationPanel
          recommendations={recommendations}
          loading={recommendationsLoading}
          error={recommendationsError}
          onOpen={(bookId) => navigate(`/books/${bookId}`)}
          onDismiss={(id) => void dismissHomeRecommendation(id)}
        />
      </div>

      <div className="mt-4 grid grid-cols-3 gap-4 max-md:grid-cols-1">
                    <MiniPanel title="最近变化 · 时间线">
              {episodes.length === 0 ? (
                <p className="mt-3 text-xs leading-relaxed text-muted" data-testid="episodes-empty">
                  暂无学习情节——完成一章后，这里会出现你的第一条时间线。
                </p>
              ) : null}
              <div className="mt-3 border-l border-border pl-3.5">
                {episodes.slice(0, 2).map((episode) => (
                  <div key={episode.episode_id} className="relative mb-3 last:mb-0">
                    <time className="font-mono text-[9px] text-muted">
                      {episode.occurred_at.slice(5, 10)}
                    </time>
                    <p className="mt-0.5 text-xs text-fg">{episode.title}</p>
                  </div>
                ))}
              </div>
              <button
                type="button"
                className="mt-3 text-xs text-fg hover:text-accent"
                onClick={() => navigate('/profile')}
              >
                查看完整变化 →
              </button>
            </MiniPanel>
            <MiniPanel title="最近测验">
              {quizzes.length === 0 ? (
                <p className="mt-3 text-xs leading-relaxed text-muted" data-testid="quizzes-empty">
                  暂无测验记录——在阅读中向我「要一道题」即可开始第一次小测。
                </p>
              ) : null}
              <div className="mt-3 space-y-3">
                {quizzes.slice(0, 2).map((quiz) => (
                  <div key={quiz.quiz_session_id} className="border-t border-border pt-2.5">
                    <div className="flex items-baseline justify-between gap-2">
                      <strong className="text-[13px] text-fg">{quiz.title}</strong>
                      <span className="font-mono text-[10px] text-fg">
                        {quiz.result_summary
                          ? `${quiz.result_summary.correct} / ${quiz.result_summary.total}`
                          : '—'}
                      </span>
                    </div>
                    <p className="mt-0.5 text-[11px] text-muted">
                      {quiz.created_at.slice(5, 10)} · 使用 {quiz.result_summary?.hints_used ?? 0} 次提示
                    </p>
                  </div>
                ))}
              </div>
              <button
                type="button"
                className="mt-3 text-xs text-fg hover:text-accent"
                onClick={() => navigate('/quizzes')}
              >
                查看全部 →
              </button>
            </MiniPanel>
            <MiniPanel title="AI 记得什么" dark>
              {memories.length === 0 ? (
                <p className="mt-3 text-xs leading-relaxed text-surface/80" data-testid="memories-empty">
                  我还没有记住关于你的稳定线索——继续学习，我会慢慢认识你。
                </p>
              ) : (
                <>
                  <blockquote className="mt-3 max-w-[20ch] font-display text-lg leading-snug text-surface">
                    {memories[0]?.content}
                  </blockquote>
                  {(memories[0]?.tags.length ?? 0) > 0 ? (
                    <div className="mt-3 flex flex-wrap gap-1.5">
                      {memories[0].tags.map((tag) => (
                        <span key={tag} className="rounded-full border border-surface/30 px-2 py-0.5 text-[10px] text-surface">
                          {tag}
                        </span>
                      ))}
                    </div>
                  ) : null}
                </>
              )}
              <button
                type="button"
                className="mt-3 text-xs text-surface hover:text-accent"
                onClick={() => void triggerIntent('memory')}
              >
                问问为什么 →
              </button>
            </MiniPanel>
      </div>
    </section>
  )
}

function RecommendationPanel({
  recommendations,
  loading,
  error,
  onOpen,
  onDismiss,
}: {
  recommendations: Recommendation[]
  loading: boolean
  error: boolean
  onOpen: (bookId: string) => void
  onDismiss: (recommendationId: string) => void
}) {
  const teacherName = useTeacherName()
  return (
    <aside
      className="flex min-h-[232px] flex-col rounded-[22px] border border-border bg-surface p-5"
      aria-label="今日推荐"
    >
      <div>
        <p className="font-mono text-[10px] text-accent">{teacherName}的下一步建议</p>
        <h2 className="mt-3 font-display text-xl leading-snug text-fg">今日推荐</h2>
      </div>

      {loading ? (
        <div role="status" className="mt-5 text-[13px] text-muted">
          正在准备今日推荐…
        </div>
      ) : error ? (
        <div role="status" className="mt-5 text-[13px] text-muted">
          推荐暂时不可用，稍后再试。
        </div>
      ) : recommendations.length === 0 ? (
        <div role="status" className="mt-5 text-[13px] leading-relaxed text-muted">
          <p>暂时没有新的推荐。</p>
          <p className="mt-1">去书库找找想学的内容吧。</p>
        </div>
      ) : (
        <div className="mt-4 space-y-3">
          {recommendations.map((recommendation) => {
            // Phase 5-B-II 缺陷 1：外层为普通容器；打开书籍与「不感兴趣」
            // 是两个兄弟按钮，消除 button 嵌套 button。
            const typeLabel =
              recommendation.recommendation_type === 'REVIEW_WEAK'
                ? '复习建议'
                : recommendation.recommendation_type === 'READ_NEXT'
                  ? '下一步阅读'
                  : '继续学习'
            const interactive = recommendation.related_book_id !== null

            return (
              <div
                key={recommendation.recommendation_id}
                className="rounded-[12px] border border-border bg-surface p-3"
              >
                <span className="font-mono text-[10px] text-muted">{typeLabel}</span>
                <strong className="mt-1 block text-[15px] leading-snug text-fg">
                  {recommendation.title}
                </strong>
                <span className="mt-1.5 block text-[12px] leading-relaxed text-muted">
                  {recommendation.description}
                </span>
                <span className="mt-2 block border-t border-border pt-2 text-[11px] leading-relaxed text-muted">
                  <strong className="text-fg">为什么推荐？</strong> {recommendation.reason}
                </span>
                <span className="mt-1.5 flex items-center justify-between">
                  <em className="text-[10px] not-italic text-muted/70">
                    依据你的学习与记忆数据
                  </em>
                  <button
                    type="button"
                    data-testid={`home-dismiss-${recommendation.recommendation_id}`}
                    aria-label={`不感兴趣：${recommendation.title}`}
                    className="rounded-full border border-border px-2 py-0.5 text-[10px] text-muted hover:border-fg hover:text-fg"
                    onClick={() => onDismiss(recommendation.recommendation_id)}
                  >
                    不感兴趣
                  </button>
                </span>
                {interactive ? (
                  <button
                    type="button"
                    aria-label={`打开推荐：${recommendation.title}`}
                    onClick={() => onOpen(recommendation.related_book_id as string)}
                    className="mt-2 block w-full rounded-[10px] border border-border bg-bg py-1.5 text-xs text-fg hover:border-fg"
                  >
                    打开这本书 →
                  </button>
                ) : null}
              </div>
            )
          })}
        </div>
      )}
    </aside>
  )
}

function MiniPanel({
  title,
  children,
  dark = false,
  quote,
  actionLabel,
  onAction,
}: {
  title: string
  children?: ReactNode
  dark?: boolean
  quote?: string
  actionLabel?: string
  onAction?: () => void
}) {
  return (
    <article
      className={`min-h-[152px] rounded-[22px] border p-4 ${
        dark ? 'border-fg bg-fg text-surface' : 'border-border bg-surface'
      }`}
    >
      <span className={`font-mono text-[10px] ${dark ? 'text-surface/60' : 'text-muted'}`}>{title}</span>
      {quote ? (
        <blockquote className="mt-3 max-w-[20ch] font-display text-lg leading-snug text-fg">
          {quote}
        </blockquote>
      ) : null}
      {children}
      {actionLabel && onAction ? (
        <button
          type="button"
          className="mt-3 text-xs text-fg hover:text-accent"
          onClick={onAction}
        >
          {actionLabel}
        </button>
      ) : null}
    </article>
  )
}
