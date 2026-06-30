import { describe, expect, it } from 'vitest'
import { formatImportResultMessage } from './useSettingsImport'

describe('formatImportResultMessage', () => {
  it('同时展示顶层警告与 MVU 兼容警告（不互斥丢失）', () => {
    const msg = formatImportResultMessage({
      imported: ['character', 'worldbook'],
      warnings: ['头像下载失败'],
      mvuCompat: { mode: 'directive', applied: true, rules: 3, warnings: ['规则A跳过'] },
    })
    expect(msg).toContain('导入完成：character, worldbook')
    expect(msg).toContain('警告：头像下载失败')
    expect(msg).toContain('MVU 警告：规则A跳过')
  })

  it('仅有 MVU 兼容警告时也展示', () => {
    const msg = formatImportResultMessage({
      imported: ['character'],
      mvuCompat: { mode: 'directive', applied: false, warnings: ['x'] },
    })
    expect(msg).toContain('MVU 警告：x')
  })

  it('归一化 L4 regex 提示文案', () => {
    const msg = formatImportResultMessage({
      imported: ['chat'],
      warnings: ['L4 暂不生成 regex 模式规则；'],
    })
    expect(msg).toContain('未生成正文正则规则')
    expect(msg).not.toContain('L4')
  })

  it('无导入项显示“无”', () => {
    expect(formatImportResultMessage({})).toContain('导入完成：无')
  })
})
