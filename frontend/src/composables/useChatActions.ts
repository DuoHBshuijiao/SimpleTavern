/**
 * useChatActions - 聊天操作逻辑Composable
 *
 * 负责消息编辑、角色/Persona管理、导出等操作。
 *
 * 主要功能：
 *    - 消息编辑：打开、保存、删除消息
 *    - 角色管理：创建、编辑、删除角色卡片，处理头像上传
 *    - Persona管理：创建、编辑、删除用户身份，处理身份切换
 *    - 导出功能：导出聊天记录和角色卡片
 *    - 成员设置：编辑群聊成员的个性化设置
 *
 * 主要函数：
 *    - openEditMessage: 打开消息编辑
 *    - saveEditedMessage: 保存编辑的消息
 *    - deleteMessage: 删除消息
 *    - openCreateCharacter: 打开创建角色
 *    - openEditCharacter: 打开编辑角色
 *    - saveCharacter: 保存角色
 *    - deleteCharacter: 删除角色
 *    - handleCharacterAvatarSave: 处理角色头像保存
 *    - applyAssistantCard: 应用助手生成的角色卡
 *    - openCreatePersona: 打开创建身份
 *    - openEditPersona: 打开编辑身份
 *    - savePersona: 保存身份
 *    - selectPersona: 选择身份
 *    - deletePersona: 删除身份
 *    - freezeUserMessagesSenderSnapshot: 固化用户消息发送者快照
 *    - exportChat: 导出聊天记录
 *    - exportCharacterCard: 导出角色卡片
 *    - openMemberSettingsEditor: 打开成员设置编辑
 *    - saveMemberSettings: 保存成员设置
 *
 * 文件关系：
 *    - 被导入：被composables/index.ts导出，被views/ChatPage.vue使用
 *    - 导入：导入vue的ref和computed、types/models.ts的类型、api/http.ts的HTTP函数
 *    - 依赖：依赖vue、stores/chats.ts、stores/settings.ts、stores/characters.ts（通过参数传入）
 *    - 位置：Composables层，提供聊天操作逻辑
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

  /**
   * 打开消息编辑
   *
   * 打开消息编辑弹窗，加载消息内容到编辑状态。
   * 如果正在生成中或消息是本地消息，则不执行。
   *
   * @param {ChatMessage} m - 要编辑的消息（来自types/models.ts）
   */
  function openEditMessage(m: ChatMessage) {
    if (!activeChat.value) return
    if (isGenerating.value) return
    if (m.id.startsWith('local_')) return
    editingMessageId.value = m.id
    editingMessageRole.value = m.role
    editingMessageContent.value = m.content
    showMessageEditor.value = true
  }

  /**
   * 关闭消息编辑
   *
   * 关闭消息编辑弹窗，清空编辑状态。
   */
  function closeEditMessage() {
    showMessageEditor.value = false
    editingMessageId.value = null
    editingMessageContent.value = ''
  }

  /**
   * 保存编辑的消息
   *
   * 将编辑后的消息内容保存到服务器。
   * 使用chatsStore.updateMessage（来自stores/chats.ts）更新消息。
   *
   * @returns {Promise<void>} 完成时返回
   */
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

  /**
   * 删除消息
   *
   * 删除指定的消息。
   * 使用chatsStore.deleteMessage（来自stores/chats.ts）删除消息。
   * 如果正在生成中或消息是本地消息，则不执行。
   *
   * @param {ChatMessage} m - 要删除的消息（来自types/models.ts）
   * @returns {Promise<void>} 完成时返回
   */
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

  /**
   * 创建新角色卡片
   *
   * 创建一个新的角色卡片对象，使用默认值。
   *
   * @returns {CharacterCard} 新角色卡片（来自types/models.ts）
   */
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

  /**
   * 打开创建角色
   *
   * 打开角色编辑弹窗，设置为新建模式。
   */
  function openCreateCharacter() {
    isNewCharacter.value = true
    editingCharacter.value = newCard()
    showCharacterEditor.value = true
  }

  /**
   * 打开编辑角色
   *
   * 打开角色编辑弹窗，设置为编辑模式，加载角色数据。
   *
   * @param {CharacterCard} card - 要编辑的角色卡片（来自types/models.ts）
   */
  function openEditCharacter(card: CharacterCard) {
    isNewCharacter.value = false
    editingCharacter.value = JSON.parse(JSON.stringify(card)) as CharacterCard
    showCharacterEditor.value = true
  }

  /**
   * 保存角色
   *
   * 保存角色卡片到服务器。
   * 使用charactersStore.create或update（来自stores/characters.ts）保存。
   * 如果名称为空，则设置为"未命名角色"。
   *
   * @returns {Promise<string | null>} 保存后的角色ID，失败返回null
   */
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

  /**
   * 取消角色编辑
   *
   * 关闭角色编辑弹窗，清空编辑状态。
   */
  function cancelCharacterEdit() {
    showCharacterEditor.value = false
    editingCharacter.value = null
  }

  /**
   * 删除角色
   *
   * 删除指定的角色卡片。
   * 使用charactersStore.remove（来自stores/characters.ts）删除。
   *
   * @param {string} id - 角色ID
   * @returns {Promise<string | null>} 第一个可用角色ID，用于选中；如果没有则返回null
   */
  async function deleteCharacter(id: string): Promise<string | null> {
    await charactersStore.remove(id)
    // 返回第一个可用角色ID，用于选中
    return charactersStore.list[0]?.id ?? null
  }

  /**
   * 处理角色头像保存
   *
   * 上传角色头像到服务器。
   * 使用apiPost函数（来自api/http.ts）发送POST请求到/api/avatars。
   * 上传成功后更新编辑中的角色头像字段。
   *
   * @param {string} imageData - base64编码的图片数据
   * @returns {Promise<void>} 完成时返回
   */
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

  /**
   * 应用助手生成的角色卡
   *
   * 将助手生成的角色卡数据应用到当前编辑的角色卡片中。
   * 只更新有值的字段，保留原有字段。
   *
   * @param {any} card - 助手生成的角色卡数据
   */
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

  /**
   * 创建新用户身份
   *
   * 创建一个新的用户身份对象，使用默认值。
   *
   * @returns {UserPersona} 新用户身份（来自types/models.ts）
   */
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

  /**
   * 打开创建身份
   *
   * 打开身份编辑弹窗，设置为新建模式。
   */
  function openCreatePersona() {
    isNewPersona.value = true
    editingPersona.value = newPersona()
    showPersonaEditor.value = true
  }

  /**
   * 打开编辑身份
   *
   * 打开身份编辑弹窗，设置为编辑模式，加载身份数据。
   *
   * @param {UserPersona} persona - 要编辑的用户身份（来自types/models.ts）
   */
  function openEditPersona(persona: UserPersona) {
    isNewPersona.value = false
    editingPersona.value = JSON.parse(JSON.stringify(persona)) as UserPersona
    showPersonaEditor.value = true
  }

  /**
   * 保存身份
   *
   * 保存用户身份到设置中。
   * 使用settingsStore.save（来自stores/settings.ts）保存。
   * 如果名称为空，则设置为"未命名用户"。
   * 保存后自动设置为选中身份。
   *
   * @returns {Promise<void>} 完成时返回
   */
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

  /**
   * 选择身份
   *
   * 切换选中的用户身份。
   * 如果在现有对话中切换，会弹出确认框（新建会话或继续对话）。
   * 使用settingsStore.save（来自stores/settings.ts）保存选中身份。
   *
   * @param {string} id - 身份ID
   * @returns {Promise<void>} 完成时返回
   */
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

  /**
   * 取消切换身份
   *
   * 关闭身份切换确认弹窗，清空待切换的身份ID。
   */
  function cancelSwitchPersona() {
    showPersonaSwitchConfirm.value = false
    pendingPersonaId.value = null
  }

  /**
   * 删除身份
   *
   * 删除指定的用户身份。
   * 使用settingsStore.save（来自stores/settings.ts）保存更新后的身份列表。
   * 如果删除的是当前选中身份，则选中第一个可用身份。
   *
   * @param {string} id - 身份ID
   * @returns {Promise<void>} 完成时返回
   */
  async function deletePersona(id: string) {
    if (!settingsStore.settings) return
    const personas = (settingsStore.settings.userPersonas || []).filter(p => p.id !== id)
    await settingsStore.save({
      ...settingsStore.settings,
      userPersonas: personas,
      selectedPersonaId: personas[0]?.id ?? null,
    })
  }

  /**
   * 处理身份头像保存
   *
   * 上传用户身份头像到服务器。
   * 使用apiPost函数（来自api/http.ts）发送POST请求到/api/avatars。
   * 上传成功后更新编辑中的身份头像字段。
   *
   * @param {string} imageData - base64编码的图片数据
   * @returns {Promise<void>} 完成时返回
   */
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
   * 固化当前user消息的发送者快照
   *
   * 当切换用户身份时，为历史user消息添加发送者快照（senderPersonaId、senderName、senderAvatar），
   * 确保历史消息仍显示原身份信息。
   * 使用apiPut函数（来自api/http.ts）更新每条消息。
   *
   * @returns {Promise<void>} 完成时返回
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
  /**
   * 获取下载文件名
   *
   * 从Content-Disposition响应头中解析文件名。
   * 支持UTF-8编码的文件名（filename*=UTF-8''格式）和普通格式（filename="..."格式）。
   *
   * @param {string | null} disposition - Content-Disposition响应头
   * @param {string} fallback - 如果解析失败则使用的默认文件名
   * @returns {string} 文件名
   */
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

  /**
   * 导出聊天记录
   *
   * 导出当前聊天会话为TXT或JSON格式。
   * 发送GET请求到/api/chats/{chatId}/export?format={format}。
   * 下载返回的文件。
   *
   * @param {'txt' | 'json'} format - 导出格式
   * @returns {Promise<void>} 完成时返回
   */
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

  /**
   * 导出角色卡片
   *
   * 将当前编辑的角色卡片导出为TXT格式的文本文件。
   * 包含角色的所有信息（名称、简介、性格、场景等）。
   *
   * @returns {void}
   */
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

  /**
   * 打开成员设置编辑
   *
   * 打开群聊成员设置编辑弹窗，加载成员的当前设置。
   *
   * @param {string} memberId - 成员角色ID
   */
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

  /**
   * 关闭成员设置编辑
   *
   * 关闭成员设置编辑弹窗，清空编辑状态。
   */
  function closeMemberSettingsEditor() {
    editingMemberId.value = null
  }

  /**
   * 保存成员设置
   *
   * 保存群聊成员的个性化设置到服务器。
   * 使用chatsStore.updateMemberSettings（来自stores/chats.ts）更新设置。
   *
   * @returns {Promise<void>} 完成时返回
   */
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
