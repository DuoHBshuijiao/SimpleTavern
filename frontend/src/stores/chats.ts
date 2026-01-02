import { defineStore } from 'pinia'

import type { Chat, ChatOverrides } from '../types/models'
import { apiDelete, apiGet, apiPost, apiPut } from '../api/http'

export const useChatsStore = defineStore('chats', {
  state: () => ({
    characterId: null as string | null,
    list: [] as Chat[],
    activeChatId: null as string | null,
    activeChat: null as Chat | null,
    loading: false,
    error: null as string | null,
  }),
  actions: {
    async loadList(characterId: string) {
      this.characterId = characterId
      this.loading = true
      this.error = null
      try {
        this.list = await apiGet<Chat[]>(`/api/chats?characterId=${encodeURIComponent(characterId)}`)
      } catch (e: any) {
        this.error = e?.message ?? String(e)
        throw e
      } finally {
        this.loading = false
      }
    },
    async create(characterId: string, title?: string) {
      const chat = await apiPost<Chat>('/api/chats', { characterId, title })
      await this.loadList(characterId)
      this.activeChatId = chat.id
      this.activeChat = chat
      return chat
    },
    async load(chatId: string) {
      this.loading = true
      this.error = null
      try {
        const chat = await apiGet<Chat>(`/api/chats/${chatId}`)
        this.activeChatId = chat.id
        this.activeChat = chat
        return chat
      } catch (e: any) {
        this.error = e?.message ?? String(e)
        throw e
      } finally {
        this.loading = false
      }
    },
    async updateOverrides(chatId: string, overrides: ChatOverrides) {
      const chat = await apiPut<Chat>(`/api/chats/${chatId}`, { overrides })
      this.activeChat = chat
      if (this.characterId) await this.loadList(this.characterId)
      return chat
    },
    async rename(chatId: string, title: string) {
      const chat = await apiPut<Chat>(`/api/chats/${chatId}`, { title })
      this.activeChat = chat
      if (this.characterId) await this.loadList(this.characterId)
      return chat
    },
    async remove(chatId: string) {
      await apiDelete(`/api/chats/${chatId}`)
      if (this.characterId) await this.loadList(this.characterId)
      if (this.activeChatId === chatId) {
        this.activeChatId = null
        this.activeChat = null
      }
    },
    async appendMessage(chatId: string, role: 'system' | 'user' | 'assistant', content: string) {
      const chat = await apiPost<Chat>(`/api/chats/${chatId}/messages`, { role, content })
      this.activeChat = chat
      if (this.characterId) await this.loadList(this.characterId)
      return chat
    },

    async updateMessage(chatId: string, messageId: string, role: 'system' | 'user' | 'assistant', content: string) {
      const chat = await apiPut<Chat>(`/api/chats/${chatId}/messages/${messageId}`, { role, content })
      this.activeChat = chat
      if (this.characterId) await this.loadList(this.characterId)
      return chat
    },

    async deleteMessage(chatId: string, messageId: string) {
      await apiDelete(`/api/chats/${chatId}/messages/${messageId}`)
      // apiDelete 返回 void，这里重新拉取保证状态一致
      await this.load(chatId)
      if (this.characterId) await this.loadList(this.characterId)
    },
  },
})


