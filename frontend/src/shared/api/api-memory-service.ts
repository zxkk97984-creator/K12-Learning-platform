import type {
  MemoryEvidence,
  MemoryStatus,
  MemoryType,
  ProfileInsight,
  StudentEpisode,
  StudentMemory,
} from '@/entities/memory/types'

import { apiRequest } from './http'
import type { MemoryAction, MemoryListParams, MemoryService } from './memory-service'

interface ApiStudentMemoryDTO {
  memory_id: string
  student_id?: string
  memory_type: MemoryType
  content: string
  tags?: string[] | null
  confidence: StudentMemory['confidence']
  status: MemoryStatus
  evidence_ids?: string[] | null
  origin_candidate_id: string | null
  user_confirmed: boolean
  created_at: string
  updated_at: string
  confirmed_at: string | null
}

interface ApiMemoryEvidenceDTO {
  evidence_id: string
  student_id?: string
  source_type: MemoryEvidence['source_type']
  event_ids?: string[] | null
  payload?: Record<string, unknown> | null
  count: number
  first_occurred_at: string | null
  last_occurred_at: string | null
  derived_at: string
  rule_version: string
}

function queryString(params: MemoryListParams = {}): string {
  const query = new URLSearchParams()
  if (params.status !== undefined) query.set('status', params.status)
  if (params.memory_type !== undefined) query.set('memory_type', params.memory_type)
  const encoded = query.toString()
  return encoded ? `?${encoded}` : ''
}

function mapMemory(dto: ApiStudentMemoryDTO): StudentMemory {
  return {
    memory_id: dto.memory_id,
    // StudentMemoryDTO intentionally omits the owner id from the student-facing API.
    student_id: dto.student_id ?? '',
    memory_type: dto.memory_type,
    content: dto.content,
    tags: dto.tags ?? [],
    confidence: dto.confidence,
    status: dto.status,
    evidence_ids: dto.evidence_ids ?? [],
    origin_candidate_id: dto.origin_candidate_id ?? null,
    user_confirmed: dto.user_confirmed,
    created_at: dto.created_at,
    updated_at: dto.updated_at,
    confirmed_at: dto.confirmed_at ?? null,
  }
}

function mapEvidence(dto: ApiMemoryEvidenceDTO): MemoryEvidence {
  return {
    // MemoryEvidenceDTO also omits the owner id; it is scoped by the API token.
    student_id: dto.student_id ?? '',
    evidence_id: dto.evidence_id,
    source_type: dto.source_type,
    event_ids: dto.event_ids ?? [],
    payload: dto.payload ?? {},
    count: dto.count,
    first_occurred_at: dto.first_occurred_at ?? null,
    last_occurred_at: dto.last_occurred_at ?? null,
    derived_at: dto.derived_at,
    rule_version: dto.rule_version,
  }
}

export class ApiMemoryService implements MemoryService {
  async getMemories(params?: MemoryListParams): Promise<StudentMemory[]> {
    const rows = await apiRequest<ApiStudentMemoryDTO[]>(
      `/me/memories${queryString(params)}`,
    )
    return rows.map(mapMemory)
  }

  async updateMemory(
    memoryId: string,
    action: MemoryAction,
    content?: string,
  ): Promise<StudentMemory> {
    return mapMemory(
      await apiRequest<ApiStudentMemoryDTO>(`/me/memories/${encodeURIComponent(memoryId)}`, {
        method: 'PATCH',
        body: {
          action,
          ...(content === undefined ? {} : { content }),
        },
      }),
    )
  }

  async getEvidence(evidenceId: string): Promise<MemoryEvidence> {
    return mapEvidence(
      await apiRequest<ApiMemoryEvidenceDTO>(
        `/me/evidence/${encodeURIComponent(evidenceId)}`,
      ),
    )
  }

  /** Insights and episodes have no frontend API service in this task. */
  async getInsights(): Promise<ProfileInsight[]> {
    return []
  }

  async getInsight(_insightId: string): Promise<ProfileInsight> {
    throw new Error('INSIGHT_ENDPOINT_NOT_IMPLEMENTED')
  }

  async getEpisodes(): Promise<StudentEpisode[]> {
    return []
  }
}
