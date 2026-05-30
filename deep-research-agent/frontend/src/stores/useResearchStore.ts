// ═══════════════════════════════════════════════════════════════════════════
// useResearchStore — Central store for research runs and SSE events
// ═══════════════════════════════════════════════════════════════════════════

import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import type {
  RunStatus,
  SseEvent,
  SseSnapshotEvent,
  ResearchRun,
  RunListItem,
  EventLogEntry,
  HumanDecisionType,
  CreateRunRequest,
} from '@/types'
import { api, ApiError } from '@/services/api'

export const useResearchStore = defineStore('research', () => {
  // ── State ──────────────────────────────────────────────────────────

  const activeThreadId = ref<string | null>(null)
  const isConnecting = ref(false)
  const isConnected = ref(false)

  const latestRun = ref<ResearchRun | null>(null)
  const runsList = ref<RunListItem[]>([])
  const eventsByThread = ref<Record<string, EventLogEntry[]>>({})
  const isLoadingRuns = ref(false)
  const isCreatingRun = ref(false)
  const runError = ref<string | null>(null)

  // ── SSE Internals ──────────────────────────────────────────────────

  let eventSource: EventSource | null = null
  let eventIdCounter = 0

  // ── Getters ────────────────────────────────────────────────────────

  const activeRun = computed<ResearchRun | RunListItem | null>(() => {
    if (!activeThreadId.value) return latestRun.value
    return (
      runsList.value.find((r) => r.thread_id === activeThreadId.value) ?? null
    )
  })

  const activeEvents = computed(() => {
    return activeThreadId.value
      ? (eventsByThread.value[activeThreadId.value] ?? [])
      : []
  })

  const activeRunStatus = computed<RunStatus | undefined>(() => {
    return activeRun.value?.status
  })

  const isRunning = computed(() => {
    return activeRunStatus.value === 'running'
  })

  const isComplete = computed(() => {
    const status = activeRunStatus.value
    return (
      status === 'completed' ||
      status === 'failed' ||
      status === 'cancelled'
    )
  })

  const isInterrupted = computed(() => {
    return activeRunStatus.value === 'interrupted'
  })

  const hasFinalReport = computed(() => {
    if (!activeRun.value?.state) return false
    const state = activeRun.value.state as Record<string, unknown>
    return (
      activeRunStatus.value === 'completed' &&
      typeof state.final_report_markdown === 'string' &&
      state.final_report_markdown.trim().length > 0
    )
  })

  const pendingHumanInput = computed(() => {
    return activeRun.value?.pending_human_input ?? null
  })

  // ── Helpers ────────────────────────────────────────────────────────

  function ensureThreadEvents(threadId: string) {
    if (!eventsByThread.value[threadId]) {
      eventsByThread.value[threadId] = []
    }
  }

  function addEvent(threadId: string, event: SseEvent) {
    ensureThreadEvents(threadId)
    const entry: EventLogEntry = {
      id: `evt-${++eventIdCounter}-${Date.now()}`,
      type: event.type,
      thread_id: threadId,
      timestamp: new Date().toISOString(),
      data: event.data as Record<string, unknown>,
    }
    const events = eventsByThread.value[threadId]!
    events.push(entry)
    // Keep max 100 events per thread
    if (events.length > 100) {
      events.splice(0, events.length - 100)
    }
    return entry
  }

  function upsertRun(run: ResearchRun | RunListItem) {
    const idx = runsList.value.findIndex((r) => r.thread_id === run.thread_id)
    if (idx >= 0) {
      runsList.value[idx] = run
    } else {
      runsList.value.unshift(run)
    }
  }

  // ── SSE Connection ─────────────────────────────────────────────────

  function connectToSse(threadId: string) {
    if (isConnecting.value || isConnected.value) return
    disconnectSse()

    isConnecting.value = true
    runError.value = null
    activeThreadId.value = threadId
    ensureThreadEvents(threadId)

    const url = api.buildEventsUrl(threadId)
    eventSource = new EventSource(url)

    eventSource.onopen = () => {
      isConnected.value = true
      isConnecting.value = false
    }

    // Generic event listener for all SSE events
    eventSource.onmessage = (msg: MessageEvent) => {
      try {
        const parsed: SseEvent = JSON.parse(msg.data)
        handleSseEvent(parsed)
      } catch {
        // ignore
      }
    }

    // Named event listeners
    eventSource.addEventListener('snapshot', (msg: MessageEvent) => {
      try {
        const data = JSON.parse(msg.data)
        const parsed: SseEvent = {
          type: 'snapshot',
          thread_id: data.thread_id ?? threadId,
          data,
        }
        handleSseEvent(parsed)
      } catch {
        // ignore
      }
    })

    eventSource.addEventListener('llm_stage_started', (msg: MessageEvent) => {
      try {
        const data = JSON.parse(msg.data)
        handleSseEvent({
          type: 'llm_stage_started',
          thread_id: data.thread_id ?? threadId,
          data,
        })
      } catch {
        // ignore
      }
    })

    eventSource.addEventListener('llm_reasoning', (msg: MessageEvent) => {
      try {
        const data = JSON.parse(msg.data)
        handleSseEvent({
          type: 'llm_reasoning',
          thread_id: data.thread_id ?? threadId,
          data,
        })
      } catch {
        // ignore
      }
    })

    eventSource.addEventListener('llm_output_preview', (msg: MessageEvent) => {
      try {
        const data = JSON.parse(msg.data)
        handleSseEvent({
          type: 'llm_output_preview',
          thread_id: data.thread_id ?? threadId,
          data,
        })
      } catch {
        // ignore
      }
    })

    eventSource.addEventListener('run_task_failed', (msg: MessageEvent) => {
      try {
        const data = JSON.parse(msg.data)
        handleSseEvent({
          type: 'run_task_failed',
          thread_id: data.thread_id ?? threadId,
          data,
        })
      } catch {
        // ignore
      }
    })

    eventSource.addEventListener('stream_end', (msg: MessageEvent) => {
      try {
        const data = JSON.parse(msg.data)
        handleSseEvent({
          type: 'stream_end',
          thread_id: data.thread_id ?? threadId,
          data,
        })
      } catch {
        // ignore
      }
      disconnectSse()
    })

    eventSource.onerror = () => {
      isConnected.value = false
      isConnecting.value = false
    }
  }

  function disconnectSse() {
    if (eventSource) {
      eventSource.close()
      eventSource = null
    }
    isConnected.value = false
    isConnecting.value = false
    activeThreadId.value = null
  }

  // ── Event Handler ──────────────────────────────────────────────────

  function handleSseEvent(event: SseEvent) {
    switch (event.type) {
      case 'snapshot': {
        addEvent(event.thread_id, event)
        const snapData = (event as SseSnapshotEvent).data
        const state = snapData.state ?? {}
        const run = {
          thread_id: (state.thread_id as string) ?? event.thread_id,
          query: (state.query as string) ?? '',
          status: (state.status as RunStatus) ?? 'created',
          created_at: (state.created_at as string) ?? '',
          updated_at: new Date().toISOString(),
          is_running: (state.status as string) === 'running',
          runtime_config: snapData.config as Record<string, unknown>,
          state: state,
          pending_human_input:
            Array.isArray(snapData.interrupt) && snapData.interrupt.length > 0
              ? snapData.interrupt[0]
              : null,
        } as ResearchRun
        latestRun.value = run
        upsertRun(run)
        break
      }

      case 'llm_stage_started':
      case 'llm_reasoning':
      case 'llm_output_preview':
      case 'run_task_failed':
      case 'stream_end': {
        addEvent(event.thread_id, event)
        break
      }
    }
  }

  // ── API Actions ────────────────────────────────────────────────────

  async function fetchRuns(limit = 50) {
    isLoadingRuns.value = true
    runError.value = null
    try {
      const data = await api.listRuns(limit)
      runsList.value = data.runs ?? []
    } catch (err) {
      runError.value =
        err instanceof ApiError ? err.message : 'Failed to fetch runs'
    } finally {
      isLoadingRuns.value = false
    }
  }

  async function fetchRun(threadId: string) {
    runError.value = null
    try {
      const run = await api.getRun(threadId)
      latestRun.value = run
      upsertRun(run)
      return run
    } catch (err) {
      runError.value =
        err instanceof ApiError ? err.message : 'Failed to fetch run'
      return null
    }
  }

  async function createRun(payload: CreateRunRequest) {
    isCreatingRun.value = true
    runError.value = null
    try {
      const run = await api.createRun(payload)
      upsertRun(run)
      connectToSse(run.thread_id)
      return run
    } catch (err) {
      runError.value =
        err instanceof ApiError ? err.message : 'Failed to create run'
      return null
    } finally {
      isCreatingRun.value = false
    }
  }

  async function submitDecision(
    threadId: string,
    decision: HumanDecisionType,
    summary = '',
  ) {
    runError.value = null
    try {
      return await api.submitDecision(threadId, { decision, summary })
    } catch (err) {
      runError.value =
        err instanceof ApiError ? err.message : 'Failed to submit decision'
      return null
    }
  }

  function selectRun(threadId: string) {
    activeThreadId.value = threadId
    const run = runsList.value.find((r) => r.thread_id === threadId)
    if (run) {
      latestRun.value = run as ResearchRun
    }
  }

  return {
    // State
    activeThreadId,
    isConnecting,
    isConnected,
    latestRun,
    runsList,
    eventsByThread,
    isLoadingRuns,
    isCreatingRun,
    runError,
    // Getters
    activeRun,
    activeEvents,
    activeRunStatus,
    isRunning,
    isComplete,
    isInterrupted,
    hasFinalReport,
    pendingHumanInput,
    // Actions
    connectToSse,
    disconnectSse,
    handleSseEvent,
    fetchRuns,
    fetchRun,
    createRun,
    submitDecision,
    selectRun,
  }
})
