<script setup lang="ts">
import { computed, onMounted, ref, watch, nextTick } from 'vue'
import MarkdownIt from 'markdown-it'

import { useCharactersStore, useChatsStore, useSettingsStore } from '../stores'
import type { CharacterCard, ChatMessage, UserPersona, GroupMemberSettings, Chat } from '../types/models'
import SettingsDrawer from '../components/SettingsDrawer.vue'
import AvatarCropper from '../components/AvatarCropper.vue'
import ModernAvatar from '../components/ModernAvatar.vue'
import ModernSelect from '../components/ModernSelect.vue'
import { postAndConsumeSse } from '../api/sse'
import { apiPost, apiPut } from '../api/http'

import {
  NButton,
  NForm,
  NFormItem,
  NInput,
  NInputNumber,
  NModal,
  NPopconfirm,
  NSpace,
} from 'naive-ui'

const settings = useSettingsStore()
const characters = useCharactersStore()
const chats = useChatsStore()

const selectedCharacterId = ref<string | null>(null)
const draftMessage = ref('')
const showSettings = ref(false)
const isGenerating = ref(false)
const streamError = ref<string | null>(null)
const sidebarCollapsed = ref(false)
const editingChatId = ref<string | null>(null)
const editingTitle = ref('')
const messagesScrollRef = ref<HTMLElement | null>(null)
let aborter: AbortController | null = null

// 角色编辑相关
const showCharacterEditor = ref(false)
const editingCharacter = ref<CharacterCard | null>(null)
const isNewCharacter = ref(false)
const showCharacterAvatarCropper = ref(false)

// Persona 相关
const showPersonaEditor = ref(false)
const editingPersona = ref<UserPersona | null>(null)
const isNewPersona = ref(false)
const showPersonaAvatarCropper = ref(false)

// Persona 切换确认
const showPersonaSwitchConfirm = ref(false)
const pendingPersonaId = ref<string | null>(null)

// 群聊相关
const showGroupCreator = ref(false)
const selectedMemberIds = ref<string[]>([])
const groupTitle = ref('')
const showMemberManager = ref(false)
// 新建单聊弹窗（沿用群聊弹窗风格）
const showChatCreator = ref(false)
const chatTitle = ref('')
const chatPureAiMode = ref(false)

// 群聊创建附加选项
const groupPureAiMode = ref(false)
const groupFirstMessageEnabled = ref(true)
const groupFirstMessageCharacterId = ref<string | null>(null)
const groupMemberInclusions = ref<Record<string, { includePersonality: boolean; includeScenario: boolean }>>({})

const groupFirstMessageOptions = computed(() => {
  const opts = selectedMemberIds.value.map(id => ({
    label: getCharacterById(id)?.name || id,
    value: id
  }))
  return [
    { label: '（未选择）', value: '' },
    ...opts
  ]
})

// 成员设置编辑
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

// 插话相关
const showInterjectPanel = ref(false)  // 是否显示插话面板
const isInterjecting = ref(false)  // 是否正在插话
const interjectPanelManuallyHidden = ref(false)

// 管理群成员：拖拽排序
const memberOrderDraft = ref<string[]>([])
const draggingMemberIdx = ref<number | null>(null)

// 快速模型切换 (聚合所有预设 + 最近使用置顶)
const chatModelOptions = computed(() => {
  const options: any[] = []
  if (!settings.settings) return []

  // 1. 最近使用 (Top Priority)
  const recentModels = settings.settings.llm.usedModels || []
  if (recentModels.length > 0) {
       options.push({
          label: '最近使用',
          options: recentModels.map(m => {
              // 尝试找到它所属的 preset
              let preset = null
              if (settings.settings?.apiPresets) {
                  preset = settings.settings.apiPresets.find(p => p.models.includes(m))
              }
              return { 
                  label: m, 
                  value: m, 
                  presetId: preset ? preset.id : null
              }
          })
      })
  }

  // 2. Presets
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
  
  // 3. Global / Default
  // 只有当没有 preset 且 global candidates 有值时才显示，作为 fallback
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

// 处理模型选择
async function handleModelSelect(option: any) {
  if (!chats.activeChat) return
  const overrides = { ...chats.activeChat.overrides }
  overrides.params = { ...overrides.params, model: option.value }
  
  if (option.presetId) {
      overrides.presetId = option.presetId
  } else {
      // 如果手动输入或选择了全局模型，尝试反查预设
      const found = settings.settings?.apiPresets.find(p => p.models.includes(option.value))
      if (found) overrides.presetId = found.id
      else overrides.presetId = null
  }
  
  await chats.updateOverrides(chats.activeChat.id, overrides)
}

function scrollToBottom() {
  nextTick(() => {
    if (messagesScrollRef.value) {
      messagesScrollRef.value.scrollTop = messagesScrollRef.value.scrollHeight
    }
  })
}

onMounted(async () => {
  if (!settings.settings) await settings.load()
  await characters.loadAll()
  await chats.loadGroupList()

  if (!selectedCharacterId.value) {
    const first = characters.list[0]
    if (first) selectedCharacterId.value = first.id
  }
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

const selectedCharacter = computed(() => {
  if (!selectedCharacterId.value) return null
  return characters.list.find((c) => c.id === selectedCharacterId.value) ?? null
})

const activeChat = computed(() => chats.activeChat)

const effectivePureAiMode = computed(() => {
  const chatOverride = activeChat.value?.overrides?.pureAiMode
  if (chatOverride !== null && chatOverride !== undefined) return !!chatOverride
  return !!settings.settings?.pureAiMode
})

const canInterject = computed(() => {
  return !!activeChat.value?.isGroup &&
    !isGenerating.value &&
    !isInterjecting.value &&
    !interjectPanelManuallyHidden.value &&
    (showInterjectPanel.value || effectivePureAiMode.value)
})

const md = new MarkdownIt({
  html: false, // 禁止原始 HTML，避免模型输出导致 XSS
  linkify: true,
  breaks: true,
})

function normalizeMarkdownInput(text: string) {
  // markdown-it 会把形如 "[xxx]: ..." 的行识别为“引用链接定义”，该行不会被渲染。
  // 群聊里模型常输出 "[角色名]: 内容" 作为说话人前缀，这会导致气泡显示为空。
  // 这里把 ":" 换成全角 "：" 来打断该语法，但保持可读性。
  return (text ?? '').replace(/(^|\n)\[([^\]\n]+)\]:(\s*)/g, (_m, p1, name, sp) => `${p1}[${name}]：${sp}`)
}

function renderMarkdown(text: string) {
  return md.render(normalizeMarkdownInput(text))
}

// 消息编辑相关
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
  await chats.updateMessage(
    activeChat.value.id,
    editingMessageId.value,
    editingMessageRole.value,
    editingMessageContent.value,
  )
  closeEditMessage()
}

async function deleteMessage(m: ChatMessage) {
  if (!activeChat.value) return
  if (isGenerating.value) return
  if (m.id.startsWith('local_')) return
  await chats.deleteMessage(activeChat.value.id, m.id)
}

const effectiveSelectedPersonaId = computed(() => {
  // 纯 AI 模式下：Persona 视为未选中（不修改全局 settings，只在当前会话 UI 层遮罩）
  if (effectivePureAiMode.value) return null
  return settings.settings?.selectedPersonaId ?? null
})

// 获取选中的 Persona
const selectedPersona = computed(() => {
  if (!effectiveSelectedPersonaId.value || !settings.settings?.userPersonas) return null
  return settings.settings.userPersonas.find(p => p.id === effectiveSelectedPersonaId.value) ?? null
})

// 头像URL
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

function getMessageLabel(m: ChatMessage) {
  if (m.role === 'user') return (m.senderName || userName.value)
  if (m.role === 'assistant') {
    // 群聊时根据 characterId 获取角色名称
    if (m.characterId) {
      const char = getCharacterById(m.characterId)
      return char?.name || 'AI'
    }
    return selectedCharacter.value?.name || 'AI'
  }
  return '系统'
}

function getMessageAvatar(m: ChatMessage) {
  if (m.role === 'user') {
    if (m.senderAvatar) return `/api/avatars/${m.senderAvatar}`
    return userAvatarUrl.value
  }
  if (m.role === 'assistant') {
    // 群聊时根据 characterId 获取角色头像
    if (m.characterId) {
      const char = getCharacterById(m.characterId)
      return char?.avatar ? `/api/avatars/${char.avatar}` : null
    }
    return characterAvatarUrl.value
  }
  return null
}

async function createChat() {
  // 改为弹出创建设置窗口
  if (!selectedCharacterId.value) return
  chatTitle.value = ''
  chatPureAiMode.value = false
  showChatCreator.value = true
}

async function deleteChat(chatId: string) {
  await chats.remove(chatId)
}

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

// 角色管理
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

async function saveCharacter() {
  if (!editingCharacter.value) return
  if (!editingCharacter.value.name.trim()) editingCharacter.value.name = '未命名角色'
  if (isNewCharacter.value) {
    await characters.create(editingCharacter.value)
    selectedCharacterId.value = editingCharacter.value.id
  } else {
    await characters.update(editingCharacter.value.id, editingCharacter.value)
  }
  showCharacterEditor.value = false
  editingCharacter.value = null
}

async function deleteCharacter(id: string) {
  await characters.remove(id)
  if (selectedCharacterId.value === id) {
    selectedCharacterId.value = characters.list[0]?.id ?? null
  }
}

// 导出角色卡为纯文本
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

// Persona 管理
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
  if (!editingPersona.value || !settings.settings) return
  if (!editingPersona.value.name.trim()) editingPersona.value.name = '未命名用户'
  
  const personas = [...(settings.settings.userPersonas || [])]
  if (isNewPersona.value) {
    personas.push(editingPersona.value)
  } else {
    const idx = personas.findIndex(p => p.id === editingPersona.value!.id)
    if (idx >= 0) {
      personas[idx] = editingPersona.value
    }
  }
  
  await settings.save({
    ...settings.settings,
    userPersonas: personas,
    selectedPersonaId: editingPersona.value.id,
  })
  
  showPersonaEditor.value = false
  editingPersona.value = null
}

async function selectPersona(id: string) {
  if (!settings.settings) return
  if (settings.settings.selectedPersonaId === id) return
  // 若在现有对话中切换 persona，弹确认框（新建会话 / 继续对话）
  if (activeChat.value && (activeChat.value.messages?.length || 0) > 0) {
    pendingPersonaId.value = id
    showPersonaSwitchConfirm.value = true
    return
  }
  await settings.save({ ...settings.settings, selectedPersonaId: id })
}

async function confirmSwitchPersonaNewSession() {
  if (!settings.settings) return
  if (!pendingPersonaId.value) return
  const targetId = pendingPersonaId.value
  showPersonaSwitchConfirm.value = false
  pendingPersonaId.value = null

  await settings.save({ ...settings.settings, selectedPersonaId: targetId })
  if (!activeChat.value) return

  const title = `${activeChat.value.title}（新建会话）`
  const pure = effectivePureAiMode.value
  if (activeChat.value.isGroup) {
    await chats.createGroup(
      activeChat.value.characterId,
      [...activeChat.value.memberIds],
      title,
      pure,
      null,
      activeChat.value.memberSettings || null,
    )
  } else {
    await chats.create(activeChat.value.characterId, title, pure)
  }
  scrollToBottom()
}

async function freezeCurrentUserMessagesSenderSnapshot() {
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
    await chats.load(chatId)
  }
}

async function confirmSwitchPersonaContinue() {
  if (!settings.settings) return
  if (!pendingPersonaId.value) return
  const targetId = pendingPersonaId.value
  showPersonaSwitchConfirm.value = false
  pendingPersonaId.value = null
  // 先固化“切换前”的历史 user 消息发送者信息，避免切换后显示被新 persona 覆盖
  await freezeCurrentUserMessagesSenderSnapshot()
  await settings.save({ ...settings.settings, selectedPersonaId: targetId })
}

function cancelSwitchPersona() {
  showPersonaSwitchConfirm.value = false
  pendingPersonaId.value = null
}

async function deletePersona(id: string) {
  if (!settings.settings) return
  const personas = (settings.settings.userPersonas || []).filter(p => p.id !== id)
  await settings.save({
    ...settings.settings,
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

// ========== 群聊相关 ==========
function openGroupCreator() {
  selectedMemberIds.value = []
  groupTitle.value = ''
  groupPureAiMode.value = false
  groupFirstMessageEnabled.value = true
  groupFirstMessageCharacterId.value = null
  groupMemberInclusions.value = {}
  showGroupCreator.value = true
}

function toggleMemberSelection(characterId: string) {
  const idx = selectedMemberIds.value.indexOf(characterId)
  if (idx >= 0) {
    selectedMemberIds.value.splice(idx, 1)
    delete groupMemberInclusions.value[characterId]
    if (groupFirstMessageCharacterId.value === characterId) {
      groupFirstMessageCharacterId.value = selectedMemberIds.value[0] ?? null
    }
  } else {
    selectedMemberIds.value.push(characterId)
    if (!groupMemberInclusions.value[characterId]) {
      groupMemberInclusions.value[characterId] = { includePersonality: true, includeScenario: true }
    }
    if (!groupFirstMessageCharacterId.value) {
      groupFirstMessageCharacterId.value = characterId
    }
  }
}

async function createGroupChat() {
  if (selectedMemberIds.value.length < 2) {
    return // 群聊至少需要2个角色
  }
  const firstMember = selectedMemberIds.value[0]
  if (!firstMember) return

  // 组装创建时 memberSettings（包含 prompt 插入字段开关）
  const memberSettings: Record<string, GroupMemberSettings> = {}
  for (const id of selectedMemberIds.value) {
    const inc = groupMemberInclusions.value[id] ?? { includePersonality: true, includeScenario: true }
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

  const firstMsgId = groupFirstMessageEnabled.value ? groupFirstMessageCharacterId.value : null
  await chats.createGroup(
    firstMember,
    selectedMemberIds.value,
    groupTitle.value || '新群聊',
    groupPureAiMode.value,
    firstMsgId,
    memberSettings,
  )
  showGroupCreator.value = false
  selectedMemberIds.value = []
  groupTitle.value = ''
}

async function confirmCreateChat() {
  if (!selectedCharacterId.value) return
  await chats.create(selectedCharacterId.value, chatTitle.value.trim() || undefined, chatPureAiMode.value)
  showChatCreator.value = false
  chatTitle.value = ''
}

async function selectGroupChat(chat: Chat) {
  await chats.load(chat.id)
  // 群聊时不切换选中的角色
  scrollToBottom()
}

// 获取角色信息 by ID
function getCharacterById(id: string) {
  return characters.list.find(c => c.id === id) ?? null
}

function getChatAvatars(chat: Chat) {
  const avatars: { src: string | null; name: string }[] = []
  
  const chatPure = (chat.overrides?.pureAiMode ?? settings.settings?.pureAiMode) === true

  // 1. User（非纯 AI 模式才展示）
  if (!chatPure) {
    const seen = new Set<string>()
    // 优先使用消息里固化的 sender 快照（支持“切换身份后历史消息不变 + 头像追加”）
    for (const m of (chat.messages || [])) {
      if (m.role !== 'user') continue
      const key = (m.senderPersonaId || '') + '|' + (m.senderAvatar || '') + '|' + (m.senderName || '')
      if (seen.has(key)) continue
      seen.add(key)
      avatars.push({
        src: m.senderAvatar ? `/api/avatars/${m.senderAvatar}` : null,
        name: m.senderName || '你',
      })
    }
    // 若还没有任何 user 消息（新会话），用当前选择作为占位
    if (avatars.length === 0) {
      if (userAvatarUrl.value) avatars.push({ src: userAvatarUrl.value, name: userName.value })
      else avatars.push({ src: null, name: '你' })
    }
  }

  // 2. Members
  if (chat.isGroup) {
    chat.memberIds.forEach(id => {
       const char = getCharacterById(id)
       if (char) avatars.push({ src: char.avatar ? `/api/avatars/${char.avatar}` : null, name: char.name })
    })
  } else {
     const char = getCharacterById(chat.characterId)
     if (char) avatars.push({ src: char.avatar ? `/api/avatars/${char.avatar}` : null, name: char.name })
  }
  return avatars
}

// 群成员角色列表
const groupMembers = computed(() => {
  if (!activeChat.value?.isGroup) return []
  return activeChat.value.memberIds
    .map(id => getCharacterById(id))
    .filter(c => c !== null)
})

const managerMemberIds = computed(() => {
  if (!activeChat.value?.isGroup) return []
  if (showMemberManager.value && memberOrderDraft.value.length > 0) return memberOrderDraft.value
  return activeChat.value.memberIds
})

const groupMembersInManager = computed(() => {
  if (!activeChat.value?.isGroup) return []
  return managerMemberIds.value.map(id => getCharacterById(id)).filter(c => c !== null)
})

// 打开成员管理
function openMemberManager() {
  // 初始化排序草稿（用于拖拽）
  if (activeChat.value?.isGroup) {
    memberOrderDraft.value = [...activeChat.value.memberIds]
  } else {
    memberOrderDraft.value = []
  }
  draggingMemberIdx.value = null
  showMemberManager.value = true
}

function onDragStartMember(idx: number) {
  draggingMemberIdx.value = idx
}

function onDropMember(idx: number) {
  const from = draggingMemberIdx.value
  if (from === null) return
  if (from === idx) return
  const arr = [...memberOrderDraft.value]
  const [moved] = arr.splice(from, 1)
  arr.splice(idx, 0, moved!)
  memberOrderDraft.value = arr
  draggingMemberIdx.value = null
}

async function finishMemberManager() {
  if (activeChat.value?.isGroup) {
    const cur = activeChat.value.memberIds
    const next = memberOrderDraft.value
    if (next.length === cur.length && next.some((v, i) => v !== cur[i])) {
      await chats.updateMemberOrder(activeChat.value.id, next)
    }
  }
  showMemberManager.value = false
}

// 添加成员到群聊
async function addMemberToGroup(characterId: string) {
  if (!activeChat.value) return
  await chats.addMember(activeChat.value.id, characterId)
}

// 从群聊移除成员
async function removeMemberFromGroup(characterId: string) {
  if (!activeChat.value) return
  await chats.removeMember(activeChat.value.id, characterId)
}

// 非群成员的角色列表（可添加）
const availableMembers = computed(() => {
  if (!activeChat.value?.isGroup) return []
  return characters.list.filter(c => !activeChat.value?.memberIds.includes(c.id))
})

// 更新群聊延迟时间
async function updateGroupDelay(delay: number | null) {
  if (!activeChat.value || delay === null) return
  await chats.updateGroupDelay(activeChat.value.id, delay)
}

// ========== 成员设置管理 ==========
function getMemberSettings(memberId: string): GroupMemberSettings {
  return activeChat.value?.memberSettings?.[memberId] ?? {
    model: null,
    presetId: null,
    temperature: null,
    top_p: null,
    probability: 1.0,
    includePersonality: true,
    includeScenario: true,
  }
}

function openMemberSettingsEditor(memberId: string) {
  editingMemberId.value = memberId
  const settings = getMemberSettings(memberId)
  editingMemberSettings.value = { ...settings }
}

function closeMemberSettingsEditor() {
  editingMemberId.value = null
}

async function saveMemberSettings() {
  if (!activeChat.value || !editingMemberId.value) return
  await chats.updateMemberSettings(
    activeChat.value.id,
    editingMemberId.value,
    editingMemberSettings.value
  )
  closeMemberSettingsEditor()
}

// ========== 插话功能 ==========
async function triggerInterject(characterId: string) {
  if (!activeChat.value || isGenerating.value || isInterjecting.value) return
  
  const chatId = activeChat.value.id
  isInterjecting.value = true
  streamError.value = null
  aborter?.abort()
  aborter = new AbortController()
  
  const useStream = settings.settings?.streamEnabled !== false
  
  // 创建本地临时消息
  const localAssistantId = `local_interject_${Date.now()}`
  const localMsg = { 
    version: 1, 
    id: localAssistantId, 
    role: 'assistant' as const, 
    content: '', 
    characterId,
    ts: new Date().toISOString() 
  }
  // activeChat.value.messages.push(localMsg)
  chats.addLocalMessage(localMsg)
  // const msgIndex = activeChat.value.messages.length - 1
  scrollToBottom()
  
  try {
    if (useStream) {
      await postAndConsumeSse(
        '/api/generate/interject',
        { chatId, characterId },
        (evt) => {
          if (evt.event === 'delta') {
            const t = evt.data?.text
            if (typeof t === 'string') {
              chats.appendLocalMessageContent(localAssistantId, t)
              scrollToBottom()
            }
          } else if (evt.event === 'error') {
            streamError.value = String(evt.data?.message ?? 'unknown error')
          }
        },
        aborter.signal,
      )
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
        // 非流式：一次性填充本地临时消息
        chats.appendLocalMessageContent(localAssistantId, res.content || '')
        scrollToBottom()
      } else {
        streamError.value = res.error || 'unknown error'
      }
    }
  } catch (e: any) {
    streamError.value = e?.message ?? String(e)
  } finally {
    isInterjecting.value = false
    await chats.load(chatId)
  }
}

// 群聊暂停/继续相关状态
const isPaused = ref(false)
const pendingMembers = ref<string[]>([])  // 暂停时剩余待发言的成员
const showContinueButton = ref(false)  // 是否显示"继续轮次"按钮

// 当前正在发言的角色索引（群聊用）
const currentSpeakerIndex = ref<number>(-1)

// 延迟函数
function delay(ms: number) {
  return new Promise(resolve => setTimeout(resolve, ms))
}

// 暂停群聊
function pauseGroupChat() {
  isPaused.value = true
}

// 继续群聊轮次
async function continueGroupChat() {
  if (!activeChat.value || pendingMembers.value.length === 0) return
  
  showContinueButton.value = false
  isPaused.value = false
  isGenerating.value = true
  
  const chatId = activeChat.value.id
  const useStream = settings.settings?.streamEnabled !== false
  const groupDelay = activeChat.value.groupDelay || 1500
  
  try {
    await runGroupGeneration(chatId, pendingMembers.value, useStream, groupDelay, 0)
  } catch (e: any) {
    streamError.value = e?.message ?? String(e)
  } finally {
    isGenerating.value = false
    currentSpeakerIndex.value = -1
    pendingMembers.value = []
    await chats.load(chatId)
    await settings.load()
  }
}

// 群聊生成核心逻辑（可被暂停）
async function runGroupGeneration(
  chatId: string, 
  memberIds: string[], 
  useStream: boolean, 
  groupDelay: number,
  startIndex: number
) {
  for (let i = startIndex; i < memberIds.length; i++) {
    const characterId = memberIds[i]
    currentSpeakerIndex.value = i
    
    // 添加角色间延迟（第一个角色不需要）
    if (i > startIndex) {
      await delay(groupDelay)
    }
    
    // 检查是否暂停
    if (isPaused.value) {
      // 保存剩余待发言的成员
      pendingMembers.value = memberIds.slice(i)
      showContinueButton.value = true
      isGenerating.value = false
      currentSpeakerIndex.value = -1
      return
    }
    
    // 确保 activeChat 仍然有效
    if (!activeChat.value) break
    
    // 创建本地临时消息
    const localAssistantId = `local_assistant_${Date.now()}_${i}`
    const localMsg = { 
      version: 1, 
      id: localAssistantId, 
      role: 'assistant' as const, 
      content: '', 
      characterId,
      ts: new Date().toISOString() 
    }
    // activeChat.value.messages.push(localMsg)
    chats.addLocalMessage(localMsg)
    
    // 保存消息索引，而不是对象引用（避免响应式引用丢失问题）
    const msgIndex = activeChat.value.messages.length - 1
    scrollToBottom()
    
    // 调用群聊生成接口
    if (useStream) {
      await postAndConsumeSse(
        '/api/generate/group',
        { chatId, characterId },
        (evt) => {
          if (evt.event === 'delta') {
            const t = evt.data?.text
            if (typeof t === 'string') {
              chats.appendLocalMessageContent(localAssistantId, t)
              scrollToBottom()
            }
          } else if (evt.event === 'error') {
            streamError.value = String(evt.data?.message ?? 'unknown error')
          }
        },
        aborter?.signal,
      )
    } else {
      const res = await apiPost<{
        ok: boolean
        chatId: string
        assistantMessageId: string | null
        characterId: string
        content: string
        error?: string
      }>('/api/generate/group', { chatId, characterId })
      
      if (res.ok && activeChat.value && activeChat.value.messages[msgIndex]) {
        const updatedMsg = { ...activeChat.value.messages[msgIndex], content: res.content }
        activeChat.value.messages.splice(msgIndex, 1, updatedMsg)
        scrollToBottom()
      } else {
        streamError.value = res.error || 'unknown error'
      }
    }
    
    // 每个角色完成后再次检查暂停状态
    if (isPaused.value && i < memberIds.length - 1) {
      pendingMembers.value = memberIds.slice(i + 1)
      showContinueButton.value = true
      isGenerating.value = false
      currentSpeakerIndex.value = -1
      return
    }
  }
  
  // 全部完成
  pendingMembers.value = []
  showContinueButton.value = false
}

async function sendUserMessage() {
  const text = draftMessage.value.trim()
  if (!text) return
  if (!activeChat.value) return
  if (isGenerating.value) return
  draftMessage.value = ''
  streamError.value = null
  
  // 用户发送新消息时，清除暂停状态和继续按钮
  isPaused.value = false
  showContinueButton.value = false
  pendingMembers.value = []
  interjectPanelManuallyHidden.value = false
  // 纯 AI 模式下可随时插话；非纯 AI 模式保持“轮次结束后再插话”
  showInterjectPanel.value = effectivePureAiMode.value ? true : false

  const chatId = activeChat.value.id
  const isGroup = activeChat.value.isGroup
  const now = new Date().toISOString()
  const userRole = effectivePureAiMode.value ? ('system' as const) : ('user' as const)

  isGenerating.value = true
  aborter?.abort()
  aborter = new AbortController()

  const useStream = settings.settings?.streamEnabled !== false

  try {
    if (isGroup) {
      // ========== 群聊轮流发言逻辑 ==========
      const allMemberIds = [...activeChat.value.memberIds]  // 复制一份，防止被覆盖
      const groupDelay = activeChat.value.groupDelay || 1500
      
      // 根据概率筛选本轮参与的成员
      const memberIds = allMemberIds.filter(memberId => {
        const memberSettings = activeChat.value?.memberSettings?.[memberId]
        const probability = memberSettings?.probability ?? 1.0
        return Math.random() < probability
      })
      
      // 如果所有成员都被跳过，至少保留一个（随机选择）
      if (memberIds.length === 0 && allMemberIds.length > 0) {
        const randomIdx = Math.floor(Math.random() * allMemberIds.length)
        memberIds.push(allMemberIds[randomIdx]!)
      }
      
      // 1. 添加用户消息到本地显示
      const localUserId = `local_user_${Date.now()}`
      // activeChat.value.messages.push({ version: 1, id: localUserId, role: 'user', content: text, ts: now })
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
      
      // 2. 先保存用户消息到后端（直接调用API，不更新store的activeChat）
      await apiPost(`/api/chats/${chatId}/messages`, {
        role: userRole,
        content: text,
        senderPersonaId: userRole === 'user' ? (selectedPersona.value?.id ?? null) : null,
        senderName: userRole === 'user' ? (selectedPersona.value?.name ?? userName.value) : null,
        senderAvatar: userRole === 'user' ? (selectedPersona.value?.avatar ?? null) : null,
      })
      
      // 3. 依次让每个角色回复（可被暂停）
      await runGroupGeneration(chatId, memberIds, useStream, groupDelay, 0)
      
      // 如果被暂停了，不执行 finally 中的重新加载
      if (isPaused.value) return
      
      currentSpeakerIndex.value = -1
      
      // 轮次结束后显示插话面板
      interjectPanelManuallyHidden.value = false
      showInterjectPanel.value = true
      
    } else {
      // ========== 单聊逻辑 ==========
      const localUserId = `local_user_${Date.now()}`
      const localAssistantId = `local_assistant_${Date.now()}`

      // activeChat.value.messages.push({ version: 1, id: localUserId, role: 'user', content: text, ts: now })
      // activeChat.value.messages.push({ version: 1, id: localAssistantId, role: 'assistant', content: '', ts: now })
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
      // const assistantMsgIndex = activeChat.value.messages.length - 1
      
      scrollToBottom()

      if (useStream) {
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
            if (evt.event === 'delta') {
              const t = evt.data?.text
              if (typeof t === 'string') {
                chats.appendLocalMessageContent(localAssistantId, t)
                scrollToBottom()
              }
            } else if (evt.event === 'error') {
              streamError.value = String(evt.data?.message ?? 'unknown error')
            }
          },
          aborter?.signal,
        )
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
    streamError.value = e?.message ?? String(e)
  } finally {
    isGenerating.value = false
    currentSpeakerIndex.value = -1
    await chats.load(chatId)
    await settings.load()
  }
}

// 跳过用户轮次：群聊“开始下一轮”
async function startNextRound() {
  if (!activeChat.value) return
  if (!activeChat.value.isGroup) return
  if (isGenerating.value) return

  streamError.value = null
  showInterjectPanel.value = false
  isPaused.value = false
  showContinueButton.value = false
  pendingMembers.value = []

  const chatId = activeChat.value.id
  const useStream = settings.settings?.streamEnabled !== false
  const groupDelay = activeChat.value.groupDelay || 1500

  isGenerating.value = true
  aborter?.abort()
  aborter = new AbortController()

  try {
    const allMemberIds = [...activeChat.value.memberIds]
    const memberIds = allMemberIds.filter(memberId => {
      const memberSettings = activeChat.value?.memberSettings?.[memberId]
      const probability = memberSettings?.probability ?? 1.0
      return Math.random() < probability
    })
    if (memberIds.length === 0 && allMemberIds.length > 0) {
      const randomIdx = Math.floor(Math.random() * allMemberIds.length)
      memberIds.push(allMemberIds[randomIdx]!)
    }

    await runGroupGeneration(chatId, memberIds, useStream, groupDelay, 0)
    if (isPaused.value) return

    interjectPanelManuallyHidden.value = false
    showInterjectPanel.value = true
  } catch (e: any) {
    streamError.value = e?.message ?? String(e)
  } finally {
    isGenerating.value = false
    currentSpeakerIndex.value = -1
    if (!isPaused.value) {
      await chats.load(chatId)
      await settings.load()
    }
  }
}

const editingCharacterAvatarUrl = computed(() => {
  if (!editingCharacter.value?.avatar) return null
  return `/api/avatars/${editingCharacter.value.avatar}`
})

const editingPersonaAvatarUrl = computed(() => {
  if (!editingPersona.value?.avatar) return null
  return `/api/avatars/${editingPersona.value.avatar}`
})
</script>

<template>
  <div class="flex h-screen w-full bg-dark-bg text-gray-200 overflow-hidden font-sans">
    
    <!-- 侧边栏开关 -->
    <div 
      class="absolute left-0 top-1/2 -translate-y-1/2 z-50 cursor-pointer p-2 bg-brand/30 hover:bg-brand/50 rounded-r-lg backdrop-blur-sm transition-colors border border-l-0 border-brand/40 shadow-lg"
      @click="sidebarCollapsed = !sidebarCollapsed"
      title="切换侧边栏"
    >
      <span class="text-xs text-white">{{ sidebarCollapsed ? '▶' : '◀' }}</span>
    </div>

    <!-- 左侧侧边栏 -->
    <aside 
      class="flex flex-col border-r border-white/5 bg-[#141418] transition-all duration-300 relative flex-shrink-0"
      :class="sidebarCollapsed ? '-ml-80 w-80' : 'w-80'"
    >
      <div class="flex flex-col h-full overflow-hidden">
        
        <!-- 用户身份区域 (头部) -->
        <div class="p-4 bg-black/10 border-b border-white/5 shrink-0">
          <div class="flex items-center justify-between mb-3">
            <span class="text-xs font-bold text-gray-400 uppercase tracking-wider">我的身份</span>
            <button class="text-xs text-brand hover:text-brand-hover transition-colors px-2 py-0.5 rounded hover:bg-white/5" @click="openCreatePersona">+ 新建</button>
          </div>
          
          <div class="space-y-2 max-h-[140px] overflow-y-auto pr-1 custom-scrollbar">
            <div 
              v-for="p in (settings.settings?.userPersonas || [])"
              :key="p.id"
              class="group flex items-center gap-3 p-2 rounded-xl cursor-pointer transition-all duration-200 border border-transparent"
              :class="effectiveSelectedPersonaId === p.id ? 'bg-brand/10 border-brand/20' : 'hover:bg-white/5'"
              @click="selectPersona(p.id)"
            >
              <ModernAvatar :src="p.avatar ? `/api/avatars/${p.avatar}` : null" :name="p.name" :size="36" aspect="1" />
              <div class="flex-1 min-w-0">
                <div class="font-medium text-sm truncate" :class="effectiveSelectedPersonaId === p.id ? 'text-brand' : 'text-gray-300'">{{ p.name }}</div>
              </div>
              <div class="opacity-0 group-hover:opacity-100 flex gap-1 transition-opacity">
                <button class="p-1 hover:text-white text-gray-500" @click.stop="openEditPersona(p)">✏</button>
                <NPopconfirm @positive-click="deletePersona(p.id)">
                  <template #trigger>
                    <button class="p-1 hover:text-red-400 text-gray-500" @click.stop>🗑</button>
                  </template>
                  确定删除这个身份？
                </NPopconfirm>
              </div>
            </div>
            
            <div v-if="!settings.settings?.userPersonas?.length" class="text-xs text-gray-500 text-center py-2">
              点击上方新建创建你的第一个身份
            </div>
          </div>
        </div>

        <!-- 角色列表区域 (中间，弹性伸缩) -->
        <div class="flex-1 overflow-y-auto min-h-0 custom-scrollbar p-3">
          <div class="flex items-center justify-between mb-2 px-1">
            <span class="text-xs font-bold text-gray-400 uppercase tracking-wider">角色列表</span>
            <button class="text-xs text-brand hover:text-brand-hover transition-colors px-2 py-0.5 rounded hover:bg-white/5" @click="openCreateCharacter">+ 新建</button>
          </div>

          <div class="grid grid-cols-1 gap-2">
            <div 
              v-for="c in characters.list"
              :key="c.id"
              class="group relative flex items-start gap-3 p-3 rounded-2xl cursor-pointer transition-all duration-200 border border-transparent"
              :class="selectedCharacterId === c.id ? 'bg-white/5 border-brand/20 shadow-sm' : 'hover:bg-white/5'"
              @click="selectedCharacterId = c.id"
            >
              <!-- 角色头像 (3:4 比例) -->
              <ModernAvatar 
                :src="c.avatar ? `/api/avatars/${c.avatar}` : null" 
                :name="c.name" 
                :size="56" 
                :aspect="0.75"
                rounded="rounded-lg"
                class="shadow-md"
              />
              
              <div class="flex-1 min-w-0 flex flex-col h-[74px]"> <!-- 56/0.75 approx 74px height -->
                <div class="flex justify-between items-start">
                  <div class="font-bold text-sm truncate" :class="selectedCharacterId === c.id ? 'text-brand-300' : 'text-gray-200'">{{ c.name }}</div>
                </div>
                <div class="text-xs text-gray-500 line-clamp-3 mt-1 leading-relaxed">{{ c.description || '暂无简介' }}</div>
              </div>

              <!-- 悬浮操作 -->
              <div class="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity bg-black/60 rounded-lg backdrop-blur-sm p-0.5 flex">
                <button class="p-1.5 hover:text-white text-gray-400" @click.stop="openEditCharacter(c)">✏</button>
                <NPopconfirm @positive-click="deleteCharacter(c.id)">
                  <template #trigger>
                    <button class="p-1.5 hover:text-red-400 text-gray-400" @click.stop>🗑</button>
                  </template>
                  确定删除？
                </NPopconfirm>
              </div>
            </div>
          </div>
        </div>

        <!-- 会话列表区域 (底部) -->
        <div class="h-1/3 min-h-[150px] border-t border-white/5 bg-black/10 flex flex-col">
          <div class="p-3 pb-1 shrink-0 flex items-center justify-between">
            <span class="text-xs font-bold text-gray-400 uppercase tracking-wider">历史会话</span>
            <div class="flex gap-2">
              <button 
                class="text-xs bg-purple-500/20 hover:bg-purple-500/30 text-purple-400 px-2 py-1 rounded transition-colors disabled:opacity-50 disabled:cursor-not-allowed" 
                :disabled="characters.list.length < 2" 
                @click="openGroupCreator"
                title="创建群聊"
              >
                + 群聊
              </button>
              <button 
                class="text-xs bg-brand/20 hover:bg-brand/30 text-brand px-2 py-1 rounded transition-colors disabled:opacity-50 disabled:cursor-not-allowed" 
                :disabled="!selectedCharacterId" 
                @click="createChat"
              >
                新建会话
              </button>
            </div>
          </div>
          <div class="flex-1 overflow-y-auto p-2 custom-scrollbar">
            <!-- 群聊列表 -->
            <div v-if="chats.groupList.length > 0" class="mb-3">
              <div class="text-[10px] text-purple-400 uppercase tracking-wider px-2 mb-1 flex items-center gap-1">
                <span>👥</span> 群聊
              </div>
              <div 
                v-for="c in chats.groupList"
                :key="c.id"
                class="group flex items-center justify-between p-2 rounded-lg cursor-pointer text-sm mb-1 transition-colors"
                :class="chats.activeChatId === c.id ? 'bg-purple-500/10 text-purple-400' : 'text-gray-400 hover:bg-white/5 hover:text-gray-200'"
                @click="selectGroupChat(c)"
              >
                <div class="flex items-center gap-2 flex-1 min-w-0 pr-2">
                  <div class="flex -space-x-1.5 overflow-hidden shrink-0">
                     <template v-for="(avatar, i) in getChatAvatars(c).slice(0, 3)" :key="i">
                       <ModernAvatar :src="avatar.src" :name="avatar.name" :size="20" aspect="1" rounded="rounded-full" class="ring-1 ring-[#141418] bg-[#141418]" />
                     </template>
                     <div v-if="getChatAvatars(c).length > 3" class="w-5 h-5 rounded-full bg-white/10 flex items-center justify-center text-[8px] ring-1 ring-[#141418]">
                       +{{ getChatAvatars(c).length - 3 }}
                     </div>
                  </div>
                  <div v-if="editingChatId === c.id" @click.stop class="flex gap-1 flex-1">
                    <input 
                      v-model="editingTitle" 
                      class="bg-black/20 border border-purple-500/50 rounded px-1 py-0.5 text-xs w-full text-white outline-none focus:border-purple-500"
                      @keyup.enter="saveTitle"
                      @keyup.escape="cancelEditTitle"
                      autoFocus
                    />
                    <button class="text-purple-400 hover:text-white" @click="saveTitle">✓</button>
                    <button class="text-gray-500 hover:text-white" @click="cancelEditTitle">✕</button>
                  </div>
                  <div v-else class="truncate">{{ c.title }}</div>
                  <span class="text-[10px] text-gray-600">({{ c.memberIds.length }}人)</span>
                </div>
                
                <div v-if="editingChatId !== c.id" class="opacity-0 group-hover:opacity-100 flex gap-1 transition-opacity">
                  <button class="hover:text-white" @click.stop="startEditTitle(c.id, c.title)">✏</button>
                  <NPopconfirm @positive-click="deleteChat(c.id)">
                    <template #trigger>
                      <button class="hover:text-red-400" @click.stop>🗑</button>
                    </template>
                    删除群聊？
                  </NPopconfirm>
                </div>
              </div>
            </div>

            <!-- 单聊列表 -->
            <div v-if="chats.list.filter(c => !c.isGroup).length > 0">
              <div v-if="chats.groupList.length > 0" class="text-[10px] text-gray-500 uppercase tracking-wider px-2 mb-1">
                单聊
              </div>
              <div 
                v-for="c in chats.list.filter(chat => !chat.isGroup)"
                :key="c.id"
                class="group flex items-center justify-between p-2 rounded-lg cursor-pointer text-sm mb-1 transition-colors"
                :class="chats.activeChatId === c.id ? 'bg-brand/10 text-brand' : 'text-gray-400 hover:bg-white/5 hover:text-gray-200'"
                @click="chats.load(c.id)"
              >
                <div class="flex items-center gap-2 flex-1 min-w-0 pr-2">
                  <div class="flex -space-x-1.5 overflow-hidden shrink-0">
                     <template v-for="(avatar, i) in getChatAvatars(c).slice(0, 2)" :key="i">
                       <ModernAvatar :src="avatar.src" :name="avatar.name" :size="20" aspect="1" rounded="rounded-full" class="ring-1 ring-[#141418] bg-[#141418]" />
                     </template>
                  </div>
                  <div class="flex-1 min-w-0">
                    <div v-if="editingChatId === c.id" @click.stop class="flex gap-1">
                        <input 
                          v-model="editingTitle" 
                          class="bg-black/20 border border-brand/50 rounded px-1 py-0.5 text-xs w-full text-white outline-none focus:border-brand"
                          @keyup.enter="saveTitle"
                          @keyup.escape="cancelEditTitle"
                          autoFocus
                        />
                        <button class="text-brand hover:text-white" @click="saveTitle">✓</button>
                        <button class="text-gray-500 hover:text-white" @click="cancelEditTitle">✕</button>
                    </div>
                    <div v-else class="truncate">{{ c.title }}</div>
                  </div>
                </div>
                
                <div v-if="editingChatId !== c.id" class="opacity-0 group-hover:opacity-100 flex gap-1 transition-opacity">
                  <button class="hover:text-white" @click.stop="startEditTitle(c.id, c.title)">✏</button>
                  <NPopconfirm @positive-click="deleteChat(c.id)">
                    <template #trigger>
                      <button class="hover:text-red-400" @click.stop>🗑</button>
                    </template>
                    删除会话？
                  </NPopconfirm>
                </div>
              </div>
            </div>
            <div v-if="!chats.list.length && !chats.groupList.length" class="text-center text-xs text-gray-600 py-4">
              无历史会话
            </div>
          </div>
        </div>
      </div>
    </aside>

    <!-- 右侧主区域 -->
    <main class="flex-1 flex flex-col relative min-w-0 bg-[#101014]">
      
      <!-- 聊天内容区 -->
      <div v-if="(selectedCharacter || activeChat?.isGroup) && activeChat" class="flex flex-col h-full relative">
        <!-- 顶部标题栏 (悬浮) -->
        <header class="absolute top-0 left-0 right-0 z-10 flex flex-col bg-gradient-to-b from-[#101014] via-[#101014]/90 to-transparent pointer-events-none">
          <!-- 主标题行 -->
          <div class="h-14 flex items-center justify-between px-6">
            <div class="pointer-events-auto flex items-center gap-3">
              <template v-if="activeChat.isGroup">
                <span class="text-purple-400">👥</span>
                <h2 class="text-lg font-bold text-purple-300 shadow-sm">{{ activeChat.title }}</h2>
                <span class="text-xs text-gray-500">({{ activeChat.memberIds.length }}个角色)</span>
              </template>
              <template v-else>
                <h2 class="text-lg font-bold text-gray-100 shadow-sm">{{ selectedCharacter?.name }}</h2>
                <span class="text-gray-600">/</span>
                <span class="text-sm text-gray-400">{{ activeChat.title }}</span>
              </template>
            </div>
            <div class="pointer-events-auto flex items-center gap-2">
              <NButton v-if="activeChat.isGroup" size="small" secondary class="!bg-purple-500/10 !text-purple-400 hover:!bg-purple-500/20" @click="openMemberManager">
                管理成员
              </NButton>
              <NButton size="small" secondary type="primary" class="!bg-brand/10 !text-brand hover:!bg-brand/20" @click="showSettings = true">
                设置
              </NButton>
            </div>
          </div>
          
          <!-- 群成员头像行 (仅群聊时显示) -->
          <div v-if="activeChat.isGroup && groupMembers.length > 0" class="px-6 pb-2 pointer-events-auto">
            <div class="flex items-center gap-2 overflow-x-auto pb-1">
              <div class="text-xs text-gray-500 shrink-0">成员:</div>
              <div 
                v-for="(member, idx) in groupMembers" 
                :key="member.id"
                class="flex items-center gap-1 shrink-0 bg-white/5 px-2 py-1 rounded-lg transition-colors group/member"
                :class="canInterject ? 'cursor-pointer hover:bg-purple-500/20 hover:border-purple-500/50' : ''"
                :title="canInterject ? `点击让 ${member.name} 插话` : member.name"
                @click="canInterject && triggerInterject(member.id)"
              >
                <span class="text-xs text-gray-500">{{ idx + 1 }}.</span>
                <ModernAvatar 
                  :src="member.avatar ? `/api/avatars/${member.avatar}` : null" 
                  :name="member.name" 
                  :size="20" 
                  aspect="1"
                  rounded="rounded"
                  :class="canInterject ? 'group-hover/member:ring-2 group-hover/member:ring-purple-500' : ''"
                />
                <span class="text-xs text-gray-300 max-w-[60px] truncate">{{ member.name }}</span>
                <!-- 显示概率标记 -->
                <span 
                  v-if="getMemberSettings(member.id).probability < 1" 
                  class="text-[10px] text-yellow-400 ml-0.5"
                  :title="`${Math.round(getMemberSettings(member.id).probability * 100)}% 参与概率`"
                >
                  {{ Math.round(getMemberSettings(member.id).probability * 100) }}%
                </span>
              </div>
              <!-- 用户也是成员（纯 AI 模式不展示用户头像） -->
              <div v-if="!effectivePureAiMode" class="flex items-center gap-1 shrink-0 bg-brand/10 px-2 py-1 rounded-lg border border-brand/20">
                <ModernAvatar 
                  :src="userAvatarUrl" 
                  :name="userName" 
                  :size="20" 
                  aspect="1"
                  rounded="rounded"
                />
                <span class="text-xs text-brand max-w-[60px] truncate">{{ userName }}</span>
                <span class="text-[10px] text-brand/60">(你)</span>
              </div>
            </div>
          </div>
        </header>

        <!-- 消息列表 -->
        <div ref="messagesScrollRef" class="flex-1 overflow-y-auto p-4 pb-4 scroll-smooth custom-scrollbar" :class="activeChat.isGroup ? 'pt-28' : 'pt-20'">
          <div class="max-w-4xl mx-auto space-y-8">
            <div v-for="m in activeChat.messages" :key="m.id" class="flex gap-4 group" :class="m.role === 'user' ? 'flex-row-reverse' : 'flex-row'">
              
              <!-- 头像 -->
              <div class="flex-shrink-0 mt-1">
                 <div v-if="m.role === 'system'" class="w-10 h-10 rounded-full bg-yellow-500/20 flex items-center justify-center text-yellow-500">
                   ⚙
                 </div>
                 <ModernAvatar 
                   v-else
                   :src="getMessageAvatar(m)"
                   :name="getMessageLabel(m)"
                   :size="40"
                   aspect="1"
                   object-fit="contain"
                   rounded="rounded-xl"
                   class="shadow-sm bg-black/20"
                 />
              </div>

              <!-- 消息体 -->
              <div class="flex flex-col max-w-[85%] min-w-0" :class="m.role === 'user' ? 'items-end' : 'items-start'">
                <div class="flex items-center gap-2 mb-1 px-1">
                  <span class="text-xs font-bold" :class="m.role === 'user' ? 'text-brand-300' : 'text-gray-400'">
                    {{ getMessageLabel(m) }}
                  </span>
                  <!-- 角色标签 (仅 System 显示，其他靠颜色区分) -->
                  <span v-if="m.role === 'system'" class="text-[10px] bg-yellow-500/10 text-yellow-500 px-1.5 py-0.5 rounded">SYSTEM</span>
                </div>

                <!-- 气泡 -->
                <div 
                  class="relative px-5 py-3.5 rounded-2xl text-[15px] leading-7 shadow-sm transition-all duration-200 border"
                  :class="[
                    m.role === 'user' 
                      ? 'bg-brand/10 border-brand/20 text-gray-100 rounded-tr-sm hover:border-brand/30' 
                      : m.role === 'assistant'
                        ? 'bg-[#1e1e24] border-white/5 text-gray-200 rounded-tl-sm hover:bg-[#232329]'
                        : 'bg-yellow-500/5 border-yellow-500/10 text-gray-300'
                  ]"
                >
                  <div class="md prose prose-invert prose-sm max-w-none prose-p:my-1 prose-headings:my-2 prose-pre:bg-black/30 prose-pre:border prose-pre:border-white/5" v-html="renderMarkdown(m.content)"></div>
                </div>

                <!-- 底部操作栏 -->
                <div class="flex items-center gap-2 mt-1 px-1 opacity-0 group-hover:opacity-100 transition-opacity">
                   <button class="text-xs text-gray-600 hover:text-brand transition-colors" @click="openEditMessage(m)" :disabled="isGenerating">编辑</button>
                   <NPopconfirm @positive-click="deleteMessage(m)">
                      <template #trigger>
                        <button class="text-xs text-gray-600 hover:text-red-400 transition-colors" :disabled="isGenerating">删除</button>
                      </template>
                      确定删除？
                   </NPopconfirm>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 输入区域 (底部悬浮) -->
        <div class="shrink-0 p-4 pb-6 w-full max-w-4xl mx-auto z-20">
           <div class="relative bg-[#18181c] border border-white/10 rounded-2xl shadow-xl p-3 flex flex-col gap-2 transition-colors focus-within:border-brand/40 focus-within:ring-1 focus-within:ring-brand/20">
              <NInput
                v-model:value="draftMessage"
                type="textarea"
                :placeholder="isGenerating && activeChat?.isGroup && !isPaused ? '等待角色发言完成...' : (showContinueButton ? '输入消息插话，或点击继续轮次...' : '发送消息...')"
                :autosize="{ minRows: 2, maxRows: 8 }"
                :disabled="isGenerating && !isPaused && !showContinueButton"
                class="!bg-transparent !border-0 text-base"
                :class="isGenerating && !isPaused && !showContinueButton ? 'opacity-50' : ''"
                style="--n-border: none; --n-box-shadow-focus: none;"
                @keydown.ctrl.enter="sendUserMessage"
              />
              
              <div class="flex items-center justify-between pt-2 border-t border-white/5">
                 <div class="flex-1 min-w-0">
                   <!-- 群聊发言状态指示器 -->
                   <div v-if="activeChat?.isGroup && isGenerating && currentSpeakerIndex >= 0" class="flex items-center gap-2 text-xs text-purple-400">
                     <span class="animate-pulse">●</span>
                     <span>{{ groupMembers[currentSpeakerIndex]?.name || '角色' }} 正在发言...</span>
                     <span class="text-gray-500">({{ currentSpeakerIndex + 1 }}/{{ groupMembers.length }})</span>
                     <!-- 暂停按钮 -->
                     <button 
                       class="ml-2 px-2 py-0.5 text-xs bg-yellow-500/20 hover:bg-yellow-500/30 text-yellow-400 rounded transition-colors"
                       @click="pauseGroupChat"
                     >
                       暂停
                     </button>
                   </div>
                   <!-- 继续轮次按钮 -->
                   <div v-else-if="showContinueButton && pendingMembers.length > 0" class="flex items-center gap-2 text-xs text-green-400">
                     <span>轮次已暂停，还有 {{ pendingMembers.length }} 位角色待发言</span>
                     <button 
                       class="px-3 py-1 text-xs bg-green-500/20 hover:bg-green-500/30 text-green-400 rounded transition-colors font-medium"
                       @click="continueGroupChat"
                     >
                       继续轮次
                     </button>
                   </div>
                   <!-- 插话面板 -->
                   <div v-else-if="canInterject && activeChat?.isGroup && !isInterjecting" class="flex items-center gap-2 text-xs">
                     <span class="text-purple-400">💬 点击角色插话：</span>
                     <div class="flex items-center gap-1">
                       <div 
                         v-for="member in groupMembers"
                         :key="member.id"
                         class="cursor-pointer hover:scale-110 transition-transform"
                         :title="`让 ${member.name} 插话`"
                         @click="triggerInterject(member.id)"
                       >
                         <ModernAvatar 
                           :src="member.avatar ? `/api/avatars/${member.avatar}` : null" 
                           :name="member.name" 
                           :size="24" 
                           aspect="1"
                           rounded="rounded"
                           class="ring-2 ring-purple-500/50 hover:ring-purple-500"
                         />
                       </div>
                     </div>
                     <button 
                       class="ml-2 px-2 py-0.5 text-xs bg-gray-500/20 hover:bg-gray-500/30 text-gray-400 rounded transition-colors"
                       @click="() => { showInterjectPanel = false; interjectPanelManuallyHidden = true }"
                     >
                       关闭
                     </button>
                   </div>
                   <!-- 插话中状态 -->
                   <div v-else-if="isInterjecting" class="flex items-center gap-2 text-xs text-purple-400">
                     <span class="animate-pulse">●</span>
                     <span>正在插话...</span>
                   </div>
                   <div v-else-if="streamError" class="text-xs text-red-400 truncate">{{ streamError }}</div>
                 </div>
                 <div class="flex items-center gap-3">
                   <ModernSelect
                      :model-value="currentModel"
                      :options="chatModelOptions"
                      placement="top"
                      placeholder="选择模型 (自动关联预设)..."
                      class="!w-[200px] !text-xs"
                      searchable
                      allow-create
                      @select="handleModelSelect"
                    />
                    <button 
                      class="bg-brand hover:bg-brand-hover text-white px-4 py-1.5 rounded-lg text-sm font-medium transition-all disabled:opacity-50 disabled:cursor-not-allowed shadow-lg shadow-brand/20"
                      :disabled="!draftMessage.trim() || (isGenerating && !isPaused && !showContinueButton)"
                      @click="sendUserMessage"
                    >
                      {{ isGenerating && !isPaused && !showContinueButton ? '生成中...' : (showContinueButton ? '插话并重新开始' : '发送') }}
                    </button>
                    <button
                      v-if="activeChat?.isGroup"
                      class="bg-purple-500/20 hover:bg-purple-500/30 text-purple-300 px-4 py-1.5 rounded-lg text-sm font-medium transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                      :disabled="isGenerating"
                      @click="startNextRound"
                      title="不发送用户消息，直接让群聊进入下一轮"
                    >
                      开始下一轮
                    </button>
                 </div>
              </div>
           </div>
           <div class="text-center mt-2 text-xs text-gray-600">
             Markdown 支持 · Ctrl + Enter 发送
           </div>
        </div>

      </div>

      <!-- 空状态 -->
      <div v-else class="flex flex-col items-center justify-center h-full text-center p-8 opacity-60">
         <div class="w-20 h-20 rounded-2xl bg-white/5 mb-6 flex items-center justify-center text-4xl">👋</div>
         <h3 class="text-xl font-bold text-gray-200 mb-2">欢迎来到 SimpleTavern</h3>
         <p class="text-gray-500 mb-8 max-w-md">请在左侧选择一个角色并开始会话，或者创建一个新的角色。</p>
         <button class="bg-brand text-white px-6 py-2 rounded-xl hover:bg-brand-hover transition-colors" @click="openCreateCharacter">
           创建新角色
         </button>
      </div>

    </main>
  </div>

  <SettingsDrawer v-model:show="showSettings" :chat="activeChat" />

  <!-- 消息编辑弹窗 -->
  <NModal v-model:show="showMessageEditor" preset="card" style="width: min(700px, 92vw)" title="编辑消息" class="!bg-[#18181c] !border-white/10">
    <NForm label-placement="top">
      <NSpace vertical size="medium">
        <NFormItem label="发送者 / 头像">
          <NSpace size="small" wrap>
            <div 
              class="cursor-pointer border-2 rounded-xl p-1 px-3 flex items-center gap-2 transition-all"
              :class="editingMessageRole === 'system' ? 'border-brand bg-brand/10' : 'border-transparent bg-white/5 hover:bg-white/10'"
              @click="editingMessageRole = 'system'"
            >
               <span class="text-lg">⚙</span>
               <span class="text-sm">系统</span>
            </div>
            <div 
              class="cursor-pointer border-2 rounded-xl p-1 px-3 flex items-center gap-2 transition-all"
              :class="editingMessageRole === 'assistant' ? 'border-brand bg-brand/10' : 'border-transparent bg-white/5 hover:bg-white/10'"
              @click="editingMessageRole = 'assistant'"
            >
               <ModernAvatar :src="characterAvatarUrl" :size="24" aspect="1" rounded="rounded" />
               <span class="text-sm">角色</span>
            </div>
            <div 
              class="cursor-pointer border-2 rounded-xl p-1 px-3 flex items-center gap-2 transition-all"
              :class="editingMessageRole === 'user' ? 'border-brand bg-brand/10' : 'border-transparent bg-white/5 hover:bg-white/10'"
              @click="editingMessageRole = 'user'"
            >
               <ModernAvatar :src="userAvatarUrl" :size="24" aspect="1" rounded="rounded" />
               <span class="text-sm">用户</span>
            </div>
          </NSpace>
        </NFormItem>

        <NFormItem label="内容">
          <NInput
            v-model:value="editingMessageContent"
            type="textarea"
            :autosize="{ minRows: 6, maxRows: 18 }"
            placeholder="输入消息内容（支持 Markdown）"
            class="!bg-black/20"
          />
        </NFormItem>

        <NSpace justify="end">
          <NButton @click="closeEditMessage">取消</NButton>
          <NButton type="primary" :disabled="isGenerating" @click="saveEditedMessage">保存</NButton>
        </NSpace>
      </NSpace>
    </NForm>
  </NModal>

  <!-- 角色编辑弹窗 -->
  <NModal v-model:show="showCharacterEditor" preset="card" style="width: min(700px, 90vw)" :title="isNewCharacter ? '新建角色' : '编辑角色'" class="!bg-[#18181c] !border-white/10">
    <NForm v-if="editingCharacter" label-placement="top">
      <NSpace vertical size="medium">
        <div class="flex gap-6">
           <div class="flex flex-col items-center gap-3">
              <ModernAvatar 
                :src="editingCharacterAvatarUrl"
                :size="120"
                :aspect="0.75"
                rounded="rounded-xl"
                class="border-2 border-brand/40 shadow-lg bg-black/20"
              />
              <NButton size="small" secondary @click="showCharacterAvatarCropper = true">更换头像</NButton>
           </div>
           <div class="flex-1 space-y-4">
        <NFormItem>
          <template #label>
            <span>名称</span>
            <span class="opacity-60 text-xs ml-2 text-brand">该项参与对话</span>
          </template>
                <NInput v-model:value="editingCharacter.name" placeholder="角色名称" />
              </NFormItem>
              <NFormItem label="简介">
                <NInput v-model:value="editingCharacter.description" type="textarea" :autosize="{ minRows: 2, maxRows: 3 }" placeholder="简短描述" />
              </NFormItem>
           </div>
        </div>

        <NFormItem>
          <template #label>
            <span>Personality（性格/外貌）</span>
            <span class="opacity-60 text-xs ml-2 text-brand">该项参与对话</span>
          </template>
          <NInput v-model:value="editingCharacter.personality" type="textarea" :autosize="{ minRows: 2, maxRows: 5 }" placeholder="详细设定..." />
        </NFormItem>

        <NFormItem>
          <template #label>
            <span>Scenario（情景/世界观）</span>
            <span class="opacity-60 text-xs ml-2 text-brand">该项参与对话</span>
          </template>
          <NInput v-model:value="editingCharacter.scenario" type="textarea" :autosize="{ minRows: 2, maxRows: 4 }" placeholder="世界背景..." />
        </NFormItem>

        <NFormItem>
          <template #label>
            <span>系统提示词</span>
            <span class="opacity-60 text-xs ml-2 text-brand">该项参与对话</span>
          </template>
          <NInput v-model:value="editingCharacter.systemPrompt" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" placeholder="回复格式要求..." />
        </NFormItem>

        <NFormItem>
          <template #label>
            <span>首句</span>
            <span class="opacity-60 text-xs ml-2">支持 {<!-- -->{user}} 占位符</span>
            <span class="opacity-60 text-xs ml-2 text-brand">该项参与对话</span>
          </template>
          <NInput v-model:value="editingCharacter.firstMessage" type="textarea" :autosize="{ minRows: 2, maxRows: 4 }" placeholder="开场白..." />
        </NFormItem>

        <NSpace justify="end">
          <NButton secondary @click="exportCharacterCard" :disabled="!editingCharacter">导出为文本</NButton>
          <NButton @click="showCharacterEditor = false">取消</NButton>
          <NButton type="primary" @click="saveCharacter">保存</NButton>
        </NSpace>
      </NSpace>
    </NForm>
  </NModal>

  <!-- Persona 编辑弹窗 -->
  <NModal v-model:show="showPersonaEditor" preset="card" style="width: min(500px, 90vw)" :title="isNewPersona ? '新建身份' : '编辑身份'" class="!bg-[#18181c] !border-white/10">
    <NForm v-if="editingPersona" label-placement="top">
      <NSpace vertical size="medium">
        <div class="flex items-center gap-4 mb-2">
            <ModernAvatar 
              :src="editingPersonaAvatarUrl"
              :size="80"
              aspect="1"
              rounded="rounded-xl"
              class="border-2 border-brand/40"
            />
            <NButton size="small" secondary @click="showPersonaAvatarCropper = true">更换头像</NButton>
        </div>

        <NFormItem label="姓名（{{user}}）">
          <NInput v-model:value="editingPersona.name" placeholder="你的角色名称" />
        </NFormItem>

        <NFormItem label="简介">
          <NInput
            v-model:value="editingPersona.description"
            type="textarea"
            :autosize="{ minRows: 3, maxRows: 6 }"
            placeholder="你的角色身份、背景等"
          />
        </NFormItem>

        <NSpace justify="end">
          <NButton @click="showPersonaEditor = false">取消</NButton>
          <NButton type="primary" @click="savePersona">保存</NButton>
        </NSpace>
      </NSpace>
    </NForm>
  </NModal>

  <AvatarCropper
    v-model:show="showCharacterAvatarCropper"
    @save="handleCharacterAvatarSave"
  />

  <AvatarCropper
    v-model:show="showPersonaAvatarCropper"
    @save="handlePersonaAvatarSave"
  />

  <!-- Persona 切换确认弹窗 -->
  <NModal v-model:show="showPersonaSwitchConfirm" preset="card" style="width: min(520px, 92vw)" title="切换用户身份" class="!bg-[#18181c] !border-white/10">
    <div class="space-y-4">
      <div class="text-sm text-gray-300">
        你正在尝试切换用户身份，请选择“新建会话”或“仍然继续对话”。
      </div>
      <div class="text-xs text-gray-500">
        提示：继续对话时，历史消息会保持原身份显示；后续新发送的 user 消息将使用新身份。
      </div>
      <div class="flex justify-end gap-2 pt-2 border-t border-white/10">
        <NButton @click="cancelSwitchPersona">取消</NButton>
        <NButton secondary @click="confirmSwitchPersonaContinue">仍然继续对话</NButton>
        <NButton type="primary" @click="confirmSwitchPersonaNewSession">新建会话</NButton>
      </div>
    </div>
  </NModal>

  <!-- 群聊创建弹窗 -->
  <NModal v-model:show="showGroupCreator" preset="card" style="width: min(600px, 90vw)" title="创建群聊" class="!bg-[#18181c] !border-white/10">
    <NSpace vertical size="medium">
      <NFormItem label="群聊名称">
        <NInput v-model:value="groupTitle" placeholder="新群聊" />
      </NFormItem>

      <div class="bg-white/5 border border-white/10 rounded-xl p-3">
        <div class="text-sm text-gray-300 font-medium mb-2">本次聊天设置</div>
        <div class="flex items-center justify-between">
          <div class="text-sm text-gray-400">纯 AI 模式（不注入 Persona，用户发言将以 system 影响世界）</div>
          <button
            class="flex items-center gap-2"
            @click="groupPureAiMode = !groupPureAiMode"
          >
            <div class="w-10 h-5 rounded-full relative transition-colors duration-200" :class="groupPureAiMode ? 'bg-brand' : 'bg-gray-700'">
              <div class="absolute top-1 w-3 h-3 rounded-full bg-white transition-transform duration-200" :class="groupPureAiMode ? 'left-6' : 'left-1'"></div>
            </div>
            <span class="text-xs text-gray-400">{{ groupPureAiMode ? '开启' : '关闭' }}</span>
          </button>
        </div>
      </div>

      <div class="bg-white/5 border border-white/10 rounded-xl p-3">
        <div class="text-sm text-gray-300 font-medium mb-2">群聊首句（故事背景）</div>
        <div class="flex items-center justify-between mb-2">
          <div class="text-sm text-gray-400">启用某角色的 First Message 作为开场</div>
          <button class="flex items-center gap-2" @click="groupFirstMessageEnabled = !groupFirstMessageEnabled">
            <div class="w-10 h-5 rounded-full relative transition-colors duration-200" :class="groupFirstMessageEnabled ? 'bg-purple-500' : 'bg-gray-700'">
              <div class="absolute top-1 w-3 h-3 rounded-full bg-white transition-transform duration-200" :class="groupFirstMessageEnabled ? 'left-6' : 'left-1'"></div>
            </div>
            <span class="text-xs text-gray-400">{{ groupFirstMessageEnabled ? '启用' : '关闭' }}</span>
          </button>
        </div>
        <div v-if="groupFirstMessageEnabled" class="flex items-center gap-2">
          <span class="text-xs text-gray-500 shrink-0">选择角色：</span>
          <ModernSelect
            :model-value="groupFirstMessageCharacterId || ''"
            @update:model-value="(v) => groupFirstMessageCharacterId = v || null"
            :options="groupFirstMessageOptions"
            :disabled="selectedMemberIds.length === 0"
            placeholder="（未选择）"
            class="flex-1"
          />
        </div>
        <div class="text-xs text-gray-500 mt-2">创建后会在聊天窗口内直接插入该角色的首句（会写入聊天记录）。</div>
      </div>
      
      <div>
        <div class="text-sm text-gray-400 mb-3">选择群成员 (至少选择2个角色):</div>
        <div class="grid grid-cols-2 sm:grid-cols-3 gap-3 max-h-[300px] overflow-y-auto pr-2 custom-scrollbar">
          <div 
            v-for="c in characters.list"
            :key="c.id"
            class="flex items-center gap-3 p-3 rounded-xl cursor-pointer transition-all border-2"
            :class="selectedMemberIds.includes(c.id) ? 'bg-purple-500/10 border-purple-500/50' : 'bg-white/5 border-transparent hover:bg-white/10'"
            @click="toggleMemberSelection(c.id)"
          >
            <div class="relative shrink-0">
              <ModernAvatar 
                :src="c.avatar ? `/api/avatars/${c.avatar}` : null" 
                :name="c.name" 
                :size="40" 
                :aspect="0.75"
                rounded="rounded-lg"
              />
              <div 
                v-if="selectedMemberIds.includes(c.id)"
                class="absolute -top-1 -right-1 w-5 h-5 bg-purple-500 rounded-full flex items-center justify-center text-white text-xs font-bold"
              >
                {{ selectedMemberIds.indexOf(c.id) + 1 }}
              </div>
            </div>
            <div class="flex-1 min-w-0">
              <div class="font-medium text-sm truncate" :class="selectedMemberIds.includes(c.id) ? 'text-purple-300' : 'text-gray-300'">{{ c.name }}</div>
              <div class="text-xs text-gray-500 truncate">{{ c.description || '暂无简介' }}</div>
              <div v-if="selectedMemberIds.includes(c.id)" class="mt-2 space-y-1" @click.stop>
                <div class="text-[10px] text-gray-500">system prompt 插入：</div>
                <div class="flex flex-wrap gap-3 text-xs text-gray-300">
                  <label class="flex items-center gap-1 cursor-pointer">
                    <input
                      type="checkbox"
                      class="accent-purple-500"
                      :checked="(groupMemberInclusions[c.id]?.includePersonality ?? true)"
                      @change="(e) => { const checked = (e.target as HTMLInputElement).checked; const inc = groupMemberInclusions[c.id] ?? { includePersonality: true, includeScenario: true }; groupMemberInclusions[c.id] = inc; inc.includePersonality = checked }"
                    />
                    Personality
                  </label>
                  <label class="flex items-center gap-1 cursor-pointer">
                    <input
                      type="checkbox"
                      class="accent-purple-500"
                      :checked="(groupMemberInclusions[c.id]?.includeScenario ?? true)"
                      @change="(e) => { const checked = (e.target as HTMLInputElement).checked; const inc = groupMemberInclusions[c.id] ?? { includePersonality: true, includeScenario: true }; groupMemberInclusions[c.id] = inc; inc.includeScenario = checked }"
                    />
                    Scenario
                  </label>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="flex items-center justify-between pt-2 border-t border-white/10">
        <div class="text-sm text-gray-500">
          已选择 {{ selectedMemberIds.length }} 个角色
          <span v-if="selectedMemberIds.length < 2" class="text-yellow-500">(至少需要2个)</span>
        </div>
        <NSpace>
          <NButton @click="showGroupCreator = false">取消</NButton>
          <NButton type="primary" :disabled="selectedMemberIds.length < 2" class="!bg-purple-500 !hover:bg-purple-600" @click="createGroupChat">
            创建群聊
          </NButton>
        </NSpace>
      </div>
    </NSpace>
  </NModal>

  <!-- 单聊创建弹窗（沿用群聊弹窗风格） -->
  <NModal v-model:show="showChatCreator" preset="card" style="width: min(520px, 90vw)" title="新建会话" class="!bg-[#18181c] !border-white/10">
    <NSpace vertical size="medium">
      <NFormItem label="会话名称（可选）">
        <NInput v-model:value="chatTitle" placeholder="新对话" />
      </NFormItem>

      <div class="bg-white/5 border border-white/10 rounded-xl p-3">
        <div class="text-sm text-gray-300 font-medium mb-2">本次聊天设置</div>
        <div class="flex items-center justify-between">
          <div class="text-sm text-gray-400">纯 AI 模式（不注入 Persona，用户发言将以 system 影响世界）</div>
          <button class="flex items-center gap-2" @click="chatPureAiMode = !chatPureAiMode">
            <div class="w-10 h-5 rounded-full relative transition-colors duration-200" :class="chatPureAiMode ? 'bg-brand' : 'bg-gray-700'">
              <div class="absolute top-1 w-3 h-3 rounded-full bg-white transition-transform duration-200" :class="chatPureAiMode ? 'left-6' : 'left-1'"></div>
            </div>
            <span class="text-xs text-gray-400">{{ chatPureAiMode ? '开启' : '关闭' }}</span>
          </button>
        </div>
      </div>

      <div class="flex justify-end pt-2 border-t border-white/10">
        <NSpace>
          <NButton @click="showChatCreator = false">取消</NButton>
          <NButton type="primary" :disabled="!selectedCharacterId" @click="confirmCreateChat">创建</NButton>
        </NSpace>
      </div>
    </NSpace>
  </NModal>

  <!-- 群成员管理弹窗 -->
  <NModal v-model:show="showMemberManager" preset="card" style="width: min(700px, 90vw)" title="管理群成员" class="!bg-[#18181c] !border-white/10">
    <NSpace vertical size="medium">
      <!-- 当前成员 -->
      <div>
        <div class="text-sm text-gray-400 mb-3">当前成员（可拖拽调整发言顺序，点击配置按钮设置独立参数）:</div>
        <div class="space-y-2 max-h-[280px] overflow-y-auto pr-2 custom-scrollbar">
          <div 
            v-for="(member, idx) in groupMembersInManager"
            :key="member.id"
            class="flex items-center justify-between p-3 rounded-xl bg-white/5"
            draggable="true"
            @dragstart="onDragStartMember(idx)"
            @dragover.prevent
            @drop="onDropMember(idx)"
          >
            <div class="flex items-center gap-3 flex-1 min-w-0">
              <span class="text-xs text-gray-500 w-5 shrink-0">{{ idx + 1 }}.</span>
              <span class="text-gray-500 select-none cursor-move w-4 text-center" title="拖拽排序">≡</span>
              <ModernAvatar 
                :src="member.avatar ? `/api/avatars/${member.avatar}` : null" 
                :name="member.name" 
                :size="36" 
                :aspect="0.75"
                rounded="rounded-lg"
              />
              <div class="flex-1 min-w-0">
                <div class="font-medium text-sm text-gray-200">{{ member.name }}</div>
                <div class="text-xs text-gray-500 truncate">{{ member.description || '暂无简介' }}</div>
                <!-- 显示成员自定义设置概览 -->
                <div v-if="getMemberSettings(member.id).model || getMemberSettings(member.id).probability < 1" class="flex gap-2 mt-1 flex-wrap">
                  <span v-if="getMemberSettings(member.id).model" class="text-[10px] bg-blue-500/20 text-blue-400 px-1.5 py-0.5 rounded">
                    {{ getMemberSettings(member.id).model }}
                  </span>
                  <span v-if="getMemberSettings(member.id).probability < 1" class="text-[10px] bg-yellow-500/20 text-yellow-400 px-1.5 py-0.5 rounded">
                    {{ Math.round(getMemberSettings(member.id).probability * 100) }}% 概率
                  </span>
                  <span v-if="getMemberSettings(member.id).temperature != null" class="text-[10px] bg-orange-500/20 text-orange-400 px-1.5 py-0.5 rounded">
                    T={{ getMemberSettings(member.id).temperature }}
                  </span>
                </div>
              </div>
            </div>
            <div class="flex items-center gap-2 shrink-0">
              <NButton size="small" secondary @click="openMemberSettingsEditor(member.id)">
                ⚙ 设置
              </NButton>
              <NPopconfirm @positive-click="removeMemberFromGroup(member.id)">
                <template #trigger>
                  <NButton size="small" quaternary type="error">移除</NButton>
                </template>
                确定移除该成员？
              </NPopconfirm>
            </div>
          </div>
          
          <!-- 用户（不可移除）（纯 AI 模式不展示用户头像） -->
          <div v-if="!effectivePureAiMode" class="flex items-center justify-between p-3 rounded-xl bg-brand/5 border border-brand/20">
            <div class="flex items-center gap-3">
              <span class="text-xs text-brand/60 w-5">—</span>
              <ModernAvatar 
                :src="userAvatarUrl" 
                :name="userName" 
                :size="36" 
                aspect="1"
                rounded="rounded-lg"
              />
              <div>
                <div class="font-medium text-sm text-brand">{{ userName }}</div>
                <div class="text-xs text-brand/60">你是群成员之一</div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 可添加的成员 -->
      <div v-if="availableMembers.length > 0">
        <div class="text-sm text-gray-400 mb-3">添加成员:</div>
        <div class="grid grid-cols-2 gap-2 max-h-[200px] overflow-y-auto pr-2 custom-scrollbar">
          <div 
            v-for="c in availableMembers"
            :key="c.id"
            class="flex items-center gap-3 p-2 rounded-xl bg-white/5 hover:bg-white/10 cursor-pointer transition-colors"
            @click="addMemberToGroup(c.id)"
          >
            <ModernAvatar 
              :src="c.avatar ? `/api/avatars/${c.avatar}` : null" 
              :name="c.name" 
              :size="32" 
              :aspect="0.75"
              rounded="rounded-lg"
            />
            <div class="flex-1 min-w-0">
              <div class="font-medium text-sm text-gray-300 truncate">{{ c.name }}</div>
            </div>
            <span class="text-green-500 text-lg">+</span>
          </div>
        </div>
      </div>

      <!-- 延迟时间设置 -->
      <div class="pt-2 border-t border-white/10">
        <div class="text-sm text-gray-400 mb-2">角色发言间隔:</div>
        <div class="flex items-center gap-3">
          <NInputNumber 
            :value="activeChat?.groupDelay || 1500" 
            :min="0" 
            :max="30000" 
            :step="500"
            class="!w-32"
            @update:value="updateGroupDelay"
          >
            <template #suffix>毫秒</template>
          </NInputNumber>
          <div class="flex gap-2">
            <button 
              class="px-2 py-1 text-xs rounded bg-white/5 hover:bg-white/10 text-gray-400"
              @click="updateGroupDelay(0)"
            >无延迟</button>
            <button 
              class="px-2 py-1 text-xs rounded bg-white/5 hover:bg-white/10 text-gray-400"
              @click="updateGroupDelay(1500)"
            >1.5秒</button>
            <button 
              class="px-2 py-1 text-xs rounded bg-white/5 hover:bg-white/10 text-gray-400"
              @click="updateGroupDelay(3000)"
            >3秒</button>
          </div>
        </div>
      </div>

      <div class="flex justify-end pt-2 border-t border-white/10">
        <NButton @click="finishMemberManager">完成</NButton>
      </div>
    </NSpace>
  </NModal>

  <!-- 成员设置编辑弹窗 -->
  <NModal 
    :show="!!editingMemberId" 
    preset="card" 
    style="width: min(500px, 90vw)" 
    title="成员设置" 
    class="!bg-[#18181c] !border-white/10" 
    @update:show="(v: boolean) => !v && closeMemberSettingsEditor()"
  >
    <NSpace vertical size="medium">
      <!-- 角色信息 -->
      <div v-if="editingMemberId" class="flex items-center gap-3 pb-3 border-b border-white/10">
        <ModernAvatar 
          :src="getCharacterById(editingMemberId)?.avatar ? `/api/avatars/${getCharacterById(editingMemberId)?.avatar}` : null" 
          :name="getCharacterById(editingMemberId)?.name || ''" 
          :size="48" 
          :aspect="0.75"
          rounded="rounded-lg"
        />
        <div>
          <div class="font-bold text-lg text-gray-200">{{ getCharacterById(editingMemberId)?.name }}</div>
          <div class="text-xs text-gray-500">独立设置（覆盖全局）</div>
        </div>
      </div>

      <!-- 模型绑定 -->
      <NFormItem label="绑定模型">
        <ModernSelect
          v-model:model-value="editingMemberSettings.model"
          :options="chatModelOptions"
          placement="bottom"
          placeholder="使用全局模型..."
          class="!w-full"
          searchable
          allow-create
          @select="(opt: any) => { editingMemberSettings.model = opt.value; editingMemberSettings.presetId = opt.presetId }"
        />
      </NFormItem>

      <!-- Temperature -->
      <NFormItem label="Temperature (覆写)">
        <NInputNumber 
          v-model:value="editingMemberSettings.temperature"
          :min="0" 
          :max="2" 
          :step="0.1"
          clearable
          placeholder="使用全局设置"
          class="!w-full"
        />
      </NFormItem>

      <!-- Top P -->
      <NFormItem label="Top P (覆写)">
        <NInputNumber 
          v-model:value="editingMemberSettings.top_p"
          :min="0" 
          :max="1" 
          :step="0.05"
          clearable
          placeholder="使用全局设置"
          class="!w-full"
        />
      </NFormItem>

      <!-- 参与概率 -->
      <NFormItem label="参与概率">
        <div class="flex items-center gap-3 w-full">
          <NInputNumber 
            v-model:value="editingMemberSettings.probability"
            :min="0" 
            :max="1" 
            :step="0.1"
            class="!w-32"
          />
          <div class="flex-1">
            <div class="h-2 bg-white/10 rounded-full overflow-hidden">
              <div 
                class="h-full bg-gradient-to-r from-yellow-500 to-green-500 transition-all"
                :style="{ width: `${editingMemberSettings.probability * 100}%` }"
              ></div>
            </div>
          </div>
          <span class="text-sm text-gray-400 w-12 text-right">{{ Math.round(editingMemberSettings.probability * 100) }}%</span>
        </div>
        <div class="text-xs text-gray-500 mt-1">设置为 100% 表示每轮必定发言，低于 100% 则按概率随机参与</div>
      </NFormItem>

      <!-- system prompt 插入字段 -->
      <NFormItem label="system prompt 插入字段">
        <div class="flex flex-col gap-2 w-full">
          <div class="flex flex-wrap gap-4">
            <label class="flex items-center gap-2 text-sm text-gray-300 cursor-pointer">
              <input type="checkbox" class="accent-brand" v-model="editingMemberSettings.includePersonality" />
              插入 Personality
            </label>
            <label class="flex items-center gap-2 text-sm text-gray-300 cursor-pointer">
              <input type="checkbox" class="accent-brand" v-model="editingMemberSettings.includeScenario" />
              插入 Scenario
            </label>
          </div>
          <div class="text-xs text-gray-500">
            关闭后，该成员对应字段将不会被注入到本轮/后续的 system prompt（用于避免多人共享世界观时的重复设定）。
          </div>
        </div>
      </NFormItem>

      <NSpace justify="end" class="pt-2 border-t border-white/10">
        <NButton @click="closeMemberSettingsEditor">取消</NButton>
        <NButton type="primary" @click="saveMemberSettings">保存</NButton>
      </NSpace>
    </NSpace>
  </NModal>
</template>

<style scoped>
/* 自定义滚动条样式，比全局的更细一些 */
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

/* Markdown 内容样式微调 */
.md :deep(p) {
  margin-bottom: 0.5em;
  margin-top: 0.5em;
}
.md :deep(p:first-child) {
  margin-top: 0;
}
.md :deep(p:last-child) {
  margin-bottom: 0;
}
.md :deep(a) {
  color: #a78bfa;
  text-decoration: underline;
}
</style>
