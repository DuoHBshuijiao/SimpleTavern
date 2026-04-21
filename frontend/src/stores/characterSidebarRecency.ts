/**
 * 侧栏角色列表「会话活跃度」排序（本地持久化）
 *
 * 与 CharacterCard.updatedAt 分离，仅反映聊天侧栏置顶意图。
 */

import { defineStore } from 'pinia'

import type { CharacterCard } from '../types/models'
import { useCharactersStore } from './characters'

export const CHARACTER_SIDEBAR_RECENCY_STORAGE_KEY = 'simpletavern-character-sidebar-recency-v1'

function loadFromStorage(): Record<string, string> {
  try {
    const raw = localStorage.getItem(CHARACTER_SIDEBAR_RECENCY_STORAGE_KEY)
    if (!raw) return {}
    const parsed = JSON.parse(raw) as unknown
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return {}
    const out: Record<string, string> = {}
    for (const [k, v] of Object.entries(parsed as Record<string, unknown>)) {
      if (typeof k === 'string' && typeof v === 'string' && v.trim()) out[k] = v
    }
    return out
  } catch {
    return {}
  }
}

function saveToStorage(map: Record<string, string>) {
  try {
    localStorage.setItem(CHARACTER_SIDEBAR_RECENCY_STORAGE_KEY, JSON.stringify(map))
  } catch {
    /* ignore quota / private mode */
  }
}

export const useCharacterSidebarRecencyStore = defineStore('characterSidebarRecency', {
  state: () => ({
    lastActiveAt: loadFromStorage() as Record<string, string>,
  }),
  actions: {
    bump(characterId: string | null | undefined) {
      const id = typeof characterId === 'string' ? characterId.trim() : ''
      if (!id) return
      const chars = useCharactersStore()
      if (!chars.list.some((c) => c.id === id)) return
      const next = { ...this.lastActiveAt, [id]: new Date().toISOString() }
      this.lastActiveAt = next
      saveToStorage(next)
    },

    sortedList(cards: CharacterCard[]): CharacterCard[] {
      const ts = this.lastActiveAt
      return [...cards].sort((a, b) => {
        const ta = Date.parse(ts[a.id] || '') || 0
        const tb = Date.parse(ts[b.id] || '') || 0
        if (tb !== ta) return tb - ta
        return Date.parse(b.updatedAt || '') - Date.parse(a.updatedAt || '')
      })
    },
  },
})
