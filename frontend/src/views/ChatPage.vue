<script setup lang="ts">
/**
 * ChatPage - 聊天页面主组件
 *
 * 组件职责：
 * - 作为聊天页面的主容器，协调所有子组件和composables
 * - 管理页面级状态（选中的角色、草稿消息、生成状态等）
 * - 处理核心业务流程（消息发送、流式生成、群聊管理等）
 * - 处理用户身份和角色的选择与管理
 * - 处理聊天会话的创建、选择、删除等操作
 * - 集成聊天助手面板
 *
 * 主要功能：
 *    - 消息发送：处理用户消息发送，支持单聊和群聊
 *    - 流式生成：处理LLM流式响应，实现打字机效果
 *    - 群聊管理：处理群聊的创建、成员管理、插话等
 *    - 消息操作：处理消息编辑、删除、重写、版本切换
 *    - 角色管理：处理角色的创建、编辑、删除
 *    - 身份管理：处理用户身份的创建、编辑、删除、切换
 *    - 设置管理：打开设置抽屉，管理全局和聊天设置
 *
 * 主要函数：
 *    - sendUserMessage: 发送用户消息
 *    - runGroupGeneration: 运行群聊生成
 *    - continueGroupChat: 继续群聊
 *    - startNextRound: 开始下一轮群聊
 *    - triggerInterject: 触发插话
 *    - stopStreaming: 停止流式传输
 *    - handlePrimaryAction: 处理主要操作
 *    - handleRewriteMessage: 处理消息重写
 *    - handleSaveAndSend: 处理保存并发送
 *    - createChat: 创建聊天
 *    - selectChat: 选择聊天
 *    - deleteChat: 删除聊天
 *    - openCreateCharacter: 打开创建角色
 *    - openEditCharacter: 打开编辑角色
 *    - saveCharacter: 保存角色
 *    - deleteCharacter: 删除角色
 *    - handleCreateGroup: 处理群聊创建
 *    - handleUpdateMemberIds: 处理成员ID更新
 *    - handleUpdateGroupDelay: 处理群聊延迟更新
 *    - handleModelSelect: 处理模型选择
 *    - scrollToBottom: 滚动到底部
 *
 * 使用的Composables：
 *    - useStreamOutput: 来自composables/useStreamOutput.ts，处理流式输出
 *    - useMessageVersions: 来自composables/useMessageVersions.ts，管理消息版本
 *    - useGroupChat: 来自composables/useGroupChat.ts，处理群聊逻辑
 *    - useAssistant: 来自composables/useAssistant.ts，处理聊天助手
 *    - useChatActions: 来自composables/useChatActions.ts，处理聊天操作
 *
 * 使用的Stores：
 *    - useSettingsStore: 来自stores/settings.ts，管理设置
 *    - useCharactersStore: 来自stores/characters.ts，管理角色
 *    - useChatsStore: 来自stores/chats.ts，管理聊天会话
 *
 * 文件关系：
 *    - 被导入：被router/index.ts导入作为聊天页面路由组件
 *    - 导入：导入vue的computed、onMounted、ref、watch、nextTick、stores/index.ts的Store、types/models.ts的类型、composables/index.ts的composables、components下的所有组件、api/http.ts和api/sse.ts的API函数
 *    - 依赖：依赖vue、stores、composables、components、api
 *    - 位置：视图层，作为聊天页面的主组件
 */
import { computed, onMounted, ref, watch, nextTick } from 'vue'
import { useCharactersStore, useChatsStore, useSettingsStore } from '../stores'
import type { CharacterCard, ChatMessage, GroupMemberSettings, Chat } from '../types/models'

// Composables
import { 
  useStreamOutput, 
  useMessageVersions, 
  useGroupChat, 
  useAssistant,
  useChatActions,
} from '../composables'

// 子组件
import { ChatSidebar, MessageList, ChatInput, AssistantPanel } from '../components/chat'
import { GroupCreatorModal, MessageEditorModal, MemberSettingsModal, GroupSettingsModal } from '../components/modals'
import SettingsDrawer from '../components/SettingsDrawer.vue'
import AvatarCropper from '../components/AvatarCropper.vue'
import ModernAvatar from '../components/ModernAvatar.vue'
import ModernSelect from '../components/ModernSelect.vue'
import { Users, Settings, Sparkles, Loader2, X, MoreHorizontal } from 'lucide-vue-next'

// API
import { postAndConsumeSse } from '../api/sse'
import { apiPost, apiGet } from '../api/http'

// ========== Stores ==========
const settings = useSettingsStore()
const characters = useCharactersStore()
const chats = useChatsStore()

// ========== 页面级状态 ==========
const selectedCharacterId = ref<string | null>(null)
const draftMessage = ref('')
const showSettings = ref(false)
const showGroupSettings = ref(false)
const settingsTab = ref<'global' | 'presets' | 'chat'>('global')
const isGenerating = ref(false)
const streamError = ref<string | null>(null)
const sidebarCollapsed = ref(false)
const editingChatId = ref<string | null>(null)
const editingTitle = ref('')
const aborter = ref<AbortController | null>(null)
const stopRequested = ref(false)
const stopStreamingHold = ref(false)
/** 主聊天当前展示思考链的消息 ID（仅前端临时，刷新后消失） */
const chatReasoningMessageId = ref<string | null>(null)
/** 主聊天思考链内容（当前正在流式接收的一条） */
const chatReasoningContent = ref('')
/** 主聊天多轮思考链块：每项为 { messageId, content }，仅前端临时展示，不写进上下文 */
const chatReasoningBlocks = ref<Array<{ messageId: string; content: string }>>([])

/** 将当前思考内容写入 blocks 并清空当前（在 stream done 或非流响应后调用，便于多轮保留） */
function pushCurrentReasoningToBlocks(finalMessageId?: string | null) {
  const id = finalMessageId ?? chatReasoningMessageId.value
  const content = chatReasoningContent.value.trim()
  if (id && content) {
    chatReasoningBlocks.value = [...chatReasoningBlocks.value, { messageId: id, content }]
  }
  chatReasoningContent.value = ''
  chatReasoningMessageId.value = null
}

/** 根据消息 ID 获取当前关联的思考内容（流式当前条或 blocks 中已保存的） */
function getReasoningForMessageId(messageId: string): string {
  if (messageId === chatReasoningMessageId.value && chatReasoningContent.value) {
    return chatReasoningContent.value
  }
  const block = chatReasoningBlocks.value.find((b) => b.messageId === messageId)
  return block?.content?.trim() ?? ''
}

/**
 * 计算选中的角色
 *
 * 根据selectedCharacterId从角色列表中查找角色。
 */
const selectedCharacter = computed(() => {
  if (!selectedCharacterId.value) return null
  return characters.list.find((c) => c.id === selectedCharacterId.value) ?? null
})

/**
 * 计算当前激活的聊天
 *
 * 从chatsStore获取当前激活的聊天会话。
 */
const activeChat = computed(() => chats.activeChat)

/**
 * 计算助手聊天ID
 *
 * 获取当前激活聊天的ID，用于助手作用域。
 */
const assistantChatId = computed(() => activeChat.value?.id ?? null)

/**
 * 计算角色头像URL
 *
 * 根据选中角色的头像字段生成头像URL。
 */
const characterAvatarUrl = computed(() => {
  if (!selectedCharacter.value?.avatar) return null
  return `/api/avatars/${selectedCharacter.value.avatar}`
})

/**
 * 计算用户头像URL
 *
 * 根据选中身份的头像字段生成头像URL。
 */
const userAvatarUrl = computed(() => {
  if (!selectedPersona.value?.avatar) return null
  return `/api/avatars/${selectedPersona.value.avatar}`
})

/**
 * 计算用户名称
 *
 * 返回选中身份的名称，如果没有则返回"你"。
 */
const userName = computed(() => {
  return selectedPersona.value?.name || '你'
})

// ========== 初始化 Composables ==========
// 流式输出
const stream = useStreamOutput(
  { appendLocalMessageContent: chats.appendLocalMessageContent },
  scrollToBottom
)

// 消息版本
const versions = useMessageVersions()

// 群聊逻辑
const group = useGroupChat({
  activeChat,
  isGenerating,
  settings: settings as any,
})

/** 是否启用流式传输（与全局设置一致），供助手与生成共用 */
const isStreamEnabled = computed(() => settings.settings?.streamEnabled !== false)

// 聊天助手
const assistant = useAssistant({
  chatId: assistantChatId,
  streamEnabled: isStreamEnabled,
})

/**
 * 获取用户身份信息
 *
 * 根据身份ID从设置中的身份列表查找身份。
 *
 * @param {string | null | undefined} id - 身份ID
 * @returns {UserPersona | null} 身份信息，如果未找到或ID为空则返回null
 */
function getPersonaById(id: string | null | undefined) {
  if (!id || !settings.settings?.userPersonas) return null
  return settings.settings.userPersonas.find(p => p.id === id) ?? null
}

/**
 * 从聊天中获取最后一个用户消息的身份ID
 *
 * 遍历聊天消息，找到最后一个用户消息的身份ID（用于身份切换时保持历史消息显示）。
 *
 * @param {Chat | null | undefined} chat - 聊天会话（来自types/models.ts）
 * @returns {string | null} 身份ID，如果未找到则返回null
 */
function getLastUserPersonaIdFromChat(chat: Chat | null | undefined) {
  if (!chat?.messages?.length) return null
  for (let i = chat.messages.length - 1; i >= 0; i--) {
    const m = chat.messages[i]
    if (m?.role === 'user' && m.senderPersonaId) return m.senderPersonaId
  }
  return null
}

/**
 * 计算有效的选中身份ID
 *
 * 优先使用聊天会话的身份ID，其次使用聊天中最后一个用户消息的身份ID，
 * 再次使用全局设置中的选中身份ID。如果为纯AI模式则返回null。
 */
const effectiveSelectedPersonaId = computed(() => {
  if (group.effectivePureAiMode.value) return null
  const chat = activeChat.value
  return chat?.userPersonaId
    ?? getLastUserPersonaIdFromChat(chat)
    ?? settings.settings?.selectedPersonaId
    ?? null
})

/**
 * 计算选中的身份
 *
 * 根据effectiveSelectedPersonaId获取身份信息。
 */
const selectedPersona = computed(() => {
  return getPersonaById(effectiveSelectedPersonaId.value)
})

// 聊天操作
const actions = useChatActions({
  activeChat,
  isGenerating,
  selectedPersona,
  userName,
  chatsStore: chats as any,
  settingsStore: settings as any,
  charactersStore: characters as any,
})

/**
 * 处理成员ID更新
 *
 * 更新群聊的成员顺序。
 * 使用chatsStore.updateMemberOrder（来自stores/chats.ts）更新。
 *
 * @param {string[]} memberIds - 新的成员ID顺序列表
 * @returns {Promise<void>} 完成时返回
 */
async function handleUpdateMemberIds(memberIds: string[]) {
  if (activeChat.value) {
    await chats.updateMemberOrder(activeChat.value.id, memberIds)
  }
}

/**
 * 处理群聊延迟更新
 *
 * 更新群聊中角色发言之间的延迟时间。
 * 使用chatsStore.updateGroupDelay（来自stores/chats.ts）更新。
 *
 * @param {number} delay - 延迟时间（毫秒）
 * @returns {Promise<void>} 完成时返回
 */
async function handleUpdateGroupDelay(delay: number) {
  if (activeChat.value) {
    await chats.updateGroupDelay(activeChat.value.id, delay)
  }
}

interface ModelOption {
  label: string
  value: string
  presetId: string | null
}

interface ModelOptionGroup {
  label: string
  options: ModelOption[]
}

/**
 * 计算聊天模型选项
 *
 * 根据设置生成聊天模型选项列表，包括"最近使用"、各API预设的模型、全局配置的模型候选。
 * 按预设分组，每个选项包含label、value和presetId。
 */
const chatModelOptions = computed(() => {
  const options: ModelOptionGroup[] = []
  if (!settings.settings) return []

  const recentModels = settings.settings.llm.usedModels || []
  if (recentModels.length > 0) {
    options.push({
      label: '最近使用',
      options: recentModels.map(m => {
        let preset = null
        if (settings.settings?.apiPresets) {
          preset = settings.settings.apiPresets.find(p => p.models.includes(m))
        }
        return { label: m, value: m, presetId: preset ? preset.id : null }
      })
    })
  }

  if (settings.settings.apiPresets) {
    for (const preset of settings.settings.apiPresets) {
      if (preset.models && preset.models.length > 0) {
        options.push({
          label: preset.name,
          options: preset.models.map(m => ({ label: m, value: m, presetId: preset.id }))
        })
      }
    }
  }

  if ((!settings.settings.apiPresets || settings.settings.apiPresets.length === 0) && 
      settings.settings.llm.modelCandidates && settings.settings.llm.modelCandidates.length > 0) {
    options.push({
      label: '全局配置',
      options: settings.settings.llm.modelCandidates.map(m => ({ label: m, value: m, presetId: null }))
    })
  }

  return options
})

/**
 * 计算当前聊天模型
 *
 * 优先使用聊天覆盖设置中的模型，其次使用全局默认模型，都没有则返回"未设置"。
 */
const currentModel = computed(() => {
  return chats.activeChat?.overrides?.params?.model || settings.settings?.llm.defaultModel || '未设置'
})

/**
 * 计算助手当前模型
 *
 * 优先使用助手设置中的模型，其次使用全局默认模型，都没有则返回"未设置"。
 */
const assistantCurrentModel = computed(() => {
  return assistant.assistantSettings.value.model || settings.settings?.llm.defaultModel || '未设置'
})

/**
 * 处理模型选择
 *
 * 更新聊天会话的模型设置。
 * 如果选项包含presetId，则使用该presetId；否则从API预设中查找匹配的预设。
 * 使用chatsStore.updateOverrides（来自stores/chats.ts）更新设置。
 *
 * @param {any} option - 模型选项，包含value和可选的presetId
 * @returns {Promise<void>} 完成时返回
 */
async function handleModelSelect(option: any) {
  if (!chats.activeChat) return
  const overrides = { ...chats.activeChat.overrides }
  overrides.params = { ...overrides.params, model: option.value }
  
  if (option.presetId) {
    overrides.presetId = option.presetId
  } else {
    const found = settings.settings?.apiPresets.find(p => p.models.includes(option.value))
    if (found) overrides.presetId = found.id
    else overrides.presetId = null
  }
  
  await chats.updateOverrides(chats.activeChat.id, overrides)
}

/**
 * 滚动到底部
 *
 * 滚动消息列表到底部，用于显示最新消息。
 * 使用nextTick确保DOM更新后再滚动。
 */
const messageListRef = ref<InstanceType<typeof MessageList> | null>(null)

function scrollToBottom() {
  nextTick(() => {
    messageListRef.value?.scrollToBottom()
  })
}

/**
 * 计算群聊成员列表
 *
 * 如果是群聊，则根据memberIds从角色列表中查找对应的角色卡片。
 */
const groupMembers = computed(() => {
  if (!activeChat.value?.isGroup) return []
  return activeChat.value.memberIds
    .map(id => characters.list.find(c => c.id === id))
    .filter((c): c is CharacterCard => c !== null)
})

/**
 * 计算是否正在流式传输
 *
 * 检查是否启用流式传输且（正在生成或正在插话）。
 */
const isStreamingActive = computed(() => isStreamEnabled.value && (isGenerating.value || group.isInterjecting.value))

/**
 * 计算是否有草稿消息
 *
 * 检查输入框是否有非空内容。
 */
const hasDraftMessage = computed(() => !!draftMessage.value.trim())

/**
 * 检查是否为AbortError
 *
 * 判断错误是否为AbortError（请求被取消）。
 *
 * @param {any} e - 错误对象
 * @returns {boolean} 是否为AbortError
 */
function isAbortError(e: any) {
  return e?.name === 'AbortError'
}

/**
 * 组件挂载时的初始化
 *
 * 加载设置、角色列表和群聊列表。
 * 如果没有选中角色，则自动选中第一个角色。
 */
onMounted(async () => {
  if (!settings.settings) await settings.load()
  await characters.loadAll()
  await chats.loadGroupList()

  if (!selectedCharacterId.value) {
    const first = characters.list[0]
    if (first) selectedCharacterId.value = first.id
  }
})

/**
 * 监听助手面板打开状态
 *
 * 当助手面板打开时，加载聊天作用域的助手状态。
 */
watch(assistant.isAssistantPanelOpen, (next) => {
  if (next) void assistant.loadState('chat')
})

/**
 * 监听选中角色ID变化
 *
 * 当选中角色变化时，加载该角色的聊天列表，并自动选择第一个聊天。
 * 使用immediate选项，在组件挂载时立即执行一次。
 */
watch(
  () => selectedCharacterId.value,
  async (cid) => {
    if (!cid) return
    await chats.loadList(cid)
    const first = chats.list[0]
    if (first) {
      await chats.load(first.id)
      scrollToBottom()
    } else {
      chats.activeChatId = null
      chats.activeChat = null
    }
  },
  { immediate: true },
)

/**
 * 监听助手聊天ID变化
 *
 * 当助手聊天ID变化且助手面板打开时，重新加载聊天作用域的助手状态。
 */
watch(
  () => assistantChatId.value,
  (next, prev) => {
    if (next && next !== prev && assistant.isAssistantPanelOpen.value) {
      void assistant.loadState('chat')
    }
  },
)

/** 切换聊天时清空主聊天的思考链（仅前端临时，不持久化） */
watch(
  () => activeChat.value?.id,
  (next, prev) => {
    if (prev != null && next !== prev) {
      chatReasoningBlocks.value = []
      chatReasoningContent.value = ''
      chatReasoningMessageId.value = null
    }
  },
)

/**
 * 监听角色编辑弹窗状态
 *
 * 当角色编辑弹窗关闭时，删除工作区助手聊天，如果助手面板打开则加载聊天作用域状态。
 */
watch(actions.showCharacterEditor, (next, prev) => {
  if (!next && prev && actions.editingCharacter.value) {
    void assistant.deleteWorkspaceChat()
    if (assistant.isAssistantPanelOpen.value) void assistant.loadState('chat')
    actions.editingCharacter.value = null
    actions.isNewCharacter.value = false
  }
})

/**
 * 根据当前聊天窗口动态更新页面标题
 *
 * 无激活聊天时显示 SimpleTavern；
 * 单聊窗口显示 SimpleTavern-角色名；
 * 群聊窗口显示 SimpleTavern-群聊名。
 */
watch(
  () => {
    const chat = activeChat.value
    if (!chat) return 'SimpleTavern'
    if (chat.isGroup) return `SimpleTavern-${chat.title}`
    const char = characters.list.find((c) => c.id === chat.characterId)
    return char ? `SimpleTavern-${char.name}` : `SimpleTavern-${chat.title}`
  },
  (title) => {
    document.title = title
  },
  { immediate: true },
)

/**
 * 运行群聊生成
 *
 * 依次让群聊中的每个成员发言，支持流式和非流式两种模式。
 * 每个成员发言前会延迟指定时间（groupDelay）。
 * 支持暂停和继续功能。
 * 使用postAndConsumeSse函数（来自api/sse.ts）或apiPost函数（来自api/http.ts）发送请求。
 *
 * @param {string} chatId - 聊天ID
 * @param {string[]} memberIds - 要发言的成员ID列表
 * @param {boolean} useStream - 是否使用流式传输
 * @param {number} groupDelay - 成员发言之间的延迟时间（毫秒）
 * @param {number} startIndex - 开始索引（用于继续暂停的群聊）
 * @returns {Promise<void>} 完成时返回
 */
async function runGroupGeneration(
  chatId: string, 
  memberIds: string[], 
  useStream: boolean, 
  groupDelay: number,
  startIndex: number
) {
  for (let i = startIndex; i < memberIds.length; i++) {
    const characterId = memberIds[i]
    if (!characterId) continue
    
    const actualIndex = activeChat.value?.memberIds ? activeChat.value.memberIds.indexOf(characterId) : -1
    group.currentSpeakerIndex.value = actualIndex
    
    if (i > startIndex) {
      await group.delay(groupDelay)
    }
    
    if (group.isPaused.value) {
      group.setPausedState(memberIds.slice(i))
      return
    }
    
    if (!activeChat.value) break
    
    const localAssistantId = `local_assistant_${Date.now()}_${i}`
    chatReasoningMessageId.value = localAssistantId
    chatReasoningContent.value = ''
    const localMsg = { 
      version: 1, 
      id: localAssistantId, 
      role: 'assistant' as const, 
      content: '', 
      characterId,
      ts: new Date().toISOString() 
    }
    chats.addLocalMessage(localMsg)
    scrollToBottom()
    
    if (useStream) {
      stream.registerStreamMessage(localAssistantId)
      try {
        await postAndConsumeSse(
          '/api/generate/group',
          { chatId, characterId },
          (evt) => {
            if (stopRequested.value) return
            if (evt.event === 'delta') {
              const data = evt.data as { text?: string } | undefined
              const t = data?.text
              if (typeof t === 'string') {
                stream.appendDeltaBuffered(localAssistantId, t)
              }
            } else if (evt.event === 'reasoning') {
              const data = evt.data as { text?: string } | undefined
              const t = data?.text
              if (typeof t === 'string') {
                chatReasoningContent.value += t
              }
            } else if (evt.event === 'done') {
              const data = evt.data as { assistantMessageId?: string } | undefined
              const serverId = data?.assistantMessageId
              if (serverId && chatReasoningContent.value) {
                chatReasoningMessageId.value = serverId
              }
              pushCurrentReasoningToBlocks(serverId ?? undefined)
            } else if (evt.event === 'error') {
              const data = evt.data as { message?: string } | undefined
              streamError.value = String(data?.message ?? 'unknown error')
            }
          },
          aborter.value?.signal,
        )
      } finally {
        stream.flushForMessage(localAssistantId)
        stopRequested.value = false
      }
    } else {
      const res = await apiPost<{
        ok: boolean
        chatId: string
        assistantMessageId: string | null
        characterId: string
        content: string
        reasoningContent?: string
        error?: string
      }>('/api/generate/group', { chatId, characterId })
      
      if (res.ok) {
        if (typeof res.reasoningContent === 'string') {
          chatReasoningContent.value = res.reasoningContent
        }
        pushCurrentReasoningToBlocks(res.assistantMessageId ?? undefined)
        chats.appendLocalMessageContent(localAssistantId, res.content || '')
        scrollToBottom()
      } else {
        streamError.value = res.error || 'unknown error'
      }
    }
    
    if (group.isPaused.value && i < memberIds.length - 1) {
      group.setPausedState(memberIds.slice(i + 1))
      return
    }
  }
  
  group.pendingMembers.value = []
  group.showContinueButton.value = false
}

/**
 * 发送用户消息
 *
 * 发送用户消息并触发AI回复生成。
 * 支持单聊和群聊两种模式。
 * 支持流式和非流式两种生成方式。
 * 在发送前会清理消息版本历史。
 * 使用postAndConsumeSse函数（来自api/sse.ts）或apiPost函数（来自api/http.ts）发送请求。
 *
 * @returns {Promise<void>} 完成时返回
 */
async function sendUserMessage() {
  const text = draftMessage.value.trim()
  if (!text) return
  if (!activeChat.value) return
  if (isGenerating.value) return
  draftMessage.value = ''
  streamError.value = null
  
  const chatId = activeChat.value.id
  const isGroup = activeChat.value.isGroup
  const now = new Date().toISOString()
  const userRole = group.effectivePureAiMode.value ? ('system' as const) : ('user' as const)

  // 处理暂停状态下的插话
  if (isGroup && group.showContinueButton.value) {
    const localUserId = `local_user_${Date.now()}`
    chats.addLocalMessage({
      version: 1,
      id: localUserId,
      role: userRole,
      content: text,
      senderPersonaId: userRole === 'user' ? (selectedPersona.value?.id ?? null) : null,
      senderName: userRole === 'user' ? (selectedPersona.value?.name ?? userName.value) : null,
      senderAvatar: userRole === 'user' ? (selectedPersona.value?.avatar ?? null) : null,
      ts: now,
    })
    scrollToBottom()
    
    try {
      await apiPost(`/api/chats/${chatId}/messages`, {
        role: userRole,
        content: text,
        senderPersonaId: userRole === 'user' ? (selectedPersona.value?.id ?? null) : null,
        senderName: userRole === 'user' ? (selectedPersona.value?.name ?? userName.value) : null,
        senderAvatar: userRole === 'user' ? (selectedPersona.value?.avatar ?? null) : null,
      })
      await chats.load(chatId)
    } catch (e: any) {
      streamError.value = e?.message ?? String(e)
    }
    return
  }

  // 清理版本历史
  if (activeChat.value) {
    for (const msg of activeChat.value.messages) {
      if (msg.role === 'assistant' && versions.hasMultipleVersions(msg)) {
        const content = versions.cleanupVersions(msg)
        await chats.updateMessage(activeChat.value.id, msg.id, msg.role, content, msg.characterId)
      }
    }
  }
  
  group.resetGroupState()
  group.showInterjectPanel.value = group.effectivePureAiMode.value

  isGenerating.value = true
  aborter.value?.abort()
  aborter.value = new AbortController()

  const useStream = settings.settings?.streamEnabled !== false

  try {
    if (isGroup) {
      const allMemberIds = [...activeChat.value.memberIds]
      const groupDelay = activeChat.value.groupDelay || 1500
      
      const memberIds = group.filterMembersByProbability(allMemberIds)
      
      const localUserId = `local_user_${Date.now()}`
      chats.addLocalMessage({
        version: 1,
        id: localUserId,
        role: userRole,
        content: text,
        senderPersonaId: userRole === 'user' ? (selectedPersona.value?.id ?? null) : null,
        senderName: userRole === 'user' ? (selectedPersona.value?.name ?? userName.value) : null,
        senderAvatar: userRole === 'user' ? (selectedPersona.value?.avatar ?? null) : null,
        ts: now,
      })
      scrollToBottom()
      
      await apiPost(`/api/chats/${chatId}/messages`, {
        role: userRole,
        content: text,
        senderPersonaId: userRole === 'user' ? (selectedPersona.value?.id ?? null) : null,
        senderName: userRole === 'user' ? (selectedPersona.value?.name ?? userName.value) : null,
        senderAvatar: userRole === 'user' ? (selectedPersona.value?.avatar ?? null) : null,
      })
      
      await runGroupGeneration(chatId, memberIds, useStream, groupDelay, 0)
      
      if (group.isPaused.value) return
      
      group.currentSpeakerIndex.value = -1
      group.showInterject()
      
    } else {
      const localUserId = `local_user_${Date.now()}`
      const localAssistantId = `local_assistant_${Date.now()}`

      chatReasoningMessageId.value = localAssistantId
      chatReasoningContent.value = ''

      chats.addLocalMessage({
        version: 1,
        id: localUserId,
        role: userRole,
        content: text,
        senderPersonaId: userRole === 'user' ? (selectedPersona.value?.id ?? null) : null,
        senderName: userRole === 'user' ? (selectedPersona.value?.name ?? userName.value) : null,
        senderAvatar: userRole === 'user' ? (selectedPersona.value?.avatar ?? null) : null,
        ts: now,
      })
      chats.addLocalMessage({ version: 1, id: localAssistantId, role: 'assistant', content: '', ts: now })
      scrollToBottom()

      if (useStream) {
        stream.registerStreamMessage(localAssistantId)
        try {
          await postAndConsumeSse(
            '/api/generate/stream',
            {
              chatId,
              userMessage: text,
              senderPersonaId: selectedPersona.value?.id ?? null,
              senderName: selectedPersona.value?.name ?? userName.value,
              senderAvatar: selectedPersona.value?.avatar ?? null,
              userPersona: selectedPersona.value ?? null,
            },
            (evt) => {
              if (stopRequested.value) return
              if (evt.event === 'delta') {
                const data = evt.data as { text?: string } | undefined
                const t = data?.text
                if (typeof t === 'string') {
                  stream.appendDeltaBuffered(localAssistantId, t)
                }
              } else if (evt.event === 'reasoning') {
                const data = evt.data as { text?: string } | undefined
                const t = data?.text
                if (typeof t === 'string') {
                  chatReasoningContent.value += t
                }
              } else if (evt.event === 'done') {
                const data = evt.data as { assistantMessageId?: string } | undefined
                const serverId = data?.assistantMessageId
                if (serverId && chatReasoningContent.value) {
                  chatReasoningMessageId.value = serverId
                }
                pushCurrentReasoningToBlocks(serverId ?? undefined)
              } else if (evt.event === 'error') {
                const data = evt.data as { message?: string } | undefined
                streamError.value = String(data?.message ?? 'unknown error')
              }
            },
            aborter.value?.signal,
          )
        } finally {
          stream.flushForMessage(localAssistantId)
          stopRequested.value = false
        }
      } else {
        const res = await apiPost<{
          ok: boolean
          chatId: string
          assistantMessageId: string | null
          content: string
          reasoningContent?: string
          error?: string
        }>('/api/generate/stream', {
          chatId,
          userMessage: text,
          senderPersonaId: selectedPersona.value?.id ?? null,
          senderName: selectedPersona.value?.name ?? userName.value,
          senderAvatar: selectedPersona.value?.avatar ?? null,
          userPersona: selectedPersona.value ?? null,
        })
        
        if (res.ok) {
          if (typeof res.reasoningContent === 'string') {
            chatReasoningContent.value = res.reasoningContent
          }
          pushCurrentReasoningToBlocks(res.assistantMessageId ?? undefined)
          chats.appendLocalMessageContent(localAssistantId, res.content || '')
          scrollToBottom()
        } else {
          streamError.value = res.error || 'unknown error'
        }
      }
    }
  } catch (e: any) {
    if (!isAbortError(e)) {
      streamError.value = e?.message ?? String(e)
    }
  } finally {
    isGenerating.value = false
    group.currentSpeakerIndex.value = -1
    if (stopStreamingHold.value) {
      await persistLocalStreamingMessages(chatId)
      stopStreamingHold.value = false
    } else {
      await chats.load(chatId)
    }
    await settings.load()
  }
}

/**
 * 继续群聊
 *
 * 继续之前暂停的群聊，让剩余成员继续发言。
 * 使用runGroupGeneration函数继续生成。
 *
 * @returns {Promise<void>} 完成时返回
 */
async function continueGroupChat() {
  if (!activeChat.value || group.pendingMembers.value.length === 0) return
  
  group.showContinueButton.value = false
  group.isPaused.value = false
  isGenerating.value = true
  
  const chatId = activeChat.value.id
  const useStream = settings.settings?.streamEnabled !== false
  const groupDelay = activeChat.value.groupDelay || 1500
  
  try {
    await runGroupGeneration(chatId, group.pendingMembers.value, useStream, groupDelay, 0)
    
    if (group.isPaused.value) return
    
    group.currentSpeakerIndex.value = -1
    group.showInterject()
  } catch (e: any) {
    if (!isAbortError(e)) {
      streamError.value = e?.message ?? String(e)
    }
  } finally {
    const skippedReload = stopStreamingHold.value
    if (skippedReload) {
      await persistLocalStreamingMessages(chatId)
      stopStreamingHold.value = false
    }
    if (!group.isPaused.value) {
      isGenerating.value = false
      group.currentSpeakerIndex.value = -1
      group.pendingMembers.value = []
      if (!skippedReload) {
        await chats.load(chatId)
        await settings.load()
      } else {
        await settings.load()
      }
    }
  }
}

/**
 * 开始下一轮群聊
 *
 * 在群聊中开始新的一轮对话，让所有成员依次发言。
 * 根据成员的概率设置筛选参与本轮对话的成员。
 * 使用runGroupGeneration函数生成回复。
 *
 * @returns {Promise<void>} 完成时返回
 */
async function startNextRound() {
  if (!activeChat.value) return
  if (!activeChat.value.isGroup) return
  if (isGenerating.value) return

  streamError.value = null
  group.showInterjectPanel.value = false
  group.resetGroupState()

  const chatId = activeChat.value.id
  const useStream = settings.settings?.streamEnabled !== false
  const groupDelay = activeChat.value.groupDelay || 1500

  isGenerating.value = true
  aborter.value?.abort()
  aborter.value = new AbortController()

  try {
    const allMemberIds = [...activeChat.value.memberIds]
    const memberIds = group.filterMembersByProbability(allMemberIds)

    await runGroupGeneration(chatId, memberIds, useStream, groupDelay, 0)
    if (group.isPaused.value) return

    group.showInterject()
  } catch (e: any) {
    streamError.value = e?.message ?? String(e)
  } finally {
    isGenerating.value = false
    group.currentSpeakerIndex.value = -1
    const skippedReload = stopStreamingHold.value
    if (skippedReload) {
      await persistLocalStreamingMessages(chatId)
      stopStreamingHold.value = false
    }
    if (!group.isPaused.value) {
      if (!skippedReload) {
        await chats.load(chatId)
      }
      await settings.load()
    }
  }
}

/**
 * 触发插话
 *
 * 在群聊中触发指定角色的插话（在非轮次时间发言）。
 * 支持流式和非流式两种模式。
 * 使用postAndConsumeSse函数（来自api/sse.ts）或apiPost函数（来自api/http.ts）发送请求到/api/generate/interject。
 *
 * @param {string} characterId - 要插话的角色ID
 * @returns {Promise<void>} 完成时返回
 */
async function triggerInterject(characterId: string) {
  if (!activeChat.value || isGenerating.value || group.isInterjecting.value) return
  
  const chatId = activeChat.value.id
  group.isInterjecting.value = true
  streamError.value = null
  aborter.value?.abort()
  aborter.value = new AbortController()
  
  const useStream = settings.settings?.streamEnabled !== false
  
  const localAssistantId = `local_interject_${Date.now()}`
  chatReasoningMessageId.value = localAssistantId
  chatReasoningContent.value = ''
  const localMsg = { 
    version: 1, 
    id: localAssistantId, 
    role: 'assistant' as const, 
    content: '', 
    characterId,
    ts: new Date().toISOString() 
  }
  chats.addLocalMessage(localMsg)
  scrollToBottom()
  
  try {
    if (useStream) {
      stream.registerStreamMessage(localAssistantId)
      try {
        await postAndConsumeSse(
          '/api/generate/interject',
          { chatId, characterId },
          (evt) => {
            if (stopRequested.value) return
            if (evt.event === 'delta') {
              const data = evt.data as { text?: string } | undefined
              const t = data?.text
              if (typeof t === 'string') {
                stream.appendDeltaBuffered(localAssistantId, t)
              }
            } else if (evt.event === 'reasoning') {
              const data = evt.data as { text?: string } | undefined
              const t = data?.text
              if (typeof t === 'string') {
                chatReasoningContent.value += t
              }
            } else if (evt.event === 'done') {
              const data = evt.data as { assistantMessageId?: string } | undefined
              const serverId = data?.assistantMessageId
              if (serverId && chatReasoningContent.value) {
                chatReasoningMessageId.value = serverId
              }
              pushCurrentReasoningToBlocks(serverId ?? undefined)
            } else if (evt.event === 'error') {
              const data = evt.data as { message?: string } | undefined
              streamError.value = String(data?.message ?? 'unknown error')
            }
          },
          aborter.value?.signal,
        )
      } finally {
        stream.flushForMessage(localAssistantId)
        stopRequested.value = false
      }
    } else {
      const res = await apiPost<{
        ok: boolean
        chatId: string
        assistantMessageId: string | null
        characterId: string
        content: string
        reasoningContent?: string
        error?: string
      }>('/api/generate/interject', { chatId, characterId })
      
      if (res.ok) {
        if (typeof res.reasoningContent === 'string') {
          chatReasoningContent.value = res.reasoningContent
        }
        pushCurrentReasoningToBlocks(res.assistantMessageId ?? undefined)
        chats.appendLocalMessageContent(localAssistantId, res.content || '')
        scrollToBottom()
      } else {
        streamError.value = res.error || 'unknown error'
      }
    }
  } catch (e: any) {
    if (!isAbortError(e)) {
      streamError.value = e?.message ?? String(e)
    }
  } finally {
    group.isInterjecting.value = false
    if (stopStreamingHold.value) {
      await persistLocalStreamingMessages(chatId)
      stopStreamingHold.value = false
    } else {
      await chats.load(chatId)
    }
  }
}

/**
 * 停止流式传输
 *
 * 停止当前正在进行的流式生成。
 * 取消请求，刷新所有流式缓冲，但不重新加载聊天数据。
 */
function stopStreaming() {
  if (!aborter.value) return
  stopRequested.value = true
  stopStreamingHold.value = true
  aborter.value.abort()
  stream.flushAll()
}

/**
 * 将当前会话中未持久化的本地流式消息（被截断的内容）保存到后端并重新加载
 * 用于用户点击终止后：打字机缓冲已通过 flushAll 写入本地消息，此处持久化并同步为可编辑的服务器消息
 */
async function persistLocalStreamingMessages(chatId: string) {
  const chat = activeChat.value
  if (!chat?.messages?.length) return
  const localAssistantMessages = chat.messages.filter(
    (m) => m.role === 'assistant' && m.id.startsWith('local_')
  )
  for (const m of localAssistantMessages) {
    const content = (m.content || '').trim()
    if (content) {
      await chats.appendMessage(chatId, 'assistant', content, {
        characterId: m.characterId ?? undefined,
      })
    }
  }
  await chats.load(chatId)
}

/**
 * 处理主要操作
 *
 * 根据当前状态执行相应的主要操作：
 * - 如果正在流式传输，则停止
 * - 如果显示继续按钮且有草稿，则发送消息
 * - 如果显示继续按钮且无草稿，则继续群聊
 * - 如果是群聊且无草稿，则开始下一轮
 * - 否则发送消息
 */
function handlePrimaryAction() {
  if (isStreamingActive.value) {
    stopStreaming()
    return
  }
  if (group.showContinueButton.value && activeChat.value?.isGroup) {
    if (hasDraftMessage.value) {
      sendUserMessage()
    } else {
      continueGroupChat()
    }
    return
  }
  if (activeChat.value?.isGroup && !hasDraftMessage.value) {
    startNextRound()
    return
  }
  sendUserMessage()
}

/**
 * 切换到上一个版本
 *
 * 使用versions.switchToPreviousVersion（来自composables/useMessageVersions.ts）切换到消息的上一个版本。
 *
 * @param {ChatMessage} m - 消息对象（来自types/models.ts）
 */
function handleSwitchPreviousVersion(m: ChatMessage) {
  const newContent = versions.switchToPreviousVersion(m)
  if (newContent !== null && activeChat.value) {
    const msg = activeChat.value.messages.find(msg => msg.id === m.id)
    if (msg) msg.content = newContent
  }
}

/**
 * 切换到下一个版本
 *
 * 使用versions.switchToNextVersion（来自composables/useMessageVersions.ts）切换到消息的下一个版本。
 *
 * @param {ChatMessage} m - 消息对象（来自types/models.ts）
 */
function handleSwitchNextVersion(m: ChatMessage) {
  const newContent = versions.switchToNextVersion(m)
  if (newContent !== null && activeChat.value) {
    const msg = activeChat.value.messages.find(msg => msg.id === m.id)
    if (msg) msg.content = newContent
  }
}

/**
 * 处理消息重写
 *
 * 重写指定的助手消息，保存当前版本，删除该消息及之后的所有消息，然后重新生成。
 * 支持单聊和群聊两种模式，支持流式和非流式两种生成方式。
 * 使用versions.saveVersion和addNewVersion（来自composables/useMessageVersions.ts）管理版本。
 * 使用postAndConsumeSse函数（来自api/sse.ts）或apiPost函数（来自api/http.ts）发送请求。
 *
 * @param {ChatMessage} m - 要重写的消息（来自types/models.ts）
 * @returns {Promise<void>} 完成时返回
 */
async function handleRewriteMessage(m: ChatMessage) {
  if (!activeChat.value) return
  if (isGenerating.value) return
  if (m.id.startsWith('local_')) return
  if (m.role !== 'assistant') return

  const chatId = activeChat.value.id
  const messageIndex = activeChat.value.messages.findIndex(msg => msg.id === m.id)
  if (messageIndex === -1) return

  let lastUserMessage: ChatMessage | null = null
  for (let i = messageIndex - 1; i >= 0; i--) {
    const msg = activeChat.value.messages[i]
    if (msg && (msg.role === 'user' || msg.role === 'system')) {
      lastUserMessage = msg
      break
    }
  }
  if (!lastUserMessage) return

  const originalMessageId = versions.getOriginalMessageId(m.id)
  const displayContent = versions.getDisplayContent(m)
  const currentReasoning = getReasoningForMessageId(m.id)
  versions.saveVersion(originalMessageId, displayContent, currentReasoning)

  const messagesToDelete = activeChat.value.messages.slice(messageIndex)
  for (const msgToDelete of messagesToDelete) {
    if (!msgToDelete.id.startsWith('local_')) {
      await chats.deleteMessage(chatId, msgToDelete.id)
    }
  }

  await chats.load(chatId)

  isGenerating.value = true
  streamError.value = null
  aborter.value?.abort()
  aborter.value = new AbortController()

  const useStream = settings.settings?.streamEnabled !== false
  const isGroup = activeChat.value.isGroup
  const characterId = m.characterId || activeChat.value.characterId || ''

  try {
    const localAssistantId = `local_rewrite_${Date.now()}`
    chatReasoningMessageId.value = localAssistantId
    chatReasoningContent.value = ''
    const localMsg = {
      version: 1,
      id: localAssistantId,
      role: 'assistant' as const,
      content: '',
      characterId,
      ts: new Date().toISOString()
    }
    chats.addLocalMessage(localMsg)
    scrollToBottom()

    if (isGroup) {
      if (useStream) {
        stream.registerStreamMessage(localAssistantId)
        try {
          await postAndConsumeSse(
            '/api/generate/group',
            { chatId, characterId },
            (evt) => {
              if (stopRequested.value) return
              if (evt.event === 'delta') {
                const data = evt.data as { text?: string } | undefined
                const t = data?.text
                if (typeof t === 'string') {
                  stream.appendDeltaBuffered(localAssistantId, t)
                }
              } else if (evt.event === 'reasoning') {
                const data = evt.data as { text?: string } | undefined
                const t = data?.text
                if (typeof t === 'string') {
                  chatReasoningContent.value += t
                }
              } else if (evt.event === 'done') {
                const data = evt.data as { assistantMessageId?: string } | undefined
                const serverId = data?.assistantMessageId
                if (serverId && chatReasoningContent.value) {
                  chatReasoningMessageId.value = serverId
                }
                pushCurrentReasoningToBlocks(serverId ?? undefined)
              } else if (evt.event === 'error') {
                const data = evt.data as { message?: string } | undefined
                streamError.value = String(data?.message ?? 'unknown error')
              }
            },
            aborter.value?.signal,
          )
        } finally {
          stream.flushForMessage(localAssistantId)
          stopRequested.value = false
        }
      } else {
        const res = await apiPost<{
          ok: boolean
          content: string
          assistantMessageId?: string | null
          reasoningContent?: string
          error?: string
        }>('/api/generate/group', { chatId, characterId })
        
        if (res.ok) {
          if (typeof res.reasoningContent === 'string') {
            chatReasoningContent.value = res.reasoningContent
          }
          pushCurrentReasoningToBlocks(res.assistantMessageId ?? undefined)
          chats.appendLocalMessageContent(localAssistantId, res.content || '')
          scrollToBottom()
        } else {
          streamError.value = res.error || 'unknown error'
        }
      }
    } else {
      if (useStream) {
        stream.registerStreamMessage(localAssistantId)
        try {
          await postAndConsumeSse(
            '/api/generate/stream',
            {
              chatId,
              userMessage: lastUserMessage.content,
              appendUserMessage: false,
              senderPersonaId: lastUserMessage.senderPersonaId ?? selectedPersona.value?.id ?? null,
              senderName: lastUserMessage.senderName ?? selectedPersona.value?.name ?? userName.value,
              senderAvatar: lastUserMessage.senderAvatar ?? selectedPersona.value?.avatar ?? null,
              userPersona: selectedPersona.value ?? null,
            },
            (evt) => {
              if (stopRequested.value) return
              if (evt.event === 'delta') {
                const data = evt.data as { text?: string } | undefined
                const t = data?.text
                if (typeof t === 'string') {
                  stream.appendDeltaBuffered(localAssistantId, t)
                }
              } else if (evt.event === 'reasoning') {
                const data = evt.data as { text?: string } | undefined
                const t = data?.text
                if (typeof t === 'string') {
                  chatReasoningContent.value += t
                }
              } else if (evt.event === 'done') {
                const data = evt.data as { assistantMessageId?: string } | undefined
                const serverId = data?.assistantMessageId
                if (serverId && chatReasoningContent.value) {
                  chatReasoningMessageId.value = serverId
                }
                pushCurrentReasoningToBlocks(serverId ?? undefined)
              } else if (evt.event === 'error') {
                const data = evt.data as { message?: string } | undefined
                streamError.value = String(data?.message ?? 'unknown error')
              }
            },
            aborter.value?.signal,
          )
        } finally {
          stream.flushForMessage(localAssistantId)
          stopRequested.value = false
        }
      } else {
        const res = await apiPost<{
          ok: boolean
          content: string
          assistantMessageId?: string | null
          reasoningContent?: string
          error?: string
        }>('/api/generate/stream', {
          chatId,
          userMessage: lastUserMessage.content,
          appendUserMessage: false,
          userPersona: selectedPersona.value ?? null,
        })
        
        if (res.ok) {
          if (typeof res.reasoningContent === 'string') {
            chatReasoningContent.value = res.reasoningContent
          }
          pushCurrentReasoningToBlocks(res.assistantMessageId ?? undefined)
          chats.appendLocalMessageContent(localAssistantId, res.content || '')
          scrollToBottom()
        } else {
          streamError.value = res.error || 'unknown error'
        }
      }
    }
  } catch (e: any) {
    if (!isAbortError(e)) {
      streamError.value = e?.message ?? String(e)
    }
  } finally {
    isGenerating.value = false
    const skippedReload = stopStreamingHold.value
    if (skippedReload) {
      await persistLocalStreamingMessages(chatId)
      stopStreamingHold.value = false
    } else {
      await chats.load(chatId)
    }
    await settings.load()
    
    // 添加新版本（使用原始消息ID以累积同一链条上的多版本），并绑定该版本的思考内容
    if (!skippedReload && activeChat.value) {
      const newMsg = activeChat.value.messages.find(msg => 
        msg.role === 'assistant' && msg.ts > m.ts
      )
      if (newMsg) {
        const newReasoning = getReasoningForMessageId(newMsg.id)
        versions.addNewVersion(originalMessageId, newMsg.id, newMsg.content, newReasoning)
      }
    }
  }
}

/**
 * 开始编辑标题
 *
 * 设置正在编辑的聊天ID和标题，用于内联编辑。
 *
 * @param {string} chatId - 聊天ID
 * @param {string} currentTitle - 当前标题
 */
function startEditTitle(chatId: string, currentTitle: string) {
  editingChatId.value = chatId
  editingTitle.value = currentTitle
}

/**
 * 保存标题
 *
 * 保存编辑后的聊天标题。
 * 使用chatsStore.rename（来自stores/chats.ts）更新标题。
 *
 * @returns {Promise<void>} 完成时返回
 */
async function saveTitle() {
  if (!editingChatId.value || !editingTitle.value.trim()) return
  await chats.rename(editingChatId.value, editingTitle.value.trim())
  editingChatId.value = null
  editingTitle.value = ''
}

/**
 * 取消编辑标题
 *
 * 取消标题编辑，清空编辑状态。
 */
function cancelEditTitle() {
  editingChatId.value = null
  editingTitle.value = ''
}

/**
 * 创建聊天
 *
 * 为当前选中的角色创建新的聊天会话。
 * 使用chatsStore.create（来自stores/chats.ts）创建聊天。
 *
 * @returns {Promise<void>} 完成时返回
 */
async function createChat() {
  if (!selectedCharacterId.value) return
  await chats.create(selectedCharacterId.value)
  scrollToBottom()
}

/**
 * 删除聊天
 *
 * 删除指定的聊天会话。
 * 使用chatsStore.remove（来自stores/chats.ts）删除聊天。
 *
 * @param {string} chatId - 聊天ID
 * @returns {Promise<void>} 完成时返回
 */
async function deleteChat(chatId: string) {
  await chats.remove(chatId)
}

/**
 * 选择聊天
 *
 * 加载并选择指定的聊天会话。
 * 使用chatsStore.load（来自stores/chats.ts）加载聊天数据。
 *
 * @param {Chat} chat - 聊天会话（来自types/models.ts）
 * @returns {Promise<void>} 完成时返回
 */
async function selectChat(chat: Chat) {
  await chats.load(chat.id)
  scrollToBottom()
}

/**
 * 处理群聊创建
 *
 * 根据GroupCreatorModal传递的数据创建群聊。
 * 为每个成员创建默认设置，包括是否包含性格和场景描述。
 * 使用chatsStore.createGroup（来自stores/chats.ts）创建群聊。
 *
 * @param {object} data - 群聊创建数据
 * @param {string} data.title - 群聊标题
 * @param {string[]} data.memberIds - 成员ID列表
 * @param {boolean} data.pureAiMode - 是否纯AI模式
 * @param {string | null} data.firstMessageCharacterId - 首句发言角色ID
 * @param {Record<string, { includePersonality: boolean; includeScenario: boolean }>} data.memberInclusions - 成员包含项设置
 * @returns {Promise<void>} 完成时返回
 */
const showGroupCreator = ref(false)

async function handleCreateGroup(data: {
  title: string
  memberIds: string[]
  pureAiMode: boolean
  firstMessageCharacterId: string | null
  memberInclusions: Record<string, { includePersonality: boolean; includeScenario: boolean }>
}) {
  const firstMember = data.memberIds[0]
  if (!firstMember) return

  const memberSettings: Record<string, GroupMemberSettings> = {}
  for (const id of data.memberIds) {
    const inc = data.memberInclusions[id] ?? { includePersonality: true, includeScenario: true }
    memberSettings[id] = {
      model: null,
      presetId: null,
      temperature: null,
      top_p: null,
      probability: 1.0,
      includePersonality: inc.includePersonality,
      includeScenario: inc.includeScenario,
    }
  }

  const personaId = data.pureAiMode ? null : effectiveSelectedPersonaId.value
  await chats.createGroup(
    firstMember,
    data.memberIds,
    data.title,
    data.pureAiMode,
    data.firstMessageCharacterId,
    memberSettings,
    personaId ?? null,
  )
  scrollToBottom()
}

/**
 * 打开创建角色
 *
 * 打开角色编辑弹窗，设置为新建模式。
 * 重置工作区助手聊天，加载助手状态，并尝试获取工作区中的角色卡数据。
 * 使用actions.openCreateCharacter（来自composables/useChatActions.ts）打开编辑。
 * 使用assistant.resetWorkspaceChat和loadState（来自composables/useAssistant.ts）管理助手状态。
 * 使用apiGet函数（来自api/http.ts）获取工作区角色卡。
 *
 * @returns {Promise<void>} 完成时返回
 */
async function openCreateCharacter() {
  actions.openCreateCharacter()
  await assistant.resetWorkspaceChat()
  void assistant.loadState('workspace')
  
  try {
    const res = await apiGet<{ ok: boolean; card: any }>('/api/assistant/workspace/character-card')
    if (res.ok && res.card) {
      actions.applyAssistantCard(res.card)
    }
  } catch (e) {
    console.log('No existing character card in workspace:', e)
  }
}

/**
 * 打开编辑角色
 *
 * 打开角色编辑弹窗，设置为编辑模式，加载角色数据。
 * 重置工作区助手聊天，加载助手状态。
 * 使用actions.openEditCharacter（来自composables/useChatActions.ts）打开编辑。
 * 使用assistant.resetWorkspaceChat和loadState（来自composables/useAssistant.ts）管理助手状态。
 *
 * @param {CharacterCard} card - 要编辑的角色卡片（来自types/models.ts）
 * @returns {Promise<void>} 完成时返回
 */
async function openEditCharacter(card: CharacterCard) {
  actions.openEditCharacter(card)
  await assistant.resetWorkspaceChat()
  void assistant.loadState('workspace')
}

/**
 * 保存角色
 *
 * 保存角色卡片，如果保存成功则选中该角色。
 * 删除工作区助手聊天，如果助手面板打开则加载聊天作用域状态。
 * 使用actions.saveCharacter（来自composables/useChatActions.ts）保存角色。
 * 使用assistant.deleteWorkspaceChat和loadState（来自composables/useAssistant.ts）管理助手状态。
 *
 * @returns {Promise<void>} 完成时返回
 */
async function saveCharacter() {
  const id = await actions.saveCharacter()
  if (id) {
    selectedCharacterId.value = id
  }
  await assistant.deleteWorkspaceChat()
  if (assistant.isAssistantPanelOpen.value) await assistant.loadState('chat')
}

/**
 * 取消角色编辑
 *
 * 取消角色编辑，删除工作区助手聊天，如果助手面板打开则加载聊天作用域状态。
 * 使用actions.cancelCharacterEdit（来自composables/useChatActions.ts）取消编辑。
 * 使用assistant.deleteWorkspaceChat和loadState（来自composables/useAssistant.ts）管理助手状态。
 *
 * @returns {Promise<void>} 完成时返回
 */
async function cancelCharacterEdit() {
  await assistant.deleteWorkspaceChat()
  if (assistant.isAssistantPanelOpen.value) await assistant.loadState('chat')
  actions.cancelCharacterEdit()
}

/**
 * 删除角色
 *
 * 删除指定的角色卡片。
 * 如果删除的是当前选中的角色，则选中第一个可用角色。
 * 使用actions.deleteCharacter（来自composables/useChatActions.ts）删除角色。
 *
 * @param {string} id - 角色ID
 * @returns {Promise<void>} 完成时返回
 */
async function deleteCharacter(id: string) {
  const nextId = await actions.deleteCharacter(id)
  if (selectedCharacterId.value === id) {
    selectedCharacterId.value = nextId
  }
}

/**
 * 确认切换身份（新建会话）
 *
 * 切换用户身份，并创建新的聊天会话。
 * 保存新的选中身份，然后基于当前聊天创建新会话（标题添加"（新建会话）"）。
 * 使用settingsStore.save（来自stores/settings.ts）保存设置。
 * 使用chatsStore.create或createGroup（来自stores/chats.ts）创建新会话。
 *
 * @returns {Promise<void>} 完成时返回
 */
async function confirmSwitchPersonaNewSession() {
  if (!settings.settings) return
  if (!actions.pendingPersonaId.value) return
  const targetId = actions.pendingPersonaId.value
  actions.showPersonaSwitchConfirm.value = false
  actions.pendingPersonaId.value = null

  await settings.save({ ...settings.settings, selectedPersonaId: targetId })
  if (!activeChat.value) return

  const title = `${activeChat.value.title}（新建会话）`
  const pure = group.effectivePureAiMode.value
  const personaId = pure ? null : targetId
  if (activeChat.value.isGroup) {
    await chats.createGroup(
      activeChat.value.characterId,
      [...activeChat.value.memberIds],
      title,
      pure,
      null,
      activeChat.value.memberSettings || null,
      personaId,
    )
  } else {
    await chats.create(activeChat.value.characterId, title, pure, personaId)
  }
  scrollToBottom()
}

/**
 * 确认切换身份（继续对话）
 *
 * 切换用户身份，但继续当前对话。
 * 先固化历史user消息的发送者快照，然后保存新的选中身份，更新聊天会话的身份ID。
 * 使用actions.freezeUserMessagesSenderSnapshot（来自composables/useChatActions.ts）固化快照。
 * 使用settingsStore.save（来自stores/settings.ts）保存设置。
 * 使用chatsStore.updateUserPersonaId（来自stores/chats.ts）更新聊天身份。
 *
 * @returns {Promise<void>} 完成时返回
 */
async function confirmSwitchPersonaContinue() {
  if (!settings.settings) return
  if (!actions.pendingPersonaId.value) return
  const targetId = actions.pendingPersonaId.value
  actions.showPersonaSwitchConfirm.value = false
  actions.pendingPersonaId.value = null
  
  await actions.freezeUserMessagesSenderSnapshot()
  await settings.save({ ...settings.settings, selectedPersonaId: targetId })
  if (activeChat.value) {
    await chats.updateUserPersonaId(activeChat.value.id, targetId)
  }
}

/**
 * 处理仅保存编辑的消息
 *
 * 保存编辑后的消息到服务器；若该消息有多版本，则同步更新当前版本内容与本地消息显示。
 *
 * @returns {Promise<void>} 完成时返回
 */
async function handleSaveEditedMessage() {
  const messageId = actions.editingMessageId.value
  const newContent = actions.editingMessageContent.value
  if (messageId && activeChat.value && newContent !== undefined) {
    const msg = activeChat.value.messages.find(m => m.id === messageId)
    if (msg && versions.hasMultipleVersions(msg)) {
      versions.updateCurrentVersionContent(messageId, newContent)
      msg.content = newContent
    }
  }
  await actions.saveEditedMessage()
}

/**
 * 处理保存并发送
 *
 * 保存编辑后的消息，删除该消息之后的所有消息，然后重新生成回复。
 * 支持单聊和群聊两种模式，支持流式和非流式两种生成方式。
 * 使用chatsStore.updateMessage和deleteMessage（来自stores/chats.ts）更新和删除消息。
 * 使用postAndConsumeSse函数（来自api/sse.ts）或apiPost函数（来自api/http.ts）发送请求。
 *
 * @returns {Promise<void>} 完成时返回
 */
async function handleSaveAndSend() {
  if (!activeChat.value) return
  if (!actions.editingMessageId.value) return
  if (isGenerating.value) return
  if (actions.editingMessageRole.value === 'assistant') return

  const chatId = activeChat.value.id
  const messageId = actions.editingMessageId.value
  const messageIndex = activeChat.value.messages.findIndex(msg => msg.id === messageId)
  if (messageIndex === -1) return

  const editedRole = actions.editingMessageRole.value
  const editedContent = actions.editingMessageContent.value
  const originalMessage = activeChat.value.messages[messageIndex]
  if (!originalMessage) return

  await chats.updateMessage(chatId, messageId, editedRole, editedContent, originalMessage.characterId)

  const messagesToDelete = activeChat.value.messages.slice(messageIndex + 1)
  for (const msgToDelete of messagesToDelete) {
    if (!msgToDelete.id.startsWith('local_')) {
      await chats.deleteMessage(chatId, msgToDelete.id)
    }
  }

  actions.closeEditMessage()
  group.resetGroupState()
  group.showInterjectPanel.value = group.effectivePureAiMode.value

  isGenerating.value = true
  aborter.value?.abort()
  aborter.value = new AbortController()

  const useStream = settings.settings?.streamEnabled !== false
  const isGroup = activeChat.value.isGroup
  const now = new Date().toISOString()

  try {
    if (isGroup) {
      const allMemberIds = [...activeChat.value.memberIds]
      const groupDelay = activeChat.value.groupDelay || 1500
      const memberIds = group.filterMembersByProbability(allMemberIds)

      await runGroupGeneration(chatId, memberIds, useStream, groupDelay, 0)
      if (group.isPaused.value) return

      group.currentSpeakerIndex.value = -1
      group.showInterject()
    } else {
      const localAssistantId = `local_assistant_${Date.now()}`
      chatReasoningMessageId.value = localAssistantId
      chatReasoningContent.value = ''
      chats.addLocalMessage({ version: 1, id: localAssistantId, role: 'assistant', content: '', ts: now })
      scrollToBottom()

      if (useStream) {
        stream.registerStreamMessage(localAssistantId)
        try {
          await postAndConsumeSse(
            '/api/generate/stream',
            {
              chatId,
              userMessage: editedContent,
              appendUserMessage: false,
              userPersona: selectedPersona.value ?? null,
            },
            (evt) => {
              if (stopRequested.value) return
              if (evt.event === 'delta') {
                const data = evt.data as { text?: string } | undefined
                const t = data?.text
                if (typeof t === 'string') {
                  stream.appendDeltaBuffered(localAssistantId, t)
                }
              } else if (evt.event === 'reasoning') {
                const data = evt.data as { text?: string } | undefined
                const t = data?.text
                if (typeof t === 'string') {
                  chatReasoningContent.value += t
                }
              } else if (evt.event === 'done') {
                const data = evt.data as { assistantMessageId?: string } | undefined
                const serverId = data?.assistantMessageId
                if (serverId && chatReasoningContent.value) {
                  chatReasoningMessageId.value = serverId
                }
                pushCurrentReasoningToBlocks(serverId ?? undefined)
              } else if (evt.event === 'error') {
                const data = evt.data as { message?: string } | undefined
                streamError.value = String(data?.message ?? 'unknown error')
              }
            },
            aborter.value?.signal,
          )
        } finally {
          stream.flushForMessage(localAssistantId)
          stopRequested.value = false
        }
      } else {
        const res = await apiPost<{ ok: boolean; content: string; reasoningContent?: string; assistantMessageId?: string | null; error?: string }>('/api/generate/stream', {
          chatId,
          userMessage: editedContent,
          appendUserMessage: false,
          userPersona: selectedPersona.value ?? null,
        })

        if (res.ok) {
          if (typeof res.reasoningContent === 'string') {
            chatReasoningContent.value = res.reasoningContent
          }
          pushCurrentReasoningToBlocks(res.assistantMessageId ?? undefined)
          chats.appendLocalMessageContent(localAssistantId, res.content || '')
          scrollToBottom()
        } else {
          streamError.value = res.error || 'unknown error'
        }
      }
    }
  } catch (e: any) {
    if (!isAbortError(e)) {
      streamError.value = e?.message ?? String(e)
    }
  } finally {
    isGenerating.value = false
    group.currentSpeakerIndex.value = -1
    if (stopStreamingHold.value) {
      await persistLocalStreamingMessages(chatId)
      stopStreamingHold.value = false
    } else {
      await chats.load(chatId)
    }
    await settings.load()
  }
}

/**
 * 计算编辑中的角色头像URL
 *
 * 根据编辑中的角色头像字段生成头像URL。
 */
const editingCharacterAvatarUrl = computed(() => {
  if (!actions.editingCharacter.value?.avatar) return null
  return `/api/avatars/${actions.editingCharacter.value.avatar}`
})

/**
 * 计算编辑中的身份头像URL
 *
 * 根据编辑中的身份头像字段生成头像URL。
 */
const editingPersonaAvatarUrl = computed(() => {
  if (!actions.editingPersona.value?.avatar) return null
  return `/api/avatars/${actions.editingPersona.value.avatar}`
})
</script>

<template>
  <div class="flex h-screen w-full bg-gradient-to-br from-[#0f172a] to-[#1e293b] text-gray-200 overflow-hidden font-sans">
    
    <!-- 左侧侧边栏 -->
    <ChatSidebar
      :collapsed="sidebarCollapsed"
      :personas="settings.settings?.userPersonas || []"
      :selected-persona-id="effectiveSelectedPersonaId"
      :effective-pure-ai-mode="group.effectivePureAiMode.value"
      :characters="characters.list"
      :selected-character-id="selectedCharacterId"
      :chat-list="chats.list"
      :group-list="chats.groupList"
      :active-chat-id="chats.activeChatId"
      :editing-chat-id="editingChatId"
      :editing-title="editingTitle"
      @update:collapsed="sidebarCollapsed = $event"
      @update:selected-character-id="selectedCharacterId = $event"
      @update:editing-title="editingTitle = $event"
      @select-persona="actions.selectPersona"
      @edit-persona="actions.openEditPersona"
      @create-persona="actions.openCreatePersona"
      @delete-persona="actions.deletePersona"
      @edit-character="openEditCharacter"
      @create-character="openCreateCharacter"
      @delete-character="deleteCharacter"
      @select-chat="selectChat"
      @select-group="selectChat"
      @create-chat="createChat"
      @create-group="showGroupCreator = true"
      @start-edit-title="startEditTitle"
      @save-title="saveTitle"
      @cancel-edit-title="cancelEditTitle"
      @delete-chat="deleteChat"
    />

    <!-- 右侧主区域 + 助理面板 -->
    <div class="flex-1 flex min-w-0 relative">
      <main class="flex-1 flex flex-col relative min-w-0 bg-transparent transition-all duration-300">
      
        <!-- 聊天内容区 -->
        <div v-if="(selectedCharacter || activeChat?.isGroup) && activeChat" class="flex flex-col h-full relative">
          <!-- 顶部标题栏 -->
          <header 
            class="absolute top-0 left-0 right-0 z-10 flex flex-col bg-gradient-to-b from-[#0f172a] via-[#0f172a]/90 to-transparent pointer-events-none"
            style="transform: translateZ(0);"
          >
            <div class="h-14 flex items-center justify-between px-6">
              <div class="pointer-events-auto flex items-center gap-3">
                <template v-if="activeChat.isGroup">
                  <span class="text-purple-400"><Users class="w-4 h-4" /></span>
                  <h2 class="text-lg font-bold text-purple-300 shadow-sm">{{ activeChat.title }}</h2>
                  <span class="text-xs text-gray-500">({{ activeChat.memberIds.length }}个角色)</span>
                  <button 
                    class="ml-1 p-1 text-purple-400 hover:text-white transition-colors" 
                    title="群聊设置"
                    @click="showGroupSettings = true"
                  >
                    <Settings class="w-4 h-4" />
                  </button>
                </template>
                <template v-else>
                  <h2 class="text-lg font-bold text-gray-100 shadow-sm">{{ selectedCharacter?.name }}</h2>
                  <span class="text-gray-600">/</span>
                  <span class="text-sm text-gray-400">{{ activeChat.title }}</span>
                </template>
              </div>
              <div class="pointer-events-auto flex items-center gap-2">
                <button class="btn btn-sm btn-secondary" @click="actions.exportChat('txt')">
                  导出TXT
                </button>
                <button class="btn btn-sm btn-secondary" @click="actions.exportChat('json')">
                  导出JSON
                </button>
                <button class="btn btn-sm btn-primary" @click="settingsTab = 'global'; showSettings = true">
                  设置
                </button>
              </div>
            </div>
            
            <!-- 群成员头像行 -->
            <div v-if="activeChat.isGroup && groupMembers.length > 0" class="px-6 pb-2 pointer-events-auto">
              <div class="flex items-center gap-2 overflow-x-auto pb-1">
                <div class="text-xs text-gray-500 shrink-0">成员:</div>
                <div 
                  v-for="(member, idx) in groupMembers" 
                  :key="member.id"
                  class="flex items-center gap-1 shrink-0 bg-white/5 px-2 py-1 rounded-lg transition-colors group/member"
                  :class="group.canInterject.value ? 'cursor-pointer hover:bg-purple-500/20' : ''"
                  @click="group.canInterject.value && triggerInterject(member.id)"
                >
                  <span class="text-xs text-gray-500">{{ idx + 1 }}.</span>
                  <ModernAvatar 
                    :src="member.avatar ? `/api/avatars/${member.avatar}` : null" 
                    :name="member.name" 
                    :size="20" 
                    aspect="1"
                    rounded="rounded"
                  />
                  <span class="text-xs text-gray-300 max-w-[60px] truncate">{{ member.name }}</span>
                  <span 
                    v-if="group.getMemberSettings(member.id).probability < 1" 
                    class="text-[10px] text-yellow-400 ml-0.5"
                  >
                    {{ Math.round(group.getMemberSettings(member.id).probability * 100) }}%
                  </span>
                </div>
                <div v-if="!group.effectivePureAiMode.value" class="flex items-center gap-1 shrink-0 bg-brand/10 px-2 py-1 rounded-lg border border-brand/20">
                  <ModernAvatar :src="userAvatarUrl" :name="userName" :size="20" aspect="1" rounded="rounded" />
                  <span class="text-xs text-brand max-w-[60px] truncate">{{ userName }}</span>
                  <span class="text-[10px] text-brand/60">(你)</span>
                </div>
              </div>
            </div>
          </header>

          <!-- 消息列表 -->
          <MessageList
            ref="messageListRef"
            :messages="activeChat.messages"
            :is-group="activeChat.isGroup"
            :selected-character="selectedCharacter"
            :characters="characters.list"
            :selected-persona="selectedPersona"
            :user-name="userName"
            :user-avatar-url="userAvatarUrl"
            :character-avatar-url="characterAvatarUrl"
            :is-generating="isGenerating"
            :reasoning-message-id="chatReasoningMessageId"
            :reasoning-content="chatReasoningContent"
            :reasoning-blocks="chatReasoningBlocks"
            :get-display-content="versions.getDisplayContent"
            :get-display-reasoning="versions.getDisplayReasoning"
            :has-multiple-versions="versions.hasMultipleVersions"
            :get-current-version-index="versions.getCurrentVersionIndex"
            :get-version-count="versions.getVersionCount"
            @edit-message="(m) => actions.openEditMessage(m, versions.getDisplayContent(m))"
            @delete-message="actions.deleteMessage"
            @rewrite-message="handleRewriteMessage"
            @switch-previous-version="handleSwitchPreviousVersion"
            @switch-next-version="handleSwitchNextVersion"
            @set-content-ref="stream.setMessageContentRef"
          />

          <!-- 输入区域 -->
          <ChatInput
            v-model="draftMessage"
            :is-generating="isGenerating"
            :stream-error="streamError"
            :is-group="activeChat.isGroup"
            :group-members="groupMembers"
            :current-speaker-index="group.currentSpeakerIndex.value"
            :is-paused="group.isPaused.value"
            :show-continue-button="group.showContinueButton.value"
            :pending-members-count="group.pendingMembers.value.length"
            :can-interject="group.canInterject.value"
            :show-interject-panel="group.showInterjectPanel.value"
            :is-interjecting="group.isInterjecting.value"
            :effective-pure-ai-mode="group.effectivePureAiMode.value"
            :is-streaming-active="isStreamingActive"
            :user-avatar-url="userAvatarUrl"
            :user-name="userName"
            :current-model="currentModel"
            :model-options="chatModelOptions"
            :get-member-settings="group.getMemberSettings"
            @send="sendUserMessage"
            @primary-action="handlePrimaryAction"
            @pause-group="group.pauseGroupChat"
            @continue-group="continueGroupChat"
            @trigger-interject="triggerInterject"
            @hide-interject="group.hideInterject"
            @select-model="handleModelSelect"
            @toggle-assistant="assistant.isAssistantPanelOpen.value = !assistant.isAssistantPanelOpen.value"
          />
        </div>

        <!-- 空状态 -->
        <div v-else class="flex flex-col items-center justify-center h-full text-center p-8 opacity-60">
          <div class="absolute top-4 right-4 pointer-events-auto opacity-100">
            <button class="btn btn-sm btn-secondary" @click="settingsTab = 'global'; showSettings = true">
              设置
            </button>
          </div>
          <div class="w-20 h-20 rounded-2xl bg-white/5 mb-6 flex items-center justify-center text-4xl">👋</div>
          <h3 class="text-xl font-bold text-gray-200 mb-2">欢迎来到 SimpleTavern</h3>
          <p class="text-gray-500 mb-8 leading-relaxed px-4 max-w-[468px] w-full">请在左侧选择一个角色并开始会话，或者创建一个新的角色。</p>
          <button class="bg-brand text-white px-6 py-2 rounded-xl hover:bg-brand-hover transition-colors" @click="openCreateCharacter">
            创建新角色
          </button>
        </div>
      </main>

    <!-- 聊天助理面板 -->
    <AssistantPanel
      :is-open="assistant.isAssistantPanelOpen.value"
      :messages="assistant.assistantMessages.value"
      :draft="assistant.assistantDraft.value"
      :is-generating="assistant.isAssistantGenerating.value"
      :stream-error="assistant.assistantStreamError.value"
      :reasoning-blocks="assistant.assistantReasoningBlocks.value"
      :current-model="assistantCurrentModel"
      :model-options="chatModelOptions"
      @update:is-open="assistant.isAssistantPanelOpen.value = $event"
      @update:draft="assistant.assistantDraft.value = $event"
      @send="assistant.sendMessage('chat')"
      @reset="assistant.resetChat"
      @open-settings="assistant.showAssistantSettings.value = true"
      @select-model="assistant.handleModelSelect"
      @edit-message="(m) => assistant.openEditMessage(m, 'chat')"
      @delete-message="(m) => assistant.deleteMessage(m, 'chat')"
      @rewrite-message="(m) => assistant.rewriteMessage(m, 'chat')"
    />

    <!-- 助手设置抽屉 -->
          <!-- 消息编辑弹窗 -->
    <MessageEditorModal
      :show="actions.showMessageEditor.value"
      :message-id="actions.editingMessageId.value"
      :message-role="actions.editingMessageRole.value"
      :message-content="actions.editingMessageContent.value"
      :character-avatar-url="characterAvatarUrl"
      :user-avatar-url="userAvatarUrl"
      :is-generating="isGenerating"
      @update:show="actions.showMessageEditor.value = $event"
      @update:message-role="actions.editingMessageRole.value = $event"
      @update:message-content="actions.editingMessageContent.value = $event"
      @save="handleSaveEditedMessage"
      @save-and-send="handleSaveAndSend"
    />

    <!-- 助手消息编辑弹窗 -->
    <MessageEditorModal
      :show="assistant.showAssistantMessageEditor.value"
      :message-id="assistant.editingAssistantMessage.value?.id || null"
      :message-role="assistant.editingAssistantMessage.value?.role || 'user'"
      :message-content="assistant.editingAssistantMessageContent.value"
      :character-avatar-url="null"
      :user-avatar-url="null"
      :is-generating="assistant.isAssistantGenerating.value || assistant.isWorkspaceAssistantGenerating.value"
      @update:show="assistant.showAssistantMessageEditor.value = $event"
      @update:message-role="(r) => { if (assistant.editingAssistantMessage.value) assistant.editingAssistantMessage.value.role = r }"
      @update:message-content="assistant.editingAssistantMessageContent.value = $event"
      @save="assistant.saveEditedMessage"
      @save-and-send="assistant.saveEditedMessage" 
    />

    <!-- 设置抽屉 -->
    <SettingsDrawer 
      v-model:show="showSettings" 
      :chat="activeChat" 
      :initial-tab="settingsTab" 
      @open-member-settings="actions.openMemberSettingsEditor"
    />

    <!-- 群聊创建弹窗 -->
    <GroupCreatorModal
      :show="showGroupCreator"
      :characters="characters.list"
      @update:show="showGroupCreator = $event"
      @create="handleCreateGroup"
    />

    <!-- 成员设置弹窗 -->
    <GroupSettingsModal
      v-model:show="showGroupSettings"
      :chat="activeChat"
      :characters="characters.list"
      @update:member-ids="handleUpdateMemberIds"
      @update:group-delay="handleUpdateGroupDelay"
      @open-member-settings="actions.openMemberSettingsEditor"
      @save="showGroupSettings = false"
    />

    <MemberSettingsModal
      :show="!!actions.editingMemberId.value"
      :member-id="actions.editingMemberId.value"
      :settings="actions.editingMemberSettings.value"
      :character="actions.editingMemberId.value ? characters.list.find(c => c.id === actions.editingMemberId.value) || null : null"
      :model-options="chatModelOptions"
      @update:show="(v) => !v && actions.closeMemberSettingsEditor()"
      @update:settings="actions.editingMemberSettings.value = $event"
      @save="actions.saveMemberSettings"
    />
  </div>
</div>

<!-- 角色编辑弹窗 -->
  <div v-if="actions.showCharacterEditor.value" class="modal">
    <div class="modal-backdrop" @click="cancelCharacterEdit"></div>
    <div class="modal-content chat-modal-width-1200-90 glass-panel bg-gradient-to-br from-slate-900/30 to-slate-800/25 backdrop-blur-2xl backdrop-saturate-[1.8] border border-white/10">
      <div class="modal-header">
        <h3 class="modal-title">{{ actions.isNewCharacter.value ? '新建角色' : '编辑角色' }}</h3>
        <button class="modal-close" @click="cancelCharacterEdit">
            <X class="w-5 h-5" />
        </button>
      </div>
      <div class="modal-body">
        <div v-if="actions.editingCharacter.value" class="flex gap-6 h-[70vh]">
          <div class="flex-1 overflow-y-auto pr-2 custom-scrollbar">
            <div class="space-y-6">
              <div class="flex gap-6">
                <div class="flex flex-col items-center gap-3">
                  <ModernAvatar 
                    :src="editingCharacterAvatarUrl"
                    :size="120"
                    aspect="auto"
                    object-fit="contain"
                    rounded="rounded-xl"
                    class="border-2 border-brand/40 shadow-lg bg-black/20"
                  />
                  <button class="btn btn-sm btn-secondary" @click="actions.showCharacterAvatarCropper.value = true">更换头像</button>
                </div>
                <div class="flex-1 space-y-4">
                  <div class="form-group">
                    <label class="label">
                      <span>名称</span>
                      <span class="opacity-60 text-xs ml-2 text-brand">该项参与对话</span>
                    </label>
                    <input v-model="actions.editingCharacter.value.name" class="input" placeholder="角色名称" />
                  </div>
                  <div class="form-group">
                    <label class="label">简介</label>
                    <textarea v-model="actions.editingCharacter.value.description" class="input textarea h-20" placeholder="简短描述"></textarea>
                  </div>
                </div>
              </div>

              <div class="form-group">
                <label class="label">
                  <span>Personality（性格/外貌）</span>
                  <span class="opacity-60 text-xs ml-2 text-brand">该项参与对话</span>
                </label>
                <textarea v-model="actions.editingCharacter.value.personality" class="input textarea h-32" placeholder="详细设定..."></textarea>
              </div>

              <div class="form-group">
                <label class="label">
                  <span>Scenario（情景/世界观）</span>
                  <span class="opacity-60 text-xs ml-2 text-brand">该项参与对话</span>
                </label>
                <textarea v-model="actions.editingCharacter.value.scenario" class="input textarea h-24" placeholder="世界背景..."></textarea>
              </div>

              <div class="form-group">
                <label class="label">
                  <span>系统提示词</span>
                  <span class="opacity-60 text-xs ml-2 text-brand">该项参与对话</span>
                </label>
                <textarea v-model="actions.editingCharacter.value.systemPrompt" class="input textarea h-32" placeholder="回复格式要求..."></textarea>
              </div>

              <div class="form-group">
                <label class="label">
                  <span>首句</span>
                  <span class="opacity-60 text-xs ml-2" v-pre>支持 {{user}} 占位符</span>
                  <span class="opacity-60 text-xs ml-2 text-brand">该项参与对话</span>
                </label>
                <textarea v-model="actions.editingCharacter.value.firstMessage" class="input textarea h-24" placeholder="开场白..."></textarea>
              </div>

              <div class="form-group">
                <label class="label">示例对话</label>
                <textarea v-model="actions.editingCharacter.value.exampleDialogue" class="input textarea h-48" placeholder="示例对话..."></textarea>
              </div>
            </div>
          </div>

          <!-- 角色编辑助手 -->
          <div class="flex-[0.66] shrink-0 glass-panel rounded-2xl p-4 flex flex-col shadow-inner">
            <div class="flex items-center justify-between mb-4 px-1">
              <span class="text-sm font-bold text-gray-400 uppercase tracking-widest flex items-center gap-2">
                <span class="w-2 h-2 rounded-full bg-brand animate-pulse"></span>
                聊天助手
              </span>
              <button class="text-gray-500 hover:text-white transition-colors" @click="assistant.showAssistantSettings.value = true">
                <MoreHorizontal class="w-4 h-4" />
              </button>
            </div>
            <div class="flex-1 overflow-y-auto custom-scrollbar space-y-4 pr-2 mb-4">
              <div v-if="assistant.workspaceAssistantMessages.value.length === 0" class="text-xs text-gray-600 text-center py-12 flex flex-col items-center gap-3">
                <div class="w-12 h-12 rounded-full bg-white/5 flex items-center justify-center text-xl">
                    <Sparkles class="w-6 h-6 text-yellow-400" />
                </div>
                开始和助手对话以完善你的角色卡
              </div>
              <div v-for="m in assistant.workspaceAssistantMessages.value" :key="m.id" class="flex flex-col gap-1 group" :class="m.role === 'user' ? 'items-end' : 'items-start'">
                <div
                  class="px-4 py-2.5 rounded-2xl text-sm leading-relaxed max-w-[90%] shadow-sm border transition-colors"
                  :class="m.role === 'user' ? 'bg-brand/10 border-brand/20 text-gray-100 rounded-tr-sm' : 'bg-white/5 border-white/5 text-gray-200 rounded-tl-sm'"
                >
                  <div class="prose prose-invert prose-sm max-w-none">{{ m.content }}</div>
                </div>
              </div>
            </div>
            <div class="pt-4 border-t border-white/5">
              <textarea
                v-model="assistant.workspaceAssistantDraft.value"
                class="input textarea h-24 !bg-black/30 !border-white/5 focus:!border-brand/40"
                placeholder="输入建议或要求 (Ctrl + Enter)..."
                :disabled="assistant.isWorkspaceAssistantGenerating.value"
                @keydown.ctrl.enter="assistant.sendMessage('workspace', true, actions.applyAssistantCard)"
              ></textarea>
              <div class="flex items-center justify-between mt-3 gap-3">
                <ModernSelect
                  :model-value="assistantCurrentModel"
                  :options="chatModelOptions"
                  placement="top"
                  placeholder="模型..."
                  class="!w-[160px] !text-xs"
                  dropdown-width="410"
                  searchable
                  allow-create
                  @select="assistant.handleModelSelect"
                />
                <button 
                  class="btn btn-primary px-6" 
                  :disabled="!assistant.workspaceAssistantDraft.value.trim() || assistant.isWorkspaceAssistantGenerating.value" 
                  @click="assistant.sendMessage('workspace', true, actions.applyAssistantCard)"
                >
                  <Loader2 v-if="assistant.isWorkspaceAssistantGenerating.value" class="animate-spin w-4 h-4 mr-2" />
                  发送
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
      <div class="modal-footer">
        <button class="btn btn-secondary" @click="actions.exportCharacterCard" :disabled="!actions.editingCharacter.value">导出为文本</button>
        <button class="btn btn-secondary" @click="cancelCharacterEdit">取消</button>
        <button class="btn btn-primary" @click="saveCharacter">保存</button>
      </div>
    </div>
  </div>

  <!-- Persona 编辑弹窗 -->
  <div v-if="actions.showPersonaEditor.value" class="modal">
    <div class="modal-backdrop" @click="actions.showPersonaEditor.value = false"></div>
    <div class="modal-content chat-modal-width-500-90 glass-panel bg-gradient-to-br from-slate-900/30 to-slate-800/25 backdrop-blur-2xl backdrop-saturate-[1.8] border border-white/10">
      <div class="modal-header">
        <h3 class="modal-title">{{ actions.isNewPersona.value ? '新建身份' : '编辑身份' }}</h3>
        <button class="modal-close" @click="actions.showPersonaEditor.value = false">
            <X class="w-5 h-5" />
        </button>
      </div>
      <div class="modal-body">
        <div v-if="actions.editingPersona.value" class="space-y-6">
          <div class="flex items-center gap-4 mb-2">
            <ModernAvatar 
              :src="editingPersonaAvatarUrl"
              :size="80"
              aspect="1"
              rounded="rounded-xl"
              class="border-2 border-brand/40"
            />
            <button class="btn btn-sm btn-secondary" @click="actions.showPersonaAvatarCropper.value = true">更换头像</button>
          </div>

          <div class="form-group">
            <label class="label">姓名（{{userName}}）</label>
            <input v-model="actions.editingPersona.value.name" class="input" placeholder="你的角色名称" />
          </div>

          <div class="form-group">
            <label class="label">简介</label>
            <textarea
              v-model="actions.editingPersona.value.description"
              class="input textarea h-32"
              placeholder="你的角色身份、背景等"
            ></textarea>
          </div>
        </div>
      </div>
      <div class="modal-footer">
        <button class="btn btn-secondary" @click="actions.showPersonaEditor.value = false">取消</button>
        <button class="btn btn-primary" @click="actions.savePersona">保存</button>
      </div>
    </div>
  </div>

  <!-- Persona 切换确认弹窗 -->
  <div v-if="actions.showPersonaSwitchConfirm.value" class="modal">
    <div class="modal-backdrop" @click="actions.cancelSwitchPersona"></div>
    <div class="modal-content chat-modal-width-520-92">
      <div class="modal-header">
        <h3 class="modal-title">切换用户身份</h3>
        <button class="modal-close" @click="actions.cancelSwitchPersona">
            <X class="w-5 h-5" />
        </button>
      </div>
      <div class="modal-body">
        <div class="space-y-4">
          <div class="text-sm text-gray-300">
            你正在尝试切换用户身份，请选择"新建会话"或"仍然继续对话"。
          </div>
          <div class="text-xs text-gray-500">
            提示：继续对话时，历史消息会保持原身份显示；后续新发送的 user 消息将使用新身份。
          </div>
        </div>
      </div>
      <div class="modal-footer">
        <button class="btn btn-secondary" @click="actions.cancelSwitchPersona">取消</button>
        <button class="btn btn-secondary" @click="confirmSwitchPersonaContinue">仍然继续对话</button>
        <button class="btn btn-primary" @click="confirmSwitchPersonaNewSession">新建会话</button>
      </div>
    </div>
  </div>

  <!-- 助手设置弹窗 -->
  <div v-if="assistant.showAssistantSettings.value" class="modal">
    <div class="modal-backdrop" @click="assistant.showAssistantSettings.value = false"></div>
    <div class="modal-content chat-modal-width-520-92">
      <div class="modal-header">
        <h3 class="modal-title">聊天助手设置</h3>
        <button class="modal-close" @click="assistant.showAssistantSettings.value = false">
            <X class="w-5 h-5" />
        </button>
      </div>
      <div class="modal-body">
        <div class="space-y-6">
          <div class="form-group">
            <label class="label">提示词</label>
            <textarea
              v-model="assistant.assistantSettings.value.prompt"
              class="input textarea h-48 !bg-black/20"
              placeholder="输入聊天助手提示词..."
            ></textarea>
          </div>
          <div class="form-group">
            <label class="label">温度</label>
            <input
              v-model.number="assistant.assistantSettings.value.temperature"
              type="number"
              min="0"
              max="2"
              step="0.1"
              class="input w-full"
            />
          </div>
          <div class="form-group">
            <label class="label">Context Size</label>
            <input
              v-model.number="assistant.assistantSettings.value.context_size"
              type="number"
              min="0"
              class="input w-full"
              placeholder="未启用（不限制）"
            />
            <p class="text-xs text-gray-500 mt-1">填 0 或留空表示未启用。实际上下文总限制长度为该 Context Size 限制加上角色卡、用户信息、自定义系统提示词。</p>
          </div>
        </div>
      </div>
      <div class="modal-footer">
        <button class="btn btn-secondary" @click="assistant.showAssistantSettings.value = false">取消</button>
        <button class="btn btn-primary" @click="assistant.saveSettingsAndClose">保存</button>
      </div>
    </div>
  </div>

  <!-- 头像裁剪 -->
  <AvatarCropper
    v-model:show="actions.showCharacterAvatarCropper.value"
    @save="actions.handleCharacterAvatarSave"
  />

  <AvatarCropper
    v-model:show="actions.showPersonaAvatarCropper.value"
    @save="actions.handlePersonaAvatarSave"
  />
</template>

<style scoped>
.custom-scrollbar::-webkit-scrollbar {
  width: 4px;
}
.custom-scrollbar::-webkit-scrollbar-track {
  background: transparent;
}
.custom-scrollbar::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.1);
  border-radius: 2px;
}
.custom-scrollbar:hover::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.2);
}
</style>
