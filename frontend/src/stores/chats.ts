import { defineStore } from 'pinia'

import type { Chat, ChatOverrides, GroupMemberSettings } from '../types/models'
import { apiDelete, apiGet, apiPost, apiPut } from '../api/http'

export const useChatsStore = defineStore('chats', {
  state: () => ({
    characterId: null as string | null,
    list: [] as Chat[],
    groupList: [] as Chat[],  // 群聊列表
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
    async create(characterId: string, title?: string, pureAiMode?: boolean, userPersonaId?: string | null) {
      const chat = await apiPost<Chat>('/api/chats', { characterId, title, pureAiMode, userPersonaId })
      await this.loadList(characterId)
      this.activeChatId = chat.id
      this.activeChat = chat
      return chat
    },
    async createGroup(
      characterId: string,
      memberIds: string[],
      title?: string,
      pureAiMode?: boolean,
      firstMessageCharacterId?: string | null,
      memberSettings?: Record<string, GroupMemberSettings> | null,
      userPersonaId?: string | null,
    ) {
      const chat = await apiPost<Chat>('/api/chats', { 
        characterId, 
        title: title || '新群聊',
        isGroup: true,
        memberIds,
        pureAiMode,
        firstMessageCharacterId: firstMessageCharacterId ?? null,
        memberSettings: memberSettings ?? null,
        userPersonaId: userPersonaId ?? null,
      })
      await this.loadGroupList()
      this.activeChatId = chat.id
      this.activeChat = chat
      return chat
    },
    async loadGroupList() {
      this.loading = true
      this.error = null
      try {
        this.groupList = await apiGet<Chat[]>('/api/chats/groups')
      } catch (e: any) {
        this.error = e?.message ?? String(e)
        throw e
      } finally {
        this.loading = false
      }
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
    async updateGroupDelay(chatId: string, groupDelay: number) {
      const chat = await apiPut<Chat>(`/api/chats/${chatId}`, { groupDelay })
      this.activeChat = chat
      await this.loadGroupList()
      return chat
    },
    async updateUserPersonaId(chatId: string, userPersonaId: string | null) {
      const chat = await apiPut<Chat>(`/api/chats/${chatId}`, { userPersonaId })
      this.activeChat = chat
      if (this.characterId) await this.loadList(this.characterId)
      await this.loadGroupList()
      return chat
    },
    async remove(chatId: string) {
      await apiDelete(`/api/chats/${chatId}`)
      if (this.characterId) await this.loadList(this.characterId)
      await this.loadGroupList()  // 同时刷新群聊列表
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
    
    // ========== 群成员管理 ==========
    async addMember(chatId: string, memberId: string) {
      const chat = await apiPost<Chat>(`/api/chats/${chatId}/members/${memberId}`, {})
      this.activeChat = chat
      await this.loadGroupList()
      return chat
    },
    async removeMember(chatId: string, memberId: string) {
      await apiDelete(`/api/chats/${chatId}/members/${memberId}`)
      // 重新加载聊天数据
      await this.load(chatId)
      await this.loadGroupList()
    },
    async updateMemberOrder(chatId: string, memberIds: string[]) {
      const chat = await apiPut<Chat>(`/api/chats/${chatId}`, { memberIds })
      this.activeChat = chat
      await this.loadGroupList()
      return chat
    },
    
    // ========== 成员设置管理 ==========
    async updateMemberSettings(chatId: string, memberId: string, settings: GroupMemberSettings) {
      const memberSettings = { [memberId]: settings }
      const chat = await apiPut<Chat>(`/api/chats/${chatId}`, { memberSettings })
      this.activeChat = chat
      return chat
    },

    // ========== 本地状态更新 (用于流式传输) ==========
    addLocalMessage(message: any) {
      if (!this.activeChat) return
      this.activeChat.messages.push(message)
    },

    appendLocalMessageContent(messageId: string, delta: string) {
      if (!this.activeChat) return
      const msg = this.activeChat.messages.find(m => m.id === messageId)
      if (msg) {
        msg.content += delta
      }
    },
  },
})


