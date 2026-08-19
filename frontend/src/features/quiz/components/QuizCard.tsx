import { useEffect, useState } from 'react'

import type { QuizQuestion } from '@/entities/quiz/types'
import { useCompanionStore } from '@/features/companion'
import { useConversationStore } from '@/features/conversation'
import { quizService } from '@/mocks/services'

interface QuizCardProps {
  sessionId: string
}

/** 对话内交互式单选题卡（0-B §2.7；正确答案判定以 MockQuizService 为准，原型为 B） */
export function QuizCard({ sessionId }: QuizCardProps) {
  const [question, setQuestion] = useState<QuizQuestion | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [selected, setSelected] = useState<string | null>(null)
  const [answered, setAnswered] = useState<string | null>(null)
  const [completed, setCompleted] = useState(false)
  const [hintLevel, setHintLevel] = useState(0)
  const [saving, setSaving] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const appendAiText = useConversationStore((state) => state.appendAiText)

  useEffect(() => {
    let cancelled = false
    quizService
      .getQuestions(sessionId)
      .then((questions) => {
        if (cancelled) return
        if (questions.length > 0) setQuestion(questions[0])
        else setError('本题暂无数据（题库由后续内容任务补全）')
      })
      .catch(() => {
        if (!cancelled) setError('题目加载失败')
      })
    return () => {
      cancelled = true
    }
  }, [sessionId])

  const showNotice = (text: string) => {
    setNotice(text)
    window.setTimeout(() => setNotice(null), 2000)
  }

  const submit = async () => {
    if (!question) return
    if (!selected) {
      showNotice('先选一个答案，霜铃会陪你一起检查')
      return
    }
    setSaving(true)
    try {
      const answer = await quizService.submitAnswer(sessionId, question.question_id, {
        answer: { key: selected },
        hint_level_at_submit: hintLevel,
      })
      setAnswered(selected)
      if (answer.is_correct) {
        setCompleted(true)
        useCompanionStore.getState().setAiState('happy')
        appendAiText(
          '答对了。你抓住了关键：训练数据的价值，不是数量本身，而是它能不能帮助机器发现可重复的规律。',
          '霜铃 · 结果已保存',
        )
        showNotice('QuizSession 已保存 · 可在测验页查看')
      } else {
        useCompanionStore.getState().setAiState('encouraging')
        appendAiText(
          '这个答案很接近了。再想想：训练数据真正帮助机器做的，是从例子里找出规律。',
          '霜铃 · 结果已保存',
        )
      }
    } catch {
      showNotice('提交失败，请重试')
    } finally {
      setSaving(false)
    }
  }

  const requestHint = async () => {
    if (!question) return
    if (completed) {
      showNotice('这道题已经完成，霜铃可以陪你复盘')
      return
    }
    if (hintLevel >= question.interaction_policy.max_hint_level) {
      showNotice('已经是第 3 级提示了，试着先选一个答案')
      return
    }
    useCompanionStore.getState().setAiState('encouraging')
    try {
      const result = await quizService.requestHint(sessionId, question.question_id)
      const level = result.hint_level
      setHintLevel(level)
      appendAiText(`给你一个${level}级提示：${result.hint_text}`, `霜铃 · 提示 ${level} / 3`)
    } catch {
      showNotice('提示生成失败，请重试')
    }
  }

  if (error) {
    return <p className="mt-2 rounded-lg border border-dashed border-border p-3 text-[11px] text-muted">{error}</p>
  }
  if (!question) {
    return (
      <p className="mt-2 rounded-lg border border-dashed border-border p-3 text-center text-[11px] text-muted">
        题目加载中…
      </p>
    )
  }

  const correctKey = String(question.correct_answer.key)

  return (
    <div className="mt-2 rounded-[13px] border border-border bg-fg-soft p-3" data-od-id="chat-quiz-card">
      <div className="flex items-center justify-between font-mono text-[9px] text-muted">
        <span>结构化测验 · Quiz Session</span>
        <span>第 1 题 / 共 3 题</span>
      </div>
      <h4 className="mt-2.5 text-[13px] leading-snug text-fg">{question.stem}</h4>
      <div className="mt-2.5 grid gap-1.5">
        {question.options.map((option) => {
          const isSelected = selected === option.key
          const isCorrect = completed && option.key === correctKey
          const isWrong = answered === option.key && !completed
          return (
            <button
              key={option.key}
              type="button"
              disabled={completed || saving}
              onClick={() => setSelected(option.key)}
              className={`flex items-start gap-2 rounded-lg border px-2.5 py-2 text-left text-[11px] ${
                isCorrect
                  ? 'border-fg bg-fg-soft text-fg'
                  : isWrong
                    ? 'border-muted text-muted'
                    : isSelected
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
      <div className="mt-2.5 flex flex-wrap items-center justify-between gap-2">
        <span className="text-[10px] text-muted">
          {completed
            ? '答题记录已保存 · 霜铃会继续陪你复盘'
            : answered
              ? '答案已记录 · 霜铃可以继续给你提示'
              : hintLevel > 0
                ? `已使用 ${hintLevel} 级提示`
                : '可以先选一个答案'}
        </span>
        {completed ? (
          <span className="text-[10px] text-fg">✓ 已完成</span>
        ) : (
          <span className="flex items-center gap-1">
            <button
              type="button"
              className="px-1.5 py-1 text-[10px] text-muted hover:text-fg hover:underline"
              onClick={() => void requestHint()}
            >
              给我一点提示
            </button>
            {!completed ? (
              <button
                type="button"
                disabled={saving}
                className="rounded-lg border border-border bg-surface px-2 py-1 text-[10px] text-fg hover:border-fg disabled:opacity-50"
                onClick={() => void submit()}
              >
                提交答案
              </button>
            ) : null}
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
