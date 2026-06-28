import { describe, expect, it } from 'vitest'
import { applyContentRegexDisplay } from './contentRegex'
import type { ChatContentRegexRule } from '../types/models'

function rule(overrides: Partial<ChatContentRegexRule>): ChatContentRegexRule {
  return {
    id: overrides.id ?? 'rule',
    enabled: overrides.enabled ?? true,
    order: overrides.order ?? 0,
    pattern: overrides.pattern ?? '',
    action: overrides.action ?? 'remove',
    replacement: overrides.replacement ?? null,
    matchMode: overrides.matchMode ?? 'global',
    ...overrides,
  } as ChatContentRegexRule
}

describe('applyContentRegexDisplay', () => {
  it('supports JS numeric replacement groups', () => {
    const result = applyContentRegexDisplay('name: Alice', [
      rule({ pattern: String.raw`name: (\w+)`, action: 'replace', replacement: 'user=$1' }),
    ])

    expect(result).toBe('user=Alice')
  })

  it('supports Python numeric replacement groups after storage normalization', () => {
    const result = applyContentRegexDisplay('name: Alice', [
      rule({ pattern: String.raw`name: (\w+)`, action: 'replace', replacement: String.raw`user=\g<1>` }),
    ])

    expect(result).toBe('user=Alice')
  })

  it('keeps literal dollars compatible with JS replacement syntax', () => {
    const result = applyContentRegexDisplay('cost: 12', [
      rule({ pattern: String.raw`cost: (\d+)`, action: 'replace', replacement: 'price=$$1=$1' }),
    ])

    expect(result).toBe('price=$1=12')
  })

  it('parses slash literals without treating slash inside character classes as the end', () => {
    const result = applyContentRegexDisplay('a/z b-c', [
      rule({ pattern: '/[a/z]+/u', action: 'replace', replacement: 'X' }),
    ])

    expect(result).toBe('X b-c')
  })

  it('applies first match mode once', () => {
    const result = applyContentRegexDisplay('one two two', [
      rule({ pattern: 'two', action: 'remove', matchMode: 'first' }),
    ])

    expect(result).toBe('one  two')
  })

  it('skips extract-only rules and applies extract_and_replace only to display text', () => {
    const result = applyContentRegexDisplay('HP: 10 MP: 5', [
      rule({ id: 'extract', pattern: String.raw`MP: \d+`, action: 'extract' }),
      rule({ id: 'hp', pattern: String.raw`HP: (\d+)`, action: 'extract_and_replace', replacement: '[state]' }),
    ])

    expect(result).toBe('[state] MP: 5')
  })

  it('skips invalid rules and continues with later rules', () => {
    const result = applyContentRegexDisplay('ok', [
      rule({ id: 'bad', pattern: '[', action: 'remove', order: 0 }),
      rule({ id: 'good', pattern: 'ok', action: 'replace', replacement: 'done', order: 1 }),
    ])

    expect(result).toBe('done')
  })
})
