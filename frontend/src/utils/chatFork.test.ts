import { describe, expect, it } from 'vitest'
import { buildForkTitle, forkMessagePreview, messageIndex1Based } from './chatFork'
import type { ChatMessage } from '../types/models'

function msg(id: string): ChatMessage {
  return {
    version: 1,
    id,
    role: 'user',
    content: 'hello',
    ts: '2026-01-01T00:00:00',
  }
}

describe('messageIndex1Based', () => {
  it('returns 1-based index when found', () => {
    expect(messageIndex1Based([msg('a'), msg('b')], 'b')).toBe(2)
  })
  it('returns null when missing', () => {
    expect(messageIndex1Based([msg('a')], 'z')).toBeNull()
  })
})

describe('buildForkTitle', () => {
  it('uses custom name when provided', () => {
    expect(buildForkTitle('原会话', false, '  我的分叉  ')).toBe('我的分叉')
  })
  it('defaults with 分叉 prefix', () => {
    expect(buildForkTitle('原会话', false)).toBe('分叉：原会话')
  })
  it('falls back for empty source title', () => {
    expect(buildForkTitle('', true)).toBe('分叉：新群聊')
  })
})

describe('forkMessagePreview', () => {
  it('truncates long text', () => {
    const long = 'a'.repeat(200)
    expect(forkMessagePreview(long).endsWith('…')).toBe(true)
  })
  it('shows placeholder for empty', () => {
    expect(forkMessagePreview('   ')).toBe('（空消息）')
  })
})
