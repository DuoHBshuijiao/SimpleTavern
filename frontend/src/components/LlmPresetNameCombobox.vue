<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ChevronDown, X } from 'lucide-vue-next'
import { LLM_PROVIDER_PRESETS, type LlmProviderPreset } from '../constants/llmProviderPresets'

const DROPDOWN_GAP_PX = 6
const PANEL_MAX_PX = 224
const PANEL_MIN_PX = 96

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
const dropdownOpen = ref(false)
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
    nextTick(() => {
      updateDropdownPlacement()
      bindPlacementListeners()
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
      <div
        class="overflow-y-auto p-1 custom-scrollbar"
        :style="{ maxHeight: `${panelMaxHeightPx}px` }"
      >
        <button
          v-for="preset in presets"
          :key="preset.id"
          type="button"
          class="flex w-full flex-col items-start gap-0.5 rounded-lg px-3 py-2 text-left transition-colors hover:bg-surface-hover"
          @click="choosePreset(preset)"
        >
          <div class="w-full truncate text-xs font-medium text-[var(--color-text-secondary)]">
            {{ preset.label }}
          </div>
          <div class="w-full truncate text-[10px] text-[var(--color-text-muted)]">
            <template v-if="preset.requiresManualEdit">需替换占位符 · </template>{{ preset.baseUrl }}
          </div>
        </button>
        <div v-if="presets.length === 0" class="px-3 py-3 text-xs text-[var(--color-text-muted)]">
          暂无供应商
        </div>
      </div>
    </div>
  </div>
</template>
