import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'

import type { Book, BookProgress, Chapter } from '@/entities/book/types'
import type { StudentEpisode, StudentMemory } from '@/entities/memory/types'
import type { QuizSession } from '@/entities/quiz/types'
import { CompanionSprite, useCompanionStore } from '@/features/companion'
import type { ConversationIntent } from '@/features/conversation'
import { useConversationStore } from '@/features/conversation'
import { homeRecommendation } from '@/mocks/data/recommendations'
import { contentService, memoryService, quizService, studentService } from '@/mocks/services'

export default function HomePage() {
  const navigate = useNavigate()
  const runIntent = useConversationStore((state) => state.runIntent)
  const [nickname, setNickname] = useState('小明')
  const [progress, setProgress] = useState<BookProgress | null>(null)
  const [continueBook, setContinueBook] = useState<Book | null>(null)
  const [continueChapter, setContinueChapter] = useState<Chapter | null>(null)
  const [progressLoading, setProgressLoading] = useState(true)
  const [episodes, setEpisodes] = useState<StudentEpisode[]>([])
  const [memories, setMemories] = useState<StudentMemory[]>([])
  const [quizzes, setQuizzes] = useState<QuizSession[]>([])
  const [demoNew, setDemoNew] = useState(false)

  useEffect(() => {
    void (async () => {
      // 2-D：studentService 已走真实后端；单调用容错，保证其余 Mock 数据在断网/后端未起时仍可展示
      try {
        const me = await studentService.getMe()
        setNickname(me.nickname)
      } catch {
        // 保持默认昵称「小明」
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

  useEffect(() => {
    document.body.classList.toggle('demo-new', demoNew)
    return () => document.body.classList.remove('demo-new')
  }, [demoNew])

  const triggerIntent = (intent: ConversationIntent) => {
    runIntent(intent)
    useCompanionStore.getState().setOpen(true)
  }

  const continuePath =
    progress?.chapter_id ? `/learn/${progress.book_id}/${progress.chapter_id}` : '/library'
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
    : '暂无阅读记录'

  return (
    <section className="py-10">
      <button
        type="button"
        className="mb-4 rounded-full border border-border px-3 py-1 text-[11px] text-muted hover:border-fg hover:text-fg"
        aria-pressed={demoNew}
        onClick={() => setDemoNew((current) => !current)}
      >
        新同学视角（demo-new）
      </button>

      <div className="flex flex-wrap items-end justify-between gap-6 border-b border-border pb-6">
        <div>
          <p className="font-mono text-xs text-accent">周二 19:42</p>
          <h1 className="mt-2 max-w-[15ch] font-display text-5xl leading-none text-fg">
            晚上好，{nickname}。
          </h1>
          <p className="mt-4 max-w-[52ch] text-[15px] leading-relaxed text-muted">
            <strong className="text-fg">
              {continueChapter ? `上次停在「${continueChapter.title}」。` : '还没有继续学习记录。'}
            </strong>{' '}
            {continueChapter
              ? '今天从这里继续，把这个难点讲明白。'
              : '去书库选一本书，霜铃会记住你的阅读位置。'}
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
              onClick={() => triggerIntent('check-in')}
            >
              和霜铃聊两句
            </button>
          </div>
        </div>

        <aside className="w-[318px] max-w-full rounded-[14px] border border-border bg-surface p-4">
          <div className="flex items-center gap-3">
            <div className="grid h-14 w-14 shrink-0 place-items-center overflow-hidden rounded-full bg-fg-soft">
              <CompanionSprite
                state="idle"
                cellWidth={53}
                label="霜铃在线"
                className="pointer-events-none -translate-x-2 -translate-y-1"
              />
            </div>
            <div>
              <p className="font-mono text-[10px] text-muted">AI 教师 · 在线</p>
              <strong className="font-display text-lg leading-tight text-fg">霜铃正在陪你学习</strong>
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
            onClick={() => triggerIntent('presence-ask')}
          >
            问问霜铃
          </button>
        </aside>
      </div>

      <div className="mt-6 grid grid-cols-[minmax(0,1.4fr)_minmax(290px,0.6fr)] gap-4 max-md:grid-cols-1">
        <article className="overflow-hidden rounded-[22px] border border-border bg-surface">
          {demoNew ? (
            <div className="grid min-h-[232px] place-items-center p-8 text-center">
              <div>
                <p className="font-mono text-[10px] text-muted">还没有开始学习</p>
                <h3 className="mt-2 font-display text-xl text-fg">让霜铃推荐第一本书</h3>
                <p className="mt-2 max-w-[40ch] text-[13px] text-muted">
                  霜铃会根据你的年级和兴趣，从 12 本书里挑一本最合适的。
                </p>
                <button
                  type="button"
                  className="mt-4 rounded-[10px] bg-accent px-4 py-2 text-xs text-surface"
                  onClick={() => triggerIntent('today-learn')}
                >
                  问问霜铃
                </button>
              </div>
            </div>
          ) : progressLoading ? (
            <div className="grid min-h-[232px] place-items-center p-8 text-center text-sm text-muted">
              正在恢复继续学习记录…
            </div>
          ) : progress && continueBook && continueChapter ? (
            <div className="grid min-h-[232px] grid-cols-[164px_minmax(0,1fr)] max-sm:grid-cols-[112px_minmax(0,1fr)]">
              <div className="flex min-h-[232px] flex-col justify-between bg-fg p-5 text-surface">
                <span className="font-mono text-[10px] text-surface/70">{continueBook.tags[0] ?? '学习内容'}</span>
                <span className="font-display text-2xl leading-tight">{continueBook.title}</span>
                <span className="text-[11px] text-surface/60">{continueBook.description ?? '从上次位置继续学习'}</span>
              </div>
              <div className="flex flex-col justify-between gap-4 p-5">
                <div>
                  <p className="font-mono text-[10px] text-muted">
                    继续第 {continueChapter.chapter_order} 章 · {continueChapter.title}
                  </p>
                  <h3 className="mt-1.5 font-display text-2xl leading-tight text-fg">
                    {continueChapter.title}
                  </h3>
                  <p className="mt-2 max-w-[48ch] text-[13px] leading-relaxed text-muted">
                    {continueChapter.summary ?? '从上次阅读位置继续，霜铃会陪你把这一节讲明白。'}
                  </p>
                </div>
                <div className="flex flex-wrap items-end justify-between gap-4">
                  <div className="min-w-[180px]">
                    <div className="h-1 overflow-hidden rounded-full bg-border">
                      <span
                        className="block h-full bg-fg"
                        style={{ width: `${progress.position_percent}%` }}
                      />
                    </div>
                    <p className="mt-2 font-mono text-[10px] tracking-wide text-muted">
                      阅读位置 {progress.position_percent}% · 最近阅读 {progressTime}
                    </p>
                  </div>
                  <button
                    type="button"
                    className="rounded-[10px] bg-accent px-3.5 py-2 text-xs text-surface"
                    onClick={() => navigate(continuePath)}
                  >
                    {continueLabel}
                  </button>
                </div>
              </div>
            </div>
          ) : (
            <div className="grid min-h-[232px] place-items-center p-8 text-center">
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

        <aside className="flex min-h-[232px] flex-col justify-between rounded-[22px] border border-border bg-surface p-5">
          <div>
            <p className="font-mono text-[10px] text-accent">霜铃的下一步建议</p>
            <h2 className="mt-3 max-w-[16ch] font-display text-xl leading-snug text-fg">
              {homeRecommendation.title}
            </h2>
            <p className="mt-2 text-[13px] leading-relaxed text-muted">{homeRecommendation.copy}</p>
          </div>
          <div className="border-t border-border pt-3 text-xs text-muted">
            <strong className="block text-fg">{homeRecommendation.evidenceTitle}</strong>
            <span className="mt-1 block">{homeRecommendation.evidence}</span>
          </div>
        </aside>
      </div>

      <div className="mt-4 grid grid-cols-3 gap-4 max-md:grid-cols-1">
        {demoNew ? (
          <>
            <MiniPanel
              title="最近变化"
              quote="等你完成几节课，这里会出现你的学习变化。"
              actionLabel="开始第一课 →"
              onAction={() => navigate('/library')}
            />
            <MiniPanel
              title="最近测验"
              quote="还没有测验记录，先从书库选一节开始吧。"
              actionLabel="去书库开始学习 →"
              onAction={() => navigate('/library')}
            />
            <MiniPanel
              title="AI 记得什么"
              quote="我们才刚认识，我还在慢慢了解你。"
              actionLabel="开始第一课 →"
              onAction={() => navigate('/library')}
            />
          </>
        ) : (
          <>
            <MiniPanel title="最近变化 · 时间线">
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
              <blockquote className="mt-3 max-w-[20ch] font-display text-lg leading-snug text-surface">
                {memories[0]?.content ?? '“你喜欢通过例子学习。”'}
              </blockquote>
              <div className="mt-3 flex flex-wrap gap-1.5">
                {(memories[0]?.tags ?? ['例子优先']).map((tag) => (
                  <span key={tag} className="rounded-full border border-surface/30 px-2 py-0.5 text-[10px] text-surface">
                    {tag}
                  </span>
                ))}
              </div>
              <button
                type="button"
                className="mt-3 text-xs text-surface hover:text-accent"
                onClick={() => triggerIntent('memory')}
              >
                问问为什么 →
              </button>
            </MiniPanel>
          </>
        )}
      </div>
    </section>
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
