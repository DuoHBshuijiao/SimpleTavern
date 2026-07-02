import { describe, expect, it } from 'vitest'
import type { DataIntegrityIssue } from '../api/dataIntegrity'
import {
  buildIssueFingerprint,
  formatIssueLine,
  partitionRepairableIssues,
  summarizeAutoRepair,
  summarizeManualOnly,
} from './dataIntegrityNotify'

function issue(overrides: Partial<DataIntegrityIssue>): DataIntegrityIssue {
  return {
    path: 'data/settings.json',
    kind: 'settings',
    code: 'invalid_json',
    message: 'JSON 解析失败',
    detail: null,
    size: 0,
    mtimeNs: 1,
    discoveredAt: '',
    repairAction: 'none',
    ...overrides,
  }
}

describe('dataIntegrityNotify', () => {
  it('formatIssueLine 包含 code 与 kind 标签', () => {
    const line = formatIssueLine(issue({ kind: 'character_card', code: 'schema_mismatch', path: 'data/characters/x.json' }))
    expect(line).toContain('结构不匹配')
    expect(line).toContain('角色卡')
    expect(line).toContain('data/characters/x.json')
  })

  it('partitionRepairableIssues 区分自动与人工', () => {
    const { autoIssues, manualIssues } = partitionRepairableIssues([
      issue({ repairAction: 'delete', kind: 'chat_record' }),
      issue({ repairAction: 'none', kind: 'settings' }),
    ])
    expect(autoIssues).toHaveLength(1)
    expect(manualIssues).toHaveLength(1)
  })

  it('summarizeAutoRepair 同时列出自动与人工异常', () => {
    const text = summarizeAutoRepair(
      [issue({ repairAction: 'delete', kind: 'chat_record', path: 'data/chats/a/chat.json' })],
      [issue({ repairAction: 'none', kind: 'settings' })],
    )
    expect(text).toContain('可自动清理')
    expect(text).toContain('需人工检查')
    expect(text).toContain('data/chats/a/chat.json')
  })

  it('formatIssueLine 在存在 detail 时附加说明', () => {
    const line = formatIssueLine(
      issue({
        code: 'orphan_reference',
        kind: 'chat_record',
        path: 'data/chats/ghost/c1/chat.json',
        detail: 'characterId=ghost 无对应角色卡',
      }),
    )
    expect(line).toContain('角色缺失')
    expect(line).toContain('characterId=ghost')
  })

  it('summarizeManualOnly 仅展示人工异常', () => {
    const text = summarizeManualOnly([issue({ code: 'orphan_reference' })])
    expect(text).toContain('角色缺失')
    expect(text).not.toContain('自动清理')
  })

  it('buildIssueFingerprint 稳定排序', () => {
    const a = issue({ path: 'b', mtimeNs: 2 })
    const b = issue({ path: 'a', mtimeNs: 1 })
    expect(buildIssueFingerprint([a, b])).toBe(buildIssueFingerprint([b, a]))
  })
})
