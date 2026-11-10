<script setup lang="ts">
import SettingsDrawerGlobalAccordion from './SettingsDrawerGlobalAccordion.vue'
import SettingsField from './SettingsField.vue'
import SettingsSwitch from './SettingsSwitch.vue'
import type { Settings } from '../../types/models'

export interface TtsCacheStats {
  usedBytes: number
  limitBytes: number
  lastPatrolAt: string
  prunedFiles: number
  lastError?: { code?: string; message?: string } | string | null
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
</script>

<template>
  <SettingsDrawerGlobalAccordion v-model:open="open" title="文字转语音（TTS）">
    <div class="settings-group">
      <SettingsSwitch
        :model-value="!!draft.ttsEnabled"
        label="启用文字转语音"
        hint="需在 API 预设中至少配置一个 TTS 服务预设。"
        @update:model-value="emit('toggle-enabled')"
      />

      <SettingsField v-if="draft.ttsEnabled" label="缓存上限（MB）">
        <input
          v-model.number="draft.ttsAudioCacheLimitMb"
          type="number"
          min="10"
          max="10000"
          class="input w-full"
        />
        <div class="h-2 w-full overflow-hidden rounded-full bg-[var(--color-track)]">
          <div
            class="h-full rounded-full transition-[width] duration-[var(--motion-duration-expand)] ease-out"
            :class="cachePercent > 90 ? 'bg-[var(--color-error)]' : cachePercent > 70 ? 'bg-[var(--color-warning)]' : 'bg-brand'"
            :style="{ width: (cacheStats ? cachePercent : 0) + '%' }"
          />
        </div>
        <div class="settings-hint flex items-center justify-between">
          <span>{{
            cacheStats
              ? `${formatBytes(cacheStats.usedBytes)} / ${formatBytes(cacheStats.limitBytes)}`
              : '正在读取缓存占用...'
          }}</span>
          <button
            type="button"
            class="btn btn-xs btn-secondary"
            :disabled="!cacheStats"
            @click="emit('clear-cache')"
          >
            清空缓存
          </button>
        </div>
        <p
          v-if="cacheStats?.lastError"
          class="text-xs text-[var(--color-error-text)]"
        >
          缓存巡检失败：{{
            typeof cacheStats.lastError === 'string'
              ? cacheStats.lastError
              : (cacheStats.lastError.message || cacheStats.lastError.code || '未知错误')
          }}
        </p>
      </SettingsField>
    </div>
  </SettingsDrawerGlobalAccordion>
</template>
