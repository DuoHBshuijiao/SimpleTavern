/**
 * markdown-it 数学定界符（与 markdown-it-katex 同源逻辑），输出 <st-math-island> 供 Shadow 内 KaTeX 渲染。
 */
import type MarkdownIt from 'markdown-it'

const TAG = 'st-math-island'

/** markdown-it 内联/块状态对象（无稳定公开类型，与 markdown-it-katex 一致按字段访问） */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function isValidDelim(state: any, pos: number) {
  const max = state.posMax
  let canOpen = true
  let canClose = true

  const prevChar = pos > 0 ? state.src.charCodeAt(pos - 1) : -1
  const nextChar = pos + 1 <= max ? state.src.charCodeAt(pos + 1) : -1

  if (prevChar === 0x20 || prevChar === 0x09 || (nextChar >= 0x30 && nextChar <= 0x39)) {
    canClose = false
  }
  if (nextChar === 0x20 || nextChar === 0x09) {
    canOpen = false
  }

  return { can_open: canOpen, can_close: canClose }
}

function mathInline(state: any, silent: boolean): boolean {
  if (state.src[state.pos] !== '$') return false

  const res = isValidDelim(state, state.pos)
  if (!res.can_open) {
    if (!silent) state.pending += '$'
    state.pos += 1
    return true
  }

  const start = state.pos + 1
  let match = start
  while ((match = state.src.indexOf('$', match)) !== -1) {
    let pos = match - 1
    while (state.src[pos] === '\\') pos -= 1
    if ((match - pos) % 2 === 1) break
    match += 1
  }

  if (match === -1) {
    if (!silent) state.pending += '$'
    state.pos = start
    return true
  }

  if (match - start === 0) {
    if (!silent) state.pending += '$$'
    state.pos = start + 1
    return true
  }

  const resClose = isValidDelim(state, match)
  if (!resClose.can_close) {
    if (!silent) state.pending += '$'
    state.pos = start
    return true
  }

  if (!silent) {
    const token = state.push('math_inline', 'math', 0)
    token.markup = '$'
    token.content = state.src.slice(start, match)
  }

  state.pos = match + 1
  return true
}

function mathBlock(state: any, start: number, end: number, silent: boolean): boolean {
  let pos = state.bMarks[start] + state.tShift[start]
  let max = state.eMarks[start]

  if (pos + 2 > max) return false
  if (state.src.slice(pos, pos + 2) !== '$$') return false

  pos += 2
  let firstLine = state.src.slice(pos, max)

  if (silent) return true

  let found = false
  if (firstLine.trim().slice(-2) === '$$') {
    firstLine = firstLine.trim().slice(0, -2)
    found = true
  }

  let next = start
  let lastLine = ''
  while (!found) {
    next += 1
    if (next >= end) break

    pos = state.bMarks[next] + state.tShift[next]
    max = state.eMarks[next]

    if (pos < max && state.tShift[next] < state.blkIndent) break

    const lineSlice = state.src.slice(pos, max).trim()
    if (lineSlice.slice(-2) === '$$') {
      const lastPos = state.src.slice(0, max).lastIndexOf('$$')
      lastLine = state.src.slice(pos, lastPos)
      found = true
    }
  }

  state.line = next + 1

  const token = state.push('math_block', 'math', 0)
  token.block = true
  token.content =
    (firstLine && firstLine.trim() ? firstLine + '\n' : '') +
    state.getLines(start + 1, next, state.tShift[start], true) +
    (lastLine && lastLine.trim() ? lastLine : '')
  token.markup = '$$'
  token.map = [start, state.line]
  return true
}

function escapeAttr(tex: string): string {
  return encodeURIComponent(tex)
}

function islandHtml(tex: string, mode: 'inline' | 'display'): string {
  const enc = escapeAttr(tex)
  return `<${TAG} data-tex="${enc}" data-mode="${mode}"></${TAG}>`
}

export function mathIslandPlugin(md: MarkdownIt): void {
  md.inline.ruler.after('escape', 'math_inline', mathInline)
  md.block.ruler.after('blockquote', 'math_block', mathBlock, {
    alt: ['paragraph', 'reference', 'blockquote', 'list'],
  })

  md.renderer.rules.math_inline = (tokens, idx) => islandHtml(tokens[idx]!.content, 'inline')

  md.renderer.rules.math_block = (tokens, idx) =>
    `<p>${islandHtml(tokens[idx]!.content.replace(/^\s+|\s+$/g, ''), 'display')}</p>\n`
}
