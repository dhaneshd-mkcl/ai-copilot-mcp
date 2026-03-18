<template>
  <div class="flex flex-col h-full">
    <div class="panel-header">
      <span class="text-accent-orange">◈ MCP Tools</span>
      <div class="flex items-center gap-2">
        <span class="tag bg-accent-green/10 text-accent-green">{{ toolStore.safeTools.length }} safe</span>
        <span class="tag bg-red-900/20 text-red-400">{{ toolStore.dangerousTools.length }} dangerous</span>
      </div>
    </div>

    <div class="flex-1 flex overflow-hidden">
      <!-- Tool list -->
      <div class="w-56 border-r border-border overflow-y-auto p-2 space-y-1 flex-shrink-0">
        <div class="text-xs text-slate-600 px-2 py-1 uppercase tracking-wider">Available</div>
        <button v-for="tool in toolStore.tools" :key="tool.name" @click="selectTool(tool)" :class="['w-full text-left px-2 py-2 rounded text-xs font-mono transition-all',
          selectedTool?.name === tool.name
            ? 'bg-accent-orange/10 text-accent-orange border border-accent-orange/30'
            : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100']">
          <div class="flex items-center gap-1.5">
            <span class="w-1.5 h-1.5 rounded-full flex-shrink-0"
              :class="tool.category === 'safe' ? 'bg-accent-green' : 'bg-red-400'" />
            <span class="font-medium truncate">{{ tool.name }}</span>
          </div>
          <div class="text-slate-600 truncate mt-0.5 text-xs pl-3">{{ tool.description?.slice(0, 40) }}...</div>
        </button>
      </div>

      <!-- Right panel -->
      <div class="flex-1 flex flex-col overflow-hidden">
        <!-- Tool form -->
        <div v-if="selectedTool" class="p-4 border-b border-border">
          <div class="flex items-center gap-2 mb-1">
            <div class="text-sm font-mono text-accent-orange">{{ selectedTool.name }}</div>
            <span class="text-xs px-1.5 py-0.5 rounded font-mono" :class="selectedTool.category === 'safe'
              ? 'bg-accent-green/10 text-accent-green'
              : 'bg-red-900/20 text-red-400'">
              {{ selectedTool.category }}
            </span>
          </div>
          <div class="text-xs text-slate-500 mb-3">{{ selectedTool.description }}</div>

          <!-- Warning for dangerous tools -->
          <div v-if="selectedTool.category === 'dangerous'"
            class="mb-3 px-3 py-2 rounded-lg border border-red-200 bg-red-50 text-xs text-red-600">
            WARNING: This tool can modify files or run code. Confirm before executing.
          </div>

          <div v-for="(spec, key) in selectedTool.parameters" :key="key" class="mb-2">
            <label class="text-xs text-slate-500 font-mono block mb-1">
              {{ key }}
              <span v-if="spec.type" class="text-slate-700 ml-1">({{ spec.type }})</span>
            </label>
            <input v-model="paramValues[key]" :placeholder="spec.description || key"
              class="input-field text-xs py-1.5" />
          </div>

          <button @click="runSelectedTool" :disabled="isRunning"
            class="mt-2 w-full text-xs py-2 rounded-lg font-mono transition-all" :class="selectedTool.category === 'dangerous'
              ? 'bg-red-600 text-white border border-red-700 hover:bg-red-700 disabled:opacity-50 shadow-lg'
              : 'btn-primary'">
            {{ isRunning ? 'Running...' : selectedTool.category === 'dangerous' ? 'Execute (Dangerous)' : 'Execute Tool'
            }}
          </button>
        </div>
        <div v-else class="p-4 text-center text-slate-600 text-sm">
          ← Select a tool to configure and run
        </div>

        <!-- Output history -->
        <div class="flex-1 overflow-y-auto p-3 space-y-3">
          <div class="flex items-center justify-between px-1">
            <span class="text-xs text-slate-600 uppercase tracking-wider">Output Log</span>
            <button v-if="toolStore.toolOutput.length" @click="toolStore.clearOutput()"
              class="text-xs text-slate-600 hover:text-slate-400">
              Clear
            </button>
          </div>

          <div v-if="toolStore.toolOutput.length === 0" class="text-center py-4 text-slate-700 text-xs">
            No tool executions yet
          </div>

          <div v-for="(out, i) in toolStore.toolOutput" :key="i"
            class="rounded-lg border overflow-hidden text-xs font-mono"
            :class="out.error ? 'border-red-900/50' : out.status === 'needs_confirmation' ? 'border-accent-orange/40' : 'border-border'">
            <div class="flex items-center justify-between px-3 py-1.5"
              :class="out.error ? 'bg-red-50 text-red-600' : out.status === 'needs_confirmation' ? 'bg-accent-orange/10 text-accent-orange' : 'bg-slate-50 text-slate-800'">
              <span>{{ out.tool }}</span>
              <span class="text-slate-600">{{ formatTime(out.timestamp) }}</span>
            </div>

            <!-- Confirmation prompt -->
            <div v-if="out.status === 'needs_confirmation'" class="p-3 space-y-2">
              <p class="text-accent-orange text-xs">{{ out.message }}</p>
              <button @click="confirmRun(out)"
                class="text-xs px-3 py-1 rounded border border-red-800 bg-red-900/30 text-red-300 hover:bg-red-900/50">
                Confirm & Run
              </button>
            </div>

            <pre v-else class="p-3 text-slate-600 overflow-x-auto text-xs max-h-40 bg-white">{{
              out.error ? out.error : JSON.stringify(out.result, null, 2)
            }}</pre>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useToolStore } from '../stores/toolStore.js'

const toolStore = useToolStore()
const selectedTool = ref(null)
const paramValues = reactive({})
const isRunning = ref(false)

function selectTool(tool) {
  selectedTool.value = tool
  Object.keys(paramValues).forEach(k => delete paramValues[k])
  for (const [key, spec] of Object.entries(tool.parameters || {})) {
    paramValues[key] = spec.default ?? ''
  }
}

async function runSelectedTool() {
  if (!selectedTool.value) return
  isRunning.value = true
  const params = {}
  for (const [k, v] of Object.entries(paramValues)) {
    params[k] = v === '' ? undefined : v
  }
  const force = selectedTool.value.category === 'dangerous'
  await toolStore.runTool(selectedTool.value.name, params, force)
  isRunning.value = false
}

async function confirmRun(out) {
  out.status = 'running'
  await toolStore.runToolForced(out.tool, out.params || {})
}

function formatTime(ts) {
  return new Date(ts).toLocaleTimeString()
}

onMounted(() => toolStore.loadTools())
</script>
