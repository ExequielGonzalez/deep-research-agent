<script setup lang="ts">
import { computed } from 'vue'
import type { EventLogEntry } from '@/types'

const props = defineProps<{
  events: EventLogEntry[]
}>()

const sorted = computed(() => {
  return [...props.events].reverse().slice(0, 40)
})

function label(event: EventLogEntry): string {
  switch (event.type) {
    case 'llm_stage_started': return 'LLM Stage'
    case 'llm_reasoning': return 'Thinking'
    case 'llm_output_preview': return 'Preview'
    case 'run_task_failed': return 'Error'
    default: return event.type
  }
}

function content(event: EventLogEntry): string {
  const d = event.data
  if (d?.content) return String(d.content)
  if (d?.message) return String(d.message)
  if (d?.stage) return `Stage: ${d.stage}`
  return JSON.stringify(d)
}
</script>

<template>
  <div class="live-feed-panel">
    <div class="text-eyebrow" style="margin-bottom: var(--space-3)">Live Feed</div>

    <div v-if="events.length === 0" class="empty-state animate-fade-in">
      <div class="empty-pulse" />
      <p>Waiting for LLM output...</p>
    </div>

    <div v-else class="feed-list">
      <article
        v-for="event in sorted"
        :key="event.id"
        class="feed-item animate-fade-in"
      >
        <div class="feed-header">
          <span
            class="feed-label"
            :class="{
              'feed-label--thinking': event.type === 'llm_reasoning',
              'feed-label--preview': event.type === 'llm_output_preview',
              'feed-label--stage': event.type === 'llm_stage_started',
              'feed-label--error': event.type === 'run_task_failed',
            }"
          >
            {{ label(event) }}
          </span>
          <span class="feed-time text-mono">
            {{ new Date(event.timestamp).toLocaleTimeString() }}
          </span>
        </div>
        <p class="feed-content">{{ content(event) }}</p>
      </article>
    </div>
  </div>
</template>

<style scoped>
.live-feed-panel {
  display: flex;
  flex-direction: column;
}

.feed-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.feed-item {
  padding: var(--space-3);
  background: var(--surface-strong);
  border: 1px solid var(--line);
  border-radius: var(--radius);
}

.feed-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: var(--space-2);
  margin-bottom: 6px;
}

.feed-label {
  font-size: 0.7rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  padding: 2px 8px;
  border-radius: var(--radius-full);
  background: var(--line);
  color: var(--muted);
}

.feed-label--thinking {
  background: var(--warm-soft);
  color: var(--warm);
}

.feed-label--preview {
  background: var(--accent-soft);
  color: var(--accent);
}

.feed-label--stage {
  background: var(--success-soft);
  color: var(--success);
}

.feed-label--error {
  background: var(--danger-soft);
  color: var(--danger);
}

.feed-time {
  font-size: 0.7rem;
}

.feed-content {
  font-size: 0.82rem;
  line-height: 1.45;
  color: var(--ink-soft);
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.empty-state {
  padding: var(--space-6) var(--space-4);
  text-align: center;
  color: var(--muted-soft);
  font-size: 0.9rem;
  border: 1px dashed var(--line-strong);
  border-radius: var(--radius);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-3);
}

.empty-pulse {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: var(--accent-soft);
  animation: pulse 2s ease-in-out infinite;
}
</style>
