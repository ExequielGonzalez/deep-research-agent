// ═══════════════════════════════════════════════════════════════════════════
// useSseConnection — Manages SSE lifecycle for a research run's event stream
// ═══════════════════════════════════════════════════════════════════════════

import { ref, readonly } from 'vue'
import type { SseEvent } from '@/types'
import { api } from '@/services/api'

export function useSseConnection() {
  const isConnecting = ref(false)
  const isConnected = ref(false)
  const error = ref<string | null>(null)

  let eventSource: EventSource | null = null
  let eventHandlers: Array<(event: SseEvent) => void> = []

  function onEvent(handler: (event: SseEvent) => void) {
    eventHandlers.push(handler)
    return () => {
      eventHandlers = eventHandlers.filter((h) => h !== handler)
    }
  }

  function connect(threadId: string) {
    disconnect()

    isConnecting.value = true
    isConnected.value = false
    error.value = null

    const url = api.buildEventsUrl(threadId)
    eventSource = new EventSource(url)

    eventSource.onopen = () => {
      isConnecting.value = false
      isConnected.value = true
    }

    eventSource.addEventListener('snapshot', (event: MessageEvent) => {
      try {
        const parsed: SseEvent = {
          type: 'snapshot',
          thread_id: threadId,
          data: JSON.parse(event.data),
        }
        eventHandlers.forEach((h) => h(parsed))
      } catch (err) {
        console.warn('SSE snapshot parse error:', err)
      }
    })

    eventSource.addEventListener('llm_stage_started', (event: MessageEvent) => {
      try {
        const payload = JSON.parse(event.data)
        const parsed: SseEvent = {
          type: 'llm_stage_started',
          thread_id: payload.thread_id || threadId,
          data: payload,
        }
        eventHandlers.forEach((h) => h(parsed))
      } catch (err) {
        console.warn('SSE llm_stage_started parse error:', err)
      }
    })

    eventSource.addEventListener('llm_reasoning', (event: MessageEvent) => {
      try {
        const payload = JSON.parse(event.data)
        const parsed: SseEvent = {
          type: 'llm_reasoning',
          thread_id: payload.thread_id || threadId,
          data: payload,
        }
        eventHandlers.forEach((h) => h(parsed))
      } catch (err) {
        console.warn('SSE llm_reasoning parse error:', err)
      }
    })

    eventSource.addEventListener(
      'llm_output_preview',
      (event: MessageEvent) => {
        try {
          const payload = JSON.parse(event.data)
          const parsed: SseEvent = {
            type: 'llm_output_preview',
            thread_id: payload.thread_id || threadId,
            data: payload,
          }
          eventHandlers.forEach((h) => h(parsed))
        } catch (err) {
          console.warn('SSE llm_output_preview parse error:', err)
        }
      },
    )

    eventSource.addEventListener('run_task_failed', (event: MessageEvent) => {
      try {
        const payload = JSON.parse(event.data)
        const parsed: SseEvent = {
          type: 'run_task_failed',
          thread_id: payload.thread_id || threadId,
          data: payload,
        }
        eventHandlers.forEach((h) => h(parsed))
      } catch (err) {
        console.warn('SSE run_task_failed parse error:', err)
      }
    })

    eventSource.addEventListener('stream_end', (event: MessageEvent) => {
      try {
        const payload = JSON.parse(event.data)
        const parsed: SseEvent = {
          type: 'stream_end',
          thread_id: payload.thread_id || threadId,
          data: payload,
        }
        eventHandlers.forEach((h) => h(parsed))
      } catch (err) {
        console.warn('SSE stream_end parse error:', err)
      }
      disconnect()
    })

    eventSource.onerror = () => {
      isConnected.value = false
      isConnecting.value = false
      error.value = 'SSE connection error'
    }
  }

  function disconnect() {
    if (eventSource) {
      eventSource.close()
      eventSource = null
    }
    isConnected.value = false
    isConnecting.value = false
  }

  return {
    isConnecting: readonly(isConnecting),
    isConnected: readonly(isConnected),
    error: readonly(error),
    connect,
    disconnect,
    onEvent,
  }
}
