// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { AdminKnowledgeResource } from '@/entities/admin/types'

const mocks = vi.hoisted(() => ({
  getKnowledgeResources: vi.fn(),
  uploadKnowledgeResource: vi.fn(),
  reprocessResource: vi.fn(),
  showToast: vi.fn(),
}))

vi.mock('@/shared/api/admin-service', () => ({
  adminService: {
    getKnowledgeResources: mocks.getKnowledgeResources,
    uploadKnowledgeResource: mocks.uploadKnowledgeResource,
    reprocessResource: mocks.reprocessResource,
  },
}))

vi.mock('@/shared/api/http', () => ({
  ApiError: class ApiError extends Error {},
}))

vi.mock('@/features/feedback', () => ({
  useToastStore: (selector: (s: { showToast: () => void }) => unknown) => selector({ showToast: mocks.showToast }),
}))

import { AdminKnowledge } from './AdminKnowledge'

afterEach(() => {
  cleanup()
  vi.useRealTimers()
})

function resource(overrides: Partial<AdminKnowledgeResource> = {}): AdminKnowledgeResource {
  return {
    resource_id: 'res-1',
    source_name: '训练数据手册',
    source_url: 'https://example.com/doc',
    author: null,
    license: 'CC-BY-4.0',
    copyright_status: '示例资源',
    storage_key: 's3://bucket/x',
    file_type: 'MARKDOWN',
    status: 'READY',
    error: null,
    created_at: '2026-09-07T00:00:00Z',
    ...overrides,
  }
}

describe('AdminKnowledge（T21 资源处理闭环）', () => {
  it('上传成功提示"已上传，正在处理"并禁用按钮防连点', async () => {
    mocks.getKnowledgeResources.mockResolvedValue([])
    mocks.uploadKnowledgeResource.mockResolvedValue(resource({ status: 'UPLOADED' }))
    render(<AdminKnowledge />)
    const uploadBtn = await screen.findByText('上传') as HTMLButtonElement
    // 选文件
    const fileInput = screen.getByLabelText('选择文件') as HTMLInputElement
    fireEvent.change(fileInput, { target: { files: [new File(['a'], 'a.md')] } })
    fireEvent.click(uploadBtn)
    // 上传中 → 禁用 + 文案
    await waitFor(() => expect(uploadBtn.disabled).toBe(true))
    expect(mocks.showToast).toHaveBeenCalledWith('已上传，正在处理')
    expect(mocks.uploadKnowledgeResource).toHaveBeenCalledTimes(1)
  })

  it('轮询把 UPLOADED 追踪到 READY，无需手刷', async () => {
    vi.useFakeTimers()
    let status = 'UPLOADED'
    mocks.getKnowledgeResources.mockImplementation(async () => [
      resource({ status, created_at: new Date().toISOString() }),
    ])
    render(<AdminKnowledge />)
    // 冲刷初始 load() 微任务。
    await vi.advanceTimersByTimeAsync(0)
    expect(screen.getByText('已上传，正在处理')).toBeTruthy()
    expect(screen.getByText(/正在自动刷新处理状态/)).toBeTruthy()
    // 处理完成 → 下一轮轮询拉到 READY。
    status = 'READY'
    await vi.advanceTimersByTimeAsync(3100)
    await vi.advanceTimersByTimeAsync(0)
    expect(screen.getByText('已就绪')).toBeTruthy()
    expect(screen.queryByText(/正在自动刷新处理状态/)).toBeNull()
  })

  it('FAILED 显示失败原因并可重试（不循环提交）', async () => {
    mocks.getKnowledgeResources.mockResolvedValue([
      resource({ status: 'FAILED', error: '解析失败：文件格式不支持' }),
    ])
    render(<AdminKnowledge />)
    expect(await screen.findByText(/失败原因：解析失败/)).toBeTruthy()
    expect(screen.getByText('重新处理')).toBeTruthy()
  })

  it('重新处理显示"已加入处理队列"并提示', async () => {
    mocks.getKnowledgeResources.mockResolvedValue([
      resource({ status: 'FAILED', error: 'boom', created_at: new Date().toISOString() }),
    ])
    mocks.reprocessResource.mockResolvedValue(resource({ status: 'UPLOADED' }))
    render(<AdminKnowledge />)
    await screen.findByText('重新处理')
    fireEvent.click(screen.getByText('重新处理'))
    await waitFor(() => expect(mocks.showToast).toHaveBeenCalledWith('已加入处理队列'))
    expect(mocks.reprocessResource).toHaveBeenCalledTimes(1)
  })

  it('超过 2 分钟仍在处理显示提示，不假定失败', async () => {
    const t = new Date(Date.now() - 180_000).toISOString()
    mocks.getKnowledgeResources.mockResolvedValue([
      resource({ status: 'INDEXING', created_at: t }),
    ])
    render(<AdminKnowledge />)
    expect(await screen.findByText(/仍在处理中/)).toBeTruthy()
    expect(screen.queryByText(/假定失败|以为失败/)).toBeNull()
  })
})
