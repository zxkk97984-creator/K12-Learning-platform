// @vitest-environment jsdom
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import React from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { AdminBooks } from './AdminBooks'
import { AdminKnowledge } from './AdminKnowledge'

const mocks = vi.hoisted(() => ({
  getBooks: vi.fn(),
  createBook: vi.fn(),
  patchBook: vi.fn(),
  getKnowledgeResources: vi.fn(),
  uploadKnowledgeResource: vi.fn(),
  reprocessResource: vi.fn(),
  getStats: vi.fn(),
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
  },
}))

vi.mock('@/features/feedback', () => ({
  useToastStore: (selector: (state: unknown) => unknown) =>
    selector({ showToast: vi.fn() }),
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
