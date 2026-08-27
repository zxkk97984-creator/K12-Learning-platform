// @vitest-environment jsdom
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import React from 'react'
import { fireEvent } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { AdminBooks } from './AdminBooks'
import { AdminKnowledge } from './AdminKnowledge'
import { AdminStyles } from './AdminStyles'
import { AdminChapters } from './AdminChapters'

const mocks = vi.hoisted(() => ({
  getBooks: vi.fn(),
  createBook: vi.fn(),
  patchBook: vi.fn(),
  getKnowledgeResources: vi.fn(),
  uploadKnowledgeResource: vi.fn(),
  reprocessResource: vi.fn(),
  getStats: vi.fn(),
  getTeacherRoles: vi.fn(),
  createTeacherRole: vi.fn(),
  patchTeacherRole: vi.fn(),
  createChapter: vi.fn(),
  patchChapter: vi.fn(),
  createContentBlock: vi.fn(),
  createKnowledgePoint: vi.fn(),
}))

vi.mock('@/shared/api/admin-service', () => ({
  adminService: {
    getBooks: mocks.getBooks,
    createBook: mocks.createBook,
    patchBook: mocks.patchBook,
    getKnowledgeResources: mocks.getKnowledgeResources,
    uploadKnowledgeResource: mocks.uploadKnowledgeResource,
    reprocessResource: mocks.reprocessResource,
    getStats: mocks.getStats,
    getTeacherRoles: mocks.getTeacherRoles,
    createTeacherRole: mocks.createTeacherRole,
    patchTeacherRole: mocks.patchTeacherRole,
    createChapter: mocks.createChapter,
    patchChapter: mocks.patchChapter,
    createContentBlock: mocks.createContentBlock,
    createKnowledgePoint: mocks.createKnowledgePoint,
  },
}))

vi.mock('@/features/feedback', () => ({
  useToastStore: (selector: (state: unknown) => unknown) =>
    selector({ showToast: vi.fn() }),
}))

const contentMocks = vi.hoisted(() => ({
  getBooks: vi.fn(),
  getChapters: vi.fn(),
  getChapter: vi.fn(),
}))

vi.mock('@/shared/services', () => ({
  contentService: contentMocks,
}))

describe('Admin pages', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.getBooks.mockResolvedValue([
      {
        book_id: 'book-1',
        title: '管理书',
        status: 'DRAFT',
        grade_min: 7,
        grade_max: 9,
        tags: ['AI'],
        created_by: null,
        created_at: '2026-08-19T00:00:00Z',
      },
    ])
    mocks.getKnowledgeResources.mockResolvedValue([
      {
        resource_id: 'resource-1',
        source_name: '知识资源',
        source_url: 'https://x',
        author: null,
        license: 'CC-BY-4.0',
        copyright_status: '测试',
        storage_key: 'k',
        file_type: 'MARKDOWN',
        status: 'READY',
        error: null,
        created_at: '2026-08-19T00:00:00Z',
      },
    ])
  })

  afterEach(() => cleanup())

  it('AdminBooks 渲染书籍列表与创建表单', async () => {
    render(React.createElement(AdminBooks))

    await waitFor(() => expect(screen.getByText('管理书')).toBeTruthy())
    expect(screen.getByLabelText('书名')).toBeTruthy()
    expect(screen.getByRole('button', { name: '发布' })).toBeTruthy()
  })

  it('AdminKnowledge 渲染资源与上传表单', async () => {
    render(React.createElement(AdminKnowledge))

    await waitFor(() => expect(screen.getByText('知识资源')).toBeTruthy())
    expect(screen.getByLabelText('选择文件')).toBeTruthy()
    expect(screen.getByLabelText('来源名称')).toBeTruthy()
    expect(screen.getByText('已就绪')).toBeTruthy()
  })
})

describe('Admin Phase 4 pages', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    contentMocks.getBooks.mockResolvedValue([
      { book_id: 'book-1', title: '管理书' },
    ])
    contentMocks.getChapters.mockResolvedValue([
      {
        chapter_id: 'ch-1',
        book_id: 'book-1',
        title: '第一章',
        chapter_order: 1,
        summary: '',
        estimated_minutes: 10,
        status: 'PUBLISHED',
      },
    ])
    contentMocks.getChapter.mockResolvedValue({
      chapter_id: 'ch-1',
      title: '第一章',
      chapter_order: 1,
      estimated_minutes: 10,
      knowledge_points: [],
      content_blocks: [],
    })
    mocks.getTeacherRoles.mockResolvedValue([
      {
        role_id: 'role-1',
        name: '温暖鼓励',
        tone: '温和',
        teaching_style: '启发式',
        enabled: true,
        version: 1,
      },
    ])
  })

  afterEach(() => cleanup())

  it('AdminStyles 展示真实风格列表并调用创建 API', async () => {
    render(React.createElement(AdminStyles))

    expect(await screen.findByText('温暖鼓励')).toBeTruthy()
    fireEvent.change(screen.getByLabelText('风格名称'), { target: { value: '幽默风趣' } })
    fireEvent.click(screen.getByRole('button', { name: '新增风格' }))

    await waitFor(() =>
      expect(mocks.createTeacherRole).toHaveBeenCalledWith({
        name: '幽默风趣',
        tone: '耐心鼓励',
        teaching_style: '温暖清晰',
      }),
    )
  })

  it('AdminChapters 创建章节携带自增 order，并调用内容块/知识点接口', async () => {
    render(React.createElement(AdminChapters))

    const select = await screen.findByTestId('admin-book-select')
    expect(select).toBeTruthy()

    // 等待章节列表加载完成（保证自增 order 基于已加载的 1 章）
    await screen.findByText(/第一章/)
    fireEvent.change(screen.getByLabelText('新章节标题'), { target: { value: '全新章节' } })
    fireEvent.click(screen.getByRole('button', { name: '创建章节' }))
    await waitFor(() => {
      expect(mocks.createChapter).toHaveBeenCalledTimes(1)
      const [calledBookId, payload] = mocks.createChapter.mock.calls[0]
      expect(calledBookId).toBe('book-1')
      expect(payload).toMatchObject({ title: '全新章节' })
      // 后端独占生成 max+1：前端不得携带 chapter_order
      expect(payload).not.toHaveProperty('chapter_order')
    })

    // 选择章节后可添加段落块
    fireEvent.click(await screen.findByText(/第一章/))
    // 等待详情（含内容块表单）异步加载完成
    await waitFor(() => expect(screen.getByText(/内容块 · 第一章/)).toBeTruthy())
    fireEvent.change(await screen.findByLabelText('新段落文本'), { target: { value: '新的段落内容' } })
    fireEvent.click(screen.getByRole('button', { name: '追加段落块' }))
    await waitFor(() =>
      expect(mocks.createContentBlock).toHaveBeenCalledWith(
        'ch-1',
        expect.objectContaining({ block_type: 'PARAGRAPH', block_order: 1 }),
      ),
    )

    fireEvent.change(screen.getByLabelText('知识点名称'), { target: { value: '规律' } })
    fireEvent.change(screen.getByLabelText('知识点 slug'), { target: { value: 'pattern' } })
    fireEvent.click(screen.getByRole('button', { name: '创建知识点' }))
    await waitFor(() =>
      expect(mocks.createKnowledgePoint).toHaveBeenCalledWith({
        name: '规律',
        slug: 'pattern',
      }),
    )
  })
})
