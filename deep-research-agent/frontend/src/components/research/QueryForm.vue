<script setup lang="ts">
import { ref } from 'vue'
import type { CreateRunRequest } from '@/types'

const emit = defineEmits<{
  (e: 'submit', payload: CreateRunRequest): void
}>()

defineProps<{
  isCreating: boolean
  models: string[]
  error: string | null
}>()

const query = ref('')
const modelName = ref('')
const audience = ref('general')
const maxIterations = ref<number | undefined>(undefined)

function onSubmit() {
  if (!query.value.trim()) return
  emit('submit', {
    query: query.value.trim(),
    audience: audience.value || 'general',
    model_name: modelName.value || undefined,
    max_iterations: maxIterations.value || undefined,
    llm_request_timeout_seconds: 600,
  })
}
</script>

<template>
  <form class="query-form" @submit.prevent="onSubmit">
    <div class="query-input-group">
      <textarea
        v-model="query"
        class="query-input"
        placeholder="E.g.: Evaluate llama.cpp as a local OpenAI-compatible backend, including HTTP compatibility, performance, limitations, and deployment workflow."
        rows="4"
        required
        aria-label="Research query"
      />
    </div>

    <div class="query-options">
      <div class="option-field">
        <label for="model-select">Model</label>
        <select
          id="model-select"
          v-model="modelName"
          class="input-select"
        >
          <option value="">Default model (from settings)</option>
          <option
            v-for="m in models"
            :key="m"
            :value="m"
          >
            {{ m }}
          </option>
        </select>
      </div>
      <div class="option-field">
        <label for="max-iterations">Max Iterations</label>
        <input
          id="max-iterations"
          v-model.number="maxIterations"
          type="number"
          class="input-select"
          min="1"
          max="20"
          placeholder="Default"
        />
      </div>
      <div class="option-field">
        <label for="audience-select">Audience</label>
        <select
          id="audience-select"
          v-model="audience"
          class="input-select"
        >
          <option value="general">General</option>
          <option value="technical">Technical</option>
          <option value="executive">Executive</option>
          <option value="researcher">Researcher</option>
        </select>
      </div>
      <div class="option-action">
        <button
          type="submit"
          class="btn btn-primary"
          :disabled="isCreating || !query.trim()"
        >
          <svg
            v-if="isCreating"
            class="btn-spinner"
            viewBox="0 0 24 24"
            fill="none"
            aria-hidden="true"
          >
            <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="3" opacity="0.3" />
            <path d="M12 2a10 10 0 019.95 9" stroke="currentColor" stroke-width="3" stroke-linecap="round" />
          </svg>
          <svg v-else class="btn-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
            <path d="M5 12h14M12 5l7 7-7 7" />
          </svg>
          <span>{{ isCreating ? 'Starting...' : 'Start Research' }}</span>
        </button>
      </div>
    </div>

    <div v-if="error" class="query-error" role="alert">
      {{ error }}
    </div>
  </form>
</template>

<style scoped>
.query-form {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.query-input-group {
  position: relative;
}

.query-input {
  width: 100%;
  padding: var(--space-4);
  border: 1px solid var(--line-strong);
  border-radius: var(--radius);
  background: var(--surface-strong);
  font-family: var(--font-body);
  font-size: 0.95rem;
  line-height: 1.6;
  color: var(--ink);
  resize: vertical;
  min-height: 100px;
  transition: border-color var(--transition-fast), box-shadow var(--transition-fast);
}

.query-input:focus {
  outline: none;
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-soft);
}

.query-input::placeholder {
  color: var(--muted-soft);
}

.query-options {
  display: flex;
  gap: var(--space-3);
  align-items: flex-end;
  flex-wrap: wrap;
}

.option-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
  flex: 1;
  min-width: 140px;
}

.option-field label {
  font-size: 0.78rem;
  font-weight: 600;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.input-select {
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--line-strong);
  border-radius: var(--radius-sm);
  background: var(--surface-strong);
  font-family: var(--font-body);
  font-size: 0.9rem;
  color: var(--ink);
  cursor: pointer;
}

.input-select:focus {
  outline: none;
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-soft);
}

.option-action {
  flex-shrink: 0;
}

.btn {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-3) var(--space-6);
  border: none;
  border-radius: var(--radius);
  font-family: var(--font-body);
  font-size: 0.95rem;
  font-weight: 600;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.btn-primary {
  background: linear-gradient(135deg, var(--accent) 0%, var(--accent-bright) 100%);
  color: white;
  box-shadow: 0 4px 14px rgba(13, 115, 102, 0.25);
}

.btn-primary:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 6px 20px rgba(13, 115, 102, 0.35);
}

.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-icon {
  width: 18px;
  height: 18px;
}

.btn-spinner {
  width: 18px;
  height: 18px;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.query-error {
  padding: var(--space-3) var(--space-4);
  background: var(--danger-soft);
  border: 1px solid var(--danger-medium);
  border-radius: var(--radius-sm);
  color: var(--danger);
  font-size: 0.9rem;
  line-height: 1.5;
}

@media (max-width: 480px) {
  .query-options {
    flex-direction: column;
  }
  .option-field {
    min-width: 100%;
  }
}
</style>
