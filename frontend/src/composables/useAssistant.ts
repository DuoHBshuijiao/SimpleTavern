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
 *    - 记忆写入 / 破坏性工具：由界面开关与请求体控制
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
import { nextTick, ref } from 'vue'
import type { ComputedRef } from 'vue'
import { apiGet, apiPost, apiPut, apiDelete } from '../api/http'
import { postAndConsumeSse } from '../api/sse'
import { notifyConfirm, notifyMessage } from './useNotify'
import type { AssistantAttachment } from '../types/models'

export type AssistantMessage = {
  id: string
  role: 'user' | 'assistant' | 'system' | 'tool' | 'reasoning'
  content: string
  ts: string
  attachments?: AssistantAttachment[]
  /** 持久化助手消息上的推理/思考链（与后端 reasoningContent 对齐；仅 assistant 从 API 恢复时可能有） */
  reasoningContent?: string | null
  /** 推理/思考耗时（秒，浮点，前端展示一位小数） */
  reasoningDurationSec?: number | null
  /** OpenAI 对齐：对应 assistant.tool_calls[].id */
  tool_call_id?: string
  /** 结构化工具调用记录（与后端 ChatMessage.toolRecord 对齐；SSE 工具步骤或历史 system 摘要） */
  toolRecord?: Record<string, unknown>
}

export type AssistantScope = 'chat' | 'workspace'

type AssistantIngestResponse = {
  attachments: AssistantAttachment[]
  workspaceSessionId?: string | null
}

/** 程序化发送助手消息时的选项（如自动记忆总结） */
export type SendAssistantMessageOptions = {
  /** 覆盖输入框草稿的正文 */
  userMessageOverride?: string
  /** 仅本次请求覆盖「记忆写入」开关（聊天作用域） */
  allowWriteMemoryOverride?: boolean
  /** 仅本次请求覆盖「破坏性工具」开关 */
  allowDestructiveToolsOverride?: boolean
}

/** 自动触发记忆总结时注入助手会话的 user 正文 */
export const AUTO_MEMORY_SUMMARY_USER_MESSAGE =
  '[这是一条自动消息]：用户要求你现在阅读最近的聊天内容，然后总结故事发展，关键人物，承诺，物品，情绪变化等，追加到长期记忆中。'

export interface AssistantSettings {
  temperature: number | null
  model: string | null
  presetId: string | null
  /** 上下文总长度限制（token），用于裁剪最近消息 */
  context_size: number | null
  /** 助手读取会话消息条数上限（服务端 chat_read_conversation） */
  tool_read_max_messages?: number | null
  /** 助手读取会话消息 token 估算上限（服务端 chat_read_conversation） */
  tool_read_max_tokens?: number | null
  /** 单次请求最大工具轮次数 */
  maxToolTurns?: number | null
  /** 单轮最大工具调用数 */
  maxToolsPerTurn?: number | null
}

/** 主聊天会话类型（与 stores/chats 中当前会话一致），用于记忆更新回调 */
export type ChatPayload = import('../types/models').Chat

export interface UseAssistantOptions {
  chatId: ComputedRef<string | null>
  /** 是否启用流式传输，与全局设置一致；未传时默认 true（流式） */
  streamEnabled?: ComputedRef<boolean>
  /** 助手在聊天作用域写入长期记忆后，SSE 会推送 chat_memory_updated；若传入此回调则用其更新当前会话状态，使设置抽屉与消息列表立即刷新 */
  onChatMemoryUpdated?: (chat: ChatPayload) => void
  /** 世界书被助手修改后 SSE worldbook_updated（可选，用于刷新世界书列表等） */
  onWorldbookUpdated?: (payload: { worldbookId?: string }) => void
  /** 当前会话 Chat.overrides 被助手修改后 SSE chat_overrides_updated */
  onChatOverridesUpdated?: (payload: { chatId?: string }) => void
}

export function useAssistant(options: UseAssistantOptions) {
  const { chatId, streamEnabled, onChatMemoryUpdated, onWorldbookUpdated, onChatOverridesUpdated } = options

  // Chat scope 状态
  const assistantMessages = ref<AssistantMessage[]>([])
  const assistantDraft = ref('')
  const assistantDraftAttachments = ref<AssistantAttachment[]>([])
  const isAssistantGenerating = ref(false)
  const assistantStreamError = ref<string | null>(null)
  /** 当前正在流式接收的正文（仅 chat 作用域），用于实时打字机效果 */
  const assistantStreamingContent = ref('')
  /** 当前正在流式接收的思考内容（仅 chat 作用域），用于实时显示 */
  const assistantStreamingReasoning = ref('')

  // Workspace scope 状态
  const workspaceAssistantMessages = ref<AssistantMessage[]>([])
  const workspaceAssistantDraft = ref('')
  const workspaceAssistantDraftAttachments = ref<AssistantAttachment[]>([])
  const workspaceSessionId = ref<string | null>(null)
  const isWorkspaceAssistantGenerating = ref(false)
  const workspaceAssistantStreamError = ref<string | null>(null)
  const workspaceStreamingContent = ref('')
  const workspaceStreamingReasoning = ref('')
  /** 首条正文 delta 前为 true（chat 作用域，供 ReasoningBubble 流式态） */
  const assistantReasoningStreamPhaseActive = ref(false)
  /** 首条正文 delta 前为 true（workspace 作用域） */
  const workspaceReasoningStreamPhaseActive = ref(false)

  // 公共状态
  const showAssistantSettings = ref(false)
  const isAssistantPanelOpen = ref(false)
  const assistantSettings = ref<AssistantSettings>({
    temperature: null,
    model: null,
    presetId: null,
    context_size: null,
    tool_read_max_messages: null,
    tool_read_max_tokens: null,
    maxToolTurns: 8,
    maxToolsPerTurn: null,
  })

  const LS_ASSISTANT_MEM = 'assistant_allow_write_memory'
  const LS_ASSISTANT_DEST = 'assistant_allow_destructive_tools'
  const LS_WARNED_MEM = 'assistant_warned_memory_switch'
  const LS_WARNED_DEST = 'assistant_warned_destructive_switch'

  const allowWriteMemoryEnabled = ref(false)
  const allowDestructiveToolsEnabled = ref(false)

  function loadAssistantToolPrefs() {
    try {
      allowWriteMemoryEnabled.value = localStorage.getItem(LS_ASSISTANT_MEM) === '1'
      allowDestructiveToolsEnabled.value = localStorage.getItem(LS_ASSISTANT_DEST) === '1'
    } catch {
      /* ignore */
    }
  }

  function persistAssistantToolPrefs() {
    try {
      localStorage.setItem(LS_ASSISTANT_MEM, allowWriteMemoryEnabled.value ? '1' : '0')
      localStorage.setItem(LS_ASSISTANT_DEST, allowDestructiveToolsEnabled.value ? '1' : '0')
    } catch {
      /* ignore */
    }
  }

  loadAssistantToolPrefs()

  async function setAllowWriteMemory(next: boolean) {
    if (allowWriteMemoryEnabled.value === next) return
    if (next && !localStorage.getItem(LS_WARNED_MEM)) {
      const ok = await notifyConfirm({
        title: '提示',
        message:
          '开启「记忆写入」后，助手可在当前会话中追加或覆盖长期记忆。请仅在信任当前对话时使用。',
      })
      if (!ok) return
      try {
        localStorage.setItem(LS_WARNED_MEM, '1')
      } catch {
        /* ignore */
      }
    }
    allowWriteMemoryEnabled.value = next
    persistAssistantToolPrefs()
  }

  async function setAllowDestructiveTools(next: boolean) {
    if (allowDestructiveToolsEnabled.value === next) return
    if (next && !localStorage.getItem(LS_WARNED_DEST)) {
      const ok = await notifyConfirm({
        title: '提示',
        message:
          '开启「破坏性工具」后，助手可执行删除文件、删除世界书、覆盖整卡与覆盖全部记忆等不可逆操作。请谨慎使用。',
        variant: 'danger',
      })
      if (!ok) return
      try {
        localStorage.setItem(LS_WARNED_DEST, '1')
      } catch {
        /* ignore */
      }
    }
    allowDestructiveToolsEnabled.value = next
    persistAssistantToolPrefs()
  }

  function toggleAllowWriteMemory() {
    void setAllowWriteMemory(!allowWriteMemoryEnabled.value)
  }

  function toggleAllowDestructiveTools() {
    void setAllowDestructiveTools(!allowDestructiveToolsEnabled.value)
  }

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
        streamingContent: workspaceStreamingContent,
        streamingReasoning: workspaceStreamingReasoning,
      }
    }
    return {
      messages: assistantMessages,
      draft: assistantDraft,
      streamError: assistantStreamError,
      isGenerating: isAssistantGenerating,
      streamingContent: assistantStreamingContent,
      streamingReasoning: assistantStreamingReasoning,
    }
  }

  function getDraftAttachmentsRef(scope: AssistantScope) {
    return scope === 'workspace' ? workspaceAssistantDraftAttachments : assistantDraftAttachments
  }

  function clearDraftAttachments(scope: AssistantScope) {
    getDraftAttachmentsRef(scope).value = []
  }

  function removeDraftAttachment(scope: AssistantScope, attachmentId: string) {
    const draftAttachments = getDraftAttachmentsRef(scope)
    draftAttachments.value = draftAttachments.value.filter((attachment) => attachment.id !== attachmentId)
  }

  function fileToDataUrl(file: File): Promise<string> {
    return new Promise((resolve, reject) => {
      const reader = new FileReader()
      reader.onload = () => resolve(String(reader.result || ''))
      reader.onerror = () => reject(new Error(`failed to read file: ${file.name}`))
      reader.readAsDataURL(file)
    })
  }

  async function ingestDraftFiles(scope: AssistantScope, files: File[]) {
    if (!files.length) return
    if (scope === 'chat' && !chatId.value) {
      await notifyMessage('当前没有激活会话，无法添加助手附件。', { title: '提示' })
      return
    }
    const payloadFiles = await Promise.all(
      files.map(async (file) => ({
        fileData: await fileToDataUrl(file),
        mimeType: file.type || 'application/octet-stream',
        originalName: file.name,
      })),
    )
    const res = await apiPost<AssistantIngestResponse>('/api/assistant/attachments/ingest', {
      scope,
      chatId: scope === 'chat' ? chatId.value : null,
      workspaceSessionId: scope === 'workspace' ? workspaceSessionId.value : null,
      files: payloadFiles,
    })
    if (scope === 'workspace' && res.workspaceSessionId) {
      workspaceSessionId.value = res.workspaceSessionId
    }
    if (!res.attachments?.length) return
    const draftAttachments = getDraftAttachmentsRef(scope)
    const existingIds = new Set(draftAttachments.value.map((attachment) => attachment.id))
    draftAttachments.value = [
      ...draftAttachments.value,
      ...res.attachments.filter((attachment) => !existingIds.has(attachment.id)),
    ]
  }

  async function cleanupWorkspaceSession() {
    const sessionId = workspaceSessionId.value
    if (!sessionId) return
    try {
      await apiPost('/api/assistant/workspace/session/cleanup', { sessionId })
    } finally {
      workspaceSessionId.value = null
      workspaceAssistantDraftAttachments.value = []
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
      .filter(
        (m) =>
          m.role === 'user' ||
          m.role === 'assistant' ||
          m.role === 'system' ||
          m.role === 'tool',
      )
      .map((m, idx: number) => {
        const rc =
          typeof (m as { reasoningContent?: unknown }).reasoningContent === 'string'
            ? (m as { reasoningContent: string }).reasoningContent
            : null
        return {
          id: m.id ?? `assistant_msg_${Date.now()}_${idx}`,
          role: m.role as 'user' | 'assistant' | 'system' | 'tool',
          content: m.content ?? '',
          ts: m.ts ?? new Date().toISOString(),
          attachments: Array.isArray((m as { attachments?: unknown }).attachments)
            ? ((m as { attachments: AssistantAttachment[] }).attachments)
            : undefined,
          reasoningContent: rc && rc.trim() ? rc : undefined,
          tool_call_id:
            typeof (m as { tool_call_id?: unknown }).tool_call_id === 'string'
              ? (m as { tool_call_id: string }).tool_call_id
              : undefined,
          toolRecord:
            m && typeof (m as { toolRecord?: unknown }).toolRecord === 'object' && (m as { toolRecord?: unknown }).toolRecord
              ? ((m as { toolRecord: Record<string, unknown> }).toolRecord)
              : undefined,
        }
      })
  }

  function normalizePositiveInt(value: number | null | undefined): number | null {
    if (value == null || Number.isNaN(value) || value < 1) return null
    return Math.floor(value)
  }

  function upsertToolMessage(
    state: ReturnType<typeof getState>,
    payload: {
      messageId?: string
      content?: string
      record?: Record<string, unknown>
    },
  ) {
    const id = payload.messageId || `assistant_tool_${Date.now()}`
    const content = payload.content ?? ''
    const existing = state.messages.value.find((message) => message.id === id)
    if (existing) {
      existing.role = 'tool'
      existing.content = content || existing.content
      existing.toolRecord = payload.record ?? existing.toolRecord
      return
    }
    state.messages.value.push({
      id,
      role: 'tool',
      content,
      ts: new Date().toISOString(),
      toolRecord: payload.record,
    })
  }

  function pushReasoningSegment(state: ReturnType<typeof getState>, text: string, seq: number) {
    const trimmed = text.trim()
    if (!trimmed) return
    const now = new Date().toISOString()
    state.messages.value.push({
      id: `assistant_reasoning_${Date.now()}_${seq}`,
      role: 'reasoning',
      content: trimmed,
      ts: now,
    })
  }

  function pushAssistantSegment(state: ReturnType<typeof getState>, text: string, seq: number) {
    const trimmed = text.trim()
    if (!trimmed) return
    const now = new Date().toISOString()
    state.messages.value.push({
      id: `assistant_ai_${Date.now()}_${seq}`,
      role: 'assistant',
      content: trimmed,
      ts: now,
    })
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
      tool_read_max_messages?: number | null
      tool_read_max_tokens?: number | null
      maxToolTurns?: number | null
      maxToolsPerTurn?: number | null
    }>('/api/assistant/settings')
    assistantSettings.value = {
      temperature: res.temperature ?? null,
      model: res.model ?? null,
      presetId: res.presetId ?? null,
      context_size: res.context_size ?? null,
      tool_read_max_messages: res.tool_read_max_messages ?? null,
      tool_read_max_tokens: res.tool_read_max_tokens ?? null,
      maxToolTurns: res.maxToolTurns ?? 8,
      maxToolsPerTurn: res.maxToolsPerTurn ?? null,
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
      tool_read_max_messages:
        assistantSettings.value.tool_read_max_messages != null &&
        assistantSettings.value.tool_read_max_messages >= 1
          ? assistantSettings.value.tool_read_max_messages
          : null,
      tool_read_max_tokens:
        assistantSettings.value.tool_read_max_tokens != null &&
        assistantSettings.value.tool_read_max_tokens >= 1
          ? assistantSettings.value.tool_read_max_tokens
          : null,
      maxToolTurns: normalizePositiveInt(assistantSettings.value.maxToolTurns),
      maxToolsPerTurn: normalizePositiveInt(assistantSettings.value.maxToolsPerTurn),
    }
    await apiPut('/api/assistant/settings', payload)
    assistantSettings.value.context_size = payload.context_size
    assistantSettings.value.tool_read_max_messages = payload.tool_read_max_messages ?? null
    assistantSettings.value.tool_read_max_tokens = payload.tool_read_max_tokens ?? null
    assistantSettings.value.maxToolTurns = payload.maxToolTurns ?? 8
    assistantSettings.value.maxToolsPerTurn = payload.maxToolsPerTurn ?? null
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
    assistantDraftAttachments.value = []
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
    workspaceAssistantDraftAttachments.value = []
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
    workspaceAssistantMessages.value = []
    workspaceAssistantDraft.value = ''
    workspaceAssistantDraftAttachments.value = []
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
    if (m.role === 'system' || m.role === 'tool' || m.role === 'reasoning') return
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
    if (m.role === 'reasoning') {
      const state = getState(scope)
      const idx = state.messages.value.findIndex((msg) => msg.id === m.id)
      if (idx >= 0) state.messages.value.splice(idx, 1)
      return
    }
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
   * @param {SendAssistantMessageOptions} [sendOptions] - 程序化发送选项（覆盖草稿与本次请求的权限）
   * @returns {Promise<void>} 完成时返回
   */
  async function sendMessage(
    scope: AssistantScope, 
    appendUserMessage: boolean | Event = true,
    onCardReceived?: (card: unknown) => void,
    sendOptions?: SendAssistantMessageOptions,
  ) {
    const state = getState(scope)
    const shouldAppend = typeof appendUserMessage === 'boolean' ? appendUserMessage : true
    const draftAttachments = shouldAppend && !sendOptions?.userMessageOverride
      ? [...getDraftAttachmentsRef(scope).value]
      : []
    const text = (sendOptions?.userMessageOverride ?? state.draft.value).trim()
    if (shouldAppend && !text && draftAttachments.length === 0) return
    if (state.isGenerating.value) return
    
    if (shouldAppend && !sendOptions?.userMessageOverride) {
      state.draft.value = ''
      clearDraftAttachments(scope)
    }
    state.streamError.value = null

    const now = new Date().toISOString()
    
    // 本地 UI 预览
    if (shouldAppend) {
      state.messages.value.push({
        id: `assistant_user_${Date.now()}`,
        role: 'user',
        content: text,
        attachments: draftAttachments,
        ts: now,
      })
    }
    
    state.streamingContent.value = ''
    state.streamingReasoning.value = ''
    state.isGenerating.value = true
    if (scope === 'workspace') {
      workspaceReasoningStreamPhaseActive.value = true
    } else {
      assistantReasoningStreamPhaseActive.value = true
    }
    assistantAborters[scope]?.abort()
    assistantAborters[scope] = new AbortController()

    const useStream = streamEnabled?.value !== false
    const allowWriteMemory =
      scope === 'chat'
        ? sendOptions?.allowWriteMemoryOverride !== undefined
          ? sendOptions.allowWriteMemoryOverride
          : allowWriteMemoryEnabled.value
        : false
    const allowDestructiveTools =
      sendOptions?.allowDestructiveToolsOverride !== undefined
        ? sendOptions.allowDestructiveToolsOverride
        : allowDestructiveToolsEnabled.value
    const body = {
      userMessage: text,
      model: assistantSettings.value.model,
      temperature: assistantSettings.value.temperature,
      appendUserMessage: shouldAppend,
      chatId: scope === 'chat' ? chatId.value : null,
      allowWriteMemory,
      allowDestructiveTools,
      scope,
      attachments: draftAttachments,
    }

    let aborted = false
    let reasoningBuffer = ''
    let deltaBuffer = ''
    let needsFlushBeforeTool = true
    let afterToolTrace = false
    let segmentSeq = 0

    function flushSegmentBeforeToolsIfNeeded() {
      state.streamingReasoning.value = ''
      state.streamingContent.value = ''
      if (!needsFlushBeforeTool) return
      if (reasoningBuffer.trim()) {
        pushReasoningSegment(state, reasoningBuffer, segmentSeq++)
        reasoningBuffer = ''
      }
      if (deltaBuffer.trim()) {
        pushAssistantSegment(state, deltaBuffer, segmentSeq++)
        deltaBuffer = ''
      }
      needsFlushBeforeTool = false
    }

    function handleToolEvent(data: {
      content?: string
      messageId?: string
      record?: Record<string, unknown>
    } | undefined) {
      flushSegmentBeforeToolsIfNeeded()
      afterToolTrace = true
      upsertToolMessage(state, {
        messageId: data?.messageId,
        content: data?.content ?? (data?.record ? JSON.stringify(data.record) : ''),
        record: data?.record,
      })
    }

    try {
      if (useStream) {
        await postAndConsumeSse(
          '/api/assistant/stream',
          body,
          (evt) => {
            if (evt.event === 'delta') {
              if (scope === 'workspace') {
                workspaceReasoningStreamPhaseActive.value = false
              } else {
                assistantReasoningStreamPhaseActive.value = false
              }
              const data = evt.data as { text?: string } | undefined
              const t = data?.text
              if (typeof t === 'string') {
                if (afterToolTrace) {
                  needsFlushBeforeTool = true
                  afterToolTrace = false
                }
                deltaBuffer += t
                state.streamingContent.value += t
              }
            } else if (evt.event === 'reasoning') {
              const data = evt.data as { text?: string } | undefined
              const t = data?.text
              if (typeof t === 'string') {
                if (afterToolTrace) {
                  needsFlushBeforeTool = true
                  afterToolTrace = false
                }
                reasoningBuffer += t
                state.streamingReasoning.value += t
              }
            } else if (evt.event === 'done') {
              if (scope === 'workspace') {
                workspaceReasoningStreamPhaseActive.value = false
              } else {
                assistantReasoningStreamPhaseActive.value = false
              }
              state.streamingContent.value = ''
              state.streamingReasoning.value = ''
              if (reasoningBuffer.trim()) {
                pushReasoningSegment(state, reasoningBuffer, segmentSeq++)
                reasoningBuffer = ''
              }
              if (deltaBuffer.trim()) {
                pushAssistantSegment(state, deltaBuffer, segmentSeq++)
                deltaBuffer = ''
              }
              const data = evt.data as { messageId?: string } | undefined
              const serverMessageId = data?.messageId
              if (typeof serverMessageId === 'string' && serverMessageId.trim()) {
                const msgs = state.messages.value
                for (let i = msgs.length - 1; i >= 0; i--) {
                  const m = msgs[i]
                  if (m && m.role === 'assistant') {
                    m.id = serverMessageId.trim()
                    break
                  }
                }
              }
            } else if (evt.event === 'tool_trace') {
              const data = evt.data as {
                content?: string
                messageId?: string
                record?: Record<string, unknown>
              } | undefined
              handleToolEvent(data)
            } else if (evt.event === 'tool_record') {
              const data = evt.data as {
                content?: string
                messageId?: string
                record?: Record<string, unknown>
              } | undefined
              handleToolEvent(data)
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
            } else if (evt.event === 'worldbook_updated') {
              const data = evt.data as { worldbookId?: string } | undefined
              onWorldbookUpdated?.(data ?? {})
            } else if (evt.event === 'chat_overrides_updated') {
              const data = evt.data as { chatId?: string } | undefined
              onChatOverridesUpdated?.(data ?? {})
            } else if (evt.event === 'error') {
              if (scope === 'workspace') {
                workspaceReasoningStreamPhaseActive.value = false
              } else {
                assistantReasoningStreamPhaseActive.value = false
              }
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
          toolTraces?: Array<{ content?: string; messageId: string; record?: Record<string, unknown> }>
          toolRecords?: Array<{ content?: string; messageId: string; record?: Record<string, unknown> }>
          card?: unknown
          worldbookUpdated?: Array<{ worldbookId?: string }>
          chatOverridesUpdated?: Array<{ chatId?: string }>
          error?: string
        }>('/api/assistant/stream', body)
        if (res?.ok && res.stream === false) {
          if (Array.isArray(res.worldbookUpdated)) {
            for (const u of res.worldbookUpdated) {
              onWorldbookUpdated?.(u ?? {})
            }
          }
          if (Array.isArray(res.chatOverridesUpdated)) {
            for (const u of res.chatOverridesUpdated) {
              onChatOverridesUpdated?.(u ?? {})
            }
          }
          if (Array.isArray(res.toolTraces)) {
            for (const tt of res.toolTraces) {
              upsertToolMessage(state, {
                messageId: tt.messageId,
                content: tt.content || (tt.record ? JSON.stringify(tt.record) : ''),
                record: tt.record,
              })
            }
          }
          if (Array.isArray(res.toolRecords)) {
            for (const tt of res.toolRecords) {
              upsertToolMessage(state, {
                messageId: tt.messageId,
                content: tt.content || (tt.record ? JSON.stringify(tt.record) : ''),
                record: tt.record,
              })
            }
          }
          if (typeof res.content === 'string' && res.content.trim()) {
            const mid =
              typeof res.messageId === 'string' && res.messageId.trim()
                ? res.messageId.trim()
                : `assistant_ai_${Date.now()}`
            state.messages.value.push({
              id: mid,
              role: 'assistant',
              content: res.content,
              ts: new Date().toISOString(),
            })
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
      const hadStreamingSurface =
        (state.streamingReasoning.value ?? '').trim() !== '' || (state.streamingContent.value ?? '').trim() !== ''
      if (scope === 'workspace') {
        workspaceReasoningStreamPhaseActive.value = false
      } else {
        assistantReasoningStreamPhaseActive.value = false
      }
      if (aborted || hadStreamingSurface) {
        await nextTick()
        await new Promise<void>((resolve) => {
          requestAnimationFrame(() => {
            requestAnimationFrame(() => resolve())
          })
        })
      }
      state.streamingContent.value = ''
      state.streamingReasoning.value = ''
      state.isGenerating.value = false
      if (aborted) {
        const reasoningPersist = reasoningBuffer.trim()
        const msgs = state.messages.value
        const parts: string[] = []
        for (let i = msgs.length - 1; i >= 0; i--) {
          const m = msgs[i]
          if (!m) continue
          if (m.role === 'user') break
          if (m.role === 'assistant' && m.content.trim()) {
            parts.unshift(m.content.trim())
          }
        }
        const merged = parts.join('\n\n')
        if (merged.trim() || reasoningPersist) {
          try {
            await apiPost(buildPath('/api/assistant/chat/messages', scope), {
              role: 'assistant',
              content: merged,
              ...(reasoningPersist ? { reasoningContent: reasoningPersist } : {}),
            })
          } catch (_) {
            // 持久化失败时仍重新加载，避免本地与服务器不一致
          }
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

  /**
   * 以 user 身份发送自动记忆总结提示并流式完成（本次请求强制允许写入长期记忆、禁止破坏性工具）。
   * @returns 是否未出现 stream 错误
   */
  async function runAutoMemorySummaryPrompt(): Promise<boolean> {
    const state = getState('chat')
    state.streamError.value = null
    await sendMessage('chat', true, undefined, {
      userMessageOverride: AUTO_MEMORY_SUMMARY_USER_MESSAGE,
      allowWriteMemoryOverride: true,
      allowDestructiveToolsOverride: false,
    })
    return !state.streamError.value
  }

  return {
    // Chat scope 状态
    assistantMessages,
    assistantDraft,
    assistantDraftAttachments,
    isAssistantGenerating,
    assistantStreamError,
    assistantStreamingContent,
    assistantStreamingReasoning,
    assistantReasoningStreamPhaseActive,

    // Workspace scope 状态
    workspaceAssistantMessages,
    workspaceAssistantDraft,
    workspaceAssistantDraftAttachments,
    workspaceSessionId,
    isWorkspaceAssistantGenerating,
    workspaceAssistantStreamError,
    workspaceStreamingContent,
    workspaceStreamingReasoning,
    workspaceReasoningStreamPhaseActive,

    // 公共状态
    showAssistantSettings,
    isAssistantPanelOpen,
    assistantSettings,
    allowWriteMemoryEnabled,
    allowDestructiveToolsEnabled,
    setAllowWriteMemory,
    setAllowDestructiveTools,
    toggleAllowWriteMemory,
    toggleAllowDestructiveTools,

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
    ingestDraftFiles,
    removeDraftAttachment,
    clearDraftAttachments,
    cleanupWorkspaceSession,
    openEditMessage,
    closeEditMessage,
    saveEditedMessage,
    saveEditedMessageAndSend,
    deleteMessage,
    rewriteMessage,
    sendMessage,
    runAutoMemorySummaryPrompt,
    handleModelSelect,
  }
}

export type UseAssistant = ReturnType<typeof useAssistant>
