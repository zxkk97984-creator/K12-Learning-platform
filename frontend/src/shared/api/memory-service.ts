import type {
  MemoryEvidence,
  ProfileInsight,
  StudentEpisode,
  StudentMemory,
} from '@/entities/memory/types'

/** 0-D §11.2 记忆状态机动作 */
export type MemoryAction = 'CONFIRM' | 'DISPUTE' | 'FORGET' | 'EDIT'

export interface MemoryService {
  getMemories(): Promise<StudentMemory[]>
  updateMemory(memoryId: string, action: MemoryAction, content?: string): Promise<StudentMemory>
  getInsights(): Promise<ProfileInsight[]>
  getInsight(insightId: string): Promise<ProfileInsight>
  getEvidence(evidenceId: string): Promise<MemoryEvidence>
  getEpisodes(): Promise<StudentEpisode[]>
}
