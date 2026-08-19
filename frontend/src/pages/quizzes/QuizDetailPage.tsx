import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import type {
  QuizAnswer,
  QuizInteraction,
  QuizQuestion,
} from '@/entities/quiz/types'
import { useCompanionStore } from '@/features/companion'
import { useConversationStore } from '@/features/conversation'
import { quizSource } from '@/features/quiz/lib'
import { quizService } from '@/mocks/services'
import type { QuizSessionDetail } from '@/shared/api/quiz-service'

function answerValue(value: Record<string, unknown> | null | undefined): string | null {
  if (!value) return null
  if (typeof value.key === 'string' || typeof value.key === 'number') return String(value.key)
  if (Array.isArray(value.keys)) return value.keys.map(String).join(', ')
  if (typeof value.value === 'string' || typeof value.value === 'number') return String(value.value)
  return null
}

export default function QuizDetailPage() {
  const { quizId = 'q1' } = useParams()
  const runIntent = useConversationStore((state) => state.runIntent)
  const [session, setSession] = useState<QuizSessionDetail | null>(null)
  const [questions, setQuestions] = useState<QuizQuestion[]>([])
  const [answers, setAnswers] = useState<QuizAnswer[]>([])
  const [interactions, setInteractions] = useState<QuizInteraction[]>([])
  const [source, setSource] = useState<{ bookTitle: string; chapterTitle: string } | null>(null)
  const [loading, setLoading] = useState(true)

  // 只读快照：仅 get* 查询，绝不调用 create/submit（0-D D5）
  useEffect(() => {
    let cancelled = false
    void (async () => {
      try {
        const [current, questionList, answerList, interactionList] = await Promise.all([
          quizService.getQuizSession(quizId),
          quizService.getQuestions(quizId),
          quizService.getAnswers(quizId),
          quizService.getInteractions(quizId),
        ])
        if (cancelled) return
        setSession(current)
        setQuestions(current.questions_snapshot?.length ? current.questions_snapshot : questionList)
        setAnswers(answerList)
        setInteractions(interactionList)
        setSource(await quizSource(current.book_id, current.chapter_id))
      } catch {
        if (!cancelled) setSession(null)
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [quizId])

  const askAgain = () => {
    runIntent('quiz-requestion')
    useCompanionStore.getState().setOpen(true)
  }

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
          const correctKey = answerValue(question.correct_answer)
          const correctText =
            question.options.find((option) => option.key === correctKey)?.text ?? correctKey ?? '—'
          const answerKey = answerValue(answer?.submitted_answer)
          const answerText = answer
            ? question.options.find((option) => option.key === answerKey)?.text ?? answerKey
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
                <strong className="font-mono text-[13px] text-fg">{answerKey ?? '—'}</strong>
                <p className="text-[13px] text-fg">{answerText ?? '—'}</p>
              </div>
              <div className="mt-1 grid grid-cols-[84px_28px_minmax(0,1fr)] items-baseline gap-3">
                <span className="font-mono text-[10px] text-muted">正确答案</span>
                <strong className="font-mono text-[13px] text-fg">{correctKey ?? '—'}</strong>
                <p className="text-[13px] text-muted">{correctText}</p>
              </div>
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
              <button
                type="button"
                className="mt-3 rounded-md px-2 py-1 text-[11px] text-muted hover:text-fg hover:underline"
                onClick={askAgain}
              >
                现在再问霜铃
              </button>
            </li>
          )
        })}
      </ol>
      <p className="mt-4 font-mono text-[10px] text-muted">
        共 {summary?.total ?? questions.length} 题 · 只读快照，不重新生成题目 · 技能版本 {session.skill_version}
      </p>
    </section>
  )
}
