<template>
  <div class="flex flex-col h-full">
    <!-- Messages -->
    <div ref="messagesEl" class="flex-1 overflow-y-auto p-4 space-y-4">
      <!-- Welcome Screen: Deployment Level -->
      <WelcomeHero v-if="store.messages.length === 0" @select="store.sendMessage" />

      <!-- Messages -->
      <template v-for="msg in store.messages" :key="msg.id">
        <div v-if="!msg.hidden" class="animate-slide-up">

          <!-- User message -->
          <div v-if="msg.role === 'user'" class="flex justify-end pr-2">
            <div class="max-w-[85%] space-y-2">
              <!-- Image inline -->
              <div v-if="msg.dataUri" class="flex justify-end">
                <img :src="msg.dataUri" :alt="msg.file"
                  class="max-w-xs max-h-48 rounded-2xl border border-border-dim object-cover shadow-2xl" />
              </div>
              <!-- File badge -->
              <div v-else-if="msg.file" class="flex justify-end">
                <span
                  class="inline-flex items-center gap-2 px-3 py-1.5 rounded-xl bg-accent-cyan/10 border border-accent-cyan/20 text-[10px] text-accent-cyan font-mono uppercase tracking-wider font-bold">
                  {{ fileIcon(msg.fileType) }} {{ msg.file }}
                </span>
              </div>
              <!-- Text bubble -->
              <div class="message-user text-sm leading-relaxed">
                {{ msg.content }}
              </div>
            </div>
          </div>

          <!-- Tool Group / Execution Block -->
          <div v-else-if="msg.role === 'tool_group'" class="flex flex-col gap-2 ml-12 my-2 animate-slide-up">
            <div class="flex items-center gap-2 mb-1">
              <div class="h-px bg-slate-200 flex-1"></div>
              <span class="text-[9px] font-black text-slate-400 uppercase tracking-[0.2em]">Tool Execution</span>
              <div class="h-px bg-slate-200 flex-1"></div>
            </div>

            <div v-for="(tool, idx) in msg.tools" :key="idx"
              class="group relative bg-white border border-slate-200/60 rounded-xl p-3 shadow-sm hover:shadow-md transition-all hover:border-accent-cyan/30 overflow-hidden">
              <div class="flex items-center justify-between mb-2">
                <div class="flex items-center gap-2">
                  <span class="text-xs">{{ tool.status === 'success' ? '✅' : (tool.status === 'error' ? '❌' : '⏳')
                  }}</span>
                  <span class="font-mono text-[11px] font-bold text-slate-700 uppercase tracking-tight">{{ tool.name
                  }}</span>
                </div>
                <span class="text-[9px] font-bold px-2 py-0.5 rounded-full uppercase tracking-tighter"
                  :class="tool.status === 'success' ? 'bg-green-50 text-green-600' : 'bg-amber-50 text-amber-600'">
                  {{ tool.status }}
                </span>
              </div>

              <!-- Result Preview -->
              <div class="text-[11px] text-slate-600 leading-relaxed font-sans mt-1">
                <template v-if="typeof tool.result === 'string'">
                  <div class="line-clamp-3 italic">{{ tool.result }}</div>
                </template>
                <template v-else>
                  <!-- Image thumbnail if available (e.g. screenshot) -->
                  <div v-if="tool.result.screenshot_path || tool.result.path?.endsWith('.png')" class="mb-2">
                    <img :src="chatStore.getStaticUrl(tool.result.screenshot_path || tool.result.path)"
                      class="rounded-lg border border-slate-200 shadow-sm max-h-40 w-full object-cover cursor-zoom-in" />
                  </div>
                  <pre
                    class="text-[10px] bg-slate-50 p-2 rounded border border-slate-100 overflow-x-auto max-h-32">{{ JSON.stringify(tool.result, null, 2) }}</pre>
                </template>
              </div>

              <!-- Hover overlay for more info -->
              <div
                class="absolute inset-0 bg-white/95 opacity-0 group-hover:opacity-100 flex items-center justify-center gap-3 transition-opacity">
                <button @click="tool.showFull = !tool.showFull"
                  class="px-3 py-1.5 rounded-lg bg-slate-900 text-white text-[10px] font-bold uppercase tracking-widest shadow-lg active:scale-95">
                  {{ tool.showFull ? 'HIDE LOGS' : 'VIEW FULL OUTPUT' }}
                </button>
              </div>
            </div>

            <!-- Full Overlay for details -->
            <div v-for="(tool, idx) in msg.tools.filter(t => t.showFull)" :key="'full-' + idx"
              class="fixed inset-0 z-[100] bg-slate-900/40 backdrop-blur-sm flex items-center justify-center p-6 animate-fade-in">
              <div
                class="bg-white w-full max-w-2xl max-h-[80vh] rounded-2xl shadow-2xl flex flex-col overflow-hidden border border-white/20">
                <div class="p-4 border-b border-slate-100 flex items-center justify-between bg-slate-50/50">
                  <div class="flex items-center gap-3">
                    <span class="text-xl">🛠️</span>
                    <div>
                      <div class="text-[10px] font-black text-slate-400 uppercase tracking-widest">Tool Output</div>
                      <div class="font-mono text-sm font-bold text-slate-800 uppercase">{{ tool.name }}</div>
                    </div>
                  </div>
                  <button @click="tool.showFull = false"
                    class="w-8 h-8 rounded-full hover:bg-slate-200 flex items-center justify-center text-slate-500">✕</button>
                </div>
                <div class="flex-1 overflow-y-auto p-6 font-mono text-[12px] bg-slate-900 text-slate-200">
                  <div
                    class="mb-4 text-slate-500 border-b border-slate-800 pb-2 uppercase tracking-[0.2em] text-[10px]">
                    Parameters
                  </div>
                  <pre class="text-accent-cyan mb-6">{{ JSON.stringify(tool.params, null, 2) }}</pre>

                  <div
                    class="mb-2 text-slate-500 border-b border-slate-800 pb-2 uppercase tracking-[0.2em] text-[10px]">
                    Result
                  </div>
                  <pre>{{ typeof tool.result === 'string' ? tool.result : JSON.stringify(tool.result, null, 2) }}</pre>
                </div>
              </div>
            </div>
          </div>

          <!-- Assistant message -->
          <div
            v-else-if="msg.role === 'assistant' && (msg.content?.trim() || msg.streaming || (msg === lastMsg && (statusStyle.isActionable || statusStyle.dots)))"
            class="flex gap-4 group">
            <div
              class="w-8 h-8 rounded-xl bg-gradient-to-br from-accent-cyan to-accent-purple flex-shrink-0 flex items-center justify-center text-[10px] font-black text-white shadow-lg mt-1 group-hover:scale-110 transition-transform">
              AI</div>
            <div class="flex-1 min-w-0 space-y-3">
              <div v-if="msg.content?.trim() || msg.streaming" class="message-ai"
                :class="{ 'cursor-blink': msg.streaming }">
                <div v-if="msg.streaming" class="ai-glow"></div>
                <div v-if="!msg.content?.trim() && msg.streaming"
                  class="flex items-center gap-3 text-slate-500 animate-pulse italic text-xs">
                  <span>🔄</span> Evaluating tools & preparing response...
                </div>
                <div v-else v-html="renderMarkdown(msg.content)"></div>
              </div>

              <!-- Live status pill (only on the last message) -->
              <div v-if="msg === lastMsg && (msg.streaming || statusStyle.isActionable)"
                class="flex items-center gap-2 px-1">
                <div class="status-pill transition-all duration-300 shadow-xl shadow-indigo-500/10"
                  :class="statusStyle.cls">
                  <!-- Animated icon -->
                  <span class="flex-shrink-0" :class="statusStyle.spin ? 'animate-spin' : ''">{{
                    statusStyle.icon }}</span>
                  <div class="flex flex-col">
                    <span v-if="statusStyle.isActionable"
                      class="text-[7px] text-indigo-400 font-black tracking-widest leading-none mb-0.5 opacity-80 uppercase">Proposed
                      Action</span>
                    <span class="font-black uppercase tracking-widest text-[9px]">{{ statusStyle.label }}</span>
                  </div>
                  <!-- Progress dots -->
                  <span v-if="statusStyle.dots" class="flex gap-1 ml-1">
                    <span class="w-1 h-1 rounded-full bg-current animate-bounce" style="animation-delay:0ms"></span>
                    <span class="w-1 h-1 rounded-full bg-current animate-bounce" style="animation-delay:150ms"></span>
                    <span class="w-1 h-1 rounded-full bg-current animate-bounce" style="animation-delay:300ms"></span>
                  </span>

                  <!-- Action button (Confirm & Execute) -->
                  <div v-if="statusStyle.isActionable" class="ml-3 flex items-center gap-2">
                    <div class="group relative">
                      <button
                        class="px-2 py-0.5 rounded border border-white/20 text-[8px] opacity-60 hover:opacity-100 transition-opacity">
                        VIEW PARAMS
                      </button>
                      <!-- Params Tooltip/Dropdown -->
                      <div
                        class="absolute bottom-full left-0 mb-2 w-64 bg-surface-3 border border-border/80 rounded-xl shadow-2xl p-3 opacity-0 pointer-events-none group-hover:opacity-100 group-hover:pointer-events-auto transition-all transform translate-y-2 group-hover:translate-y-0 z-50">
                        <div class="text-[9px] font-black text-slate-500 mb-2 uppercase tracking-widest">Tool Parameters
                        </div>
                        <pre
                          class="text-[10px] font-mono text-accent-cyan bg-black/40 p-2 rounded-lg border border-white/5 overflow-x-auto">
                {{ JSON.stringify(statusStyle.event.data.parameters, null, 2) }}</pre>
                      </div>
                    </div>
                    <button @click="chatStore.runToolManually(statusStyle.event)"
                      class="px-3 py-1 rounded-full bg-slate-900 text-white text-[9px] font-black hover:bg-accent-cyan transition-all transform hover:scale-105 shadow-xl border border-white/20 active:scale-95">
                      CONFIRM & EXECUTE
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </template>
    </div>

    <!-- Quick actions -->
    <div class="px-6 pb-3 flex gap-2 flex-wrap overflow-x-auto no-scrollbar">
      <button v-for="action in quickActions" :key="action.label" @click="action.fn()" :disabled="store.isStreaming"
        class="px-2.5 py-1.5 rounded-full border border-slate-200 bg-white text-[9px] font-display font-black text-text-secondary hover:text-text-primary hover:border-accent-cyan/40 transition-all whitespace-nowrap uppercase tracking-widest shadow-sm">
        {{ action.label }}
      </button>
    </div>

    <!-- Attached files / images preview -->
    <div v-if="attachedFiles.length" class="px-6 pb-4 space-y-2">
      <div v-for="(file, idx) in attachedFiles" :key="idx"
        class="flex items-start gap-4 p-3 rounded-xl bg-white/5 backdrop-blur-md border border-border-dim max-w-lg shadow-lg group relative">
        <!-- Image thumbnail -->
        <img v-if="file.type === 'image'" :src="file.data_uri"
          class="w-12 h-12 rounded-lg object-cover flex-shrink-0 border border-border" alt="preview" />
        <!-- Non-image icon -->
        <div v-else
          class="w-12 h-12 rounded-lg bg-surface-3 border border-border flex items-center justify-center text-xl flex-shrink-0">
          {{ fileIcon(file.type) }}
        </div>

        <div class="flex-1 min-w-0">
          <div class="text-[10px] font-mono text-slate-800 truncate font-semibold uppercase tracking-tight">{{
            file.filename }}</div>
          <div class="text-[10px] text-slate-500">{{ file.type }} · {{ formatSize(file.size) }}</div>

          <!-- Zip info -->
          <div v-if="file.type === 'zip'"
            class="text-[9px] text-accent-cyan mt-1 font-display font-black uppercase tracking-tight italic">
            {{ file.content }}
          </div>
        </div>

        <button @click="removeAttachment(idx)"
          class="text-slate-600 hover:text-red-400 transition-colors px-1 absolute -top-2 -right-2 bg-surface-2 rounded-full w-5 h-5 flex items-center justify-center border border-border shadow-md">✕</button>
      </div>
    </div>

    <!-- Upload progress -->
    <div v-if="isUploading" class="px-4 pb-2">
      <div
        class="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg bg-surface-2 border border-border text-xs font-mono text-slate-400 animate-pulse">
        ⏳ Uploading…</div>
    </div>

    <!-- Input row -->
    <div class="p-4 pt-0">
      <div class="input-panel" :class="dragOver ? 'border-accent-cyan bg-white/60' : ''"
        @dragover.prevent="dragOver = true" @dragleave="dragOver = false" @drop.prevent="handleDrop">
        <input ref="fileInputEl" type="file" class="hidden" accept="*/*" @change="handleFileSelect" />

        <button @click="fileInputEl.click()" :disabled="store.isStreaming || isUploading" title="Attach file or image"
          class="flex-shrink-0 self-end p-2 rounded-lg text-slate-500 hover:text-accent-cyan hover:bg-surface-3 transition-all disabled:opacity-40 text-base">📎</button>

        <textarea ref="inputEl" v-model="inputText" @keydown.enter.exact.prevent="submit"
          @keydown.shift.enter.exact="inputText += '\n'"
          :placeholder="dragOver ? 'Drop file here…' : 'Ask Titan anything…'" rows="2"
          class="flex-1 bg-transparent resize-none text-[14px] text-slate-800 placeholder-slate-400 focus:outline-none font-sans py-1 min-h-[2.5rem] max-h-48 leading-relaxed" />

        <div class="flex gap-2 self-end pb-1">
          <button v-if="store.isStreaming" @click="chatStore.stopStreaming()"
            class="px-5 py-2 rounded-xl bg-red-50/80 border border-red-200 text-red-600 hover:bg-red-100 transition-all font-black text-[10px] uppercase tracking-widest shadow-sm">
            STOP
          </button>
          <button @click="submit" :disabled="store.isStreaming || (!inputText.trim() && !attachedFile)"
            class="btn-primary py-2 px-6 rounded-2xl flex items-center justify-center min-w-[60px]">
            <span v-if="!store.isStreaming" class="text-base">🚀</span>
            <span v-else class="text-xs animate-spin-slow">⏳</span>
          </button>
        </div>
      </div>
      <p class="text-[11px] text-slate-500 mt-2 px-3 font-medium opacity-60">
        Attach images, code files, or generic prompts. Use <span class="text-indigo-500">Shift + Enter</span> for new
        lines.
      </p>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, nextTick, computed } from 'vue'
import { marked } from 'marked'
import hljs from 'highlight.js'
import { useCopilotStore } from '../stores/copilotStore.js'
import { useChatStore } from '../stores/chatStore.js'
import { useTimeline } from '../composables/useTimeline.js'
import { useAttachments } from '../composables/useAttachments.js'
import WelcomeHero from './WelcomeHero.vue'

const store = useCopilotStore()
const chatStore = useChatStore()
const inputText = ref('')
const messagesEl = ref(null)
const fileInputEl = ref(null)
const dragOver = ref(false)

// Last streaming message reference
const lastMsg = computed(() => {
  const msgs = store.messages
  if (!msgs.length) return null
  // Find the last assistant message that is streaming OR the last assistant message if the AI is overall streaming
  for (let i = msgs.length - 1; i >= 0; i--) {
    if (msgs[i].role === 'assistant') return msgs[i]
  }
  return null
})

const { statusStyle } = useTimeline(chatStore)

const renderMarkdown = (t) => { try { return marked.parse(t || '') } catch { return t } }
const formatSize = (b) => b < 1024 ? `${b} B` : b < 1048576 ? `${(b / 1024).toFixed(1)} KB` : `${(b / 1048576).toFixed(1)} MB`
const fileIcon = (t) => t === 'image' ? '🖼️' : t === 'text' ? '📄' : (t === 'zip' ? '📦' : '📦')


const quickActions = [
  { label: '🔍 Analyze', fn: () => store.analyzeCurrentCode('analyze') },
  { label: '🐛 Debug', fn: () => store.analyzeCurrentCode('debug') },
  { label: '📖 Explain', fn: () => store.analyzeCurrentCode('explain') },
  { label: '♻️ Refactor', fn: () => store.analyzeCurrentCode('refactor') },
  { label: '🧪 Tests', fn: () => store.analyzeCurrentCode('test') },
  { label: '🗑️ Clear', fn: () => store.clearMessages() },
]

const {
  isUploading,
  attachedFiles,
  handleFileSelect,
  handleDrop,
  removeAttachment
} = useAttachments(inputText)

async function submit() {
  const text = inputText.value.trim()
  if ((!text && attachedFiles.value.length === 0) || store.isStreaming) return

  const messageText = text || "Analyze these files."
  const files = [...attachedFiles.value]

  inputText.value = ''
  attachedFiles.value = []

  await store.sendMessage(messageText, files)
}

watch(() => store.messages.length, async () => { await nextTick(); if (messagesEl.value) messagesEl.value.scrollTop = messagesEl.value.scrollHeight })
watch(() => store.messages[store.messages.length - 1]?.content, async () => { await nextTick(); if (messagesEl.value) messagesEl.value.scrollTop = messagesEl.value.scrollHeight })
</script>
