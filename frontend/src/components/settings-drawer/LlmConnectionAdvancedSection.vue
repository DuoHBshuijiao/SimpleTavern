<script setup lang="ts">
/**
 * LlmConnectionAdvancedSection - LLM 连接高级区块（v0.810 T-820 / T-821 / T-822）
 *
 * API 预设编辑器与全局连接区共用。直接就地修改传入的 connection 对象（与 SettingsDrawer 草稿模式一致）。
 *
 * 包含：
 * - 供应商参数（providerParams）：名录里带占位符的厂商（Azure resource / Cloudflare account_id / Bedrock region）
 * - 缓存策略（promptCache）：模式 / TTL / 断点 / cache key + 「查看原理」入口
 * - 回传思考内容（echoReasoning）：带 data-settings-field，供错误卡片深链定位
 * - 「这次会怎么发」预览：按第一个模型（或手输模型名）实时展示协议 / 深度 / Fast / 缓存 / 调整
 */
import { computed, ref, watch } from 'vue'
import { BookOpen, ExternalLink, Loader2, Sparkles } from 'lucide-vue-next'
import ModernSelect from '../ModernSelect.vue'
import ThemedCheckbox from '../ThemedCheckbox.vue'
import type { LlmCatalogProvider } from '../../api/llm'
import { useProtocolPreview, describeAdjustment, PROMPT_CACHE_MODE_LABELS } from '../../composables/useProtocolPreview'
import {
  PROMPT_CACHE_BREAKPOINTS,
  PROMPT_CACHE_MODE_OPTIONS,
  defaultPromptCacheConfig,
  type PromptCacheBreakpoint,
  type PromptCacheConfig,
  type PromptCacheMode,
} from '../../types/models'

/** 预设 / 全局连接的公共子集 */
export interface LlmConnectionLike {
  baseUrl: string
  protocol?: string | null
  providerId?: string | null
  providerParams?: Record<string, string> | null
  promptCache?: PromptCacheConfig | null
  echoReasoning?: boolean | null
  anthropicPromptCache?: string | null
}

const props = withDefaults(
  defineProps<{
    connection: LlmConnectionLike
    /** 预览用模型候选（预设 models / 全局 defaultModel + candidates） */
    models?: string[]
    /** 名录条目（有则显示占位符表单与文档链接） */
    catalogProvider?: LlmCatalogProvider | null
    /** 全局 reasoningEffort，用于预览默认深度 */
    reasoningEffort?: string | null
    /** 全局「回传思考内容」三态；on/off 时预设开关被覆盖，给出提示 */
    globalEchoBack?: string | null
    compact?: boolean
  }>(),
  {
    models: () => [],
    catalogProvider: null,
    reasoningEffort: 'none',
    globalEchoBack: 'preset',
    compact: false,
  },
)

const emit = defineEmits<{
  (e: 'open-cache-guide'): void
}>()

// ---- promptCache 就地初始化 ------------------------------------------------

const cache = computed<PromptCacheConfig>({
  get() {
    if (!props.connection.promptCache) {
      // 旧字段迁移：anthropicPromptCache 5m/1h → explicit + ttl；off → auto（与后端 prompt_cache_from_legacy 一致的可见行为）
      const legacy = props.connection.anthropicPromptCache
      const base = defaultPromptCacheConfig()
      if (legacy === '5m' || legacy === '1h') {
        base.mode = 'explicit'
        base.ttl = legacy
      }
      props.connection.promptCache = base
    }
    return props.connection.promptCache!
  },
  set(v) {
    props.connection.promptCache = v
  },
})

const cacheModeOptions = computed(() =>
  PROMPT_CACHE_MODE_OPTIONS.map((o) => {
    const reason = cacheModeDisabledReason(o.value)
    return {
      label: reason ? `${o.label}（不可用）` : o.label,
      value: o.value,
      disabled: Boolean(reason),
      hint: reason || o.hint,
    }
  }),
)
const cacheModeHint = computed(() => {
  const reason = cacheModeDisabledReason(cache.value.mode)
  if (reason) return reason
  return PROMPT_CACHE_MODE_OPTIONS.find((o) => o.value === cache.value.mode)?.hint ?? ''
})

const strategy = computed(() => String(props.catalogProvider?.cacheStrategy || '').toLowerCase())
const proto = computed(() => props.connection.protocol || 'auto')
const dashscopeMarkers = computed(() => Boolean(props.catalogProvider?.explicitCacheMarkers))

function cacheModeDisabledReason(mode: PromptCacheMode): string | null {
  if (mode === 'off' || mode === 'auto') return null
  if (strategy.value === 'none') return '目录标明该供应商不提供 prompt cache'
  if (mode === 'explicit') {
    if (strategy.value === 'implicit' && proto.value !== 'gemini_generate_content' && proto.value !== 'auto' && proto.value !== 'anthropic_messages' && proto.value !== 'openai_responses') {
      return '该供应商以自动前缀缓存为主，没有显式断点 API'
    }
    if (strategy.value === 'best_effort' && !dashscopeMarkers.value && proto.value === 'openai_compatible_chat') {
      return '该 OpenAI 兼容端点没有显式缓存参数'
    }
  }
  if (mode === 'implicit' && proto.value === 'anthropic_messages') {
    return 'Anthropic 只有显式 cache_control，选隐式会被改成显式'
  }
  return null
}

function ttlDisabledReason(value: string): string | null {
  if (!value) return null
  if (strategy.value === 'none') return '该供应商不提供 prompt cache'
  if (value === '5m' || value === '1h') {
    if (proto.value !== 'anthropic_messages' && proto.value !== 'auto') return '仅 Anthropic Messages 使用 5m / 1h'
  }
  if (value === '30m' || value === '24h') {
    if (proto.value !== 'openai_responses' && proto.value !== 'openai_compatible_chat' && proto.value !== 'auto') {
      return '仅 OpenAI Chat / Responses 使用 30m / 24h'
    }
  }
  if (value === '3600' || value === '21600') {
    if (proto.value !== 'gemini_generate_content' && proto.value !== 'auto') return '仅 Gemini cachedContents 使用秒级 TTL'
  }
  return null
}

/** TTL 选项按协议家族给出；无效组合禁选并带原因 */
const ttlOptions = computed(() => {
  const p = proto.value
  const opts: Array<{ label: string; value: string; disabled?: boolean; hint?: string }> = [{ label: '供应商默认', value: '' }]
  const push = (label: string, value: string) => {
    const reason = ttlDisabledReason(value)
    opts.push({
      label: reason ? `${label}（${reason}）` : label,
      value,
      disabled: Boolean(reason),
      hint: reason || undefined,
    })
  }
  if (p === 'anthropic_messages' || p === 'auto') {
    push('5 分钟（Anthropic 默认）', '5m')
    push('1 小时（Anthropic 长缓存）', '1h')
  }
  if (p === 'openai_responses' || p === 'openai_compatible_chat' || p === 'auto') {
    push('30 分钟（GPT-5.6+ 显式断点）', '30m')
    push('24 小时（OpenAI retention）', '24h')
  }
  if (p === 'gemini_generate_content' || p === 'auto') {
    push('1 小时（Gemini cachedContents 3600s）', '3600')
    push('6 小时（Gemini 21600s）', '21600')
  }
  return opts
})
const ttlValue = computed({
  get: () => (cache.value.ttl == null ? '' : String(cache.value.ttl)),
  set: (v: string) => {
    const trimmed = String(v ?? '').trim()
    if (!trimmed) cache.value = { ...cache.value, ttl: null }
    else if (/^\d+$/.test(trimmed)) cache.value = { ...cache.value, ttl: Number(trimmed) }
    else cache.value = { ...cache.value, ttl: trimmed }
  },
})

const BREAKPOINT_LABELS: Record<PromptCacheBreakpoint, string> = {
  system: 'System / 角色卡（最稳定，必选）',
  tools: '工具定义',
  history_tail: '历史尾部（滚动前缀：多轮对话命中率更高）',
}
function hasBreakpoint(bp: PromptCacheBreakpoint) {
  return (cache.value.breakpoints ?? ['system']).includes(bp)
}
function toggleBreakpoint(bp: PromptCacheBreakpoint) {
  if (bp === 'system') return
  const cur = new Set(cache.value.breakpoints ?? ['system'])
  if (cur.has(bp)) cur.delete(bp)
  else cur.add(bp)
  cur.add('system')
  cache.value = { ...cache.value, breakpoints: PROMPT_CACHE_BREAKPOINTS.filter((x) => cur.has(x)) }
}

const cacheKeyDisabledReason = computed(() => {
  if (strategy.value === 'none') return '该供应商不提供 prompt cache'
  if (proto.value !== 'openai_responses' && proto.value !== 'openai_compatible_chat' && proto.value !== 'auto') {
    return 'prompt_cache_key 仅 OpenAI Chat / Responses 生效'
  }
  return null
})
const breakpointsDisabledReason = computed(() => {
  if (cache.value.mode !== 'explicit' && cache.value.mode !== 'auto') return '仅显式 / 自动模式会打断点'
  if (proto.value === 'openai_compatible_chat') return 'Chat Completions 没有内容块断点'
  if (proto.value === 'gemini_generate_content') return 'Gemini 显式缓存走 cachedContents，不在消息上打断点'
  return null
})
const markersDisabledReason = computed(() => {
  if (strategy.value === 'none') return '该供应商不提供 prompt cache'
  if (!dashscopeMarkers.value) return '仅百炼等声明了 explicitCacheMarkers 的供应商需要消息级标记'
  return null
})

const cacheKeyOptions = [
  { label: '按会话（每个聊天独立前缀）', value: 'per_chat' },
  { label: '按角色（同角色多会话共享）', value: 'per_character' },
  { label: '不派生 cache key', value: 'off' },
]

const showExplicitControls = computed(() => cache.value.mode === 'explicit' || cache.value.mode === 'auto')

// ---- 供应商参数 ------------------------------------------------------------

const placeholders = computed(() => props.catalogProvider?.placeholders ?? [])
function paramValue(key: string): string {
  return props.connection.providerParams?.[key] ?? ''
}
function setParam(key: string, value: string) {
  props.connection.providerParams = { ...(props.connection.providerParams ?? {}), [key]: value }
}

// ---- 回传思考 ----------------------------------------------------------------

const echo = computed({
  get: () => props.connection.echoReasoning !== false,
  set: (v: boolean) => {
    props.connection.echoReasoning = v
  },
})
const echoOverriddenByGlobal = computed(() => props.globalEchoBack === 'on' || props.globalEchoBack === 'off')

// ---- 预览 --------------------------------------------------------------------

const previewModel = ref('')
watch(
  () => props.models,
  (list) => {
    if (!previewModel.value && list.length) previewModel.value = list[0] ?? ''
  },
  { immediate: true },
)
const previewModelOptions = computed(() => props.models.map((m) => ({ label: m, value: m })))

const { preview, loading, error } = useProtocolPreview(
  () => {
    if (!previewModel.value.trim()) return null
    return {
      baseUrl: props.connection.baseUrl,
      model: previewModel.value.trim(),
      protocol: props.connection.protocol ?? null,
      providerId: props.connection.providerId ?? null,
      providerParams: props.connection.providerParams ?? null,
      promptCache: cache.value,
      reasoningEffort: props.reasoningEffort ?? 'none',
      fastMode: false,
      echoReasoning: echo.value,
    }
  },
  { debounceMs: 260 },
)

const cacheSummary = computed(() => {
  const c = preview.value?.cache
  if (!c) return null
  const mode = PROMPT_CACHE_MODE_LABELS[c.mode] ?? c.mode
  const ttl = c.ttl != null && c.ttl !== '' ? `，TTL ${typeof c.ttl === 'number' ? `${c.ttl}s` : c.ttl}` : ''
  const bps = c.breakpoints?.length ? `，断点：${c.breakpoints.join(' / ')}` : ''
  return `${mode}${ttl}${bps}`
})
</script>

<template>
  <div class="space-y-4">
    <!-- 供应商参数 -->
    <div v-if="placeholders.length" class="space-y-2" data-settings-field="providerParams">
      <div class="flex items-center justify-between gap-2">
        <label class="block text-xs font-medium text-[var(--color-text-secondary)]">供应商参数</label>
        <a
          v-if="catalogProvider?.docsUrl"
          :href="catalogProvider.docsUrl"
          target="_blank"
          rel="noreferrer"
          class="inline-flex items-center gap-1 text-2xs text-brand hover:underline"
        >
          官方文档 <ExternalLink class="h-3 w-3" />
        </a>
      </div>
      <div class="grid gap-2 sm:grid-cols-2">
        <label v-for="ph in placeholders" :key="ph.key" class="block space-y-1">
          <span class="text-2xs text-[var(--color-text-muted)]">{{ ph.label || ph.key }}</span>
          <input
            :value="paramValue(ph.key)"
            type="text"
            class="input input-sm w-full"
            :placeholder="ph.example || ph.key"
            @input="setParam(ph.key, ($event.target as HTMLInputElement).value)"
          />
          <span v-if="ph.hint" class="block text-2xs text-[var(--color-text-muted)]">{{ ph.hint }}</span>
        </label>
      </div>
      <p class="text-2xs text-[var(--color-text-muted)]">
        地址模板：<code class="font-mono">{{ catalogProvider?.baseUrlTemplate }}</code>；保存后由后端按参数生成，缺参会明确报错。
      </p>
    </div>
    <p v-else-if="catalogProvider?.hint" class="rounded-lg bg-[var(--color-glass-l2)] px-3 py-2 text-2xs leading-4 text-[var(--color-text-secondary)]">
      {{ catalogProvider.hint }}
      <a v-if="catalogProvider.docsUrl" :href="catalogProvider.docsUrl" target="_blank" rel="noreferrer" class="ml-1 inline-flex items-center gap-0.5 text-brand hover:underline">
        文档 <ExternalLink class="h-3 w-3" />
      </a>
    </p>

    <!-- 缓存策略 -->
    <section class="space-y-2 rounded-xl border border-[var(--color-border-subtle)] p-3" data-settings-field="promptCache">
      <div class="flex items-center justify-between gap-2">
        <label class="block text-xs font-medium text-[var(--color-text-secondary)]">提示词缓存策略</label>
        <button type="button" class="inline-flex items-center gap-1 text-2xs text-brand hover:underline" @click="emit('open-cache-guide')">
          <BookOpen class="h-3 w-3" />
          缓存原理与断点教学
        </button>
      </div>
      <ModernSelect
        :model-value="cache.mode"
        :options="cacheModeOptions"
        class="w-full"
        placeholder="选择缓存模式…"
        @update:model-value="(v) => { if (!cacheModeDisabledReason(String(v) as PromptCacheMode)) cache = { ...cache, mode: String(v) as PromptCacheMode } }"
      />
      <p class="text-2xs leading-4 text-[var(--color-text-muted)]">{{ cacheModeHint }}</p>

      <template v-if="cache.mode !== 'off'">
        <div class="grid gap-2 sm:grid-cols-2">
          <div class="space-y-1">
            <span class="block text-2xs text-[var(--color-text-muted)]">缓存 TTL</span>
            <ModernSelect :model-value="ttlValue" :options="ttlOptions" class="w-full" placeholder="供应商默认" @update:model-value="(v) => { if (!ttlDisabledReason(String(v))) (ttlValue = String(v)) }" />
          </div>
          <div class="space-y-1">
            <span class="block text-2xs text-[var(--color-text-muted)]">缓存键（OpenAI prompt_cache_key）</span>
            <ModernSelect
              :model-value="cache.cacheKey || 'per_chat'"
              :options="cacheKeyOptions"
              class="w-full"
              :disabled="Boolean(cacheKeyDisabledReason)"
              @update:model-value="(v) => (cache = { ...cache, cacheKey: String(v) })"
            />
            <p v-if="cacheKeyDisabledReason" class="text-2xs text-[var(--color-text-muted)]">{{ cacheKeyDisabledReason }}</p>
          </div>
        </div>

        <div v-if="showExplicitControls" class="space-y-1">
          <span class="block text-2xs text-[var(--color-text-muted)]">显式断点位置（Anthropic cache_control / GPT-5.6+ prompt_cache_breakpoint）</span>
          <p v-if="breakpointsDisabledReason" class="text-2xs text-[var(--color-text-muted)]">{{ breakpointsDisabledReason }}</p>
          <div class="flex flex-col gap-1" :class="breakpointsDisabledReason ? 'pointer-events-none opacity-60' : ''">
            <button
              v-for="bp in PROMPT_CACHE_BREAKPOINTS"
              :key="bp"
              type="button"
              class="inline-flex items-center gap-2 text-left text-xs text-[var(--color-text-secondary)] transition-colors hover:text-[var(--color-text)]"
              :class="bp === 'system' ? 'cursor-default opacity-80' : ''"
              @click="toggleBreakpoint(bp)"
            >
              <ThemedCheckbox :checked="hasBreakpoint(bp)" />
              <span>{{ BREAKPOINT_LABELS[bp] }}</span>
            </button>
          </div>
        </div>

        <button
          type="button"
          class="inline-flex items-center gap-2 text-left text-xs text-[var(--color-text-secondary)] transition-colors hover:text-[var(--color-text)]"
          :class="markersDisabledReason ? 'opacity-60' : ''"
          :disabled="Boolean(markersDisabledReason)"
          @click="cache = { ...cache, explicitMarkers: !cache.explicitMarkers }"
        >
          <ThemedCheckbox :checked="!!cache.explicitMarkers" />
          <span>在消息上打显式缓存标记（百炼 DashScope 等中国厂商需要）</span>
        </button>
        <p v-if="markersDisabledReason" class="text-2xs text-[var(--color-text-muted)]">{{ markersDisabledReason }}</p>
      </template>
    </section>

    <!-- 回传思考内容 -->
    <section class="space-y-1.5 rounded-xl border border-[var(--color-border-subtle)] p-3" data-settings-field="echoReasoning">
      <button
        type="button"
        class="flex w-full items-center justify-between gap-3 text-left"
        role="switch"
        :aria-checked="echo"
        @click="echo = !echo"
      >
        <span class="min-w-0">
          <span class="block text-xs font-medium text-[var(--color-text-secondary)]">回传思考内容（reasoning_content）</span>
          <span class="block text-2xs leading-4 text-[var(--color-text-muted)]">
            开：把上一轮 assistant 的思考链一并发回（DeepSeek 带工具调用时<b>必须</b>开启）；关：省 token，多数厂商可接受。
          </span>
        </span>
        <span class="relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors" :class="echo ? 'bg-brand' : 'bg-[var(--color-track)]'">
          <span class="absolute h-4 w-4 rounded-full bg-[var(--color-on-brand)] shadow transition-transform" :class="echo ? 'translate-x-4' : 'translate-x-0.5'" />
        </span>
      </button>
      <p v-if="echoOverriddenByGlobal" class="text-2xs text-[var(--color-warning-text,var(--color-warning))]">
        全局设置当前为「{{ globalEchoBack === 'on' ? '全部回传' : '全部不回传' }}」，会覆盖此处开关；改回「按预设」才生效。
      </p>
    </section>

    <!-- 预览 -->
    <section class="space-y-2 rounded-xl bg-[var(--color-glass-l2)] p-3">
      <div class="flex flex-wrap items-center justify-between gap-2">
        <span class="inline-flex items-center gap-1.5 text-xs font-medium text-[var(--color-text-secondary)]">
          <Sparkles class="h-3.5 w-3.5 text-brand" />
          这次会怎么发
          <Loader2 v-if="loading" class="h-3 w-3 animate-spin text-[var(--color-text-muted)]" />
        </span>
        <div class="min-w-[10rem] flex-1 sm:max-w-[16rem]">
          <ModernSelect
            v-if="previewModelOptions.length"
            :model-value="previewModel"
            :options="previewModelOptions"
            class="w-full !text-xs"
            searchable
            allow-create
            placeholder="选择要预览的模型"
            @update:model-value="(v) => (previewModel = String(v))"
          />
          <input v-else v-model="previewModel" type="text" class="input input-sm w-full" placeholder="输入模型名预览（如 claude-opus-4-6）" />
        </div>
      </div>
      <div v-if="preview" class="space-y-1 text-2xs leading-4 text-[var(--color-text-secondary)]">
        <div class="flex flex-wrap gap-x-3 gap-y-1">
          <span>协议：<b class="font-medium text-[var(--color-text)]">{{ preview.effectiveLabel }}</b><span v-if="preview.requested === 'auto'" class="ml-1 rounded bg-brand-a15 px-1 text-brand">自动</span></span>
          <span>思考：<b class="font-medium text-[var(--color-text)]">{{ preview.effort }}</b><span class="text-[var(--color-text-muted)]">（可用：{{ preview.availableEfforts.join(' / ') || '—' }}）</span></span>
          <span>Fast：{{ preview.supportsFastMode ? '支持' : '不支持' }}</span>
          <span v-if="preview.providerLabel">供应商：{{ preview.providerLabel }}</span>
          <span>能力来源：{{ preview.capabilitiesSource }}</span>
        </div>
        <div v-if="cacheSummary">缓存：{{ cacheSummary }}</div>
        <ul v-if="preview.adjustments.length" class="list-disc space-y-0.5 pl-4 text-[var(--color-text-muted)]">
          <li v-for="(adj, i) in preview.adjustments" :key="`${adj.type}-${i}`">{{ describeAdjustment(adj) }}</li>
        </ul>
        <ul v-if="preview.reasons.length" class="space-y-0.5 text-[var(--color-text-muted)]">
          <li v-for="(r, i) in preview.reasons" :key="i">· {{ r }}</li>
        </ul>
      </div>
      <p v-else-if="error" class="text-2xs text-[var(--color-error-text)]">预览失败：{{ error }}</p>
      <p v-else class="text-2xs text-[var(--color-text-muted)]">选择或输入一个模型名即可看到协议 / 思考深度 / 缓存的真实落地方式。</p>
    </section>
  </div>
</template>
