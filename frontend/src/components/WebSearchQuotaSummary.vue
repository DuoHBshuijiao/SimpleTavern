<script setup lang="ts">
/**
 * 将 GET /api/web-search/status 的结果渲染为可读用量/余额（不展示原始 JSON）。
 * 仅展示当前选中的提供方，避免切换厂商时混显两边的余额。
 */
import { computed } from 'vue'
import type { WebSearchProvider } from '../types/models'

const props = defineProps<{
  status: Record<string, unknown> | null
  provider: WebSearchProvider
}>()

const nfInt = new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 0 })
const nfMoney = new Intl.NumberFormat('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

function asRecord(v: unknown): Record<string, unknown> | null {
  return v !== null && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : null
}

function num(v: unknown): number | null {
  if (typeof v === 'number' && Number.isFinite(v)) return v
  if (typeof v === 'string' && v.trim() !== '') {
    const n = Number(v)
    return Number.isFinite(n) ? n : null
  }
  return null
}

function usagePct(used: number, limit: number): number {
  if (!(limit > 0)) return 0
  return Math.min(100, Math.max(0, (used / limit) * 100))
}

function barToneClass(pct: number): string {
  if (pct > 90) return 'bg-red-500'
  if (pct > 70) return 'bg-amber-500'
  return 'bg-brand'
}

function blockMessage(block: Record<string, unknown>): string {
  const m = block.message
  if (typeof m === 'string' && m.trim()) return m.trim()
  const err = block.error
  if (typeof err === 'string' && err.trim()) return err.trim()
  const data = asRecord(block.data)
  if (data) {
    const detail = asRecord(data.detail)
    if (detail) {
      const e = detail.error
      if (typeof e === 'string' && e.trim()) return e.trim()
    }
  }
  const st = block.status
  if (typeof st === 'number') return `请求失败（HTTP ${st}）`
  return '查询失败'
}

type KeyMetrics = { usage: number; limit: number; breakdown: string }
type PlanMetrics = { used: number; limit: number; planLabel: string | null }

function parseKeyMetrics(data: Record<string, unknown>): KeyMetrics | null {
  const key = asRecord(data.key)
  if (!key) return null
  const usage = num(key.usage)
  const limit = num(key.limit)
  if (usage === null || limit === null) return null
  const parts: string[] = []
  const labels: Record<string, string> = {
    search_usage: '搜索',
    extract_usage: '提取',
    crawl_usage: '爬取',
    map_usage: '地图',
    research_usage: '研究',
  }
  for (const [k, lab] of Object.entries(labels)) {
    const n = num(key[k])
    if (n !== null) parts.push(`${lab} ${nfInt.format(n)}`)
  }
  return { usage, limit, breakdown: parts.length ? parts.join(' · ') : '' }
}

function parseAccountPlan(data: Record<string, unknown>): PlanMetrics | null {
  const account = asRecord(data.account)
  if (!account) return null
  const used = num(account.plan_usage)
  const limit = num(account.plan_limit)
  if (used === null || limit === null) return null
  const plan = account.current_plan
  const planLabel = typeof plan === 'string' && plan.trim() ? plan.trim() : null
  return { used, limit, planLabel }
}

type TavilyParsed =
  | { mode: 'hint'; text: string }
  | { mode: 'bars'; keyM: KeyMetrics | null; planM: PlanMetrics | null }

const tavilyBlock = computed(() => asRecord(props.status?.tavily))
const bochaBlock = computed(() => asRecord(props.status?.bocha))

const tavilyParsed = computed((): TavilyParsed | null => {
  const b = tavilyBlock.value
  if (!b || b.ok !== true) return null
  const data = asRecord(b.data)
  if (!data) return { mode: 'hint', text: '接口未返回用量结构，请稍后重试或检查 Key。' }
  const keyM = parseKeyMetrics(data)
  const planM = parseAccountPlan(data)
  if (!keyM && !planM) return { mode: 'hint', text: '暂无可用用量字段（响应格式可能已变更）。' }
  return { mode: 'bars', keyM, planM }
})

const bochaRemaining = computed(() => {
  const b = bochaBlock.value
  if (!b) return null
  return num(b.remaining)
})

const showTavily = computed(() => props.provider === 'tavily')
const showBocha = computed(() => props.provider === 'bocha')

const emptyHintForCurrentProvider = computed(() => {
  if (!props.status) return ''
  if (props.provider === 'tavily' && !tavilyBlock.value) {
    return '服务端未返回 Tavily 用量（通常表示未保存或未填写 Tavily API Key）。保存 Key 后重新打开抽屉可刷新。'
  }
  if (props.provider === 'bocha' && !bochaBlock.value) {
    return '服务端未返回博查余额（通常表示未保存或未填写博查 API Key）。保存 Key 后重新打开抽屉可刷新。'
  }
  return ''
})
</script>

<template>
  <div v-if="!status" class="text-[var(--color-text-muted)]">暂无数据（关闭抽屉后重开可刷新）</div>
  <div v-else class="space-y-4">
    <div v-if="showTavily && tavilyBlock" class="space-y-3">
      <div class="text-xs font-medium text-[var(--color-text-secondary)]">Tavily</div>
      <template v-if="tavilyBlock.ok === true">
        <template v-if="tavilyParsed?.mode === 'hint'">
          <p class="text-xs text-[var(--color-text-muted)]">{{ tavilyParsed.text }}</p>
        </template>
        <template v-else-if="tavilyParsed?.mode === 'bars'">
          <div v-if="tavilyParsed.keyM" class="space-y-2">
            <div class="flex items-center justify-between gap-2 text-xs text-[var(--color-text-muted)]">
              <span>API Key 用量</span>
              <span class="tabular-nums text-[var(--color-text-secondary)]">
                {{ nfInt.format(tavilyParsed.keyM.usage) }} / {{ nfInt.format(tavilyParsed.keyM.limit) }}
              </span>
            </div>
            <div class="h-2 w-full overflow-hidden rounded-full bg-[var(--color-track)]">
              <div
                class="h-full rounded-full transition-[width] duration-500 ease-out"
                :class="barToneClass(usagePct(tavilyParsed.keyM.usage, tavilyParsed.keyM.limit))"
                :style="{ width: usagePct(tavilyParsed.keyM.usage, tavilyParsed.keyM.limit) + '%' }"
              ></div>
            </div>
            <p v-if="tavilyParsed.keyM.breakdown" class="text-[11px] leading-snug text-[var(--color-text-muted)]">
              {{ tavilyParsed.keyM.breakdown }}
            </p>
          </div>

          <div
            v-if="tavilyParsed.planM"
            class="space-y-2 border-t border-[var(--color-border-subtle)] pt-3"
            :class="{ 'mt-3': tavilyParsed.keyM }"
          >
            <div class="flex items-center justify-between gap-2 text-xs text-[var(--color-text-muted)]">
              <span>
                套餐内用量
                <template v-if="tavilyParsed.planM.planLabel">
                  <span class="text-[var(--color-text-muted)]">（{{ tavilyParsed.planM.planLabel }}）</span>
                </template>
              </span>
              <span class="tabular-nums text-[var(--color-text-secondary)]">
                {{ nfInt.format(tavilyParsed.planM.used) }} / {{ nfInt.format(tavilyParsed.planM.limit) }}
              </span>
            </div>
            <div class="h-2 w-full overflow-hidden rounded-full bg-[var(--color-track)]">
              <div
                class="h-full rounded-full transition-[width] duration-500 ease-out"
                :class="barToneClass(usagePct(tavilyParsed.planM.used, tavilyParsed.planM.limit))"
                :style="{ width: usagePct(tavilyParsed.planM.used, tavilyParsed.planM.limit) + '%' }"
              ></div>
            </div>
          </div>
        </template>
      </template>
      <p v-else class="text-xs text-[var(--color-error-text)]">{{ blockMessage(tavilyBlock) }}</p>
    </div>

    <div v-if="showBocha && bochaBlock" class="space-y-3">
      <div class="text-xs font-medium text-[var(--color-text-secondary)]">博查</div>
      <template v-if="bochaBlock.ok === true">
        <p v-if="bochaRemaining !== null" class="text-xs text-[var(--color-text-muted)]">
          账户余额（元）
          <span class="ml-1 tabular-nums text-sm font-medium text-[var(--color-text-secondary)]">
            ¥{{ nfMoney.format(bochaRemaining) }}
          </span>
        </p>
        <p v-else class="text-xs text-[var(--color-text-muted)]">暂无法读取余额字段。</p>
      </template>
      <p v-else class="text-xs text-[var(--color-error-text)]">{{ blockMessage(bochaBlock) }}</p>
    </div>

    <p v-if="emptyHintForCurrentProvider" class="text-xs text-[var(--color-text-muted)]">
      {{ emptyHintForCurrentProvider }}
    </p>
  </div>
</template>
