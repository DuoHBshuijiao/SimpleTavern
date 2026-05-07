import type { CharacterCard } from '../types/models'

const extractActions = new Set<string>(['extract', 'extract_and_replace'])

/** 与后端 character_has_mvu_profile_data 对齐 */
export function characterHasMvuProfileData(card: CharacterCard): boolean {
  const tables = card.initialStateTables ?? []
  if (tables.length > 0) return true
  if ((card.mvuDirective ?? '').trim()) return true
  for (const r of card.contentRegexRules ?? []) {
    if (extractActions.has(r.action)) return true
  }
  return false
}

export type ChatLikeForMvu = {
  isGroup: boolean
  characterId: string
  overrides: {
    groupMvuEnabled?: boolean | null
    groupMvuAnchorCharacterId?: string | null
    mvuMode?: string | null
    mvuDirective?: string | null
  }
}

export function isChatMvuRuntimeEnabled(
  chat: ChatLikeForMvu,
  getCharacter: (id: string) => CharacterCard | undefined,
): boolean {
  if (!chat.isGroup) {
    return getCharacter(chat.characterId)?.mvuEnabled === true
  }
  const ex = chat.overrides.groupMvuEnabled
  if (ex === true) return true
  if (ex === false) return false
  return getCharacter(chat.characterId)?.mvuEnabled === true
}
