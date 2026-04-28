import { computed, onMounted, onUnmounted, ref } from 'vue'

/** 参考主流平板纵向偏窄的一类：三星 Galaxy Tab S 等为 16:10（宽/高≈10/16）；同为主流平板的 iPad 多为 4:3（≈0.75）、部分 iPad Pro 约 16:11（≈0.689）。取 16:10 作为常见平板里最「窄」一档，避免误判窄竖屏专项布局。 */
const ASPECT_RATIO_THRESHOLD = 10 / 16

/** 视窗宽高比 < threshold（偏窄偏高，多见于手机纵向）时使用竖屏专项布局（侧栏 overlay、输入栏收窄等）。 */
export function useViewportNarrowPortrait() {
  const width = ref(typeof window !== 'undefined' ? window.innerWidth : 1024)
  const height = ref(typeof window !== 'undefined' ? window.innerHeight : 768)

  const aspectRatio = computed(() =>
    height.value > 0 ? width.value / height.value : 1,
  )
  const isNarrowPortrait = computed(() => aspectRatio.value < ASPECT_RATIO_THRESHOLD)

  let frame = 0
  function onResize() {
    if (frame) cancelAnimationFrame(frame)
    frame = requestAnimationFrame(() => {
      frame = 0
      width.value = window.innerWidth
      height.value = window.innerHeight
    })
  }

  onMounted(() => {
    width.value = window.innerWidth
    height.value = window.innerHeight
    window.addEventListener('resize', onResize)
  })

  onUnmounted(() => {
    window.removeEventListener('resize', onResize)
    if (frame) cancelAnimationFrame(frame)
  })

  return { width, height, aspectRatio, isNarrowPortrait }
}
