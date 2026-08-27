import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import type {
  MemoryEvidence,
  ProfileInsight,
  StudentEpisode,
  StudentMemory,
} from '@/entities/memory/types'
import type { StudentPreference, StudentProfile } from '@/entities/student/types'
import { useAuth } from '@/features/auth'
import { useCompanionStore, useTeacherName } from '@/features/companion'
import { useConversationStore } from '@/features/conversation'
import { useScreenContext } from '@/features/screen-context'
import { useToastStore } from '@/features/feedback'
import { buildProfileExportJson, parseProfileFrontmatter } from './profile-labels'
import { memoryService, studentService } from '@/shared/services'

import { ArchiveDocCard } from './components/ArchiveDocCard'
import { ChangeCard } from './components/ChangeCard'
import { EpisodeListCard } from './components/EpisodeListCard'
import { HistoryCard } from './components/HistoryCard'
import { InsightListCard } from './components/InsightListCard'
import { ProfileOverviewCard } from './components/ProfileOverviewCard'
import { ProfileSidebar } from './components/ProfileSidebar'

type ProfileView = 'student' | 'archive'
type DocMode = 'preview' | 'edit'

const VIEW_TABS: Array<[ProfileView, string]> = [
  ['student', '学习画像'],
  ['archive', 'AI 档案'],
]

function ProfileSkeleton() {
  return (
    <div className="mt-6 grid gap-4" aria-busy="true" aria-label="正在加载学习画像">
      <div className="h-[180px] animate-pulse rounded-[14px] bg-fg-soft" />
      <div className="h-[120px] animate-pulse rounded-[14px] bg-fg-soft" />
      <div className="h-[200px] animate-pulse rounded-[14px] bg-fg-soft" />
    </div>
  )
}

export default function ProfilePage() {
  const navigate = useNavigate()
  const runIntent = useConversationStore((state) => state.runIntent)
  const { screenContext } = useScreenContext()
  const showToast = useToastStore((state) => state.showToast)
  const teacherName = useTeacherName()
  const { currentUser } = useAuth()
  const [profile, setProfile] = useState<StudentProfile | null>(null)
  const [prefs, setPrefs] = useState<StudentPreference | null>(null)
  const [insights, setInsights] = useState<ProfileInsight[]>([])
  const [historyInsights, setHistoryInsights] = useState<ProfileInsight[]>([])
  const [episodes, setEpisodes] = useState<StudentEpisode[]>([])
  const [memories, setMemories] = useState<StudentMemory[]>([])
  const [loading, setLoading] = useState(true)
  const [view, setView] = useState<ProfileView>('student')
  const [docMode, setDocMode] = useState<DocMode>('preview')
  const [mdDraft, setMdDraft] = useState('')
  const [userEdited, setUserEdited] = useState(false)
  // Phase 4：真实持久化草稿与导出数据
  const [learningGoalDraft, setLearningGoalDraft] = useState('')
  const [goalDirty, setGoalDirty] = useState(false)
  const [exportMemories, setExportMemories] = useState<
    Array<{
      memory_id: string
      memory_type: string
      content: string
      confidence: string
      status: string
    }>
  >([])

  const load = useCallback(async () => {
    try {
      const [preference, insightList, historyList, memoryList, episodeList] = await Promise.all([
        studentService.getPreferences(),
        memoryService.getInsights(),
        memoryService.getInsights({ status: 'SUPERSEDED' }),
        memoryService.getMemories(),
        memoryService.getEpisodes(),
      ])
      setPrefs(preference)
      setInsights(insightList)
      setHistoryInsights(historyList)
      setMemories(memoryList)
      setEpisodes(episodeList)
      // Phase 4：导出数据源 + 学习目标草稿初始化（来自 DB）
      setExportMemories(
        memoryList.map((item) => ({
          memory_id: item.memory_id,
          memory_type: item.memory_type,
          content: item.content,
          confidence: item.confidence,
          status: item.status,
        })),
      )
    } catch {
      // 后端不可用时降级为空态
    } finally {
      setLoading(false)
    }
  }, [])

  // 整改 3：profile 变化（首次加载或保存返回）时同步草稿；
  // 用户已开始编辑（dirty）时不覆盖未保存输入。
  useEffect(() => {
    if (!goalDirty && profile) {
      setLearningGoalDraft(profile.learning_goal ?? '')
    }
  }, [profile?.learning_goal, profile, goalDirty])

  useEffect(() => {
    setProfile(currentUser)
    if (currentUser) void load()
  }, [currentUser, load])

  const triggerIntent = (intent: Parameters<typeof runIntent>[0]) => {
    runIntent(intent, undefined, screenContext)
    useCompanionStore.getState().setOpen(true)
  }

  const openArchive = () => setView('archive')

  const loadEvidence = async (insight: ProfileInsight): Promise<MemoryEvidence[]> => {
    const detail = await memoryService.getInsightDetail(insight.insight_id)
    return detail.evidence
  }

  const loadEpisodeDetail = (episode: StudentEpisode): Promise<StudentEpisode> =>
    memoryService.getEpisodeDetail(episode.episode_id)

  const saveDoc = async () => {
    if (!mdDraft.trim() && !learningGoalDraft.trim()) {
      showToast('内容不能为空')
      return
    }
    // Phase 4：编辑真实持久化到 student_profiles / student_preferences
    try {
      const patch = parseProfileFrontmatter(mdDraft || '')
      const goal = learningGoalDraft.trim()
      const profilePatch: Record<string, unknown> = {}
      if (patch.grade !== undefined) profilePatch.grade = patch.grade
      if (goal) profilePatch.learning_goal = goal
      if (Object.keys(profilePatch).length > 0 && profile) {
        // 整改 3：以 updateMe 返回的最新档案刷新本地状态（含 grade 等）
        const updated = await studentService.updateMe(profilePatch)
        if (updated) setProfile(updated)
        setGoalDirty(false)
      }
      const prefPatch: Record<string, unknown> = {}
      for (const key of [
        'preferred_explanation_style',
        'preferred_difficulty',
        'preferred_session_length',
      ] as const) {
        if (patch[key] !== undefined) prefPatch[key] = patch[key]
      }
      if (Object.keys(prefPatch).length > 0) {
        await studentService.updatePreferences(prefPatch)
      }
      setUserEdited(false)
      setDocMode('preview')
      await load()
      showToast(`已保存，${teacherName}下次讲解会参考新画像`)
    } catch {
      showToast('保存失败，请稍后重试')
    }
  }

  /** 导出真实档案 JSON（来自数据库），触发浏览器下载 */
  const exportProfile = () => {
    if (!profile) return
    const json = buildProfileExportJson({
      profile: { ...profile },
      preferences: prefs ? { ...prefs } : null,
      insights: insights.map((item) => ({ ...item })),
      memories: exportMemories.map((item) => ({ ...item })),
    })
    const blob = new Blob([json], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = `${profile.nickname}-profile.json`
    document.body.appendChild(anchor)
    anchor.click()
    document.body.removeChild(anchor)
    URL.revokeObjectURL(url)
    showToast('已导出学习档案 JSON')
  }

  return (
    <section className="py-10">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="font-mono text-xs uppercase tracking-widest text-accent">成长 · AI 学习画像</p>
          <h1 className="mt-3 font-display text-4xl text-fg">{teacherName}眼中的你。</h1>
        </div>
        <div className="flex gap-0.5 rounded-[10px] bg-fg-soft p-1" role="tablist" aria-label="画像视图切换">
          {VIEW_TABS.map(([value, label]) => (
            <button
              key={value}
              type="button"
              role="tab"
              aria-selected={view === value}
              onClick={() => setView(value)}
              className={`rounded-lg px-3 py-1.5 text-xs transition-colors ${
                view === value ? 'bg-surface text-fg shadow-sm' : 'text-muted hover:text-fg'
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {!currentUser ? (
        <p className="mt-6 text-sm text-muted">
          学习画像暂不可用
          <Link to="/login" className="ml-2 text-accent hover:underline">
            去登录 →
          </Link>
        </p>
      ) : loading || !prefs ? (
        <ProfileSkeleton />
      ) : (
        <div className="mt-6 grid grid-cols-[minmax(0,1fr)_280px] items-start gap-4 max-md:grid-cols-1">
          <div className="grid gap-4">
            {view === 'student' ? (
              <>
                <ProfileOverviewCard prefs={prefs} overview={insights.find((item) => item.dimension === 'explanation_preference')} />
                <InsightListCard insights={insights} teacherName={teacherName} loadEvidence={loadEvidence} />
                <ChangeCard change={insights.find((item) => item.dimension === 'questioning_habit' && item.insight_type === 'CHANGE')} />
                <HistoryCard historyInsights={historyInsights} />
                <EpisodeListCard episodes={episodes} loadDetail={loadEpisodeDetail} />
              </>
            ) : (
              <ArchiveDocCard
                profile={profile ?? currentUser}
                prefs={prefs}
                historyInsights={historyInsights}
                learningGoalDraft={learningGoalDraft}
                onLearningGoalDraftChange={(value) => {
                  setGoalDirty(true)
                  setLearningGoalDraft(value)
                }}
                insights={insights}
                teacherName={teacherName}
                userEdited={userEdited}
                docMode={docMode}
                mdDraft={mdDraft}
                onDocModeChange={setDocMode}
                onMdDraftChange={setMdDraft}
                onSave={() => void saveDoc()}
                onExport={exportProfile}
              />
            )}
          </div>

          <div className="mt-4">
            <button
              type="button"
              data-testid="open-memories"
              className="rounded-[10px] border border-border bg-surface px-3 py-2 text-xs text-fg hover:border-fg"
              onClick={() => navigate('/profile/memories')}
            >
              管理我的记忆 →
            </button>
          </div>

          <ProfileSidebar
            teacherName={teacherName}
            memories={memories}
            onChanged={() => void load()}
            onAskWhy={() => triggerIntent('profile-question')}
            onOpenArchive={openArchive}
          />
        </div>
      )}
    </section>
  )
}
