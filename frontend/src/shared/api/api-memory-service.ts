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

import { getToken } from './auth'
import { API_BASE, ApiError, apiRequest } from './http'
import type {
  EpisodeListParams,
  InsightDetail,
  InsightListParams,
  MemoryAction,
  MemoryListParams,
  MemoryService,
} from './memory-service'

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

interface ApiProfileInsightDTO {
  insight_id: string
  student_id?: string
  insight_type: ProfileInsightType
  dimension: string
  level: ProfileInsight['level']
  description: string
  evidence_ids?: string[] | null
  status: InsightStatus
  valid_from: string
  valid_until: string | null
  rule_version: string
  model_info?: Record<string, unknown> | null
  created_at?: string
  updated_at: string
}

interface ApiStudentEpisodeDTO {
  episode_id: string
  student_id?: string
  title: string
  summary: string
  occurred_at: string
  event_ids?: string[] | null
  book_id: string | null
  chapter_id: string | null
  knowledge_point_ids?: string[] | null
  importance: EpisodeImportance
  tags?: string[] | null
  created_at: string
}

function queryString(params: MemoryListParams = {}): string {
  const query = new URLSearchParams()
  if (params.status !== undefined) query.set('status', params.status)
  if (params.memory_type !== undefined) query.set('memory_type', params.memory_type)
  const encoded = query.toString()
  return encoded ? `?${encoded}` : ''
}

function queryStringFor(
  params: InsightListParams | EpisodeListParams = {},
): string {
  const query = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== '') query.set(key, String(value))
  }
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

function mapInsight(dto: ApiProfileInsightDTO): ProfileInsight {
  return {
    insight_id: dto.insight_id,
    student_id: dto.student_id ?? '',
    insight_type: dto.insight_type,
    dimension: dto.dimension,
    level: dto.level,
    description: dto.description,
    evidence_ids: dto.evidence_ids ?? [],
    status: dto.status,
    valid_from: dto.valid_from,
    valid_until: dto.valid_until,
    rule_version: dto.rule_version,
    model_info: dto.model_info ?? null,
    created_at: dto.created_at ?? dto.updated_at,
    updated_at: dto.updated_at,
  }
}

function mapEpisode(dto: ApiStudentEpisodeDTO): StudentEpisode {
  return {
    episode_id: dto.episode_id,
    student_id: dto.student_id ?? '',
    title: dto.title,
    summary: dto.summary,
    occurred_at: dto.occurred_at,
    event_ids: dto.event_ids ?? [],
    book_id: dto.book_id,
    chapter_id: dto.chapter_id,
    knowledge_point_ids: dto.knowledge_point_ids ?? [],
    importance: dto.importance,
    tags: dto.tags ?? [],
    created_at: dto.created_at,
  }
}

async function requestWithMeta<T>(
  path: string,
): Promise<{ data: T; meta: Record<string, unknown> }> {
  const token = getToken()
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (token) headers.Authorization = `Bearer ${token}`
  const response = await fetch(`${API_BASE}${path}`, { headers })
  const payload: unknown = await response.json().catch(() => null)
  if (!response.ok) {
    const error = (payload as { error?: { code?: string; message?: string; details?: unknown } })
      ?.error
    throw new ApiError(
      response.status,
      error?.code ?? 'HTTP_ERROR',
      error?.message ?? `HTTP ${response.status}`,
      error?.details,
    )
  }
  const envelope = payload as { data: T; meta?: Record<string, unknown> }
  return { data: envelope.data, meta: envelope.meta ?? {} }
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

  async getInsights(params?: InsightListParams): Promise<ProfileInsight[]> {
    const rows = await apiRequest<ApiProfileInsightDTO[]>(
      `/me/insights${queryStringFor(params)}`,
    )
    return rows.map(mapInsight)
  }

  async getInsight(insightId: string): Promise<ProfileInsight> {
    const detail = await this.getInsightDetail(insightId)
    return detail.insight
  }

  async getInsightDetail(insightId: string): Promise<InsightDetail> {
    const { data, meta } = await requestWithMeta<ApiProfileInsightDTO>(
      `/me/insights/${encodeURIComponent(insightId)}`,
    )
    const evidence = Array.isArray(meta.evidence)
      ? (meta.evidence as ApiMemoryEvidenceDTO[]).map(mapEvidence)
      : []
    return { insight: mapInsight(data), evidence }
  }

  async getEpisodes(params?: EpisodeListParams): Promise<StudentEpisode[]> {
    const rows = await apiRequest<ApiStudentEpisodeDTO[]>(
      `/me/episodes${queryStringFor(params)}`,
    )
    return rows.map(mapEpisode)
  }

  async getEpisodeDetail(episodeId: string): Promise<StudentEpisode> {
    return mapEpisode(
      await apiRequest<ApiStudentEpisodeDTO>(
        `/me/episodes/${encodeURIComponent(episodeId)}`,
      ),
    )
  }
}
