// ═══════════════════════════════════════════════════════════════════════════
// API Service Layer — Wraps all backend endpoints
// ═══════════════════════════════════════════════════════════════════════════

import type {
  AppConfig,
  AgentSettings,
  ResearchRun,
  RefreshSearxngPoolResponse,
  RunListItem,
  CreateRunRequest,
  SubmitDecisionRequest,
  SaveSettingsRequest,
} from '@/types'

class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

async function request<T>(
  url: string,
  options: RequestInit = {},
): Promise<T> {
  const res = await fetch(url, {
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
    ...options,
  })

  if (!res.ok) {
    const text = await res.text().catch(() => 'Unknown error')
    throw new ApiError(res.status, text || `HTTP ${res.status}`)
  }

  if (res.status === 204) {
    return undefined as T
  }

  return res.json()
}

async function requestText(url: string): Promise<string> {
  const res = await fetch(url)
  if (!res.ok) {
    throw new ApiError(res.status, `HTTP ${res.status}`)
  }
  return res.text()
}

export const api = {
  // ── Health ───────────────────────────────────────────────────────────

  health(): Promise<{ status: string }> {
    return request('/api/health')
  },

  // ── Config ───────────────────────────────────────────────────────────

  getConfig(): Promise<AppConfig> {
    return request('/api/config')
  },

  // ── Settings ─────────────────────────────────────────────────────────

  getSettings(): Promise<AgentSettings> {
    return request('/api/settings')
  },

  saveSettings(data: SaveSettingsRequest): Promise<{ status: string }> {
    return request('/api/settings', {
      method: 'POST',
      body: JSON.stringify(data),
    })
  },

  refreshSearxngPool(): Promise<RefreshSearxngPoolResponse> {
    return request('/api/settings/searxng/refresh', {
      method: 'POST',
    })
  },

  // ── Models ───────────────────────────────────────────────────────────

  getModels(): Promise<{ base_url: string; models: string[] }> {
    return request('/api/models')
  },

  // ── Runs ─────────────────────────────────────────────────────────────

  listRuns(limit = 20): Promise<{ runs: RunListItem[] }> {
    return request(`/api/runs?limit=${limit}`)
  },

  getRun(threadId: string): Promise<ResearchRun> {
    return request(`/api/runs/${encodeURIComponent(threadId)}`)
  },

  createRun(payload: CreateRunRequest): Promise<ResearchRun> {
    return request('/api/runs', {
      method: 'POST',
      body: JSON.stringify(payload),
    })
  },

  submitDecision(
    threadId: string,
    payload: SubmitDecisionRequest,
  ): Promise<ResearchRun> {
    return request(`/api/runs/${encodeURIComponent(threadId)}/decisions`, {
      method: 'POST',
      body: JSON.stringify(payload),
    })
  },

  getReportMarkdown(threadId: string): Promise<string> {
    return requestText(
      `/api/runs/${encodeURIComponent(threadId)}/report.md`,
    )
  },

  // ── SSE ──────────────────────────────────────────────────────────────

  buildEventsUrl(threadId: string, history = 25): string {
    return `/api/runs/${encodeURIComponent(threadId)}/events?history=${history}&follow=true`
  },
}

export { ApiError }
