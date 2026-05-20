<template>
  <Teleport to="body">
    <aside
      class="fixed right-4 top-4 bottom-4 theme-panel-bg backdrop-blur-xl backdrop-saturate-[1.8] border border-[var(--color-border)] shadow-glass-panel rounded-2xl transition-all duration-300 overflow-hidden flex flex-col z-[110] pointer-events-auto"
      :class="isOpen
        ? 'translate-x-0 w-[min(360px,calc(100vw-2rem))] opacity-100'
        : 'translate-x-[calc(100%+20px)] w-[min(360px,calc(100vw-2rem))] opacity-0 pointer-events-none'"
      style="contain: content; will-change: transform, opacity;"
    >
      <!-- 标题栏 -->
      <header class="flex items-center justify-between px-4 py-2 border-b border-white/5 shrink-0 bg-white/5 backdrop-blur-md">
        <div class="flex min-w-0 flex-1 items-center gap-2">
          <div
            role="button"
            tabindex="0"
            class="min-w-0 cursor-pointer rounded-lg px-2 py-1 -mx-1 -my-0.5 transition-colors hover:bg-[var(--color-surface-hover)]"
            aria-label="切换到聊天助手"
            @click="$emit('switch-to-assistant')"
            @keydown.enter.prevent="$emit('switch-to-assistant')"
            @keydown.space.prevent="$emit('switch-to-assistant')"
          >
            <span class="text-xs font-bold text-gray-400 uppercase tracking-widest flex items-center gap-2 flex-wrap min-w-0">
              <span class="w-2 h-2 rounded-full bg-[#b76e79] shrink-0" :class="{ 'animate-pulse': running }" />
              <span class="truncate">MVU 工作日志</span>
            </span>
          </div>
        </div>
        <button
          type="button"
          class="inline-flex items-center justify-center w-7 h-7 rounded-lg text-[var(--color-text-muted)] hover:text-[var(--color-text)] hover:bg-[var(--color-surface-hover)] transition-colors shrink-0"
          aria-label="关闭"
          @click="$emit('update:isOpen', false)"
        >
          <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>
      </header>

      <div
        v-if="hasKnowledgeGraph"
        class="shrink-0 px-4 py-2 border-b border-[var(--color-border-subtle)]"
      >
        <button
          type="button"
          class="w-full text-left text-xs text-[var(--color-brand)] hover:underline"
          @click="$emit('open-knowledge-graph')"
        >
          查看知识图谱
        </button>
      </div>

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

      <!-- MVU 模型 -->
      <div class="shrink-0 space-y-1 px-4 py-2 border-t border-[var(--color-border-subtle)]">
        <ModernSelect
          :model-value="mvuModel ?? ''"
          :options="modelOptions"
          placement="top"
          placeholder="留空则使用默认模型名称与候选回退"
          class="!text-[11px] !min-w-0 w-full"
          dropdown-width="360"
          searchable
          allow-create
          @select="(v: any) => $emit('select-mvu-model', v)"
        />
        <p
          v-if="resolvedMvuModel && !(mvuModel || '').trim()"
          class="text-[10px] leading-snug text-[var(--color-text-muted)]"
        >
          当前生效（回退）：<span class="font-mono text-[var(--color-text-secondary)]">{{ resolvedMvuModel }}</span>
        </p>
      </div>
    </aside>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, ref, watch, nextTick } from 'vue'
import type { MvuWorkLogEntry } from '../../types/models'
import ModernSelect from '../ModernSelect.vue'

interface ModelOption {
  label: string
  value: string
  presetId?: string | null
}
interface ModelOptionGroup {
  label: string
  options: ModelOption[]
}

interface Props {
  isOpen: boolean
  logs: MvuWorkLogEntry[]
  hasKnowledgeGraph?: boolean
  maxVisible?: number
  running?: boolean
  /** 全局 settings.mvuModel（与设置抽屉同源） */
  mvuModel?: string | null
  modelOptions?: (ModelOption | ModelOptionGroup)[]
  /** 未单独指定 MVU 模型时的回退生效名（仅作提示） */
  resolvedMvuModel?: string | null
}

const props = withDefaults(defineProps<Props>(), {
  hasKnowledgeGraph: false,
  maxVisible: 100,
  running: false,
  mvuModel: null,
  modelOptions: () => [],
  resolvedMvuModel: null,
})

defineEmits<{
  'update:isOpen': [value: boolean]
  'select-mvu-model': [value: { value: string; presetId?: string | null }]
  'switch-to-assistant': []
  'open-knowledge-graph': []
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
