import { useEffect, useState } from 'react'
import { Link, useLocation, useParams } from 'react-router-dom'

import type {
  QuizAnswer,
  QuizInteraction,
  QuizQuestion,
} from '@/entities/quiz/types'
import { useCompanionStore } from '@/features/companion'
import { useConversationStore } from '@/features/conversation'
import { derivePageType } from '@/features/screen-context/types'
import { quizSource } from '@/features/quiz/lib'
import { quizService } from '@/shared/services'
import type { QuizSessionDetail } from '@/shared/api/quiz-service'

/** 归一化单选/多选/判断/填空的答案键（多选为多个 key）。 */
function answerKeys(value: Record<string, unknown> | null | undefined): string[] {
  if (!value) return []
  if (Array.isArray(value.keys)) return value.keys.map(String)
  if (Array.isArray(value.values)) return value.values.map(String)
  if (value.key !== undefined && value.key !== null) return [String(value.key)]
  if (value.value !== undefined && value.value !== null) return [String(value.value)]
  return []
}

/** 从答案键映射到选项文本（找不到时回退到键本身）。 */
function optionText(question: QuizQuestion, key: string): string {
  return question.options.find((option) => option.key === key)?.text ?? key
}

export default function QuizDetailPage() {
  const { quizId = 'q1' } = useParams()
  const { pathname } = useLocation()
  const runIntent = useConversationStore((state) => state.runIntent)
  const [session, setSession] = useState<QuizSessionDetail | null>(null)
  const [questions, setQuestions] = useState<QuizQuestion[]>([])
  const [answers, setAnswers] = useState<QuizAnswer[]>([])
  const [interactions, setInteractions] = useState<QuizInteraction[]>([])
  const [source, setSource] = useState<{ bookTitle: string; chapterTitle: string } | null>(null)
  const [loading, setLoading] = useState(true)

  // 只读快照：仅 get* 查询，绝不调用 create/submit（0-D D5）；单来源失败不抹掉整份列表。
  useEffect(() => {
    let cancelled = false
    void (async () => {
      const [current] = await Promise.allSettled([quizService.getQuizSession(quizId)])
      if (current.status === 'rejected') {
        if (!cancelled) {
          setSession(null)
          setLoading(false)
        }
        return
      }
      const sessionValue = current.value
      try {
        const [questionList, answerList, interactionList] = await Promise.all([
          quizService.getQuestions(quizId),
          quizService.getAnswers(quizId),
          quizService.getInteractions(quizId),
        ])
        if (cancelled) return
        setSession(sessionValue)
        setQuestions(
          sessionValue.questions_snapshot?.length
            ? sessionValue.questions_snapshot
            : questionList,
        )
        setAnswers(answerList)
        setInteractions(interactionList)
        setSource(await quizSource(sessionValue.book_id, sessionValue.chapter_id))
      } catch {
        if (!cancelled) {
          // 局部来源失败：仍展示会话主体，不丢整份列表。
          setSession(sessionValue)
          setQuestions(sessionValue.questions_snapshot ?? [])
          setAnswers([])
          setInteractions([])
          setSource(await quizSource(sessionValue.book_id, sessionValue.chapter_id).catch(() => null))
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [quizId])

  if (loading) {
    return <p className="py-10 text-center text-sm text-muted">正在加载答卷…</p>
  }
  if (!session) {
    return (
      <section className="py-10">
        <Link to="/quizzes" className="text-sm text-muted hover:text-fg">
          ← 返回测验记录
        </Link>
        <p className="mt-6 text-sm text-muted">答卷不存在。</p>
      </section>
    )
  }

  const summary = session.result_summary
  const pageType = derivePageType(pathname)
  const baseContext = { route: pathname, pageType, quizSessionId: session.quiz_session_id }

  const explainQuestion = (questionId: string) => {
    runIntent('explain-question', undefined, { ...baseContext, questionId })
    useCompanionStore.getState().setOpen(true)
  }
  const practiseAgain = () => {
    runIntent('quiz-requestion', undefined, baseContext)
    useCompanionStore.getState().setOpen(true)
  }

  return (
    <section className="py-10">
      <Link to="/quizzes" className="text-sm text-muted hover:text-fg">
        ← 返回测验记录
      </Link>
      <div className="mt-4 border-b border-fg pb-6">
        <h1 className="font-display text-4xl text-fg">{session.title}</h1>
        <p className="mt-2 text-sm text-muted">
          《{source?.bookTitle ?? '—'}》 · {source?.chapterTitle ?? '—'} · {session.created_at.slice(0, 10)} ·{' '}
          {session.quiz_kind === 'CHAPTER_QUIZ' ? '章节测验' : 'AI 小测'}
        </p>
        <div className="mt-4 flex flex-wrap items-center gap-4">
          <span className="font-mono text-sm text-fg">
            {summary ? `${summary.correct} / ${summary.total}` : '—'}
          </span>
          {session.ai_feedback ? (
            <blockquote className="min-w-[260px] flex-1 border-l-2 border-fg pl-3 font-display text-sm leading-relaxed text-fg">
              {session.ai_feedback}
            </blockquote>
          ) : null}
        </div>
      </div>

      <ol className="list-none">
        {questions.map((question) => {
          const answer = [...answers]
            .reverse()
            .find((item) => item.question_id === question.question_id)
          const hintInteractions = interactions.filter(
            (item) =>
              item.question_id === question.question_id && item.interaction_type === 'HINT_RESPONSE',
          )
          const correctKeys = answerKeys(question.correct_answer)
          const correctTexts = correctKeys.length
            ? correctKeys.map((key) => optionText(question, key)).join('；')
            : '—'
          const answerKeysList = answerKeys(answer?.submitted_answer)
          const answerTexts = answer
            ? answerKeysList.length
              ? answerKeysList.map((key) => optionText(question, key)).join('；')
              : answerKeysList.join('；')
            : null
          return (
            <li key={question.question_id} className="border-b border-border py-6">
              <div className="flex items-center gap-3">
                <span className="font-mono text-[10px] text-muted">第 {question.question_order} 题</span>
                {answer ? (
                  <span
                    className={`rounded-full px-2 py-0.5 font-mono text-[10px] ${
                      answer.is_correct
                        ? 'bg-fg-soft text-fg'
                        : 'border border-muted text-muted'
                    }`}
                  >
                    {answer.is_correct ? '正确' : '错误'}
                  </span>
                ) : (
                  <span className="rounded-full border border-border px-2 py-0.5 font-mono text-[10px] text-muted">
                    未记录
                  </span>
                )}
              </div>
              <p className="mt-3 max-w-[60ch] font-display text-xl leading-relaxed text-fg">
                {question.stem}
              </p>
              <div className="mt-2.5 grid grid-cols-[84px_28px_minmax(0,1fr)] items-baseline gap-3">
                <span className="font-mono text-[10px] text-muted">你的答案</span>
                <strong className="font-mono text-[13px] text-fg">
                  {answerKeysList.join(', ') || '—'}
                </strong>
                <p className="text-[13px] text-fg">{answerTexts ?? '—'}</p>
              </div>
              <div className="mt-1 grid grid-cols-[84px_28px_minmax(0,1fr)] items-baseline gap-3">
                <span className="font-mono text-[10px] text-muted">正确答案</span>
                <strong className="font-mono text-[13px] text-fg">{correctKeys.join(', ') || '—'}</strong>
                <p className="text-[13px] text-muted">{correctTexts}</p>
              </div>
              {question.explanation ? (
                <div className="mt-3 rounded-[10px] border border-border bg-fg-soft p-3.5">
                  <p className="font-mono text-[10px] tracking-wider text-muted">解析</p>
                  <p className="mt-1 text-[13px] leading-relaxed text-fg">{question.explanation}</p>
                </div>
              ) : null}
              {hintInteractions.length > 0 ? (
                <div className="mt-3 rounded-[10px] bg-fg-soft p-3.5">
                  {hintInteractions.map((interaction) => (
                    <p key={interaction.interaction_id} className="text-xs leading-relaxed text-muted">
                      你当时使用了 <b className="text-fg">第 {String(interaction.payload.hint_level)} 级提示</b>
                      ：{String(interaction.payload.hint_text)}
                    </p>
                  ))}
                </div>
              ) : null}
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  className="rounded-md border border-border px-2 py-1 text-[11px] text-fg hover:border-fg"
                  onClick={() => explainQuestion(question.question_id)}
                >
                  讲解这道题
                </button>
                <button
                  type="button"
                  className="rounded-md px-2 py-1 text-[11px] text-muted hover:text-fg hover:underline"
                  onClick={practiseAgain}
                >
                  再练一道类似的
                </button>
              </div>
            </li>
          )
        })}
      </ol>
      <p className="mt-4 font-mono text-[10px] text-muted">
        共 {summary?.total ?? questions.length} 题 · 只读快照，不重新生成题目
      </p>
    </section>
  )
}
