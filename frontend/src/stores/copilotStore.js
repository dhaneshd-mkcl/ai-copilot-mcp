/**
 * copilotStore.js — backward-compatible façade.
 *
 * Imports from the split stores (chatStore, repoStore, toolStore) and
 * re-exports a unified API so existing components continue to work.
 *
 * New components should import directly from stores/*.
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { streamRequest, api } from '../services/api.js'
import { useChatStore } from '../stores/chatStore.js'
import { useRepoStore } from '../stores/repoStore.js'
import { useToolStore } from '../stores/toolStore.js'

export const useCopilotStore = defineStore('copilot', () => {
  const isConnected = ref(false)
  const activeTab = ref('chat')
  const currentCode = ref('')
  const currentLanguage = ref('python')

  // Lazily proxy to sub-stores so pinia is already initialized
  const chat = () => useChatStore()
  const repo = () => useRepoStore()
  const tools = () => useToolStore()

  // ── Computed shims ──────────────────────────────────────────────
  const messages = computed(() => chat().messages)
  const isStreaming = computed(() => chat().isStreaming)
  const error = computed(() => chat().error)
  const chatHistory = computed(() => chat().chatHistory)
  const repoFiles = computed(() => repo().files)
  const toolOutput = computed(() => tools().toolOutput)

  const toolList = computed(() => tools().tools)
  // alias for template code that uses `store.tools`
  const toolsProxy = toolList

  // ── Action shims ─────────────────────────────────────────────────
  async function sendMessage(text, attachments = []) {
    return chat().sendMessage(text, attachments)
  }

  async function analyzeCurrentCode(task = 'analyze') {
    if (!currentCode.value.trim()) return
    const chatSt = chat()
    
    // Add messages to chat for visual feedback
    const userMsg = {
      role: 'user',
      content: `[${task.toUpperCase()}] for current file`,
      id: Date.now()
    }
    chatSt.messages.push(userMsg)
    
    const assistantMsg = {
      role: 'assistant',
      content: '',
      id: Date.now() + 1,
      streaming: true
    }
    chatSt.messages.push(assistantMsg)
    chatSt.isStreaming = true

    const step = chatSt.addTimelineStep('user_message', { message: `[${task.toUpperCase()}] on current buffer` })

    await streamRequest(
      '/api/code/analyze',
      { code: currentCode.value, language: currentLanguage.value, task },
      (chunk) => {
        if (typeof chunk === 'string') {
          assistantMsg.content += chunk
        } else if (chunk && chunk.type) {
          chatSt.handleStructuredEvent(chunk, step)
        }
      },
      () => { 
        assistantMsg.streaming = false
        chatSt.isStreaming = false 
      },
      (err) => { 
        assistantMsg.streaming = false
        chatSt.isStreaming = false
        chatSt.error = err 
        assistantMsg.content += `\n\n⚠️ Error: ${err}`
      }
    )
  }

  async function generateCode(prompt) {
    const attachments = []
    if (currentCode.value.trim()) {
      attachments.push({
        filename: 'context',
        type: 'text',
        content: currentCode.value
      })
    }
    // Add a custom property to the array (hacky but sendMessage can read it)
    attachments.language = currentLanguage.value
    return chat().sendMessage(`Generate: ${prompt}`, attachments)
  }

  async function loadTools() { return tools().loadTools() }

  async function runTool(toolName, parameters) {
    return tools().runTool(toolName, parameters)
  }

  async function loadRepoFiles(path = '.') { return repo().loadFiles(path) }

  async function checkConnection() {
    try {
      await api.health()
      isConnected.value = true
    } catch {
      isConnected.value = false
    }
  }

  function clearMessages() { chat().clearMessages() }

  function detectLanguage(filename) {
    if (!filename) return 'python'
    const ext = filename.split('.').pop().toLowerCase()
    const map = {
      'py': 'python',
      'js': 'javascript',
      'ts': 'typescript',
      'vue': 'javascript',
      'html': 'html',
      'css': 'css',
      'json': 'json',
      'sh': 'bash',
      'go': 'go',
      'rs': 'rust',
      'java': 'java',
      'c': 'c',
      'cpp': 'cpp',
      'cs': 'csharp'
    }
    return map[ext] || 'python'
  }

  function setCode(code, filename = null) {
    currentCode.value = code
    if (filename) {
      currentLanguage.value = detectLanguage(filename)
    }
  }

  return {
    // state
    isConnected, activeTab, currentCode, currentLanguage,
    // computed shims
    messages, isStreaming, error, chatHistory, repoFiles,
    toolOutput, tools: toolsProxy,
    // actions
    sendMessage, analyzeCurrentCode, generateCode, loadTools,
    runTool, loadRepoFiles, checkConnection, clearMessages, setCode,
  }
})
