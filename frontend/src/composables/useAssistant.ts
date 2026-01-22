/**
 * useAssistant - 聊天助手逻辑Composable
 *
 * 负责聊天助手面板的消息管理、设置、流式对话等功能。
 * 支持两种作用域：chat（聊天作用域）和workspace（工作区作用域）。
 *
 * 主要功能：
 *    - 消息管理：加载、发送、编辑、删除助手消息
 *    - 设置管理：加载和保存助手设置（提示词、温度、模型等）
 *    - 流式对话：支持SSE流式接收助手回复
 *    - 作用域管理：区分聊天作用域和工作区作用域
 *    - 消息重写：支持重写助手消息
 *
 * 主要函数：
 *    - getState: 获取指定作用域的状态
 *    - buildPath: 构建助手API路径
 *    - normalizeMessages: 规范化消息数组
 *    - allowMemoryWrite: 检测是否允许写入记忆
 *    - loadSettings: 加载助手设置
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
  prompt: string
  temperature: number | null
  model: string | null
}

export interface UseAssistantOptions {
  chatId: ComputedRef<string | null>
}

export function useAssistant(options: UseAssistantOptions) {
  const { chatId } = options

  // Chat scope 状态
  const assistantMessages = ref<AssistantMessage[]>([])
  const assistantDraft = ref('')
  const isAssistantGenerating = ref(false)
  const assistantStreamError = ref<string | null>(null)

  // Workspace scope 状态
  const workspaceAssistantMessages = ref<AssistantMessage[]>([])
  const workspaceAssistantDraft = ref('')
  const isWorkspaceAssistantGenerating = ref(false)
  const workspaceAssistantStreamError = ref<string | null>(null)

  // 公共状态
  const showAssistantSettings = ref(false)
  const isAssistantPanelOpen = ref(false)
  const assistantSettings = ref<AssistantSettings>({
    prompt: '',
    temperature: null,
    model: null,
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
      }
    }
    return {
      messages: assistantMessages,
      draft: assistantDraft,
      streamError: assistantStreamError,
      isGenerating: isAssistantGenerating,
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
   * @param {any[]} raw - 原始消息数组
   * @returns {AssistantMessage[]} 规范化后的消息数组
   */
  function normalizeMessages(raw: any[]): AssistantMessage[] {
    return (raw || [])
      .filter((m: any) => m && (m.role === 'user' || m.role === 'assistant' || m.role === 'system'))
      .map((m: any, idx: number) => ({
        id: m.id ?? `assistant_msg_${Date.now()}_${idx}`,
        role: m.role,
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
   * 从服务器加载助手设置（提示词、温度、模型等）。
   * 使用apiGet函数（来自api/http.ts）发送GET请求到/api/assistant/settings。
   *
   * @returns {Promise<void>} 完成时返回
   */
  async function loadSettings() {
    const res = await apiGet<{ prompt: string; temperature: number | null; model: string | null }>(
      '/api/assistant/settings',
    )
    assistantSettings.value = {
      prompt: res.prompt ?? '',
      temperature: res.temperature ?? null,
      model: res.model ?? null,
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
  async function saveSettings() {
    await apiPut('/api/assistant/settings', assistantSettings.value)
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
    const res = await apiGet<{ messages: any[] }>(buildPath('/api/assistant/chat', scope))
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
    } catch (e: any) {
      const state = getState(scope)
      state.streamError.value = e?.message ?? String(e)
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
    } catch (e: any) {
      const state = getState(scope)
      state.streamError.value = e?.message ?? String(e)
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
   * @param {(card: any) => void} [onCardReceived] - 接收角色卡的回调函数（可选）
   * @returns {Promise<void>} 完成时返回
   */
  async function sendMessage(
    scope: AssistantScope, 
    appendUserMessage: boolean | Event = true,
    onCardReceived?: (card: any) => void
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
    
    state.isGenerating.value = true
    assistantAborters[scope]?.abort()
    assistantAborters[scope] = new AbortController()

    try {
      await postAndConsumeSse(
        '/api/assistant/stream',
        {
          userMessage: text,
          model: assistantSettings.value.model,
          temperature: assistantSettings.value.temperature,
          appendUserMessage: shouldAppend,
          chatId: scope === 'chat' ? chatId.value : null,
          allowWriteMemory: scope === 'chat' ? allowMemoryWrite(text) : false,
          scope,
        },
        (evt) => {
          if (evt.event === 'delta') {
            const t = evt.data?.text
            if (typeof t === 'string') {
              assistantMsg.content += t
            }
          } else if (evt.event === 'tool_trace') {
            const content = evt.data?.content
            if (typeof content === 'string' && content.trim()) {
              state.messages.value.push({
                id: evt.data?.messageId || `assistant_tool_${Date.now()}`,
                role: 'system',
                content,
                ts: new Date().toISOString(),
              })
            }
          } else if (evt.event === 'card') {
            const card = evt.data?.card
            if (card && onCardReceived) {
              onCardReceived(card)
            }
          } else if (evt.event === 'error') {
            state.streamError.value = String(evt.data?.message ?? 'unknown error')
          }
        },
        assistantAborters[scope]?.signal,
      )
    } catch (e: any) {
      if (e?.name !== 'AbortError') {
        state.streamError.value = e?.message ?? String(e)
      }
    } finally {
      state.isGenerating.value = false
      await loadChat(scope)
    }
  }

  /**
   * 处理模型选择
   *
   * 更新助手设置中的模型，并保存到服务器。
   *
   * @param {{ value: string }} option - 模型选项，包含value字段
   * @returns {Promise<void>} 完成时返回
   */
  async function handleModelSelect(option: { value: string }) {
    assistantSettings.value.model = option.value
    await saveSettings()
  }

  return {
    // Chat scope 状态
    assistantMessages,
    assistantDraft,
    isAssistantGenerating,
    assistantStreamError,

    // Workspace scope 状态
    workspaceAssistantMessages,
    workspaceAssistantDraft,
    isWorkspaceAssistantGenerating,
    workspaceAssistantStreamError,

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
    deleteMessage,
    rewriteMessage,
    sendMessage,
    handleModelSelect,
  }
}

export type UseAssistant = ReturnType<typeof useAssistant>
