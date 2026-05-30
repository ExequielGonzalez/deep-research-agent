<script setup lang="ts">
import { ref } from 'vue'
import type { HumanReviewRequest, HumanDecisionType } from '@/types'

defineProps<{
  input: HumanReviewRequest
}>()

const emit = defineEmits<{
  (e: 'decision', decision: HumanDecisionType, summary: string): void
}>()

const summary = ref('')

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
</style>
