// ═══════════════════════════════════════════════════════════════════════════
// useApi — Composable wrapper around ApiService providing reactive state
// ═══════════════════════════════════════════════════════════════════════════

import { ref } from 'vue'
import { api, ApiError } from '@/services/api'

export function useApi() {
  const isError = ref(false)
  const errorMessage = ref('')
  const isLoading = ref(false)

  async function wrap<T>(fn: () => Promise<T>): Promise<T | null> {
    isLoading.value = true
    isError.value = false
    errorMessage.value = ''

    try {
      const result = await fn()
      return result
    } catch (err) {
      isError.value = true
      if (err instanceof ApiError) {
        errorMessage.value = err.message
      } else if (err instanceof Error) {
        errorMessage.value = err.message
      } else {
        errorMessage.value = 'An unexpected error occurred'
      }
      return null
    } finally {
      isLoading.value = false
    }
  }

  function clearError() {
    isError.value = false
    errorMessage.value = ''
  }

  return {
    api,
    isError,
    errorMessage,
    isLoading,
    wrap,
    clearError,
  }
}
