import type { ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'

import { useAuth } from '@/features/auth'
import { useScreenContext } from '@/features/screen-context'
import { formatNow, greetingForHour } from './home-time'
import { ContinueLearningCard } from './components/ContinueLearningCard'
import { NextActionCard } from './components/NextActionCard'
import { useHomeData } from './use-home-data'

import { CompanionSprite, useCompanionStore, useTeacherName } from '@/features/companion'
import type { ConversationIntent } from '@/features/conversation'
import { useConversationStore } from '@/features/conversation'
import type { LearningNextAction } from '@/shared/api/recommendation-service'
import type { Recommendation } from '@/shared/api/recommendation-service'

export default function HomePage() {
  const { currentUser } = useAuth()
  const { screenContext } = useScreenContext()
  const teacherName = useTeacherName()
  const navigate = useNavigate()
  const runIntent = useConversationStore((state) => state.runIntent)

  const data = useHomeData(currentUser?.nickname ?? '同学')

  const now = new Date()
  const greeting = greetingForHour(now.getHours())

  const triggerIntent = async (intent: ConversationIntent) => {
    runIntent(intent, undefined, screenContext)
    useCompanionStore.getState().setOpen(true)
  }

  const openNextAction = (action: LearningNextAction) => {
    if (action.type === 'CONTINUE_QUIZ' || action.type === 'REVIEW_QUIZ') {
      if (action.quiz_session_id) navigate(`/quizzes/${action.quiz_session_id}`)
      else navigate('/quizzes')
      return
    }
    if (action.book_id && action.chapter_id) {
      navigate(`/learn/${action.book_id}/${action.chapter_id}`)
      return
    }
    if (action.book_id) {
      navigate(`/books/${action.book_id}`)
      return
    }
    navigate('/library')
  }

  const continuePath = data.progress?.chapter_id
    ? `/learn/${data.progress.book_id}/${data.progress.chapter_id}`
    : '/library'

  const stats = data.stats

  return (
    <section className="py-10">
      {/* 1. 问候与一句今日提示 */}
      <header className="border-b border-border pb-6">
        <p className="font-mono text-xs text-accent">{formatNow(now)}</p>
        <h1 className="mt-2 font-display text-4xl leading-tight text-fg">
          {greeting}，{data.nickname}。
        </h1>
        <p className="mt-3 max-w-[52ch] text-base leading-relaxed text-muted">
          {data.continueChapter ? (
            <>
              <strong className="text-fg">上次停在「{data.continueChapter.title}」。</strong>{' '}
              今天从这里继续，把这个难点讲明白。
            </>
          ) : (
            <>
              {teacherName}会记住你的阅读位置。去书库选一本适合你的，今天学一点新的。
            </>
          )}
        </p>
      </header>

      {/* 2. 唯一主学习卡（2/3）+ 1/3 老师提示 */}
      <div className="mt-6 grid grid-cols-[minmax(0,1.4fr)_minmax(290px,0.6fr)] gap-4 max-md:grid-cols-1">
        <ContinueLearningCard
          loading={data.progressLoading}
          error={data.progressError}
          progress={data.progress}
          book={data.continueBook}
          chapter={data.continueChapter}
          onContinue={() => navigate(continuePath)}
          onStart={() => navigate('/library')}
          onChat={() => void triggerIntent('check-in')}
        />

        <aside className="flex min-h-[232px] flex-col rounded-[22px] border border-border bg-surface p-5" aria-label="老师提示">
          <div className="flex items-center gap-3">
            <div className="grid h-14 w-14 shrink-0 place-items-center overflow-hidden rounded-full bg-fg-soft">
              <CompanionSprite
                state="idle"
                cellWidth={53}
                label={teacherName}
                className="pointer-events-none -translate-x-2 -translate-y-1"
              />
            </div>
            <div>
              <p className="font-mono text-xs text-muted">学习助手</p>
              <strong className="font-display text-lg leading-tight text-fg">{teacherName}</strong>
            </div>
          </div>
          <p className="mt-3 text-sm leading-relaxed text-muted">
            {data.continueChapter
              ? `我会结合你的阅读位置，帮你把「${data.continueChapter.title}」讲明白。`
              : '你可以在阅读时向我提问、要题，我会根据你的进度帮助。'}
          </p>
          <button
            type="button"
            className="mt-auto min-h-[44px] rounded-[10px] border border-border bg-surface px-3 py-2 text-sm text-fg hover:border-fg"
            onClick={() => void triggerIntent('check-in')}
          >
            问问{teacherName}
          </button>
        </aside>
      </div>

      {/* 2.5 §6.1 下一步行动卡（单个行动目标，避免与继续学习/推荐入口重复） */}
      {data.learningNext || data.learningNextLoading ? (
        <div className="mt-4">
          <NextActionCard
            action={data.learningNext ?? undefined}
            loading={data.learningNextLoading}
            onOpen={openNextAction}
          />
        </div>
      ) : null}

      {/* 3. 下一步建议（真实推荐，失败独立降级） */}
      <RecommendationPanel
        recommendations={data.recommendations}
        loading={data.recommendationsLoading}
        error={data.recommendationsError}
        onOpen={(bookId) => navigate(`/books/${bookId}`)}
        onDismiss={(id) => void data.dismissRecommendation(id)}
        onRetry={() => void data.reloadRecommendations()}
      />

      {/* 4. 低权重统计（最多三个与当前阶段相关指标） */}
      {stats ? (
        <div className="mt-4 flex flex-wrap gap-2" data-testid="learning-stats" aria-label="学习统计（来自数据库）">
          {[
            ['学习天数', stats.learning_days],
            ['累计分钟', stats.total_learning_minutes],
            ['测验次数', stats.quiz_count],
          ].map(([label, value]) => (
            <span key={label} className="rounded-full border border-border bg-surface px-3 py-1 text-xs text-muted">
              {label} · <strong className="font-mono text-fg">{value}</strong>
            </span>
          ))}
          <button
            type="button"
            className="text-xs text-accent hover:underline"
            onClick={() => navigate('/profile')}
          >
            查看全部 →
          </button>
        </div>
      ) : null}

      {/* 5. 最近一次学习变化 */}
      <div className="mt-4 grid grid-cols-3 gap-4 max-md:grid-cols-1">
        <MiniPanel title="最近变化 · 时间线">
          {data.episodes.length === 0 ? (
            <p className="mt-3 text-sm leading-relaxed text-muted" data-testid="episodes-empty">
              {data.episodesError ? '变化加载失败，稍后重试。' : '暂无学习情节——完成一章后，这里会出现你的第一条时间线。'}
            </p>
          ) : null}
          <div className="mt-3 border-l border-border pl-3.5">
            {data.episodes.slice(0, 2).map((episode) => (
              <div key={episode.episode_id} className="relative mb-3 last:mb-0">
                <time className="font-mono text-xs text-muted">{episode.occurred_at.slice(5, 10)}</time>
                <p className="mt-0.5 text-sm text-fg">{episode.title}</p>
              </div>
            ))}
          </div>
          <button type="button" className="mt-3 text-sm text-fg hover:text-accent" onClick={() => navigate('/profile')}>
            查看完整变化 →
          </button>
        </MiniPanel>

        <MiniPanel title="最近测验">
          {data.quizzes.length === 0 ? (
            <p className="mt-3 text-sm leading-relaxed text-muted" data-testid="quizzes-empty">
              {data.quizzesError ? '测验记录加载失败，稍后重试。' : '暂无测验记录——在阅读中向我「要一道题」即可开始第一次小测。'}
            </p>
          ) : null}
          <div className="mt-3 space-y-3">
            {data.quizzes.slice(0, 2).map((quiz) => (
              <div key={quiz.quiz_session_id} className="border-t border-border pt-2.5">
                <div className="flex items-baseline justify-between gap-2">
                  <strong className="text-sm text-fg">{quiz.title}</strong>
                  <span className="font-mono text-xs text-fg">
                    {quiz.result_summary ? `${quiz.result_summary.correct} / ${quiz.result_summary.total}` : '—'}
                  </span>
                </div>
                <p className="mt-0.5 text-xs text-muted">
                  {quiz.created_at.slice(5, 10)} · 使用 {quiz.result_summary?.hints_used ?? 0} 次提示
                </p>
              </div>
            ))}
          </div>
          <button type="button" className="mt-3 text-sm text-fg hover:text-accent" onClick={() => navigate('/quizzes')}>
            查看全部 →
          </button>
        </MiniPanel>

        <MiniPanel title="AI 记得什么" dark>
          {data.memories.length === 0 ? (
            <p className="mt-3 text-sm leading-relaxed text-surface/80" data-testid="memories-empty">
              我还没有记住关于你的稳定线索——继续学习，我会慢慢认识你。
            </p>
          ) : (
            <>
              <blockquote className="mt-3 max-w-[20ch] font-display text-lg leading-snug text-surface">
                {data.memories[0]?.content}
              </blockquote>
              <button type="button" className="mt-3 text-sm text-surface hover:text-accent" onClick={() => void triggerIntent('memory')}>
                问问为什么 →
              </button>
            </>
          )}
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
  onRetry,
}: {
  recommendations: Recommendation[]
  loading: boolean
  error: boolean
  onOpen: (bookId: string) => void
  onDismiss: (recommendationId: string) => void
  onRetry: () => void
}) {
  const teacherName = useTeacherName()
  return (
    <aside className="mt-6 rounded-[22px] border border-border bg-surface p-5" aria-label="下一步建议">
      <div className="flex items-baseline justify-between">
        <h2 className="font-display text-xl leading-snug text-fg">{teacherName}的下一步建议</h2>
        <span className="text-xs text-muted">基于你的真实学习记录</span>
      </div>

      {loading ? (
        <p role="status" className="mt-4 text-sm text-muted">正在准备今日推荐…</p>
      ) : error ? (
        <div role="status" className="mt-4 text-sm text-muted">
          <p>推荐暂时不可用，稍后再试。</p>
          <button type="button" className="mt-2 text-sm text-accent hover:underline" onClick={onRetry}>
            重试
          </button>
        </div>
      ) : recommendations.length === 0 ? (
        <p role="status" className="mt-4 text-sm leading-relaxed text-muted">
          <span data-testid="home-recommend-empty">暂时没有新的推荐。</span> 去书库找找想学的内容吧。
        </p>
      ) : (
        <div className="mt-4 space-y-3">
          {recommendations.map((recommendation) => {
            const typeLabel =
              recommendation.recommendation_type === 'REVIEW_WEAK'
                ? '复习建议'
                : recommendation.recommendation_type === 'READ_NEXT'
                  ? '下一步阅读'
                  : '继续学习'
            const interactive = recommendation.related_book_id !== null
            return (
              <div key={recommendation.recommendation_id} className="rounded-[12px] border border-border bg-surface p-3">
                <span className="text-xs text-muted">{typeLabel}</span>
                <strong className="mt-1 block text-base leading-snug text-fg">{recommendation.title}</strong>
                <span className="mt-1.5 block text-sm leading-relaxed text-muted">{recommendation.description}</span>
                <span className="mt-2 block border-t border-border pt-2 text-sm leading-relaxed text-muted">
                  <strong className="text-fg">为什么推荐？</strong> {recommendation.reason}
                </span>
                <span className="mt-1.5 flex items-center justify-between">
                  <em className="text-xs not-italic text-muted/70">依据你的学习与记忆数据</em>
                  <button
                    type="button"
                    data-testid={`home-dismiss-${recommendation.recommendation_id}`}
                    aria-label={`不感兴趣：${recommendation.title}`}
                    className="rounded-full border border-border px-2.5 py-1 text-xs text-muted hover:border-fg hover:text-fg"
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
                    className="mt-2 block w-full min-h-[44px] rounded-[10px] border border-border bg-bg py-1.5 text-sm text-fg hover:border-fg"
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

function MiniPanel({ title, children, dark = false }: { title: string; children?: ReactNode; dark?: boolean }) {
  return (
    <article className={`min-h-[152px] rounded-[22px] border p-4 ${dark ? 'border-fg bg-fg text-surface' : 'border-border bg-surface'}`}>
      <span className={`font-mono text-xs ${dark ? 'text-surface/60' : 'text-muted'}`}>{title}</span>
      {children}
    </article>
  )
}
