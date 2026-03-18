<template>
  <div class="flex flex-col h-full bg-surface-1/30 backdrop-blur-xl border-l border-border/50">
    <div class="panel-header flex justify-between items-center px-6 py-4 border-b border-slate-100 bg-white/50">
      <div class="flex items-center gap-4">
        <span
          class="text-slate-800 font-display font-black text-[11px] tracking-[0.1em] uppercase flex items-center gap-2">
          <span class="text-indigo-600">◈</span> Workspace
        </span>
        <button v-if="repoStore.currentPath !== '.'" @click="goBack"
          class="group flex items-center gap-2 text-[9px] font-display font-black uppercase tracking-widest bg-slate-50 px-3 py-1.5 rounded-full border border-slate-200 hover:border-indigo-400/50 hover:bg-white transition-all shadow-sm">
          <span class="text-slate-400 group-hover:text-indigo-600 transition-colors">←</span>
          <span class="text-slate-500 group-hover:text-slate-900">UP</span>
        </button>
      </div>
      <div class="flex items-center gap-3">
        <button @click="promptNewFolder" title="New Folder"
          class="p-2 rounded-xl border border-transparent hover:border-slate-200 hover:bg-white text-slate-500 hover:text-accent-green transition-all transform active:scale-95 shadow-sm hover:shadow-md">
          📁<span class="text-[9px] ml-1 font-black">+</span>
        </button>
        <button @click="repoStore.loadFiles(repoStore.currentPath)" title="Refresh"
          class="p-2 rounded-xl border border-transparent hover:border-slate-200 hover:bg-white text-slate-500 hover:text-accent-cyan transition-all transform active:scale-95 shadow-sm hover:shadow-md">
          <span :class="{ 'animate-spin inline-block': repoStore.isLoading }">↻</span>
        </button>
      </div>
    </div>

    <!-- Breadcrumbs -->
    <div
      class="px-4 py-2 bg-surface-1/40 border-b border-border/30 flex items-center gap-1 overflow-x-auto no-scrollbar shadow-inner">
      <button @click="repoStore.loadFiles('.')"
        class="text-[10px] font-mono hover:text-accent-cyan flex-shrink-0 transition-colors"
        :class="repoStore.currentPath === '.' ? 'text-accent-cyan font-bold' : 'text-slate-500'">
        root
      </button>
      <template v-for="(part, idx) in breadcrumbs" :key="idx">
        <span class="text-[10px] text-slate-700">/</span>
        <button @click="jumpTo(idx)"
          class="text-[10px] font-mono hover:text-accent-cyan truncate flex-shrink-0 transition-colors"
          :class="idx === breadcrumbs.length - 1 ? 'text-accent-cyan font-bold' : 'text-slate-500'">
          {{ part }}
        </button>
      </template>
    </div>

    <!-- Search Section -->
    <div class="p-4 border-b border-border/30 bg-gradient-to-b from-slate-100 to-transparent">
      <div class="relative group">
        <input v-model="searchQuery" @keydown.enter="doSearch" placeholder="Search files & symbols..."
          class="w-full bg-white border border-slate-200 rounded-xl px-4 py-2 text-xs font-mono text-text-primary focus:outline-none focus:border-accent-cyan/50 focus:ring-1 focus:ring-accent-cyan/20 transition-all placeholder:text-slate-400 shadow-sm" />
        <button @click="doSearch"
          class="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-slate-600 hover:text-accent-cyan transition-colors">
          🔍
        </button>
      </div>
    </div>

    <!-- Stats Dashboard (Glassmorphic) -->
    <div v-if="repoStore.repoStats" class="px-6 py-3">
      <div class="grid grid-cols-3 gap-3">
        <div v-for="stat in statsItems" :key="stat.label"
          class="bg-white rounded-2xl p-2.5 border border-slate-100 shadow-sm hover:shadow-xl hover:-translate-y-1 transition-all duration-300">
          <div class="text-[14px] font-display font-black mb-1 flex items-center justify-center gap-2"
            :class="stat.cls">
            <span class="text-[11px] opacity-70">{{ stat.icon }}</span>
            {{ stat.value }}
          </div>
          <div class="text-[9px] text-slate-400 uppercase tracking-widest text-center font-bold">{{ stat.label }}</div>
        </div>
      </div>
    </div>

    <!-- File tree -->
    <div class="flex-1 overflow-y-auto px-2 py-2 space-y-0.5 custom-scrollbar">
      <div v-if="repoStore.isLoading" class="flex flex-col items-center justify-center h-40 space-y-3">
        <div class="w-8 h-8 border-2 border-accent-cyan/20 border-t-accent-cyan rounded-full animate-spin"></div>
        <div class="text-[10px] text-slate-500 font-mono animate-pulse uppercase tracking-widest">Scanning...</div>
      </div>

      <div v-else-if="repoStore.searchResults.length > 0">
        <div
          class="flex items-center justify-between px-3 py-1 mb-2 bg-accent-cyan/5 rounded-lg border border-accent-cyan/20">
          <span class="text-[10px] text-accent-cyan font-bold uppercase tracking-wider">{{
            repoStore.searchResults.length }}
            Results</span>
          <button @click="repoStore.clearSearch()"
            class="text-[10px] text-slate-500 hover:text-red-400 trasition-colors">✕
            Clear</button>
        </div>
        <div v-for="r in repoStore.searchResults" :key="r.file + r.line"
          class="px-3 py-2 rounded-xl hove:bg-white/5 border border-transparent hover:border-border/30 hover:bg-surface-2 cursor-pointer group transition-all"
          @click="openSearchResult(r)">
          <div class="text-xs font-mono text-accent-cyan font-bold truncate mb-1">
            <span class="opacity-50">./</span>{{ r.file }}<span class="text-slate-400 ml-1">:{{ r.line }}</span>
          </div>
          <div
            class="text-[10px] text-slate-600 font-mono truncate bg-slate-100 p-1.5 rounded-lg border border-slate-200 group-hover:text-slate-800">
            {{ r.match }}</div>
        </div>
      </div>

      <div v-else-if="!repoStore.hasFiles"
        class="flex flex-col items-center justify-center h-60 text-center p-6 opacity-30">
        <div class="text-6xl mb-4 grayscale">📂</div>
        <p class="text-text-primary text-sm font-bold">Workspace Empty</p>
        <p class="text-slate-500 text-xs mt-2 font-mono">Inject code to begin</p>
      </div>

      <div v-else>
        <!-- File list -->
        <div v-for="file in repoStore.files" :key="file.name"
          class="flex items-center gap-4 px-4 py-3 rounded-2xl transition-all cursor-pointer group border border-transparent mb-1"
          :class="file.type === 'dir' ? 'hover:bg-accent-green/10 hover:border-accent-green/30' : 'hover:bg-white hover:border-slate-100 hover:shadow-xl hover:shadow-slate-200/50'"
          @click="selectFile(file)">

          <span class="text-xl group-hover:scale-125 transition-transform duration-500 drop-shadow-xl">{{
            getIcon(file)
          }}</span>

          <div class="flex-1 min-w-0">
            <div class="text-[10px] font-display font-black truncate transition-colors uppercase tracking-widest"
              :class="file.type === 'dir' ? 'text-accent-green' : 'text-slate-400 group-hover:text-text-primary'">
              {{ file.name }}
            </div>
            <div v-if="file.size" class="text-[8px] text-slate-400 font-display font-black uppercase tracking-tight">{{
              formatSize(file.size) }}</div>
          </div>

          <!-- Inline Actions -->
          <div
            class="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-all transform translate-x-2 group-hover:translate-x-0">
            <button @click.stop="promptRename(file)" title="Rename"
              class="p-1 rounded bg-surface-3 border border-border/50 hover:text-accent-cyan hover:border-accent-cyan/50 transition-all shadow-xl">
              <span class="text-[10px]">✏️</span>
            </button>
            <button @click.stop="confirmDelete(file)" title="Delete"
              class="p-1 rounded bg-surface-3 border border-border/50 hover:text-red-400 hover:border-red-400/50 transition-all shadow-xl">
              <span class="text-[10px]">🗑️</span>
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Analyze & Deep Scan -->
    <div class="p-4 space-y-2 border-t border-border/30 bg-surface-2/20">
      <button @click="repoStore.analyze()" :disabled="repoStore.isAnalyzing"
        class="w-full group flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl border border-border/50 hover:border-accent-green/50 hover:bg-accent-green/5 transition-all disabled:opacity-50 overflow-hidden relative">
        <div v-if="repoStore.isAnalyzing" class="absolute inset-0 bg-accent-green/10 animate-pulse"></div>
        <span class="text-lg group-hover:rotate-12 transition-transform">{{ repoStore.isAnalyzing ? '⚡' : '🔬' }}</span>
        <span
          class="text-[10px] font-display font-black uppercase tracking-widest text-slate-400 group-hover:text-accent-green transition-colors">
          {{ repoStore.isAnalyzing ? 'Analyzing Core...' : 'Deep Project Analysis' }}
        </span>
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import { useRepoStore } from '../stores/repoStore.js'
import { useCopilotStore } from '../stores/copilotStore.js'

const repoStore = useRepoStore()
const copilotStore = useCopilotStore()
const searchQuery = ref('')

const statsItems = computed(() => [
  { label: 'Files', value: repoStore.repoStats?.file_count || 0, icon: '📄', cls: 'text-accent-cyan' },
  { label: 'Lines', value: formatCount(repoStore.repoStats?.total_lines) || 0, icon: '⚡', cls: 'text-accent-green' },
  { label: 'Language', value: repoStore.topLanguage, icon: '💎', cls: 'text-accent-orange' }
])

function formatCount(n) {
  if (!n) return 0
  if (n > 1000) return (n / 1000).toFixed(1) + 'k'
  return n
}

const formatSize = (b) => b < 1024 ? `${b}b` : `${(b / 1024).toFixed(1)}k`

const getIcon = (file) => {
  if (file.type === 'dir') return '📁'
  const icons = {
    py: '🐍', js: '🟨', ts: '🔷', vue: '💚',
    json: '📋', md: '📝', html: '🌐', css: '🎨', sh: '⚙️',
  }
  const ext = file.name.split('.').pop()
  return icons[ext] || '📄'
}

async function doSearch() {
  await repoStore.search(searchQuery.value)
}

async function selectFile(file) {
  const relPath = repoStore.currentPath === '.'
    ? file.name
    : `${repoStore.currentPath}/${file.name}`

  if (file.type === 'dir') {
    await repoStore.loadFiles(relPath)
  } else if (file.type === 'file') {
    const content = await repoStore.readFile(relPath)
    if (content !== null) {
      copilotStore.setCode(content, file.name)
      copilotStore.activeTab = 'editor'
    }
  }
}

const breadcrumbs = computed(() => {
  if (repoStore.currentPath === '.' || !repoStore.currentPath) return []
  return repoStore.currentPath.split('/').filter(p => p && p !== '.')
})

function jumpTo(idx) {
  const parts = breadcrumbs.value.slice(0, idx + 1)
  repoStore.loadFiles(parts.join('/'))
}

function goBack() {
  const parts = repoStore.currentPath.split('/')
  if (parts.length > 1) {
    parts.pop()
    repoStore.loadFiles(parts.join('/'))
  } else {
    repoStore.loadFiles('.')
  }
}

async function openSearchResult(r) {
  const content = await repoStore.readFile(r.file)
  if (content !== null) {
    copilotStore.setCode(content, r.file)
    copilotStore.activeTab = 'editor'
  }
}

// New File Operations UI Handlers
async function promptNewFolder() {
  const name = prompt("Enter new folder name:")
  if (!name) return
  const path = repoStore.currentPath === '.' ? name : `${repoStore.currentPath}/${name}`
  const res = await repoStore.createDirectory(path)
  if (res.error) alert(`Error: ${res.error}`)
}

async function promptRename(file) {
  const newName = prompt(`Rename ${file.name} to:`, file.name)
  if (!newName || newName === file.name) return

  const source = repoStore.currentPath === '.' ? file.name : `${repoStore.currentPath}/${file.name}`
  const destination = repoStore.currentPath === '.' ? newName : `${repoStore.currentPath}/${newName}`

  const res = await repoStore.moveItem(source, destination)
  if (res.error) alert(`Error: ${res.error}`)
}

async function confirmDelete(file) {
  const confirmMsg = file.type === 'dir'
    ? `Are you sure you want to delete folder "${file.name}" and all its contents?`
    : `Delete file "${file.name}"?`

  if (!confirm(confirmMsg)) return

  const path = repoStore.currentPath === '.' ? file.name : `${repoStore.currentPath}/${file.name}`
  const res = await repoStore.deleteItem(path, file.type === 'dir')
  if (res.error) alert(`Error: ${res.error}`)
}

onMounted(() => {
  repoStore.loadFiles()
  repoStore.analyze()
})
</script>

<style scoped>
.custom-scrollbar::-webkit-scrollbar {
  width: 4px;
}

.custom-scrollbar::-webkit-scrollbar-track {
  background: transparent;
}

.custom-scrollbar::-webkit-scrollbar-thumb {
  background: rgba(0, 0, 0, 0.05);
  border-radius: 10px;
}

.custom-scrollbar::-webkit-scrollbar-thumb:hover {
  background: rgba(0, 0, 0, 0.1);
}
</style>
