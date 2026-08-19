import type { MemoryService } from '@/shared/api/memory-service'
import type { MemoryAction } from '@/shared/api/memory-service'
import type { StudentMemory } from '@/entities/memory/types'

import { delay } from '../delay'
import { mockEpisodes, mockEvidence, mockInsights, mockMemories } from '../data/memory'

let memories: StudentMemory[] = mockMemories.map((memory) => ({ ...memory }))

export class MockMemoryService implements MemoryService {
  async getMemories() {
    return delay(memories.map((memory) => ({ ...memory })), 200)
  }

  async updateMemory(memoryId: string, action: MemoryAction, content?: string) {
    const memory = memories.find((item) => item.memory_id === memoryId)
    if (!memory) throw new Error(`MEMORY_NOT_FOUND: ${memoryId}`)
    const now = new Date().toISOString()
    const updated: StudentMemory = { ...memory, updated_at: now }
    if (action === 'CONFIRM') {
      updated.status = 'ACTIVE'
      updated.user_confirmed = true
      updated.confirmed_at = now
    } else if (action === 'DISPUTE') {
      updated.status = 'DISPUTED'
    } else if (action === 'FORGET') {
      updated.status = 'REMOVED'
    } else if (action === 'EDIT') {
      if (!content) throw new Error('VALIDATION_ERROR: content required for EDIT')
      updated.content = content
      updated.user_confirmed = true
    }
    memories = memories.map((item) => (item.memory_id === memoryId ? updated : item))
    return delay({ ...updated }, 200)
  }

  async getInsights() {
    return delay(mockInsights.map((insight) => ({ ...insight })), 200)
  }

  async getInsight(insightId: string) {
    const insight = mockInsights.find((item) => item.insight_id === insightId)
    if (!insight) throw new Error(`INSIGHT_NOT_FOUND: ${insightId}`)
    return delay({ ...insight }, 200)
  }

  async getEvidence(evidenceId: string) {
    const evidence = mockEvidence.find((item) => item.evidence_id === evidenceId)
    if (!evidence) throw new Error(`EVIDENCE_NOT_FOUND: ${evidenceId}`)
    return delay({ ...evidence }, 200)
  }

  async getEpisodes() {
    return delay(mockEpisodes.map((episode) => ({ ...episode })), 200)
  }
}
