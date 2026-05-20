import type { ChatMessage } from '../types/models'

/** 1-based index of message id in messages array; null if not found. */
export function messageIndex1Based(messages: ChatMessage[], messageId: string): number | null {
  const idx = messages.findIndex((m) => m.id === messageId)
  return idx >= 0 ? idx + 1 : null
}

/** Default fork session title when user leaves name empty. */
export function buildForkTitle(
  sourceTitle: string,
  isGroup: boolean,
  customName?: string,
): string {
  const name = (customName ?? '').trim()
  if (name) return name
  const base = (sourceTitle ?? '').trim() || (isGroup ? '新群聊' : '新对话')
  return `分叉：${base}`
}

/** Truncate message preview for fork confirm modal. */
export function forkMessagePreview(content: string, maxLen = 120): string {
  const t = (content ?? '').trim().replace(/\s+/g, ' ')
  if (!t) return '（空消息）'
  if (t.length <= maxLen) return t
  return `${t.slice(0, maxLen)}…`
}
