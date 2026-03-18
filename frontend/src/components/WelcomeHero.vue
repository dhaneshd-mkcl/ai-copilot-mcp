<template>
  <div class="flex flex-col items-center justify-start h-full text-center pt-24 pb-12 animate-slide-up px-4 max-w-4xl mx-auto">
    <!-- Hero Section -->
    <div class="mb-16">
      <div class="relative inline-block mb-10">
        <div class="absolute -inset-4 bg-gradient-to-tr from-blue-600 to-indigo-600 rounded-[42px] blur-2xl opacity-20 animate-pulse"></div>
        <div class="relative w-24 h-24 rounded-[36px] bg-gradient-to-br from-[#3b82f6] to-[#4f46e5] flex items-center justify-center text-5xl shadow-2xl border border-white/40 animate-float">
          ⚡
        </div>
      </div>
      <h2 class="font-display text-4xl font-black text-slate-900 mb-4 tracking-tight">Titan MKCL AI</h2>
      <p class="text-slate-500 text-base max-w-md mx-auto font-medium leading-relaxed opacity-80">
        Professional autonomous coding engine for <span class="text-blue-600 font-bold">architectural precision</span> and industrial-scale development.
      </p>
    </div>

    <!-- Card Grid -->
    <div class="grid grid-cols-1 md:grid-cols-3 gap-6 w-full">
      <button v-for="ex in examples" :key="ex.text" @click="$emit('select', ex.text)"
        class="group p-6 rounded-3xl border border-slate-200 bg-white/70 backdrop-blur-xl hover:border-blue-400 hover:bg-white hover:shadow-2xl hover:shadow-blue-500/10 transition-all duration-500 transform hover:-translate-y-2 text-left relative overflow-hidden">
        <div class="absolute top-0 right-0 p-4 opacity-5 group-hover:opacity-10 transition-opacity">
          <span class="text-6xl">{{ ex.icon }}</span>
        </div>
        <div class="w-12 h-12 rounded-2xl bg-slate-50 flex items-center justify-center text-2xl mb-6 group-hover:bg-blue-50 group-hover:scale-110 transition-all duration-500 border border-slate-100 group-hover:border-blue-100">
          {{ ex.icon }}
        </div>
        <h3 class="text-[14px] font-black text-slate-900 mb-2 uppercase tracking-tight">
          {{ ex.text }}
        </h3>
        <p class="text-[11px] text-slate-500 font-bold uppercase tracking-[0.1em] flex items-center gap-2">
          Try this <span class="group-hover:translate-x-1 transition-transform">→</span>
        </p>
      </button>
    </div>
  </div>
</template>

<script setup>
const examples = [
  { icon: '🔧', text: 'Fix this Python TypeError' },
  { icon: '✨', text: 'Create a FastAPI REST endpoint' },
  { icon: '📖', text: 'Explain this async code' },
  { icon: '🧪', text: 'Generate unit tests for my class' },
  { icon: '♻️', text: 'Refactor this long function' },
  { icon: '🔍', text: 'Find security issues in code' },
]

defineEmits(['select'])
</script>
