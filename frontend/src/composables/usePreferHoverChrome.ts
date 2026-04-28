import { computed, onMounted, onUnmounted, ref } from 'vue'

/** 当前 UA 是否更像「可用鼠标 hover」的主指针（未发生过覆盖性 pointer 事件前）。 */
function mediaPreferHoverChrome(): boolean {
  if (typeof window === 'undefined') return true
  return (
    window.matchMedia('(hover: hover)').matches &&
    window.matchMedia('(pointer: fine)').matches
  )
}

/**
 * 侧栏列表等：鼠标场景使用 opacity + group-hover；触屏/笔场景在高亮行常显操作钮。
 * 媒体查询给出初始倾向；capture pointerdown 按 mouse vs touch/pen 粘性覆盖（便于 Surface / iPad 外接键鼠切换）。
 */
export function usePreferHoverChrome() {
  const mediaBaseline = ref(mediaPreferHoverChrome())
  /** null：尚未收到覆盖性 pointer，沿用 mediaBaseline */
  const lastPointerPrimary = ref<'mouse' | 'touch' | null>(null)

  let mqHover: MediaQueryList | null = null
  let mqFine: MediaQueryList | null = null

  function updateMediaBaseline() {
    mediaBaseline.value = mediaPreferHoverChrome()
  }

  function onPointerDownCapture(e: PointerEvent) {
    if (e.pointerType === 'mouse') lastPointerPrimary.value = 'mouse'
    else if (e.pointerType === 'touch' || e.pointerType === 'pen') lastPointerPrimary.value = 'touch'
  }

  const preferHoverChrome = computed(() => {
    if (lastPointerPrimary.value === 'mouse') return true
    if (lastPointerPrimary.value === 'touch') return false
    return mediaBaseline.value
  })

  onMounted(() => {
    updateMediaBaseline()
    mqHover = window.matchMedia('(hover: hover)')
    mqFine = window.matchMedia('(pointer: fine)')
    mqHover.addEventListener('change', updateMediaBaseline)
    mqFine.addEventListener('change', updateMediaBaseline)
    window.addEventListener('pointerdown', onPointerDownCapture, true)
  })

  onUnmounted(() => {
    mqHover?.removeEventListener('change', updateMediaBaseline)
    mqFine?.removeEventListener('change', updateMediaBaseline)
    window.removeEventListener('pointerdown', onPointerDownCapture, true)
  })

  return { preferHoverChrome }
}
