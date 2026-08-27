import type {
  MemoryEvidence,
  ProfileInsight,
  ProfileInsightType,
} from '@/entities/memory/types'
import type { StudentPreference, StudentProfile } from '@/entities/student/types'

export const STYLE_LABEL: Record<string, string> = {
  EXAMPLE_BASED: '例子优先',
  VISUAL: '图解优先',
  STORY: '故事优先',
  DIRECT_DEFINITION: '直接定义',
  STEP_BY_STEP: '分步骤',
  CODE: '代码示例',
  INTERACTIVE: '互动提问',
}

export const DIFFICULTY_LABEL: Record<string, string> = { EASY: '简单', MEDIUM: '中等', HARD: '较难' }
export const LENGTH_LABEL: Record<string, string> = { SHORT: '短时、多轮', MEDIUM: '中等时长', LONG: '较长连续' }

export const INSIGHT_TYPE_LABEL: Record<ProfileInsightType, string> = {
  STRENGTH: '优势',
  WEAKNESS: '薄弱',
  UNDERSTANDING: '理解力',
  HABIT: '习惯',
  CHANGE: '变化',
  INTEREST: '兴趣',
}

export const SOURCE_LABEL: Record<MemoryEvidence['source_type'], string> = {
  QUIZ: '测验记录',
  LEARNING_SESSION: '学习时段',
  CONVERSATION: '课程对话',
  BOOK_PROGRESS: '阅读进度',
}

export function payloadSummary(payload: Record<string, unknown>): string {
  return Object.entries(payload)
    .filter(([key]) => key !== 'dimension')
    .map(([key, value]) => `${key}: ${typeof value === 'string' ? value : JSON.stringify(value)}`)
    .join(' · ')
}

export function buildMarkdown(
  profile: StudentProfile,
  prefs: StudentPreference,
  insights: ProfileInsight[],
): string {
  // Phase 4 整改：只输出数据库中的真实 insights；无数据时写明确空态。
  const changeInsights = insights.filter((insight) => insight.insight_type === 'CHANGE')
  const lines = [
    '---',
    `name: ${profile.nickname}`,
    `grade: ${profile.grade} 年级`,
    `updated: ${profile.updated_at.slice(0, 10)}`,
    `preferred_explanation_style: ${prefs.preferred_explanation_style.toLowerCase()}   # ${STYLE_LABEL[prefs.preferred_explanation_style] ?? prefs.preferred_explanation_style}`,
    `preferred_difficulty: ${prefs.preferred_difficulty.toLowerCase()}   # ${DIFFICULTY_LABEL[prefs.preferred_difficulty] ?? ''}`,
    `preferred_session_length: ${prefs.preferred_session_length.toLowerCase()}   # ${LENGTH_LABEL[prefs.preferred_session_length] ?? ''}`,
    ...(profile.learning_goal ? [`learning_goal: ${profile.learning_goal}`] : []),
    '---',
    '',
    '## AI 对我的认识',
    '',
    ...(insights.length > 0
      ? insights.map(
          (insight) => `- ${insight.dimension} —— ${insight.level}：${insight.description}`,
        )
      : ['暂无画像判断']),
    '',
    '## 最近变化',
    '',
    ...(changeInsights.length > 0
      ? changeInsights.map(
          (insight) => `- ${insight.dimension} —— ${insight.level}：${insight.description}`,
        )
      : ['暂无最近变化']),
  ]
  return lines.join('\n')
}

// ---------- Phase 4：档案编辑解析与导出 ----------

export interface ProfileFrontmatterPatch {
  grade?: number
  preferred_explanation_style?: StudentPreference['preferred_explanation_style']
  preferred_difficulty?: StudentPreference['preferred_difficulty']
  preferred_session_length?: StudentPreference['preferred_session_length']
  learning_goal?: string
}

const STYLE_KEYS = Object.keys(STYLE_LABEL) as Array<keyof typeof STYLE_LABEL>
const DIFFICULTY_KEYS = Object.keys(DIFFICULTY_LABEL) as Array<
  keyof typeof DIFFICULTY_LABEL
>
const LENGTH_KEYS = Object.keys(LENGTH_LABEL) as Array<keyof typeof LENGTH_LABEL>

/**
 * 从用户编辑的 agent.md frontmatter 中解析可持久化字段。
 * 仅接受合法枚举/数字，非法值忽略——不静默改库。
 */
export function parseProfileFrontmatter(markdown: string): ProfileFrontmatterPatch {
  const patch: ProfileFrontmatterPatch = {}
  const lines = markdown.split(/\r?\n/)
  let inFrontmatter = false
  for (const rawLine of lines) {
    const line = rawLine.trim()
    if (line === '---') {
      if (inFrontmatter) break
      inFrontmatter = true
      continue
    }
    if (!inFrontmatter) continue
    const separator = line.indexOf(':')
    if (separator <= 0) continue
    const key = line.slice(0, separator).trim()
    const value = line.slice(separator + 1).trim()
    if (!value) continue
    if (key === 'grade') {
      const grade = Number.parseInt(value, 10)
      if (Number.isFinite(grade) && grade >= 1 && grade <= 12) patch.grade = grade
    } else if (key === 'preferred_explanation_style') {
      const upper = value.toUpperCase()
      if ((STYLE_KEYS as string[]).includes(upper)) {
        patch.preferred_explanation_style = upper as ProfileFrontmatterPatch['preferred_explanation_style']
      }
    } else if (key === 'preferred_difficulty') {
      const upper = value.toUpperCase()
      if ((DIFFICULTY_KEYS as string[]).includes(upper)) {
        patch.preferred_difficulty = upper as ProfileFrontmatterPatch['preferred_difficulty']
      }
    } else if (key === 'preferred_session_length') {
      const upper = value.toUpperCase()
      if ((LENGTH_KEYS as string[]).includes(upper)) {
        patch.preferred_session_length = upper as ProfileFrontmatterPatch['preferred_session_length']
      }
    }
  }
  // 正文中的学习目标行：- 学习目标：<内容>
  const goalMatch = markdown.match(/学习目标[：:]\s*(.+)\s*$/m)
  if (goalMatch) patch.learning_goal = goalMatch[1].trim()
  return patch
}

export interface ProfileExportPayload {
  exported_at: string
  profile: Record<string, unknown>
  preferences: Record<string, unknown> | null
  insights: Array<Record<string, unknown>>
  memories: Array<Record<string, unknown>>
}

/** 导出文件内容构建（纯函数；下载由调用方触发）。 */
export function buildProfileExportJson(payload: {
  profile: Record<string, unknown>
  preferences: Record<string, unknown> | null
  insights: Array<Record<string, unknown>>
  memories: Array<Record<string, unknown>>
}): string {
  const body: ProfileExportPayload = {
    exported_at: new Date().toISOString(),
    ...payload,
  }
  return JSON.stringify(body, null, 2)
}
