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

/** 聊天区 / 助手区 / 更新说明等共用渲染（含脚注与 KaTeX） */
export function renderChatMarkdown(text: string): string {
  return md.render(normalizeMarkdownInput(text))
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
