<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ChevronDown, KeyRound, Search, X } from 'lucide-vue-next'
import { LLM_PROVIDER_PRESETS, groupProviderPresets, LLM_CACHE_STRATEGY_LABELS, type LlmProviderPreset } from '../constants/llmProviderPresets'
import { LLM_PROTOCOL_SHORT_LABELS } from '../constants/llmProtocols'

const DROPDOWN_GAP_PX = 6
const PANEL_MAX_PX = 420
/** 搜索框那一条的高度，算列表可用高度时要扣掉 */
const PANEL_HEADER_PX = 46
const PANEL_MIN_PX = 120
const VIEWPORT_GUTTER_PX = 8
const PANEL_MIN_WIDTH_PX = 380

const props = withDefaults(
  defineProps<{
    modelValue: string
    presets?: LlmProviderPreset[]
    disabled?: boolean
    placeholder?: string
  }>(),
  {
    presets: () => LLM_PROVIDER_PRESETS,
    disabled: false,
    placeholder: '输入或下拉选择供应商/预设名称',
  },
)

const emit = defineEmits<{
  (e: 'update:modelValue', value: string): void
  (e: 'select', preset: LlmProviderPreset): void
}>()

const rootRef = ref<HTMLElement | null>(null)
const panelRef = ref<HTMLElement | null>(null)
const searchInputRef = ref<HTMLInputElement | null>(null)
const dropdownOpen = ref(false)
/** 面板内独立搜索框：不用主输入框筛选，默认名称如「新 API 预设」不会挡住整表 */
const filterQuery = ref('')

const groupedPresets = computed(() => {
  const q = filterQuery.value.trim().toLowerCase()
  const list = q
    ? props.presets.filter((p) => {
        const hay = [p.label, p.name, p.id, p.baseUrl, ...(p.keywords || []), ...(p.suggestedModels || [])].join(' ').toLowerCase()
        return hay.includes(q)
      })
    : props.presets
  return groupProviderPresets(list)
})

const totalVisible = computed(() => groupedPresets.value.reduce((n, g) => n + g.items.length, 0))

function protocolBadges(p: LlmProviderPreset): string[] {
  const list = (p.supportedProtocols || []).filter((x) => x !== 'auto')
  return list.map((x) => LLM_PROTOCOL_SHORT_LABELS[x] ?? x)
}
function cacheLabel(p: LlmProviderPreset): string {
  if (!p.cacheStrategy) return ''
  return LLM_CACHE_STRATEGY_LABELS[p.cacheStrategy] ?? p.cacheStrategy
}
const dropdownPlacement = ref<'down' | 'up'>('down')
const panelMaxHeightPx = ref(PANEL_MAX_PX)
/**
 * 面板 Teleport 到 body 用 fixed 定位：留在设置抽屉里时，抽屉面板自己的 backdrop-filter
 * 会让里面这层模糊失效（嵌套 backdrop-filter），所以必须脱离抽屉。
 */
const panelStyle = ref<Record<string, string>>({})

function updateDropdownPlacement() {
  const root = rootRef.value
  if (!root) return

  const rect = root.getBoundingClientRect()
  const viewportH = window.innerHeight
  const reserved = DROPDOWN_GAP_PX + VIEWPORT_GUTTER_PX + PANEL_HEADER_PX
  const spaceBelow = viewportH - rect.bottom - reserved
  const spaceAbove = rect.top - reserved

  const clampMax = (space: number) =>
    Math.min(PANEL_MAX_PX, Math.max(PANEL_MIN_PX, Math.floor(space)))

  if (spaceBelow >= PANEL_MAX_PX) {
    dropdownPlacement.value = 'down'
    panelMaxHeightPx.value = PANEL_MAX_PX
  } else if (spaceAbove >= PANEL_MAX_PX) {
    dropdownPlacement.value = 'up'
    panelMaxHeightPx.value = PANEL_MAX_PX
  } else if (spaceBelow >= spaceAbove) {
    dropdownPlacement.value = 'down'
    panelMaxHeightPx.value = clampMax(spaceBelow)
  } else {
    dropdownPlacement.value = 'up'
    panelMaxHeightPx.value = clampMax(spaceAbove)
  }

  // 三行里的协议标签要排得下：面板不窄于 PANEL_MIN_WIDTH_PX，右边对齐输入框，多出来的宽度向左伸
  const width = Math.min(Math.max(rect.width, PANEL_MIN_WIDTH_PX), window.innerWidth - VIEWPORT_GUTTER_PX * 2)
  const left = Math.max(VIEWPORT_GUTTER_PX, rect.right - width)
  const style: Record<string, string> = {
    position: 'fixed',
    left: `${left}px`,
    width: `${width}px`,
  }
  if (dropdownPlacement.value === 'down') {
    style.top = `${rect.bottom + DROPDOWN_GAP_PX}px`
  } else {
    style.bottom = `${viewportH - rect.top + DROPDOWN_GAP_PX}px`
  }
  panelStyle.value = style
}

let placementListenersBound = false
function onPlacementInvalidate() {
  if (dropdownOpen.value) updateDropdownPlacement()
}

function bindPlacementListeners() {
  if (placementListenersBound) return
  placementListenersBound = true
  window.addEventListener('resize', onPlacementInvalidate)
  window.visualViewport?.addEventListener('resize', onPlacementInvalidate)
  window.addEventListener('scroll', onPlacementInvalidate, true)
}

function unbindPlacementListeners() {
  if (!placementListenersBound) return
  placementListenersBound = false
  window.removeEventListener('resize', onPlacementInvalidate)
  window.visualViewport?.removeEventListener('resize', onPlacementInvalidate)
  window.removeEventListener('scroll', onPlacementInvalidate, true)
}

/** 不按输入框筛选：默认名称如「新 API 预设」不应挡住整表下拉。 */
function handleDocumentPointerDown(event: PointerEvent) {
  const root = rootRef.value
  if (!root) return
  if (event.target instanceof Node && (root.contains(event.target) || panelRef.value?.contains(event.target))) return
  dropdownOpen.value = false
}

function toggleDropdown() {
  if (props.disabled) return
  dropdownOpen.value = !dropdownOpen.value
}

function choosePreset(preset: LlmProviderPreset) {
  emit('update:modelValue', preset.name)
  emit('select', preset)
  dropdownOpen.value = false
}

function onPanelKeydown(event: KeyboardEvent) {
  // 面板已不在抽屉的 DOM 里，按键不该再冒泡到全局快捷键
  event.stopPropagation()
  if (event.key !== 'Escape') return
  event.preventDefault()
  dropdownOpen.value = false
}

function onInput(e: Event) {
  const t = e.target as HTMLInputElement
  emit('update:modelValue', t.value)
}

function clearInput() {
  if (props.disabled) return
  emit('update:modelValue', '')
}

onMounted(() => {
  document.addEventListener('pointerdown', handleDocumentPointerDown)
})

onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', handleDocumentPointerDown)
  unbindPlacementListeners()
})

watch(dropdownOpen, (open) => {
  if (open) {
    filterQuery.value = ''
    updateDropdownPlacement()
    bindPlacementListeners()
    nextTick(() => {
      searchInputRef.value?.focus({ preventScroll: true })
    })
  } else {
    unbindPlacementListeners()
  }
})
</script>

<template>
  <div ref="rootRef" class="relative">
    <input
      :value="modelValue"
      type="text"
      class="input w-full pr-20"
      :placeholder="placeholder"
      :disabled="disabled"
      @input="onInput"
    />
    <div class="absolute inset-y-1 right-1 flex items-center gap-0.5">
      <button
        type="button"
        class="inline-flex h-full min-h-0 w-8 shrink-0 items-center justify-center rounded-md text-[var(--color-text-muted)] transition-colors hover:bg-surface-hover hover:text-[var(--color-text-secondary)] disabled:pointer-events-none disabled:opacity-40"
        :disabled="disabled || !modelValue.trim()"
        aria-label="清空"
        @click.stop="clearInput"
      >
        <X class="h-4 w-4" stroke-width="2.5" />
      </button>
      <button
        type="button"
        class="inline-flex h-full min-h-0 w-8 shrink-0 items-center justify-center rounded-md text-[var(--color-text-muted)] transition-colors hover:bg-surface-hover hover:text-[var(--color-text-secondary)]"
        :disabled="disabled"
        aria-label="展开供应商列表"
        @click="toggleDropdown"
      >
        <ChevronDown class="h-4 w-4" :class="dropdownOpen ? 'rotate-180' : ''" />
      </button>
    </div>

    <Teleport to="body">
      <Transition name="select-dropdown-pop">
        <div
          v-if="dropdownOpen"
          ref="panelRef"
          class="preset-combobox-panel z-dropdown flex flex-col overflow-hidden rounded-xl border border-[var(--color-border)] bg-[color-mix(in_srgb,var(--color-glass-l6)_62%,transparent)] shadow-xl backdrop-blur-[var(--glass-blur-popover)]"
          :class="dropdownPlacement === 'down' ? 'select-dropdown-pop--bottom' : 'select-dropdown-pop--top'"
          :style="panelStyle"
          @keydown="onPanelKeydown"
        >
          <div class="shrink-0 border-b border-[var(--color-border-subtle)] p-1.5">
            <label class="relative block">
              <Search class="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[var(--color-text-muted)]" />
              <input
                ref="searchInputRef"
                v-model="filterQuery"
                type="text"
                class="input input-sm w-full !pl-8"
                placeholder="搜索厂商、模型或地址"
                aria-label="搜索供应商"
              />
            </label>
          </div>
          <div
            class="min-h-0 overflow-y-auto p-1 custom-scrollbar"
            :style="{ maxHeight: `${panelMaxHeightPx}px` }"
          >
            <template v-for="group in groupedPresets" :key="group.group">
              <div class="px-2.5 pt-2 pb-1 text-2xs font-bold tracking-wider text-[var(--color-text-muted)]">
                {{ group.label }}
              </div>
              <button
                v-for="preset in group.items"
                :key="preset.id"
                type="button"
                class="preset-combobox-item flex w-full flex-col items-stretch gap-1 rounded-lg px-2.5 py-2 text-left transition-colors hover:bg-surface-hover"
                :class="{ 'bg-brand-a10': preset.name === modelValue }"
                @click="choosePreset(preset)"
              >
                <div class="flex min-w-0 items-center gap-2">
                  <span class="preset-combobox-name min-w-0 flex-1 truncate text-sm font-medium text-[var(--color-text)]">{{ preset.label }}</span>
                  <span
                    v-if="preset.requiresOAuth"
                    class="preset-combobox-chip preset-combobox-chip--warn inline-flex items-center gap-0.5"
                  ><KeyRound class="h-2.5 w-2.5" />登录</span>
                  <span
                    v-else-if="preset.requiresManualEdit"
                    class="preset-combobox-chip preset-combobox-chip--brand"
                  >需参数</span>
                </div>
                <div
                  v-if="protocolBadges(preset).length || cacheLabel(preset)"
                  class="flex min-w-0 flex-wrap items-center gap-1"
                >
                  <span
                    v-for="b in protocolBadges(preset)"
                    :key="b"
                    class="preset-combobox-chip"
                  >{{ b }}</span>
                  <span
                    v-if="cacheLabel(preset)"
                    class="preset-combobox-chip"
                    :class="{ 'preset-combobox-chip--brand': preset.cacheStrategy !== 'none' }"
                  >{{ cacheLabel(preset) }}</span>
                </div>
                <div class="truncate font-mono text-2xs text-[var(--color-text-muted)]">
                  {{ preset.baseUrl || '地址由参数生成' }}
                </div>
              </button>
            </template>
            <div v-if="totalVisible === 0" class="px-3 py-3 text-xs text-[var(--color-text-muted)]">
              {{ presets.length === 0 ? '暂无供应商' : '没有匹配的厂商，可以直接在名称框里输入' }}
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<style>
/* 面板 Teleport 到 body，所以不能用 scoped */
.preset-combobox-chip {
  flex-shrink: 0;
  border-radius: 0.25rem;
  padding: 0.125rem 0.375rem;
  font-size: var(--text-2xs);
  line-height: 1.2;
  color: var(--color-text-secondary);
  background-color: var(--color-glass-l2);
}
.preset-combobox-chip--brand {
  color: var(--color-brand);
  background-color: var(--color-brand-a15);
}
.preset-combobox-chip--warn {
  color: var(--color-warning-text, var(--color-warning));
  background-color: color-mix(in srgb, var(--color-warning) 18%, transparent);
}
</style>
