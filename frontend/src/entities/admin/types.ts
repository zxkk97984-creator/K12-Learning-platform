export interface AdminStats {
  books_total: number
  books_published: number
  chapters_total: number
  knowledge_points_total: number
  resources_total: number
  resources_ready: number
  resources_failed: number
  students_total: number
}

export interface AdminBook {
  book_id: string
  title: string
  description: string | null
  grade_min: number
  grade_max: number
  status: 'DRAFT' | 'PUBLISHED' | 'ARCHIVED'
  tags: string[]
  created_by: string | null
  created_at: string
}

export interface AdminKnowledgeResource {
  resource_id: string
  source_name: string
  source_url: string
  author: string | null
  license: string
  copyright_status: string
  storage_key: string
  file_type: string
  status: string
  error: string | null
  created_at: string
}
