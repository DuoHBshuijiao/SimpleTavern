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
 * - 请求预览：展开后显示当前模型的实际协议、思考深度和缓存策略
 */
import { computed, ref, watch } from 'vue'
import { ExternalLink, Loader2 } from 'lucide-vue-next'
import DisclosureSummary from '../common/DisclosureSummary.vue'
import SettingsField from './SettingsField.vue'
import SettingsHint from './SettingsHint.vue'
import SettingsSwitch from './SettingsSwitch.vue'
import ModernSelect from '../ModernSelect.vue'
import ThemedCheckbox from '../ThemedCheckbox.vue'
import type { LlmCatalogProvider } from '../../api/llm'
import { VERTEX_SERVICE_ACCOUNT_AUTH_STYLE } from '../../types/models'
import { useProtocolPreview, describeAdjustment, PROMPT_CACHE_MODE_LABELS } from '../../composables/useProtocolPreview'
import {
  PROMPT_CACHE_BREAKPOINTS,
  PROMPT_CACHE_MODE_OPTIONS,
  REASONING_EFFORT_SHORT_LABELS,
  defaultPromptCacheConfig,
  normalizeReasoningEffort,
  type PromptCacheBreakpoint,
  type PromptCacheConfig,
  type PromptCacheMode,
} from '../../types/models'

/** 预设 / 全局连接的公共子集 */
export interface LlmConnectionLike {
  webSearchSearchEnabled?: boolean | null
  webSearchFetchEnabled?: boolean | null
  baseUrl: string
  protocol?: string | null
  providerId?: string | null
  providerParams?: Record<string, string> | null
  authStyle?: string | null
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
  }>(),
  {
    models: () => [],
    catalogProvider: null,
    reasoningEffort: 'none',
    globalEchoBack: 'preset',
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
const cacheModeHint = computed(() => cacheModeDisabledReason(cache.value.mode) ?? undefined)

const strategy = computed(() => String(props.catalogProvider?.cacheStrategy || '').toLowerCase())
const proto = computed(() => props.connection.protocol || 'auto')
const dashscopeMarkers = computed(() => Boolean(props.catalogProvider?.explicitCacheMarkers))

function cacheModeDisabledReason(mode: PromptCacheMode): string | null {
  if (mode === 'off' || mode === 'auto') return null
  if (strategy.value === 'none') return '目录标明该供应商不提供 prompt cache'
  if (mode === 'explicit') {
    if (proto.value === 'mistral_conversations') return 'Mistral Conversations 没有显式缓存参数'
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
    if (proto.value !== 'anthropic_messages' && proto.value !== 'bedrock_converse' && proto.value !== 'auto') return '仅 Anthropic Messages / Bedrock Converse 使用 5m / 1h'
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
      label,
      value,
      disabled: Boolean(reason),
      hint: reason || undefined,
    })
  }
  if (p === 'anthropic_messages' || p === 'bedrock_converse' || p === 'auto') {
    push('5 分钟', '5m')
    push('1 小时（Anthropic）', '1h')
  }
  if (p === 'openai_responses' || p === 'openai_compatible_chat' || p === 'auto') {
    push('30 分钟', '30m')
    push('24 小时', '24h')
  }
  if (p === 'gemini_generate_content' || p === 'auto') {
    push('1 小时（Gemini）', '3600')
    push('6 小时', '21600')
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
  system: '系统提示与角色卡',
  tools: '工具定义',
  history_tail: '对话历史末尾',
}
const responsesCache = computed(() => proto.value === 'openai_responses' ||
  (proto.value === 'auto' && preview.value?.effective === 'openai_responses'))

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
  if (proto.value === 'mistral_conversations') return 'Mistral Conversations 没有缓存断点'
  return null
})
const markersDisabledReason = computed(() => {
  if (strategy.value === 'none') return '该供应商不提供 prompt cache'
  if (!dashscopeMarkers.value) return '仅百炼等声明了 explicitCacheMarkers 的供应商需要消息级标记'
  return null
})

const cacheKeyOptions = [
  { label: '按会话', value: 'per_chat' },
  { label: '按角色', value: 'per_character' },
  { label: '不指定', value: 'off' },
]

const showBreakpoints = computed(() => !breakpointsDisabledReason.value && !responsesCache.value)

// ---- 供应商参数 ------------------------------------------------------------

const linkedWeb = computed(() => props.connection.protocol === 'openai_responses' || ['openai', 'openai-chatgpt', 'openai-codex'].includes(props.connection.providerId || '') || props.models.some(m => /^(gpt|o[134])/.test(m)))
function setSearchEnabled(enabled: boolean) {
  props.connection.webSearchSearchEnabled = enabled
  if (linkedWeb.value) props.connection.webSearchFetchEnabled = enabled
}
/** 服务账号鉴权时，项目 ID 和位置和账号信息一起显示在 VertexServiceAccountFields 里，这里不重复 */
const placeholders = computed(() => {
  const list = props.catalogProvider?.placeholders ?? []
  if (props.connection.authStyle !== VERTEX_SERVICE_ACCOUNT_AUTH_STYLE) return list
  return list.filter((ph) => ph.key !== 'project' && ph.key !== 'location')
})
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
const effectiveEcho = computed(() => echoOverriddenByGlobal.value ? props.globalEchoBack === 'on' : echo.value)
const needsEcho = computed(() => props.catalogProvider?.id === 'deepseek' ||
  props.models.some((model) => /(^|\/)deepseek[-/]/i.test(model)))

// ---- 预览 --------------------------------------------------------------------

const previewModel = ref('')
const advancedOpen = ref(false)
const previewOpen = ref(false)
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
      authStyle: props.connection.authStyle ?? null,
      promptCache: cache.value,
      reasoningEffort: props.reasoningEffort ?? 'none',
      fastMode: false,
      echoReasoning: effectiveEcho.value,
    }
  },
  { debounceMs: 260, enabled: () => previewOpen.value || (advancedOpen.value && proto.value === 'auto') },
)
const requestBlocker = computed(() => preview.value?.adjustments.find((item) => item.type === 'capability_unsupported')?.reason)
const previewAdjustments = computed(() => preview.value?.adjustments.filter((item) => item.type !== 'capability_unsupported') ?? [])

</script>

<template>
  <section v-if="placeholders.length" class="settings-group" data-settings-field="providerParams">
    <div class="settings-field-head">
      <div class="settings-group-title">供应商参数</div>
      <a
        v-if="catalogProvider?.docsUrl"
        :href="catalogProvider.docsUrl"
        target="_blank"
        rel="noreferrer"
        class="inline-flex shrink-0 items-center gap-1 text-sm text-brand hover:underline"
      >
        官方文档 <ExternalLink class="h-3 w-3" aria-hidden="true" />
      </a>
    </div>
    <div class="grid gap-3 sm:grid-cols-2">
      <SettingsField v-for="ph in placeholders" :key="ph.key" :label="ph.label || ph.key" :more="ph.hint || undefined">
        <input
          :value="paramValue(ph.key)"
          type="text"
          class="input w-full"
          :placeholder="ph.example || ph.key"
          @input="setParam(ph.key, ($event.target as HTMLInputElement).value)"
        />
      </SettingsField>
    </div>
  </section>

  <details class="settings-group" @toggle="advancedOpen = ($event.currentTarget as HTMLDetailsElement).open">
    <DisclosureSummary class="settings-group-title min-h-10 py-1">高级设置</DisclosureSummary>
    <div class="py-2">
      <section class="settings-group" data-settings-field="webSearchSource">
        <SettingsHint title="原生联网" more="会话使用供应商原生联网时，这些开关才会生效。" />
        <SettingsSwitch
          :label="linkedWeb ? '搜索和网页读取' : '允许搜索'"
          :model-value="connection.webSearchSearchEnabled !== false"
          @update:model-value="setSearchEnabled"
        />
        <SettingsSwitch
          v-if="!linkedWeb"
          label="允许网页读取"
          :model-value="connection.webSearchFetchEnabled !== false"
          @update:model-value="(v) => { connection.webSearchFetchEnabled = v }"
        />
      </section>

      <section class="settings-group" data-settings-field="promptCache">
        <div class="settings-field-head">
          <div class="settings-group-title">提示词缓存</div>
                <button type="button" class="btn btn-link shrink-0" @click="emit('open-cache-guide')">
            缓存指南
          </button>
        </div>
        <SettingsField :hint="cacheModeHint">
          <ModernSelect
            :model-value="cache.mode"
            :options="cacheModeOptions"
            class="w-full"
            placeholder="选择缓存模式"
            @update:model-value="(v) => { if (!cacheModeDisabledReason(String(v) as PromptCacheMode)) cache = { ...cache, mode: String(v) as PromptCacheMode } }"
          />
        </SettingsField>

        <template v-if="cache.mode !== 'off'">
          <SettingsField label="缓存时长">
            <ModernSelect
              :model-value="ttlValue"
              :options="ttlOptions"
              class="w-full"
              placeholder="供应商默认"
              @update:model-value="(v) => { if (!ttlDisabledReason(String(v))) ttlValue = String(v) }"
            />
          </SettingsField>
          <SettingsField v-if="!cacheKeyDisabledReason" label="缓存范围" more="按会话独立缓存，或让同一角色的不同会话共享缓存。">
            <ModernSelect
              :model-value="cache.cacheKey || 'per_chat'"
              :options="cacheKeyOptions"
              class="w-full"
              @update:model-value="(v) => (cache = { ...cache, cacheKey: String(v) })"
            />
          </SettingsField>

          <SettingsField v-if="showBreakpoints" label="缓存断点">
            <div class="flex flex-col gap-2">
              <label
                v-for="bp in PROMPT_CACHE_BREAKPOINTS"
                :key="bp"
                class="inline-flex items-center gap-2 text-sm text-[var(--color-text-secondary)]"
                :class="bp === 'system' ? 'opacity-60' : 'cursor-pointer'"
              >
                <ThemedCheckbox
                  :aria-label="BREAKPOINT_LABELS[bp]"
                  :checked="bp === 'system' || hasBreakpoint(bp)"
                  :disabled="bp === 'system'"
                  @update:checked="toggleBreakpoint(bp)"
                />
                <span>{{ BREAKPOINT_LABELS[bp] }}</span>
              </label>
            </div>
          </SettingsField>
          <SettingsSwitch
            v-if="!markersDisabledReason"
            label="标记要缓存的消息"
            :model-value="!!cache.explicitMarkers"
            @update:model-value="(v) => (cache = { ...cache, explicitMarkers: v })"
          />
        </template>
      </section>

      <section class="settings-group" data-settings-field="echoReasoning">
        <SettingsSwitch
          v-model="echo"
          label="回传思考内容"
          :hint="needsEcho && !effectiveEcho ? 'DeepSeek 调用工具时需要回传思考内容。' : undefined"
          more="发送下一条消息时附上上一轮的思考内容。"
        />
        <SettingsHint v-if="echoOverriddenByGlobal">
          当前由全局设置「{{ globalEchoBack === 'on' ? '全部回传' : '全部不回传' }}」控制。
        </SettingsHint>
      </section>
    </div>
  </details>

  <details @toggle="previewOpen = ($event.currentTarget as HTMLDetailsElement).open">
    <DisclosureSummary class="settings-group-title min-h-10 py-1">请求预览</DisclosureSummary>
    <div class="flex min-w-0 flex-col gap-3 pt-2">
      <ModernSelect
        v-if="previewModelOptions.length"
        :model-value="previewModel"
        :options="previewModelOptions"
        class="w-full"
        searchable
        allow-create
        placeholder="选择模型"
        @update:model-value="(v) => (previewModel = String(v))"
      />
      <input v-else v-model="previewModel" type="text" class="input w-full" aria-label="预览模型" placeholder="输入模型名称" />
      <div v-if="loading" class="flex items-center gap-2 text-sm text-[var(--color-text-secondary)]" role="status">
        <Loader2 class="h-4 w-4 animate-spin" aria-hidden="true" />
        正在生成预览
      </div>
      <p v-else-if="error && previewModel.trim()" class="text-sm text-[var(--color-error-text)]">预览失败。{{ error }}</p>
      <template v-else-if="preview && previewModel.trim()">
        <SettingsHint v-if="requestBlocker">{{ requestBlocker }}</SettingsHint>
        <dl class="settings-readout grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-1 text-sm">
          <dt>协议</dt>
          <dd class="break-words text-[var(--color-text)]">{{ preview.effectiveLabel }}</dd>
          <dt>思考深度</dt>
          <dd class="text-[var(--color-text)]">{{ REASONING_EFFORT_SHORT_LABELS[normalizeReasoningEffort(preview.effort)] }}</dd>
          <template v-if="preview.cache">
            <dt>缓存</dt>
            <dd class="text-[var(--color-text)]">{{ PROMPT_CACHE_MODE_LABELS[preview.cache.mode] ?? preview.cache.mode }}</dd>
          </template>
        </dl>
        <details>
          <DisclosureSummary class="py-1 text-sm text-secondary">技术详情</DisclosureSummary>
          <div class="space-y-2 break-words pt-2 text-sm text-[var(--color-text-secondary)]">
            <p v-if="preview.providerLabel">供应商 {{ preview.providerLabel }}</p>
            <p>Fast {{ preview.supportsFastMode ? '支持' : '不支持' }}，能力来源 {{ preview.capabilitiesSource }}</p>
            <p v-if="preview.availableEfforts.length">可用思考档位 {{ preview.availableEfforts.join(' / ') }}</p>
            <p v-if="preview.cache?.ttl != null">缓存时长 {{ preview.cache.ttl }}{{ typeof preview.cache.ttl === 'number' ? ' 秒' : '' }}</p>
            <p v-if="preview.cache?.breakpoints?.length">断点 {{ preview.cache.breakpoints.join(' / ') }}</p>
            <ul v-if="previewAdjustments.length || preview.reasons.length" class="list-disc space-y-1 pl-5">
              <li v-for="(adj, i) in previewAdjustments" :key="`${adj.type}-${i}`">{{ describeAdjustment(adj) }}</li>
              <li v-for="reason in preview.reasons" :key="reason">{{ reason }}</li>
            </ul>
          </div>
        </details>
      </template>
      <a
        v-if="catalogProvider?.docsUrl && !placeholders.length"
        :href="catalogProvider.docsUrl"
        target="_blank"
        rel="noreferrer"
        class="inline-flex w-fit items-center gap-1 text-sm text-brand hover:underline"
      >
        供应商文档 <ExternalLink class="h-3 w-3" aria-hidden="true" />
      </a>
    </div>
  </details>
</template>
