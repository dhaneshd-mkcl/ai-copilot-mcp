import axios from 'axios'

const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const http = axios.create({ baseURL: BASE_URL, timeout: 10000 })

/**
 * SSE streaming helper.
 * onChunk receives either a string (text delta) or a structured event object.
 */
export async function streamRequest(endpoint, body, onChunk, onDone, onError, signal) {
  const url = `${BASE_URL}${endpoint}`
  try {
    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal,
    })
    if (!response.ok) throw new Error(`HTTP ${response.status}`)

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop()

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        try {
          const data = JSON.parse(line.slice(6))
          if (data.type === 'done') { onDone?.(); return }
          if (data.type === 'error') { onError?.(data.message); return }
          if (data.type === 'delta') {
            onChunk?.(data.delta)
          } else if (data.type === 'preamble') {
            // ignore preamble events silently
          } else {
            // Pass structured events (tool_start, tool_result, analysis, etc.) to caller
            onChunk?.(data)
          }
        } catch {}
      }
    }
    onDone?.()
  } catch (err) {
    onError?.(err.message)
  }
}

/**
 * WebSocket streaming helper — alternative to SSE.
 * Returns a cleanup function.
 */
export function connectWsChat(onMessage, onClose) {
  const wsUrl = BASE_URL.replace(/^http/, 'ws') + '/api/ws/chat'
  const ws = new WebSocket(wsUrl)
  ws.onmessage = (e) => {
    try { onMessage(JSON.parse(e.data)) } catch {}
  }
  ws.onclose = () => onClose?.()
  ws.onerror = (e) => console.error('WebSocket error:', e)
  return {
    send: (payload) => ws.send(JSON.stringify(payload)),
    close: () => ws.close(),
    get readyState() { return ws.readyState },
  }
}

export const api = {
  // Chat
  health: () => http.get('/health'),

  // Code
  analyzeCode: (code, language, task) =>
    http.post('/api/code/analyze', { code, language, task }),

  generateCode: (prompt, language, context) =>
    http.post('/api/code/generate', { prompt, language, context }),

  debugCode: (code, error, language) =>
    http.post('/api/code/debug', { code, error, language }),

  // Tools — force=true bypasses dangerous-tool confirmation
  runTool: (tool_name, parameters, force = false) =>
    http.post('/api/tools/run', { tool_name, parameters, force }),

  listTools: () => http.get('/api/tools'),
  toolCategories: () => http.get('/api/tools/categories'),

  // Repo
  listFiles: (path = '.') => http.get('/api/repo/files', { params: { path } }),
  readFile: (path) => http.get('/api/repo/read', { params: { path } }),
  searchRepo: (query, file_types = [], path = '.') =>
    http.post('/api/repo/search', { query, path, file_types }),
  analyzeRepo: () => http.get('/api/repo/analyze'),
  scanRepo: (path = '.', max_depth = 3) =>
    http.get('/api/repo/scan', { params: { path, max_depth } }),

  // Sessions
  getSessions: () => http.get('/api/sessions'),
  clearSession: (session_id = 'default') =>
    http.post('/api/sessions/clear', { session_id }),

  // OCR — extract text from image
  extractText: (data_uri, mime) =>
    http.post('/api/ocr', { data_uri, mime }, { timeout: 120000 }),

  // File upload
  uploadFile: (file) => {
    const form = new FormData()
    form.append('file', file)
    return http.post('/api/upload', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 30000,
    })
  },
}

export default api
