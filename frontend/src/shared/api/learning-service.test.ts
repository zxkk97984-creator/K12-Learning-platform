import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError } from './http'
import { ApiLearningService } from './learning-service'

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response
}

describe('ApiLearningService', () => {
  let service: ApiLearningService
  let storedToken: string | null

  beforeEach(() => {
    storedToken = null
    vi.stubGlobal('window', { localStorage: { getItem: () => storedToken } })
    vi.stubGlobal('fetch', vi.fn())
    service = new ApiLearningService()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('creates and closes a learning session through the Learning API', async () => {
    const session = { session_id: 'session-1', status: 'ACTIVE' }
    const fetchMock = vi.mocked(fetch)
      .mockResolvedValueOnce(jsonResponse(201, { data: session, meta: {} }))
      .mockResolvedValueOnce(jsonResponse(200, { data: { ...session, status: 'ENDED' }, meta: {} }))

    await expect(
      service.createSession({
        book_id: 'book-1',
        chapter_id: 'chapter-3',
        entry_route: '/learn/book-1/chapter-3',
      }),
    ).resolves.toEqual(session)
    await expect(service.endSession('session-1')).resolves.toMatchObject({ status: 'ENDED' })
    expect(fetchMock.mock.calls).toEqual([
      [
        '/api/v1/learning-sessions',
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({
            book_id: 'book-1',
            chapter_id: 'chapter-3',
            entry_route: '/learn/book-1/chapter-3',
          }),
        }),
      ],
      [
        '/api/v1/learning-sessions/session-1',
        expect.objectContaining({
          method: 'PATCH',
          body: JSON.stringify({ status: 'ENDED' }),
        }),
      ],
    ])
  })

  it('appends learning events and persists reading progress', async () => {
    const event = { event_id: 'event-1', event_type: 'TEXT_SELECTED' }
    const progress = { progress_id: 'progress-1', position_percent: 62 }
    const fetchMock = vi.mocked(fetch)
      .mockResolvedValueOnce(jsonResponse(201, { data: event, meta: {} }))
      .mockResolvedValueOnce(jsonResponse(200, { data: progress, meta: {} }))

    await expect(
      service.createEvent({
        event_type: 'TEXT_SELECTED',
        occurred_at: '2026-08-19T08:00:00Z',
        book_id: 'book-1',
        chapter_id: 'chapter-3',
        payload: { selectedText: '训练数据' },
      }),
    ).resolves.toEqual(event)
    await expect(
      service.upsertProgress('book-1', {
        chapter_id: 'chapter-3',
        block_id: 'block-2',
        status: 'READING',
        position_percent: 62,
      }),
    ).resolves.toEqual(progress)
    expect(fetchMock.mock.calls.map(([url, init]) => [url, init?.method, init?.body])).toEqual([
      ['/api/v1/learning-events', 'POST', JSON.stringify({
        event_type: 'TEXT_SELECTED',
        occurred_at: '2026-08-19T08:00:00Z',
        book_id: 'book-1',
        chapter_id: 'chapter-3',
        payload: { selectedText: '训练数据' },
      })],
      ['/api/v1/me/progress/book-1', 'PUT', JSON.stringify({
        chapter_id: 'chapter-3',
        block_id: 'block-2',
        status: 'READING',
        position_percent: 62,
      })],
    ])
  })

  it('can end a session after the auth token was cleared by logout', async () => {
    storedToken = 'token-1'
    const session = { session_id: 'session-1', status: 'ACTIVE' }
    const fetchMock = vi.mocked(fetch)
      .mockResolvedValueOnce(jsonResponse(201, { data: session, meta: {} }))
      .mockResolvedValueOnce(jsonResponse(200, { data: { ...session, status: 'ENDED' }, meta: {} }))

    await service.createSession({ book_id: 'book-1', chapter_id: 'chapter-3' })
    storedToken = null
    await service.endSession('session-1')

    expect(fetchMock.mock.calls[1][1]).toEqual(expect.objectContaining({
      headers: {
        'Content-Type': 'application/json',
        Authorization: 'Bearer token-1',
      },
    }))
  })

  it('createSession posts the book, chapter, and entry route', async () => {
    const session = { session_id: 'session-2', status: 'ACTIVE' }
    const fetchMock = vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse(201, { data: session, meta: {} }),
    )

    await service.createSession({
      book_id: 'book-2',
      chapter_id: 'chapter-4',
      entry_route: '/reader/chapter-4',
    })

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/learning-sessions',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({
          book_id: 'book-2',
          chapter_id: 'chapter-4',
          entry_route: '/reader/chapter-4',
        }),
      }),
    )
  })

  it('endSession patches the session to ENDED', async () => {
    const fetchMock = vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse(200, { data: { session_id: 'session-2', status: 'ENDED' }, meta: {} }),
    )

    await service.endSession('session-2')

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/learning-sessions/session-2',
      expect.objectContaining({
        method: 'PATCH',
        body: JSON.stringify({ status: 'ENDED' }),
      }),
    )
  })

  it('createEvent posts the event payload to the append-only endpoint', async () => {
    const fetchMock = vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse(201, { data: { event_id: 'event-2' }, meta: {} }),
    )

    await service.createEvent({
      event_type: 'CHAPTER_STARTED',
      occurred_at: '2026-08-19T08:00:00Z',
      book_id: 'book-2',
      chapter_id: 'chapter-4',
      payload: { source: 'reader' },
    })

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/learning-events',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({
          event_type: 'CHAPTER_STARTED',
          occurred_at: '2026-08-19T08:00:00Z',
          book_id: 'book-2',
          chapter_id: 'chapter-4',
          payload: { source: 'reader' },
        }),
      }),
    )
  })

  it('upsertProgress puts the partial progress payload by book', async () => {
    const fetchMock = vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse(200, { data: { progress_id: 'progress-2' }, meta: {} }),
    )

    await service.upsertProgress('book-2', {
      chapter_id: 'chapter-4',
      block_id: 'block-3',
      status: 'READING',
      position_percent: 37,
    })

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/me/progress/book-2',
      expect.objectContaining({
        method: 'PUT',
        body: JSON.stringify({
          chapter_id: 'chapter-4',
          block_id: 'block-3',
          status: 'READING',
          position_percent: 37,
        }),
      }),
    )
  })

  it('createSession converts a 401 response into ApiError', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse(401, {
        error: { code: 'UNAUTHENTICATED', message: 'missing bearer token' },
      }),
    )

    const error = await service
      .createSession({ book_id: 'book-2', chapter_id: 'chapter-4' })
      .catch((value: unknown) => value)

    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({ status: 401, code: 'UNAUTHENTICATED' })
  })

  it('upsertProgress converts a 401 response into ApiError', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse(401, {
        error: { code: 'UNAUTHENTICATED', message: 'missing bearer token' },
      }),
    )

    const error = await service
      .upsertProgress('book-2', { position_percent: 37 })
      .catch((value: unknown) => value)

    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({ status: 401, code: 'UNAUTHENTICATED' })
  })
})
