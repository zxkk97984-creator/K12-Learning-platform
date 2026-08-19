import type {
  EpisodeImportance,
  InsightStatus,
  MemoryEvidence,
  ProfileInsight,
  ProfileInsightType,
  StudentEpisode,
  StudentMemory,
  MemoryStatus,
  MemoryType,
} from '@/entities/memory/types'

/** 0-D §11.2 记忆状态机动作 */
export type MemoryAction = 'CONFIRM' | 'DISPUTE' | 'FORGET' | 'EDIT'

export interface MemoryListParams {
  status?: MemoryStatus
  memory_type?: MemoryType
}

export interface InsightListParams {
  status?: InsightStatus
  insight_type?: ProfileInsightType
  cursor?: string
  limit?: number
}

export interface EpisodeListParams {
  importance?: EpisodeImportance
  cursor?: string
  limit?: number
}

export interface InsightDetail {
  insight: ProfileInsight
  evidence: MemoryEvidence[]
}

export interface MemoryService {
  getMemories(params?: MemoryListParams): Promise<StudentMemory[]>
  updateMemory(memoryId: string, action: MemoryAction, content?: string): Promise<StudentMemory>
  getInsights(params?: InsightListParams): Promise<ProfileInsight[]>
  getInsight(insightId: string): Promise<ProfileInsight>
  getInsightDetail(insightId: string): Promise<InsightDetail>
  getEvidence(evidenceId: string): Promise<MemoryEvidence>
  getEpisodes(params?: EpisodeListParams): Promise<StudentEpisode[]>
  getEpisodeDetail(episodeId: string): Promise<StudentEpisode>
}
