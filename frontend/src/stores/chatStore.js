import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { streamRequest } from '../services/api.js'

export const useChatStore = defineStore('chat', () => {
  const messages = ref([])
  const isStreaming = ref(false)
  const error = ref(null)
  const sessionId = ref('default')

  // Tool execution timeline events
  const timelineEvents = ref([])

  const chatHistory = computed(() =>
    messages.value.map(m => ({ role: m.role, content: m.content }))
  )

  const abortController = ref(null)
  
  const baseUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000'
  
  function getStaticUrl(path) {
    if (!path) return null
    // If it's already a full URL or data URI, return as is
    if (path.startsWith('http') || path.startsWith('data:')) return path
    
    // Normalize path: replace backslashes and find relative part from workspace root
    // This is a bit heuristic since we don't know the exact absolute root here, 
    // but tools usually return paths containing 'data/screenshots' etc.
    const normalized = path.replace(/\\/g, '/')
    
    // If it's an absolute path on Windows (e.g. D:/...), we need to find 
    // the part relative to config.ALLOWED_BASE_PATH. 
    // For now, we'll assume the tool returns something we can map or we just take the last few parts.
    const parts = normalized.split('/')
    const dataIdx = parts.indexOf('data')
    const repoIdx = parts.indexOf('repo')
    const backupsIdx = parts.indexOf('backups')
    
    const startIdx = Math.max(dataIdx, repoIdx, backupsIdx)
    if (startIdx !== -1) {
      return `${baseUrl}/static/${parts.slice(startIdx).join('/')}`
    }
    
    return `${baseUrl}/static/${parts.pop()}` // Fallback to just the filename
  }
  
  async function sendMessage(text, attachments = [], isHidden = false) {
    if (!text.trim() && attachments.length === 0) return
    if (isStreaming.value) return

    // attachments: Array<{ fileName, fileType, dataUri, content }>
    const userMsg = {
      role: 'user',
      content: text,
      id: Date.now(),
      attachments: attachments,
      hidden: isHidden
    }
    messages.value.push(userMsg)
    
    const assistantMsg = {
      role: 'assistant',
      content: '',
      id: Date.now() + 1,
      streaming: true,
    }
    messages.value.push(assistantMsg)
    isStreaming.value = true
    error.value = null
    
    // Initialize controller for this request
    abortController.value = new AbortController()

    // Track new timeline step
    const step = addTimelineStep('user_message', { message: text })

    // Build structured context from attachments
    const contextCode = attachments
      .filter(a => a.type === 'text' || a.content)
      .map(a => `FILE: ${a.filename}\n\n${a.content || ''}`)
      .join('\n\n---\n\n')

    await streamRequest(
      '/api/chat',
      {
        message: text,
        session_id: sessionId.value,
        history: chatHistory.value.slice(0, -2),
        context_code: contextCode || null,
        language: attachments?.language || null // Custom property for language context
      },
      // onChunk: string delta or structured event object
      (chunk) => {
        if (typeof chunk === 'string') {
          assistantMsg.content += chunk
        } else if (chunk && chunk.type) {
          handleStructuredEvent(chunk, step)
        }
      },
      // onDone
      () => {
        assistantMsg.streaming = false
        isStreaming.value = false
        abortController.value = null
        finalizeTimelineStep(step, 'done')
      },
      // onError
      (err) => {
        if (err === 'The user aborted a request.' || err === 'AbortError') {
           assistantMsg.content += `\n\n[Generation stopped by user]`
        } else {
           assistantMsg.content += `\n\n⚠️ Error: ${err}`
           error.value = err
        }
        assistantMsg.streaming = false
        isStreaming.value = false
        abortController.value = null
        finalizeTimelineStep(step, 'error')
      },
      abortController.value.signal
    )
  }

  function stopStreaming() {
    if (abortController.value) {
      abortController.value.abort()
      abortController.value = null
      isStreaming.value = false
    }
  }

  function handleStructuredEvent(event, parentStep) {
    if (event.type === 'tool_start') {
      addTimelineStep('tool_start', { count: event.count })
      // Push placeholder for tool blocks
      messages.value.push({
        role: 'tool_group',
        id: Date.now(),
        count: event.count,
        tools: []
      })
    } else if (event.type === 'tool_result') {
      const status = event.data?.status
      const stepStatus = status === 'requires_confirmation' ? 'needs_confirmation' : (status === 'success' ? 'done' : 'error')
      
      const step = addTimelineStep('tool_result', { 
        tool: event.data?.tool, 
        status: status,
        parameters: event.data?.parameters,
        message: event.data?.message,
        diff: event.data?.diff,
        backup: event.data?.backup,
        path: event.data?.path
      }, stepStatus)

      // Find the last tool_group and push this result into it
      const lastGroup = [...messages.value].reverse().find(m => m.role === 'tool_group')
      if (lastGroup) {
        lastGroup.tools.push({
          name: event.data?.tool,
          status: status,
          result: event.data?.message || event.data?.result || event.data,
          params: event.data?.parameters
        })
      }
    } else if (event.type === 'tool_followup_start') {
      addTimelineStep('followup', { label: 'Generating answer with tool context' })
    } else if (event.type === 'analysis') {
      addTimelineStep('debug_analysis', { data: event.data })
    } else if (event.type === 'discovery') {
      addTimelineStep('discovery', { section: event.section, content: event.content }, 'done')
      // Also append to the non-done assistant message for real-time visibility
      const assistantMsg = [...messages.value].reverse().find(m => m.role === 'assistant' && m.streaming !== false)
      if (assistantMsg) {
        assistantMsg.content += `\n\n🔍 **Discovery: ${event.section}**\n> ${event.content}\n\n`
      }
    } else if (event.type === 'granular_status') {
      addTimelineStep('granular', { label: event.label, detail: event.detail })
    }
  }

  async function runToolManually(step) {
    if (!step || step.data.status !== 'requires_confirmation') return
    
    step.status = 'running'
    try {
      const baseUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000'
      const response = await fetch(`${baseUrl}/api/tools/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          tool_name: step.data.tool,
          parameters: step.data.parameters,
          force: true,
          session_id: sessionId.value
        })
      })
      const result = await response.json()
      if (result.status === 'success') {
        step.status = 'done'
        step.data.status = 'success'
        step.data.message = 'Executed successfully (confirmed by user)'
        
        // Proactively sendMessage as a "hidden" follow-up to resume the AI turn
        const followUpText = `Tool ${step.data.tool} executed successfully. Please summarize and finalize.`
        this.sendMessage(followUpText, [], true) // Added 'true' for hidden flag
      } else {
        step.status = 'error'
        step.data.status = 'error'
        step.data.message = result.message || 'Execution failed'
      }
    } catch (err) {
      step.status = 'error'
      step.data.message = err.message
    }
  }

  function addTimelineStep(type, data = {}, status = 'running') {
    const step = {
      id: Date.now() + Math.random(),
      type,
      data,
      timestamp: new Date().toISOString(),
      status: status,
    }
    timelineEvents.value.push(step)
    // Keep last 100 events
    if (timelineEvents.value.length > 100) {
      timelineEvents.value = timelineEvents.value.slice(-100)
    }
    return step
  }

  function finalizeTimelineStep(step, status) {
    if (step) step.status = status
  }

  function clearMessages() {
    messages.value = []
    timelineEvents.value = []
  }

  function setSessionId(id) {
    sessionId.value = id
  }

  return {
    messages,
    isStreaming,
    error,
    sessionId,
    timelineEvents,
    chatHistory,
    sendMessage,
    stopStreaming,
    runToolManually,
    clearMessages,
    setSessionId,
    addTimelineStep,
    getStaticUrl,
  }
})
