<template>
  <div class="flex flex-col h-full">
    <div class="panel-header">
      <span class="text-accent-purple">◈ Execution Timeline</span>
      <button @click="chatStore.timelineEvents.splice(0)" class="btn-ghost text-xs py-0 px-1.5">
        Clear
      </button>
    </div>

    <div class="flex-1 overflow-y-auto p-3 space-y-2">
      <div v-if="chatStore.timelineEvents.length === 0"
        class="flex flex-col items-center justify-center h-full text-center py-8">
        <div class="text-3xl mb-3 opacity-30">⏱</div>
        <p class="text-slate-400 text-xs">No events yet.</p>
        <p class="text-slate-500 text-xs mt-1">Send a message to see the execution flow.</p>
      </div>

      <TransitionGroup name="timeline">
        <div v-for="event in reversed" :key="event.id" class="flex gap-3 items-start">
          <!-- Icon column -->
          <div class="flex flex-col items-center flex-shrink-0 mt-0.5">
            <div
              class="w-7 h-7 rounded-full flex items-center justify-center text-sm border transition-all duration-500"
              :class="[iconClass(event), event.status === 'running' ? 'animate-spin-slow' : '']">
              {{ icon(event) }}
            </div>
          </div>

          <!-- Content -->
          <div
            class="flex-1 min-w-0 pb-3 border-b border-border/40 relative group overflow-hidden rounded-r-lg hover:bg-slate-50/50 transition-colors">
            <!-- Shimmer effect for running items -->
            <div v-if="event.status === 'running'"
              class="absolute inset-0 shimmer-effect opacity-30 pointer-events-none"></div>
            <div class="flex items-center justify-between gap-2">
              <span
                class="text-[11px] font-bold uppercase tracking-widest px-2 py-0.5 rounded shadow-sm border border-current transition-all duration-300 transform group-hover:scale-105"
                :class="labelClass(event)">
                {{ label(event) }}
              </span>
              <span class="text-[10px] text-slate-500 flex-shrink-0 font-mono">
                {{ formatTime(event.timestamp) }}
              </span>
            </div>

            <!-- Extra detail per event type -->
            <div class="mt-2 text-xs text-slate-500 font-mono pl-1 border-l-2 border-slate-200">
              <template v-if="event.type === 'tool_start'">
                <div class="text-[13px] font-black text-slate-800 mb-1">PROMPT ANALYSIS</div>
                Detected {{ event.data.count }} tool call{{ event.data.count !== 1 ? 's' : '' }}
              </template>
              <template v-else-if="event.type === 'tool_result'">
                <div class="text-[14px] font-black text-accent-purple mb-1 uppercase tracking-tight">{{ event.data.tool
                  }}</div>
                <span
                  :class="event.data.status === 'success' ? 'text-accent-green font-bold' : 'text-red-400 font-bold'">
                  STATUS: {{ event.data.status.toUpperCase() }}
                </span>
              </template>
              <template v-else-if="event.type === 'user_message'">
                <div class="text-[13px] font-black text-accent-cyan mb-1">INCOMING REQUEST</div>
                <span class="truncate block max-w-xs opacity-70">{{ event.data.message }}</span>
              </template>
              <template v-else-if="event.type === 'debug_analysis'">
                <div class="text-[13px] font-black text-yellow-600 mb-1">DEBUG DIAGNOSIS</div>
                Error type: {{ event.data.data?.error_type || 'unknown' }}
              </template>
              <template v-else-if="event.type === 'discovery'">
                <div class="text-[15px] font-black text-accent-cyan animate-pulse">{{ event.data.section.toUpperCase()
                  }}</div>
                <div
                  class="italic opacity-90 mt-1 line-clamp-3 bg-accent-cyan/5 p-2 rounded border-l-4 border-accent-cyan shadow-sm">
                  {{ event.data.content }}</div>
              </template>
            </div>

            <!-- Status badge and actions -->
            <div class="mt-2 flex flex-wrap items-center gap-2" v-if="event.status">
              <span
                class="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] uppercase font-bold tracking-tighter"
                :class="statusClass(event.status)">
                {{ statusLabel(event.status) }}
              </span>

              <button v-if="event.status === 'running'" @click="chatStore.stopStreaming()"
                class="px-2 py-0.5 rounded bg-red-900/40 text-red-400 border border-red-500/50 text-[10px] hover:bg-red-800/60 transition-colors uppercase">
                Cancel
              </button>

              <button v-if="event.status === 'needs_confirmation'" @click="chatStore.runToolManually(event)"
                class="px-2 py-0.5 rounded bg-accent-orange text-black font-bold text-[10px] hover:bg-orange-300 transition-colors uppercase">
                Execute
              </button>

              <button v-if="event.data?.diff" @click="event.showDiff = !event.showDiff"
                class="px-2 py-0.5 rounded bg-accent-cyan/10 text-accent-cyan border border-accent-cyan/30 text-[10px] hover:bg-accent-cyan/20 transition-colors uppercase">
                {{ event.showDiff ? 'Hide Diff' : 'View Diff' }}
              </button>
            </div>

            <!-- Diff Viewer -->
            <div v-if="event.data?.diff && event.showDiff"
              class="mt-2 rounded bg-slate-900 border border-border/60 overflow-hidden">
              <div
                class="bg-surface-2 px-2 py-1 border-b border-border/40 text-[10px] text-slate-400 flex justify-between items-center">
                <span>UNIFIED DIFF</span>
                <span class="font-mono">{{ event.data.path }}</span>
              </div>
              <pre class="p-2 text-[10px] overflow-x-auto font-mono leading-relaxed max-h-60 overflow-y-auto">
    <template v-for="(line, i) in event.data.diff.split('\n')" :key="i">
<div :class="line.startsWith('+') ? 'text-green-400 bg-green-900/20' : (line.startsWith('-') ? 'text-red-400 bg-red-900/20' : 'text-slate-500')">
{{ line }}
</div>
</template>
  </pre>
            </div>
          </div>
        </div>
      </TransitionGroup>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useChatStore } from '../stores/chatStore.js'

const chatStore = useChatStore()

const reversed = computed(() =>
  [...chatStore.timelineEvents].reverse()
)

function icon(event) {
  const map = {
    user_message: '💬',
    tool_start: '⚙️',
    tool_result: '✅',
    tool_followup_start: '🔄',
    debug_analysis: '🔍',
    discovery: '🌟',
    followup: '🔄'
  }
  return map[event.type] || '◆'
}

function iconClass(event) {
  const base = 'text-base'
  const map = {
    user_message: 'bg-accent-cyan/10 border-accent-cyan/30 text-accent-cyan',
    tool_start: 'bg-accent-orange/10 border-accent-orange/30 text-accent-orange',
    tool_result: 'bg-accent-green/10 border-accent-green/30 text-accent-green',
    tool_followup_start: 'bg-accent-purple/10 border-accent-purple/30 text-accent-purple',
    debug_analysis: 'bg-yellow-100 border-yellow-200 text-yellow-700',
    discovery: 'bg-accent-cyan/10 border-accent-cyan/30 text-accent-cyan',
    followup: 'bg-accent-purple/10 border-accent-purple/30 text-accent-purple'
  }
  return `${base} ${map[event.type] || 'bg-surface-2 border-border text-slate-400'}`
}

function label(event) {
  const map = {
    user_message: 'User Message',
    tool_start: 'Tools Detected',
    tool_result: 'Tool Executed',
    tool_followup_start: 'Follow-up Generation',
    debug_analysis: 'Error Analysis',
    discovery: 'Discovery Made',
    followup: 'Generating Answer'
  }
  return map[event.type] || event.type
}

function labelClass(event) {
  const map = {
    user_message: 'text-accent-cyan',
    tool_start: 'text-accent-orange',
    tool_result: 'text-accent-green',
    tool_followup_start: 'text-accent-purple',
    debug_analysis: 'text-yellow-400',
    discovery: 'text-accent-cyan font-bold',
    followup: 'text-accent-purple'
  }
  return map[event.type] || 'text-slate-400'
}

function statusClass(status) {
  const map = {
    running: 'bg-yellow-900/30 text-yellow-400',
    done: 'bg-accent-green/10 text-accent-green',
    error: 'bg-red-900/30 text-red-400',
    needs_confirmation: 'bg-accent-orange/10 text-accent-orange',
  }
  return map[status] || 'bg-surface-2 text-slate-500'
}

function statusLabel(status) {
  const map = {
    running: '⏳ running',
    done: '✓ done',
    error: '✗ error',
    needs_confirmation: '⚠ needs confirmation',
  }
  return map[status] || status
}

function formatTime(ts) {
  return new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}
</script>

<style scoped>
@keyframes slide-in {
  0% {
    opacity: 0;
    transform: translateX(-20px) scale(0.95);
  }

  100% {
    opacity: 1;
    transform: translateX(0) scale(1);
  }
}

.timeline-enter-active {
  animation: slide-in 0.4s cubic-bezier(0.34, 1.56, 0.64, 1);
}

.timeline-leave-active {
  transition: all 0.3s ease;
}

.timeline-leave-to {
  opacity: 0;
  transform: scale(0.9);
}

.animate-spin-slow {
  animation: spin 3s linear infinite;
}

@keyframes spin {
  from {
    transform: rotate(0deg);
  }

  to {
    transform: rotate(360deg);
  }
}

/* Shimmer effect for running state */
.shimmer-effect {
  background: linear-gradient(90deg,
      transparent,
      rgba(255, 255, 255, 0.2),
      transparent);
  background-size: 200% 100%;
  animation: shimmer 1.5s infinite;
}

@keyframes shimmer {
  0% {
    background-position: -200% 0;
  }

  100% {
    background-position: 200% 0;
  }
}
</style>
