import type { Directive } from 'vue'

type PreviewPosition = { position: { x: number; y: number } }
const cleanups = new WeakMap<HTMLElement, () => void>()

function moveCloseButtonIntoView(element: HTMLElement, preview: PreviewPosition) {
  const close = element.querySelector<HTMLButtonElement>('.image-preview-close')
  if (!close) return
  const rect = close.getBoundingClientRect()
  const viewport = window.visualViewport
  const left = (viewport?.offsetLeft ?? 0) + 6
  const top = (viewport?.offsetTop ?? 0) + 6
  const right = left + (viewport?.width ?? window.innerWidth) - 12
  const bottom = top + (viewport?.height ?? window.innerHeight) - 12
  const dx = rect.left < left ? left - rect.left : Math.min(0, right - rect.right)
  const dy = rect.top < top ? top - rect.top : Math.min(0, bottom - rect.bottom)
  if (Math.abs(dx) > 0.5 || Math.abs(dy) > 0.5) {
    preview.position = { x: preview.position.x + dx, y: preview.position.y + dy }
  }
}

export const keepPreviewCloseVisible: Directive<HTMLElement, PreviewPosition> = {
  mounted(element, { value }) {
    const clamp = () => moveCloseButtonIntoView(element, value)
    const observer = new ResizeObserver(clamp)
    observer.observe(element)
    window.addEventListener('resize', clamp)
    window.visualViewport?.addEventListener('resize', clamp)
    window.visualViewport?.addEventListener('scroll', clamp)
    cleanups.set(element, () => {
      observer.disconnect()
      window.removeEventListener('resize', clamp)
      window.visualViewport?.removeEventListener('resize', clamp)
      window.visualViewport?.removeEventListener('scroll', clamp)
    })
  },
  updated(element, { value }) {
    moveCloseButtonIntoView(element, value)
  },
  beforeUnmount(element) {
    cleanups.get(element)?.()
    cleanups.delete(element)
  },
}
