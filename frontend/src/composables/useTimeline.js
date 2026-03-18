import { computed } from 'vue'

export function useTimeline(chatStore) {
  // Read the latest timeline event to derive current status label + style
  const statusStyle = computed(() => {
    const events = chatStore.timelineEvents
    const last = events.length ? events[events.length - 1] : null
    const type = last?.type || 'thinking'

    if (type === 'tool_start') {
      return {
        icon: '🔧', spin: false, dots: true,
        label: `ACT → Calling ${last?.data?.count > 1 ? last.data.count + ' tools' : 'tool'}…`,
        cls: 'bg-amber-500/10 border-amber-500/30 text-amber-400 animate-pulse-glow-orange',
      }
    }
    if (type === 'tool_result') {
      const toolName = last?.data?.tool || 'tool'
      const status = last?.data?.status
      const ok = status === 'success'
      const needsConf = status === 'requires_confirmation'

      if (needsConf) {
        return {
          icon: '🛡️', spin: false, dots: false,
          label: `${toolName} → Requires Approval`,
          cls: 'bg-accent-orange/20 border-accent-orange/40 text-accent-orange shadow-[0_0_15px_-5px_theme(colors.accent.orange)] animate-pulse-glow-orange',
          isActionable: true,
          event: last
        }
      }

      return {
        icon: ok ? '✅' : '⚠️', spin: false, dots: false,
        label: `VERIFY → ${toolName} ${ok ? 'done' : 'error'}`,
        cls: ok
          ? 'bg-green-500/10 border-green-500/30 text-green-400 animate-pulse-glow'
          : 'bg-red-500/10 border-red-500/30 text-red-400',
      }
    }
    if (type === 'followup') {
      return {
        icon: '📝', spin: false, dots: true,
        label: 'ACT → Generating answer…',
        cls: 'bg-accent-purple/10 border-accent-purple/30 text-accent-purple',
      }
    }
    if (type === 'debug_analysis') {
      return {
        icon: '🐛', spin: false, dots: true,
        label: 'VERIFY → Analyzing error…',
        cls: 'bg-red-500/10 border-red-500/30 text-red-400',
      }
    }
    if (type === 'granular') {
      const label = last?.data?.label || ''
      const isPlan = label.toLowerCase().includes('plan')
      const isVer = label.toLowerCase().includes('verify')

      return {
        icon: isPlan ? '🎯' : (isVer ? '🔍' : '⚙️'),
        spin: !isPlan && !isVer,
        dots: true,
        label: label.toUpperCase(),
        cls: isPlan
          ? 'bg-accent-purple/10 border-accent-purple/30 text-accent-purple animate-pulse-glow-purple'
          : (isVer ? 'bg-green-500/10 border-green-500/30 text-green-400 animate-pulse-glow' : 'bg-accent-cyan/10 border-accent-cyan/30 text-accent-cyan'),
      }
    }
    // Default: LLM is generating
    return {
      icon: '⚡', spin: false, dots: true,
      label: 'PLAN → Brainstorming…',
      cls: 'bg-accent-cyan/10 border-accent-cyan/30 text-accent-cyan animate-pulse-glow',
    }
  })

  return { statusStyle }
}
