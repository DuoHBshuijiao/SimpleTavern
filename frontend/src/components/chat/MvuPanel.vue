<template>
  <Teleport to="body">
    <aside
      class="fixed right-4 top-4 bottom-4 theme-panel-bg backdrop-blur-xl rounded-2xl shadow-2xl transition-all duration-300 overflow-hidden flex flex-col z-[110]"
      :class="isOpen
        ? 'translate-x-0 w-[360px] opacity-100'
        : 'translate-x-[calc(100%+20px)] w-[360px] opacity-0 pointer-events-none'"
    >
      <!-- 标题栏 -->
      <header class="flex items-center justify-between px-5 py-4 border-b border-[var(--color-border-subtle)] shrink-0">
        <div class="flex items-center gap-2 min-w-0">
          <h2 class="text-sm font-semibold text-[var(--color-text)] truncate">MVU 工作日志</h2>
          <span
            v-if="running"
            class="inline-flex items-center justify-center w-2 h-2 rounded-full bg-[var(--color-brand)] animate-pulse"
          />
        </div>
        <button
          type="button"
          class="inline-flex items-center justify-center w-7 h-7 rounded-lg text-[var(--color-text-muted)] hover:text-[var(--color-text)] hover:bg-[var(--color-surface-hover)] transition-colors shrink-0"
          title="关闭"
          @click="$emit('update:isOpen', false)"
        >
          <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>
      </header>

      <!-- 日志列表 -->
      <div ref="logListRef" class="flex-1 overflow-y-auto px-5 py-3 space-y-2">
        <div v-if="logs.length === 0" class="text-xs text-[var(--color-text-muted)] py-6 text-center">
          暂无工作日志
        </div>
        <div
          v-for="entry in visibleLogs"
          :key="entry.id"
          class="flex items-start gap-3 py-2 border-b border-[var(--color-border-subtle)] last:border-b-0"
        >
          <span class="text-[11px] text-[var(--color-text-muted)] w-[52px] shrink-0 font-mono leading-5 pt-px">{{
            formatTime(entry.timestamp)
          }}</span>
          <span
            class="shrink-0 text-[10px] px-1.5 py-0.5 rounded-full font-medium leading-4 mt-px"
            :class="badgeClass(entry.eventType)"
          >{{ badgeLabel(entry.eventType) }}</span>
          <span class="text-xs text-[var(--color-text-secondary)] leading-5 min-w-0 break-words">{{ entry.summary }}</span>
        </div>
      </div>
    </aside>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, ref, watch, nextTick } from 'vue'
import type { MvuWorkLogEntry } from '../../types/models'

const props = withDefaults(defineProps<{
  isOpen: boolean
  logs: MvuWorkLogEntry[]
  maxVisible?: number
  running?: boolean
}>(), {
  maxVisible: 100,
  running: false,
})

defineEmits<{
  'update:isOpen': [value: boolean]
}>()

const logListRef = ref<HTMLElement | null>(null)

const visibleLogs = computed(() => {
  const recent = props.logs.slice(-props.maxVisible)
  return recent
})

function formatTime(iso: string): string {
  if (!iso) return ''
  try {
    const d = new Date(iso)
    const hh = String(d.getHours()).padStart(2, '0')
    const mm = String(d.getMinutes()).padStart(2, '0')
    const ss = String(d.getSeconds()).padStart(2, '0')
    return `${hh}:${mm}:${ss}`
  } catch {
    return ''
  }
}

function badgeLabel(et: MvuWorkLogEntry['eventType']): string {
  const map: Record<string, string> = {
    triggered: '触发',
    planning: '规划',
    tool_call: '调用',
    commit: '提交',
    error: '错误',
  }
  return map[et] ?? et
}

function badgeClass(et: MvuWorkLogEntry['eventType']): string {
  const map: Record<string, string> = {
    triggered: 'bg-blue-500/20 text-blue-400',
    planning: 'bg-yellow-500/20 text-yellow-400',
    tool_call: 'bg-green-500/20 text-green-400',
    commit:   'bg-purple-500/20 text-purple-400',
    error:    'bg-red-500/20 text-red-400',
  }
  return map[et] ?? 'bg-[var(--color-surface-muted)] text-[var(--color-text-muted)]'
}

watch(() => props.logs.length, async () => {
  await nextTick()
  if (logListRef.value) {
    logListRef.value.scrollTop = logListRef.value.scrollHeight
  }
})
</script>
