<template>
  <div class="flex flex-col h-full bg-transparent">
    <!-- Toolbar -->
    <div class="panel-header glass-panel border-none">
      <div class="flex items-center gap-4">
        <span class="text-accent-cyan font-black tracking-widest text-[10px]">// SOURCE_EDITOR</span>
        <div class="h-4 w-px bg-white/10"></div>
        <select v-model="store.currentLanguage"
          class="bg-slate-50 border border-slate-200 text-slate-800 text-[10px] rounded-lg px-3 py-1 font-mono focus:outline-none focus:border-accent-cyan/40 appearance-none cursor-pointer hover:bg-slate-100 transition-colors">
          <option v-for="lang in languages" :key="lang" :value="lang">{{ lang.toUpperCase() }}</option>
        </select>
      </div>
      <div class="flex items-center gap-2">
        <button v-for="act in editorActions" :key="act.label" @click="handleAction(act.id)" :class="['px-3 py-1.5 rounded-lg text-[10px] font-mono transition-all duration-300 border',
          act.primary
            ? 'bg-accent-cyan border-accent-cyan text-white hover:bg-accent-cyan/90 shadow-sm'
            : 'bg-white border-slate-200 text-slate-600 hover:text-slate-900 hover:bg-slate-50']">
          {{ act.label }}
        </button>
        <button @click="clearEditor"
          class="ml-2 w-8 h-8 flex items-center justify-center rounded-lg bg-red-500/5 border border-red-500/10 text-red-500 hover:bg-red-500/10 transition-all">✕</button>
      </div>
    </div>

    <!-- CodeMirror editor -->
    <div ref="editorEl" class="flex-1 overflow-hidden"></div>

    <!-- Footer stats -->
    <div
      class="px-6 py-2 border-t border-border-dim bg-slate-50 flex items-center justify-between text-[10px] font-mono text-slate-500 uppercase tracking-widest">
      <div class="flex items-center gap-4">
        <span>LOC: {{ lineCount }}</span>
        <span>SIZE: {{ charCount }} CHR</span>
      </div>
      <div class="flex items-center gap-4">
        <span v-if="store.isStreaming" class="text-accent-purple animate-pulse flex items-center gap-2">
          <span class="w-1.5 h-1.5 rounded-full bg-accent-purple shadow-[0_0_8px_#9d50ff]"></span>
          UPDATING_BUFFER...
        </span>
        <button @click="generatePrompt"
          class="text-accent-cyan/70 hover:text-accent-cyan transition-colors flex items-center gap-2">
          <span>⚡</span>
          PROMPT_GENERATE
        </button>
      </div>
    </div>

    <!-- Generate prompt modal -->
    <div v-if="showGenPrompt"
      class="absolute inset-0 bg-black/60 backdrop-blur-md flex items-center justify-center z-[100] animate-fade-in p-6">
      <div
        class="glass-panel w-full max-w-lg rounded-3xl overflow-hidden shadow-2xl border border-white/10 animate-slide-up">
        <div class="px-6 py-5 border-b border-white/5 flex items-center justify-between bg-white/5">
          <div class="flex items-center gap-3">
            <span class="text-xl">⚡</span>
            <span class="font-display font-black tracking-widest text-xs uppercase">Instructional Synthesis</span>
          </div>
          <button @click="showGenPrompt = false"
            class="text-text-secondary hover:text-white transition-colors">✕</button>
        </div>
        <div class="p-6 space-y-6">
          <textarea v-model="genPromptText" rows="4" class="input-field min-h-[120px]"
            placeholder="Define the structural parameters for generation..."></textarea>
          <div class="flex gap-3">
            <button @click="submitGenPrompt" :disabled="!genPromptText.trim()"
              class="btn-primary flex-1 h-12 uppercase tracking-widest text-xs">Execute Generation</button>
            <button @click="showGenPrompt = false"
              class="btn-ghost border border-white/10 h-12 uppercase tracking-widest text-xs">Abort</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { EditorView, basicSetup } from 'codemirror'
import { EditorState } from '@codemirror/state'
import { oneDark } from '@codemirror/theme-one-dark'
import { python } from '@codemirror/lang-python'
import { javascript } from '@codemirror/lang-javascript'
import { useCopilotStore } from '../stores/copilotStore.js'

const store = useCopilotStore()
const editorEl = ref(null)
const showGenPrompt = ref(false)
const genPromptText = ref('')
let editorView = null

const languages = ['python', 'javascript', 'typescript', 'html', 'css', 'json', 'bash', 'go', 'rust', 'java']

const editorActions = [
  { id: 'explain', label: '📖 EXPLAIN' },
  { id: 'debug', label: '🐛 DEBUG' },
  { id: 'refactor', label: '♻️ REFACTOR', primary: true },
]

const getLanguageExt = (lang) => {
  if (lang === 'python') return python()
  if (['javascript', 'typescript', 'jsx', 'tsx'].includes(lang)) return javascript({ typescript: lang === 'typescript' || lang === 'tsx' })
  // For other languages like Java, C++, etc., we use a base highlight or just text for now
  // Add more dynamic imports here if needed for full support
  return []
}

const lineCount = computed(() => (store.currentCode.match(/\n/g) || []).length + 1)
const charCount = computed(() => store.currentCode.length)

async function createEditor() {
  await nextTick()
  if (!editorEl.value) return
  if (editorView) editorView.destroy()

  const state = EditorState.create({
    doc: store.currentCode,
    extensions: [
      basicSetup,
      oneDark,
      getLanguageExt(store.currentLanguage),
      EditorView.updateListener.of((update) => {
        if (update.docChanged) {
          store.currentCode = update.state.doc.toString()
        }
      }),
      EditorView.theme({
        '&': { height: '100%', background: '#ffffff' },
        '.cm-content': { fontFamily: "'JetBrains Mono', monospace", fontSize: '13px', color: '#1e293b' },
        '.cm-gutters': { background: '#f8fafc', borderRight: '1px solid #e2e8f0', color: '#94a3b8' },
      })
    ]
  })
  editorView = new EditorView({ state, parent: editorEl.value })
}

function updateEditorContent(code) {
  if (!editorView) return
  const current = editorView.state.doc.toString()
  if (current !== code) {
    editorView.dispatch({
      changes: { from: 0, to: current.length, insert: code }
    })
  }
}

function handleAction(task) {
  if (store.currentCode.trim()) {
    store.analyzeCurrentCode(task)
    store.activeTab = 'chat'
  }
}

function clearEditor() {
  store.currentCode = ''
  updateEditorContent('')
}

function generatePrompt() {
  showGenPrompt.value = true
}

async function submitGenPrompt() {
  if (!genPromptText.value.trim()) return
  showGenPrompt.value = false
  store.activeTab = 'chat'
  await store.generateCode(genPromptText.value)
  genPromptText.value = ''
}

watch(() => store.currentLanguage, () => createEditor())
watch(() => store.currentCode, (code) => updateEditorContent(code))
watch(() => store.activeTab, (tab) => {
  if (tab === 'editor') createEditor()
})

onMounted(() => createEditor())
onUnmounted(() => editorView?.destroy())
</script>
