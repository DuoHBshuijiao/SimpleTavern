<script setup lang="ts">
/**
 * Teleport + 与站内模型下拉相同的玻璃渐变外壳与 fixed 定位（含窄竖屏左右留白）。
 * 仅用于 ChatInput 写作辅助 / 省略号菜单及同类「按钮锚点 + 自定义条目」场景；不参与 ModernSelect 等既有稳定下拉。
 */
import type { MaybeRef } from 'vue'
import { ref, watch, nextTick, onMounted, onUnmounted, unref } from 'vue'
import { useViewportNarrowPortrait } from '../composables/useViewportNarrowPortrait'

const NARROW_SELECT_GUTTER = '1rem'

const props = withDefaults(
  defineProps<{
    /** 定位锚点；模板绑定 ref 时由编译器解包，MaybeRef 兼容 Ref 与元素 */
    anchorRef: MaybeRef<HTMLElement | null>
    placement?: 'top' | 'bottom'
    /** 与锚点间距（px），对齐 mb-2 时常用 8 */
    gapPx?: number
    /** true：宽度随内容；窄竖屏下仍使用与 ModernSelect 一致的左右留白铺满 */
    autoWidth?: boolean
    maxHeightClass?: string
  }>(),
  {
    placement: 'bottom',
    gapPx: 8,
    autoWidth: true,
    maxHeightClass: 'max-h-[320px]',
  },
)

const open = defineModel<boolean>('open', { default: false })

const { isNarrowPortrait } = useViewportNarrowPortrait()

const dropdownRef = ref<HTMLElement | null>(null)
const dropdownStyle = ref<Record<string, string>>({})

function updateDropdownPosition() {
  const trigger = unref(props.anchorRef)
  if (!trigger) return
  const rect = trigger.getBoundingClientRect()
  const g = props.gapPx
  const style: Record<string, string> = { position: 'fixed' }
  if (props.placement === 'top') {
    style.bottom = `${window.innerHeight - rect.top + g}px`
    style.top = 'auto'
  } else {
    style.top = `${rect.bottom + g}px`
    style.bottom = 'auto'
  }
  if (props.autoWidth) {
    /** 横向始终以锚点为基准；勿在窄屏改用视口 left 留白（那会贴屏幕左缘，与工具栏按钮脱节） */
    const vw = window.innerWidth
    const edge = 8
    style.left = `${rect.left}px`
    style.right = 'auto'
    style.width = 'max-content'
    style.maxWidth = `${Math.max(120, vw - rect.left - edge)}px`
  } else if (isNarrowPortrait.value) {
    style.left = NARROW_SELECT_GUTTER
    style.right = NARROW_SELECT_GUTTER
    style.width = 'auto'
  } else {
    style.left = `${rect.left}px`
    style.width = `${rect.width}px`
  }
  dropdownStyle.value = style
}

let positionRaf = 0
let removePositionListeners: (() => void) | null = null

function scheduleUpdateDropdownPosition() {
  if (positionRaf) return
  positionRaf = requestAnimationFrame(() => {
    positionRaf = 0
    updateDropdownPosition()
  })
}

function attachDropdownPositionListeners() {
  removePositionListeners?.()
  const schedule = () => scheduleUpdateDropdownPosition()

  const onScroll = () => schedule()
  const onWinResize = () => schedule()

  document.addEventListener('scroll', onScroll, true)
  window.addEventListener('resize', onWinResize)

  let ro: ResizeObserver | undefined
  const trigger = unref(props.anchorRef)
  if (trigger && typeof ResizeObserver !== 'undefined') {
    ro = new ResizeObserver(schedule)
    ro.observe(trigger)
  }

  const vv = typeof window !== 'undefined' ? window.visualViewport : null
  const onVvResize = () => schedule()
  const onVvScroll = () => schedule()
  if (vv) {
    vv.addEventListener('resize', onVvResize)
    vv.addEventListener('scroll', onVvScroll)
  }

  removePositionListeners = () => {
    document.removeEventListener('scroll', onScroll, true)
    window.removeEventListener('resize', onWinResize)
    ro?.disconnect()
    if (vv) {
      vv.removeEventListener('resize', onVvResize)
      vv.removeEventListener('scroll', onVvScroll)
    }
    removePositionListeners = null
  }
}

watch(open, (isOpen) => {
  if (isOpen) {
    nextTick(() => {
      attachDropdownPositionListeners()
      updateDropdownPosition()
    })
  } else {
    removePositionListeners?.()
    if (positionRaf) {
      cancelAnimationFrame(positionRaf)
      positionRaf = 0
    }
  }
})

watch(
  () => [props.placement, props.autoWidth, props.gapPx] as const,
  () => {
    if (open.value) scheduleUpdateDropdownPosition()
  },
)

watch(isNarrowPortrait, () => {
  if (open.value) scheduleUpdateDropdownPosition()
})

function handleClickOutside(event: MouseEvent) {
  const target = event.target as Node
  const anchor = unref(props.anchorRef)
  if (anchor?.contains(target) || dropdownRef.value?.contains(target)) return
  if (open.value) open.value = false
}

onMounted(() => {
  document.addEventListener('click', handleClickOutside)
})

onUnmounted(() => {
  document.removeEventListener('click', handleClickOutside)
  removePositionListeners?.()
  if (positionRaf) {
    cancelAnimationFrame(positionRaf)
    positionRaf = 0
  }
})
</script>

<template>
  <Teleport to="body">
    <Transition name="select-dropdown-pop">
      <div
        v-if="open"
        ref="dropdownRef"
        class="z-dropdown select-dropdown theme-panel-bg rounded-xl shadow-glass-panel overflow-hidden flex flex-col border border-[var(--color-border)] backdrop-blur-xl backdrop-saturate-[1.8]"
        :class="[
          autoWidth ? 'w-max min-w-0' : '',
          maxHeightClass,
          placement === 'top' ? 'select-dropdown-pop--top' : 'select-dropdown-pop--bottom',
        ]"
        :style="dropdownStyle"
      >
        <slot name="header" />
        <div
          class="select-dropdown-options min-h-0 flex-1 overflow-y-auto custom-scrollbar p-1"
        >
          <slot />
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.select-dropdown {
  background:
    linear-gradient(
      to bottom right,
      color-mix(in srgb, var(--color-brand-a20) 55%, var(--app-panel-from)),
      color-mix(in srgb, var(--color-brand-a10) 45%, var(--app-panel-to))
    );
}

.select-dropdown-options {
  background:
    linear-gradient(
      to bottom,
      color-mix(in srgb, var(--color-brand-a10) 55%, transparent),
      transparent 18%,
      transparent 82%,
      color-mix(in srgb, var(--color-brand-a10) 35%, transparent)
    );
}

.custom-scrollbar::-webkit-scrollbar {
  width: 4px;
}
.custom-scrollbar::-webkit-scrollbar-track {
  background: transparent;
}
.custom-scrollbar::-webkit-scrollbar-thumb {
  background: var(--color-border);
  border-radius: 2px;
}
.custom-scrollbar:hover::-webkit-scrollbar-thumb {
  background: var(--color-border-strong);
}

.select-dropdown-pop-enter-active,
.select-dropdown-pop-leave-active {
  transition:
    transform 0.2s cubic-bezier(0.33, 1, 0.68, 1),
    opacity 0.2s ease;
}

.select-dropdown-pop-enter-from.select-dropdown-pop--bottom,
.select-dropdown-pop-leave-to.select-dropdown-pop--bottom {
  transform: translateY(-0.5rem);
  opacity: 0;
}

.select-dropdown-pop-enter-to.select-dropdown-pop--bottom,
.select-dropdown-pop-leave-from.select-dropdown-pop--bottom {
  transform: translateY(0);
  opacity: 1;
}

.select-dropdown-pop-enter-from.select-dropdown-pop--top,
.select-dropdown-pop-leave-to.select-dropdown-pop--top {
  transform: translateY(0.5rem);
  opacity: 0;
}

.select-dropdown-pop-enter-to.select-dropdown-pop--top,
.select-dropdown-pop-leave-from.select-dropdown-pop--top {
  transform: translateY(0);
  opacity: 1;
}

@media (prefers-reduced-motion: reduce) {
  .select-dropdown-pop-enter-active,
  .select-dropdown-pop-leave-active {
    transition: opacity 0.15s ease;
  }

  .select-dropdown-pop-enter-from.select-dropdown-pop--bottom,
  .select-dropdown-pop-leave-to.select-dropdown-pop--bottom,
  .select-dropdown-pop-enter-from.select-dropdown-pop--top,
  .select-dropdown-pop-leave-to.select-dropdown-pop--top {
    transform: none;
  }
}
</style>
