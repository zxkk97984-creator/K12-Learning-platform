import type { CodeReview, CorrectnessStatus } from '@/shared/api'

/**
 * AI 编程评价面板。
 *
 * 这个组件的首要职责是**如实表达评分的可信边界**，而不是把分数做得好看：
 *
 * - 有自动测试时：正确性由确定性测试决定（PASSED / PARTIAL / FAILED），
 *   给出 0–100 总分，AI 的算法/代码质量分只是其中两个维度。
 * - 没有自动测试时：correctness_status = NOT_VERIFIED 且 final_score_100 为 null，
 *   界面必须显式写出「本题未验证正确性」，只展示算法与代码质量分及其各自满分。
 *   绝不让 LLM 的主观评价看起来像一份权威成绩。
 */

const CORRECTNESS: Record<
  CorrectnessStatus,
  { label: string; hint: string; className: string }
> = {
  PASSED: {
    label: '已通过自动测试',
    hint: '所有功能与鲁棒性测试均通过。',
    className: 'text-accent',
  },
  PARTIAL: {
    label: '部分通过自动测试',
    hint: '部分测试未通过，总分按通过比例计算。',
    className: 'text-warn',
  },
  FAILED: {
    label: '未通过自动测试',
    hint: '自动测试全部未通过，功能尚未正确实现。',
    className: 'text-danger',
  },
  NOT_VERIFIED: {
    label: '未验证正确性',
    hint: '本题没有配置自动测试，无法判断功能是否正确。下面的分数只反映算法思路与代码质量，不代表程序运行正确。',
    className: 'text-muted',
  },
}

const LEVEL_LABEL: Record<string, string> = {
  complete: '完成',
  partial: '部分完成',
  missing: '未完成',
}

function ScoreBar({
  label,
  score,
  max,
}: {
  label: string
  score: number | null
  max: number
}) {
  const value = score ?? 0
  const percent = max > 0 ? Math.round((value / max) * 100) : 0
  return (
    <div>
      <div className="flex items-baseline justify-between text-xs">
        <span className="text-muted">{label}</span>
        <span className="text-fg">
          {score === null ? '—' : `${score} / ${max}`}
        </span>
      </div>
      <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-surface-sunken">
        <div className="h-full rounded-full bg-accent" style={{ width: `${percent}%` }} />
      </div>
    </div>
  )
}

export function AiReviewPanel({ review }: { review: CodeReview | null }) {
  if (!review) {
    return <p className="text-sm text-muted">运行代码后可以请 AI 评价你的写法。</p>
  }

  if (review.status === 'FAILED') {
    return (
      <div className="rounded-[10px] border border-danger/40 bg-danger/5 p-3 text-sm text-danger">
        AI 评审失败：{review.error ?? '未知原因'}
      </div>
    )
  }

  const correctness = CORRECTNESS[review.correctness_status] ?? CORRECTNESS.NOT_VERIFIED
  const feedback = review.student_feedback

  return (
    <div className="space-y-4" data-testid="codelab-review-panel">
      {/* ── 正确性：只由自动测试决定 ── */}
      <section>
        <h3 className={`text-sm font-semibold ${correctness.className}`}>
          {correctness.label}
        </h3>
        <p className="mt-1 text-xs leading-relaxed text-muted">{correctness.hint}</p>
      </section>

      {/* ── 总分：只有存在自动测试时才展示 ── */}
      {review.final_score_100 !== null ? (
        <section className="rounded-[10px] border border-border bg-surface p-3">
          <div className="flex items-baseline gap-2">
            <span className="font-display text-3xl text-fg">{review.final_score_100}</span>
            <span className="text-sm text-muted">/ 100</span>
          </div>
          <p className="mt-1 text-xs text-muted">
            由自动测试（60 + 10）与 AI 评价（20 + 10）合并得出。
          </p>
        </section>
      ) : (
        <section className="rounded-[10px] border border-border bg-surface-sunken p-3 text-xs leading-relaxed text-muted">
          本题没有自动测试，因此<strong className="text-fg">不给出总分</strong>。
          下面是 AI 对算法思路与代码质量的评价，仅供学习参考。
        </section>
      )}

      {/* ── 维度分 ── */}
      <section className="space-y-2.5">
        {review.deterministic_available ? (
          <>
            <ScoreBar label="功能正确性（自动测试）" score={review.functional_score} max={review.functional_max} />
            <ScoreBar label="鲁棒性（自动测试）" score={review.robustness_score} max={review.robustness_max} />
          </>
        ) : null}
        <ScoreBar label="算法思路（AI 评价）" score={review.algorithm_score} max={review.algorithm_max} />
        <ScoreBar label="代码质量（AI 评价）" score={review.quality_score} max={review.quality_max} />
      </section>

      {/* ── 测试组明细 ── */}
      {review.groups.length > 0 ? (
        <section>
          <h4 className="text-xs font-semibold text-fg">测试组</h4>
          <ul className="mt-1.5 space-y-1 text-xs" data-testid="codelab-review-groups">
            {review.groups.map((group) => (
              <li key={group.id} className="flex items-center justify-between gap-2">
                <span className="text-muted">
                  {group.dimension}·{group.name}
                </span>
                <span className={group.system_error ? 'text-warn' : 'text-fg'}>
                  {group.system_error
                    ? '系统未能执行该组'
                    : group.score === null
                      ? '—'
                      : `${group.score} / ${group.max_score}`}
                  {group.counts && !group.system_error
                    ? `（通过 ${group.counts.passed ?? 0}，失败 ${group.counts.failed ?? 0}）`
                    : ''}
                </span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {/* ── 教学反馈 ── */}
      {feedback ? (
        <section className="space-y-3">
          {feedback.strengths.length > 0 ? (
            <div>
              <h4 className="text-xs font-semibold text-accent">做得好的地方</h4>
              <ul className="mt-1 list-disc space-y-0.5 pl-5 text-xs leading-relaxed text-fg">
                {feedback.strengths.map((item, index) => (
                  <li key={index}>{item}</li>
                ))}
              </ul>
            </div>
          ) : null}

          {feedback.issues.length > 0 ? (
            <div>
              <h4 className="text-xs font-semibold text-danger">需要修正</h4>
              <ul className="mt-1 list-disc space-y-0.5 pl-5 text-xs leading-relaxed text-fg">
                {feedback.issues.map((item, index) => (
                  <li key={index}>{item}</li>
                ))}
              </ul>
            </div>
          ) : null}

          {feedback.suggestions.length > 0 ? (
            <div>
              <h4 className="text-xs font-semibold text-fg">改进建议</h4>
              <ul className="mt-1 list-disc space-y-0.5 pl-5 text-xs leading-relaxed text-fg">
                {feedback.suggestions.map((item, index) => (
                  <li key={index}>{item}</li>
                ))}
              </ul>
            </div>
          ) : null}

          {feedback.code_suggestions.length > 0 ? (
            <div>
              <h4 className="text-xs font-semibold text-fg">具体修改建议</h4>
              <div className="mt-1.5 space-y-2">
                {feedback.code_suggestions.map((suggestion, index) => (
                  <details
                    key={index}
                    className="rounded-[8px] border border-border bg-surface-sunken p-2"
                  >
                    <summary className="cursor-pointer text-xs text-fg">
                      {suggestion.title}
                    </summary>
                    <pre className="mt-1.5 overflow-x-auto whitespace-pre text-[11px] leading-relaxed text-muted">
                      {suggestion.diff}
                    </pre>
                  </details>
                ))}
              </div>
            </div>
          ) : null}
        </section>
      ) : null}

      {/* ── 逐条评分依据 ── */}
      {review.items.length > 0 ? (
        <section>
          <h4 className="text-xs font-semibold text-fg">评分依据</h4>
          <ul className="mt-1.5 space-y-1.5" data-testid="codelab-review-items">
            {review.items.map((item) => (
              <li key={`${item.dimension}-${item.criterion_id}`} className="text-xs leading-relaxed">
                <div className="flex items-baseline gap-2">
                  <span className="text-fg">{item.criterion}</span>
                  <span className="text-muted">
                    {item.dimension}·{item.criterion_id} · {LEVEL_LABEL[item.level] ?? item.level}
                  </span>
                </div>
                {item.evidence ? <p className="mt-0.5 text-muted">{item.evidence}</p> : null}
                {item.code_lines.length > 0 ? (
                  <p className="mt-0.5 text-muted">相关代码行：{item.code_lines.join(', ')}</p>
                ) : null}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {/* ── 需人工复核 ── */}
      {review.needs_teacher_review ? (
        <section
          data-testid="codelab-review-flag"
          className="rounded-[10px] border border-warn/40 bg-warn/5 p-3 text-xs leading-relaxed text-warn"
        >
          <strong>这份评价需要老师再看一眼。</strong>
          {review.review_reason ? <p className="mt-1">{review.review_reason}</p> : null}
          {review.validation_errors.length > 0 ? (
            <ul className="mt-1 list-disc pl-4">
              {review.validation_errors.map((item, index) => (
                <li key={index}>{item}</li>
              ))}
            </ul>
          ) : null}
        </section>
      ) : null}
    </div>
  )
}
