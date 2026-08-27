import { getToken } from './auth'
import { emitUnauthorized, ApiError  } from './http'

export interface ParsedSSEEvent {
  id: string | null
  event: string
  data: unknown
  rawData: string
}

export interface FetchSSEOptions {
  method?: string
  headers?: HeadersInit
  body?: BodyInit | null
  signal?: AbortSignal
  onEvent: (eventType: string, data: unknown, event: ParsedSSEEvent) => void | Promise<void>
  onError?: (error: unknown) => void | Promise<void>
}

function frameEnd(buffer: string): { index: number; length: number } | null {
  const lfIndex = buffer.indexOf('\n\n')
  const crlfIndex = buffer.indexOf('\r\n\r\n')
  if (lfIndex < 0 && crlfIndex < 0) return null
  if (lfIndex < 0) return { index: crlfIndex, length: 4 }
  if (crlfIndex < 0) return { index: lfIndex, length: 2 }
  return lfIndex < crlfIndex
    ? { index: lfIndex, length: 2 }
    : { index: crlfIndex, length: 4 }
}

/** Parse one complete SSE frame. Comment-only heartbeat frames return null. */
export function parseSSEFrame(frame: string): ParsedSSEEvent | null {
  const lines = frame.replace(/\r\n/g, '\n').replace(/\r/g, '\n').split('\n')
  let id: string | null = null
  let event = 'message'
  const dataLines: string[] = []

  for (const line of lines) {
    if (!line || line.startsWith(':')) continue
    const separator = line.indexOf(':')
    const field = separator < 0 ? line : line.slice(0, separator)
    let value = separator < 0 ? '' : line.slice(separator + 1)
    if (value.startsWith(' ')) value = value.slice(1)

    if (field === 'id') id = value
    else if (field === 'event') event = value || 'message'
    else if (field === 'data') dataLines.push(value)
  }

  if (dataLines.length === 0) return null
  const rawData = dataLines.join('\n')
  let data: unknown = rawData
  try {
    data = JSON.parse(rawData) as unknown
  } catch {
    // SSE permits plain-text data; JSON is only required by this API contract.
  }
  return { id, event, data, rawData }
}

function responseError(response: Response, payload: unknown): ApiError {
  const error = (payload as {
    error?: { code?: string; message?: string; details?: unknown }
  } | null)?.error
  return new ApiError(
    response.status,
    error?.code ?? 'HTTP_ERROR',
    error?.message ?? `HTTP ${response.status}`,
    error?.details,
  )
}

async function reportError(options: FetchSSEOptions, error: unknown): Promise<void> {
  if (!options.onError) return
  try {
    await options.onError(error)
  } catch {
    // The transport error remains the primary failure; callback errors must not hide it.
  }
}

/**
 * POST-compatible SSE transport. It owns UTF-8 incremental decoding and frame
 * boundaries; callers only receive parsed event payloads.
 */
export async function fetchSSE(url: string, options: FetchSSEOptions): Promise<void> {
  const providedHeaders = new Headers(options.headers)
  const headers: Record<string, string> = {}
  providedHeaders.forEach((value, key) => {
    headers[key] = value
  })
  if (!headers.accept) headers.accept = 'text/event-stream'
  if (options.body !== undefined && options.body !== null && !headers['content-type']) {
    headers['content-type'] = 'application/json'
  }
  const token = getToken()
  if (token && !headers.authorization) headers.authorization = `Bearer ${token}`

  let response: Response
  try {
    response = await fetch(url, {
      method: options.method ?? 'GET',
      headers,
      body: options.body,
      signal: options.signal,
    })
    if (response.status === 401) {
      emitUnauthorized()
    }
    if (!response.ok) {
      const payload: unknown = await response.json().catch(() => null)
      throw responseError(response, payload)
    }
    if (!response.body) throw new Error('SSE response has no readable body')

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    const dispatch = async (frame: string) => {
      const event = parseSSEFrame(frame)
      if (event) await options.onEvent(event.event, event.data, event)
    }

    try {
      while (true) {
        const result = await reader.read()
        buffer += decoder.decode(result.value, { stream: !result.done })
        let boundary = frameEnd(buffer)
        while (boundary) {
          const frame = buffer.slice(0, boundary.index)
          buffer = buffer.slice(boundary.index + boundary.length)
          await dispatch(frame)
          boundary = frameEnd(buffer)
        }
        if (result.done) break
      }
      buffer += decoder.decode()
      if (buffer) await dispatch(buffer)
    } finally {
      reader.releaseLock()
    }
  } catch (error) {
    await reportError(options, error)
    throw error
  }
}
