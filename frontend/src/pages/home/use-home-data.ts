import { useCallback, useEffect, useState } from 'react'

import type { Book, BookProgress, Chapter } from '@/entities/book/types'
import type { StudentEpisode, StudentMemory } from '@/entities/memory/types'
import type { QuizSession } from '@/entities/quiz/types'
import type { LearningNextAction, Recommendation } from '@/shared/api/recommendation-service'
import {
  contentService,
  memoryService,
  quizService,
  recommendationService,
  studentService,
} from '@/shared/services'

export interface HomeStats {
  learning_days: number
  total_learning_minutes: number
  completed_books: number
  completed_chapters: number
  quiz_count: number
}

export interface HomeData {
  nickname: string
  stats: HomeStats | null
  statsError: boolean
  /** 继续学习卡 */
  progressLoading: boolean
  progressError: boolean
  progress: BookProgress | null
  continueBook: Book | null
  continueChapter: Chapter | null
  episodes: StudentEpisode[]
  episodesError: boolean
  memories: StudentMemory[]
  memoriesError: boolean
  quizzes: QuizSession[]
  quizzesError: boolean
  recommendations: Recommendation[]
  recommendationsLoading: boolean
  recommendationsError: boolean
  /** §6.1 统一下一步行动（首页行动卡）。 */
  learningNext: LearningNextAction | null
  learningNextLoading: boolean
  reloadRecommendations: () => Promise<void>
  dismissRecommendation: (id: string) => Promise<void>
}

/** T08：首页数据独立并发请求；任一片区失败不影响其他片区，不拖垮整页。 */
export function useHomeData(initialNickname: string): HomeData {
  const [nickname, setNickname] = useState(initialNickname)
  const [stats, setStats] = useState<HomeStats | null>(null)
  const [statsError, setStatsError] = useState(false)
  const [progressLoading, setProgressLoading] = useState(true)
  const [progressError, setProgressError] = useState(false)
  const [progress, setProgress] = useState<BookProgress | null>(null)
  const [continueBook, setContinueBook] = useState<Book | null>(null)
  const [continueChapter, setContinueChapter] = useState<Chapter | null>(null)
  const [episodes, setEpisodes] = useState<StudentEpisode[]>([])
  const [episodesError, setEpisodesError] = useState(false)
  const [memories, setMemories] = useState<StudentMemory[]>([])
  const [memoriesError, setMemoriesError] = useState(false)
  const [quizzes, setQuizzes] = useState<QuizSession[]>([])
  const [quizzesError, setQuizzesError] = useState(false)
  const [recommendations, setRecommendations] = useState<Recommendation[]>([])
  const [recommendationsLoading, setRecommendationsLoading] = useState(true)
  const [recommendationsError, setRecommendationsError] = useState(false)
  const [learningNext, setLearningNext] = useState<LearningNextAction | null>(null)
  const [learningNextLoading, setLearningNextLoading] = useState(true)

  // 统计与继续学习：并发独立，互不拖累，失败保留空态 + 可见错误标志。
  useEffect(() => {
    let active = true
    void (async () => {
      try {
        const me = await studentService.getMe()
        if (!active) return
        setNickname(me.nickname)
        setStats({
          learning_days: me.learning_days,
          total_learning_minutes: me.total_learning_minutes,
          completed_books: me.completed_books,
          completed_chapters: me.completed_chapters,
          quiz_count: me.quiz_count,
        })
        setStatsError(false)
      } catch {
        if (!active) return
        setStats(null)
        setStatsError(true)
      }
    })()
    void (async () => {
      try {
        const progressItems = await contentService.getProgress()
        if (!active) return
        const latest =
          progressItems
            .filter((item) => item.chapter_id)
            .sort((left, right) => {
              const l = left.last_read_at ? Date.parse(left.last_read_at) : 0
              const r = right.last_read_at ? Date.parse(right.last_read_at) : 0
              return r - l
            })[0] ?? null
        setProgress(latest)
        if (latest?.chapter_id) {
          const [book, chapter] = await Promise.all([
            contentService.getBook(latest.book_id),
            contentService.getChapter(latest.chapter_id),
          ])
          if (!active) return
          setContinueBook(book)
          setContinueChapter(chapter)
        } else {
          setContinueBook(null)
          setContinueChapter(null)
        }
        setProgressError(false)
      } catch {
        if (!active) return
        setProgress(null)
        setContinueBook(null)
        setContinueChapter(null)
        setProgressError(true)
      } finally {
        if (active) setProgressLoading(false)
      }
    })()
    void (async () => {
      try {
        const items = await memoryService.getEpisodes()
        if (active) { setEpisodes(items); setEpisodesError(false) }
      } catch {
        if (active) { setEpisodes([]); setEpisodesError(true) }
      }
    })()
    void (async () => {
      try {
        const items = await memoryService.getMemories()
        if (active) { setMemories(items); setMemoriesError(false) }
      } catch {
        if (active) { setMemories([]); setMemoriesError(true) }
      }
    })()
    void (async () => {
      try {
        const items = await quizService.getQuizSessions()
        if (active) { setQuizzes(items); setQuizzesError(false) }
      } catch {
        if (active) { setQuizzes([]); setQuizzesError(true) }
      }
    })()
    return () => {
      active = false
    }
  }, [])

  const loadRecommendationList = useCallback(async () => {
    setRecommendationsLoading(true)
    try {
      const items = await recommendationService.getRecommendations()
      setRecommendations(items.filter((item) => item.status === 'ACTIVE').slice(0, 3))
      setRecommendationsError(false)
    } catch {
      setRecommendations([])
      setRecommendationsError(true)
    } finally {
      setRecommendationsLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadRecommendationList()
  }, [loadRecommendationList])

  // T16 §6.1 下一步行动：独立并发，失败保留空态（不拖垮首页）。
  useEffect(() => {
    let active = true
    void (async () => {
      try {
        const next = await recommendationService.getLearningNext()
        if (active) setLearningNext(next)
      } catch {
        if (active) setLearningNext(null)
      } finally {
        if (active) setLearningNextLoading(false)
      }
    })()
    return () => {
      active = false
    }
  }, [])

  const dismissRecommendation = useCallback(
    async (recommendationId: string) => {
      try {
        await recommendationService.dismissRecommendation(recommendationId)
      } catch {
        // 失败静默，下次刷新重试
      }
      await loadRecommendationList()
    },
    [loadRecommendationList],
  )

  return {
    nickname,
    stats,
    statsError,
    progressLoading,
    progressError,
    progress,
    continueBook,
    continueChapter,
    episodes,
    episodesError,
    memories,
    memoriesError,
    quizzes,
    quizzesError,
    recommendations,
    recommendationsLoading,
    recommendationsError,
    learningNext,
    learningNextLoading,
    reloadRecommendations: loadRecommendationList,
    dismissRecommendation,
  }
}
