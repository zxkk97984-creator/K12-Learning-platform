import { useEffect, useState } from 'react'

import type {
  PreferredDifficulty,
  PreferredExplanationStyle,
  PreferredSessionLength,
  TeacherRoleDTO,
} from '@/entities/student/types'
import { deriveStage, type TeacherRole } from '@/entities/student/types'
import { useAuth } from '@/features/auth'
import { CompanionPetPicker, getCompanionPet, useCompanionStore } from '@/features/companion'
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

const SPEED_OPTIONS = [0.5, 0.75, 1, 1.25, 1.5, 2]

function applyAge(age: 'primary' | 'junior' | 'senior'): void {
  document.documentElement.dataset.age = age === 'junior' ? '' : age
  window.localStorage.setItem('shuangling-age', age)
}

export default function SettingsPage() {
  const showToast = useToastStore((state) => state.showToast)
  const { currentUser, refreshMe } = useAuth()
  const selectedPetId = useCompanionStore((state) => state.selectedPetId)
  const setSelectedPet = useCompanionStore((state) => state.setSelectedPet)
  const [nickname, setNickname] = useState('')
  const [grade, setGrade] = useState(8)
  const [language, setLanguage] = useState('zh-CN')
  const [learningGoal, setLearningGoal] = useState('')
  const [style, setStyle] = useState<PreferredExplanationStyle>('EXAMPLE_BASED')
  const [difficulty, setDifficulty] = useState<PreferredDifficulty>('MEDIUM')
  const [sessionLength, setSessionLength] = useState<PreferredSessionLength>('SHORT')
  const [inputEnabled, setInputEnabled] = useState(true)
  const [ttsEnabled, setTtsEnabled] = useState(true)
  const [volumePercent, setVolumePercent] = useState(80)
  const [speed, setSpeed] = useState(1)
  const [roleId, setRoleId] = useState('role-shuangling')
  const [roles, setRoles] = useState<TeacherRole[]>([])
  const [teacherRoles, setTeacherRoles] = useState<TeacherRoleDTO[]>([])
  const [age, setAge] = useState<'primary' | 'junior' | 'senior'>('junior')
  const [loaded, setLoaded] = useState(false)

  useEffect(() => {
    if (!currentUser) {
      setLoaded(true)
      return
    }
    void (async () => {
      try {
        const [prefs, roleList, teacherRoleList] = await Promise.all([
          studentService.getPreferences(),
          teacherRoleService.getRoles(),
          studentService.getTeacherRoles(),
        ])
        setNickname(currentUser.nickname)
        setGrade(currentUser.grade)
        setLanguage(currentUser.language)
        setLearningGoal(currentUser.learning_goal ?? '')
        setStyle(prefs.preferred_explanation_style)
        setDifficulty(prefs.preferred_difficulty)
        setSessionLength(prefs.preferred_session_length)
        setInputEnabled(prefs.voice_preference.input_enabled)
        setTtsEnabled(prefs.voice_preference.tts_enabled)
        setVolumePercent(Math.round(prefs.voice_preference.volume * 100))
        setSpeed(prefs.voice_preference.speed)
        setRoleId(currentUser.current_teacher_role_id ?? 'role-shuangling')
        setRoles(roleList)
        setTeacherRoles(teacherRoleList)
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
        voice_preference: {
          input_enabled: inputEnabled,
          tts_enabled: ttsEnabled,
          volume: volumePercent / 100,
          speed,
        },
      })
      applyAge(age)
      await refreshMe()
      showToast('设置已保存')
    } catch {
      showToast('保存失败，请重试')
    }
  }

  const switchTeacher = async (nextRoleId: string) => {
    try {
      await studentService.updateMe({ current_teacher_role_id: nextRoleId })
      await refreshMe()
      showToast('已切换 AI 教师')
    } catch {
      showToast('切换失败，请重试')
    }
  }

  const currentTeacher = teacherRoles.find(
    (role) => role.role_id === currentUser?.current_teacher_role_id,
  )

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
          <h2 className="font-display text-lg text-fg">桌宠</h2>
          <p className="mt-1 text-xs text-muted">
            选择陪伴你学习的桌面伙伴。当前：{getCompanionPet(selectedPetId).displayName}
          </p>
          <CompanionPetPicker
            selectedPetId={selectedPetId}
            onSelect={(petId) => {
              setSelectedPet(petId)
              showToast(`已切换为${getCompanionPet(petId).displayName}`)
            }}
          />
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
          <h2 className="font-display text-lg text-fg">我的 AI 教师</h2>
          <p className="mt-2 text-xs text-muted">
            当前：{currentTeacher?.name ?? '默认（霜铃）'} · {currentTeacher?.tone ?? ''}
          </p>
          {teacherRoles.length === 0 ? (
            <p className="mt-3 text-xs text-muted">暂无可用教师</p>
          ) : (
            <div className="mt-3 grid gap-2">
              {teacherRoles.map((role) => {
                const selected = role.role_id === currentUser?.current_teacher_role_id
                return (
                  <button
                    key={role.role_id}
                    type="button"
                    aria-pressed={selected}
                    className={`rounded-[12px] border p-3 text-left ${
                      selected ? 'border-fg bg-surface' : 'border-border bg-bg hover:border-fg'
                    }`}
                    onClick={() => void switchTeacher(role.role_id)}
                  >
                    <div className="flex items-center justify-between">
                      <strong className="text-sm text-fg">{role.name}</strong>
                      {selected ? (
                        <span className="rounded-full bg-fg-soft px-2 py-0.5 font-mono text-[9px] text-fg">
                          使用中
                        </span>
                      ) : null}
                    </div>
                    <p className="mt-1 text-[11px] text-muted">{role.description}</p>
                    <p className="mt-1 text-[11px] text-muted">
                      {role.tone} · {role.teaching_style}
                    </p>
                  </button>
                )
              })}
            </div>
          )}
        </section>

        <section className="rounded-[14px] border border-border bg-surface p-5">
          <h2 className="font-display text-lg text-fg">语音</h2>
          <div className="mt-4 grid gap-3">
            <label className="flex items-center justify-between text-xs text-muted">
              <span>语音输入</span>
              <input
                type="checkbox"
                checked={inputEnabled}
                aria-label="语音输入开关"
                onChange={(event) => setInputEnabled(event.target.checked)}
                className="h-4 w-4 accent-fg"
              />
            </label>
            <label className="flex items-center justify-between text-xs text-muted">
              <span>语音朗读（TTS）</span>
              <input
                type="checkbox"
                checked={ttsEnabled}
                aria-label="语音朗读开关"
                onChange={(event) => setTtsEnabled(event.target.checked)}
                className="h-4 w-4 accent-fg"
              />
            </label>
            <label className="grid gap-1 text-xs text-muted">
              <span>音量（{volumePercent}%）</span>
              <input
                type="range"
                min={0}
                max={100}
                value={volumePercent}
                aria-label="语音音量"
                onChange={(event) => setVolumePercent(Number(event.target.value))}
                className="accent-fg"
              />
            </label>
            <label className="grid gap-1 text-xs text-muted">
              语速
              <select
                value={speed}
                aria-label="语音语速"
                onChange={(event) => setSpeed(Number(event.target.value))}
                className="h-10 rounded-[10px] border border-border bg-bg px-3 text-[13px] text-fg outline-none focus:border-fg"
              >
                {SPEED_OPTIONS.map((option) => (
                  <option key={option} value={option}>
                    {option}x
                  </option>
                ))}
              </select>
            </label>
          </div>
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
