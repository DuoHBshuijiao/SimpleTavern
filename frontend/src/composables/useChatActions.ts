/**
 * useChatActions - 聊天操作逻辑
 * 
 * 负责消息编辑、角色/Persona 管理、导出等操作
 */
import { ref, computed } from 'vue'
import type { Ref, ComputedRef } from 'vue'
import type { 
  Chat, 
  ChatMessage, 
  CharacterCard, 
  UserPersona, 
  GroupMemberSettings 
} from '../types/models'
import { apiPost, apiPut } from '../api/http'

export interface ChatActionsDeps {
  activeChat: Ref<Chat | null>
  isGenerating: Ref<boolean>
  selectedPersona: ComputedRef<UserPersona | null>
  userName: ComputedRef<string>
  chatsStore: {
    updateMessage: (chatId: string, messageId: string, role: string, content: string) => Promise<void>
    deleteMessage: (chatId: string, messageId: string) => Promise<void>
    load: (chatId: string) => Promise<void>
    updateUserPersonaId: (chatId: string, personaId: string) => Promise<void>
    updateMemberSettings: (chatId: string, memberId: string, settings: GroupMemberSettings) => Promise<void>
  }
  settingsStore: {
    settings: {
      userPersonas?: UserPersona[]
      selectedPersonaId?: string | null
    } | null
    save: (settings: any) => Promise<void>
    load: () => Promise<void>
  }
  charactersStore: {
    list: CharacterCard[]
    create: (card: CharacterCard) => Promise<void>
    update: (id: string, card: CharacterCard) => Promise<void>
    remove: (id: string) => Promise<void>
  }
}

export function useChatActions(deps: ChatActionsDeps) {
  const { 
    activeChat, 
    isGenerating, 
    selectedPersona,
    userName,
    chatsStore, 
    settingsStore, 
    charactersStore 
  } = deps

  // ========== 消息编辑 ==========
  const showMessageEditor = ref(false)
  const editingMessageId = ref<string | null>(null)
  const editingMessageRole = ref<ChatMessage['role']>('assistant')
  const editingMessageContent = ref('')

  function openEditMessage(m: ChatMessage) {
    if (!activeChat.value) return
    if (isGenerating.value) return
    if (m.id.startsWith('local_')) return
    editingMessageId.value = m.id
    editingMessageRole.value = m.role
    editingMessageContent.value = m.content
    showMessageEditor.value = true
  }

  function closeEditMessage() {
    showMessageEditor.value = false
    editingMessageId.value = null
    editingMessageContent.value = ''
  }

  async function saveEditedMessage() {
    if (!activeChat.value) return
    if (!editingMessageId.value) return
    if (isGenerating.value) return
    await chatsStore.updateMessage(
      activeChat.value.id,
      editingMessageId.value,
      editingMessageRole.value,
      editingMessageContent.value,
    )
    closeEditMessage()
  }

  const canSendEditedMessage = computed(() => editingMessageRole.value !== 'assistant')

  async function deleteMessage(m: ChatMessage) {
    if (!activeChat.value) return
    if (isGenerating.value) return
    if (m.id.startsWith('local_')) return
    await chatsStore.deleteMessage(activeChat.value.id, m.id)
  }

  // ========== 角色管理 ==========
  const showCharacterEditor = ref(false)
  const editingCharacter = ref<CharacterCard | null>(null)
  const isNewCharacter = ref(false)
  const showCharacterAvatarCropper = ref(false)

  function newCard(): CharacterCard {
    const now = new Date().toISOString()
    return {
      version: 1,
      id: crypto.randomUUID().replace(/-/g, ''),
      name: '新角色',
      description: '',
      personality: '',
      scenario: '',
      firstMessage: '',
      exampleDialogue: '',
      systemPrompt: '',
      avatar: '',
      createdAt: now,
      updatedAt: now,
    }
  }

  function openCreateCharacter() {
    isNewCharacter.value = true
    editingCharacter.value = newCard()
    showCharacterEditor.value = true
  }

  function openEditCharacter(card: CharacterCard) {
    isNewCharacter.value = false
    editingCharacter.value = JSON.parse(JSON.stringify(card)) as CharacterCard
    showCharacterEditor.value = true
  }

  async function saveCharacter(): Promise<string | null> {
    if (!editingCharacter.value) return null
    if (!editingCharacter.value.name.trim()) editingCharacter.value.name = '未命名角色'
    
    const id = editingCharacter.value.id
    if (isNewCharacter.value) {
      await charactersStore.create(editingCharacter.value)
    } else {
      await charactersStore.update(id, editingCharacter.value)
    }
    
    showCharacterEditor.value = false
    editingCharacter.value = null
    return id
  }

  function cancelCharacterEdit() {
    showCharacterEditor.value = false
    editingCharacter.value = null
  }

  async function deleteCharacter(id: string): Promise<string | null> {
    await charactersStore.remove(id)
    // 返回第一个可用角色ID，用于选中
    return charactersStore.list[0]?.id ?? null
  }

  async function handleCharacterAvatarSave(imageData: string) {
    try {
      const res = await apiPost<{ filename: string }>('/api/avatars', { imageData })
      if (editingCharacter.value) {
        editingCharacter.value.avatar = res.filename
      }
    } catch (e) {
      console.error('Failed to upload avatar:', e)
    }
  }

  function applyAssistantCard(card: any) {
    if (!editingCharacter.value) return
    const current = editingCharacter.value
    editingCharacter.value = {
      ...current,
      name: card.name ?? current.name,
      description: card.description ?? current.description,
      personality: card.personality ?? current.personality,
      scenario: card.scenario ?? current.scenario,
      firstMessage: card.firstMessage ?? current.firstMessage,
      exampleDialogue: card.exampleDialogue ?? current.exampleDialogue,
      systemPrompt: card.systemPrompt ?? current.systemPrompt,
      avatar: card.avatar ?? current.avatar,
    }
  }

  // ========== Persona 管理 ==========
  const showPersonaEditor = ref(false)
  const editingPersona = ref<UserPersona | null>(null)
  const isNewPersona = ref(false)
  const showPersonaAvatarCropper = ref(false)
  const showPersonaSwitchConfirm = ref(false)
  const pendingPersonaId = ref<string | null>(null)

  function newPersona(): UserPersona {
    const now = new Date().toISOString()
    return {
      id: crypto.randomUUID().replace(/-/g, ''),
      name: '新用户',
      description: '',
      avatar: '',
      createdAt: now,
      updatedAt: now,
    }
  }

  function openCreatePersona() {
    isNewPersona.value = true
    editingPersona.value = newPersona()
    showPersonaEditor.value = true
  }

  function openEditPersona(persona: UserPersona) {
    isNewPersona.value = false
    editingPersona.value = JSON.parse(JSON.stringify(persona)) as UserPersona
    showPersonaEditor.value = true
  }

  async function savePersona() {
    if (!editingPersona.value || !settingsStore.settings) return
    if (!editingPersona.value.name.trim()) editingPersona.value.name = '未命名用户'
    
    const personas = [...(settingsStore.settings.userPersonas || [])]
    if (isNewPersona.value) {
      personas.push(editingPersona.value)
    } else {
      const idx = personas.findIndex(p => p.id === editingPersona.value!.id)
      if (idx >= 0) {
        personas[idx] = editingPersona.value
      }
    }
    
    await settingsStore.save({
      ...settingsStore.settings,
      userPersonas: personas,
      selectedPersonaId: editingPersona.value.id,
    })
    
    showPersonaEditor.value = false
    editingPersona.value = null
  }

  async function selectPersona(id: string) {
    if (!settingsStore.settings) return
    if (settingsStore.settings.selectedPersonaId === id && activeChat.value?.userPersonaId === id) return
    
    // 若在现有对话中切换 persona，弹确认框
    if (activeChat.value && (activeChat.value.messages?.length || 0) > 0) {
      pendingPersonaId.value = id
      showPersonaSwitchConfirm.value = true
      return
    }
    
    await settingsStore.save({ ...settingsStore.settings, selectedPersonaId: id })
    if (activeChat.value && activeChat.value.userPersonaId !== id) {
      await chatsStore.updateUserPersonaId(activeChat.value.id, id)
    }
  }

  function cancelSwitchPersona() {
    showPersonaSwitchConfirm.value = false
    pendingPersonaId.value = null
  }

  async function deletePersona(id: string) {
    if (!settingsStore.settings) return
    const personas = (settingsStore.settings.userPersonas || []).filter(p => p.id !== id)
    await settingsStore.save({
      ...settingsStore.settings,
      userPersonas: personas,
      selectedPersonaId: personas[0]?.id ?? null,
    })
  }

  async function handlePersonaAvatarSave(imageData: string) {
    try {
      const res = await apiPost<{ filename: string }>('/api/avatars', { imageData })
      if (editingPersona.value) {
        editingPersona.value.avatar = res.filename
      }
    } catch (e) {
      console.error('Failed to upload avatar:', e)
    }
  }

  /**
   * 固化当前 user 消息的发送者快照
   */
  async function freezeUserMessagesSenderSnapshot() {
    if (!activeChat.value) return
    const chatId = activeChat.value.id
    const oldPersonaId = selectedPersona.value?.id ?? null
    const oldName = selectedPersona.value?.name ?? userName.value
    const oldAvatar = selectedPersona.value?.avatar ?? null

    const targets = (activeChat.value.messages || []).filter(m =>
      m.role === 'user' &&
      !String(m.id).startsWith('local_') &&
      (!m.senderName || !m.senderAvatar || !m.senderPersonaId)
    )

    for (const m of targets) {
      await apiPut(`/api/chats/${chatId}/messages/${m.id}`, {
        role: 'user',
        content: m.content,
        senderPersonaId: oldPersonaId,
        senderName: oldName,
        senderAvatar: oldAvatar,
      })
    }

    if (targets.length > 0) {
      await chatsStore.load(chatId)
    }
  }

  // ========== 导出功能 ==========
  function getDownloadFilename(disposition: string | null, fallback: string): string {
    if (!disposition) return fallback
    const utf8Match = /filename\*\s*=\s*UTF-8''([^;]+)/i.exec(disposition)
    if (utf8Match?.[1]) {
      try {
        return decodeURIComponent(utf8Match[1])
      } catch {
        return utf8Match[1]
      }
    }
    const match = /filename="([^"]+)"/i.exec(disposition)
    if (match?.[1]) return match[1]
    return fallback
  }

  async function exportChat(format: 'txt' | 'json') {
    if (!activeChat.value) return
    const r = await fetch(`/api/chats/${activeChat.value.id}/export?format=${format}`)
    if (!r.ok) {
      alert(await r.text())
      return
    }
    const blob = await r.blob()
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    const fallback = `${activeChat.value.title || '聊天记录'}.${format}`
    link.download = getDownloadFilename(r.headers.get('Content-Disposition'), fallback)
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
  }

  function exportCharacterCard() {
    if (!editingCharacter.value) return
    
    const card = editingCharacter.value
    const lines: string[] = []
    
    lines.push('='.repeat(60))
    lines.push(`角色名称: ${card.name}`)
    lines.push('='.repeat(60))
    lines.push('')
    
    if (card.description) {
      lines.push('【简介】')
      lines.push(card.description)
      lines.push('')
    }
    
    if (card.personality) {
      lines.push('【Personality（性格/外貌）】')
      lines.push(card.personality)
      lines.push('')
    }
    
    if (card.scenario) {
      lines.push('【Scenario（情景/世界观）】')
      lines.push(card.scenario)
      lines.push('')
    }
    
    if (card.systemPrompt) {
      lines.push('【系统提示词】')
      lines.push(card.systemPrompt)
      lines.push('')
    }
    
    if (card.firstMessage) {
      lines.push('【首句】')
      lines.push(card.firstMessage)
      lines.push('')
    }
    
    if (card.exampleDialogue) {
      lines.push('【示例对话】')
      lines.push(card.exampleDialogue)
      lines.push('')
    }
    
    lines.push('='.repeat(60))
    lines.push(`创建时间: ${card.createdAt ? new Date(card.createdAt).toLocaleString('zh-CN') : '未知'}`)
    if (card.updatedAt && card.updatedAt !== card.createdAt) {
      lines.push(`更新时间: ${new Date(card.updatedAt).toLocaleString('zh-CN')}`)
    }
    lines.push('='.repeat(60))
    
    const content = lines.join('\n')
    const blob = new Blob([content], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `${card.name || '角色卡'}.txt`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
  }

  // ========== 成员设置编辑 ==========
  const editingMemberId = ref<string | null>(null)
  const editingMemberSettings = ref<GroupMemberSettings>({
    model: null,
    presetId: null,
    temperature: null,
    top_p: null,
    probability: 1.0,
    includePersonality: true,
    includeScenario: true,
  })

  function openMemberSettingsEditor(memberId: string) {
    editingMemberId.value = memberId
    const settings = activeChat.value?.memberSettings?.[memberId] ?? {
      model: null,
      presetId: null,
      temperature: null,
      top_p: null,
      probability: 1.0,
      includePersonality: true,
      includeScenario: true,
    }
    editingMemberSettings.value = { ...settings }
  }

  function closeMemberSettingsEditor() {
    editingMemberId.value = null
  }

  async function saveMemberSettings() {
    if (!activeChat.value || !editingMemberId.value) return
    await chatsStore.updateMemberSettings(
      activeChat.value.id,
      editingMemberId.value,
      editingMemberSettings.value
    )
    closeMemberSettingsEditor()
  }

  return {
    // 消息编辑
    showMessageEditor,
    editingMessageId,
    editingMessageRole,
    editingMessageContent,
    canSendEditedMessage,
    openEditMessage,
    closeEditMessage,
    saveEditedMessage,
    deleteMessage,

    // 角色管理
    showCharacterEditor,
    editingCharacter,
    isNewCharacter,
    showCharacterAvatarCropper,
    newCard,
    openCreateCharacter,
    openEditCharacter,
    saveCharacter,
    cancelCharacterEdit,
    deleteCharacter,
    handleCharacterAvatarSave,
    applyAssistantCard,

    // Persona 管理
    showPersonaEditor,
    editingPersona,
    isNewPersona,
    showPersonaAvatarCropper,
    showPersonaSwitchConfirm,
    pendingPersonaId,
    newPersona,
    openCreatePersona,
    openEditPersona,
    savePersona,
    selectPersona,
    cancelSwitchPersona,
    deletePersona,
    handlePersonaAvatarSave,
    freezeUserMessagesSenderSnapshot,

    // 导出
    exportChat,
    exportCharacterCard,

    // 成员设置
    editingMemberId,
    editingMemberSettings,
    openMemberSettingsEditor,
    closeMemberSettingsEditor,
    saveMemberSettings,
  }
}

export type UseChatActions = ReturnType<typeof useChatActions>
