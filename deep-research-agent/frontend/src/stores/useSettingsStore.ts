// ═══════════════════════════════════════════════════════════════════════════
// useSettingsStore — Settings and configuration state
// ═══════════════════════════════════════════════════════════════════════════

import { ref } from 'vue'
import { defineStore } from 'pinia'
import type { AgentSettings, AppConfig, SaveSettingsRequest } from '@/types'
import { api, ApiError } from '@/services/api'

export const useSettingsStore = defineStore('settings', () => {
  // ── State ──────────────────────────────────────────────────────────

  const settings = ref<AgentSettings | null>(null)
  const appConfig = ref<AppConfig | null>(null)
  const models = ref<string[]>([])
  const modelsBaseUrl = ref('')
  const isLoading = ref(false)
  const isSaving = ref(false)
  const isRefreshingSearxng = ref(false)
  const isFetchingModels = ref(false)
  const error = ref<string | null>(null)
  const savedSuccessfully = ref(false)

  // ── Actions ────────────────────────────────────────────────────────

  async function fetchSettings() {
    isLoading.value = true
    error.value = null
    try {
      const data = await api.getSettings()
      settings.value = data
    } catch (err) {
      error.value =
        err instanceof ApiError ? err.message : 'Failed to load settings'
    } finally {
      isLoading.value = false
    }
  }

  async function saveSettings(data: SaveSettingsRequest) {
    isSaving.value = true
    error.value = null
    savedSuccessfully.value = false
    try {
      await api.saveSettings(data)
      settings.value = await api.getSettings()
      savedSuccessfully.value = true
      setTimeout(() => {
        savedSuccessfully.value = false
      }, 2000)
    } catch (err) {
      error.value =
        err instanceof ApiError ? err.message : 'Failed to save settings'
    } finally {
      isSaving.value = false
    }
  }

  async function fetchConfig() {
    try {
      const data = await api.getConfig()
      appConfig.value = data
    } catch {
      // config is non-critical
    }
  }

  async function fetchModels() {
    isFetchingModels.value = true
    try {
      const data = await api.getModels()
      models.value = data.models ?? []
      modelsBaseUrl.value = data.base_url ?? ''
    } catch {
      models.value = []
    } finally {
      isFetchingModels.value = false
    }
  }

  async function refreshSearxngPool() {
    isRefreshingSearxng.value = true
    error.value = null
    try {
      await api.refreshSearxngPool()
      settings.value = await api.getSettings()
    } catch (err) {
      error.value =
        err instanceof ApiError ? err.message : 'Failed to refresh the SearXNG instance pool'
    } finally {
      isRefreshingSearxng.value = false
    }
  }

  return {
    // State
    settings,
    appConfig,
    models,
    modelsBaseUrl,
    isLoading,
    isSaving,
    isRefreshingSearxng,
    isFetchingModels,
    error,
    savedSuccessfully,
    // Actions
    fetchSettings,
    saveSettings,
    fetchConfig,
    fetchModels,
    refreshSearxngPool,
  }
})
