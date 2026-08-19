import type { StudentMemory, StudentEpisode } from '@/entities/memory/types'
import type {
  EpisodeListParams,
  InsightDetail,
  InsightListParams,
  MemoryAction,
  MemoryService,
} from '@/shared/api/memory-service'

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

  async getInsights(params?: InsightListParams) {
    let rows = mockInsights.map((insight) => ({ ...insight }))
    if (params?.status) rows = rows.filter((insight) => insight.status === params.status)
    if (params?.insight_type) {
      rows = rows.filter((insight) => insight.insight_type === params.insight_type)
    }
    return delay(rows, 200)
  }

  async getInsight(insightId: string) {
    const insight = mockInsights.find((item) => item.insight_id === insightId)
    if (!insight) throw new Error(`INSIGHT_NOT_FOUND: ${insightId}`)
    return delay({ ...insight }, 200)
  }

  async getInsightDetail(insightId: string): Promise<InsightDetail> {
    const insight = mockInsights.find((item) => item.insight_id === insightId)
    if (!insight) throw new Error(`INSIGHT_NOT_FOUND: ${insightId}`)
    const evidence = mockEvidence.filter((item) =>
      insight.evidence_ids.includes(item.evidence_id),
    )
    return delay({ insight: { ...insight }, evidence: evidence.map((item) => ({ ...item })) }, 200)
  }

  async getEvidence(evidenceId: string) {
    const evidence = mockEvidence.find((item) => item.evidence_id === evidenceId)
    if (!evidence) throw new Error(`EVIDENCE_NOT_FOUND: ${evidenceId}`)
    return delay({ ...evidence }, 200)
  }

  async getEpisodes(params?: EpisodeListParams) {
    let rows: StudentEpisode[] = mockEpisodes.map((episode) => ({ ...episode }))
    if (params?.importance) {
      rows = rows.filter((episode) => episode.importance === params.importance)
    }
    return delay(rows, 200)
  }

  async getEpisodeDetail(episodeId: string) {
    const episode = mockEpisodes.find((item) => item.episode_id === episodeId)
    if (!episode) throw new Error(`EPISODE_NOT_FOUND: ${episodeId}`)
    return delay({ ...episode }, 200)
  }
}
