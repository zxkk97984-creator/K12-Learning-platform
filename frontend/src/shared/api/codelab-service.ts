/** CodeLab 领域类型（与后端 app/modules/codelab/schemas.py 一一对应）。 */

export interface CodeTaskListItem {
  task_id: string
  slug: string
  title: string
  description: string
  /** 是否配置了自动测试；决定评审是否给出总分（false → 只评代码质量） */
  has_tests: boolean
  status: string
}

export interface CodeTask {
  task_id: string
  slug: string
  title: string
  description: string
  starter_code: string
  has_tests: boolean
  status: string
}

/**
 * 沙箱输出条目，契约沿用 dai / Jupyter IOPub：
 *   stream       → content.name ∈ {stdout, stderr}，content.text 为文本
 *   error        → content.text 为 traceback
 *   display_data → content.data['image/png'] 为 base64
 */
export interface CodeOutput {
  msg_type: 'stream' | 'error' | 'display_data' | string
  content: {
    name?: 'stdout' | 'stderr' | string
    text?: string
    data?: Record<string, string>
  }
}

export type CodeRunStatus = 'SUCCESS' | 'FAILED' | 'TIMEOUT' | 'ERROR'

export interface CodeRun {
  run_id: string
  task_id: string
  status: CodeRunStatus
  outputs: CodeOutput[]
  execution_time_ms: number | null
  exit_code: number | null
  error: string | null
  created_at: string
}

export type CorrectnessStatus = 'PASSED' | 'PARTIAL' | 'FAILED' | 'NOT_VERIFIED'

export interface DimensionItem {
  dimension: string
  criterion_id: string
  criterion: string
  level: string
  evidence: string
  code_lines: number[]
  deduction_reason: string | null
}

export interface StudentFeedback {
  strengths: string[]
  issues: string[]
  suggestions: string[]
  code_suggestions: { title: string; diff: string }[]
  uncertainties: string[]
}

export interface DeterministicGroup {
  id: string
  name: string
  dimension: 'F' | 'R'
  max_score: number
  score: number | null
  counts: { passed?: number; failed?: number; errors?: number; skipped?: number } | null
  system_error?: boolean
}

export interface CodeReview {
  review_id: string
  run_id: string
  status: 'RUNNING' | 'COMPLETED' | 'FAILED' | 'REVIEW_REQUIRED'
  grading_mode: 'tests' | 'review_only'
  deterministic_available: boolean
  correctness_status: CorrectnessStatus

  functional_score: number | null
  robustness_score: number | null
  algorithm_score: number | null
  quality_score: number | null

  functional_max: number
  robustness_max: number
  algorithm_max: number
  quality_max: number

  /** 无自动测试时为 null —— 「未验证正确性」不得看起来像一份正式成绩 */
  final_score_100: number | null
  groups: DeterministicGroup[]
  items: DimensionItem[]
  student_feedback: StudentFeedback | null
  needs_teacher_review: boolean
  review_reason: string | null
  validation_errors: string[]
  error: string | null
  created_at: string
  updated_at: string
}

export interface CodeLabService {
  listTasks(): Promise<CodeTaskListItem[]>
  getTask(taskId: string): Promise<CodeTask>
  runCode(taskId: string, code: string): Promise<CodeRun>
  requestReview(runId: string): Promise<CodeReview>
  getReview(reviewId: string): Promise<CodeReview>
}
