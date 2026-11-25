<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { ChevronDown, X } from 'lucide-vue-next'
import type { ApiPresetVoice } from '../types/models'
import SelectDropdownSurface from './SelectDropdownSurface.vue'

const DROPDOWN_GAP_PX = 6
const PANEL_MAX_PX = 224
const PANEL_MIN_PX = 96

const props = withDefaults(defineProps<{
  modelValue: string
  voices?: ApiPresetVoice[]
  disabled?: boolean
  placeholder?: string
}>(), {
  voices: () => [],
  disabled: false,
  placeholder: '填写 voice_id',
})

const emit = defineEmits<{
  (e: 'update:modelValue', value: string): void
}>()

const rootRef = ref<HTMLElement | null>(null)
const toggleRef = ref<HTMLButtonElement | null>(null)
const optionsRef = ref<HTMLElement | null>(null)
const dropdownOpen = ref(false)
/** 优先向下；空间不足时向上 */
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
  document.addEventListener('keydown', handleDropdownEscape, true)
}

function unbindPlacementListeners() {
  if (!placementListenersBound) return
  placementListenersBound = false
  window.removeEventListener('resize', onPlacementInvalidate)
  window.visualViewport?.removeEventListener('resize', onPlacementInvalidate)
  window.removeEventListener('scroll', onPlacementInvalidate, true)
  document.removeEventListener('keydown', handleDropdownEscape, true)
}

const filteredVoices = computed(() => {
  const query = props.modelValue.trim().toLowerCase()
  if (!query) return props.voices
  return props.voices.filter((voice) => {
    return voice.voiceId.toLowerCase().includes(query) || voice.name.toLowerCase().includes(query)
  })
})

function handleDropdownEscape(event: KeyboardEvent) {
  if (!dropdownOpen.value || event.key !== 'Escape') return
  event.preventDefault()
  event.stopImmediatePropagation()
  dropdownOpen.value = false
  toggleRef.value?.focus({ preventScroll: true })
}

async function toggleDropdown(event: MouseEvent) {
  if (props.disabled) return
  dropdownOpen.value = !dropdownOpen.value
  if (dropdownOpen.value && event.detail === 0) {
    await nextTick()
    optionsRef.value?.querySelector('button')?.focus({ preventScroll: true })
  }
}

function chooseVoice(voiceId: string) {
  emit('update:modelValue', voiceId)
  dropdownOpen.value = false
  toggleRef.value?.focus({ preventScroll: true })
}

function onInput(e: Event) {
  const t = e.target as HTMLInputElement
  emit('update:modelValue', t.value)
}

function clearInput() {
  if (props.disabled) return
  emit('update:modelValue', '')
}

onBeforeUnmount(() => {
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
        class="icon-button h-full w-8 shrink-0 disabled:pointer-events-none disabled:opacity-40"
        :disabled="disabled || !modelValue.trim()"
        aria-label="清空"
        @click.stop="clearInput"
      >
        <X class="h-4 w-4" stroke-width="2.5" />
      </button>
      <button
        ref="toggleRef"
        type="button"
        class="icon-button h-full w-8 shrink-0"
        :disabled="disabled"
        aria-label="展开音色列表"
        :aria-expanded="dropdownOpen"
        @click="toggleDropdown"
      >
        <ChevronDown class="h-4 w-4" :class="dropdownOpen ? 'rotate-180' : ''" />
      </button>
    </div>

    <SelectDropdownSurface
      v-model:open="dropdownOpen"
      :anchor-ref="rootRef"
      :auto-width="false"
      :placement="dropdownPlacement === 'down' ? 'bottom' : 'top'"
      :gap-px="DROPDOWN_GAP_PX"
    >
      <div
        ref="optionsRef"
        class="overflow-y-auto custom-scrollbar"
        :style="{ maxHeight: `${panelMaxHeightPx}px` }"
      >
        <button
          v-for="voice in filteredVoices"
          :key="voice.voiceId"
          type="button"
          class="select-option items-start"
          @click="chooseVoice(voice.voiceId)"
        >
          <div class="min-w-0 flex-1">
            <div class="truncate text-xs font-medium text-[var(--color-text-secondary)]">{{ voice.name }}</div>
            <div class="truncate text-2xs text-[var(--color-text-muted)]">{{ voice.voiceId }}</div>
          </div>
          <span class="shrink-0 rounded-full bg-surface-muted px-2 py-0.5 text-2xs text-[var(--color-text-muted)]">{{ voice.voiceType }}</span>
        </button>
        <div v-if="filteredVoices.length === 0" class="px-3 py-3 text-xs text-[var(--color-text-muted)]">
          暂无已获取音色
        </div>
      </div>
    </SelectDropdownSurface>
  </div>
</template>
