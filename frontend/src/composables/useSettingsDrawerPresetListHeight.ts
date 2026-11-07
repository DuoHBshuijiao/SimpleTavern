import { nextTick, onUnmounted, ref, watch, type Ref } from 'vue'

const PRESET_LIST_MIN_HEIGHT_PX = 120

export interface UseSettingsDrawerPresetListHeightOptions {
  show: Ref<boolean>
  tab: Ref<'global' | 'presets' | 'chat'>
  preloaded: Ref<boolean>
  drawerScrollRef: Ref<HTMLElement | null>
}

/** 预设 Tab 左栏列表 max-height：随 drawer 主滚动区与 header 位置动态计算。 */
export function useSettingsDrawerPresetListHeight(options: UseSettingsDrawerPresetListHeightOptions) {
  const { show, tab, preloaded, drawerScrollRef } = options

  const presetListHeaderRef = ref<HTMLElement | null>(null)
  const presetListMaxHeightPx = ref<number | null>(null)

  let presetListHeightRaf = 0

  function updatePresetListMaxHeight() {
    if (!show.value || tab.value !== 'presets' || !preloaded.value) {
      presetListMaxHeightPx.value = null
      return
    }
    const scroll = drawerScrollRef.value
    const header = presetListHeaderRef.value
    if (!scroll || !header) {
      presetListMaxHeightPx.value = null
      return
    }
    const scrollRect = scroll.getBoundingClientRect()
    const headerRect = header.getBoundingClientRect()
    if (scrollRect.height <= 0 || headerRect.height <= 0) {
      presetListMaxHeightPx.value = null
      return
    }
    // 底边留出滚动区的内边距：超过它，吸附的左栏会被父容器顶走，只有右栏滚到底才看得到最后一项。
    // clientHeight 不含横向滚动条；列表的顶边还要算上标题的外边距。
    const contentBottom = scrollRect.top + scroll.clientTop + scroll.clientHeight - parseFloat(getComputedStyle(scroll).paddingBottom)
    const listTop = headerRect.bottom + parseFloat(getComputedStyle(header).marginBottom)
    presetListMaxHeightPx.value = Math.max(PRESET_LIST_MIN_HEIGHT_PX, Math.floor(contentBottom - listTop))
  }

  function schedulePresetListMaxHeight() {
    if (presetListHeightRaf) cancelAnimationFrame(presetListHeightRaf)
    presetListHeightRaf = requestAnimationFrame(() => {
      presetListHeightRaf = 0
      updatePresetListMaxHeight()
    })
  }

  let presetListResizeObserver: ResizeObserver | null = null

  function teardownPresetListHeightObservers() {
    if (presetListResizeObserver) {
      presetListResizeObserver.disconnect()
      presetListResizeObserver = null
    }
    const el = drawerScrollRef.value
    if (el) {
      el.removeEventListener('scroll', schedulePresetListMaxHeight)
    }
    window.removeEventListener('resize', schedulePresetListMaxHeight)
  }

  function setupPresetListHeightObservers() {
    teardownPresetListHeightObservers()
    if (!show.value || tab.value !== 'presets' || !preloaded.value) return
    const el = drawerScrollRef.value
    if (!el) return
    presetListResizeObserver = new ResizeObserver(() => schedulePresetListMaxHeight())
    presetListResizeObserver.observe(el)
    el.addEventListener('scroll', schedulePresetListMaxHeight, { passive: true })
    window.addEventListener('resize', schedulePresetListMaxHeight)
    nextTick(() => schedulePresetListMaxHeight())
  }

  watch([show, tab, preloaded], () => {
    if (!show.value || tab.value !== 'presets' || !preloaded.value) {
      teardownPresetListHeightObservers()
      presetListMaxHeightPx.value = null
      return
    }
    nextTick(() => setupPresetListHeightObservers())
  }, { flush: 'post' })

  onUnmounted(() => {
    teardownPresetListHeightObservers()
  })

  return {
    presetListHeaderRef,
    presetListMaxHeightPx,
  }
}
