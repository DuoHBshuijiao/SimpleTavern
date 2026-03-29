/**
 * 聊天Store模块
 *
 * 管理聊天会话的状态，包括单聊和群聊的CRUD操作、消息管理、成员管理等。
 *
 * 主要功能：
 *    - 聊天列表管理：加载单聊列表和群聊列表
 *    - 聊天会话管理：创建、加载、更新、删除聊天会话
 *    - 消息管理：添加、更新、删除消息
 *    - 群聊成员管理：添加、删除成员，更新成员顺序
 *    - 成员设置管理：更新群聊成员的个性化设置
 *    - 本地状态更新：用于流式传输时的实时更新
 *
 * 主要函数：
 *    - loadList: 加载单聊列表
 *    - loadGroupList: 加载群聊列表
 *    - create: 创建单聊
 *    - createGroup: 创建群聊
 *    - load: 加载单个聊天会话
 *    - updateOverrides: 更新聊天覆盖设置
 *    - rename: 重命名聊天
 *    - updateGroupDelay: 更新群聊延迟时间
 *    - updateUserPersonaId: 更新用户身份ID
 *    - remove: 删除聊天
 *    - appendMessage: 添加消息
 *    - updateMessage: 更新消息
 *    - deleteMessage: 删除消息
 *    - addMember: 添加群聊成员
 *    - removeMember: 删除群聊成员
 *    - updateMemberOrder: 更新成员顺序
 *    - updateMemberSettings: 更新成员设置
 *    - addLocalMessage: 添加本地消息（流式传输用）
 *    - appendLocalMessageContent: 追加本地消息内容（流式传输用）
 *
 * 状态说明：
 *    - characterId: 当前选中的角色ID
 *    - list: 单聊列表（来自types/models.ts的Chat[]类型）
 *    - groupList: 群聊列表（来自types/models.ts的Chat[]类型）
 *    - activeChatId: 当前激活的聊天ID
 *    - activeChat: 当前激活的聊天数据（来自types/models.ts的Chat类型）
 *    - loading: 加载状态
 *    - error: 错误信息
 *
 * 文件关系：
 *    - 被导入：被stores/index.ts导出，被composables、components、views等模块使用
 *    - 导入：导入types/models.ts的类型、api/http.ts的HTTP请求函数
 *    - 依赖：依赖pinia、api/http.ts
 *    - 位置：Store层，管理聊天会话状态
 */

import { defineStore } from 'pinia'

import type { Chat, ChatMessage, ChatOverrides, GroupMemberSettings } from '../types/models'
import { apiDelete, apiGet, apiPost, apiPut } from '../api/http'

/**
 * 聊天Store
 *
 * 使用Pinia定义聊天相关的状态管理。
 */
export const useChatsStore = defineStore('chats', {
  state: () => ({
    characterId: null as string | null,
    list: [] as Chat[],
    groupList: [] as Chat[],
    activeChatId: null as string | null,
    activeChat: null as Chat | null,
    loading: false,
    error: null as string | null,
  }),
  actions: {
    /**
     * 加载单聊列表
     *
     * 根据角色ID加载该角色的所有单聊会话列表。
     * 使用apiGet函数（来自api/http.ts）发送GET请求到/api/chats?characterId={id}。
     *
     * @param {string} characterId - 角色ID
     * @throws {Error} 请求失败时抛出错误，错误信息存储在error状态中
     */
    async loadList(characterId: string) {
      this.characterId = characterId
      this.loading = true
      this.error = null
      try {
        this.list = await apiGet<Chat[]>(`/api/chats?characterId=${encodeURIComponent(characterId)}`)
      } catch (e: unknown) {
        const error = e instanceof Error ? e.message : String(e)
        this.error = error
        throw e
      } finally {
        this.loading = false
      }
    },
    /**
     * 创建单聊
     *
     * 创建新的单聊会话。
     * 使用apiPost函数（来自api/http.ts）发送POST请求到/api/chats。
     * 创建成功后自动刷新单聊列表并设置为激活状态。
     *
     * @param {string} characterId - 角色ID
     * @param {string} [title] - 聊天标题（可选）
     * @param {boolean} [pureAiMode] - 是否纯AI模式（可选）
     * @param {string | null} [userPersonaId] - 用户身份ID（可选）
     * @returns {Promise<Chat>} 创建后的聊天会话
     */
    async create(characterId: string, title?: string, pureAiMode?: boolean, userPersonaId?: string | null) {
      const chat = await apiPost<Chat>('/api/chats', { characterId, title, pureAiMode, userPersonaId })
      await this.loadList(characterId)
      this.activeChatId = chat.id
      this.activeChat = chat
      return chat
    },
    /**
     * 创建群聊
     *
     * 创建新的群聊会话。
     * 使用apiPost函数（来自api/http.ts）发送POST请求到/api/chats。
     * 创建成功后自动刷新群聊列表并设置为激活状态。
     *
     * @param {string} characterId - 主角色ID（第一个成员）
     * @param {string[]} memberIds - 成员ID列表
     * @param {string} [title] - 聊天标题（可选，默认为"新群聊"）
     * @param {boolean} [pureAiMode] - 是否纯AI模式（可选）
     * @param {string | null} [firstMessageCharacterId] - 首句发言角色ID（可选）
     * @param {Record<string, GroupMemberSettings> | null} [memberSettings] - 成员设置（可选）
     * @param {string | null} [userPersonaId] - 用户身份ID（可选）
     * @returns {Promise<Chat>} 创建后的群聊会话
     */
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
    /**
     * 将单聊复制为新群聊（不删除原单聊）
     */
    async promoteToGroup(
      sourceChatId: string,
      opts: {
        title?: string
        memberIds: string[]
        pureAiMode?: boolean
        memberSettings?: Record<string, GroupMemberSettings> | null
        userPersonaId?: string | null
      },
    ) {
      const chat = await apiPost<Chat>(
        `/api/chats/${encodeURIComponent(sourceChatId)}/promote-to-group`,
        {
          title: opts.title,
          memberIds: opts.memberIds,
          pureAiMode: opts.pureAiMode,
          memberSettings: opts.memberSettings ?? null,
          userPersonaId: opts.userPersonaId ?? null,
        },
      )
      await this.loadGroupList()
      await this.loadList(chat.characterId)
      this.activeChatId = chat.id
      this.activeChat = chat
      return chat
    },
    /**
     * 加载群聊列表
     *
     * 加载所有群聊会话列表。
     * 使用apiGet函数（来自api/http.ts）发送GET请求到/api/chats/groups。
     *
     * @throws {Error} 请求失败时抛出错误，错误信息存储在error状态中
     */
    async loadGroupList() {
      this.loading = true
      this.error = null
      try {
        this.groupList = await apiGet<Chat[]>('/api/chats/groups')
      } catch (e: unknown) {
        const error = e instanceof Error ? e.message : String(e)
        this.error = error
        throw e
      } finally {
        this.loading = false
      }
    },
    /**
     * 加载单个聊天会话
     *
     * 根据聊天ID加载完整的聊天会话数据。
     * 使用apiGet函数（来自api/http.ts）发送GET请求到/api/chats/{chatId}。
     * 加载成功后设置为激活状态。
     *
     * @param {string} chatId - 聊天ID
     * @returns {Promise<Chat>} 聊天会话数据
     * @throws {Error} 请求失败时抛出错误，错误信息存储在error状态中
     */
    async load(chatId: string) {
      this.loading = true
      this.error = null
      try {
        const chat = await apiGet<Chat>(`/api/chats/${chatId}`)
        this.activeChatId = chat.id
        this.activeChat = chat
        return chat
      } catch (e: unknown) {
        const error = e instanceof Error ? e.message : String(e)
        this.error = error
        throw e
      } finally {
        this.loading = false
      }
    },
    /**
     * 用服务端下发的聊天数据就地更新当前会话（不发起请求）。
     * 用于助手在写入长期记忆后通过 SSE 推送的 chat_memory_updated，使前端立即刷新「当前会话」长期记忆与消息的「已保存」标记。
     *
     * @param {Chat} chat - 完整的聊天会话数据（如 /api/chats/{id} 或 SSE chat_memory_updated 的 chat）
     */
    applyChatPayload(chat: Chat) {
      if (this.activeChatId === chat.id) {
        this.activeChat = chat
      }
    },
    /**
     * 更新聊天覆盖设置
     *
     * 更新聊天会话的覆盖设置（如提示词、长期记忆、生成参数等）。
     * 使用apiPut函数（来自api/http.ts）发送PUT请求到/api/chats/{chatId}。
     * 更新成功后自动刷新单聊列表（如果存在characterId）。
     *
     * @param {string} chatId - 聊天ID
     * @param {ChatOverrides} overrides - 覆盖设置（来自types/models.ts）
     * @returns {Promise<Chat>} 更新后的聊天会话
     */
    async updateOverrides(chatId: string, overrides: ChatOverrides) {
      const { memberSettings, ...restOverrides } = overrides
      const chat = await apiPut<Chat>(`/api/chats/${chatId}`, { 
        overrides: restOverrides,
        memberSettings: memberSettings || undefined
      })
      this.activeChat = chat
      if (this.characterId) await this.loadList(this.characterId)
      return chat
    },
    /**
     * 重命名聊天
     *
     * 更新聊天会话的标题。
     * 使用apiPut函数（来自api/http.ts）发送PUT请求到/api/chats/{chatId}。
     * 更新成功后自动刷新单聊列表（如果存在characterId）。
     *
     * @param {string} chatId - 聊天ID
     * @param {string} title - 新标题
     * @returns {Promise<Chat>} 更新后的聊天会话
     */
    async rename(chatId: string, title: string) {
      const chat = await apiPut<Chat>(`/api/chats/${chatId}`, { title })
      this.activeChat = chat
      if (this.characterId) await this.loadList(this.characterId)
      return chat
    },
    /**
     * 更新群聊延迟时间
     *
     * 更新群聊中角色发言之间的延迟时间（毫秒）。
     * 使用apiPut函数（来自api/http.ts）发送PUT请求到/api/chats/{chatId}。
     * 更新成功后自动刷新群聊列表。
     *
     * @param {string} chatId - 聊天ID
     * @param {number} groupDelay - 延迟时间（毫秒）
     * @returns {Promise<Chat>} 更新后的聊天会话
     */
    async updateGroupDelay(chatId: string, groupDelay: number) {
      const chat = await apiPut<Chat>(`/api/chats/${chatId}`, { groupDelay })
      this.activeChat = chat
      await this.loadGroupList()
      return chat
    },
    /**
     * 更新用户身份ID
     *
     * 更新聊天会话关联的用户身份ID。
     * 使用apiPut函数（来自api/http.ts）发送PUT请求到/api/chats/{chatId}。
     * 更新成功后自动刷新单聊列表和群聊列表。
     *
     * @param {string} chatId - 聊天ID
     * @param {string | null} userPersonaId - 用户身份ID
     * @returns {Promise<Chat>} 更新后的聊天会话
     */
    async updateUserPersonaId(chatId: string, userPersonaId: string | null) {
      const chat = await apiPut<Chat>(`/api/chats/${chatId}`, { userPersonaId })
      this.activeChat = chat
      if (this.characterId) await this.loadList(this.characterId)
      await this.loadGroupList()
      return chat
    },
    /**
     * 删除聊天
     *
     * 删除指定的聊天会话。
     * 使用apiDelete函数（来自api/http.ts）发送DELETE请求到/api/chats/{chatId}。
     * 删除成功后自动刷新单聊列表和群聊列表。
     * 如果删除的是当前激活的聊天，则清空激活状态。
     *
     * @param {string} chatId - 聊天ID
     */
    async remove(chatId: string) {
      await apiDelete(`/api/chats/${chatId}`)
      if (this.characterId) await this.loadList(this.characterId)
      await this.loadGroupList()
      if (this.activeChatId === chatId) {
        this.activeChatId = null
        this.activeChat = null
      }
    },
    /**
     * 添加消息
     *
     * 向聊天会话添加一条新消息。
     * 使用apiPost函数（来自api/http.ts）发送POST请求到/api/chats/{chatId}/messages。
     * 添加成功后自动刷新单聊列表（如果存在characterId）。
     *
     * @param {string} chatId - 聊天ID
     * @param {'system' | 'user' | 'assistant'} role - 消息角色
     * @param {string} content - 消息内容
     * @param {{ characterId?: string }} [options] - 可选，群聊时传 characterId
     * @returns {Promise<Chat>} 更新后的聊天会话
     */
    async appendMessage(
      chatId: string,
      role: 'system' | 'user' | 'assistant',
      content: string,
      options?: { characterId?: string }
    ) {
      const body: Record<string, unknown> = { role, content }
      if (options?.characterId != null) body.characterId = options.characterId
      const chat = await apiPost<Chat>(`/api/chats/${chatId}/messages`, body)
      this.activeChat = chat
      if (this.characterId) await this.loadList(this.characterId)
      return chat
    },

    /**
     * 更新消息
     *
     * 更新聊天会话中的一条消息。
     * 使用apiPut函数（来自api/http.ts）发送PUT请求到/api/chats/{chatId}/messages/{messageId}。
     * 更新成功后自动刷新单聊列表（如果存在characterId）。
     * 群聊时传入 characterId 以保持该条消息的发言人不变。
     *
     * @param {string} chatId - 聊天ID
     * @param {string} messageId - 消息ID
     * @param {'system' | 'user' | 'assistant'} role - 消息角色
     * @param {string} content - 消息内容
     * @param {string | null | undefined} [characterId] - 群聊时发言人角色ID，传入以保持发言人
     * @returns {Promise<Chat>} 更新后的聊天会话
     */
    async updateMessage(chatId: string, messageId: string, role: 'system' | 'user' | 'assistant', content: string, characterId?: string | null) {
      const body: { role: string; content: string; characterId?: string | null } = { role, content }
      if (characterId !== undefined) body.characterId = characterId
      const chat = await apiPut<Chat>(`/api/chats/${chatId}/messages/${messageId}`, body)
      this.activeChat = chat
      if (this.characterId) await this.loadList(this.characterId)
      return chat
    },

    /**
     * 删除消息
     *
     * 删除聊天会话中的一条消息。
     * 使用apiDelete函数（来自api/http.ts）发送DELETE请求到/api/chats/{chatId}/messages/{messageId}。
     * 删除成功后重新加载聊天会话和单聊列表（如果存在characterId），保证状态一致。
     *
     * @param {string} chatId - 聊天ID
     * @param {string} messageId - 消息ID
     */
    async deleteMessage(chatId: string, messageId: string) {
      await apiDelete(`/api/chats/${chatId}/messages/${messageId}`)
      await this.load(chatId)
      if (this.characterId) await this.loadList(this.characterId)
    },
    
    /**
     * 添加群聊成员
     *
     * 向群聊中添加一个新成员。
     * 使用apiPost函数（来自api/http.ts）发送POST请求到/api/chats/{chatId}/members/{memberId}。
     * 添加成功后自动刷新群聊列表。
     *
     * @param {string} chatId - 聊天ID
     * @param {string} memberId - 成员角色ID
     * @returns {Promise<Chat>} 更新后的聊天会话
     */
    async addMember(chatId: string, memberId: string) {
      const chat = await apiPost<Chat>(`/api/chats/${chatId}/members/${memberId}`, {})
      this.activeChat = chat
      await this.loadGroupList()
      return chat
    },
    /**
     * 删除群聊成员
     *
     * 从群聊中删除一个成员。
     * 使用apiDelete函数（来自api/http.ts）发送DELETE请求到/api/chats/{chatId}/members/{memberId}。
     * 删除成功后重新加载聊天会话和群聊列表，保证状态一致。
     *
     * @param {string} chatId - 聊天ID
     * @param {string} memberId - 成员角色ID
     */
    async removeMember(chatId: string, memberId: string) {
      await apiDelete(`/api/chats/${chatId}/members/${memberId}`)
      await this.load(chatId)
      await this.loadGroupList()
    },
    /**
     * 更新成员顺序
     *
     * 更新群聊中成员的发言顺序。
     * 使用apiPut函数（来自api/http.ts）发送PUT请求到/api/chats/{chatId}。
     * 更新成功后自动刷新群聊列表。
     *
     * @param {string} chatId - 聊天ID
     * @param {string[]} memberIds - 新的成员ID顺序列表
     * @returns {Promise<Chat>} 更新后的聊天会话
     */
    async updateMemberOrder(chatId: string, memberIds: string[]) {
      const chat = await apiPut<Chat>(`/api/chats/${chatId}`, { memberIds })
      this.activeChat = chat
      await this.loadGroupList()
      return chat
    },
    /**
     * 更新成员设置
     *
     * 更新群聊中某个成员的个性化设置（如模型、参数、参与概率等）。
     * 使用apiPut函数（来自api/http.ts）发送PUT请求到/api/chats/{chatId}。
     *
     * @param {string} chatId - 聊天ID
     * @param {string} memberId - 成员角色ID
     * @param {GroupMemberSettings} settings - 成员设置（来自types/models.ts）
     * @returns {Promise<Chat>} 更新后的聊天会话
     */
    async updateMemberSettings(chatId: string, memberId: string, settings: GroupMemberSettings) {
      const memberSettings = { [memberId]: settings }
      const chat = await apiPut<Chat>(`/api/chats/${chatId}`, { memberSettings })
      this.activeChat = chat
      return chat
    },
    /**
     * 添加本地消息
     *
     * 用于流式传输时，在本地状态中添加临时消息，实现实时预览。
     * 不发送网络请求，仅更新本地状态。
     *
     * @param {ChatMessage} message - 消息对象
     */
    addLocalMessage(message: ChatMessage) {
      if (!this.activeChat) return
      this.activeChat.messages.push(message)
    },

    /**
     * 追加本地消息内容
     *
     * 用于流式传输时，实时追加消息内容，实现打字机效果。
     * 不发送网络请求，仅更新本地状态。
     * 由useStreamOutput composable（来自composables/useStreamOutput.ts）调用。
     *
     * @param {string} messageId - 消息ID
     * @param {string} delta - 要追加的内容增量
     */
    appendLocalMessageContent(messageId: string, delta: string) {
      if (!this.activeChat) return
      const msg = this.activeChat.messages.find(m => m.id === messageId)
      if (msg) {
        msg.content += delta
      }
    },
  },
})


