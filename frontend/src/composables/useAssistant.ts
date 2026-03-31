/**
 * useAssistant - 聊天助手逻辑Composable
 *
 * 负责聊天助手面板的消息管理、设置、流式对话等功能。
 * 支持两种作用域：chat（聊天作用域）和workspace（工作区作用域）。
 *
 * 主要功能：
 *    - 消息管理：加载、发送、编辑、删除助手消息
 *    - 设置管理：加载和保存助手设置（温度、模型等）
 *    - 流式对话：支持SSE流式接收助手回复
 *    - 作用域管理：区分聊天作用域和工作区作用域
 *    - 消息重写：支持重写助手消息
 *
 * 主要函数：
 *    - getState: 获取指定作用域的状态
 *    - buildPath: 构建助手API路径
 *    - normalizeMessages: 规范化消息数组
 *    - allowMemoryWrite: 检测是否允许写入记忆
 *    - loadSettings: 加载助手设置（不含服务端保留的助手系统提示词）
 *    - saveSettings: 保存助手设置
 *    - loadChat: 加载助手聊天记录
 *    - loadState: 加载助手完整状态
 *    - resetChat: 重置聊天作用域
 *    - resetWorkspaceChat: 重置工作区作用域
 *    - sendMessage: 发送助手消息
 *    - openEditMessage: 打开消息编辑
 *    - saveEditedMessage: 保存编辑的消息
 *    - deleteMessage: 删除消息
 *    - rewriteMessage: 重写消息
 *    - handleModelSelect: 处理模型选择
 *
 * 文件关系：
 *    - 被导入：被composables/index.ts导出，被views/ChatPage.vue使用
 *    - 导入：导入vue的ref和ComputedRef、api/http.ts的HTTP函数、api/sse.ts的postAndConsumeSse
 *    - 依赖：依赖vue、api/http.ts、api/sse.ts
 *    - 位置：Composables层，提供聊天助手逻辑
 */
import { ref } from 'vue'
import type { ComputedRef } from 'vue'
import { apiGet, apiPost, apiPut, apiDelete } from '../api/http'
import { postAndConsumeSse } from '../api/sse'

export type AssistantMessage = {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  ts: string
}

export type AssistantScope = 'chat' | 'workspace'

export interface AssistantSettings {
  temperature: number | null
  model: string | null
  presetId: string | null
  /** 上下文总长度限制（token），用于裁剪最近消息 */
  context_size: number | null
}

/** 主聊天会话类型（与 stores/chats 中当前会话一致），用于记忆更新回调 */
export type ChatPayload = import('../types/models').Chat

export interface UseAssistantOptions {
  chatId: ComputedRef<string | null>
  /** 是否启用流式传输，与全局设置一致；未传时默认 true（流式） */
  streamEnabled?: ComputedRef<boolean>
  /** 助手在聊天作用域写入长期记忆后，SSE 会推送 chat_memory_updated；若传入此回调则用其更新当前会话状态，使设置抽屉与消息列表立即刷新 */
  onChatMemoryUpdated?: (chat: ChatPayload) => void
}

export function useAssistant(options: UseAssistantOptions) {
  const { chatId, streamEnabled, onChatMemoryUpdated } = options

  // Chat scope 状态
  const assistantMessages = ref<AssistantMessage[]>([])
  const assistantDraft = ref('')
  const isAssistantGenerating = ref(false)
  const assistantStreamError = ref<string | null>(null)
  /** 思考链块列表：每项为 { messageId, content }，展示在对应消息之前（仅前端临时，刷新后消失） */
  const assistantReasoningBlocks = ref<Array<{ messageId: string; content: string }>>([])
  /** 当前正在流式接收的正文（仅 chat 作用域），用于实时打字机效果 */
  const assistantStreamingContent = ref('')
  /** 当前正在流式接收的思考内容（仅 chat 作用域），用于实时显示 */
  const assistantStreamingReasoning = ref('')

  // Workspace scope 状态
  const workspaceAssistantMessages = ref<AssistantMessage[]>([])
  const workspaceAssistantDraft = ref('')
  const isWorkspaceAssistantGenerating = ref(false)
  const workspaceAssistantStreamError = ref<string | null>(null)
  const workspaceReasoningBlocks = ref<Array<{ messageId: string; content: string }>>([])
  const workspaceStreamingContent = ref('')
  const workspaceStreamingReasoning = ref('')

  // 公共状态
  const showAssistantSettings = ref(false)
  const isAssistantPanelOpen = ref(false)
  const assistantSettings = ref<AssistantSettings>({
    temperature: null,
    model: null,
    presetId: null,
    context_size: null,
  })

  // 消息编辑状态
  const showAssistantMessageEditor = ref(false)
  const editingAssistantMessage = ref<AssistantMessage | null>(null)
  const editingAssistantMessageContent = ref('')
  const editingAssistantMessageScope = ref<AssistantScope | null>(null)

  // Aborters
  const assistantAborters: Record<AssistantScope, AbortController | null> = {
    chat: null,
    workspace: null,
  }

  /**
   * 获取指定作用域的状态
   *
   * 根据作用域返回对应的状态对象（消息、草稿、错误、生成状态）。
   *
   * @param {AssistantScope} scope - 作用域（'chat'或'workspace'）
   * @returns {object} 状态对象，包含messages、draft、streamError、isGenerating
   */
  function getState(scope: AssistantScope) {
    if (scope === 'workspace') {
      return {
        messages: workspaceAssistantMessages,
        draft: workspaceAssistantDraft,
        streamError: workspaceAssistantStreamError,
        isGenerating: isWorkspaceAssistantGenerating,
        reasoningBlocks: workspaceReasoningBlocks,
        streamingContent: workspaceStreamingContent,
        streamingReasoning: workspaceStreamingReasoning,
      }
    }
    return {
      messages: assistantMessages,
      draft: assistantDraft,
      streamError: assistantStreamError,
      isGenerating: isAssistantGenerating,
      reasoningBlocks: assistantReasoningBlocks,
      streamingContent: assistantStreamingContent,
      streamingReasoning: assistantStreamingReasoning,
    }
  }

  /**
   * 构建助手API路径
   *
   * 根据作用域构建完整的API路径，添加必要的查询参数。
   * workspace作用域添加scope=workspace，chat作用域添加chatId参数。
   *
   * @param {string} base - 基础路径
   * @param {AssistantScope} scope - 作用域（'chat'或'workspace'）
   * @returns {string} 完整的API路径
   */
  function buildPath(base: string, scope: AssistantScope): string {
    const params: string[] = []
    if (scope === 'workspace') {
      params.push('scope=workspace')
    } else {
      const id = chatId.value
      if (id) params.push(`chatId=${encodeURIComponent(id)}`)
    }
    if (!params.length) return base
    const sep = base.includes('?') ? '&' : '?'
    return `${base}${sep}${params.join('&')}`
  }

  /**
   * 规范化消息数组
   *
   * 将原始消息数组转换为标准格式的AssistantMessage数组。
   * 过滤无效消息，为缺失字段提供默认值。
   *
   * @param {unknown[]} raw - 原始消息数组
   * @returns {AssistantMessage[]} 规范化后的消息数组
   */
  function normalizeMessages(raw: unknown[]): AssistantMessage[] {
    return (raw || [])
      .filter((m): m is { role?: string; id?: string; content?: string; ts?: string } => 
        m !== null && typeof m === 'object' && (m as { role?: string }).role !== undefined
      )
      .filter((m) => m.role === 'user' || m.role === 'assistant' || m.role === 'system')
      .map((m, idx: number) => ({
        id: m.id ?? `assistant_msg_${Date.now()}_${idx}`,
        role: m.role as 'user' | 'assistant' | 'system',
        content: m.content ?? '',
        ts: m.ts ?? new Date().toISOString(),
      }))
  }

  /**
   * 检测是否允许写入记忆
   *
   * 通过正则表达式检测用户消息中是否包含写入记忆的指令。
   *
   * @param {string} text - 用户消息文本
   * @returns {boolean} 是否允许写入记忆
   */
  function allowMemoryWrite(text: string): boolean {
    if (!text) return false
    const patterns = [
      /写入.*记忆/,
      /更新.*记忆/,
      /保存.*记忆/,
      /记录.*记忆/,
      /写.*长期记忆/,
      /保存.*长期记忆/,
    ]
    return patterns.some((p) => p.test(text))
  }

  /**
   * 加载助手设置
   *
   * 从服务器加载助手设置（温度、模型等）。
   * 使用apiGet函数（来自api/http.ts）发送GET请求到/api/assistant/settings。
   *
   * @returns {Promise<void>} 完成时返回
   */
  async function loadSettings() {
    const res = await apiGet<{
      temperature: number | null
      model: string | null
      presetId?: string | null
      context_size?: number | null
    }>('/api/assistant/settings')
    assistantSettings.value = {
      temperature: res.temperature ?? null,
      model: res.model ?? null,
      presetId: res.presetId ?? null,
      context_size: res.context_size ?? null,
    }
  }

  /**
   * 保存助手设置
   *
   * 将助手设置保存到服务器。
   * 使用apiPut函数（来自api/http.ts）发送PUT请求到/api/assistant/settings。
   *
   * @returns {Promise<void>} 完成时返回
   */
  /** 将 context_size 规范为 number | null：0、NaN、undefined 视为“未启用”即 null */
  function normalizeContextSize(v: number | null | undefined): number | null {
    if (v == null || Number.isNaN(v) || v < 1) return null
    return v
  }

  async function saveSettings() {
    const payload = {
      temperature: assistantSettings.value.temperature,
      model: assistantSettings.value.model,
      presetId: assistantSettings.value.presetId,
      context_size: normalizeContextSize(assistantSettings.value.context_size),
    }
    await apiPut('/api/assistant/settings', payload)
    assistantSettings.value.context_size = payload.context_size
  }

  /**
   * 保存设置并关闭弹窗
   *
   * 保存助手设置，然后关闭设置弹窗。
   *
   * @returns {Promise<void>} 完成时返回
   */
  async function saveSettingsAndClose() {
    await saveSettings()
    showAssistantSettings.value = false
  }

  /**
   * 加载助手聊天记录
   *
   * 从服务器加载指定作用域的助手聊天记录。
   * 使用apiGet函数（来自api/http.ts）发送GET请求到/api/assistant/chat。
   *
   * @param {AssistantScope} scope - 作用域（'chat'或'workspace'）
   * @returns {Promise<void>} 完成时返回
   */
  async function loadChat(scope: AssistantScope) {
    const state = getState(scope)
    const res = await apiGet<{ messages: unknown[] }>(buildPath('/api/assistant/chat', scope))
    state.messages.value = normalizeMessages(res.messages)
  }

  /**
   * 加载助手完整状态
   *
   * 同时加载助手设置和聊天记录。
   *
   * @param {AssistantScope} scope - 作用域（'chat'或'workspace'）
   * @returns {Promise<void>} 完成时返回
   */
  async function loadState(scope: AssistantScope) {
    const state = getState(scope)
    state.streamError.value = null
    try {
      await Promise.all([loadSettings(), loadChat(scope)])
    } catch (e) {
      console.error('Failed to load assistant state:', e)
    }
  }

  /**
   * 重置聊天作用域
   *
   * 重置聊天作用域的聊天记录，清空消息和草稿。
   * 使用apiPost函数（来自api/http.ts）发送POST请求到/api/assistant/reset。
   *
   * @returns {Promise<void>} 完成时返回
   */
  async function resetChat() {
    if (chatId.value) {
      await apiPost(buildPath('/api/assistant/reset', 'chat'), {})
    }
    assistantMessages.value = []
    assistantDraft.value = ''
    assistantStreamError.value = null
    assistantReasoningBlocks.value = []
  }

  /**
   * 重置工作区作用域
   *
   * 重置工作区作用域的聊天记录，清空消息和草稿。
   * 使用apiPost函数（来自api/http.ts）发送POST请求到/api/assistant/reset?scope=workspace。
   *
   * @returns {Promise<void>} 完成时返回
   */
  async function resetWorkspaceChat() {
    await apiPost('/api/assistant/reset?scope=workspace', {})
    workspaceAssistantMessages.value = []
    workspaceAssistantDraft.value = ''
    workspaceAssistantStreamError.value = null
    workspaceReasoningBlocks.value = []
  }

  /**
   * 删除工作区助手聊天
   *
   * 删除工作区作用域的助手聊天记录。
   * 使用apiPost函数（来自api/http.ts）发送POST请求到/api/assistant/workspace/chat/delete。
   *
   * @returns {Promise<void>} 完成时返回
   */
  async function deleteWorkspaceChat() {
    await apiPost('/api/assistant/workspace/chat/delete', {})
  }

  /**
   * 打开消息编辑弹窗
   *
   * 打开助手消息编辑弹窗，加载消息内容到编辑状态。
   *
   * @param {AssistantMessage} m - 要编辑的消息
   * @param {AssistantScope} scope - 作用域（'chat'或'workspace'）
   */
  function openEditMessage(m: AssistantMessage, scope: AssistantScope) {
    editingAssistantMessage.value = m
    editingAssistantMessageContent.value = m.content
    editingAssistantMessageScope.value = scope
    showAssistantMessageEditor.value = true
  }

  /**
   * 关闭消息编辑弹窗
   *
   * 关闭助手消息编辑弹窗，清空编辑状态。
   */
  function closeEditMessage() {
    showAssistantMessageEditor.value = false
    editingAssistantMessage.value = null
    editingAssistantMessageContent.value = ''
    editingAssistantMessageScope.value = null
  }

  /**
   * 保存编辑的消息
   *
   * 将编辑后的助手消息保存到服务器。
   * 使用apiPut函数（来自api/http.ts）发送PUT请求到/api/assistant/chat/messages/{id}。
   * 保存成功后重新加载聊天记录。
   *
   * @returns {Promise<void>} 完成时返回
   */
  async function saveEditedMessage() {
    if (!editingAssistantMessage.value) return
    if (!editingAssistantMessageScope.value) return
    const scope = editingAssistantMessageScope.value
    const m = editingAssistantMessage.value
    try {
      await apiPut(buildPath(`/api/assistant/chat/messages/${m.id}`, scope), {
        role: m.role,
        content: editingAssistantMessageContent.value,
      })
      await loadChat(scope)
      closeEditMessage()
    } catch (e: unknown) {
      const state = getState(scope)
      const error = e instanceof Error ? e.message : String(e)
      state.streamError.value = error
    }
  }

  /**
   * 保存编辑的消息并发送（清除该条之后的消息并重新生成）
   *
   * 与主聊天「保存并发送」行为一致：保存编辑后的用户消息，删除该消息之后的所有消息，
   * 然后以该条内容重新请求助手流式回复。
   * 仅对用户消息生效；若正在生成则直接返回。
   *
   * @returns {Promise<void>} 完成时返回
   */
  async function saveEditedMessageAndSend() {
    if (!editingAssistantMessage.value) return
    if (!editingAssistantMessageScope.value) return
    if (editingAssistantMessage.value.role !== 'user') return
    const scope = editingAssistantMessageScope.value
    const state = getState(scope)
    if (state.isGenerating.value) return

    const m = editingAssistantMessage.value
    const content = editingAssistantMessageContent.value.trim()
    try {
      await apiPut(buildPath(`/api/assistant/chat/messages/${m.id}`, scope), {
        role: m.role,
        content,
      })
      const messages = state.messages.value
      const idx = messages.findIndex(msg => msg.id === m.id)
      if (idx >= 0) {
        const toDelete = messages.slice(idx + 1)
        for (const msg of toDelete) {
          await apiDelete(buildPath(`/api/assistant/chat/messages/${msg.id}`, scope))
        }
      }
      await loadChat(scope)
      closeEditMessage()
      state.draft.value = content
      await sendMessage(scope, false)
    } catch (e: unknown) {
      const error = e instanceof Error ? e.message : String(e)
      state.streamError.value = error
    }
  }

  /**
   * 删除消息
   *
   * 删除指定的助手消息。
   * 使用apiDelete函数（来自api/http.ts）发送DELETE请求到/api/assistant/chat/messages/{id}。
   * 删除成功后重新加载聊天记录。
   *
   * @param {AssistantMessage} m - 要删除的消息
   * @param {AssistantScope} scope - 作用域（'chat'或'workspace'）
   * @returns {Promise<void>} 完成时返回
   */
  async function deleteMessage(m: AssistantMessage, scope: AssistantScope) {
    try {
      await apiDelete(buildPath(`/api/assistant/chat/messages/${m.id}`, scope))
      await loadChat(scope)
    } catch (e: unknown) {
      const state = getState(scope)
      const error = e instanceof Error ? e.message : String(e)
      state.streamError.value = error
    }
  }

  /**
   * 重写助手消息
   *
   * 删除指定的助手消息，然后使用上一个用户消息重新生成回复。
   * 如果找到上一个用户消息，则将其设置为草稿并发送。
   *
   * @param {AssistantMessage} m - 要重写的消息
   * @param {AssistantScope} scope - 作用域（'chat'或'workspace'）
   * @returns {Promise<void>} 完成时返回
   */
  async function rewriteMessage(m: AssistantMessage, scope: AssistantScope) {
    const state = getState(scope)
    const idx = state.messages.value.findIndex(msg => msg.id === m.id)
    if (idx < 0) return
    
    let lastUserMsgText = ''
    for (let i = idx - 1; i >= 0; i--) {
      const msg = state.messages.value[i]
      if (!msg) continue
      if (msg.role === 'user') {
        lastUserMsgText = msg.content
        break
      }
    }

    await deleteMessage(m, scope)
    
    if (lastUserMsgText) {
      state.draft.value = lastUserMsgText
      await sendMessage(scope, false)
    }
  }

  /**
   * 发送助手消息
   *
   * 发送用户消息给助手，接收流式回复。
   * 使用postAndConsumeSse函数（来自api/sse.ts）发送POST请求到/api/assistant/stream。
   * 支持实时接收delta事件更新消息内容，支持tool_trace事件显示工具调用，支持card事件接收角色卡。
   *
   * @param {AssistantScope} scope - 作用域（'chat'或'workspace'）
   * @param {boolean | Event} appendUserMessage - 是否追加用户消息到消息列表
   * @param {(card: unknown) => void} [onCardReceived] - 接收角色卡的回调函数（可选）
   * @returns {Promise<void>} 完成时返回
   */
  async function sendMessage(
    scope: AssistantScope, 
    appendUserMessage: boolean | Event = true,
    onCardReceived?: (card: unknown) => void
  ) {
    const state = getState(scope)
    const shouldAppend = typeof appendUserMessage === 'boolean' ? appendUserMessage : true
    const text = state.draft.value.trim()
    if (shouldAppend && !text) return
    if (state.isGenerating.value) return
    
    if (shouldAppend) state.draft.value = ''
    state.streamError.value = null

    const now = new Date().toISOString()
    
    // 本地 UI 预览
    if (shouldAppend) {
      state.messages.value.push({
        id: `assistant_user_${Date.now()}`,
        role: 'user',
        content: text,
        ts: now,
      })
    }
    
    const assistantMsgId = `assistant_ai_${Date.now()}`
    const assistantMsg: AssistantMessage = {
      id: assistantMsgId,
      role: 'assistant',
      content: '',
      ts: now,
    }
    state.messages.value.push(assistantMsg)
    state.streamingContent.value = ''
    state.streamingReasoning.value = ''
    state.isGenerating.value = true
    assistantAborters[scope]?.abort()
    assistantAborters[scope] = new AbortController()

    const useStream = streamEnabled?.value !== false
    const body = {
      userMessage: text,
      model: assistantSettings.value.model,
      temperature: assistantSettings.value.temperature,
      appendUserMessage: shouldAppend,
      chatId: scope === 'chat' ? chatId.value : null,
      allowWriteMemory: scope === 'chat' ? allowMemoryWrite(text) : false,
      scope,
    }

    let aborted = false
    let reasoningBuffer = ''
    try {
      if (useStream) {
        await postAndConsumeSse(
          '/api/assistant/stream',
          body,
          (evt) => {
            if (evt.event === 'delta') {
              const data = evt.data as { text?: string } | undefined
              const t = data?.text
              if (typeof t === 'string') {
                assistantMsg.content += t
                state.streamingContent.value += t
              }
            } else if (evt.event === 'reasoning') {
              const data = evt.data as { text?: string } | undefined
              const t = data?.text
              if (typeof t === 'string') {
                reasoningBuffer += t
                state.streamingReasoning.value += t
              }
            } else if (evt.event === 'done') {
              state.streamingContent.value = ''
              state.streamingReasoning.value = ''
              if (reasoningBuffer.trim()) {
                const data = evt.data as { messageId?: string } | undefined
                const serverMessageId = data?.messageId
                const blockMessageId = typeof serverMessageId === 'string' && serverMessageId ? serverMessageId : assistantMsgId
                state.reasoningBlocks.value = [...state.reasoningBlocks.value, { messageId: blockMessageId, content: reasoningBuffer }]
                reasoningBuffer = ''
              }
            } else if (evt.event === 'tool_trace') {
              const data = evt.data as { content?: string; messageId?: string } | undefined
              const content = data?.content
              const toolMessageId = data?.messageId || `assistant_tool_${Date.now()}`
              state.streamingReasoning.value = ''
              if (reasoningBuffer.trim()) {
                state.reasoningBlocks.value = [...state.reasoningBlocks.value, { messageId: toolMessageId, content: reasoningBuffer }]
                reasoningBuffer = ''
              }
              if (typeof content === 'string' && content.trim()) {
                state.messages.value.push({
                  id: toolMessageId,
                  role: 'system',
                  content,
                  ts: new Date().toISOString(),
                })
              }
            } else if (evt.event === 'card') {
              const data = evt.data as { card?: unknown } | undefined
              const card = data?.card
              if (card && onCardReceived) {
                onCardReceived(card)
              }
            } else if (evt.event === 'chat_memory_updated') {
              const data = evt.data as { chat?: ChatPayload } | undefined
              const chatPayload = data?.chat
              if (scope === 'chat' && chatPayload?.id && chatId.value === chatPayload.id && onChatMemoryUpdated) {
                onChatMemoryUpdated(chatPayload)
              }
            } else if (evt.event === 'error') {
              const data = evt.data as { message?: string } | undefined
              state.streamError.value = String(data?.message ?? 'unknown error')
            }
          },
          assistantAborters[scope]?.signal,
        )
      } else {
        const res = await apiPost<{
          ok: boolean
          stream?: boolean
          content?: string
          messageId?: string
          toolTraces?: Array<{ content: string; messageId: string }>
          card?: unknown
          error?: string
        }>('/api/assistant/stream', body)
        if (res?.ok && res.stream === false) {
          if (Array.isArray(res.toolTraces)) {
            for (const tt of res.toolTraces) {
              state.messages.value.push({
                id: tt.messageId || `assistant_tool_${Date.now()}`,
                role: 'system',
                content: tt.content || '',
                ts: new Date().toISOString(),
              })
            }
          }
          if (typeof res.content === 'string') {
            assistantMsg.content = res.content
          }
          if (res.card != null && onCardReceived) {
            onCardReceived(res.card)
          }
        } else if (!res?.ok && typeof res?.error === 'string') {
          state.streamError.value = res.error
        }
      }
    } catch (e: unknown) {
      if (e instanceof Error && e.name === 'AbortError') {
        aborted = true
      } else if (e instanceof Error) {
        state.streamError.value = e.message
      } else {
        state.streamError.value = String(e)
      }
    } finally {
      state.streamingContent.value = ''
      state.streamingReasoning.value = ''
      state.isGenerating.value = false
      if (aborted && assistantMsg.content.trim()) {
        try {
          await apiPost(buildPath('/api/assistant/chat/messages', scope), {
            role: 'assistant',
            content: assistantMsg.content,
          })
        } catch (_) {
          // 持久化失败时仍重新加载，避免本地与服务器不一致
        }
      }
      await loadChat(scope)
    }
  }

  /**
   * 处理模型选择
   *
   * 更新助手设置中的模型和关联的 API 预设 ID，并保存到服务器。
   * 若选项带 presetId 则使用该预设；否则清空 presetId，由后端按模型匹配预设。
   *
   * @param {{ value: string; presetId?: string | null }} option - 模型选项，含 value 与可选的 presetId
   * @returns {Promise<void>} 完成时返回
   */
  async function handleModelSelect(option: { value: string; presetId?: string | null }) {
    assistantSettings.value.model = option.value
    assistantSettings.value.presetId = option.presetId ?? null
    await saveSettings()
  }

  return {
    // Chat scope 状态
    assistantMessages,
    assistantDraft,
    isAssistantGenerating,
    assistantStreamError,
    assistantReasoningBlocks,
    assistantStreamingContent,
    assistantStreamingReasoning,

    // Workspace scope 状态
    workspaceAssistantMessages,
    workspaceAssistantDraft,
    isWorkspaceAssistantGenerating,
    workspaceAssistantStreamError,
    workspaceReasoningBlocks,
    workspaceStreamingContent,
    workspaceStreamingReasoning,

    // 公共状态
    showAssistantSettings,
    isAssistantPanelOpen,
    assistantSettings,

    // 消息编辑状态
    showAssistantMessageEditor,
    editingAssistantMessage,
    editingAssistantMessageContent,
    editingAssistantMessageScope,

    // 方法
    getState,
    loadSettings,
    saveSettings,
    saveSettingsAndClose,
    loadChat,
    loadState,
    resetChat,
    resetWorkspaceChat,
    deleteWorkspaceChat,
    openEditMessage,
    closeEditMessage,
    saveEditedMessage,
    saveEditedMessageAndSend,
    deleteMessage,
    rewriteMessage,
    sendMessage,
    handleModelSelect,
  }
}

export type UseAssistant = ReturnType<typeof useAssistant>
