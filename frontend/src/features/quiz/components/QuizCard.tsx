import { useCallback, useEffect, useState } from 'react'

import type {
  QuizAnswer,
  QuizQuestion,
  QuizQuestionType,
  QuizSession,
} from '@/entities/quiz/types'
import { useCompanionStore, useTeacherName } from '@/features/companion'
import { useConversationStore } from '@/features/conversation'
import { quizService } from '@/shared/services'

interface QuizCardProps {
  sessionId: string
}

interface FeedbackState {
  isCorrect: boolean
  isFinal: boolean
  explanation: string | null
  attemptNo: number
}

const TYPE_LABEL: Record<QuizQuestionType, string> = {
  SINGLE_CHOICE: '单选',
  MULTIPLE_CHOICE: '多选',
  TRUE_FALSE: '判断',
  FILL_BLANK: '填空',
}

function answerFor(
  question: QuizQuestion,
  selectedKeys: string[],
  textValue: string,
): Record<string, unknown> | null {
  switch (question.question_type) {
    case 'SINGLE_CHOICE':
    case 'TRUE_FALSE':
      return selectedKeys.length === 1 ? { key: selectedKeys[0] } : null
    case 'MULTIPLE_CHOICE':
      return selectedKeys.length > 0 ? { keys: [...selectedKeys].sort() } : null
    case 'FILL_BLANK':
      return textValue.trim() ? { value: textValue.trim() } : null
    default:
      return null
  }
}

/** 对话内交互式测验卡：多题逐题推进、四种题型、服务端判分（Phase 2-B）。 */
export function QuizCard({ sessionId }: QuizCardProps) {
  const [session, setSession] = useState<QuizSession | null>(null)
  const [questions, setQuestions] = useState<QuizQuestion[]>([])
  const [finalByQuestion, setFinalByQuestion] = useState<Map<string, QuizAnswer>>(
    () => new Map(),
  )
  const [loaded, setLoaded] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [selectedKeys, setSelectedKeys] = useState<string[]>([])
  const [textValue, setTextValue] = useState('')
  const [feedback, setFeedback] = useState<FeedbackState | null>(null)
  const [hintLevel, setHintLevel] = useState(0)
  const [saving, setSaving] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  /** 当前展示的题目下标；-1 表示结果态。仅在初始恢复或用户点击后变化，
   * 避免提交回读导致的自动跳题（Phase 2-B9）。 */
  const [viewedIndex, setViewedIndex] = useState(0)

  const appendAiText = useConversationStore((state) => state.appendAiText)
  const teacherName = useTeacherName()

  const applyServerState = useCallback(
    async (id: string) => {
      const [sessionDetail, questionRows, answerRows] = await Promise.all([
        quizService.getQuizSession(id),
        quizService.getQuestions(id),
        quizService.getAnswers(id),
      ])
      const finals = new Map<string, QuizAnswer>()
      for (const answer of answerRows) {
        const existing = finals.get(answer.question_id)
        if (!existing || answer.attempt_no >= existing.attempt_no) {
          finals.set(answer.question_id, answer)
        }
      }
      setSession(sessionDetail)
      setQuestions(questionRows)
      setFinalByQuestion(finals)
      return { sessionDetail, questionRows, finals }
    },
    [],
  )

  useEffect(() => {
    let cancelled = false
    void applyServerState(sessionId)
      .then((state) => {
        if (cancelled) return
        if (state.questionRows.length === 0) setError('本题暂无数据（题目生成失败）')
        let firstUnfinished = -1
        for (let index = 0; index < state.questionRows.length; index += 1) {
          const answer = state.finals.get(state.questionRows[index].question_id)
          if (!answer || !answer.is_final) {
            firstUnfinished = index
            break
          }
        }
        setViewedIndex(firstUnfinished)
        setLoaded(true)
      })
      .catch(() => {
        if (!cancelled) {
          setError('题目加载失败')
          setLoaded(true)
        }
      })
    return () => {
      cancelled = true
    }
  }, [sessionId, applyServerState])

  const isCompleted =
    loaded && questions.length > 0 && viewedIndex === -1 && session !== null

  const question = viewedIndex >= 0 ? questions[viewedIndex] ?? null : null

  // 切换当前题目时清空草稿状态。
  useEffect(() => {
    setSelectedKeys([])
    setTextValue('')
    setFeedback(null)
    setHintLevel(
      question ? (finalByQuestion.get(question.question_id)?.hint_level_at_submit ?? 0) : 0,
    )
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [viewedIndex])

  const showNotice = (text: string) => {
    setNotice(text)
    window.setTimeout(() => setNotice(null), 2000)
  }

  const toggleMultiSelect = (key: string) => {
    setSelectedKeys((previous) =>
      previous.includes(key)
        ? previous.filter((item) => item !== key)
        : [...previous, key],
    )
  }

  const submit = async () => {
    if (!question || !session) return
    const payload = answerFor(question, selectedKeys, textValue)
    if (payload === null) {
      showNotice(
        question.question_type === 'FILL_BLANK'
          ? `先写下你的答案，${teacherName}会陪你一起检查`
          : question.question_type === 'MULTIPLE_CHOICE'
            ? '多选题请至少选择一项'
            : `先选一个答案，${teacherName}会陪你一起检查`,
      )
      return
    }
    setSaving(true)
    try {
      const answer = await quizService.submitAnswer(sessionId, question.question_id, {
        answer: payload,
        hint_level_at_submit: hintLevel,
      })
      // 服务端判定后回读：解析（explanation）仅在已作答后可见。
      const refreshed = await applyServerState(sessionId)
      setFeedback({
        isCorrect: answer.is_correct,
        isFinal: answer.is_final,
        explanation:
          refreshed.questionRows.find((row) => row.question_id === question.question_id)
            ?.explanation ?? null,
        attemptNo: answer.attempt_no,
      })
      if (answer.is_correct) useCompanionStore.getState().setAiState('happy')
      else useCompanionStore.getState().setAiState('encouraging')
    } catch {
      showNotice('提交失败，请重试')
    } finally {
      setSaving(false)
    }
  }

  const requestHint = async () => {
    if (!question || !session) return
    if (feedback?.isFinal) {
      showNotice(`这道题已经完成，${teacherName}可以陪你复盘`)
      return
    }
    if (hintLevel >= question.interaction_policy.max_hint_level) {
      showNotice(`已经是第 ${question.interaction_policy.max_hint_level} 级提示了，试着先答一次`)
      return
    }
    useCompanionStore.getState().setAiState('encouraging')
    try {
      const result = await quizService.requestHint(sessionId, question.question_id)
      setHintLevel(result.hint_level)
      appendAiText(
        `给你一个${result.hint_level}级提示：${result.hint_text}`,
        `${teacherName} · 提示 ${result.hint_level} / ${result.max_hint_level}`,
      )
    } catch {
      showNotice('提示生成失败，请重试')
    }
  }

  const goToNext = () => {
    let next = -1
    for (let index = viewedIndex + 1; index < questions.length; index += 1) {
      const answer = finalByQuestion.get(questions[index].question_id)
      if (!answer || !answer.is_final) {
        next = index
        break
      }
    }
    setViewedIndex(next)
  }

  if (error) {
    return (
      <p className="mt-2 rounded-lg border border-dashed border-border p-3 text-[11px] text-muted">
        {error}
      </p>
    )
  }
  if (!loaded || (questions.length === 0 && !error)) {
    return (
      <p className="mt-2 rounded-lg border border-dashed border-border p-3 text-center text-[11px] text-muted">
        题目加载中…
      </p>
    )
  }

  // ---- 完成态：展示真实 result_summary 与后端 ai_feedback ----
  if (isCompleted && session) {
    const summary = session.result_summary
    return (
      <div className="mt-2 rounded-[13px] border border-border bg-fg-soft p-3" data-od-id="chat-quiz-card">
        <div className="flex items-center justify-between font-mono text-[9px] text-muted">
          <span>结构化测验 · 已完成</span>
          <span>共 {questions.length} 题</span>
        </div>
        <p className="mt-2.5 text-[13px] font-medium leading-snug text-fg">
          ✓ 测验完成{summary ? ` · 最终正确 ${summary.correct}/${summary.total}` : ''}
          {summary && summary.hints_used > 0 ? ` · 使用提示 ${summary.hints_used} 次` : ''}
        </p>
        <p className="mt-1.5 text-[11px] leading-relaxed text-muted">
          {session.ai_feedback
            ? session.ai_feedback
            : `${teacherName}建议你回看每道题的解析，把做错题目的规律用自己的话讲一遍——这比多做十道新题更有效。`}
        </p>
        <p className="mt-2 text-[10px] text-muted">答题记录已保存 · 可在「测验」页查看</p>
      </div>
    )
  }
  if (!question) return null

  const choiceTypes = ['SINGLE_CHOICE', 'TRUE_FALSE', 'MULTIPLE_CHOICE']

  return (
    <div className="mt-2 rounded-[13px] border border-border bg-fg-soft p-3" data-od-id="chat-quiz-card">
      <div className="flex items-center justify-between font-mono text-[9px] text-muted">
        <span>结构化测验 · Quiz Session</span>
        <span>
          第 {viewedIndex + 1} 题 / 共 {questions.length} 题 · {TYPE_LABEL[question.question_type]}
        </span>
      </div>
      <h4 className="mt-2.5 text-[13px] leading-snug text-fg">{question.stem}</h4>

      {choiceTypes.includes(question.question_type) ? (
        <div className="mt-2.5 grid gap-1.5" role="group" aria-label="选项列表">
          {question.options.map((option) => {
            const isSelected = selectedKeys.includes(option.key)
            return (
              <button
                key={option.key}
                type="button"
                disabled={saving || Boolean(feedback?.isFinal)}
                aria-pressed={isSelected}
                onClick={() => {
                  if (question.question_type === 'MULTIPLE_CHOICE') toggleMultiSelect(option.key)
                  else setSelectedKeys([option.key])
                }}
                className={`flex items-start gap-2 rounded-lg border px-2.5 py-2 text-left text-[11px] ${
                  isSelected
                    ? 'border-fg bg-surface text-fg'
                    : 'border-border bg-surface text-fg hover:border-fg'
                }`}
              >
                <em className="grid h-[17px] w-[17px] shrink-0 place-items-center rounded-full border border-border font-mono text-[9px] not-italic text-muted">
                  {option.key}
                </em>
                <span>{option.text}</span>
              </button>
            )
          })}
        </div>
      ) : (
        <input
          type="text"
          value={textValue}
          disabled={saving || Boolean(feedback?.isFinal)}
          onChange={(event) => setTextValue(event.target.value)}
          aria-label="填空答案"
          placeholder="在横线上写出你的答案"
          className="mt-2.5 w-full rounded-lg border border-border bg-surface px-2.5 py-2 text-[12px] text-fg outline-none focus:border-fg"
        />
      )}

      {feedback ? (
        <div
          className={`mt-2.5 rounded-lg border p-2.5 text-[11px] leading-relaxed ${
            feedback.isCorrect
              ? 'border-accent bg-accent/10 text-fg'
              : 'border-border bg-surface text-muted'
          }`}
          role="status"
        >
          <p className={feedback.isCorrect ? 'font-medium text-fg' : ''}>
            {feedback.isCorrect
              ? '✓ 答对了'
              : feedback.isFinal
                ? '这道题的尝试次数用完了'
                : `✗ 这次不对（第 ${feedback.attemptNo} 次尝试），再想想`}
          </p>
          {feedback.explanation ? <p className="mt-1">解析:{feedback.explanation}</p> : null}
        </div>
      ) : null}

      <div className="mt-2.5 flex flex-wrap items-center justify-between gap-2">
        <span className="text-[10px] text-muted">
          {feedback?.isFinal
            ? '本题已记录'
            : feedback
              ? '根据解析调整思路后再试一次'
              : hintLevel > 0
                ? `已使用 ${hintLevel} 级提示`
                : question.question_type === 'FILL_BLANK'
                  ? '可以先写一个答案'
                  : '可以先选一个答案'}
        </span>
        {feedback?.isFinal ? (
          <button
            type="button"
            className="rounded-lg border border-fg bg-fg px-2.5 py-1 text-[10px] text-surface hover:bg-fg/85"
            onClick={goToNext}
          >
            {viewedIndex + 1 >= questions.length ? '查看结果' : '下一题 →'}
          </button>
        ) : (
          <span className="flex items-center gap-1">
            <button
              type="button"
              className="px-1.5 py-1 text-[10px] text-muted hover:text-fg hover:underline"
              onClick={() => void requestHint()}
            >
              给我一点提示
            </button>
            <button
              type="button"
              disabled={saving}
              className="rounded-lg border border-border bg-surface px-2 py-1 text-[10px] text-fg hover:border-fg disabled:opacity-50"
              onClick={() => void submit()}
            >
              提交答案
            </button>
          </span>
        )}
      </div>
      {notice ? (
        <p className="mt-2 text-center text-[10px] text-accent" role="status" aria-live="polite">
          {notice}
        </p>
      ) : null}
    </div>
  )
}
