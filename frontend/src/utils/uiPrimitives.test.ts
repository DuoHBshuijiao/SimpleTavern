import { describe, expect, it } from 'vitest'
import { buttonClass, dialogAria, surfaceClass } from './uiPrimitives'

describe('uiPrimitives', () => {
  it('composes consistent button classes', () => {
    expect(buttonClass()).toBe('btn btn-secondary')
    expect(buttonClass({ variant: 'danger', size: 'sm', loading: true })).toBe(
      'btn btn-danger btn-sm btn-loading',
    )
    expect(buttonClass({ variant: 'primary', iconOnly: true })).toBe('btn btn-primary btn-icon')
  })

  it('composes surface classes by semantic tone and state', () => {
    expect(surfaceClass()).toBe('surface-card')
    expect(surfaceClass({ tone: 'panel', interactive: true, selected: true })).toBe(
      'surface-panel interactive-surface surface-selected',
    )
  })

  it('returns dialog accessibility attributes', () => {
    expect(dialogAria('dialog-title')).toEqual({
      role: 'dialog',
      'aria-modal': 'true',
      'aria-labelledby': 'dialog-title',
    })
    expect(dialogAria('dialog-title', 'dialog-description')).toMatchObject({
      'aria-describedby': 'dialog-description',
    })
  })
})
