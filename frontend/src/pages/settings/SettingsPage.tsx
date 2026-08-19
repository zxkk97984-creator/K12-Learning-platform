import { useEffect, useState } from 'react'

import type {
  PreferredDifficulty,
  PreferredExplanationStyle,
  PreferredSessionLength,
} from '@/entities/student/types'
import { deriveStage, type TeacherRole } from '@/entities/student/types'
import { useAuth } from '@/features/auth'
import { useToastStore } from '@/features/feedback'
import { studentService, teacherRoleService } from '@/mocks/services'

const AGE_OPTIONS = [
  { key: 'primary', label: '小学' },
  { key: 'junior', label: '初中' },
  { key: 'senior', label: '高中' },
] as const

const STYLE_OPTIONS: PreferredExplanationStyle[] = [
  'EXAMPLE_BASED',
  'VISUAL',
  'STORY',
  'DIRECT_DEFINITION',
  'STEP_BY_STEP',
  'CODE',
  'INTERACTIVE',
]

function applyAge(age: 'primary' | 'junior' | 'senior'): void {
  document.documentElement.dataset.age = age === 'junior' ? '' : age
  window.localStorage.setItem('shuangling-age', age)
}

export default function SettingsPage() {
  const showToast = useToastStore((state) => state.showToast)
  const { currentUser, refreshMe } = useAuth()
  const [nickname, setNickname] = useState('')
  const [grade, setGrade] = useState(8)
  const [language, setLanguage] = useState('zh-CN')
  const [learningGoal, setLearningGoal] = useState('')
  const [style, setStyle] = useState<PreferredExplanationStyle>('EXAMPLE_BASED')
  const [difficulty, setDifficulty] = useState<PreferredDifficulty>('MEDIUM')
  const [sessionLength, setSessionLength] = useState<PreferredSessionLength>('SHORT')
  const [roleId, setRoleId] = useState('role-shuangling')
  const [roles, setRoles] = useState<TeacherRole[]>([])
  const [age, setAge] = useState<'primary' | 'junior' | 'senior'>('junior')
  const [loaded, setLoaded] = useState(false)

  useEffect(() => {
    if (!currentUser) {
      setLoaded(true)
      return
    }
    void (async () => {
      try {
        const [prefs, roleList] = await Promise.all([
          studentService.getPreferences(),
          teacherRoleService.getRoles(),
        ])
        setNickname(currentUser.nickname)
        setGrade(currentUser.grade)
        setLanguage(currentUser.language)
        setLearningGoal(currentUser.learning_goal ?? '')
        setStyle(prefs.preferred_explanation_style)
        setDifficulty(prefs.preferred_difficulty)
        setSessionLength(prefs.preferred_session_length)
        setRoleId(currentUser.current_teacher_role_id ?? 'role-shuangling')
        setRoles(roleList)
      } catch {
        // 保留默认表单
      }
      const saved = window.localStorage.getItem('shuangling-age')
      if (saved === 'primary' || saved === 'senior' || saved === 'junior') {
        setAge(saved)
        applyAge(saved)
      }
      setLoaded(true)
    })()
  }, [currentUser])

  const save = async () => {
    try {
      // Mock 角色 id（role-shuangling）不是 UUID；仅在合法 UUID 时提交，
      // 否则省略（真实 teacher_roles 数据 Phase 11 接入）
      const roleIdValid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(
        roleId,
      )
      const profilePatch = {
        nickname,
        grade,
        language,
        learning_goal: learningGoal || null,
        ...(roleIdValid ? { current_teacher_role_id: roleId } : {}),
      }
      await studentService.updateMe(profilePatch)
      await studentService.updatePreferences({
        preferred_explanation_style: style,
        preferred_difficulty: difficulty,
        preferred_session_length: sessionLength,
      })
      applyAge(age)
      await refreshMe()
      showToast('设置已保存')
    } catch {
      showToast('保存失败，请重试')
    }
  }

  if (!loaded) {
    return (
      <section className="py-10">
        <p className="font-mono text-xs uppercase tracking-widest text-accent">设置</p>
        <h1 className="mt-3 font-display text-4xl text-fg">设置</h1>
        <p className="mt-4 text-sm text-muted">正在加载设置…</p>
      </section>
    )
  }

  return (
    <section className="py-10">
      <p className="font-mono text-xs uppercase tracking-widest text-accent">设置</p>
      <h1 className="mt-3 font-display text-4xl text-fg">设置</h1>

      <div className="mt-6 grid max-w-2xl gap-6">
        <section className="rounded-[14px] border border-border bg-surface p-5">
          <h2 className="font-display text-lg text-fg">账号</h2>
          <div className="mt-4 grid gap-3">
            <label className="grid gap-1 text-xs text-muted">
              昵称
              <input
                value={nickname}
                onChange={(event) => setNickname(event.target.value)}
                className="h-10 rounded-[10px] border border-border bg-bg px-3 text-[13px] text-fg outline-none focus:border-fg"
              />
            </label>
            <label className="grid gap-1 text-xs text-muted">
              年级（1~12）
              <span className="flex items-center gap-3">
                <select
                  value={grade}
                  onChange={(event) => setGrade(Number(event.target.value))}
                  className="h-10 rounded-[10px] border border-border bg-bg px-3 text-[13px] text-fg outline-none focus:border-fg"
                >
                  {Array.from({ length: 12 }, (_, index) => index + 1).map((value) => (
                    <option key={value} value={value}>
                      {value} 年级
                    </option>
                  ))}
                </select>
                <span className="rounded-full border border-border px-2.5 py-1 font-mono text-[10px] text-muted">
                  {deriveStage(grade)}（{grade <= 6 ? '小学' : grade <= 9 ? '初中' : '高中'}）
                </span>
              </span>
            </label>
            <label className="grid gap-1 text-xs text-muted">
              语言
              <input
                value={language}
                onChange={(event) => setLanguage(event.target.value)}
                className="h-10 rounded-[10px] border border-border bg-bg px-3 text-[13px] text-fg outline-none focus:border-fg"
              />
            </label>
            <label className="grid gap-1 text-xs text-muted">
              学习目标
              <input
                value={learningGoal}
                onChange={(event) => setLearningGoal(event.target.value)}
                placeholder="例如：理解机器学习的基本概念"
                className="h-10 rounded-[10px] border border-border bg-bg px-3 text-[13px] text-fg outline-none focus:border-fg"
              />
            </label>
          </div>
        </section>

        <section className="rounded-[14px] border border-border bg-surface p-5">
          <h2 className="font-display text-lg text-fg">学习偏好</h2>
          <div className="mt-4 grid gap-3">
            <label className="grid gap-1 text-xs text-muted">
              讲解方式
              <select
                value={style}
                onChange={(event) => setStyle(event.target.value as PreferredExplanationStyle)}
                className="h-10 rounded-[10px] border border-border bg-bg px-3 text-[13px] text-fg outline-none focus:border-fg"
              >
                {STYLE_OPTIONS.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            </label>
            <label className="grid gap-1 text-xs text-muted">
              难度
              <select
                value={difficulty}
                onChange={(event) => setDifficulty(event.target.value as PreferredDifficulty)}
                className="h-10 rounded-[10px] border border-border bg-bg px-3 text-[13px] text-fg outline-none focus:border-fg"
              >
                {(['EASY', 'MEDIUM', 'HARD'] as const).map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            </label>
            <label className="grid gap-1 text-xs text-muted">
              学习节奏
              <select
                value={sessionLength}
                onChange={(event) => setSessionLength(event.target.value as PreferredSessionLength)}
                className="h-10 rounded-[10px] border border-border bg-bg px-3 text-[13px] text-fg outline-none focus:border-fg"
              >
                {(['SHORT', 'MEDIUM', 'LONG'] as const).map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            </label>
          </div>
        </section>

        <section className="rounded-[14px] border border-border bg-surface p-5">
          <h2 className="font-display text-lg text-fg">AI 教师</h2>
          <label className="mt-4 grid gap-1 text-xs text-muted">
            角色
            <select
              value={roleId}
              onChange={(event) => setRoleId(event.target.value)}
              className="h-10 rounded-[10px] border border-border bg-bg px-3 text-[13px] text-fg outline-none focus:border-fg"
            >
              {roles.map((role) => (
                <option key={role.role_id} value={role.role_id}>
                  {role.name}
                </option>
              ))}
            </select>
          </label>
        </section>

        <section className="rounded-[14px] border border-border bg-surface p-5">
          <h2 className="font-display text-lg text-fg">界面适配 · 学段</h2>
          <div className="mt-4 flex gap-2">
            {AGE_OPTIONS.map((option) => (
              <button
                key={option.key}
                type="button"
                aria-pressed={age === option.key}
                onClick={() => {
                  setAge(option.key)
                  applyAge(option.key)
                  showToast(`已切换${option.label}适配`)
                }}
                className={`rounded-[10px] border px-4 py-2 text-xs ${
                  age === option.key
                    ? 'border-fg bg-surface text-fg'
                    : 'border-border text-muted hover:border-fg hover:text-fg'
                }`}
              >
                {option.label}
              </button>
            ))}
          </div>
        </section>

        <section className="rounded-[14px] border border-border bg-surface p-5">
          <h2 className="font-display text-lg text-fg">语音</h2>
          <p className="mt-2 text-xs text-muted">语音输入 / TTS 设置（Phase 9 实现，当前占位）。</p>
        </section>

        <div>
          <button
            type="button"
            className="rounded-[10px] bg-accent px-5 py-2.5 text-sm text-surface hover:bg-accent/85"
            onClick={() => void save()}
          >
            保存设置
          </button>
        </div>
      </div>
    </section>
  )
}
