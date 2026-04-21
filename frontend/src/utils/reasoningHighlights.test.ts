import { describe, expect, it } from 'vitest'
import { getLatestReasoningHighlight } from './reasoningHighlights'

describe('getLatestReasoningHighlight', () => {
  it('ATX 一至三级标题取标题文本', () => {
    expect(getLatestReasoningHighlight('# A')).toBe('A')
    expect(getLatestReasoningHighlight('## B')).toBe('B')
    expect(getLatestReasoningHighlight('### C')).toBe('C')
  })

  it('行末可选 # 会去掉', () => {
    expect(getLatestReasoningHighlight('## Title ##')).toBe('Title')
  })

  it('多段时返回文档顺序最后一个', () => {
    const t = '# First\n\n## Second\n\n***last***'
    expect(getLatestReasoningHighlight(t)).toBe('last')
  })

  it('同段中 *** 与 ___ 按出现顺序', () => {
    expect(getLatestReasoningHighlight('___a___ then ***b***')).toBe('b')
    expect(getLatestReasoningHighlight('***a*** then ___b___')).toBe('b')
  })

  it('单 * 斜体不抽取', () => {
    expect(getLatestReasoningHighlight('*foo*')).toBe(null)
    expect(getLatestReasoningHighlight('plain *foo* bar')).toBe(null)
  })

  it('流式时全文最后一行不参与', () => {
    expect(getLatestReasoningHighlight('## Draft title', { isStreaming: true })).toBe(null)
    expect(getLatestReasoningHighlight('***half', { isStreaming: true })).toBe(null)
  })

  it('流式时末行已换行则上一行标题可抽', () => {
    expect(getLatestReasoningHighlight('## OK\n', { isStreaming: true })).toBe('OK')
    expect(getLatestReasoningHighlight('## OK\nstill', { isStreaming: true })).toBe('OK')
  })

  it('围栏代码块内忽略', () => {
    const t = '```\n## Fake\n***x***\n```\n## Real\n'
    expect(getLatestReasoningHighlight(t)).toBe('Real')
  })

  it('标题行不重复抽行内粗斜体', () => {
    expect(getLatestReasoningHighlight('## H ***x***')).toBe('H ***x***')
    // 整行匹配为标题，标题文本包含字面 ***x***（不解析行内）
  })
})
