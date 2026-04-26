export type Stage = 'quick' | 'standard' | 'full'

export interface GeneratePayload {
  industry: string
  count: number
  stage: Stage
}

export interface HistoryItem {
  session_id: string
  industry: string
  scenario: string
  stage: Stage
  status: string
  requested_count: number
  record_count: number
  quality_score: number | null
  trace_thread_id: string | null
  error_message: string | null
  started_at: string | null
  completed_at: string | null
  created_at: string
  updated_at: string | null
}

const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://127.0.0.1:8000/api/v1/traffic'
const LANGSMITH_PROJECT_URL = import.meta.env.VITE_LANGSMITH_PROJECT_URL ?? ''

export async function generateTraffic(payload: GeneratePayload) {
  const res = await fetch(`${API_BASE}/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    throw new Error(await res.text())
  }
  return res.json()
}

export async function listHistory(page = 1, pageSize = 20) {
  const res = await fetch(`${API_BASE}/history?page=${page}&page_size=${pageSize}`)
  if (!res.ok) {
    throw new Error(await res.text())
  }
  return res.json() as Promise<{
    total: number
    page: number
    page_size: number
    total_pages: number
    items: HistoryItem[]
  }>
}

export async function deleteHistory(sessionId: string) {
  const res = await fetch(`${API_BASE}/history/${sessionId}`, { method: 'DELETE' })
  if (!res.ok) {
    throw new Error(await res.text())
  }
  return res.json()
}

export async function cancelGenerate(sessionId: string) {
  const res = await fetch(`${API_BASE}/generate/${sessionId}`, { method: 'DELETE' })
  if (!res.ok) {
    throw new Error(await res.text())
  }
  return res.json()
}

export type StageProgress = {
  stage: string
  name: string
}

export type StageComplete = {
  stage: string
  status: string
}

export type Finalize = {
  download_url: string
}

export type Complete = {
  success: boolean
}

export function generateTrafficStream(
  payload: GeneratePayload,
  onStart: (sessionId: string) => void,
  onStageStart: (progress: StageProgress) => void,
  onStageComplete: (progress: StageComplete) => void,
  onFinalize: (data: Finalize) => void,
  onComplete: (result: Complete) => void,
  onError: (error: string) => void,
  signal?: AbortSignal
) {
  fetch(`${API_BASE}/generate/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    signal,
  }).then(async (res) => {
    if (!res.ok) {
      throw new Error(await res.text())
    }
    const reader = res.body?.getReader()
    if (!reader) throw new Error('No response body')

    const decoder = new TextDecoder()
    let buffer = ''
    let currentEventType = ''

    const processLine = (line: string) => {
      if (line.startsWith('event:')) {
        currentEventType = line.slice(6).trim()
        return
      }
      if (line.startsWith('data:')) {
        const dataStr = line.slice(5).trim()
        if (!currentEventType || !dataStr) return
        try {
          const data = JSON.parse(dataStr)
          switch (currentEventType) {
            case 'start':
              onStart(data.session_id)
              break
            case 'stage_start':
              onStageStart(data)
              break
            case 'stage_complete':
              onStageComplete(data)
              break
            case 'finalize':
              onFinalize(data)
              break
            case 'complete':
              onComplete(data)
              break
            case 'cancelled':
              onError(data.message || '任务已取消')
              break
          }
        } catch {
          // ignore parse errors
        }
        currentEventType = ''
      }
    }

    const read = async () => {
      try {
        const { done, value } = await reader.read()
        if (done) {
          if (buffer) processLine(buffer)
          return
        }
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''
        for (const line of lines) {
          processLine(line)
        }
        read()
      } catch (e) {
        onError(String(e))
      }
    }
    read()
  }).catch((e) => {
    if (e instanceof DOMException && e.name === 'AbortError') {
      onError('任务已取消')
      return
    }
    onError(e.message || '请求失败')
  })
}

export function downloadUrl(sessionId: string) {
  return `${API_BASE}/download/${sessionId}`
}

export function langsmithTraceUrl(sessionId: string) {
  if (!LANGSMITH_PROJECT_URL) return ''
  const url = new URL(LANGSMITH_PROJECT_URL)
  url.searchParams.set('search', `metadata.session_id:${sessionId}`)
  return url.toString()
}
