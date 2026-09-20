<script setup lang="ts">
/**
 * ModelControlPanel - 聊天模型控制面板（v0.810 T-824）
 *
 * 组件职责：
 * - 触发区：一颗胶囊按钮，显示当前模型 + 思考深度徽标 + Fast 徽标
 * - 弹层：模型搜索 / 分组列表（与原 ModernSelect 选项结构兼容）+ 思考深度分段控件 + Fast 开关
 * - 实时预览：切换模型时调用 /api/llm/resolve-preview，只展示该模型真正可用的思考档位、
 *   Fast 是否生效、协议是否自动切换、缓存策略是什么（T-822「可见、可配置的自适应」）
 *
 * Props：
 * - currentModel / currentPresetId / modelOptions：与 ChatInput 原 ModernSelect 相同
 * - reasoningEffort：会话级覆盖（null = 沿用全局）
 * - globalReasoningEffort：全局档位（展示「沿用全局 · 中」）
 * - fastMode：会话级 Fast（null = 沿用全局 false）
 * - disabled / placement
 *
 * Emits：
 * - select-model(option)：与 ModernSelect 的 select 一致（含 presetId）
 * - update:reasoningEffort(value | null)
 * - update:fastMode(boolean | null)
 */
import { computed, ref, watch } from 'vue'
import { Brain, Check, ChevronDown, Loader2, Search, Sparkles, Zap } from 'lucide-vue-next'
import SelectDropdownSurface from '../SelectDropdownSurface.vue'
import { useSettingsStore } from '../../stores'
import { useProtocolPreview, describeAdjustment, PROMPT_CACHE_MODE_LABELS } from '../../composables/useProtocolPreview'
import {
  REASONING_EFFORT_SHORT_LABELS,
  REASONING_EFFORT_VALUES,
  normalizeReasoningEffort,
  type ReasoningEffort,
} from '../../types/models'
import { isTtsApiPreset } from '../../utils/apiPresetKind'

interface ModelOption {
  label: string
  value: string
  presetId?: string | null
}

interface ModelOptionGroup {
  label: string
  options: ModelOption[]
}

const props = withDefaults(
  defineProps<{
    currentModel: string
    currentPresetId?: string | null
    modelOptions: (ModelOption | ModelOptionGroup | string)[]
    reasoningEffort?: ReasoningEffort | string | null
    globalReasoningEffort?: ReasoningEffort | string | null
    fastMode?: boolean | null
    disabled?: boolean
    placement?: 'top' | 'bottom'
    /** 弹层固定宽度（px） */
    panelWidthPx?: number
  }>(),
  {
    currentPresetId: null,
    reasoningEffort: null,
    globalReasoningEffort: 'none',
    fastMode: null,
    disabled: false,
    placement: 'top',
    panelWidthPx: 440,
  },
)

const emit = defineEmits<{
  (e: 'select-model', option: ModelOption): void
  (e: 'update:reasoningEffort', value: ReasoningEffort | null): void
  (e: 'update:fastMode', value: boolean | null): void
}>()

const settings = useSettingsStore()

const open = ref(false)
const anchorRef = ref<HTMLElement | null>(null)
const searchInputRef = ref<HTMLInputElement | null>(null)
const query = ref('')

/** 当前会话真正生效的深度：覆盖优先，否则全局 */
const effectiveEffort = computed<ReasoningEffort>(() => {
  if (props.reasoningEffort != null && props.reasoningEffort !== '') {
    return normalizeReasoningEffort(props.reasoningEffort)
  }
  return normalizeReasoningEffort(props.globalReasoningEffort)
})
const isOverridingEffort = computed(() => props.reasoningEffort != null && props.reasoningEffort !== '')
const effectiveFast = computed(() => props.fastMode === true)
const thinkingOn = computed(() => effectiveEffort.value !== 'none')
const lastNonNoneEffort = ref<ReasoningEffort>(
  normalizeReasoningEffort(props.globalReasoningEffort) === 'none'
    ? 'medium'
    : normalizeReasoningEffort(props.globalReasoningEffort),
)
watch(effectiveEffort, (v) => {
  if (v !== 'none') lastNonNoneEffort.value = v
})
const modelClampHint = ref<string | null>(null)

// ---- 模型选项 ----------------------------------------------------------

const normalizedGroups = computed<ModelOptionGroup[]>(() => {
  const groups: ModelOptionGroup[] = []
  const loose: ModelOption[] = []
  for (const opt of props.modelOptions) {
    if (typeof opt === 'string') {
      loose.push({ label: opt, value: opt })
    } else if ('options' in opt && Array.isArray(opt.options)) {
      groups.push({
        label: opt.label,
        options: opt.options.map((o) => (typeof o === 'string' ? { label: o, value: o } : o)),
      })
    } else {
      loose.push(opt as ModelOption)
    }
  }
  if (loose.length) groups.unshift({ label: '模型', options: loose })
  return groups
})

const filteredGroups = computed(() => {
  const q = query.value.trim().toLowerCase()
  if (!q) return normalizedGroups.value
  const out: ModelOptionGroup[] = []
  for (const g of normalizedGroups.value) {
    const hit = g.options.filter((o) => o.label.toLowerCase().includes(q) || o.value.toLowerCase().includes(q))
    if (hit.length) out.push({ ...g, options: hit })
  }
  return out
})

const hasAnyOption = computed(() => normalizedGroups.value.some((g) => g.options.length > 0))

function isSelected(opt: ModelOption): boolean {
  if (String(opt.value) !== String(props.currentModel ?? '')) return false
  if (props.currentPresetId == null || props.currentPresetId === '') return true
  return String(opt.presetId ?? '') === String(props.currentPresetId)
}

function pickModel(opt: ModelOption) {
  emit('select-model', opt)
  query.value = ''
}

function handleSearchEnter() {
  const first = filteredGroups.value[0]?.options[0]
  if (first) {
    pickModel(first)
    return
  }
  const typed = query.value.trim()
  if (typed) pickModel({ label: typed, value: typed })
}

// ---- 预览（协议 / 可用深度 / Fast） -------------------------------------

/** 当前预设（或全局连接）的连接参数，供预览使用 */
const connection = computed(() => {
  const s = settings.settings
  if (!s) return null
  const preset = props.currentPresetId
    ? s.apiPresets.find((p) => p.id === props.currentPresetId && !isTtsApiPreset(p))
    : s.apiPresets.find((p) => !isTtsApiPreset(p) && p.models.includes(props.currentModel))
  if (preset) {
    return {
      baseUrl: preset.baseUrl,
      protocol: preset.protocol ?? null,
      providerId: preset.providerId ?? null,
      providerParams: preset.providerParams ?? null,
      promptCache: preset.promptCache ?? null,
      echoReasoning: preset.echoReasoning ?? true,
    }
  }
  return {
    baseUrl: s.llm.baseUrl,
    protocol: s.llm.protocol ?? null,
    providerId: s.llm.providerId ?? null,
    providerParams: s.llm.providerParams ?? null,
    promptCache: s.llm.promptCache ?? null,
    echoReasoning: s.llm.echoReasoning ?? true,
  }
})

const { preview, loading: previewLoading, availableEfforts, supportsFastMode, adjustments } = useProtocolPreview(
  () => {
    const c = connection.value
    if (!c || !props.currentModel || props.currentModel === '未设置') return null
    return {
      baseUrl: c.baseUrl,
      model: props.currentModel,
      protocol: c.protocol,
      providerId: c.providerId,
      providerParams: c.providerParams,
      promptCache: c.promptCache,
      reasoningEffort: effectiveEffort.value,
      fastMode: effectiveFast.value,
      echoReasoning: c.echoReasoning,
    }
  },
  { enabled: open, debounceMs: 160 },
)

/** 深度分段：未拿到预览时全档位可点；拿到后不可用档位置灰但仍显示，保证「可见」 */
const effortChips = computed(() =>
  REASONING_EFFORT_VALUES.map((value) => ({
    value,
    label: REASONING_EFFORT_SHORT_LABELS[value],
    available: availableEfforts.value.length === 0 || availableEfforts.value.includes(value),
  })),
)

const effortClampNote = computed(() => {
  const adj = adjustments.value.find((a) => a.type === 'reasoning_effort_clamped')
  return adj ? describeAdjustment(adj) : null
})
const fastNote = computed(() => {
  const adj = adjustments.value.find((a) => a.type === 'fast_mode_unsupported')
  return adj ? describeAdjustment(adj) : null
})
const otherAdjustments = computed(() =>
  adjustments.value.filter((a) => !['reasoning_effort_clamped', 'fast_mode_unsupported', 'cache_mode_auto'].includes(a.type)),
)

const cacheLabel = computed(() => {
  const c = preview.value?.cache
  if (!c) return null
  const mode = PROMPT_CACHE_MODE_LABELS[c.mode] ?? c.mode
  const ttl = c.ttl != null && c.ttl !== '' ? ` · ${typeof c.ttl === 'number' ? `${c.ttl}s` : c.ttl}` : ''
  return `${mode}${ttl}`
})

function setEffort(value: ReasoningEffort) {
  emit('update:reasoningEffort', value)
}
function clearEffortOverride() {
  emit('update:reasoningEffort', null)
}
const canDisableThinking = computed(
  () => availableEfforts.value.length === 0 || availableEfforts.value.includes('none'),
)
function toggleThinking() {
  if (thinkingOn.value) {
    if (!canDisableThinking.value) return
    setEffort('none')
    return
  }
  setEffort(lastNonNoneEffort.value)
}
function toggleFast() {
  if (!effectiveFast.value && preview.value && !supportsFastMode.value) return
  emit('update:fastMode', effectiveFast.value ? null : true)
}

const pendingModelClamp = ref(false)
watch(
  () => props.currentModel,
  (model, prev) => {
    if (prev != null && prev !== model) pendingModelClamp.value = true
  },
)
watch(preview, (p) => {
  if (!p || !pendingModelClamp.value) return
  pendingModelClamp.value = false
  const hints: string[] = []
  const efforts = availableEfforts.value
  if (efforts.length && !efforts.includes(effectiveEffort.value)) {
    const global = normalizeReasoningEffort(props.globalReasoningEffort)
    const next = efforts.includes(global)
      ? null
      : ((efforts.find((e) => e !== 'none') ?? efforts[0]) as ReasoningEffort)
    emit('update:reasoningEffort', next)
    hints.push('已按新模型调整思考深度')
  }
  if (effectiveFast.value && !supportsFastMode.value) {
    emit('update:fastMode', null)
    hints.push('当前模型不支持 Fast，已关闭')
  }
  modelClampHint.value = hints.length ? hints.join('；') : null
})

/** 触发区徽标 */
const triggerEffortLabel = computed(() => REASONING_EFFORT_SHORT_LABELS[effectiveEffort.value])
const triggerModelLabel = computed(() => props.currentModel || '选择模型')
const triggerAriaLabel = computed(() => {
  const scope = isOverridingEffort.value ? '会话' : '全局'
  return `模型：${triggerModelLabel.value}，思考：${triggerEffortLabel.value}（${scope}），Fast：${effectiveFast.value ? '开' : '关'}`
})

watch(open, (v) => {
  if (v) {
    query.value = ''
    requestAnimationFrame(() => searchInputRef.value?.focus())
  }
})

function toggleOpen() {
  if (props.disabled) return
  open.value = !open.value
}
</script>

<template>
  <div class="relative min-w-0 w-full">
    <button
      ref="anchorRef"
      type="button"
      class="model-control-trigger flex w-full min-w-0 items-center gap-1.5 rounded-lg border border-[var(--color-border)] bg-surface-muted px-2.5 py-1.5 text-xs text-[var(--color-text)] shadow-sm transition-[background-color,border-color,box-shadow]"
      :class="[
        disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer hover:bg-surface-hover hover:border-brand-a30',
        open ? '!border-brand-a50 ring-1 ring-brand-a20' : '',
      ]"
      :aria-expanded="open"
      aria-haspopup="dialog"
      :aria-label="triggerAriaLabel"
      @click="toggleOpen"
    >
      <span class="min-w-0 flex-1 truncate text-left" :class="!currentModel || currentModel === '未设置' ? 'text-[var(--color-text-muted)]' : ''">
        {{ triggerModelLabel }}
      </span>
      <span
        class="model-control-badge inline-flex shrink-0 items-center gap-0.5 rounded-md px-1 py-0.5 text-2xs leading-none"
        :class="effectiveEffort === 'none' ? 'text-[var(--color-text-muted)] bg-[var(--color-glass-l2)]' : 'text-brand bg-brand-a15'"
        :aria-label="`思考深度 ${triggerEffortLabel}`"
      >
        <Brain class="h-3 w-3" />
        <span class="hidden sm:inline">{{ triggerEffortLabel }}</span>
      </span>
      <span
        v-if="effectiveFast"
        class="model-control-badge inline-flex shrink-0 items-center rounded-md bg-[color-mix(in_srgb,var(--color-warning)_18%,transparent)] px-1 py-0.5 text-2xs leading-none text-[var(--color-warning-text,var(--color-warning))]"
        aria-label="Fast 模式已开启"
      >
        <Zap class="h-3 w-3" />
      </span>
      <ChevronDown class="h-3 w-3 shrink-0 text-[var(--color-text-muted)] transition-transform duration-200" :class="open ? 'rotate-180' : ''" />
    </button>

    <SelectDropdownSurface
      v-model:open="open"
      :anchor-ref="anchorRef"
      :placement="placement"
      :auto-width="false"
      :fixed-width-px="panelWidthPx"
      :gap-px="8"
      prefer-bottom-sheet
      max-height-class="max-h-[min(560px,calc(100vh-5rem))]"
    >
      <template #header>
        <div class="border-b border-[var(--color-border-subtle)] p-2">
          <label class="relative block">
            <Search class="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[var(--color-text-muted)]" />
            <input
              ref="searchInputRef"
              v-model="query"
              type="text"
              class="input input-sm w-full !pl-8"
              placeholder="搜索模型，或输入新模型名后回车"
              aria-label="搜索模型"
              @keydown.enter.prevent="handleSearchEnter"
            />
          </label>
        </div>
      </template>

      <div class="model-control-panel flex flex-col gap-1" role="dialog" aria-label="模型控制面板">
        <!-- 模型列表 -->
        <div class="model-control-list max-h-[220px] overflow-y-auto custom-scrollbar pr-0.5">
          <template v-for="(group, gi) in filteredGroups" :key="`g-${gi}-${group.label}`">
            <div class="px-2 pt-1.5 pb-0.5 text-2xs font-bold uppercase tracking-wider text-[var(--color-text-muted)]">
              {{ group.label }}
            </div>
            <button
              v-for="opt in group.options"
              :key="`${group.label}:${opt.value}:${opt.presetId ?? ''}`"
              type="button"
              class="flex w-full items-center justify-between gap-2 rounded-lg px-3 py-1.5 text-left text-sm transition-colors"
              :class="isSelected(opt) ? 'bg-brand-a20 text-brand' : 'text-[var(--color-text-secondary)] hover:bg-surface-muted'"
              role="option"
              :aria-selected="isSelected(opt)"
              @click="pickModel(opt)"
            >
              <span class="min-w-0 truncate">{{ opt.label }}</span>
              <Check v-if="isSelected(opt)" class="h-3 w-3 shrink-0 text-brand" />
            </button>
          </template>
          <div v-if="filteredGroups.length === 0" class="px-3 py-4 text-center text-xs text-[var(--color-text-muted)]">
            <span v-if="query.trim()">按回车使用「{{ query.trim() }}」</span>
            <span v-else-if="!hasAnyOption">还没有模型：先在设置 → API 预设里拉取模型列表</span>
            <span v-else>无匹配项</span>
          </div>
        </div>

        <div class="mx-2 my-1 border-t border-[var(--color-border-subtle)]" />

        <section class="px-2 pb-1">
          <button
            type="button"
            class="flex w-full items-center justify-between gap-2 rounded-lg px-1 py-1.5 text-left transition-colors hover:bg-surface-muted"
            role="switch"
            :aria-checked="thinkingOn"
            :aria-disabled="thinkingOn && !canDisableThinking"
            @click="toggleThinking"
          >
            <span class="flex min-w-0 items-center gap-1.5 text-xs font-medium text-[var(--color-text)]">
              <Brain class="h-3.5 w-3.5" :class="thinkingOn ? 'text-brand' : 'text-[var(--color-text-muted)]'" />
              思考
              <span class="truncate text-2xs font-normal text-[var(--color-text-muted)]">
                {{ thinkingOn ? (canDisableThinking ? '开' : '该模型不能关闭思考') : '关 = none' }}
              </span>
            </span>
            <span
              class="relative inline-flex h-4 w-7 shrink-0 items-center rounded-full transition-colors"
              :class="thinkingOn ? 'bg-brand' : 'bg-[var(--color-glass-l3,var(--color-border))]'"
            >
              <span
                class="absolute h-3 w-3 rounded-full bg-white shadow transition-transform"
                :class="thinkingOn ? 'translate-x-3.5' : 'translate-x-0.5'"
              />
            </span>
          </button>
        </section>

        <!-- 思考深度 -->
        <section class="px-2 pb-1">
          <div class="mb-1.5 flex items-center justify-between gap-2">
            <div class="flex items-center gap-1.5 text-xs font-medium text-[var(--color-text)]">
              <Brain class="h-3.5 w-3.5 text-brand" />
              思考深度
              <Loader2 v-if="previewLoading" class="h-3 w-3 animate-spin text-[var(--color-text-muted)]" />
            </div>
            <button
              type="button"
              class="text-2xs transition-colors"
              :class="isOverridingEffort ? 'text-brand hover:underline' : 'text-[var(--color-text-muted)] cursor-default'"
              :disabled="!isOverridingEffort"
              @click="clearEffortOverride"
            >
              {{ isOverridingEffort ? '恢复沿用全局' : `沿用全局 · ${REASONING_EFFORT_SHORT_LABELS[normalizeReasoningEffort(globalReasoningEffort)]}` }}
            </button>
          </div>
          <div class="model-control-segment grid grid-cols-7 gap-1" role="radiogroup" aria-label="思考深度">
            <button
              v-for="chip in effortChips"
              :key="chip.value"
              type="button"
              role="radio"
              :aria-checked="effectiveEffort === chip.value"
              class="rounded-md px-1 py-1.5 text-2xs leading-none transition-colors"
              :class="[
                effectiveEffort === chip.value
                  ? 'bg-brand text-[var(--color-on-brand,#fff)] shadow-sm'
                  : chip.available
                    ? 'bg-[var(--color-glass-l2)] text-[var(--color-text-secondary)] hover:bg-surface-muted'
                    : 'bg-transparent text-[var(--color-text-muted)] line-through opacity-60',
              ]"
              :aria-label="chip.available ? `思考深度 ${chip.label}` : `思考深度 ${chip.label}：该模型不支持，将自动收敛到最近可用档`"
              @click="setEffort(chip.value)"
            >
              {{ chip.label }}
            </button>
          </div>
          <p v-if="modelClampHint" class="mt-1.5 text-2xs leading-4 text-[var(--color-warning-text,var(--color-warning))]">
            {{ modelClampHint }}
          </p>
          <p v-else-if="effortClampNote" class="mt-1.5 text-2xs leading-4 text-[var(--color-warning-text,var(--color-warning))]">
            {{ effortClampNote }}
          </p>
          <p v-else-if="effectiveEffort === 'none'" class="mt-1.5 text-2xs leading-4 text-[var(--color-text-muted)]">
            关闭：OpenAI reasoning.effort=none / Anthropic 不发 thinking / Gemini thinkingBudget=0 / 国内厂商 thinking.type=disabled
          </p>
        </section>

        <!-- Fast 模式 -->
        <section class="px-2 pb-1">
          <button
            type="button"
            class="flex w-full items-center justify-between gap-2 rounded-lg px-1 py-1.5 text-left transition-colors"
            :class="preview && !supportsFastMode ? 'opacity-60 cursor-not-allowed' : 'hover:bg-surface-muted'"
            role="switch"
            :aria-checked="effectiveFast"
            :aria-disabled="Boolean(preview && !supportsFastMode)"
            :disabled="Boolean(preview && !supportsFastMode)"
            @click="toggleFast"
          >
            <span class="flex min-w-0 items-center gap-1.5 text-xs font-medium text-[var(--color-text)]">
              <Zap class="h-3.5 w-3.5" :class="effectiveFast ? 'text-[var(--color-warning-text,var(--color-warning))]' : 'text-[var(--color-text-muted)]'" />
              Fast 模式
              <span class="truncate text-2xs font-normal text-[var(--color-text-muted)]">
                约 2× 计费
                <template v-if="preview"> · {{ supportsFastMode ? '优先算力' : '当前模型不支持' }}</template>
              </span>
            </span>
            <span
              class="relative inline-flex h-4 w-7 shrink-0 items-center rounded-full transition-colors"
              :class="effectiveFast ? 'bg-brand' : 'bg-[var(--color-glass-l3,var(--color-border))]'"
            >
              <span
                class="absolute h-3 w-3 rounded-full bg-white shadow transition-transform"
                :class="effectiveFast ? 'translate-x-3.5' : 'translate-x-0.5'"
              />
            </span>
          </button>
          <p v-if="effectiveFast && fastNote" class="mt-0.5 px-1 text-2xs leading-4 text-[var(--color-warning-text,var(--color-warning))]">
            {{ fastNote }}
          </p>
        </section>

        <!-- 预览：协议 / 缓存 / 其他调整 -->
        <section v-if="preview" class="mx-2 mb-2 rounded-lg bg-[var(--color-glass-l2)] px-2.5 py-2 text-2xs leading-4 text-[var(--color-text-secondary)]">
          <div class="flex flex-wrap items-center gap-x-2 gap-y-1">
            <span class="inline-flex items-center gap-1">
              <Sparkles class="h-3 w-3 text-brand" />
              协议：<b class="font-medium text-[var(--color-text)]">{{ preview.effectiveLabel }}</b>
              <span v-if="preview.requested === 'auto'" class="rounded bg-brand-a15 px-1 text-brand">自动</span>
            </span>
            <span v-if="cacheLabel">缓存：<b class="font-medium text-[var(--color-text)]">{{ cacheLabel }}</b></span>
            <span v-if="preview.providerLabel">供应商：{{ preview.providerLabel }}</span>
          </div>
          <ul v-if="otherAdjustments.length" class="mt-1 list-disc space-y-0.5 pl-4 text-[var(--color-text-muted)]">
            <li v-for="(adj, i) in otherAdjustments" :key="`${adj.type}-${i}`">{{ describeAdjustment(adj) }}</li>
          </ul>
        </section>
      </div>
    </SelectDropdownSurface>
  </div>
</template>

<style scoped>
.model-control-trigger {
  min-height: 2rem;
}

.model-control-panel {
  padding-bottom: 0.25rem;
}

@media (prefers-reduced-motion: reduce) {
  .model-control-trigger,
  .model-control-segment button {
    transition: none;
  }
}
</style>
