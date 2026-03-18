<template>
  <div class="h-screen flex flex-col overflow-hidden font-sans bg-transparent">
    <!-- Header -->
    <header
      class="flex items-center justify-between px-8 py-5 glass-panel border-none flex-shrink-0 z-50 rounded-none shadow-none">
      <div class="flex items-center gap-5">
        <div
          class="group relative w-12 h-12 rounded-[18px] bg-gradient-to-br from-[#0ea5e9] to-[#8b5cf6] flex items-center justify-center text-2xl shadow-xl shadow-indigo-500/20 hover:scale-110 transition-transform duration-500 cursor-pointer">
          <div class="absolute inset-0 bg-white/10 rounded-[18px] opacity-0 group-hover:opacity-100 transition-opacity">
          </div>
          ⚡
        </div>
        <div>
          <h1
            class="font-display text-lg font-black text-slate-900 tracking-tighter leading-none flex items-center gap-2 uppercase">
            MKCL AI <span
              class="bg-indigo-600 text-white px-2 py-0.5 rounded-lg text-[10px] uppercase font-bold tracking-[0.2em]">Titan</span>
          </h1>
          <div
            class="text-[10px] text-slate-400 font-display font-black leading-none mt-2 uppercase tracking-[0.25em] opacity-80">
            {{ modelName }}</div>
        </div>
      </div>

      <!-- Nav navigation -->
      <nav
        class="flex items-center gap-2 bg-slate-100/50 backdrop-blur-md p-1.5 rounded-2xl border border-white shadow-inner">
        <button v-for="tab in tabs" :key="tab.id" @click="store.activeTab = tab.id" :class="['flex items-center gap-2 px-4 py-2 rounded-xl text-[10px] font-display font-black transition-all duration-500 transform',
          store.activeTab === tab.id
            ? 'bg-white text-text-primary shadow-xl border border-slate-200 scale-105'
            : 'text-slate-500 hover:text-text-primary hover:bg-white/60']">
          <span class="text-sm">{{ tab.icon }}</span>
          <span class="uppercase tracking-wider">{{ tab.label }}</span>
        </button>
      </nav>

      <!-- Connection Status -->
      <div class="flex items-center gap-4">
        <div
          class="flex items-center gap-2 px-3 py-1.5 rounded-full bg-white/80 border border-white text-[8px] font-display font-black tracking-widest uppercase shadow-premium">
          <span class="w-1.5 h-1.5 rounded-full"
            :class="store.isConnected ? 'bg-green-400 shadow-[0_0_12px_#4ade80] animate-pulse' : 'bg-red-400 shadow-[0_0_12px_#f87171]'"></span>
          <span :class="store.isConnected ? 'text-green-600' : 'text-red-500'">
            {{ store.isConnected ? 'Engine_Ready' : 'Offline' }}
          </span>
        </div>
      </div>
    </header>

    <!-- Main content area -->
    <main class="flex-1 flex overflow-hidden relative p-4 gap-4">
      <!-- Background Ambient Glows -->
      <div class="absolute inset-0 pointer-events-none opacity-40 overflow-hidden">
        <div
          class="absolute top-[-20%] left-[-10%] w-[60%] h-[60%] bg-accent-cyan rounded-full blur-[150px] animate-pulse-slow">
        </div>
        <div
          class="absolute bottom-[-20%] right-[-10%] w-[60%] h-[60%] bg-accent-purple rounded-full blur-[150px] animate-pulse-slow"
          style="animation-delay: 1s"></div>
        <div
          class="absolute top-[30%] right-[10%] w-[30%] h-[30%] bg-accent-pink rounded-full blur-[120px] animate-pulse-slow"
          style="animation-delay: 2s"></div>
      </div>

      <!-- Left sidebar: Repo explorer -->
      <aside
        class="w-80 flex-shrink-0 hidden lg:block glass-panel rounded-3xl overflow-hidden shadow-2xl animate-slide-up border-none">
        <RepoExplorer />
      </aside>

      <!-- Center content -->
      <div class="flex-1 flex flex-col overflow-hidden rounded-3xl glass-panel shadow-2xl border-none animate-slide-up"
        style="animation-delay: 0.1s">
        <div v-show="store.activeTab === 'chat'" class="flex-1 overflow-hidden">
          <ChatPanel />
        </div>
        <div v-show="store.activeTab === 'editor'" class="flex-1 overflow-hidden relative">
          <CodeEditor />
        </div>
        <div v-show="store.activeTab === 'tools'" class="flex-1 overflow-hidden">
          <ToolOutput />
        </div>
      </div>
    </main>

    <!-- Status bar -->
    <footer
      class="px-8 py-2 bg-white/40 backdrop-blur-xl border-t border-white/40 flex items-center justify-between text-[8px] font-display font-black text-slate-400 uppercase tracking-widest flex-shrink-0 z-50">
      <div class="flex items-center gap-4">
        <span class="opacity-40">System_Protocol_V4</span>
        <span class="w-px h-3 bg-slate-300"></span>
        <span class="text-accent-cyan">Response_Opt: 24ms</span>
      </div>
      <div class="flex items-center gap-4">
        <span v-if="store.isStreaming" class="text-accent-pink animate-pulse flex items-center gap-2">
          <span class="w-1.5 h-1.5 rounded-full bg-accent-pink shadow-[0_0_10px_#f472b6]"></span>
          Cognitive_Processing_Active
        </span>
        <span v-else class="flex items-center gap-2">
          <span class="w-1.5 h-1.5 rounded-full bg-accent-green"></span>
          Ready_For_Input
        </span>
      </div>
    </footer>
  </div>
</template>

<script setup>
import { onMounted } from 'vue'
import { useCopilotStore } from './stores/copilotStore.js'
import ChatPanel from './components/ChatPanel.vue'
import CodeEditor from './components/CodeEditor.vue'
import RepoExplorer from './components/RepoExplorer.vue'
import ToolOutput from './components/ToolOutput.vue'

const store = useCopilotStore()

const modelName = 'qwen3-coder:latest @ Ollama'

const tabs = [
  { id: 'chat', icon: '💬', label: 'Chat' },
  { id: 'editor', icon: '⌨️', label: 'Editor' },
  { id: 'tools', icon: '🔧', label: 'Tools' },
]

onMounted(async () => {
  await store.checkConnection()
  setInterval(() => store.checkConnection(), 120000)
  store.loadTools()
  store.loadRepoFiles()
})
</script>
