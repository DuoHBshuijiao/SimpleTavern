import { describe, expect, it } from 'vitest'
import { computeFlexWrapExtraHeight } from './stateBarWrapExtra'

describe('computeFlexWrapExtraHeight', () => {
  it('returns the total height above the first visual line', () => {
    const extra = computeFlexWrapExtraHeight([
      { offsetTop: 0, offsetHeight: 20, offsetWidth: 80 },
      { offsetTop: 1, offsetHeight: 18, offsetWidth: 48 },
      { offsetTop: 28, offsetHeight: 20, offsetWidth: 72 },
      { offsetTop: 56, offsetHeight: 20, offsetWidth: 32 },
    ])

    expect(extra).toBe(56)
  })

  it('returns zero when all items stay on one visual line', () => {
    const extra = computeFlexWrapExtraHeight([
      { offsetTop: 0, offsetHeight: 20, offsetWidth: 80 },
      { offsetTop: 1, offsetHeight: 18, offsetWidth: 48 },
      { offsetTop: 0, offsetHeight: 20, offsetWidth: 32 },
    ])

    expect(extra).toBe(0)
  })
})
