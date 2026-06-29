import { describe, expect, it } from 'vitest'
import { getDialogFocusableElements } from './useDialogBehavior'

function focusable(attrs: Record<string, string | null> = {}, tabIndex = 0): HTMLElement {
  return {
    tabIndex,
    getAttribute(name: string) {
      return attrs[name] ?? null
    },
  } as HTMLElement
}

describe('getDialogFocusableElements', () => {
  it('filters aria-hidden, aria-disabled and tabindex -1 elements', () => {
    const visible = focusable()
    const root = {
      querySelectorAll: () => [
        visible,
        focusable({ 'aria-hidden': 'true' }),
        focusable({ 'aria-disabled': 'true' }),
        focusable({}, -1),
      ],
    } as unknown as ParentNode

    expect(getDialogFocusableElements(root)).toEqual([visible])
  })

  it('returns an empty list without a root', () => {
    expect(getDialogFocusableElements(null)).toEqual([])
  })
})
