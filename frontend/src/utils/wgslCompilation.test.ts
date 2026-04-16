import { describe, expect, it } from 'vitest'
import {
  errorLineNumbersFromDiagnostics,
  formatDiagnosticsAsText,
  gpuMessageToDiagnostic,
} from './wgslCompilation'

describe('wgslCompilation', () => {
  it('formatDiagnosticsAsText joins with blank lines', () => {
    expect(
      formatDiagnosticsAsText([
        {
          severity: 'error',
          message: 'a',
          line: 1,
          column: 0,
          length: 0,
          raw: 'first',
        },
        {
          severity: 'error',
          message: 'b',
          line: 2,
          column: 0,
          length: 0,
          raw: 'second',
        },
      ]),
    ).toBe('first\n\nsecond')
  })

  it('errorLineNumbersFromDiagnostics dedupes and sorts', () => {
    expect(
      errorLineNumbersFromDiagnostics([
        {
          severity: 'error',
          message: 'a',
          line: 5,
          column: 0,
          length: 0,
          raw: 'a',
        },
        {
          severity: 'error',
          message: 'b',
          line: 2,
          column: 0,
          length: 0,
          raw: 'b',
        },
        {
          severity: 'warning',
          message: 'c',
          line: 99,
          column: 0,
          length: 0,
          raw: 'c',
        },
      ]),
    ).toEqual([2, 5])
  })

  it('gpuMessageToDiagnostic maps GPUCompilationMessage fields', () => {
    const d = gpuMessageToDiagnostic({
      message: 'Error while parsing WGSL: :174:3 error: expected',
      type: 'error',
      lineNum: 174,
      linePos: 3,
      offset: 0,
      length: 1,
    })
    expect(d.line).toBe(174)
    expect(d.column).toBe(3)
    expect(d.length).toBe(1)
    expect(d.raw).toContain('expected')
  })
})
