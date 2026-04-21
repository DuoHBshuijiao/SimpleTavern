/**
 * 从思考纯文本中提取「当前最后一条」可用于尾槽展示的片段：
 * - ATX 一至三级标题（整行；流式时跳过全文最后一行）
 * - 粗斜体 ***...***、___...___（单行内成对闭合；流式时跳过全文最后一行）
 * 围栏代码块内不解析（规则对齐 markdownIt.splitByFencedCode）。
 */

const FENCE_LINE = /^\s{0,3}(```+|~~~+)/

function parseAtxTitle(line: string): string | null {
  const m = line.match(/^\s{0,3}(#{1,3})\s+(.+)$/)
  if (!m?.[2]) return null
  let t = m[2].replace(/\s*#+\s*$/, '').trim()
  return t.length > 0 ? t : null
}

function extractTripleEmphasisSegments(line: string): string[] {
  type Hit = { start: number; text: string }
  const hits: Hit[] = []
  const starRe = /\*\*\*(.+?)\*\*\*/g
  let m: RegExpExecArray | null
  while ((m = starRe.exec(line)) !== null) {
    const raw = m[1]
    if (raw === undefined) continue
    const inner = raw.trim()
    if (inner.length > 0) hits.push({ start: m.index, text: inner })
  }
  const undRe = /___(.+?)___/g
  while ((m = undRe.exec(line)) !== null) {
    const raw = m[1]
    if (raw === undefined) continue
    const inner = raw.trim()
    if (inner.length > 0) hits.push({ start: m.index, text: inner })
  }
  hits.sort((a, b) => a.start - b.start)
  return hits.map((h) => h.text)
}

export function getLatestReasoningHighlight(
  text: string,
  options?: { isStreaming?: boolean },
): string | null {
  const isStreaming = options?.isStreaming ?? false
  const lines = (text ?? '').split('\n')
  let inCode = false
  const matches: string[] = []

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i] ?? ''
    const isLastLine = i === lines.length - 1

    if (FENCE_LINE.test(line)) {
      inCode = !inCode
      continue
    }
    if (inCode) continue

    const allowLine = !isStreaming || !isLastLine

    if (!allowLine) continue

    const title = parseAtxTitle(line)
    if (title !== null) {
      matches.push(title)
      continue
    }

    for (const seg of extractTripleEmphasisSegments(line)) {
      matches.push(seg)
    }
  }

  if (matches.length === 0) return null
  return matches[matches.length - 1] ?? null
}
