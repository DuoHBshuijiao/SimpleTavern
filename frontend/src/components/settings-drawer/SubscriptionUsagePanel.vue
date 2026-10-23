<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { fetchOAuthUsage, type OAuthUsage } from '../../api/llm'
const props = defineProps<{ presetId: string; providerId?: string | null; loggedIn: boolean; accountId?: string | null }>()
const panel = ref<HTMLElement | null>(null)
const latest = ref<OAuthUsage | null>(null)
const snapshot = ref<OAuthUsage | null>(null)
const busy = ref(false)
const error = ref('')
const now = ref(Date.now())
const visible = ref(false)
let generation = 0
let lastAttempt = 0
let observer: IntersectionObserver | null = null
let timer: ReturnType<typeof setInterval> | null = null
const shown = computed(() => snapshot.value || latest.value)
const stale = computed(() => !!snapshot.value && (!!error.value || latest.value?.state === 'error'))
const manageUrl = computed(() => {
  const value = shown.value?.manageUrl
  if (value && /^https:\/\//i.test(value)) return value
  return props.providerId === 'openai-chatgpt' ? 'https://chatgpt.com/settings/usage' : null
})
function timestamp(value: string | number | null | undefined): number {
  if (value == null) return NaN
  return typeof value === 'number' ? (value < 1e12 ? value * 1000 : value) : Date.parse(value)
}
function date(value: string | number | null | undefined) {
  const time = timestamp(value)
  return Number.isFinite(time) ? new Date(time).toLocaleString() : '暂未提供'
}
function countdown(value: string | number | null | undefined) {
  const time = timestamp(value)
  if (!Number.isFinite(time)) return ''
  const minutes = Math.ceil((time - now.value) / 60000)
  if (minutes <= 0) return '已到刷新时间'
  const days = Math.floor(minutes / 1440)
  const hours = Math.floor(minutes % 1440 / 60)
  return `${days ? `${days}天 ` : ''}${hours}小时 ${minutes % 60}分钟后刷新`
}
function percent(value?: number | null) {
  return typeof value === 'number' && Number.isFinite(value) ? `${Math.max(0, Math.min(100, value)).toFixed(1)}%` : '暂未提供'
}
async function load(refresh = false) {
  if (!props.loggedIn || busy.value) return
  const gen = generation
  busy.value = true
  error.value = ''
  lastAttempt = Date.now()
  try {
    const result = await fetchOAuthUsage(props.presetId, refresh)
    if (gen !== generation) return
    latest.value = result
    if (result.state === 'available') snapshot.value = result
    else if (result.state === 'not_logged_in') snapshot.value = null
  } catch (e) {
    if (gen === generation) error.value = e instanceof Error ? e.message : String(e)
  } finally { if (gen === generation) busy.value = false }
}
function maybeRefresh() {
  now.value = Date.now()
  if (visible.value && document.visibilityState === 'visible' && now.value - lastAttempt >= 60000) void load()
}
watch(() => [props.presetId, props.loggedIn, props.accountId], () => {
  generation++
  latest.value = null
  snapshot.value = null
  error.value = ''
  busy.value = false
  lastAttempt = 0
  if (visible.value) void load()
})
onMounted(() => {
  observer = new IntersectionObserver(entries => {
    visible.value = entries.some(entry => entry.isIntersecting)
    maybeRefresh()
  })
  if (panel.value) observer.observe(panel.value)
  timer = setInterval(maybeRefresh, 1000)
  document.addEventListener('visibilitychange', maybeRefresh)
})
onBeforeUnmount(() => {
  generation++
  observer?.disconnect()
  if (timer) clearInterval(timer)
  document.removeEventListener('visibilitychange', maybeRefresh)
})
</script>
<template>
  <section ref="panel" class="space-y-2 border-t border-[var(--color-border-subtle)] pt-3" aria-label="订阅账号用量" :aria-busy="busy">
    <div class="flex flex-wrap items-center justify-between gap-2">
      <h4 class="text-sm font-medium">订阅用量<span v-if="shown?.plan"> · {{ shown.plan }}</span></h4>
      <div class="flex flex-wrap items-center gap-3">
        <a v-if="manageUrl" :href="manageUrl" target="_blank" rel="noopener noreferrer" class="text-xs text-brand hover:underline">管理用量</a>
        <button type="button" class="btn btn-xs btn-secondary" :disabled="busy || !loggedIn" @click="load(true)">{{ busy ? '查询中…' : '刷新额度' }}</button>
      </div>
    </div>
    <p v-if="!loggedIn || latest?.state === 'not_logged_in'" class="text-xs text-[var(--color-text-secondary)]">登录后查看订阅信息。</p>
    <template v-else>
      <p v-if="error || latest?.state === 'error'" role="status" class="text-xs text-error">{{ stale ? '查询失败，以下为上次成功结果（已过期）。' : '暂无法查询额度。' }} {{ error || latest?.errorCode }}</p>
      <p v-else-if="latest?.state === 'unsupported' || (latest?.state === 'available' && !latest.windows.length)" class="text-xs leading-relaxed text-[var(--color-text-secondary)]">暂无法查询：服务方未提供可用的订阅额度接口。5小时、周额度及刷新时间仅在官方返回时展示，不估算消息数。</p>
      <p v-else-if="!shown" role="status" class="text-xs text-[var(--color-text-secondary)]">{{ busy ? '正在查询账号用量…' : '尚未查询' }}</p>
      <dl v-if="shown?.windows.length" class="space-y-3">
        <div v-for="window in shown.windows" :key="window.id" class="space-y-1 text-xs">
          <dt class="font-medium">{{ window.label || (window.windowMinutes === 300 ? '5小时额度' : window.windowMinutes === 10080 ? '周额度' : window.id) }}</dt>
          <dd class="text-[var(--color-text-secondary)]">剩余 {{ percent(window.remainingPercent) }}<span v-if="window.usedPercent != null"> · 已用 {{ percent(window.usedPercent) }}</span></dd>
          <dd class="text-[var(--color-text-secondary)]">刷新时间：{{ date(window.resetsAt) }}<span v-if="countdown(window.resetsAt)"> · {{ countdown(window.resetsAt) }}</span></dd>
        </div>
      </dl>
      <p v-if="shown?.checkedAt" class="text-xs text-[var(--color-text-secondary)]">{{ stale ? '上次成功查询' : '查询时间' }}：{{ date(shown.checkedAt) }}（本地时区）</p>
    </template>
  </section>
</template>
