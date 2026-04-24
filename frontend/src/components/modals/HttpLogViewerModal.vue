<script setup lang="ts">
/**
 * HttpLogViewerModal - HTTP 请求查看弹窗
 *
 * 入口：设置抽屉 → 应用与更新 → 查看 HTTP 请求
 *
 * 左栏：时间线列表（从旧到新）
 * 右栏：详情（Pretty / Raw 切换；详情区再分 Request / Response）
 *  - Pretty：走 HttpRecordPreview（身份卡 + 工具卡 + 图像原图 + 文件截断）
 *  - Raw：走 CodeViewer，JSON 按层级自动折叠，防止数千行一打开就爆炸
 */
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { RefreshCw, Trash2, Copy, X, Clock, Radio } from 'lucide-vue-next'
import {
  clearHttpLog,
  getHttpLog,
  getHttpLogDetail,
  type HttpLogDetail,
  type HttpLogListItem,
} from '../../api/httpLog'
import CodeViewer from '../common/CodeViewer.vue'
import HttpRecordPreview from '../http-log/HttpRecordPreview.vue'

const props = defineProps<{
  show: boolean
}>()

const emit = defineEmits<{
  (e: 'update:show', v: boolean): void
}>()

const items = ref<HttpLogListItem[]>([])
const listLoading = ref(false)
const listError = ref('')
const listRetentionMinutes = ref(30)

const selectedId = ref<string | null>(null)
const detail = ref<HttpLogDetail | null>(null)
const detailLoading = ref(false)
const detailError = ref('')

const viewMode = ref<'pretty' | 'raw'>('pretty')
const rawSection = ref<'request' | 'response'>('request')

let refreshTimer: number | null = null

function close() {
  emit('update:show', false)
}

async function loadList(keepSelection = true) {
  listLoading.value = true
  listError.value = ''
  try {
    const res = await getHttpLog()
    items.value = res.items
    listRetentionMinutes.value = res.retentionMinutes
    if (!keepSelection || !selectedId.value) {
      const last = res.items[res.items.length - 1]
      if (last) {
        selectedId.value = last.id
      }
    } else if (selectedId.value && !res.items.some((it) => it.id === selectedId.value)) {
      detail.value = null
      selectedId.value = null
    }
  } catch (e) {
    listError.value = String(e)
  } finally {
    listLoading.value = false
  }
}

async function loadDetail(id: string) {
  detailLoading.value = true
  detailError.value = ''
  detail.value = null
  try {
    detail.value = await getHttpLogDetail(id)
  } catch (e) {
    detailError.value = String(e)
  } finally {
    detailLoading.value = false
  }
}

watch(
  () => selectedId.value,
  (id) => {
    if (id) void loadDetail(id)
    else detail.value = null
  },
)

watch(
  () => props.show,
  (v) => {
    if (v) {
      void loadList(false)
      if (refreshTimer == null) {
        refreshTimer = window.setInterval(() => {
          if (props.show) void loadList(true)
        }, 30_000)
      }
    } else {
      if (refreshTimer != null) {
        window.clearInterval(refreshTimer)
        refreshTimer = null
      }
    }
  },
  { immediate: true },
)

onBeforeUnmount(() => {
  if (refreshTimer != null) {
    window.clearInterval(refreshTimer)
    refreshTimer = null
  }
})

async function onClear() {
  if (!confirm('确定清空本地全部 HTTP 请求日志？')) return
  try {
    await clearHttpLog()
    items.value = []
    detail.value = null
    selectedId.value = null
  } catch (e) {
    alert('清空失败：' + String(e))
  }
}

const rawText = computed(() => {
  if (!detail.value) return ''
  const payload = rawSection.value === 'request'
    ? {
        method: detail.value.method,
        url: detail.value.url,
        headers: detail.value.requestHeaders,
        body: detail.value.requestBody,
      }
    : {
        status: detail.value.responseStatus,
        headers: detail.value.responseHeaders,
        body: detail.value.responseBody,
        error: detail.value.error,
      }
  try {
    return JSON.stringify(payload, null, 2)
  } catch {
    return String(payload)
  }
})

async function onCopy() {
  const text = viewMode.value === 'raw' ? rawText.value : (detail.value ? JSON.stringify(detail.value, null, 2) : '')
  try {
    await navigator.clipboard.writeText(text)
  } catch {
    // fallback
    const ta = document.createElement('textarea')
    ta.value = text
    document.body.appendChild(ta)
    ta.select()
    try {
      document.execCommand('copy')
    } finally {
      document.body.removeChild(ta)
    }
  }
}

function formatTime(iso: string): string {
  try {
    const d = new Date(iso)
    const hh = String(d.getHours()).padStart(2, '0')
    const mm = String(d.getMinutes()).padStart(2, '0')
    const ss = String(d.getSeconds()).padStart(2, '0')
    return `${hh}:${mm}:${ss}`
  } catch {
    return iso
  }
}

function sourceLabel(src: string): string {
  switch (src) {
    case 'llm':
      return 'LLM'
    case 'update':
      return '更新'
    case 'other':
      return '其它'
    default:
      return src
  }
}

function statusClass(item: HttpLogListItem): string {
  if (item.error) return 'text-rose-300'
  const s = item.responseStatus ?? 0
  if (s >= 500) return 'text-rose-300'
  if (s >= 400) return 'text-amber-300'
  if (s >= 200 && s < 300) return 'text-emerald-300'
  return 'text-[var(--color-text-muted)]'
}

function sourceBadgeClass(src: string): string {
  const base = 'inline-flex items-center rounded px-1 py-0.5 text-[10px] font-semibold'
  switch (src) {
    case 'llm':
      return `${base} bg-emerald-500/15 text-emerald-300`
    case 'update':
      return `${base} bg-sky-500/15 text-sky-300`
    default:
      return `${base} bg-zinc-500/20 text-[var(--color-text-secondary)]`
  }
}

function truncateUrl(u: string, max = 60): string {
  if (!u) return ''
  if (u.length <= max) return u
  return u.slice(0, max - 1) + '…'
}
</script>

<template>
  <Transition name="modal">
    <div v-if="show" class="modal">
      <div class="modal-backdrop backdrop-blur-[var(--blur-heavy)]" @click="close"></div>
      <div
        class="modal-content chat-modal-width-1200-90 glass-panel theme-panel-bg backdrop-blur-[var(--blur-heavy)] backdrop-saturate-[1.8] border border-[var(--color-border)] flex flex-col min-h-0"
        style="max-height: 88vh"
      >
        <div class="modal-header border-b border-[var(--color-border-subtle)] shrink-0">
          <h3 class="modal-title text-[var(--color-text)]">HTTP 请求查看</h3>
          <div class="ml-auto flex items-center gap-2">
            <button
              type="button"
              class="inline-flex min-h-9 items-center gap-1 rounded-lg bg-surface-muted px-2.5 py-1.5 text-xs text-[var(--color-text)] transition-colors hover:bg-surface-hover disabled:opacity-50"
              :disabled="listLoading"
              @click="loadList(true)"
            >
              <RefreshCw class="h-3.5 w-3.5" :class="listLoading ? 'animate-spin' : ''" />
              刷新
            </button>
            <button
              type="button"
              class="inline-flex min-h-9 items-center gap-1 rounded-lg bg-surface-muted px-2.5 py-1.5 text-xs text-[var(--color-text)] transition-colors hover:bg-surface-hover"
              @click="onCopy"
            >
              <Copy class="h-3.5 w-3.5" />
              复制
            </button>
            <button
              type="button"
              class="inline-flex min-h-9 items-center gap-1 rounded-lg border border-rose-500/30 bg-rose-500/10 px-2.5 py-1.5 text-xs text-rose-300 transition-colors hover:bg-rose-500/20"
              @click="onClear"
            >
              <Trash2 class="h-3.5 w-3.5" />
              清空
            </button>
            <button
              type="button"
              class="modal-close inline-flex min-h-9 min-w-9 items-center justify-center rounded-lg text-[var(--color-text-muted)] hover:text-[var(--color-text)] touch-manipulation"
              aria-label="关闭"
              @click="close"
            >
              <X class="h-4 w-4" />
            </button>
          </div>
        </div>

        <div class="modal-body flex min-h-0 min-w-0 flex-1 flex-row gap-3 overflow-hidden !p-0">
          <!-- 左栏：列表 -->
          <aside
            class="flex min-h-0 w-[280px] shrink-0 flex-col border-r border-[var(--color-border-subtle)] bg-[var(--color-surface-muted)]/30"
          >
            <div class="flex items-center justify-between gap-2 border-b border-[var(--color-border-subtle)] px-3 py-2">
              <span class="flex items-center gap-1 text-xs text-[var(--color-text-secondary)]">
                <Clock class="h-3 w-3" />
                最近 {{ listRetentionMinutes }} 分钟
              </span>
              <span class="text-[10px] text-[var(--color-text-muted)]">{{ items.length }} 条</span>
            </div>
            <div v-if="listError" class="px-3 py-2 text-xs text-rose-300">{{ listError }}</div>
            <div v-else-if="items.length === 0 && !listLoading" class="flex flex-1 items-center justify-center px-3 text-center text-xs text-[var(--color-text-muted)]">
              暂无记录。发起一次云端请求（对话 / 检查更新）后刷新即可看到。
            </div>
            <div class="min-h-0 flex-1 overflow-y-auto">
              <button
                v-for="it in items"
                :key="it.id"
                type="button"
                class="flex w-full flex-col gap-1 border-b border-[var(--color-border-subtle)]/60 px-3 py-2 text-left transition-colors hover:bg-[var(--color-surface-hover)]"
                :class="selectedId === it.id ? 'bg-[var(--color-surface-hover)]' : ''"
                @click="selectedId = it.id"
              >
                <div class="flex items-center gap-1.5">
                  <span :class="sourceBadgeClass(it.source)">{{ sourceLabel(it.source) }}</span>
                  <span class="font-mono text-[10px] text-[var(--color-text-muted)]">{{ it.method }}</span>
                  <span :class="['ml-auto font-mono text-[10px]', statusClass(it)]">
                    <template v-if="it.error">ERR</template>
                    <template v-else-if="it.responseStatus != null">{{ it.responseStatus }}</template>
                    <template v-else>—</template>
                  </span>
                </div>
                <div class="truncate font-mono text-[10px] text-[var(--color-text-secondary)]" :title="it.url">
                  {{ truncateUrl(it.url, 60) }}
                </div>
                <div class="flex items-center gap-1.5 text-[10px] text-[var(--color-text-muted)]">
                  <span>{{ formatTime(it.ts) }}</span>
                  <Radio v-if="it.streaming" class="h-2.5 w-2.5" />
                  <span v-if="it.streaming">stream</span>
                  <span class="ml-auto">{{ it.durationMs }}ms</span>
                </div>
              </button>
            </div>
          </aside>

          <!-- 右栏：详情 -->
          <section class="flex min-h-0 min-w-0 flex-1 flex-col">
            <div class="flex shrink-0 flex-wrap items-center gap-2 border-b border-[var(--color-border-subtle)] bg-[var(--color-surface-muted)]/20 px-3 py-2">
              <div class="inline-flex overflow-hidden rounded-lg border border-[var(--color-border-subtle)]">
                <button
                  type="button"
                  class="px-3 py-1 text-xs transition-colors"
                  :class="viewMode === 'pretty' ? 'bg-brand-a20 text-[var(--color-brand)]' : 'text-[var(--color-text-secondary)] hover:bg-surface-hover'"
                  @click="viewMode = 'pretty'"
                >Pretty</button>
                <button
                  type="button"
                  class="px-3 py-1 text-xs transition-colors"
                  :class="viewMode === 'raw' ? 'bg-brand-a20 text-[var(--color-brand)]' : 'text-[var(--color-text-secondary)] hover:bg-surface-hover'"
                  @click="viewMode = 'raw'"
                >Raw JSON</button>
              </div>
              <div
                v-if="viewMode === 'raw'"
                class="inline-flex overflow-hidden rounded-lg border border-[var(--color-border-subtle)]"
              >
                <button
                  type="button"
                  class="px-3 py-1 text-xs transition-colors"
                  :class="rawSection === 'request' ? 'bg-[var(--color-surface-hover)] text-[var(--color-text)]' : 'text-[var(--color-text-secondary)] hover:bg-surface-hover'"
                  @click="rawSection = 'request'"
                >Request</button>
                <button
                  type="button"
                  class="px-3 py-1 text-xs transition-colors"
                  :class="rawSection === 'response' ? 'bg-[var(--color-surface-hover)] text-[var(--color-text)]' : 'text-[var(--color-text-secondary)] hover:bg-surface-hover'"
                  @click="rawSection = 'response'"
                >Response</button>
              </div>
              <div v-if="detail" class="ml-auto flex flex-wrap items-center gap-2 text-[11px] text-[var(--color-text-muted)]">
                <span class="font-mono">{{ detail.method }}</span>
                <span class="max-w-[50vw] truncate" :title="detail.url">{{ detail.url }}</span>
              </div>
            </div>

            <div class="min-h-0 flex-1 overflow-auto px-3 py-3">
              <div v-if="!selectedId" class="flex h-full items-center justify-center text-xs text-[var(--color-text-muted)]">
                请从左侧选择一条记录查看
              </div>
              <div v-else-if="detailLoading" class="flex h-full items-center justify-center text-xs text-[var(--color-text-muted)]">
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
                  max-height-class="max-h-[72vh]"
                />
              </template>
            </div>

            <div class="shrink-0 border-t border-[var(--color-border-subtle)] bg-[var(--color-surface-muted)]/20 px-3 py-1.5 text-center text-[10px] text-[var(--color-text-muted)]">
              仅保留最近 30 分钟，每 30s 自动清理一次；API Key 与文件内容已脱敏。
            </div>
          </section>
        </div>
      </div>
    </div>
  </Transition>
</template>
