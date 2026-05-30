<script setup lang="ts">
import { computed } from 'vue'
import type { PlanTask } from '@/types'

const props = defineProps<{
  tasks: PlanTask[]
}>()

const sorted = computed(() => {
  return [...props.tasks].sort((a, b) => a.priority - b.priority)
})

const statusConfig: Record<string, string> = {
  todo: 'muted',
  in_progress: 'accent',
  done: 'success',
  blocked: 'warm',
  failed: 'danger',
}
</script>

<template>
  <div class="tasks-panel">
    <div class="panel-header">
      <span class="text-eyebrow">Tasks</span>
      <span class="count-badge">{{ tasks.length }}</span>
    </div>

    <div v-if="tasks.length === 0" class="empty-state">
      <p>No tasks planned yet. Tasks appear after the planning phase.</p>
    </div>

    <div v-else class="tasks-list">
      <article
        v-for="task in sorted"
        :key="task.task_id"
        class="task-card animate-fade-in"
      >
        <div class="task-header">
          <h4 class="task-title">{{ task.title }}</h4>
          <span
            class="task-status"
            :class="`task-status--${statusConfig[task.status] ?? 'muted'}`"
          >
            {{ task.status.replace('_', ' ') }}
          </span>
        </div>
        <p class="task-desc">{{ task.description }}</p>
        <div class="task-meta">
          <span class="task-query text-mono">
            Search: {{ task.search_query }}
          </span>
          <span v-if="task.depends_on.length" class="task-deps text-mono">
            Depends on: {{ task.depends_on.length }}
          </span>
        </div>
      </article>
    </div>
  </div>
</template>

<style scoped>
.tasks-panel {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.count-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 24px;
  height: 24px;
  padding: 0 8px;
  border-radius: var(--radius-full);
  background: var(--accent-soft);
  color: var(--accent);
  font-size: 0.78rem;
  font-weight: 700;
  font-family: var(--font-mono);
}

.tasks-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.task-card {
  padding: var(--space-3) var(--space-4);
  background: var(--surface-strong);
  border: 1px solid var(--line);
  border-radius: var(--radius);
}

.task-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: var(--space-3);
}

.task-title {
  font-family: var(--font-body);
  font-size: 0.9rem;
  font-weight: 600;
  line-height: 1.35;
  color: var(--ink);
}

.task-status {
  flex-shrink: 0;
  font-size: 0.72rem;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: var(--radius-full);
  text-transform: capitalize;
}

.task-status--accent { background: var(--accent-soft); color: var(--accent); }
.task-status--success { background: var(--success-soft); color: var(--success); }
.task-status--warm { background: var(--warm-soft); color: var(--warm); }
.task-status--danger { background: var(--danger-soft); color: var(--danger); }
.task-status--muted { background: rgba(99, 93, 83, 0.1); color: var(--muted); }

.task-desc {
  font-size: 0.85rem;
  color: var(--ink-soft);
  margin-top: 6px;
  line-height: 1.45;
}

.task-meta {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3);
  margin-top: var(--space-2);
}

.task-query,
.task-deps {
  font-size: 0.75rem;
}

.empty-state {
  padding: var(--space-6) var(--space-4);
  text-align: center;
  color: var(--muted-soft);
  font-size: 0.9rem;
  border: 1px dashed var(--line-strong);
  border-radius: var(--radius);
}
</style>
