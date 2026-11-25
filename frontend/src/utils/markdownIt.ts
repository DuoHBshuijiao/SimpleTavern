import MarkdownIt from 'markdown-it'
import footnote from 'markdown-it-footnote'
import { mathIslandPlugin } from './markdownItKatexIsland'

/**
 * 将易被误识别为链接引用定义的 `[name]:` 行内冒号改为全角，避免与 Markdown 引用语法冲突。
 * 跳过脚注定义 `[^id]:`，否则会破坏脚注。
 */
export function normalizeMarkdownInput(text: string): string {
  return (text ?? '').replace(/(^|\n)\[([^\]\n]+)\]:(\s*)/g, (full, p1: string, name: string, sp: string) => {
    if (name.startsWith('^')) return full
    return `${p1}[${name}]：${sp}`
  })
}

const md = new MarkdownIt({
  html: false,
  linkify: true,
  breaks: true,
})

md.use(footnote)
md.use(mathIslandPlugin)

// 中文列表常见的 "**标题：**正文" 在标点和正文之间不能闭合加粗。
// 只调整列表项首段，代码块、转义符号和正文中的 Markdown 保持原有解析规则。
md.core.ruler.before('inline', 'localized_list_labels', ({ tokens }) => {
  tokens.forEach((token, index) => {
    if (token.type !== 'inline' || tokens[index - 1]?.type !== 'paragraph_open'
      || tokens[index - 2]?.type !== 'list_item_open') return
    token.content = token.content.replace(
      /^(\*\*|__)([^*_`\\\r\n]+?)([：:])[ \t]*\1(?=[\p{L}\p{N}])/u,
      '$1$2$1$3',
    )
  })
})

md.renderer.rules.link_open = (tokens, index, options, _environment, renderer) => {
  const link = tokens[index]!
  if (!link.attrGet('href')?.startsWith('#')) {
    link.attrSet('target', '_blank')
    link.attrSet('rel', 'noopener noreferrer')
  }
  return renderer.renderToken(tokens, index, options)
}

/** 聊天区 / 助手区 / 更新说明等共用渲染（含脚注与 KaTeX） */
export function renderChatMarkdown(text: string): string {
  return md.render(normalizeMarkdownInput(text))
}

export interface ChatWebSource {
  url: string
  label: string
}

const WEB_SOURCE_HEADING = /^ {0,3}(?:#{1,6}[ \t]+)?(?:\*\*|__)?(?:来源|参考来源|参考链接|Sources|References)(?:(?:\*\*|__)?[：:](?:\*\*|__)?|(?:\*\*|__)?(?=[ \t]*$))[ \t]*/i
const WEB_SOURCE_BLOCKS = /^(?:bullet_list|ordered_list|list_item|paragraph)_(?:open|close)$/
const WEB_SOURCE_SEPARATOR = /^[\s·•|,，、;；]*$/

function sourceLinks(markdown: string): ChatWebSource[] {
  const sources: ChatWebSource[] = []
  for (const token of md.parse(markdown, {})) {
    if (WEB_SOURCE_BLOCKS.test(token.type)) continue
    if (token.type !== 'inline') return []

    let url: URL | null = null
    let label = ''
    for (const part of token.children ?? []) {
      if (part.type === 'link_open') {
        const raw = part.attrGet('href')
        try {
          url = new URL(raw ?? '')
        } catch {
          return []
        }
        if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password) return []
        label = ''
      } else if (part.type === 'link_close' && url) {
        const title = label.trim()
        sources.push({
          url: url.href,
          label: title && !/^https?:\/\//i.test(title) ? title : url.hostname.replace(/^www\./, ''),
        })
        url = null
      } else if (url) {
        if (['text', 'code_inline', 'image'].includes(part.type)) label += part.content
      } else if (!['softbreak', 'hardbreak'].includes(part.type) &&
                 !(part.type === 'text' && WEB_SOURCE_SEPARATOR.test(part.content))) {
        return []
      }
    }
  }
  return sources
}

/** Only convert a trailing, top-level sources section. Leave prose, code and inline citations in the body. */
export function splitChatWebSources(text: string): { body: string; sources: ChatWebSource[] } {
  const lines = text.split(/\r?\n/)
  if (!lines.some(line => WEB_SOURCE_HEADING.test(line))) return { body: text, sources: [] }

  const headings = md.parse(normalizeMarkdownInput(text), {})
    .filter(token => token.level === 0 && token.map && ['paragraph_open', 'heading_open'].includes(token.type))
    .map(token => token.map![0])
    .filter(index => WEB_SOURCE_HEADING.test(lines[index] ?? ''))

  const chunks: ChatWebSource[][] = []
  let end = lines.length
  for (const start of headings.reverse()) {
    const section = lines.slice(start, end)
    section[0] = section[0]!.replace(WEB_SOURCE_HEADING, '')
    const links = sourceLinks(section.join('\n'))
    if (!links.length) break
    chunks.unshift(links)
    end = start
  }
  if (!chunks.length) return { body: text, sources: [] }

  const sources = new Map<string, ChatWebSource>()
  for (const source of chunks.flat()) {
    if (!sources.has(source.url)) sources.set(source.url, source)
  }
  return { body: lines.slice(0, end).join('\n').trimEnd(), sources: [...sources.values()] }
}

type FencedSplitPart = { code: boolean; content: string }

type FencedSplitResult = {
  parts: FencedSplitPart[]
  inCodeAtEnd: boolean
  /** 当前未闭合块的开场围栏定界串（与 CommonMark 闭合长度一致），仅在 inCodeAtEnd 时有效 */
  lastOpenFence: string | null
}

/**
 * 按围栏代码（``` / ~~~）切分，并跟踪是否停在未闭合块内。
 * 代码块内分段不补行内定界符；流式末尾可据 lastOpenFence 虚补一行闭合。
 */
function splitByFencedCode(text: string): FencedSplitResult {
  const lines = text.split('\n')
  const parts: FencedSplitPart[] = []
  let inCode = false
  let buf: string[] = []
  let lastOpenFence: string | null = null

  for (const line of lines) {
    if (/^\s{0,3}(```+|~~~+)/.test(line)) {
      buf.push(line)
      parts.push({ code: inCode, content: buf.join('\n') })
      buf = []
      const m = line.match(/^\s{0,3}(```+|~~~+)/)
      const run = m?.[1] ?? '```'
      if (!inCode) lastOpenFence = run
      else lastOpenFence = null
      inCode = !inCode
      continue
    }
    buf.push(line)
  }
  if (buf.length > 0) parts.push({ code: inCode, content: buf.join('\n') })

  return {
    parts,
    inCodeAtEnd: inCode,
    lastOpenFence: inCode ? lastOpenFence : null,
  }
}

/**
 * 按段落（连续非空行）补虚闭合：标记未跨段落传播，避免一个段落的未闭合影响到下一段。
 */
function autoCloseInlineMarkers(segment: string): string {
  const paragraphs = segment.split(/(\n\s*\n)/)
  return paragraphs.map((p) => (/^\n\s*\n$/.test(p) ? p : autoCloseParagraph(p))).join('')
}

/** 不参与行内反引号计数的行：行首围栏定界（否则 ```python 会触发补 ```，破坏围栏） */
const FENCE_LINE_START = /^\s{0,3}(```+|~~~+)/

function textForInlineBacktickBalance(text: string): string {
  return text
    .split('\n')
    .map((line) => (FENCE_LINE_START.test(line) ? '' : line))
    .join('\n')
}

/**
 * 对单段文本补齐未闭合的行内成对定界符。
 * 顺序：反引号串 > 粗体/斜体类 `**`/`__`/`*`/`_` > 删除线 `~~`。
 * 反引号优先是因为反引号内部的其它字符不参与 Markdown 解析。
 */
function autoCloseParagraph(text: string): string {
  if (!text) return text
  let out = text

  // 反引号串：匹配任意连续反引号，奇数组数则在末尾补相同长度一组
  // 例如 "a `b `` c `" 的 ``` ` ``` 总段数
  // 围栏行整行不参与计数，避免把 ```python 当成未闭合行内反引号
  const backtickRuns = textForInlineBacktickBalance(out).match(/`+/g) ?? []
  // 长度 → 出现次数映射；奇数次数视为未闭合，补上相同长度一组
  if (backtickRuns.length > 0) {
    const runCountByLen = new Map<number, number>()
    for (const run of backtickRuns) {
      const n = run.length
      runCountByLen.set(n, (runCountByLen.get(n) ?? 0) + 1)
    }
    // 选第一个奇数长度补齐即可：Markdown 对 inline code 的闭合以首个「长度相同」的反引号串为准
    for (const [len, count] of runCountByLen) {
      if (count % 2 === 1) {
        out += '`'.repeat(len)
        break
      }
    }
  }

  // 粗体类：`**` 与 `__` 各自成对
  for (const marker of ['**', '__'] as const) {
    const count = countOccurrences(out, marker)
    if (count % 2 === 1) out += marker
  }

  // 删除线：`~~` 成对
  {
    const count = countOccurrences(out, '~~')
    if (count % 2 === 1) out += '~~'
  }

  // 单字符强调：先屏蔽已补齐的 `**`/`__`/`~~` 再数；下划线容易在词中命中（`a_b_c`），
  // 仅处理 `*`，`_` 风险较大先不动。
  {
    const stripped = out.replace(/\*\*/g, '')
    const single = countOccurrences(stripped, '*')
    if (single % 2 === 1) out += '*'
  }

  return out
}

function countOccurrences(text: string, token: string): number {
  if (!token) return 0
  let i = 0
  let n = 0
  while (true) {
    const idx = text.indexOf(token, i)
    if (idx < 0) break
    n += 1
    i = idx + token.length
  }
  return n
}

/**
 * 流式渲染：在把文本交给 markdown-it 前，
 * - 对**行内成对定界符**补虚闭合，减轻闭合瞬间排版跳动；
 * - 若缓冲区仍停在未闭合围栏内，在渲染用文本末尾虚补一行闭合围栏（与开场同字符、同长度），
 *   避免 markdown-it 把后文全部吞进代码块；最终全文闭合后与 renderChatMarkdown 一致。
 *
 * 显式不处理：`$` / `$$`（避免 KaTeX 残式）、HTML 块。
 */
export function renderChatMarkdownStreaming(text: string): string {
  const normalized = normalizeMarkdownInput(text)
  const { parts: rawParts, inCodeAtEnd, lastOpenFence } = splitByFencedCode(normalized)
  const parts =
    inCodeAtEnd && lastOpenFence && rawParts.length > 0
      ? (() => {
          const copy = rawParts.map((p) => ({ ...p }))
          const last = copy[copy.length - 1]!
          last.content = `${last.content}\n${lastOpenFence}`
          return copy
        })()
      : rawParts

  const stabilized = parts
    .map((part) => (part.code ? part.content : autoCloseInlineMarkers(part.content)))
    // 分段之间必须恢复「行边界」：否则 ```python 与下一行会粘成 ```pythonx，闭合围栏无法识别
    .join('\n')
  return md.render(stabilized)
}
