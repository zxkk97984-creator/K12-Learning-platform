import type {
  MemoryEvidence,
  MemoryStatus,
  MemoryType,
  ProfileInsight,
  StudentEpisode,
  StudentMemory,
} from '@/entities/memory/types'

/** 0-D §11.2 记忆状态机动作 */
export type MemoryAction = 'CONFIRM' | 'DISPUTE' | 'FORGET' | 'EDIT'

export interface MemoryListParams {
  status?: MemoryStatus
  memory_type?: MemoryType
}

export interface MemoryService {
  getMemories(params?: MemoryListParams): Promise<StudentMemory[]>
  updateMemory(memoryId: string, action: MemoryAction, content?: string): Promise<StudentMemory>
  getInsights(): Promise<ProfileInsight[]>
  getInsight(insightId: string): Promise<ProfileInsight>
  getEvidence(evidenceId: string): Promise<MemoryEvidence>
  getEpisodes(): Promise<StudentEpisode[]>
}
