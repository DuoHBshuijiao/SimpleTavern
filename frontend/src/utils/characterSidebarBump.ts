import type { Chat } from '../types/models'

/**
 * 会话活跃度置顶：解析应对哪张角色卡 bump。
 * 单聊：会话 characterId；群聊：侧栏当前选中的角色，缺省时回退群主 characterId。
 */
export function resolveBumpCharacterId(
  chat: Chat | null | undefined,
  selectedCharacterId: string | null | undefined,
): string | null {
  if (!chat) return null
  if (chat.isGroup) {
    const sid = typeof selectedCharacterId === 'string' ? selectedCharacterId.trim() : ''
    if (sid) return sid
    const cid = chat.characterId?.trim()
    return cid || null
  }
  const cid = chat.characterId?.trim()
  return cid || null
}
