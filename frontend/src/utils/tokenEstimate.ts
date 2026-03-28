import { apiPost } from '../api/http'
import type { WorldBook } from '../types/models'

/**
 * 调用后端 tokenizer 估算文本 token 数；空文本为 0，失败为 null。
 */
export async function countTokensForText(text: string): Promise<number | null> {
  const t = text.trim()
  if (!t) return 0
  try {
    const res = await apiPost<{ tokens: number | null }>('/api/tokenizer/count', { text: t })
    return res.tokens ?? null
  } catch {
    return null
  }
}

/** 拼接世界书中已启用条目的正文，用于整书 token 估测（与注入内容一致） */
export function concatEnabledWorldBookContents(book: WorldBook): string {
  return (book.entries || [])
    .filter((e) => e.enabled)
    .map((e) => (e.content || '').trim())
    .filter(Boolean)
    .join('\n\n')
}
