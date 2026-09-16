import { useMemo } from 'react'

import type { ProfileInsight } from '@/entities/memory/types'
import type { StudentPreference, StudentProfile } from '@/entities/student/types'
import {
  DIFFICULTY_LABEL,
  LENGTH_LABEL,
  STYLE_LABEL,
  buildMarkdown,
} from '../profile-labels'

interface ArchiveDocCardProps {
  profile: StudentProfile
  prefs: StudentPreference
  /** 学习目标草稿（编辑模式可改，保存走真实 API） */
  learningGoalDraft: string
  onLearningGoalDraftChange: (value: string) => void
  insights: ProfileInsight[]
  historyInsights: ProfileInsight[]
  teacherName: string
  userEdited: boolean
  docMode: 'preview' | 'edit'
  mdDraft: string
  onDocModeChange: (mode: 'preview' | 'edit') => void
  onMdDraftChange: (draft: string) => void
  onSave: () => void
  onExport: () => void
}

/** 「原始 AI 档案」：xiaoming.agent.md 只读预览 / 源码编辑 */
export function ArchiveDocCard({
  profile,
  prefs,
  learningGoalDraft,
  onLearningGoalDraftChange,
  insights,
  historyInsights,
  teacherName,
  userEdited,
  docMode,
  mdDraft,
  onDocModeChange,
  onMdDraftChange,
  onSave,
  onExport,
}: ArchiveDocCardProps) {
  const markdown = useMemo(() => buildMarkdown(profile, prefs, insights), [profile, prefs, insights])

  const frontmatter: Array<[string, string]> = [
    ['name', profile.nickname],
    ['grade', `${profile.grade} 年级`],
    ['updated', profile.updated_at.slice(0, 10)],
    ['preferred_explanation_style', prefs.preferred_explanation_style.toLowerCase()],
    ['preferred_difficulty', prefs.preferred_difficulty.toLowerCase()],
    ['preferred_session_length', prefs.preferred_session_length.toLowerCase()],
    ...(profile.learning_goal ? [['learning_goal', profile.learning_goal] as [string, string]] : []),
  ]

  return (
    <article className="overflow-hidden rounded-[14px] border border-border bg-surface">
      <div className="flex min-h-[56px] flex-wrap items-center justify-between gap-3 border-b border-border px-4 py-2.5">
        <div className="min-w-0">
          <span className="font-mono text-xs font-semibold text-fg">{profile.nickname}.agent.md</span>
          {userEdited ? (
            <span className="ml-2 rounded-full border border-border bg-fg-soft px-2 py-0.5 font-mono text-[9px] text-fg">
              用户修改
            </span>
          ) : null}
          <span className="ml-2 text-[11px] text-muted">
            {userEdited
              ? '已修改，尚未保存'
              : `由${teacherName}维护 · 最近更新 ${profile.updated_at.slice(5, 10)}`}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            className="rounded-md px-2 py-1 text-[11px] text-muted hover:bg-fg-soft hover:text-fg"
            onClick={onExport}
          >
            导出
          </button>
          <div className="flex gap-0.5 rounded-[10px] bg-fg-soft p-0.5">
            {(['preview', 'edit'] as const).map((mode) => (
              <button
                key={mode}
                type="button"
                aria-selected={docMode === mode}
                onClick={() => onDocModeChange(mode)}
                className={`rounded-lg px-3 py-1 text-xs transition-colors ${
                  docMode === mode ? 'bg-surface text-fg shadow-sm' : 'text-muted hover:text-fg'
                }`}
              >
                {mode === 'preview' ? '预览' : '编辑'}
              </button>
            ))}
          </div>
        </div>
      </div>

      {docMode === 'preview' ? (
        <div className="px-6 py-4 font-mono text-xs leading-relaxed text-fg wrap-anywhere">
          <span className="block text-muted opacity-55">---</span>
          {frontmatter.map(([key, value]) => (
            <span key={key} className="block">
              {key}: <span className="text-fg">{value}</span>
            </span>
          ))}
          <span className="block text-muted opacity-55">---</span>
          <div className="mt-4 space-y-4 font-body">
            <section>
              <h3 className="font-display text-lg text-fg">AI 对我的认识</h3>
              <p className="mt-2 max-w-[64ch] text-[13px] leading-relaxed text-muted">
                {insights.length > 0
                  ? '以下内容由 AI 基于你的真实学习记录生成，可在下方查看与质疑。'
                  : '暂无画像判断——随着学习记录积累，这里会展示 AI 对你的认识。'}
              </p>
              <p className="mt-2 text-[11px] text-muted">
                讲解偏好：{STYLE_LABEL[prefs.preferred_explanation_style]} · 学习节奏：
                {LENGTH_LABEL[prefs.preferred_session_length]} · 难度偏好：
                {DIFFICULTY_LABEL[prefs.preferred_difficulty]}
              </p>
            </section>
            <section>
              <h3 className="font-display text-lg text-fg">当前表现</h3>
              {insights.length === 0 ? (
                <p className="mt-2 text-[13px] text-muted">暂无画像判断。</p>
              ) : (
                <ul className="mt-2 space-y-2">
                  {insights.map((insight) => (
                    <li key={insight.insight_id} className="max-w-[72ch] text-[13px] leading-relaxed text-muted">
                      <span className="text-fg">{insight.dimension}</span> —— {insight.level}：
                      {insight.description}
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </div>
        </div>
      ) : (
        <div className="p-4">
          <label className="mb-2 block text-[11px] text-muted">
            学习目标（保存到学生档案）
            <input
              type="text"
              value={learningGoalDraft}
              onChange={(event) => onLearningGoalDraftChange(event.target.value)}
              className="mt-1 w-full rounded-lg border border-border bg-surface px-2.5 py-2 text-[12px] text-fg outline-none focus:border-fg"
              placeholder="例如：期末 AI 成绩提升"
            />
          </label>
          <textarea
            value={mdDraft || markdown}
            onChange={(event) => onMdDraftChange(event.target.value)}
            rows={16}
            spellCheck={false}
            aria-label="画像文件源码"
            className="w-full resize-y rounded-[10px] border border-border bg-surface p-3 font-mono text-xs leading-relaxed text-fg outline-none focus:border-fg"
          />
          <div className="mt-3 flex justify-end gap-2">
            <button
              type="button"
              className="rounded-[10px] px-3 py-1.5 text-xs text-muted hover:bg-fg-soft hover:text-fg"
              onClick={() => {
                onMdDraftChange('')
                onDocModeChange('preview')
              }}
            >
              放弃修改
            </button>
            <button
              type="button"
              className="rounded-[10px] border border-border bg-surface px-3 py-1.5 text-xs text-fg hover:border-fg"
              onClick={onSave}
            >
              保存修改
            </button>
          </div>
        </div>
      )}

      <div className="border-t border-border px-4 py-3">
        <p className="font-mono text-[10px] text-muted">修改记录</p>
        {historyInsights.length === 0 ? (
          <p className="mt-2 text-xs text-muted" data-testid="history-empty">
            暂无修改记录——画像被更新时，历史版本会留存在这里。
          </p>
        ) : (
          <ul className="mt-2 grid gap-2 text-xs">
            {historyInsights.map((insight) => (
              <li key={insight.insight_id}>
                <time className="font-mono text-[10px] text-muted">
                  {insight.updated_at.slice(5, 10)}
                </time>
                <span className="ml-2">
                  {insight.dimension} · {insight.level}：{insight.description}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </article>
  )
}
