<script setup lang="ts">
/**
 * PromptCacheGuideModal — 近全屏缓存教学（T-821-B3）
 *
 * 叠在当前设置抽屉上，不跳页。7 步：前缀与 KV → 断点 → 成本 → TTL → 厂商差异 → 应用到本预设 → 可选探测。
 */
import { computed, ref, watch } from 'vue'
import { ArrowLeft, ArrowRight, Check, Sparkles, X } from 'lucide-vue-next'
import { useDialogBehavior } from '../../composables/useDialogBehavior'
import { dialogAria } from '../../utils/uiPrimitives'
import ThemedCheckbox from '../ThemedCheckbox.vue'
import type { PromptCacheConfig, PromptCacheMode } from '../../types/models'
import { defaultPromptCacheConfig } from '../../types/models'

export interface CacheGuideConnection {
  promptCache?: PromptCacheConfig | null
  protocol?: string | null
}

const props = defineProps<{
  show: boolean
  connection?: CacheGuideConnection | null
}>()

const emit = defineEmits<{
  (e: 'update:show', v: boolean): void
}>()

const titleId = 'prompt-cache-guide-title'
const dialogAttrs = dialogAria(titleId)
function close() {
  emit('update:show', false)
}
const { dialogRef } = useDialogBehavior(() => props.show, close)
defineExpose({ dialogRef })

const step = ref(0)
const STEPS = [
  { id: 'prefix', title: '什么是提示词缓存' },
  { id: 'breakpoints', title: '断点放在哪' },
  { id: 'cost', title: '写入与命中的成本' },
  { id: 'ttl', title: '缓存能活多久' },
  { id: 'vendors', title: '各厂商怎么写' },
  { id: 'apply', title: '应用到当前预设' },
  { id: 'probe', title: '可选探测' },
] as const

const draft = ref<PromptCacheConfig>(defaultPromptCacheConfig())
const allowProbe = ref(false)
const applied = ref(false)

watch(
  () => [props.show, props.connection] as const,
  ([open]) => {
    if (!open) return
    step.value = 0
    applied.value = false
    allowProbe.value = false
    draft.value = { ...defaultPromptCacheConfig(), ...(props.connection?.promptCache ?? {}) }
    if (!draft.value.breakpoints?.length) draft.value.breakpoints = ['system']
  },
)

const progress = computed(() => ((step.value + 1) / STEPS.length) * 100)
const isLast = computed(() => step.value === STEPS.length - 1)
const requestSnippet = computed(() => {
  const mode = draft.value.mode
  const bps = (draft.value.breakpoints || ['system']).join(', ')
  const proto = props.connection?.protocol || 'auto'
  if (mode === 'off') return '// 关闭缓存：请求体不带 cache_control / prompt_cache_*'
  if (proto === 'anthropic_messages') {
    return `// Anthropic\n{ "system": [{ "type": "text", "text": "…", "cache_control": { "type": "ephemeral"${draft.value.ttl ? `, "ttl": "${draft.value.ttl}"` : ''} } }] }\n// breakpoints: ${bps}`
  }
  if (proto === 'openai_responses') {
    return `// OpenAI Responses\n{ "prompt_cache_key": "chat:…", "prompt_cache_options": { "mode": "${mode === 'explicit' ? 'explicit' : 'implicit'}", "ttl": "30m" } }`
  }
  if (proto === 'gemini_generate_content') {
    return `// Gemini\nPOST /cachedContents { "model": "models/…", "ttl": "3600s" }\nPOST :generateContent { "cachedContent": "cachedContents/…" }`
  }
  return `// 自动 / 尽力而为\n{ "promptCache": { "mode": "${mode}", "breakpoints": [${bps}] } }`
})

function next() {
  if (isLast.value) {
    applyToConnection()
    close()
    return
  }
  step.value += 1
}
function prev() {
  if (step.value > 0) step.value -= 1
}

function applyToConnection() {
  if (!props.connection) return
  props.connection.promptCache = { ...draft.value }
  applied.value = true
}

const MODE_CARDS: Array<{ mode: PromptCacheMode; title: string; body: string }> = [
  { mode: 'auto', title: '自动', body: '按供应商目录选：Anthropic 显式、Gemini 隐式、OpenAI 官方按模型、中国厂商尽力缓存。' },
  { mode: 'explicit', title: '显式写入', body: '主动打断点 / 创建缓存。写入更贵（约 1.25×），之后命中约 0.1×。' },
  { mode: 'implicit', title: '隐式', body: '不打标记，依赖厂商自动前缀匹配（Gemini 默认、OpenAI 旧模型 retention）。' },
  { mode: 'best_effort', title: '尽力而为', body: '不发缓存字段。DeepSeek / Kimi / GLM 等硬盘前缀缓存会自己生效。' },
  { mode: 'off', title: '关闭', body: '明确不使用缓存策略。' },
]

const inputTokens = ref(8000)
const cachedRatio = computed(() => Math.min(0.92, Math.max(0.35, (draft.value.breakpoints?.length ?? 1) * 0.28)))
const writeCost = computed(() => Math.round(inputTokens.value * 1.25))
const hitCost = computed(() => Math.round(inputTokens.value * cachedRatio.value * 0.1 + inputTokens.value * (1 - cachedRatio.value)))
</script>

<template>
  <Teleport to="body">
    <Transition name="modal">
      <div v-if="show" class="fixed inset-0 z-[80] flex items-center justify-center p-3 sm:p-6">
        <div class="absolute inset-0 bg-[color-mix(in_srgb,var(--color-bg)_55%,transparent)] backdrop-blur-md" @click="close" />
        <div
          ref="dialogRef"
          v-bind="dialogAttrs"
          tabindex="-1"
          class="surface-panel relative flex h-[92vh] w-full max-w-5xl flex-col overflow-hidden border border-[var(--color-border-subtle)]"
          data-testid="prompt-cache-guide"
        >
          <header class="flex items-center justify-between gap-3 border-b border-[var(--color-border-subtle)] px-4 py-3">
            <div class="min-w-0">
              <h2 :id="titleId" class="truncate text-sm font-semibold text-[var(--color-text)]">缓存原理与断点教学</h2>
              <p class="text-2xs text-[var(--color-text-muted)]">第 {{ step + 1 }} / {{ STEPS.length }} 步 · {{ STEPS[step]?.title }}</p>
            </div>
            <button type="button" class="icon-button p-1.5" aria-label="关闭教学" @click="close">
              <X class="h-4 w-4" />
            </button>
          </header>
          <div class="h-1 bg-[var(--color-track)]">
            <div class="cache-guide-progress h-full bg-brand" :style="{ width: `${progress}%` }" />
          </div>

          <div class="drawer-scroll min-h-0 flex-1 overflow-y-auto px-5 py-4 custom-scrollbar">
            <!-- 1 前缀 -->
            <section v-if="step === 0" class="space-y-4">
              <p class="text-sm leading-6 text-[var(--color-text-secondary)]">
                大模型按<strong class="text-[var(--color-text)]">从左到右的前缀</strong>计算 KV 缓存。角色卡、世界观、工具定义如果每轮一字不差地排在最前面，第二次请求就能「命中」已经算过的部分，只付很少的读缓存费。
              </p>
              <div class="flex flex-col gap-2 font-mono text-2xs">
                <div class="cache-block cache-block--stable flex overflow-hidden rounded-xl">
                  <span class="cache-fill flex-[3] px-3 py-3">角色卡 / System（稳定前缀）</span>
                  <span class="flex-[1] bg-[var(--color-glass-l2)] px-3 py-3 text-[var(--color-text-muted)]">本轮用户</span>
                </div>
                <div class="cache-block cache-block--stable flex overflow-hidden rounded-xl">
                  <span class="cache-fill flex-[3] px-3 py-3">同一前缀 → 缓存命中</span>
                  <span class="flex-[1] bg-[var(--color-glass-l2)] px-3 py-3">新的一句</span>
                </div>
              </div>
              <p class="text-2xs leading-5 text-[var(--color-text-muted)]">
                如果 system 里夹了「当前时间」「随机种子」或每轮都变的状态表，前缀就断了，缓存会整段失效。
              </p>
            </section>

            <!-- 2 断点 -->
            <section v-else-if="step === 1" class="space-y-4">
              <p class="text-sm leading-6 text-[var(--color-text-secondary)]">
                显式缓存需要告诉上游「写到这里」。断点必须落在<strong class="text-[var(--color-text)]">不会每轮改动</strong>的块尾部。GPT-5.6+ 若不打断点，写入会静默失败。
              </p>
              <ol class="space-y-2 text-sm">
                <li class="rounded-xl border border-brand/30 bg-brand-a10 px-3 py-2">1. System / 角色卡 — 几乎总该选</li>
                <li class="rounded-xl border border-[var(--color-border-subtle)] px-3 py-2">2. 工具定义 — 助手开了工具时选</li>
                <li class="rounded-xl border border-[var(--color-border-subtle)] px-3 py-2">3. 历史尾部 — 多轮对话滚动前缀，提高命中</li>
              </ol>
              <p class="text-2xs text-[var(--color-text-muted)]">Anthropic 最多 4 个断点；顶层 cache_control 会自动落到最后一个可缓存块。</p>
            </section>

            <!-- 3 成本 -->
            <section v-else-if="step === 2" class="space-y-4">
              <p class="text-sm leading-6 text-[var(--color-text-secondary)]">
                以 OpenAI 官方定价量级估算：写入约 1.25 倍输入价，命中约 0.1 倍。拖动输入长度看两次请求的相对花费。
              </p>
              <label class="block space-y-1">
                <span class="text-2xs text-[var(--color-text-muted)]">输入 token：{{ inputTokens }}</span>
                <input v-model.number="inputTokens" type="range" min="1024" max="32000" step="256" class="w-full" />
              </label>
              <div class="grid gap-3 sm:grid-cols-2">
                <div class="rounded-xl bg-[var(--color-glass-l2)] p-3">
                  <div class="text-2xs text-[var(--color-text-muted)]">第一次（写入）</div>
                  <div class="text-lg font-semibold">{{ writeCost }} <span class="text-xs font-normal text-[var(--color-text-muted)]">相对单位</span></div>
                </div>
                <div class="rounded-xl bg-[var(--color-glass-l2)] p-3">
                  <div class="text-2xs text-[var(--color-text-muted)]">第二次（命中约 {{ Math.round(cachedRatio * 100) }}%）</div>
                  <div class="text-lg font-semibold text-brand">{{ hitCost }} <span class="text-xs font-normal text-[var(--color-text-muted)]">相对单位</span></div>
                </div>
              </div>
            </section>

            <!-- 4 TTL -->
            <section v-else-if="step === 3" class="space-y-4">
              <p class="text-sm leading-6 text-[var(--color-text-secondary)]">各厂 TTL 是硬枚举，不能自己发明时长。教学页会帮你选，后端再翻译成该协议合法值。</p>
              <div class="relative mx-auto h-28 w-28">
                <div class="cache-hourglass absolute inset-0 rounded-full border-4 border-brand/40" />
                <div class="absolute inset-4 rounded-full bg-brand/20" />
              </div>
              <ul class="space-y-1 text-sm text-[var(--color-text-secondary)]">
                <li>Anthropic：5 分钟 / 1 小时</li>
                <li>GPT-5.6+ Responses：固定 30 分钟 + 显式断点</li>
                <li>更早 OpenAI：内存短缓存 或 24 小时 retention</li>
                <li>Gemini 显式 cachedContents：秒（默认 3600）</li>
                <li>百炼显式标记：固定 5 分钟</li>
              </ul>
            </section>

            <!-- 5 厂商 -->
            <section v-else-if="step === 4" class="grid gap-3 sm:grid-cols-2">
              <article class="rounded-xl border border-[var(--color-border-subtle)] p-3">
                <h3 class="text-sm font-medium">OpenAI</h3>
                <p class="mt-1 text-2xs leading-5 text-[var(--color-text-muted)]">Responses：prompt_cache_key + options/断点；Chat：仅 key/retention（官方/Azure）。</p>
              </article>
              <article class="rounded-xl border border-[var(--color-border-subtle)] p-3">
                <h3 class="text-sm font-medium">Anthropic</h3>
                <p class="mt-1 text-2xs leading-5 text-[var(--color-text-muted)]">块级 cache_control；history_tail 走顶层 cache_control。</p>
              </article>
              <article class="rounded-xl border border-[var(--color-border-subtle)] p-3">
                <h3 class="text-sm font-medium">Gemini</h3>
                <p class="mt-1 text-2xs leading-5 text-[var(--color-text-muted)]">隐式默认开；显式会创建 cachedContents，404 重建一次。</p>
              </article>
              <article class="rounded-xl border border-[var(--color-border-subtle)] p-3">
                <h3 class="text-sm font-medium">中国厂商</h3>
                <p class="mt-1 text-2xs leading-5 text-[var(--color-text-muted)]">DeepSeek 硬盘缓存自动；百炼可在消息上打 ephemeral 标记。</p>
              </article>
            </section>

            <!-- 6 应用 -->
            <section v-else-if="step === 5" class="space-y-3">
              <p class="text-sm text-[var(--color-text-secondary)]">选一种模式写入当前正在编辑的预设 / 全局连接。下一步可以关闭教学。</p>
              <div class="grid gap-2 sm:grid-cols-2">
                <button
                  v-for="card in MODE_CARDS"
                  :key="card.mode"
                  type="button"
                  class="rounded-xl border p-3 text-left transition-colors"
                  :class="draft.mode === card.mode ? 'border-brand bg-brand-a10' : 'border-[var(--color-border-subtle)] hover:bg-[var(--color-glass-l2)]'"
                  @click="draft.mode = card.mode"
                >
                  <div class="text-sm font-medium">{{ card.title }}</div>
                  <p class="mt-1 text-2xs leading-4 text-[var(--color-text-muted)]">{{ card.body }}</p>
                </button>
              </div>
              <p class="rounded-lg bg-[var(--color-glass-l2)] px-3 py-2 font-mono text-2xs text-[var(--color-text-muted)]">
                将使用：mode={{ draft.mode }} · breakpoints={{ (draft.breakpoints || ['system']).join(',') }}
              </p>
              <pre class="overflow-x-auto rounded-lg bg-[var(--color-glass-l2)] px-3 py-2 font-mono text-2xs leading-5 text-[var(--color-text-secondary)]">{{ requestSnippet }}</pre>
              <button type="button" class="btn btn-sm btn-secondary" @click="applyToConnection">
                <Check class="h-3.5 w-3.5" />
                {{ applied ? '已写入当前预设' : '现在写入当前预设' }}
              </button>
            </section>

            <!-- 7 探测 -->
            <section v-else class="space-y-3">
              <p class="text-sm leading-6 text-[var(--color-text-secondary)]">
                真实探测需要你的 API Key 连发两次相同前缀。默认关闭，避免意外扣费。
              </p>
              <button type="button" class="flex items-center gap-2 text-sm" @click="allowProbe = !allowProbe">
                <ThemedCheckbox :checked="allowProbe" />
                我了解费用，允许以后在 HTTP 日志里核对 cache 读写（本页不自动发请求）
              </button>
              <p class="text-2xs text-[var(--color-text-muted)]">
                完成后看消息气泡的「缓存命中」徽标，或设置 → 查看 HTTP 请求里的 usage.cacheReadInputTokens。
              </p>
            </section>
          </div>

          <footer class="flex items-center justify-between gap-2 border-t border-[var(--color-border-subtle)] px-4 py-3">
            <button type="button" class="btn btn-sm btn-secondary" :disabled="step === 0" @click="prev">
              <ArrowLeft class="h-3.5 w-3.5" />
              上一步
            </button>
            <button type="button" class="btn btn-sm btn-primary" data-testid="cache-guide-next" @click="next">
              <Sparkles v-if="isLast" class="h-3.5 w-3.5" />
              <ArrowRight v-else class="h-3.5 w-3.5" />
              {{ isLast ? '完成并写入' : '下一步' }}
            </button>
          </footer>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.cache-guide-progress {
  transition: width 280ms ease;
}
.cache-fill {
  background: color-mix(in srgb, var(--color-brand, #7c6af7) 28%, transparent);
  color: var(--color-text);
}
.cache-block--stable .cache-fill {
  animation: cache-shimmer 2.4s ease-in-out infinite;
}
.cache-hourglass {
  animation: cache-spin 8s linear infinite;
}
@media (prefers-reduced-motion: reduce) {
  .cache-guide-progress,
  .cache-block--stable .cache-fill,
  .cache-hourglass {
    animation: none;
    transition: none;
  }
}
@keyframes cache-shimmer {
  0%,
  100% { filter: brightness(1); }
  50% { filter: brightness(1.15); }
}
@keyframes cache-spin {
  to { transform: rotate(360deg); }
}
</style>
