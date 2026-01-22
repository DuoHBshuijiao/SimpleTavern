/**
 * useAssistant - 聊天助手逻辑
 * 
 * 负责聊天助手面板的消息管理、设置、流式对话等功能
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
   * 获取指定 scope 的状态
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
   * 构建助手 API 路径
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
   */
  async function saveSettings() {
    await apiPut('/api/assistant/settings', assistantSettings.value)
  }

  /**
   * 保存设置并关闭弹窗
   */
  async function saveSettingsAndClose() {
    await saveSettings()
    showAssistantSettings.value = false
  }

  /**
   * 加载助手聊天记录
   */
  async function loadChat(scope: AssistantScope) {
    const state = getState(scope)
    const res = await apiGet<{ messages: any[] }>(buildPath('/api/assistant/chat', scope))
    state.messages.value = normalizeMessages(res.messages)
  }

  /**
   * 加载助手完整状态
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
   * 重置 chat scope 聊天
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
   * 重置 workspace scope 聊天
   */
  async function resetWorkspaceChat() {
    await apiPost('/api/assistant/reset?scope=workspace', {})
    workspaceAssistantMessages.value = []
    workspaceAssistantDraft.value = ''
    workspaceAssistantStreamError.value = null
  }

  /**
   * 删除 workspace 助手聊天
   */
  async function deleteWorkspaceChat() {
    await apiPost('/api/assistant/workspace/chat/delete', {})
  }

  /**
   * 打开消息编辑弹窗
   */
  function openEditMessage(m: AssistantMessage, scope: AssistantScope) {
    editingAssistantMessage.value = m
    editingAssistantMessageContent.value = m.content
    editingAssistantMessageScope.value = scope
    showAssistantMessageEditor.value = true
  }

  /**
   * 关闭消息编辑弹窗
   */
  function closeEditMessage() {
    showAssistantMessageEditor.value = false
    editingAssistantMessage.value = null
    editingAssistantMessageContent.value = ''
    editingAssistantMessageScope.value = null
  }

  /**
   * 保存编辑的消息
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
