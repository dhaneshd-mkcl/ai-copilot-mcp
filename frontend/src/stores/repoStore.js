import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { api } from '../services/api.js'

export const useRepoStore = defineStore('repo', () => {
  const files = ref([])
  const repoStats = ref(null)
  const searchResults = ref([])
  const isLoading = ref(false)
  const isAnalyzing = ref(false)
  const currentPath = ref('.')

  const topLanguage = computed(() => {
    if (!repoStats.value?.languages) return '—'
    const langs = Object.entries(repoStats.value.languages)
    if (!langs.length) return '—'
    return langs.sort((a, b) => b[1] - a[1])[0][0]
  })

  const hasFiles = computed(() => files.value.length > 0)

  async function loadFiles(path = '.') {
    isLoading.value = true
    currentPath.value = path
    try {
      const res = await api.listFiles(path)
      files.value = res.data.data?.result?.files || res.data.data?.files || []
    } catch (e) {
      console.error('repoStore.loadFiles:', e)
    } finally {
      isLoading.value = false
    }
  }

  async function readFile(path) {
    try {
      const res = await api.runTool('read_file', { path })
      const data = res.data.data
      return data?.result?.content || data?.content || ''
    } catch (e) {
      console.error('repoStore.readFile:', e)
      return null
    }
  }

  async function search(query, fileTypes = []) {
    if (!query.trim()) {
      searchResults.value = []
      return
    }
    try {
      const res = await api.searchRepo(query, fileTypes)
      const data = res.data.data
      searchResults.value = data?.result?.results || data?.results || []
    } catch (e) {
      console.error('repoStore.search:', e)
    }
  }

  function clearSearch() {
    searchResults.value = []
  }

  async function analyze() {
    isAnalyzing.value = true
    try {
      const res = await api.analyzeRepo()
      // Pydantic refactor: data.result contains the actual stats
      repoStats.value = res.data.data?.result || res.data.data
      return repoStats.value
    } catch (e) {
      console.error('repoStore.analyze:', e)
    } finally {
      isAnalyzing.value = false
    }
  }

  async function createDirectory(path) {
    try {
      const res = await api.runTool('create_directory', { path }, true)
      if (!res.data.error) await loadFiles(currentPath.value)
      return res.data
    } catch (e) {
      console.error('repoStore.createDirectory:', e)
      return { error: e.message }
    }
  }

  async function deleteItem(path, recursive = false) {
    try {
      const res = await api.runTool('delete_item', { path, recursive }, true)
      if (!res.data.error) await loadFiles(currentPath.value)
      return res.data
    } catch (e) {
      console.error('repoStore.deleteItem:', e)
      return { error: e.message }
    }
  }

  async function moveItem(source, destination) {
    try {
      const res = await api.runTool('move_item', { source, destination }, true)
      if (!res.data.error) await loadFiles(currentPath.value)
      return res.data
    } catch (e) {
      console.error('repoStore.moveItem:', e)
      return { error: e.message }
    }
  }

  return {
    files,
    repoStats,
    searchResults,
    isLoading,
    isAnalyzing,
    currentPath,
    topLanguage,
    hasFiles,
    loadFiles,
    readFile,
    search,
    clearSearch,
    analyze,
    createDirectory,
    deleteItem,
    moveItem,
  }
})
