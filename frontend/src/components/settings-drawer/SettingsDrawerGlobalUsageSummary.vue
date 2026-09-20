<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import ModernSelect from '../ModernSelect.vue'
import ThemedRadioTags from '../ThemedRadioTags.vue'
import {
  getUsageModels,
  getUsageSummary,
  type UsageModelRow,
  type UsageRange,
  type UsageScope,
  type UsageSummaryMetrics,
} from '../../api/usage'

const props = defineProps<{
  chatId: string | null
}>()

const scope = ref<UsageScope>('global')
const range = ref<UsageRange>('all')
const loading = ref(false)
const errorText = ref('')
const summary = ref<UsageSummaryMetrics | null>(null)
const models = ref<UsageModelRow[]>([])
const eventCount = ref(0)

const RANGE_OPTIONS = [
  { label: '全部时间', value: 'all' },
  { label: '近 7 天', value: '7d' },
  { label: '近 30 天', value: '30d' },
  { label: '本月', value: 'month' },
]

const scopeOptions = computed(() => [
  { label: '当前会话', value: 'chat', disabled: !props.chatId },
  { label: '全局', value: 'global' },
])

const nf = new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 1 })
const money = new Intl.NumberFormat('zh-CN', { minimumFractionDigits: 4, maximumFractionDigits: 4 })

function fmtNum(n: number | null | undefined) {
  if (n == null || !Number.isFinite(n)) return '—'
  return nf.format(n)
}

function fmtPct(n: number | null | undefined) {
  if (n == null || !Number.isFinite(n)) return '—'
  return `${(n * 100).toFixed(1)}%`
}

function fmtMs(n: number | null | undefined) {
  if (n == null || !Number.isFinite(n)) return '—'
  return `${Math.round(n)} ms`
}

function fmtRowCost(row: UsageModelRow) {
  const by = row.costByCurrency || {}
  const keys = Object.keys(by)
  if (!keys.length) return '—'
  return keys
    .map((currency) => {
      const item = by[currency]
      if (!item) return null
      return `${currency} ${money.format(item.total)}`
    })
    .filter((x): x is string => Boolean(x))
    .join(' · ')
}

function onScope(value: string) {
  if (value === 'chat' || value === 'global') scope.value = value
}

function onRange(value: string) {
  if (value === 'all' || value === '7d' || value === '30d' || value === 'month') {
    range.value = value
  }
}

const costLines = computed(() => {
  const by = summary.value?.costByCurrency || {}
  const keys = Object.keys(by)
  if (!keys.length) return []
  return keys.flatMap((currency) => {
    const row = by[currency]
    if (!row) return []
    return [
      {
        currency,
        total: row.total,
        provider: row.provider,
        estimated: row.estimated,
      },
    ]
  })
})

let refreshSeq = 0

async function refresh() {
  const seq = ++refreshSeq
  if (scope.value === 'chat' && !props.chatId) {
    if (seq !== refreshSeq) return
    errorText.value = '没有活动会话，当前会话统计不可用。'
    summary.value = null
    models.value = []
    eventCount.value = 0
    return
  }
  loading.value = true
  errorText.value = ''
  try {
    const params = {
      scope: scope.value,
      chatId: scope.value === 'chat' ? props.chatId : null,
      range: range.value,
    }
    const [sum, modelRes] = await Promise.all([getUsageSummary(params), getUsageModels(params)])
    if (seq !== refreshSeq) return
    summary.value = sum.summary
    eventCount.value = sum.eventCount
    models.value = modelRes.models
  } catch (e: unknown) {
    if (seq !== refreshSeq) return
    errorText.value = e instanceof Error ? e.message : String(e)
  } finally {
    if (seq === refreshSeq) loading.value = false
  }
}

watch(
  [scope, range, () => props.chatId],
  () => {
    if (!props.chatId && scope.value === 'chat') {
      scope.value = 'global'
      return
    }
    void refresh()
  },
  { immediate: true },
)
</script>

<template>
  <section class="space-y-3 rounded-xl border border-[var(--color-border-subtle)] bg-[var(--color-settings-control-bg)] p-3">
    <div class="flex flex-wrap items-center justify-between gap-2">
      <h3 class="text-sm font-medium text-[var(--color-text-secondary)]">用量与成本</h3>
      <button
        type="button"
        class="min-h-8 rounded-lg bg-surface-muted px-3 py-1.5 text-xs text-[var(--color-text)] transition-colors hover:bg-surface-hover disabled:opacity-60"
        :disabled="loading"
        @click="refresh"
      >
        {{ loading ? '刷新中…' : '刷新' }}
      </button>
    </div>
    <ThemedRadioTags
      :model-value="scope"
      :options="scopeOptions"
      aria-label="用量统计范围"
      @update:model-value="onScope"
    />
    <p v-if="!chatId" class="text-2xs text-[var(--color-text-muted)]">
      没有打开的会话，「当前会话」不可用。
    </p>
    <div class="space-y-1.5">
      <label class="block text-xs text-[var(--color-text-muted)]">时间范围</label>
      <ModernSelect :model-value="range" :options="RANGE_OPTIONS" placeholder="选择时间范围…" class="w-full" @update:model-value="onRange" />
    </div>
    <p v-if="errorText" class="text-xs text-[var(--color-error-text)]">{{ errorText }}</p>
    <p class="text-2xs text-[var(--color-text-muted)]">
      账本事件 {{ eventCount }} 条。云端金额不被本地估算覆盖；未知成本不计 0。
    </p>
    <div v-if="summary" class="grid grid-cols-2 gap-2 text-xs">
      <div class="rounded-lg bg-surface-muted/60 p-2">
        <div class="text-[var(--color-text-muted)]">输入 / 输出 token</div>
        <div class="tabular-nums text-[var(--color-text)]">{{ fmtNum(summary.inputTokens) }} / {{ fmtNum(summary.outputTokens) }}</div>
        <div class="mt-1 text-2xs text-[var(--color-text-muted)]">
          平均 {{ fmtNum(summary.avgInputTokens) }} / {{ fmtNum(summary.avgOutputTokens) }}
        </div>
      </div>
      <div class="rounded-lg bg-surface-muted/60 p-2">
        <div class="text-[var(--color-text-muted)]">缓存读 / 写</div>
        <div class="tabular-nums text-[var(--color-text)]">{{ fmtNum(summary.cacheReadInputTokens) }} / {{ fmtNum(summary.cacheWriteInputTokens) }}</div>
        <div class="mt-1 text-2xs text-[var(--color-text-muted)]">命中率 {{ fmtPct(summary.cacheHitRate) }}</div>
      </div>
      <div class="rounded-lg bg-surface-muted/60 p-2">
        <div class="text-[var(--color-text-muted)]">请求</div>
        <div class="tabular-nums text-[var(--color-text)]">{{ summary.requestCount }}</div>
        <div class="mt-1 text-2xs text-[var(--color-text-muted)]">
          成功 {{ summary.completedCount }} · 失败 {{ summary.failedCount }} · 取消 {{ summary.cancelledCount }}
        </div>
      </div>
      <div class="rounded-lg bg-surface-muted/60 p-2">
        <div class="text-[var(--color-text-muted)]">TTFT / 总耗时</div>
        <div class="tabular-nums text-[var(--color-text)]">{{ fmtMs(summary.avgFirstTokenLatencyMs) }}</div>
        <div class="mt-1 text-2xs text-[var(--color-text-muted)]">
          P50 {{ fmtMs(summary.p50FirstTokenLatencyMs) }} · P95 {{ fmtMs(summary.p95FirstTokenLatencyMs) }} · 平均总 {{ fmtMs(summary.avgTotalDurationMs) }}
        </div>
      </div>
    </div>
    <div class="space-y-1 text-xs">
      <div class="font-medium text-[var(--color-text-secondary)]">成本来源</div>
      <p class="text-2xs text-[var(--color-text-muted)]">云端 = 供应商返回金额；本地估算 = 目录/用户价格表；未知 = 无法可靠计算。</p>
      <ul v-if="costLines.length" class="space-y-0.5 text-[var(--color-text)]">
        <li v-for="line in costLines" :key="line.currency" class="tabular-nums">
          {{ line.currency }} 合计 {{ money.format(line.total) }}
          （云端 {{ money.format(line.provider) }} · 估算 {{ money.format(line.estimated) }}）
        </li>
      </ul>
      <p v-else class="text-[var(--color-text-muted)]">尚无已知金额。</p>
      <p class="text-2xs text-[var(--color-text-muted)]">未知成本事件 {{ summary?.unknownCostCount ?? 0 }} 条</p>
    </div>
    <div v-if="models.length" class="overflow-x-auto">
      <table class="w-full min-w-[28rem] text-left text-2xs">
        <thead class="text-[var(--color-text-muted)]">
          <tr>
            <th class="py-1 pr-2 font-medium">供应商</th>
            <th class="py-1 pr-2 font-medium">模型</th>
            <th class="py-1 pr-2 font-medium">协议</th>
            <th class="py-1 pr-2 font-medium">请求</th>
            <th class="py-1 pr-2 font-medium">输入</th>
            <th class="py-1 pr-2 font-medium">输出</th>
            <th class="py-1 pr-2 font-medium">TTFT</th>
            <th class="py-1 pr-2 font-medium">总耗时</th>
            <th class="py-1 pr-2 font-medium">成本</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in models" :key="`${row.provider}:${row.protocol}:${row.resolvedModel}`" class="text-[var(--color-text)]">
            <td class="py-1 pr-2">{{ row.provider || '—' }}</td>
            <td class="py-1 pr-2">{{ row.resolvedModel || '—' }}</td>
            <td class="py-1 pr-2">{{ row.protocol || '—' }}</td>
            <td class="py-1 pr-2 tabular-nums">{{ row.requestCount }}</td>
            <td class="py-1 pr-2 tabular-nums">{{ fmtNum(row.inputTokens) }}</td>
            <td class="py-1 pr-2 tabular-nums">{{ fmtNum(row.outputTokens) }}</td>
            <td class="py-1 pr-2 tabular-nums">{{ fmtMs(row.avgFirstTokenLatencyMs) }}</td>
            <td class="py-1 pr-2 tabular-nums">{{ fmtMs(row.avgTotalDurationMs) }}</td>
            <td class="py-1 pr-2 tabular-nums">{{ fmtRowCost(row) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>
