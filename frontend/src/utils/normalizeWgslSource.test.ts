import { describe, expect, it } from 'vitest'
import { normalizeWgslSource } from './normalizeWgslSource'

describe('normalizeWgslSource', () => {
  it('replaces NBSP with ASCII space', () => {
    expect(normalizeWgslSource('let\u00a0x')).toBe('let x')
  })

  it('strips BOM and normalizes CRLF', () => {
    expect(normalizeWgslSource('\ufeffa\r\nb')).toBe('a\nb')
  })
})
