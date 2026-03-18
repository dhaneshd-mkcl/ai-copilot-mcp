<template>
  <div class="flex h-screen bg-terminal-bg text-terminal-text font-sans overflow-hidden">
    <!-- Sidebar -->
    <aside
      class="w-14 flex flex-col items-center py-4 gap-3 border-r border-terminal-border bg-terminal-surface shrink-0">
      <div
        class="w-9 h-9 bg-terminal-accent rounded-xl flex items-center justify-center text-terminal-bg font-bold text-sm font-mono mb-2">
        ⚡</div>

      <button v-for="tab in tabs" :key="tab.id" @click="store.activeTab = tab.id" :title="tab.label"
        class="w-9 h-9 rounded-xl flex items-center justify-center text-lg transition-all" :class="store.activeTab === tab.id
          ? 'bg-terminal-accent/15 text-terminal-accent ring-1 ring-terminal-accent/30'
          : 'text-terminal-muted hover:text-terminal-text hover:bg-terminal-surface'">{{ tab.icon }}</button>

      <div class="flex-1" />

      <!-- Connection status -->
      <div :title="store.isConnected ? 'Backend connected' : 'Backend disconnected'"
        class="w-3 h-3 rounded-full transition-colors"
        :class="store.isConnected ? 'bg-terminal-green animate-pulse' : 'bg-terminal-red'" />
    </aside>

    <!-- Main content -->
    <div class="flex flex-1 min-w-0 flex-col">
      <!-- Top bar -->
      <header class="flex items-center gap-3 px-4 h-11 border-b border-terminal-border bg-terminal-surface shrink-0">
        <span class="text-sm font-semibold font-mono text-terminal-text">
          {{ currentTab?.label }}
        </span>
        <div class="flex-1" />
        <div class="text-xs font-mono text-terminal-muted flex items-center gap-2">
          <span class="text-terminal-accent">{{ config.model }}</span>
          <span>·</span>
          <span>{{ config.backend }}</span>
        </div>
        <button v-if="store.activeTab === 'chat'" @click="store.clearMessages()"
          class="text-xs text-terminal-muted hover:text-terminal-red transition-colors font-mono">
          ✕ Clear
        </button>
      </header>

      <!-- Tab content -->
      <div class="flex-1 min-h-0 overflow-hidden">
        <ChatPanel v-show="store.activeTab === 'chat'" />
        <CodeEditor v-show="store.activeTab === 'editor'" />
        <RepoExplorer v-show="store.activeTab === 'repo'" />
        <ToolOutput v-show="store.activeTab === 'tools'" />
        <ToolTimeline v-show="store.activeTab === 'timeline'" />
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted } from 'vue'
import ChatPanel from '../components/ChatPanel.vue'
import CodeEditor from '../components/CodeEditor.vue'
import RepoExplorer from '../components/RepoExplorer.vue'
import ToolOutput from '../components/ToolOutput.vue'
import ToolTimeline from '../components/ToolTimeline.vue'
import { useCopilotStore } from '../stores/copilotStore.js'

const store = useCopilotStore()

const config = {
  model: import.meta.env.VITE_LLM_MODEL || 'qwen3-coder:latest',
  backend: 'ollama',
}

const tabs = [
  { id: 'chat', icon: '💬', label: 'Chat' },
  { id: 'editor', icon: '📝', label: 'Code Editor' },
  { id: 'repo', icon: '📁', label: 'Repository' },
  { id: 'tools', icon: '🔧', label: 'MCP Tools' },
  { id: 'timeline', icon: '⏱', label: 'Execution Timeline' },
]

const currentTab = computed(() => tabs.find(t => t.id === store.activeTab))

onMounted(() => {
  // Connection state is managed by App.vue to avoid duplicate heartbeat checks
})
</script>
