// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import { AiReviewPanel } from './AiReviewPanel'
import type { CodeReview } from '@/shared/api'

function makeReview(overrides: Partial<CodeReview> = {}): CodeReview {
  return {
    review_id: 'review-1',
    run_id: 'run-1',
    status: 'COMPLETED',
    grading_mode: 'tests',
    deterministic_available: true,
    correctness_status: 'PASSED',
    functional_score: 60,
    robustness_score: 10,
    algorithm_score: 16,
    quality_score: 8,
    functional_max: 60,
    robustness_max: 10,
    algorithm_max: 20,
    quality_max: 10,
    final_score_100: 94,
    groups: [],
    items: [],
    student_feedback: null,
    needs_teacher_review: false,
    review_reason: null,
    validation_errors: [],
    error: null,
    created_at: '2026-09-16T00:00:00Z',
    updated_at: '2026-09-16T00:00:00Z',
    ...overrides,
  }
}

describe('AiReviewPanel', () => {
  it('空态提示先运行代码', () => {
    render(<AiReviewPanel review={null} />)
    expect(screen.getByText(/运行代码后/)).toBeTruthy()
  })

  it('有测试时展示总分与正确性结论', () => {
    render(<AiReviewPanel review={makeReview()} />)
    expect(screen.getByText('94')).toBeTruthy()
    expect(screen.getByText('已通过自动测试')).toBeTruthy()
    expect(screen.getByText('功能正确性（自动测试）')).toBeTruthy()
    expect(screen.getByText('算法思路（AI 评价）')).toBeTruthy()
  })

  it('无测试时不给总分，并明确标出「未验证正确性」', () => {
    render(
      <AiReviewPanel
        review={makeReview({
          grading_mode: 'review_only',
          deterministic_available: false,
          correctness_status: 'NOT_VERIFIED',
          functional_score: null,
          robustness_score: null,
          final_score_100: null,
        })}
      />,
    )
    expect(screen.getByText('未验证正确性')).toBeTruthy()
    expect(screen.getByText(/本题没有自动测试/)).toBeTruthy()
    expect(screen.getByText(/不给出总分/)).toBeTruthy()
    // 不应出现总分数字
    expect(screen.queryByText('/ 100')).toBeNull()
    // 也不应展示确定性维度
    expect(screen.queryByText('功能正确性（自动测试）')).toBeNull()
  })

  it('正确性判定不因 AI 高分而改变', () => {
    render(
      <AiReviewPanel
        review={makeReview({
          correctness_status: 'FAILED',
          functional_score: 0,
          robustness_score: 0,
          algorithm_score: 20,
        })}
      />,
    )
    expect(screen.getByText('未通过自动测试')).toBeTruthy()
  })

  it('展示教学反馈的三个部分与具体修改建议', () => {
    render(
      <AiReviewPanel
        review={makeReview({
          student_feedback: {
            strengths: ['命名清晰'],
            issues: ['缺少空列表处理'],
            suggestions: ['先判断输入是否为空'],
            code_suggestions: [
              { title: '补全空输入处理', diff: '--- a\n+++ b\n@@ -1 +1,2 @@\n+    pass\n' },
            ],
            uncertainties: [],
          },
        })}
      />,
    )
    expect(screen.getByText('做得好的地方')).toBeTruthy()
    expect(screen.getByText('命名清晰')).toBeTruthy()
    expect(screen.getByText('需要修正')).toBeTruthy()
    expect(screen.getByText('缺少空列表处理')).toBeTruthy()
    expect(screen.getByText('改进建议')).toBeTruthy()
    expect(screen.getByText('补全空输入处理')).toBeTruthy()
  })

  it('需要人工复核时展示提示与原因', () => {
    render(
      <AiReviewPanel
        review={makeReview({
          needs_teacher_review: true,
          review_reason: '自动测试全部未通过，但 AI 给出的算法评价明显偏高',
          validation_errors: ['测试与 AI 评分不一致'],
        })}
      />,
    )
    expect(screen.getByTestId('codelab-review-flag')).toBeTruthy()
    expect(screen.getByText(/需要老师再看一眼/)).toBeTruthy()
    expect(screen.getByText('测试与 AI 评分不一致')).toBeTruthy()
  })

  it('展示测试组明细与逐条评分依据', () => {
    render(
      <AiReviewPanel
        review={makeReview({
          groups: [
            { id: 'F1', name: '基本换算', dimension: 'F', max_score: 60, score: 60, counts: { passed: 3, failed: 0 } },
          ],
          items: [
            {
              dimension: '算法',
              criterion_id: 'A1',
              criterion: '换算公式正确',
              level: 'complete',
              evidence: '第 2 行使用了正确的公式',
              code_lines: [2],
              deduction_reason: null,
            },
          ],
        })}
      />,
    )
    expect(screen.getByTestId('codelab-review-groups').textContent).toContain('基本换算')
    expect(screen.getByTestId('codelab-review-items').textContent).toContain('换算公式正确')
    expect(screen.getByText(/相关代码行：2/)).toBeTruthy()
  })

  it('评审失败时给出错误提示而不是空白', () => {
    render(<AiReviewPanel review={makeReview({ status: 'FAILED', error: 'AI 服务不可用' })} />)
    expect(screen.getByText(/AI 评审失败/)).toBeTruthy()
    expect(screen.getByText(/AI 服务不可用/)).toBeTruthy()
  })
})

afterEach(cleanup)
