<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useSettingsStore } from '@/stores/useSettingsStore'

const settingsStore = useSettingsStore()

// Form state
const form = ref({
  openai_api_key: '',
  openai_base_url: '',
  ollama_base_url: '',
  default_search_provider: 'none',
  tavily_api_key: '',
  serper_api_key: '',
  max_iterations: 6,
  max_sources_per_task: 8,
  total_token_budget: 120000,
  max_notes: 200,
})

onMounted(async () => {
  await settingsStore.fetchSettings()
  if (settingsStore.settings) {
    Object.assign(form.value, settingsStore.settings)
  }
})

async function saveSettings() {
  await settingsStore.saveSettings(form.value)
}

async function loadSettings() {
  await settingsStore.fetchSettings()
  if (settingsStore.settings) {
    Object.assign(form.value, settingsStore.settings)
  }
}

function isModified(): boolean {
  if (!settingsStore.settings) return false
  return (
    form.value.openai_api_key !== settingsStore.settings.openai_api_key ||
    form.value.openai_base_url !== settingsStore.settings.openai_base_url ||
    form.value.ollama_base_url !== settingsStore.settings.ollama_base_url ||
    form.value.default_search_provider !== settingsStore.settings.default_search_provider ||
    form.value.max_iterations !== settingsStore.settings.max_iterations ||
    form.value.max_sources_per_task !== settingsStore.settings.max_sources_per_task ||
    form.value.total_token_budget !== settingsStore.settings.total_token_budget ||
    form.value.max_notes !== settingsStore.settings.max_notes
  )
}
</script>

<template>
  <div class="settings-view">
    <div class="settings-header">
      <div>
        <h2>Settings</h2>
        <p class="settings-desc">
          Configure your LLM providers, search backends, and execution parameters.
        </p>
      </div>
      <div class="settings-actions">
        <button
          class="btn btn-secondary"
          :disabled="settingsStore.isLoading"
          @click="loadSettings"
        >
          Load from Server
        </button>
        <button
          class="btn btn-primary"
          :disabled="settingsStore.isSaving || !isModified()"
          @click="saveSettings"
        >
          <span v-if="settingsStore.isSaving">Saving...</span>
          <span v-else>Save Settings</span>
        </button>
      </div>
    </div>

    <div v-if="settingsStore.error" class="settings-error" role="alert">
      {{ settingsStore.error }}
    </div>

    <div v-if="settingsStore.savedSuccessfully" class="settings-saved">
      Settings saved successfully!
    </div>

    <div class="settings-grid">
      <!-- LLM Provider: OpenAI -->
      <section class="settings-card">
        <div class="card-header">
          <div class="provider-icon openai">O</div>
          <div>
            <h3>OpenAI / OpenAI-Compatible</h3>
            <p class="card-desc">For OpenAI API or compatible endpoints (vLLM, llama.cpp, etc.)</p>
          </div>
        </div>
        <div class="card-body">
          <div class="field">
            <label for="openai-key">API Key</label>
            <input
              id="openai-key"
              v-model="form.openai_api_key"
              type="password"
              placeholder="sk-..."
            />
          </div>
          <div class="field">
            <label for="openai-url">Base URL</label>
            <input
              id="openai-url"
              v-model="form.openai_base_url"
              type="url"
              placeholder="https://api.openai.com/v1"
            />
          </div>
        </div>
      </section>

      <!-- LLM Provider: Ollama -->
      <section class="settings-card">
        <div class="card-header">
          <div class="provider-icon ollama">O</div>
          <div>
            <h3>Ollama (Local)</h3>
            <p class="card-desc">Run models locally with Ollama</p>
          </div>
        </div>
        <div class="card-body">
          <div class="field">
            <label for="ollama-url">Base URL</label>
            <input
              id="ollama-url"
              v-model="form.ollama_base_url"
              type="url"
              placeholder="http://host.docker.internal:11434"
            />
          </div>
        </div>
      </section>

      <!-- Search Provider -->
      <section class="settings-card">
        <div class="card-header">
          <div class="provider-icon search">S</div>
          <div>
            <h3>Search Provider</h3>
            <p class="card-desc">Backend for web search capabilities</p>
          </div>
        </div>
        <div class="card-body">
          <div class="field">
            <label for="search-provider">Provider</label>
            <select id="search-provider" v-model="form.default_search_provider">
              <option value="none">DuckDuckGo (Free, default)</option>
              <option value="tavily">Tavily</option>
              <option value="serper">Serper (Google)</option>
            </select>
          </div>
          <div v-if="form.default_search_provider === 'tavily'" class="field">
            <label for="tavily-key">Tavily API Key</label>
            <input
              id="tavily-key"
              v-model="form.tavily_api_key"
              type="password"
              placeholder="Enter your Tavily API key"
            />
          </div>
          <div v-else-if="form.default_search_provider === 'serper'" class="field">
            <label for="serper-key">Serper API Key</label>
            <input
              id="serper-key"
              v-model="form.serper_api_key"
              type="password"
              placeholder="Enter your Serper API key"
            />
          </div>
        </div>
      </section>

      <!-- Execution Parameters -->
      <section class="settings-card">
        <div class="card-header">
          <div class="provider-icon exec">E</div>
          <div>
            <h3>Execution Parameters</h3>
            <p class="card-desc">Control the research depth and resource limits</p>
          </div>
        </div>
        <div class="card-body">
          <div class="fields-grid">
            <div class="field">
              <label for="max-iterations">Max Iterations</label>
              <input
                id="max-iterations"
                v-model.number="form.max_iterations"
                type="number"
                min="1"
                max="20"
              />
            </div>
            <div class="field">
              <label for="max-sources">Max Sources per Task</label>
              <input
                id="max-sources"
                v-model.number="form.max_sources_per_task"
                type="number"
                min="1"
                max="20"
              />
            </div>
            <div class="field">
              <label for="token-budget">Token Budget (total)</label>
              <input
                id="token-budget"
                v-model.number="form.total_token_budget"
                type="number"
                min="1000"
                step="1000"
              />
            </div>
            <div class="field">
              <label for="max-notes">Max Notes</label>
              <input
                id="max-notes"
                v-model.number="form.max_notes"
                type="number"
                min="10"
                step="10"
              />
            </div>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.settings-view {
  display: flex;
  flex-direction: column;
  gap: var(--space-6);
  max-width: 800px;
  animation: fadeIn var(--transition-slow) forwards;
}

.settings-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: var(--space-4);
  flex-wrap: wrap;
}

.settings-header h2 {
  font-size: 1.6rem;
}

.settings-desc {
  color: var(--muted);
  font-size: 0.95rem;
  margin-top: 4px;
}

.settings-actions {
  display: flex;
  gap: var(--space-2);
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

.btn-primary:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(13, 115, 102, 0.3);
}

.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-secondary {
  background: var(--surface-strong);
  color: var(--ink);
  border: 1px solid var(--line-strong);
}

.btn-secondary:hover:not(:disabled) {
  border-color: var(--accent);
  color: var(--accent);
}

.btn-secondary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.settings-error {
  padding: var(--space-3) var(--space-4);
  background: var(--danger-soft);
  border: 1px solid var(--danger-medium);
  border-radius: var(--radius);
  color: var(--danger);
  font-size: 0.9rem;
}

.settings-saved {
  padding: var(--space-3) var(--space-4);
  background: var(--success-soft);
  border: 1px solid var(--success-medium);
  border-radius: var(--radius);
  color: var(--success);
  font-size: 0.9rem;
  font-weight: 600;
}

.settings-grid {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.settings-card {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--radius-lg);
  overflow: hidden;
}

.card-header {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-4) var(--space-5);
  border-bottom: 1px solid var(--line);
}

.provider-icon {
  width: 36px;
  height: 36px;
  border-radius: var(--radius);
  display: grid;
  place-items: center;
  font-size: 0.85rem;
  font-weight: 800;
  color: white;
  flex-shrink: 0;
}

.provider-icon.openai {
  background: linear-gradient(135deg, #10a37f, #1b8d77);
}

.provider-icon.ollama {
  background: linear-gradient(135deg, #6366f1, #8b5cf6);
}

.provider-icon.search {
  background: linear-gradient(135deg, #f59e0b, #d97706);
}

.provider-icon.exec {
  background: linear-gradient(135deg, #0d7366, #12a08c);
}

.card-header h3 {
  font-family: var(--font-body);
  font-size: 1rem;
  font-weight: 600;
}

.card-desc {
  font-size: 0.82rem;
  color: var(--muted);
  margin-top: 2px;
}

.card-body {
  padding: var(--space-5);
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.fields-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-4);
}

.field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.field label {
  font-size: 0.78rem;
  font-weight: 600;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.field input,
.field select {
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--line-strong);
  border-radius: var(--radius-sm);
  background: var(--surface-strong);
  font-family: var(--font-body);
  font-size: 0.9rem;
  color: var(--ink);
}

.field input:focus,
.field select:focus {
  outline: none;
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-soft);
}

@media (max-width: 600px) {
  .settings-header {
    flex-direction: column;
  }
  .fields-grid {
    grid-template-columns: 1fr;
  }
}
</style>
