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

  function removeKeydown() {
    if (typeof document === 'undefined') return
    document.removeEventListener('keydown', onDocumentKeydown)
  }

  function onDocumentKeydown(event: KeyboardEvent) {
    if (!readIsOpen(isOpen)) return

    if (event.key === 'Escape' && closeOnEscape) {
      event.preventDefault()
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
