<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ChevronDown, KeyRound, Search, X } from 'lucide-vue-next'
import { LLM_PROVIDER_PRESETS, groupProviderPresets, LLM_CACHE_STRATEGY_LABELS, type LlmProviderPreset } from '../constants/llmProviderPresets'
import { LLM_PROTOCOL_SHORT_LABELS } from '../constants/llmProtocols'

const DROPDOWN_GAP_PX = 6
const PANEL_MAX_PX = 320
const PANEL_MIN_PX = 120

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
const dropdownPlacement = ref<'down' | 'up'>('down')
const panelMaxHeightPx = ref(PANEL_MAX_PX)

function updateDropdownPlacement() {
  const root = rootRef.value
  if (!root) return

  const rect = root.getBoundingClientRect()
  const viewportH = window.innerHeight
  const spaceBelow = viewportH - rect.bottom - DROPDOWN_GAP_PX
  const spaceAbove = rect.top - DROPDOWN_GAP_PX

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
  if (event.target instanceof Node && root.contains(event.target)) return
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
    nextTick(() => {
      updateDropdownPlacement()
      bindPlacementListeners()
      searchInputRef.value?.focus()
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
      class="input input-sm w-full pr-20"
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

    <div
      v-if="dropdownOpen"
      class="absolute left-0 right-0 z-40 overflow-hidden rounded-xl border border-[var(--color-border-subtle)] bg-surface-overlay shadow-xl backdrop-blur-[var(--glass-blur-popover)]"
      :class="
        dropdownPlacement === 'down'
          ? 'top-[calc(100%+0.375rem)] bottom-auto'
          : 'bottom-[calc(100%+0.375rem)] top-auto'
      "
    >
      <div class="border-b border-[var(--color-border-subtle)] p-1.5">
        <label class="relative block">
          <Search class="pointer-events-none absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[var(--color-text-muted)]" />
          <input
            ref="searchInputRef"
            v-model="filterQuery"
            type="text"
            class="input input-sm w-full !pl-7"
            placeholder="搜索厂商 / 关键词 / 模型名…"
            aria-label="搜索供应商"
            @keydown.stop
          />
        </label>
      </div>
      <div
        class="overflow-y-auto p-1 custom-scrollbar"
        :style="{ maxHeight: `${panelMaxHeightPx}px` }"
      >
        <template v-for="group in groupedPresets" :key="group.group">
          <div class="px-2 pt-1.5 pb-0.5 text-2xs font-bold uppercase tracking-wider text-[var(--color-text-muted)]">
            {{ group.label }}
          </div>
          <button
            v-for="preset in group.items"
            :key="preset.id"
            type="button"
            class="flex w-full flex-col items-start gap-0.5 rounded-lg px-3 py-2 text-left transition-colors hover:bg-surface-hover"
            @click="choosePreset(preset)"
          >
            <div class="flex w-full min-w-0 items-center gap-1.5">
              <span class="min-w-0 truncate text-xs font-medium text-[var(--color-text-secondary)]">{{ preset.label }}</span>
              <span
                v-for="b in protocolBadges(preset)"
                :key="b"
                class="shrink-0 rounded bg-[var(--color-glass-l2)] px-1 py-px text-2xs leading-none text-[var(--color-text-muted)]"
              >{{ b }}</span>
              <span
                v-if="preset.cacheStrategy && preset.cacheStrategy !== 'none'"
                class="shrink-0 rounded bg-brand-a15 px-1 py-px text-2xs leading-none text-brand"
              >{{ LLM_CACHE_STRATEGY_LABELS[preset.cacheStrategy] ?? preset.cacheStrategy }}</span>
              <span
                v-else-if="preset.cacheStrategy === 'none'"
                class="shrink-0 rounded bg-[var(--color-glass-l2)] px-1 py-px text-2xs leading-none text-[var(--color-text-muted)]"
              >无缓存</span>
              <span
                v-if="preset.requiresOAuth"
                class="inline-flex shrink-0 items-center gap-0.5 rounded bg-[color-mix(in_srgb,var(--color-warning)_18%,transparent)] px-1 py-px text-2xs leading-none text-[var(--color-warning-text,var(--color-warning))]"
              ><KeyRound class="h-2.5 w-2.5" />登录</span>
              <span
                v-else-if="preset.requiresManualEdit"
                class="shrink-0 rounded bg-brand-a15 px-1 py-px text-2xs leading-none text-brand"
              >需参数</span>
            </div>
            <div class="w-full truncate text-2xs text-[var(--color-text-muted)]">
              {{ preset.baseUrl || '（地址由参数生成）' }}
            </div>
          </button>
        </template>
        <div v-if="totalVisible === 0" class="px-3 py-3 text-xs text-[var(--color-text-muted)]">
          {{ presets.length === 0 ? '暂无供应商' : '无匹配厂商；可直接在名称框输入自定义名称' }}
        </div>
      </div>
    </div>
  </div>
</template>
