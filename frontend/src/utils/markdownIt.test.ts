import { describe, expect, it } from 'vitest'
import { normalizeMarkdownInput, renderChatMarkdown, renderChatMarkdownStreaming } from './markdownIt'

describe('markdownIt', () => {
  it('normalizeMarkdownInput 保留脚注定义行', () => {
    const raw = '正文[^1]\n\n[^1]: 注脚内容'
    expect(normalizeMarkdownInput(raw)).toContain('[^1]: 注脚内容')
  })

  it('normalizeMarkdownInput 仍替换普通引用定义冒号', () => {
    const raw = '[ref]: http://x.com'
    expect(normalizeMarkdownInput(raw)).toMatch(/\[ref]：\s/)
  })

  it('renderChatMarkdown 含粗体、列表、脚注、KaTeX', () => {
    const md = [
      '**粗体** ***粗斜***',
      '- a',
      '  - nested',
      '1. one',
      '   1. sub',
      '行内 $\\sqrt{x}$',
      '',
      '$$',
      '\\sum_{i=1}^{n} i',
      '$$',
      '',
      '脚注[^1]',
      '',
      '[^1]: 说明',
    ].join('\n')
    const html = renderChatMarkdown(md)
    expect(html).toMatch(/<strong>粗体<\/strong>/)
    expect(html).toMatch(/<em><strong>粗斜<\/strong><\/em>|<strong><em>粗斜<\/em><\/strong>/)
    expect(html).toMatch(/<ul[\s>]/)
    expect(html).toMatch(/<ol[\s>]/)
    expect(html).toMatch(/class="footnote-ref"/)
    expect(html).toMatch(/<st-math-island[\s>]/)
  })

  describe('renderChatMarkdownStreaming 行内定界符补闭合', () => {
    it('未闭合 ** 应被当作 strong 渲染', () => {
      const html = renderChatMarkdownStreaming('**粗')
      expect(html).toMatch(/<strong>粗<\/strong>/)
    })

    it('未闭合 * 应被当作 em 渲染', () => {
      const html = renderChatMarkdownStreaming('*斜')
      expect(html).toMatch(/<em>斜<\/em>/)
    })

    it('未闭合单反引号应被当作 code 渲染', () => {
      const html = renderChatMarkdownStreaming('`x')
      expect(html).toMatch(/<code>x<\/code>/)
    })

    it('未闭合 ~~ 应被当作 s 渲染', () => {
      const html = renderChatMarkdownStreaming('~~del')
      expect(html).toMatch(/<s>del<\/s>/)
    })

    it('围栏代码内部不补定界符', () => {
      const src = '```\n**not-bold\n'
      const html = renderChatMarkdownStreaming(src)
      expect(html).not.toMatch(/<strong>/)
    })

    it('renderChatMarkdown 对同输入保持原样（不补闭合）', () => {
      const html = renderChatMarkdown('**粗')
      expect(html).not.toMatch(/<strong>/)
    })

    it('已闭合文本不会再追加', () => {
      const html = renderChatMarkdownStreaming('**已闭合**')
      expect(html).toMatch(/<strong>已闭合<\/strong>/)
      expect(html).not.toMatch(/<strong><\/strong>/)
    })

    it('流式分段拼接须保留围栏行后换行（否则破坏闭合围栏与语言标记）', () => {
      const src = ['```python', 'x = 1', '```', '', '## 后文标题'].join('\n')
      const html = renderChatMarkdownStreaming(src)
      expect(html).toMatch(/<h2[\s>]/)
      expect(html).toMatch(/language-python/)
      expect(html).not.toMatch(/language-pythonx/)
    })

    it('未闭合围栏至 EOF 时虚补一行闭合（避免解析器吞掉文档其余结构）', () => {
      const src = ['intro', '', '```', 'x', '## not-heading-yet'].join('\n')
      const html = renderChatMarkdownStreaming(src)
      expect(html).toMatch(/<pre[\s>]|<code/)
      expect(html).not.toMatch(/<h2[\s>]/)
    })

    it('围栏行不应触发行尾追加反引号（避免破坏真实闭合围栏）', () => {
      const src = ['前文 **粗**', '', '```python', 'pass', '```', '', '## 标题'].join('\n')
      const stream = renderChatMarkdownStreaming(src)
      const stable = renderChatMarkdown(src)
      expect(stream).toMatch(/<h2[\s>]/)
      expect(stable).toMatch(/<h2[\s>]/)
    })
  })
})
