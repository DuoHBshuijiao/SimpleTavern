<script setup lang="ts">
/** 聊天模型、思考深度和 Fast 控件。档位以当前连接的请求预览为准。 */
import { computed, nextTick, ref, shallowRef, useId, watch } from 'vue'
import { Brain, Check, ChevronDown, Search, Zap } from 'lucide-vue-next'
import SelectDropdownSurface from '../SelectDropdownSurface.vue'
import DraggableRadioTags from '../DraggableRadioTags.vue'
import { useSettingsStore } from '../../stores'
import { useProtocolPreview } from '../../composables/useProtocolPreview'
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
    saveReasoningEffort: (value: ReasoningEffort | null) => Promise<void>
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
  (e: 'update:fastMode', value: boolean | null): void
}>()

const settings = useSettingsStore()

const open = ref(false)
const anchorRef = ref<HTMLElement | null>(null)
const searchInputRef = ref<HTMLInputElement | null>(null)
const panelRef = ref<HTMLElement | null>(null)
const modelListRef = ref<HTMLElement | null>(null)
const query = ref('')
const panelId = useId()
const listboxId = `${panelId}-models`
const activeModel = shallowRef<ModelOption | null>(null)
let pendingModelClamp: string | null = null

/** 会话覆盖或全局默认，交给后端按模型能力解析。 */
const requestedEffort = computed<ReasoningEffort>(() => {
  if (props.reasoningEffort != null && props.reasoningEffort !== '') {
    return normalizeReasoningEffort(props.reasoningEffort)
  }
  return normalizeReasoningEffort(props.globalReasoningEffort)
})
const isOverridingEffort = computed(() => props.reasoningEffort != null && props.reasoningEffort !== '')
const effectiveFast = computed(() => props.fastMode === true)
const lastNonNoneEffort = ref<ReasoningEffort>(
  normalizeReasoningEffort(props.globalReasoningEffort) === 'none'
    ? 'medium'
    : normalizeReasoningEffort(props.globalReasoningEffort),
)

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
const visibleModels = computed(() => filteredGroups.value.flatMap(group => group.options))
const activeModelId = computed(() =>
  activeModel.value && visibleModels.value.includes(activeModel.value) ? `${listboxId}-active` : undefined,
)

const selectedModel = computed(() => {
  const presetId = props.currentPresetId ?? settings.settings?.apiPresets.find(
    preset => !isTtsApiPreset(preset) && preset.models.includes(props.currentModel),
  )?.id
  const matches = (option: ModelOption) =>
    option.value === props.currentModel && (option.presetId || null) === (presetId || null)
  const groups = filteredGroups.value
  return groups.filter(group => group.label !== '最近使用').flatMap(group => group.options).find(matches)
    ?? visibleModels.value.find(matches)
})

function pickModel(opt: ModelOption) {
  pendingModelClamp = selectedModel.value && selectedModel.value.value === opt.value
    && selectedModel.value.presetId === opt.presetId ? null : opt.value
  emit('select-model', opt)
  query.value = ''
  activeModel.value = null
  searchInputRef.value?.focus({ preventScroll: true })
}

function handleSearchEnter(event: KeyboardEvent) {
  if (event.isComposing) return
  event.preventDefault()
  const option = activeModelId.value ? activeModel.value : visibleModels.value[0]
  if (option) {
    pickModel(option)
    return
  }
  const typed = query.value.trim()
  if (typed) pickModel({ label: typed, value: typed })
}

function moveModelFocus(event: KeyboardEvent, step: number) {
  if (event.isComposing || !visibleModels.value.length) return
  event.preventDefault()
  const items = visibleModels.value
  const index = activeModel.value ? items.indexOf(activeModel.value) : -1
  const start = index < 0 ? (step > 0 ? 0 : items.length - 1) : index + step
  activeModel.value = items[Math.max(0, Math.min(items.length - 1, start))] ?? null
  nextTick(() => document.getElementById(activeModelId.value ?? '')?.scrollIntoView({ block: 'nearest' }))
}

watch(query, () => {
  activeModel.value = null
  if (modelListRef.value) modelListRef.value.scrollTop = 0
})

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
      authStyle: preset.authStyle ?? null,
      promptCache: preset.promptCache ?? null,
      echoReasoning: preset.echoReasoning ?? true,
    }
  }
  return {
    baseUrl: s.llm.baseUrl,
    protocol: s.llm.protocol ?? null,
    providerId: s.llm.providerId ?? null,
    providerParams: s.llm.providerParams ?? null,
    authStyle: s.llm.authStyle ?? null,
    promptCache: s.llm.promptCache ?? null,
    echoReasoning: s.llm.echoReasoning ?? true,
  }
})

const { preview } = useProtocolPreview(
  () => {
    const c = connection.value
    if (!c || !props.currentModel || props.currentModel === '未设置') return null
    return {
      ...c,
      model: props.currentModel,
      reasoningEffort: requestedEffort.value,
      fastMode: effectiveFast.value,
    }
  },
  { enabled: () => open.value || requestedEffort.value !== 'none', debounceMs: 160 },
)

const currentPreview = computed(() => preview.value?.model === props.currentModel ? preview.value : null)
const availableEfforts = computed(() => REASONING_EFFORT_VALUES.filter(
  (effort) => currentPreview.value?.availableEfforts.includes(effort),
))
const effectiveEffort = computed(() => {
  if (!currentPreview.value || availableEfforts.value.includes(requestedEffort.value)) return requestedEffort.value
  return normalizeReasoningEffort(currentPreview.value.effort)
})
const effortOptions = computed(() => availableEfforts.value.map(value => ({
  value,
  label: REASONING_EFFORT_SHORT_LABELS[value],
  ariaLabel: `思考深度 ${REASONING_EFFORT_SHORT_LABELS[value]}`,
})))
const effortPreview = ref<ReasoningEffort | null>(null)
let effortRevision = 0
const thinkingOn = computed(() => effectiveEffort.value !== 'none')
const supportsFastMode = computed(() => currentPreview.value?.supportsFastMode === true)
const enabledEfforts = computed(() => availableEfforts.value.filter((effort) => effort !== 'none'))
const canToggleThinking = computed(() =>
  thinkingOn.value ? availableEfforts.value.includes('none') : enabledEfforts.value.length > 0,
)
watch(effectiveEffort, (effort) => {
  if (effort !== 'none') lastNonNoneEffort.value = effort
})

function clearEffortPreview() {
  effortRevision += 1
  effortPreview.value = null
}

watch([open, () => props.currentModel, () => props.currentPresetId], clearEffortPreview)

async function selectEffort(value: ReasoningEffort) {
  if (!availableEfforts.value.includes(value)) return
  const revision = ++effortRevision
  effortPreview.value = value
  try {
    await props.saveReasoningEffort(value)
  } finally {
    if (effortRevision === revision) clearEffortPreview()
  }
}

function clearEffortOverride() {
  clearEffortPreview()
  return props.saveReasoningEffort(null)
}
function toggleThinking() {
  if (!canToggleThinking.value) return
  if (thinkingOn.value) return selectEffort('none')
  const next = enabledEfforts.value.find((effort) => effort === lastNonNoneEffort.value) ?? enabledEfforts.value[0]
  if (next) return selectEffort(next)
}

function toggleFast() {
  if (supportsFastMode.value) emit('update:fastMode', effectiveFast.value ? null : true)
}

watch(currentPreview, (current) => {
  if (!current || current.model !== pendingModelClamp) return
  pendingModelClamp = null
  const efforts = availableEfforts.value
  if (efforts.length && !efforts.includes(requestedEffort.value)) {
    const global = normalizeReasoningEffort(props.globalReasoningEffort)
    const save = props.saveReasoningEffort(efforts.includes(global) ? null : effectiveEffort.value)
    if (effectiveFast.value && !current.supportsFastMode) {
      const presetId = props.currentPresetId
      return save.then(() => {
        if (props.currentModel === current.model && props.currentPresetId === presetId) {
          emit('update:fastMode', null)
        }
      })
    }
    return save
  }
  if (effectiveFast.value && !current.supportsFastMode) emit('update:fastMode', null)
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
    activeModel.value = null
    nextTick(() => searchInputRef.value?.focus({ preventScroll: true }))
  }
})

function closeAndRestoreFocus() {
  open.value = false
  anchorRef.value?.focus({ preventScroll: true })
}

function handleAnchorEscape(event: KeyboardEvent) {
  if (!open.value) return
  event.preventDefault()
  event.stopPropagation()
  closeAndRestoreFocus()
}

function handlePanelFocusOut(event: FocusEvent) {
  const next = event.relatedTarget as Node | null
  if (next && !panelRef.value?.contains(next) && next !== anchorRef.value) open.value = false
}

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
      class="select-trigger model-control-trigger min-w-0 gap-1.5 px-2.5 py-1.5 text-xs"
      :disabled="disabled"
      :aria-expanded="open"
      :aria-controls="open ? panelId : undefined"
      aria-haspopup="dialog"
      :aria-label="triggerAriaLabel"
      @click="toggleOpen"
      @keydown.esc="handleAnchorEscape"
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
      fit-to-viewport
    >
      <template #body>
        <div
          :id="panelId"
          ref="panelRef"
          class="model-control-panel"
          role="dialog"
          aria-label="模型控制面板"
          @keydown.esc.stop.prevent="closeAndRestoreFocus"
          @focusout="handlePanelFocusOut"
        >
          <div class="shrink-0 border-b border-[var(--color-border-subtle)] p-2">
            <label class="relative block">
              <Search class="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[var(--color-text-muted)]" />
              <input
                ref="searchInputRef"
                v-model="query"
                type="text"
                class="input input-sm w-full !pl-8"
                placeholder="搜索模型，或输入新模型名后回车"
                aria-label="搜索模型"
                role="combobox"
                aria-autocomplete="list"
                aria-expanded="true"
                :aria-controls="listboxId"
                :aria-activedescendant="activeModelId"
                @blur="activeModel = null"
                @keydown.down="moveModelFocus($event, 1)"
                @keydown.up="moveModelFocus($event, -1)"
                @keydown.enter="handleSearchEnter"
              />
            </label>
          </div>
          <div class="model-control-body work-area-scrollbar">
            <div ref="modelListRef" class="model-control-list work-area-scrollbar">
              <div :id="listboxId" role="listbox" aria-label="可用模型">
                <div v-for="(group, gi) in filteredGroups" :key="`g-${gi}-${group.label}`" role="group" :aria-label="group.label">
                  <div class="px-2 pt-1.5 pb-0.5 text-2xs font-bold uppercase tracking-wider text-[var(--color-text-muted)]" aria-hidden="true">
                    {{ group.label }}
                  </div>
                  <button
                    v-for="opt in group.options"
                    :key="`${group.label}:${opt.value}:${opt.presetId ?? ''}`"
                    :id="activeModel === opt ? activeModelId : undefined"
                    type="button"
                    class="select-option py-1.5"
                    role="option"
                    tabindex="-1"
                    :aria-selected="selectedModel === opt"
                    :data-active="activeModel === opt"
                    @mousedown.prevent
                    @click="pickModel(opt)"
                  >
                    <span class="min-w-0 truncate">{{ opt.label }}</span>
                    <Check v-if="selectedModel === opt" class="h-3 w-3 shrink-0 text-brand" aria-hidden="true" />
                  </button>
                </div>
              </div>
              <div v-if="filteredGroups.length === 0" class="px-3 py-4 text-center text-xs text-[var(--color-text-muted)]">
                <span v-if="query.trim()">按回车使用「{{ query.trim() }}」</span>
                <span v-else-if="!hasAnyOption">还没有模型：先在设置 → API 预设里拉取模型列表</span>
                <span v-else>无匹配项</span>
              </div>
            </div>

            <div class="model-control-settings">
              <section class="px-2 pb-1">
                <button
                  type="button"
                  class="btn btn-ghost w-full justify-between px-1 py-1.5 text-left"
                  role="switch"
                  :aria-checked="thinkingOn"
                  :disabled="!canToggleThinking"
                  @click="toggleThinking"
                >
                  <span class="flex min-w-0 items-center gap-1.5 text-xs font-medium text-[var(--color-text)]">
                    <Brain class="h-3.5 w-3.5 shrink-0" :class="thinkingOn ? 'text-brand' : 'text-[var(--color-text-muted)]'" aria-hidden="true" />
                    思考
                  </span>
                  <span
                    class="settings-switch"
                    :class="{ 'settings-switch--on': thinkingOn }"
                    aria-hidden="true"
                  >
                    <span class="settings-switch-knob" />
                  </span>
                </button>
              </section>

              <!-- 思考深度 -->
              <section class="px-2 pb-1">
                <div class="mb-1.5 flex items-center justify-between gap-2 px-1">
                  <div class="flex items-center gap-1.5 pl-5 text-xs font-medium text-[var(--color-text)]">
                    思考深度
                  </div>
                  <button
                    type="button"
                    class="btn btn-xs btn-link text-2xs"
                    :disabled="!isOverridingEffort"
                    @click="clearEffortOverride"
                  >
                    {{ isOverridingEffort ? '恢复沿用全局' : '沿用全局' }}
                  </button>
                </div>
                <DraggableRadioTags
                  v-if="effortOptions.length"
                  :key="`${currentPresetId ?? ''}:${currentModel}`"
                  :model-value="effortPreview ?? effectiveEffort"
                  :options="effortOptions"
                  ariaLabel="思考深度"
                  stretch
                  @update:model-value="selectEffort"
                />
              </section>

              <!-- Fast 模式 -->
              <section class="px-2 pb-1">
                <button
                  type="button"
                  class="btn btn-ghost w-full justify-between px-1 py-1.5 text-left"
                  role="switch"
                  :aria-checked="effectiveFast"
                  :disabled="!supportsFastMode"
                  @click="toggleFast"
                >
                  <span class="flex min-w-0 items-center gap-1.5 text-xs font-medium text-[var(--color-text)]">
                    <Zap class="h-3.5 w-3.5 shrink-0" :class="effectiveFast ? 'text-[var(--color-warning-text,var(--color-warning))]' : 'text-[var(--color-text-muted)]'" aria-hidden="true" />
                    Fast 模式
                    <span v-if="supportsFastMode" class="truncate text-2xs font-normal text-[var(--color-text-muted)]">
                      约 2× 计费
                    </span>
                    <span v-else-if="currentPreview" class="text-2xs font-normal text-[var(--color-text-muted)]">
                      当前模型或连接不支持
                    </span>
                  </span>
                  <span
                    class="settings-switch"
                    :class="{ 'settings-switch--on': effectiveFast }"
                    aria-hidden="true"
                  >
                    <span class="settings-switch-knob" />
                  </span>
                </button>
              </section>
            </div>
          </div>
        </div>
      </template>
    </SelectDropdownSurface>
  </div>
</template>

<style scoped>
.model-control-trigger {
  min-height: 2rem;
}

.model-control-panel {
  display: flex;
  flex: 1 1 auto;
  flex-direction: column;
  min-height: 0;
}

.model-control-body {
  display: flex;
  flex: 1 1 auto;
  flex-direction: column;
  min-height: 0;
}

.model-control-list {
  min-height: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
  scrollbar-gutter: stable;
  padding: 0.25rem;
}

.model-control-settings {
  flex: none;
  padding: 0.25rem 0.25rem 0;
  border-top: 1px solid var(--color-border-subtle);
}

@media (max-height: 350px) {
  .model-control-body {
    display: block;
    overflow-y: auto;
  }
  .model-control-list {
    overflow: visible;
  }
}

@media (prefers-reduced-motion: reduce) {
  .model-control-trigger {
    transition: none;
  }
}
</style>
