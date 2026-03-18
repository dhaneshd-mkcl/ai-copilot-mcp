import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { api } from '../services/api.js'

export const useToolStore = defineStore('tools', () => {
  const tools = ref([])
  const toolOutput = ref([])
  const categories = ref({ safe: [], dangerous: [] })
  const isLoading = ref(false)
  const pendingConfirmation = ref(null) // { tool, params, resolve }

  const safeTools = computed(() =>
    tools.value.filter(t => t.category === 'safe')
  )

  const dangerousTools = computed(() =>
    tools.value.filter(t => t.category === 'dangerous')
  )

  async function loadTools() {
    isLoading.value = true
    try {
      const res = await api.listTools()
      const data = res.data.data
      tools.value = data?.tools || data || []
      categories.value = data?.categories || { safe: [], dangerous: [] }
    } catch (e) {
      console.error('toolStore.loadTools:', e)
    } finally {
      isLoading.value = false
    }
  }

  async function runTool(toolName, parameters, force = false) {
    const entry = {
      tool: toolName,
      params: parameters,
      timestamp: new Date().toISOString(),
      status: 'running',
      result: null,
      error: null,
    }
    toolOutput.value.unshift(entry)

    try {
      const res = await api.runTool(toolName, parameters, force)
      const result = res.data.data

      // Backend returned requires_confirmation
      if (result?.status === 'requires_confirmation') {
        entry.status = 'needs_confirmation'
        entry.message = result.message
        return result
      }

      entry.status = result?.status || 'success'
      entry.result = result?.result || result
      entry.diff = entry.result?.diff // Extract for UI visibility
      return result
    } catch (e) {
      entry.status = 'error'
      entry.error = e.message
      return { error: e.message }
    }
  }

  async function runToolForced(toolName, parameters) {
    return runTool(toolName, parameters, true)
  }

  function clearOutput() {
    toolOutput.value = []
  }

  return {
    tools,
    toolOutput,
    categories,
    isLoading,
    safeTools,
    dangerousTools,
    loadTools,
    runTool,
    runToolForced,
    clearOutput,
  }
})
