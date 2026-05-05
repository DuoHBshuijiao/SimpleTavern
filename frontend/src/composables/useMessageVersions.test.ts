import { describe, expect, it } from 'vitest'
import type { ChatMessage } from '../types/models'
import { useMessageVersions } from './useMessageVersions'

function assistantMessage(overrides: Partial<ChatMessage> = {}): ChatMessage {
  return {
    version: 1,
    id: 'assistant-1',
    role: 'assistant',
    content: 'old',
    ts: '2026-01-01T00:00:00.000Z',
    ...overrides,
  }
}

describe('useMessageVersions', () => {
  it('prepares a persist snapshot for a single reasoning-only version', () => {
    const versions = useMessageVersions()
    const msg = assistantMessage({ content: '' })

    versions.addNewVersion(msg.id, msg.id, '', 'thinking only', 0.5)

    expect(versions.getVariantArraysForPersist(msg)).toEqual({
      contents: [''],
      reasonings: ['thinking only'],
      durations: [0.5],
    })
  })

  it('keeps duplicate content when reasoning differs so interrupted output remains a version', () => {
    const versions = useMessageVersions()
    const msg = assistantMessage()

    versions.saveVersion(msg.id, 'same', 'old reasoning', 1)
    versions.addNewVersion(msg.id, msg.id, 'same', 'new reasoning', 2)

    expect(versions.getVariantArraysForPersist(msg)).toEqual({
      contents: ['same', 'same'],
      reasonings: ['old reasoning', 'new reasoning'],
      durations: [1, 2],
    })
  })
})
