import { nextTick, onBeforeUnmount, ref, watch, type Ref } from 'vue'

type DialogOpenSource = Ref<boolean> | (() => boolean)

interface UseDialogBehaviorOptions {
  closeOnEscape?: boolean
  autoFocus?: boolean
  restoreFocus?: boolean
}

const FOCUSABLE_SELECTOR = [
  'button:not([disabled])',
  '[href]',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',')

/** 当前打开的弹窗，后打开的在末尾 */
const openDialogs: object[] = []

function readIsOpen(source: DialogOpenSource): boolean {
  return typeof source === 'function' ? source() : source.value
}

export function getDialogFocusableElements(root: ParentNode | null): HTMLElement[] {
  if (!root) return []
  return Array.from(root.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)).filter((el) => {
    const ariaHidden = el.getAttribute('aria-hidden') === 'true'
    const disabled = el.getAttribute('aria-disabled') === 'true'
    return !ariaHidden && !disabled && el.tabIndex !== -1
  })
}

export function useDialogBehavior(
  isOpen: DialogOpenSource,
  close: () => void,
  options: UseDialogBehaviorOptions = {},
) {
  const dialogRef = ref<HTMLElement | null>(null)
  const closeOnEscape = options.closeOnEscape !== false
  const autoFocus = options.autoFocus !== false
  const restoreFocus = options.restoreFocus !== false
  let previouslyFocused: HTMLElement | null = null
  const dialogToken = {}

  function removeKeydown() {
    const index = openDialogs.indexOf(dialogToken)
    if (index !== -1) openDialogs.splice(index, 1)
    if (typeof document === 'undefined') return
    document.removeEventListener('keydown', onDocumentKeydown)
  }

  function onDocumentKeydown(event: KeyboardEvent) {
    if (!readIsOpen(isOpen)) return
    // 弹窗可以叠加，一次按键只归最上层
    if (openDialogs[openDialogs.length - 1] !== dialogToken) return

    if (event.key === 'Escape' && closeOnEscape) {
      event.preventDefault()
      // 抽屉和聊天页在 window 上另有 Esc 处理，不拦住的话弹窗一关它们会接着关下一层
      event.stopPropagation()
      close()
      return
    }

    if (event.key !== 'Tab') return
    const focusable = getDialogFocusableElements(dialogRef.value)
    if (focusable.length === 0) {
      event.preventDefault()
      dialogRef.value?.focus()
      return
    }

    const first = focusable[0]!
    const last = focusable[focusable.length - 1]!
    const active = document.activeElement
    if (event.shiftKey && active === first) {
      event.preventDefault()
      last.focus()
    } else if (!event.shiftKey && active === last) {
      event.preventDefault()
      first.focus()
    }
  }

  watch(
    () => readIsOpen(isOpen),
    async (open) => {
      if (typeof document === 'undefined') return
      removeKeydown()
      if (!open) {
        if (restoreFocus) previouslyFocused?.focus()
        previouslyFocused = null
        return
      }

      previouslyFocused = document.activeElement instanceof HTMLElement ? document.activeElement : null
      openDialogs.push(dialogToken)
      document.addEventListener('keydown', onDocumentKeydown)
      await nextTick()
      if (!autoFocus) return
      const target = getDialogFocusableElements(dialogRef.value)[0] ?? dialogRef.value
      target?.focus()
    },
    { immediate: true },
  )

  onBeforeUnmount(removeKeydown)

  return { dialogRef }
}
