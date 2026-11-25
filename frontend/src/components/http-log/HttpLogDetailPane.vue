<script setup lang="ts">
/**
 * HTTP 日志详情区：顶栏（宽屏单行：模式按钮与 method/url 同排；stackDetailHeader 时两行）+ 正文 + 底栏
 */
import type { HttpLogDetail } from '../../api/httpLog'
import CodeViewer from '../common/CodeViewer.vue'
import ThemedRadioTags from '../ThemedRadioTags.vue'
import HttpRecordPreview from './HttpRecordPreview.vue'

defineProps<{
  selectedId: string | null
  detail: HttpLogDetail | null
  detailLoading: boolean
  detailError: string
  viewMode: 'pretty' | 'raw'
  rawSection: 'request' | 'response'
  rawText: string
  /** CodeViewer 等区域最大高度（宽屏可用 72vh，窄屏嵌入手风琴时略小） */
  contentMaxHeightClass?: string
  emptyHint?: string
  /** 为 true 时顶栏两行堆叠（窄屏手风琴）；宽屏用 false 使模式按钮与 URL 同一行 */
  stackDetailHeader?: boolean
}>()

const emit = defineEmits<{
  'update:viewMode': [v: 'pretty' | 'raw']
  'update:rawSection': [v: 'request' | 'response']
}>()

const contentMaxHeightClassDefault = 'max-h-[72vh]'
const viewModeOptions: { value: 'pretty' | 'raw'; label: string }[] = [
  { value: 'pretty', label: 'Pretty' },
  { value: 'raw', label: 'Raw JSON' },
]
const rawSectionOptions: { value: 'request' | 'response'; label: string }[] = [
  { value: 'request', label: 'Request' },
  { value: 'response', label: 'Response' },
]
</script>

<template>
  <div class="flex min-h-0 min-w-0 flex-1 flex-col">
    <div
      class="flex shrink-0 border-b border-[var(--color-border-subtle)] bg-[var(--color-surface-muted)]/20 px-3 py-2"
      :class="stackDetailHeader ? 'flex-col gap-2' : 'flex-row flex-wrap items-center gap-x-3 gap-y-1'"
    >
      <div class="flex flex-wrap items-center gap-2" :class="stackDetailHeader ? '' : 'shrink-0'">
        <ThemedRadioTags
          :model-value="viewMode"
          :options="viewModeOptions"
          aria-label="日志显示格式"
          @update:model-value="emit('update:viewMode', $event)"
        />
        <ThemedRadioTags
          v-if="viewMode === 'raw'"
          :model-value="rawSection"
          :options="rawSectionOptions"
          aria-label="日志原始数据"
          @update:model-value="emit('update:rawSection', $event)"
        />
      </div>
      <div
        v-if="detail"
        class="flex min-w-0 flex-wrap gap-x-2 gap-y-0.5 text-2xs text-[var(--color-text-muted)]"
        :class="stackDetailHeader ? 'items-baseline' : 'min-w-[120px] flex-1 items-center'"
      >
        <span class="shrink-0 font-mono">{{ detail.method }}</span>
        <span class="min-w-0 max-w-full break-all font-mono">{{ detail.url }}</span>
      </div>
    </div>

    <div class="min-h-0 flex-1 overflow-auto px-3 py-3">
      <div
        v-if="!selectedId"
        class="flex h-full min-h-[120px] items-center justify-center text-xs text-[var(--color-text-muted)]"
      >
        {{ emptyHint ?? '请从左侧选择一条记录查看' }}
      </div>
      <div
        v-else-if="detailLoading"
        class="flex h-full min-h-[120px] items-center justify-center text-xs text-[var(--color-text-muted)]"
      >
        加载中…
      </div>
      <div v-else-if="detailError" class="text-xs text-rose-300">{{ detailError }}</div>
      <template v-else-if="detail">
        <HttpRecordPreview v-if="viewMode === 'pretty'" :record="detail" />
        <CodeViewer
          v-else
          :model-value="rawText"
          language="json"
          :fold-level="2"
          :max-height-class="contentMaxHeightClass ?? contentMaxHeightClassDefault"
        />
      </template>
    </div>

    <div
      class="shrink-0 border-t border-[var(--color-border-subtle)] bg-[var(--color-surface-muted)]/20 px-3 py-1.5 text-center text-2xs text-[var(--color-text-muted)]"
    >
      显示最近 30 分钟的请求。
    </div>
  </div>
</template>
