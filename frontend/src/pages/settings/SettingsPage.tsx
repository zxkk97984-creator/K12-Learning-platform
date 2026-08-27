import { useEffect, useRef, useState, type ReactNode } from 'react'

import type {
  PreferredDifficulty,
  PreferredExplanationStyle,
  PreferredSessionLength,
  TeacherRoleDTO,
} from '@/entities/student/types'
import type { Stage } from '@/entities/student/types'
import { useAuth } from '@/features/auth'
import { CompanionPetPicker, getCompanionPet, useCompanionStore } from '@/features/companion'
import { useToastStore } from '@/features/feedback'
import { learningService } from '@/shared/api/learning-service'
import { studentService } from '@/shared/services'
import { UserAvatar } from '@/shared/ui/UserAvatar'

const AGE_OPTIONS = [
  { key: 'primary', label: '小学' },
  { key: 'junior', label: '初中' },
  { key: 'senior', label: '高中' },
] as const

const AVATAR_PRESETS = ['🐱', '🦊', '🐼', '🐸', '🐧', '🦁', '🐨', '🐯', '🐰', '🦉', '⭐', '🚀']

const GRADE_STAGE_OPTIONS: { key: Stage; label: string; grades: number[] }[] = [
  { key: 'PRIMARY', label: '小学', grades: [1, 2, 3, 4, 5, 6] },
  { key: 'JUNIOR', label: '初中', grades: [7, 8, 9] },
  { key: 'SENIOR', label: '高中', grades: [10, 11, 12] },
]

const STYLE_OPTIONS: { value: PreferredExplanationStyle; label: string }[] = [
  { value: 'EXAMPLE_BASED', label: '例子优先' },
  { value: 'VISUAL', label: '图解优先' },
  { value: 'STORY', label: '故事优先' },
  { value: 'DIRECT_DEFINITION', label: '直接定义' },
  { value: 'STEP_BY_STEP', label: '分步骤' },
  { value: 'CODE', label: '代码示例' },
  { value: 'INTERACTIVE', label: '互动提问' },
]

function gradeLabel(grade: number): string {
  if (grade <= 6) return `${grade} 年级`
  if (grade <= 9) return `初${'一二三'[grade - 7]}`
  return `${['高一', '高二', '高三'][grade - 10]}`
}

const SPEED_OPTIONS = [0.5, 0.75, 1, 1.25, 1.5, 2]

function applyAge(age: 'primary' | 'junior' | 'senior'): void {
  document.documentElement.dataset.age = age === 'junior' ? '' : age
  window.localStorage.setItem('shuangling-age', age)
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="grid gap-1 text-xs text-muted">
      {label}
      {children}
    </label>
  )
}

const inputClass =
  'h-10 rounded-[10px] border border-border bg-bg px-3 text-[13px] text-fg outline-none focus:border-fg'

export default function SettingsPage() {
  const showToast = useToastStore((state) => state.showToast)
  const { currentUser, refreshMe } = useAuth()
  const selectedPetId = useCompanionStore((state) => state.selectedPetId)
  const setSelectedPet = useCompanionStore((state) => state.setSelectedPet)
  const [nickname, setNickname] = useState('')
  const [avatarUrl, setAvatarUrl] = useState('')
  const [avatarUploading, setAvatarUploading] = useState(false)
  const avatarInputRef = useRef<HTMLInputElement>(null)
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
        const [prefs, teacherRoleList] = await Promise.all([
          studentService.getPreferences(),
          studentService.getTeacherRoles(),
        ])
        setNickname(currentUser.nickname)
        setAvatarUrl(currentUser.avatar_url ?? '')
        setGrade(currentUser.grade)
        setLanguage(currentUser.language || 'zh-CN')
        setLearningGoal(currentUser.learning_goal ?? '')
        setStyle(prefs.preferred_explanation_style)
        setDifficulty(prefs.preferred_difficulty)
        setSessionLength(prefs.preferred_session_length)
        setInputEnabled(prefs.voice_preference.input_enabled)
        setTtsEnabled(prefs.voice_preference.tts_enabled)
        setVolumePercent(Math.round(prefs.voice_preference.volume * 100))
        setSpeed(prefs.voice_preference.speed)
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
      const profilePatch = {
        nickname,
        avatar_url: avatarUrl || null,
        grade,
        language,
        learning_goal: learningGoal || null,
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
      void learningService
        .createEvent({
          event_type: 'ROLE_SWITCHED',
          occurred_at: new Date().toISOString(),
          payload: { teacher_role_id: nextRoleId },
        })
        .catch(() => undefined)
      await refreshMe()
      showToast('已切换教学风格')
    } catch {
      showToast('切换失败，请重试')
    }
  }

  const uploadAvatar = async (file: File) => {
    setAvatarUploading(true)
    try {
      const updated = await studentService.uploadAvatar(file)
      setAvatarUrl(updated.avatar_url ?? '')
      await refreshMe()
      showToast('头像已更新')
    } catch {
      showToast('头像上传失败，请重试')
    } finally {
      setAvatarUploading(false)
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
        <p className="mt-4 text-sm text-muted" role="status">正在加载设置…</p>
      </section>
    )
  }

  return (
    <section className="py-10">
      <p className="font-mono text-xs uppercase tracking-widest text-accent">设置</p>
      <h1 className="mt-3 font-display text-4xl text-fg">设置</h1>

      <div className="mt-6 grid items-start gap-6 lg:grid-cols-2">
        <div className="grid content-start gap-6">
          <section className="rounded-[14px] border border-border bg-surface p-5">
            <h2 className="font-display text-lg text-fg">账号</h2>
            <div className="mt-4 flex items-center gap-4">
              <UserAvatar nickname={nickname} avatarUrl={avatarUrl} size="lg" />
              <div>
                <p className="text-xs font-medium text-fg">头像</p>
                <p className="mt-0.5 text-[11px] leading-relaxed text-muted">
                  挑一个系统头像，或上传你自己的图片，保存后会显示在顶栏与首页。
                </p>
              </div>
            </div>
            <div className="mt-3 flex flex-wrap items-center gap-2" aria-label="头像选择">
              {AVATAR_PRESETS.map((emoji) => {
                const selected = avatarUrl === emoji
                return (
                  <button
                    key={emoji}
                    type="button"
                    aria-pressed={selected}
                    aria-label={`选择头像 ${emoji}`}
                    onClick={() => setAvatarUrl(selected ? '' : emoji)}
                    className={`grid h-10 w-10 place-items-center rounded-full border text-lg transition-colors ${
                      selected ? 'border-fg bg-fg-soft shadow-sm' : 'border-border hover:border-fg'
                    }`}
                  >
                    <span aria-hidden="true">{emoji}</span>
                  </button>
                )
              })}
              <button
                type="button"
                aria-pressed={Boolean(avatarUrl && !AVATAR_PRESETS.includes(avatarUrl))}
                onClick={() => avatarInputRef.current?.click()}
                disabled={avatarUploading}
                title={avatarUploading ? '上传中…' : '上传自定义头像'}
                className={`grid h-10 w-10 place-items-center overflow-hidden rounded-full border border-dashed transition-colors ${
                  avatarUploading ? 'opacity-60' : 'border-border hover:border-fg'
                }`}
              >
                {avatarUrl && !AVATAR_PRESETS.includes(avatarUrl) ? (
                  <img src={avatarUrl} alt="" className="h-full w-full object-cover" />
                ) : (
                  <span className="flex flex-col items-center text-[9px] leading-tight text-muted">
                    <span aria-hidden="true" className="text-base">＋</span>
                    上传
                  </span>
                )}
              </button>
            </div>
            <input
              ref={avatarInputRef}
              type="file"
              accept="image/jpeg,image/png,image/webp"
              className="hidden"
              aria-label="上传自定义头像"
              onChange={(event) => {
                const file = event.target.files?.[0]
                event.target.value = ''
                if (file) void uploadAvatar(file)
              }}
            />
            <div className="mt-4 grid gap-3">
              <Field label="昵称">
                <input
                  value={nickname}
                  onChange={(event) => setNickname(event.target.value)}
                  className={inputClass}
                />
              </Field>
              <Field label="年级">
                <select
                  aria-label="年级"
                  value={grade}
                  onChange={(event) => setGrade(Number(event.target.value))}
                  className={inputClass}
                >
                  {GRADE_STAGE_OPTIONS.map((stage) => (
                    <optgroup key={stage.key} label={stage.label}>
                      {stage.grades.map((value) => (
                        <option key={value} value={value}>
                          {gradeLabel(value)}
                        </option>
                      ))}
                    </optgroup>
                  ))}
                </select>
              </Field>
              <Field label="语言">
                <select
                  value={language}
                  onChange={(event) => setLanguage(event.target.value)}
                  className={inputClass}
                >
                  <option value="zh-CN">简体中文</option>
                  <option value="zh-TW">繁體中文</option>
                  <option value="en-US">English</option>
                </select>
              </Field>
              <Field label="学习目标">
                <input
                  value={learningGoal}
                  onChange={(event) => setLearningGoal(event.target.value)}
                  placeholder="例如：理解机器学习的基本概念"
                  className={inputClass}
                />
              </Field>
            </div>
          </section>

          <section className="rounded-[14px] border border-border bg-surface p-5">
            <h2 className="font-display text-lg text-fg">学习偏好</h2>
            <div className="mt-4 grid gap-3">
              <Field label="讲解方式">
                <select
                  value={style}
                  onChange={(event) => setStyle(event.target.value as PreferredExplanationStyle)}
                  className={inputClass}
                >
                  {STYLE_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="难度">
                <select
                  value={difficulty}
                  onChange={(event) => setDifficulty(event.target.value as PreferredDifficulty)}
                  className={inputClass}
                >
                  {(
                    [
                      ['EASY', '简单'],
                      ['MEDIUM', '中等'],
                      ['HARD', '较难'],
                    ] as const
                  ).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="学习节奏">
                <select
                  value={sessionLength}
                  onChange={(event) => setSessionLength(event.target.value as PreferredSessionLength)}
                  className={inputClass}
                >
                  {(
                    [
                      ['SHORT', '短时、多轮'],
                      ['MEDIUM', '中等时长'],
                      ['LONG', '较长连续'],
                    ] as const
                  ).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
              </Field>
            </div>
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
              <Field label="语速">
                <select
                  value={speed}
                  aria-label="语音语速"
                  onChange={(event) => setSpeed(Number(event.target.value))}
                  className={inputClass}
                >
                  {SPEED_OPTIONS.map((option) => (
                    <option key={option} value={option}>
                      {option}x
                    </option>
                  ))}
                </select>
              </Field>
            </div>
          </section>
        </div>

        <div className="grid content-start gap-6">
          <section className="rounded-[14px] border border-border bg-surface p-5">
            <h2 className="font-display text-lg text-fg">AI 教师风格</h2>
            <p className="mt-2 text-xs text-muted">
              选择 AI 回答你的方式，可搭配任意教师形象。当前：
              {currentTeacher?.name ?? '默认（温暖鼓励）'} · {currentTeacher?.tone ?? ''}
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
            <h2 className="font-display text-lg text-fg">AI 教师形象</h2>
            <p className="mt-1 text-xs text-muted">
              选择你的 AI 教师形象，教学风格保持不变。当前：{getCompanionPet(selectedPetId).displayName}
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
        </div>
      </div>

      <div className="mt-8 flex justify-end border-t border-border pt-5">
        <button
          type="button"
          className="rounded-[10px] bg-accent px-6 py-2.5 text-sm text-surface hover:bg-accent/85"
          onClick={() => void save()}
        >
          保存设置
        </button>
      </div>
    </section>
  )
}
