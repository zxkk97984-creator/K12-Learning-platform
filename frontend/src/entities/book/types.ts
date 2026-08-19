// 内容域类型（对齐 0-C Domain Model，字段按前端需要精简）

export type BookDifficulty = 'EASY' | 'MEDIUM' | 'HARD'
export type BookStatus = 'DRAFT' | 'PUBLISHED' | 'ARCHIVED'
export type BookTint = 1 | 2 | 3 | 4

export interface Book {
  book_id: string
  title: string
  cover_url: string | null
  description: string | null
  grade_min: number
  grade_max: number
  difficulty: BookDifficulty
  estimated_minutes: number
  author: string | null
  /** 后端 tags；seed 约定 tags[0]=主题、tags[1]=关键词 */
  tags: string[]
  /** 从 tags[1] 派生的关键词（搜索/展示用） */
  keywords: string
  /** 原型 num（展示编号 01~12）；后端 BookDTO 不返回，真实 API 数据中可能为空 */
  book_no?: string
  /** 原型 tint（封面视觉变体 1~4）；后端 BookDTO 不返回，真实 API 数据中可能为空 */
  tint?: BookTint
  status: BookStatus
  /** (derived) 章数 */
  chapter_count: number
  /** 来源（0-C：source_ids jsonb 引用） */
  source_ids: string[]
  license: string | null
  copyright_status: string | null
}

export interface Chapter {
  chapter_id: string
  book_id: string
  title: string
  chapter_order: number
  summary: string | null
  estimated_minutes: number | null
  status: BookStatus
  /** (derived) 当前学生是否完成 */
  is_completed?: boolean
}

export type ContentBlockType =
  | 'TITLE'
  | 'PARAGRAPH'
  | 'IMAGE'
  | 'FIGURE'
  | 'KNOWLEDGE_CARD'
  | 'EXAMPLE'
  | 'CALLOUT'
  | 'HIGHLIGHT'

export interface ContentBlock {
  block_id: string
  chapter_id: string
  block_type: ContentBlockType
  /** 按 block_type 校验（0-C）；原型 data-read-section 锚点见 section_key */
  content: Record<string, unknown>
  block_order: number
  /** 原型 data-read-section 锚点 */
  section_key: string | null
  knowledge_point_ids: string[]
}

export interface KnowledgePoint {
  knowledge_point_id: string
  name: string
  slug: string
  description: string | null
  topic: string | null
  parent_id: string | null
  status: 'ACTIVE' | 'ARCHIVED'
}

export type BookProgressStatus = 'NOT_STARTED' | 'READING' | 'COMPLETED'

export interface BookProgress {
  progress_id: string
  student_id: string
  book_id: string
  chapter_id: string | null
  block_id: string | null
  status: BookProgressStatus
  /** 阅读位置 0~100（0-C：位置指示器，非掌握度） */
  position_percent: number
  last_read_at: string | null
  started_at: string | null
  completed_at: string | null
  total_seconds: number
}

export interface ChapterDetail extends Chapter {
  content_blocks: ContentBlock[]
  knowledge_points: KnowledgePoint[]
}
