import type {
  AdminBook,
  AdminKnowledgeResource,
  AdminStats,
} from '@/entities/admin/types'

import { getToken } from './auth'
import { ApiError, emitUnauthorized } from './http'
import { API_BASE, apiRequest } from './http'

export interface CreateBookInput {
  title: string
  grade_min: number
  grade_max: number
  tags?: string[]
}

export interface UploadKnowledgeInput {
  file: File
  source_name: string
  source_url: string
  author?: string
  license: string
  copyright_status: string
}

function requestKey(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`
}

async function requestWithKey<T>(
  path: string,
  method: 'POST' | 'PATCH',
  body: Record<string, unknown>,
): Promise<T> {
  const token = getToken()
  const response = await fetch(`${API_BASE}${path}`, {
    method,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      'Idempotency-Key': requestKey(),
    },
    body: JSON.stringify(body),
  })
  const payload = (await response.json()) as {
    data: T
    error?: { code: string; message: string }
  }
  if (response.status === 401) {
    // Phase 5-A 整改 5：原始 fetch 路径同样触发全局未授权事件
    emitUnauthorized()
    throw new ApiError(401, payload.error?.code ?? 'UNAUTHENTICATED', payload.error?.message ?? '登录已过期')
  }
  if (!response.ok) {
    throw new Error(payload.error?.message ?? `HTTP ${response.status}`)
  }
  return payload.data
}

export const adminService = {
  async getStats(): Promise<AdminStats> {
    return apiRequest<AdminStats>('/admin/stats')
  },

  async getBooks(): Promise<AdminBook[]> {
    const payload = await apiRequest<AdminBook[] | { items: AdminBook[] }>(
      '/admin/books?limit=100',
    )
    return Array.isArray(payload) ? payload : payload.items
  },

  async createBook(input: CreateBookInput): Promise<AdminBook> {
    return requestWithKey<AdminBook>('/admin/books', 'POST', {
      ...input,
      difficulty: 'MEDIUM',
      estimated_minutes: 30,
    })
  },

  async patchBook(bookId: string, patch: { status: AdminBook['status'] }): Promise<AdminBook> {
    return requestWithKey<AdminBook>(`/admin/books/${bookId}`, 'PATCH', patch)
  },

  async getKnowledgeResources(): Promise<AdminKnowledgeResource[]> {
    const [ready, failed] = await Promise.all([
      apiRequest<AdminKnowledgeResource[] | { items: AdminKnowledgeResource[] }>(
        '/knowledge/resources?status=READY&limit=100',
      ),
      apiRequest<AdminKnowledgeResource[] | { items: AdminKnowledgeResource[] }>(
        '/knowledge/resources?status=FAILED&limit=100',
      ),
    ])
    const normalize = (payload: AdminKnowledgeResource[] | { items: AdminKnowledgeResource[] }) =>
      Array.isArray(payload) ? payload : payload.items
    return [...normalize(ready), ...normalize(failed)]
  },

  async uploadKnowledgeResource(input: UploadKnowledgeInput): Promise<AdminKnowledgeResource> {
    const form = new FormData()
    form.append('file', input.file)
    form.append('source_name', input.source_name)
    form.append('source_url', input.source_url)
    if (input.author) form.append('author', input.author)
    form.append('license', input.license)
    form.append('copyright_status', input.copyright_status)
    const token = getToken()
    const response = await fetch(`${API_BASE}/admin/knowledge/resources`, {
      method: 'POST',
      headers: {
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        'Idempotency-Key': requestKey(),
      },
      body: form,
    })
    const payload = (await response.json()) as {
      data: AdminKnowledgeResource
      error?: { code: string; message: string }
    }
    if (response.status === 401) {
      emitUnauthorized()
      throw new ApiError(
        401,
        payload.error?.code ?? 'UNAUTHENTICATED',
        payload.error?.message ?? '登录已过期',
      )
    }
    if (!response.ok) {
      throw new Error(payload.error?.message ?? '上传失败')
    }
    return payload.data
  },

  async reprocessResource(resourceId: string): Promise<AdminKnowledgeResource> {
    return requestWithKey<AdminKnowledgeResource>(
      `/admin/knowledge/resources/${resourceId}/reprocess`,
      'POST',
      {},
    )
  },

  async createChapter(bookId: string, input: CreateChapterInput) {
    return requestWithKey(`/admin/books/${bookId}/chapters`, 'POST', { ...input })
  },
  async patchChapter(chapterId: string, patch: PatchChapterInput) {
    return requestWithKey(`/admin/chapters/${chapterId}`, 'PATCH', { ...patch })
  },
  async createContentBlock(chapterId: string, input: CreateContentBlockInput) {
    return requestWithKey(`/admin/chapters/${chapterId}/content-blocks`, 'POST', { ...input })
  },
  async createKnowledgePoint(input: CreateKnowledgePointInput) {
    return apiRequest('/admin/knowledge-points', { method: 'POST', body: { ...input } })
  },
  async getAdminMe(): Promise<{ admin_id: string | null; user_id: string; display_name: string; role_level: string }> {
    return apiRequest('/me/admin')
  },
  async getTeacherRoles(): Promise<AdminTeacherRole[]> {
    const payload = await apiRequest<AdminTeacherRole[] | { items: AdminTeacherRole[] }>(
      '/admin/teacher-roles',
    )
    return Array.isArray(payload) ? payload : payload.items
  },
  async createTeacherRole(input: CreateTeacherRoleInput) {
    return requestWithKey('/admin/teacher-roles', 'POST', { ...input, is_enabled: true })
  },
  async patchTeacherRole(roleId: string, patch: PatchTeacherRoleInput) {
    return requestWithKey(`/admin/teacher-roles/${roleId}`, 'PATCH', { ...patch })
  },
}
// ---------- Phase 4：章节 / 内容块 / 知识点 / 教师风格管理 ----------

export interface CreateChapterInput {
  title: string
  /** Phase 4 验收：chapter_order 由后端独占生成，前端不传 */
  summary?: string
  estimated_minutes?: number
}

export interface PatchChapterInput {
  title?: string
  estimated_minutes?: number
  status?: 'DRAFT' | 'PUBLISHED' | 'ARCHIVED'
}

export interface CreateContentBlockInput {
  block_type: string
  content: Record<string, unknown>
  section_key?: string
  block_order: number
}

export interface CreateKnowledgePointInput {
  name: string
  slug: string
  description?: string
  topic?: string
}

export interface AdminTeacherRole {
  role_id: string
  name: string
  tone: string
  teaching_style: string
  enabled: boolean
  version: number
}

export interface CreateTeacherRoleInput {
  name: string
  tone: string
  teaching_style: string
  persona?: Record<string, unknown>
  is_enabled?: boolean
}

export interface PatchTeacherRoleInput {
  name?: string
  tone?: string
  teaching_style?: string
  is_enabled?: boolean
}

// Phase 4：管理端扩展方法（章节/内容块/知识点/教师风格）
