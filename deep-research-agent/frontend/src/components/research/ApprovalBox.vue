<script setup lang="ts">
import { computed, ref } from 'vue'
import type { HumanReviewRequest, HumanDecisionType, PlanTask } from '@/types'

const props = defineProps<{
  input: HumanReviewRequest
}>()

const emit = defineEmits<{
  (e: 'decision', decision: HumanDecisionType, summary: string): void
}>()

const summary = ref('')

const planTitle = computed(() => {
  return (props.input.context as Record<string, unknown>)?.title as string | undefined
})

const planSummary = computed(() => {
  return (props.input.context as Record<string, unknown>)?.plan_summary as string | undefined
})

const planTasks = computed(() => {
  return (props.input.context as Record<string, unknown>)?.tasks as PlanTask[] | undefined
})

const hasPlanContext = computed(() => {
  return !!(planTitle.value || planSummary.value || planTasks.value)
})

function submit(decision: HumanDecisionType) {
  emit('decision', decision, summary.value)
  summary.value = ''
}
</script>

<template>
  <div class="approval-box animate-fade-in" role="dialog" aria-label="Human review required">
    <div class="approval-header">
      <span class="text-eyebrow">Human-in-the-Loop</span>
      <span class="approval-kind">{{ input.review_kind.replace(/_/g, ' ') }}</span>
    </div>

    <p class="approval-prompt">{{ input.prompt }}</p>

    <!-- Plan preview for plan_approval -->
    <div v-if="hasPlanContext" class="plan-preview">
      <h3 v-if="planTitle" class="plan-title">{{ planTitle }}</h3>
      <p v-if="planSummary" class="plan-summary">{{ planSummary }}</p>

      <div v-if="planTasks && planTasks.length" class="plan-tasks">
        <div v-for="task in planTasks" :key="task.task_id" class="plan-task">
          <div class="plan-task-header">
            <span class="plan-task-title">{{ task.title }}</span>
            <span class="plan-task-priority" :class="`priority-${task.priority}`">
              {{ task.priority === 1 ? 'Critical' : task.priority === 2 ? 'High' : 'Normal' }}
            </span>
          </div>
          <p class="plan-task-desc">{{ task.description }}</p>
        </div>
      </div>
    </div>

    <div class="approval-input">
      <label for="approval-summary" class="visually-hidden">Add feedback or context</label>
      <textarea
        id="approval-summary"
        v-model="summary"
        class="approval-textarea"
        placeholder="Optional: add feedback or context for the agent..."
        rows="2"
      />
    </div>

    <div class="approval-actions">
      <button
        v-for="decision in input.allowed_decisions"
        :key="decision"
        class="btn"
        :class="{
          'btn-primary': decision === 'approve',
          'btn-secondary': decision === 'clarify' || decision === 'continue',
          'btn-danger': decision === 'stop',
        }"
        @click="submit(decision)"
      >
        {{ decision.charAt(0).toUpperCase() + decision.slice(1) }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.approval-box {
  padding: var(--space-4);
  background: linear-gradient(135deg, var(--accent-soft) 0%, var(--warm-soft) 100%);
  border: 1px solid var(--accent-medium);
  border-radius: var(--radius);
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.approval-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.approval-kind {
  font-size: 0.78rem;
  font-weight: 600;
  padding: 2px 10px;
  border-radius: var(--radius-full);
  background: var(--warm-soft);
  color: var(--warm);
  text-transform: capitalize;
}

.approval-prompt {
  font-size: 0.95rem;
  line-height: 1.55;
  color: var(--ink);
}

.approval-textarea {
  width: 100%;
  padding: var(--space-3);
  border: 1px solid var(--line-strong);
  border-radius: var(--radius-sm);
  background: var(--surface-strong);
  font-family: var(--font-body);
  font-size: 0.9rem;
  color: var(--ink);
  resize: vertical;
}

.approval-textarea:focus {
  outline: none;
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-soft);
}

.approval-actions {
  display: flex;
  gap: var(--space-2);
  flex-wrap: wrap;
}

.btn {
  padding: var(--space-2) var(--space-5);
  border: none;
  border-radius: var(--radius);
  font-family: var(--font-body);
  font-size: 0.85rem;
  font-weight: 600;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.btn-primary {
  background: linear-gradient(135deg, var(--accent) 0%, var(--accent-bright) 100%);
  color: white;
}

.btn-primary:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(13, 115, 102, 0.3);
}

.btn-secondary {
  background: var(--surface-strong);
  color: var(--ink);
  border: 1px solid var(--line-strong);
}

.btn-secondary:hover {
  border-color: var(--accent);
  color: var(--accent);
}

.btn-danger {
  background: var(--danger-soft);
  color: var(--danger);
  border: 1px solid var(--danger-medium);
}

.btn-danger:hover {
  background: var(--danger-medium);
}
.plan-preview {
  background: var(--surface-strong);
  border: 1px solid var(--line);
  border-radius: var(--radius-sm);
  padding: var(--space-4);
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.plan-title {
  font-size: 1.1rem;
  font-weight: 700;
  color: var(--ink);
  line-height: 1.3;
}

.plan-summary {
  font-size: 0.9rem;
  line-height: 1.55;
  color: var(--muted);
}

.plan-tasks {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.plan-task {
  background: rgba(255,255,255,0.6);
  border: 1px solid var(--line);
  border-radius: var(--radius-sm);
  padding: var(--space-3);
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.plan-task-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: var(--space-2);
}

.plan-task-title {
  font-weight: 600;
  font-size: 0.9rem;
  color: var(--ink);
  line-height: 1.3;
}

.plan-task-priority {
  font-size: 0.68rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  padding: 2px 8px;
  border-radius: var(--radius-full);
  white-space: nowrap;
  background: var(--line);
  color: var(--muted);
}

.plan-task-priority.priority-1 {
  background: var(--danger-soft);
  color: var(--danger);
}

.plan-task-priority.priority-2 {
  background: var(--warm-soft);
  color: var(--warm);
}

.plan-task-desc {
  font-size: 0.82rem;
  line-height: 1.5;
  color: var(--muted);
}
</style>
