<script setup lang="ts">
import SettingsDrawerGlobalAccordion from './SettingsDrawerGlobalAccordion.vue'
import type { Settings } from '../../types/models'

export interface TtsCacheStats {
  usedBytes: number
  limitBytes: number
  lastPatrolAt: string
  prunedFiles: number
}

defineProps<{
  draft: Settings
  cacheStats: TtsCacheStats | null
  cachePercent: number
}>()

const open = defineModel<boolean>('open', { required: true })

const emit = defineEmits<{
  'toggle-enabled': []
  'clear-cache': []
}>()

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1048576).toFixed(1)} MB`
}

function onToggleTts() {
  emit('toggle-enabled')
}
</script>

<template>
  <SettingsDrawerGlobalAccordion v-model:open="open" title="文字转语音（TTS）">
    <div class="space-y-2">
      <label class="block text-sm font-medium text-[var(--color-text-secondary)]">启用文字转语音</label>
      <button
        type="button"
        class="group flex min-h-11 w-full cursor-pointer items-center gap-3 py-1 text-left"
        @click="onToggleTts"
      >
        <div
          class="relative h-6 w-11 shrink-0 rounded-full transition-colors duration-200 ease-out"
          :class="draft.ttsEnabled ? 'bg-brand' : 'bg-[var(--color-track)]'"
        >
          <div
            class="absolute left-1 top-1 h-4 w-4 rounded-full bg-[var(--color-on-brand)]"
            :style="{
              transform: draft.ttsEnabled ? 'translateX(1.25rem)' : 'translateX(0)',
              transition: 'transform 200ms ease-out',
            }"
          />
        </div>
        <span class="text-xs text-[var(--color-text-secondary)]">
          {{ draft.ttsEnabled ? '已开启：启用语音合成功能' : '已关闭' }}
        </span>
      </button>
    </div>

    <div v-if="draft.ttsEnabled" class="space-y-2">
      <label class="block text-sm font-medium text-[var(--color-text-secondary)]">缓存上限（MB）</label>
      <input
        v-model.number="draft.ttsAudioCacheLimitMb"
        type="number"
        min="10"
        max="10000"
        class="input w-full"
      />
      <div class="space-y-1">
        <div class="h-2 w-full overflow-hidden rounded-full bg-[var(--color-track)]">
          <div
            class="h-full rounded-full transition-[width] duration-[var(--motion-duration-expand)] ease-out"
            :class="cachePercent > 90 ? 'bg-[var(--color-error)]' : cachePercent > 70 ? 'bg-[var(--color-warning)]' : 'bg-brand'"
            :style="{ width: (cacheStats ? cachePercent : 0) + '%' }"
          />
        </div>
        <div class="flex items-center justify-between text-xs text-[var(--color-text-muted)]">
          <span>{{
            cacheStats
              ? `${formatBytes(cacheStats.usedBytes)} / ${formatBytes(cacheStats.limitBytes)}`
              : '正在读取缓存占用...'
          }}</span>
          <button
            type="button"
            class="rounded px-2 py-0.5 text-xs text-[var(--color-text-secondary)] transition-colors hover:bg-surface-hover"
            :disabled="!cacheStats"
            @click="emit('clear-cache')"
          >
            清空缓存
          </button>
        </div>
      </div>
    </div>

    <p class="text-xs text-[var(--color-text-muted)]">
      开启后可在聊天界面使用语音合成功能。需在 API 预设中至少配置一个 TTS 服务预设（MiniMax、GLM TTS、OpenRouter TTS、硅基流动等）。
    </p>
  </SettingsDrawerGlobalAccordion>
</template>
