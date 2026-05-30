<script setup lang="ts">
import type { RunStatus } from '@/types'

const props = defineProps<{
  status: RunStatus
}>()

const statusConfig: Record<RunStatus, { label: string; color: string }> = {
  created: { label: 'Created', color: 'accent' },
  running: { label: 'Running', color: 'accent' },
  interrupted: { label: 'Interrupted', color: 'warm' },
  completed: { label: 'Completed', color: 'success' },
  failed: { label: 'Failed', color: 'danger' },
  cancelled: { label: 'Cancelled', color: 'muted' },
}

const config = statusConfig[props.status] ?? statusConfig.created
</script>

<template>
  <span
    class="status-pill"
    :class="`status-${config.color}`"
    :aria-label="`Status: ${config.label}`"
  >
    <span class="status-dot" :class="config.color" />
    {{ config.label }}
  </span>
</template>

<style scoped>
.status-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 12px;
  border-radius: var(--radius-full);
  font-size: 0.78rem;
  font-weight: 600;
  font-family: var(--font-body);
  letter-spacing: 0.02em;
}

.status-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex-shrink: 0;
}

.status-accent {
  background: var(--accent-soft);
  color: var(--accent);
}
.status-accent .status-dot {
  background: var(--accent);
}

.status-success {
  background: var(--success-soft);
  color: var(--success);
}
.status-success .status-dot {
  background: var(--success);
}

.status-warm {
  background: var(--warm-soft);
  color: var(--warm);
}
.status-warm .status-dot {
  background: var(--warm);
}

.status-danger {
  background: var(--danger-soft);
  color: var(--danger);
}
.status-danger .status-dot {
  background: var(--danger);
}

.status-muted {
  background: rgba(99, 93, 83, 0.1);
  color: var(--muted);
}
.status-muted .status-dot {
  background: var(--muted);
}
</style>
