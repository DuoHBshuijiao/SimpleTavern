<script setup lang="ts">
/**
 * ChatPage - 聊天页面主组件
 * 
 * 职责：
 * - 协调各子组件和 composables
 * - 管理页面级状态
 * - 处理核心业务流程（消息发送、生成等）
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

// ========== 计算属性 ==========
const selectedCharacter = computed(() => {
  if (!selectedCharacterId.value) return null
  return characters.list.find((c) => c.id === selectedCharacterId.value) ?? null
})

const activeChat = computed(() => chats.activeChat)
const assistantChatId = computed(() => activeChat.value?.id ?? null)

const characterAvatarUrl = computed(() => {
  if (!selectedCharacter.value?.avatar) return null
  return `/api/avatars/${selectedCharacter.value.avatar}`
})

const userAvatarUrl = computed(() => {
  if (!selectedPersona.value?.avatar) return null
  return `/api/avatars/${selectedPersona.value.avatar}`
})

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

// 聊天助手
const assistant = useAssistant({
  chatId: assistantChatId,
})

// Persona 相关计算
function getPersonaById(id: string | null | undefined) {
  if (!id || !settings.settings?.userPersonas) return null
  return settings.settings.userPersonas.find(p => p.id === id) ?? null
}

function getLastUserPersonaIdFromChat(chat: Chat | null | undefined) {
  if (!chat?.messages?.length) return null
  for (let i = chat.messages.length - 1; i >= 0; i--) {
    const m = chat.messages[i]
    if (m?.role === 'user' && m.senderPersonaId) return m.senderPersonaId
  }
  return null
}

const effectiveSelectedPersonaId = computed(() => {
  if (group.effectivePureAiMode.value) return null
  const chat = activeChat.value
  return chat?.userPersonaId
    ?? getLastUserPersonaIdFromChat(chat)
    ?? settings.settings?.selectedPersonaId
    ?? null
})

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

// ========== 群聊设置相关 ==========
async function handleUpdateMemberIds(memberIds: string[]) {
  if (activeChat.value) {
    await chats.updateMemberOrder(activeChat.value.id, memberIds)
  }
}

async function handleUpdateGroupDelay(delay: number) {
  if (activeChat.value) {
    await chats.updateGroupDelay(activeChat.value.id, delay)
  }
}

// ========== 模型选择相关 ==========
const chatModelOptions = computed(() => {
  const options: any[] = []
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

const currentModel = computed(() => {
  return chats.activeChat?.overrides?.params?.model || settings.settings?.llm.defaultModel || '未设置'
})

const assistantCurrentModel = computed(() => {
  return assistant.assistantSettings.value.model || settings.settings?.llm.defaultModel || '未设置'
})

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

// ========== 滚动和引用 ==========
const messageListRef = ref<InstanceType<typeof MessageList> | null>(null)

function scrollToBottom() {
  nextTick(() => {
    messageListRef.value?.scrollToBottom()
  })
}

// ========== 群成员相关 ==========
const groupMembers = computed(() => {
  if (!activeChat.value?.isGroup) return []
  return activeChat.value.memberIds
    .map(id => characters.list.find(c => c.id === id))
    .filter((c): c is CharacterCard => c !== null)
})

// ========== 流式相关计算 ==========
const isStreamEnabled = computed(() => settings.settings?.streamEnabled !== false)
const isStreamingActive = computed(() => isStreamEnabled.value && (isGenerating.value || group.isInterjecting.value))
const hasDraftMessage = computed(() => !!draftMessage.value.trim())

// ========== 辅助函数 ==========
function isAbortError(e: any) {
  return e?.name === 'AbortError'
}

// ========== 生命周期 ==========
onMounted(async () => {
  if (!settings.settings) await settings.load()
  await characters.loadAll()
  await chats.loadGroupList()

  if (!selectedCharacterId.value) {
    const first = characters.list[0]
    if (first) selectedCharacterId.value = first.id
  }
})

// ========== Watchers ==========
watch(assistant.isAssistantPanelOpen, (next) => {
  if (next) void assistant.loadState('chat')
})

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

watch(
  () => assistantChatId.value,
  (next, prev) => {
    if (next && next !== prev && assistant.isAssistantPanelOpen.value) {
      void assistant.loadState('chat')
    }
  },
)

watch(actions.showCharacterEditor, (next, prev) => {
  if (!next && prev && actions.editingCharacter.value) {
    void assistant.deleteWorkspaceChat()
    if (assistant.isAssistantPanelOpen.value) void assistant.loadState('chat')
    actions.editingCharacter.value = null
    actions.isNewCharacter.value = false
  }
})

// ========== 核心业务方法 ==========
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
              const t = evt.data?.text
              if (typeof t === 'string') {
                stream.appendDeltaBuffered(localAssistantId, t)
              }
            } else if (evt.event === 'error') {
              streamError.value = String(evt.data?.message ?? 'unknown error')
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
        error?: string
      }>('/api/generate/group', { chatId, characterId })
      
      if (res.ok) {
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
        await chats.updateMessage(activeChat.value.id, msg.id, msg.role, content)
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
            },
            (evt) => {
              if (stopRequested.value) return
              if (evt.event === 'delta') {
                const t = evt.data?.text
                if (typeof t === 'string') {
                  stream.appendDeltaBuffered(localAssistantId, t)
                }
              } else if (evt.event === 'error') {
                streamError.value = String(evt.data?.message ?? 'unknown error')
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
          error?: string
        }>('/api/generate/stream', {
          chatId,
          userMessage: text,
          senderPersonaId: selectedPersona.value?.id ?? null,
          senderName: selectedPersona.value?.name ?? userName.value,
          senderAvatar: selectedPersona.value?.avatar ?? null,
        })
        
        if (res.ok) {
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
      stopStreamingHold.value = false
    } else {
      await chats.load(chatId)
    }
    await settings.load()
  }
}

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
    if (skippedReload) stopStreamingHold.value = false
    if (!group.isPaused.value) {
      isGenerating.value = false
      group.currentSpeakerIndex.value = -1
      group.pendingMembers.value = []
      if (!skippedReload) {
        await chats.load(chatId)
        await settings.load()
      }
    }
  }
}

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
    if (skippedReload) stopStreamingHold.value = false
    if (!group.isPaused.value && !skippedReload) {
      await chats.load(chatId)
      await settings.load()
    }
  }
}

async function triggerInterject(characterId: string) {
  if (!activeChat.value || isGenerating.value || group.isInterjecting.value) return
  
  const chatId = activeChat.value.id
  group.isInterjecting.value = true
  streamError.value = null
  aborter.value?.abort()
  aborter.value = new AbortController()
  
  const useStream = settings.settings?.streamEnabled !== false
  
  const localAssistantId = `local_interject_${Date.now()}`
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
              const t = evt.data?.text
              if (typeof t === 'string') {
                stream.appendDeltaBuffered(localAssistantId, t)
              }
            } else if (evt.event === 'error') {
              streamError.value = String(evt.data?.message ?? 'unknown error')
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
        error?: string
      }>('/api/generate/interject', { chatId, characterId })
      
      if (res.ok) {
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
      stopStreamingHold.value = false
    } else {
      await chats.load(chatId)
    }
  }
}

function stopStreaming() {
  if (!aborter.value) return
  stopRequested.value = true
  stopStreamingHold.value = true
  aborter.value.abort()
  stream.flushAll()
}

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

// ========== 消息版本操作 ==========
function handleSwitchPreviousVersion(m: ChatMessage) {
  const newContent = versions.switchToPreviousVersion(m)
  if (newContent !== null && activeChat.value) {
    const msg = activeChat.value.messages.find(msg => msg.id === m.id)
    if (msg) msg.content = newContent
  }
}

function handleSwitchNextVersion(m: ChatMessage) {
  const newContent = versions.switchToNextVersion(m)
  if (newContent !== null && activeChat.value) {
    const msg = activeChat.value.messages.find(msg => msg.id === m.id)
    if (msg) msg.content = newContent
  }
}

// ========== 消息操作 ==========
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

  versions.saveVersion(m.id, m.content)

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
                const t = evt.data?.text
                if (typeof t === 'string') {
                  stream.appendDeltaBuffered(localAssistantId, t)
                }
              } else if (evt.event === 'error') {
                streamError.value = String(evt.data?.message ?? 'unknown error')
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
          error?: string
        }>('/api/generate/group', { chatId, characterId })
        
        if (res.ok) {
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
            },
            (evt) => {
              if (stopRequested.value) return
              if (evt.event === 'delta') {
                const t = evt.data?.text
                if (typeof t === 'string') {
                  stream.appendDeltaBuffered(localAssistantId, t)
                }
              } else if (evt.event === 'error') {
                streamError.value = String(evt.data?.message ?? 'unknown error')
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
          error?: string
        }>('/api/generate/stream', {
          chatId,
          userMessage: lastUserMessage.content,
          appendUserMessage: false,
        })
        
        if (res.ok) {
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
      stopStreamingHold.value = false
    } else {
      await chats.load(chatId)
    }
    await settings.load()
    
    // 添加新版本
    if (!skippedReload && activeChat.value) {
      const newMsg = activeChat.value.messages.find(msg => 
        msg.role === 'assistant' && msg.ts > m.ts
      )
      if (newMsg) {
        versions.addNewVersion(m.id, newMsg.id, newMsg.content)
      }
    }
  }
}

// ========== 会话管理 ==========
function startEditTitle(chatId: string, currentTitle: string) {
  editingChatId.value = chatId
  editingTitle.value = currentTitle
}

async function saveTitle() {
  if (!editingChatId.value || !editingTitle.value.trim()) return
  await chats.rename(editingChatId.value, editingTitle.value.trim())
  editingChatId.value = null
  editingTitle.value = ''
}

function cancelEditTitle() {
  editingChatId.value = null
  editingTitle.value = ''
}

async function createChat() {
  if (!selectedCharacterId.value) return
  await chats.create(selectedCharacterId.value)
  scrollToBottom()
}

async function deleteChat(chatId: string) {
  await chats.remove(chatId)
}

async function selectChat(chat: Chat) {
  await chats.load(chat.id)
  scrollToBottom()
}

// ========== 群聊创建 ==========
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

// ========== 角色管理 ==========
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

async function openEditCharacter(card: CharacterCard) {
  actions.openEditCharacter(card)
  await assistant.resetWorkspaceChat()
  void assistant.loadState('workspace')
}

async function saveCharacter() {
  const id = await actions.saveCharacter()
  if (id) {
    selectedCharacterId.value = id
  }
  await assistant.deleteWorkspaceChat()
  if (assistant.isAssistantPanelOpen.value) await assistant.loadState('chat')
}

async function cancelCharacterEdit() {
  await assistant.deleteWorkspaceChat()
  if (assistant.isAssistantPanelOpen.value) await assistant.loadState('chat')
  actions.cancelCharacterEdit()
}

async function deleteCharacter(id: string) {
  const nextId = await actions.deleteCharacter(id)
  if (selectedCharacterId.value === id) {
    selectedCharacterId.value = nextId
  }
}

// ========== Persona 管理 ==========
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

// ========== 编辑后发送 ==========
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

  await chats.updateMessage(chatId, messageId, editedRole, editedContent)

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
            },
            (evt) => {
              if (stopRequested.value) return
              if (evt.event === 'delta') {
                const t = evt.data?.text
                if (typeof t === 'string') {
                  stream.appendDeltaBuffered(localAssistantId, t)
                }
              } else if (evt.event === 'error') {
                streamError.value = String(evt.data?.message ?? 'unknown error')
              }
            },
            aborter.value?.signal,
          )
        } finally {
          stream.flushForMessage(localAssistantId)
          stopRequested.value = false
        }
      } else {
        const res = await apiPost<{ ok: boolean; content: string; error?: string }>('/api/generate/stream', {
          chatId,
          userMessage: editedContent,
          appendUserMessage: false,
        })

        if (res.ok) {
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
      stopStreamingHold.value = false
    } else {
      await chats.load(chatId)
    }
    await settings.load()
  }
}

// ========== 计算属性 - 用于组件 ==========
const editingCharacterAvatarUrl = computed(() => {
  if (!actions.editingCharacter.value?.avatar) return null
  return `/api/avatars/${actions.editingCharacter.value.avatar}`
})

const editingPersonaAvatarUrl = computed(() => {
  if (!actions.editingPersona.value?.avatar) return null
  return `/api/avatars/${actions.editingPersona.value.avatar}`
})
</script>

<template>
  <div class="flex h-screen w-full bg-dark-bg text-gray-200 overflow-hidden font-sans">
    
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
      <main class="flex-1 flex flex-col relative min-w-0 bg-[#101014] transition-all duration-300">
      
        <!-- 聊天内容区 -->
        <div v-if="(selectedCharacter || activeChat?.isGroup) && activeChat" class="flex flex-col h-full relative">
          <!-- 顶部标题栏 -->
          <header class="absolute top-0 left-0 right-0 z-10 flex flex-col bg-gradient-to-b from-[#101014] via-[#101014]/90 to-transparent pointer-events-none">
            <div class="h-14 flex items-center justify-between px-6">
              <div class="pointer-events-auto flex items-center gap-3">
                <template v-if="activeChat.isGroup">
                  <span class="text-purple-400">👥</span>
                  <h2 class="text-lg font-bold text-purple-300 shadow-sm">{{ activeChat.title }}</h2>
                  <span class="text-xs text-gray-500">({{ activeChat.memberIds.length }}个角色)</span>
                  <button 
                    class="ml-1 p-1 text-purple-400 hover:text-white transition-colors" 
                    title="群聊设置"
                    @click="showGroupSettings = true"
                  >
                    ⚙
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
            :get-display-content="versions.getDisplayContent"
            :has-multiple-versions="versions.hasMultipleVersions"
            :get-current-version-index="versions.getCurrentVersionIndex"
            :get-version-count="versions.getVersionCount"
            @edit-message="actions.openEditMessage"
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

    <!-- 设置抽屉 -->
    <SettingsDrawer 
      v-model:show="showSettings" 
      :chat="activeChat" 
      :initial-tab="settingsTab" 
      @open-member-settings="actions.openMemberSettingsEditor"
    />

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
      @save="actions.saveEditedMessage"
      @save-and-send="handleSaveAndSend"
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
    <div class="modal-content chat-modal-width-1200-90">
      <div class="modal-header">
        <h3 class="modal-title">{{ actions.isNewCharacter.value ? '新建角色' : '编辑角色' }}</h3>
        <button class="modal-close" @click="cancelCharacterEdit">×</button>
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
          <div class="flex-[0.66] shrink-0 bg-[#141418] border border-white/10 rounded-2xl p-4 flex flex-col shadow-inner">
            <div class="flex items-center justify-between mb-4 px-1">
              <span class="text-sm font-bold text-gray-400 uppercase tracking-widest flex items-center gap-2">
                <span class="w-2 h-2 rounded-full bg-brand animate-pulse"></span>
                聊天助手
              </span>
              <button class="text-gray-500 hover:text-white transition-colors" @click="assistant.showAssistantSettings.value = true">⋯</button>
            </div>
            <div class="flex-1 overflow-y-auto custom-scrollbar space-y-4 pr-2 mb-4">
              <div v-if="assistant.workspaceAssistantMessages.value.length === 0" class="text-xs text-gray-600 text-center py-12 flex flex-col items-center gap-3">
                <div class="w-12 h-12 rounded-full bg-white/5 flex items-center justify-center text-xl">✨</div>
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
                  <span v-if="assistant.isWorkspaceAssistantGenerating.value" class="animate-spin mr-2">⌛</span>
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
    <div class="modal-content chat-modal-width-500-90">
      <div class="modal-header">
        <h3 class="modal-title">{{ actions.isNewPersona.value ? '新建身份' : '编辑身份' }}</h3>
        <button class="modal-close" @click="actions.showPersonaEditor.value = false">×</button>
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
        <button class="modal-close" @click="actions.cancelSwitchPersona">×</button>
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
        <button class="modal-close" @click="assistant.showAssistantSettings.value = false">×</button>
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
