<script setup lang="ts">
import { computed, onMounted, ref, watch, nextTick } from 'vue'
import MarkdownIt from 'markdown-it'

import { useCharactersStore, useChatsStore, useSettingsStore } from '../stores'
import type { CharacterCard, ChatMessage, UserPersona } from '../types/models'
import SettingsDrawer from '../components/SettingsDrawer.vue'
import AvatarCropper from '../components/AvatarCropper.vue'
import ModernAvatar from '../components/ModernAvatar.vue'
import ModernSelect from '../components/ModernSelect.vue'
import { postAndConsumeSse } from '../api/sse'
import { apiPost } from '../api/http'

import {
  NButton,
  NDivider,
  NDropdown,
  NForm,
  NFormItem,
  NInput,
  NModal,
  NPopconfirm,
  NSpace,
  NTag,
  NTooltip
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

const md = new MarkdownIt({
  html: false, // 禁止原始 HTML，避免模型输出导致 XSS
  linkify: true,
  breaks: true,
})

function renderMarkdown(text: string) {
  return md.render(text ?? '')
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

// 获取选中的 Persona
const selectedPersona = computed(() => {
  if (!settings.settings?.selectedPersonaId || !settings.settings?.userPersonas) return null
  return settings.settings.userPersonas.find(p => p.id === settings.settings!.selectedPersonaId) ?? null
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

function roleTagType(role: ChatMessage['role']) {
  if (role === 'user') return 'info'
  if (role === 'assistant') return 'success'
  return 'warning'
}

function getMessageLabel(role: ChatMessage['role']) {
  if (role === 'user') return userName.value
  if (role === 'assistant') return selectedCharacter.value?.name || 'AI'
  return '系统'
}

function getMessageAvatar(role: ChatMessage['role']) {
  if (role === 'user') return userAvatarUrl.value
  if (role === 'assistant') return characterAvatarUrl.value
  return null
}

async function createChat() {
  if (!selectedCharacterId.value) return
  await chats.create(selectedCharacterId.value)
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
  await settings.save({
    ...settings.settings,
    selectedPersonaId: id,
  })
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

async function sendUserMessage() {
  const text = draftMessage.value.trim()
  if (!text) return
  if (!activeChat.value) return
  if (isGenerating.value) return
  draftMessage.value = ''
  streamError.value = null

  const chatId = activeChat.value.id
  const now = new Date().toISOString()
  const localUserId = `local_user_${Date.now()}`
  const localAssistantId = `local_assistant_${Date.now()}`

  activeChat.value.messages.push({ version: 1, id: localUserId, role: 'user', content: text, ts: now })
  const assistantMsg: ChatMessage = { version: 1, id: localAssistantId, role: 'assistant', content: '', ts: now }
  activeChat.value.messages.push(assistantMsg)
  
  scrollToBottom()

  isGenerating.value = true
  aborter?.abort()
  aborter = new AbortController()

  const useStream = settings.settings?.streamEnabled !== false

  try {
    if (useStream) {
      await postAndConsumeSse(
        '/api/generate/stream',
        { chatId, userMessage: text },
        (evt) => {
          if (evt.event === 'delta') {
            const t = evt.data?.text
            if (typeof t === 'string') {
              assistantMsg.content += t
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
        content: string
        error?: string
      }>('/api/generate/stream', { chatId, userMessage: text })
      
      if (res.ok) {
        assistantMsg.content = res.content
        scrollToBottom()
      } else {
        streamError.value = res.error || 'unknown error'
      }
    }
  } catch (e: any) {
    streamError.value = e?.message ?? String(e)
  } finally {
    isGenerating.value = false
    await chats.load(chatId)
    await settings.load()
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
              :class="settings.settings?.selectedPersonaId === p.id ? 'bg-brand/10 border-brand/20' : 'hover:bg-white/5'"
              @click="selectPersona(p.id)"
            >
              <ModernAvatar :src="p.avatar ? `/api/avatars/${p.avatar}` : null" :name="p.name" :size="36" aspect="1" />
              <div class="flex-1 min-w-0">
                <div class="font-medium text-sm truncate" :class="settings.settings?.selectedPersonaId === p.id ? 'text-brand' : 'text-gray-300'">{{ p.name }}</div>
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
            <button 
              class="text-xs bg-brand/20 hover:bg-brand/30 text-brand px-2 py-1 rounded transition-colors disabled:opacity-50 disabled:cursor-not-allowed" 
              :disabled="!selectedCharacterId" 
              @click="createChat"
            >
              新建会话
            </button>
          </div>
          <div class="flex-1 overflow-y-auto p-2 custom-scrollbar">
            <div 
              v-for="c in chats.list"
              :key="c.id"
              class="group flex items-center justify-between p-2 rounded-lg cursor-pointer text-sm mb-1 transition-colors"
              :class="chats.activeChatId === c.id ? 'bg-brand/10 text-brand' : 'text-gray-400 hover:bg-white/5 hover:text-gray-200'"
              @click="chats.load(c.id)"
            >
              <div class="flex-1 min-w-0 pr-2">
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
            <div v-if="!chats.list.length" class="text-center text-xs text-gray-600 py-4">
              无历史会话
            </div>
          </div>
        </div>
      </div>
    </aside>

    <!-- 右侧主区域 -->
    <main class="flex-1 flex flex-col relative min-w-0 bg-[#101014]">
      
      <!-- 聊天内容区 -->
      <div v-if="selectedCharacter && activeChat" class="flex flex-col h-full relative">
        <!-- 顶部标题栏 (悬浮) -->
        <header class="absolute top-0 left-0 right-0 z-10 h-16 flex items-center justify-between px-6 bg-gradient-to-b from-[#101014] via-[#101014]/90 to-transparent pointer-events-none">
          <div class="pointer-events-auto flex items-center gap-3">
             <h2 class="text-lg font-bold text-gray-100 shadow-sm">{{ selectedCharacter.name }}</h2>
             <span class="text-gray-600">/</span>
             <span class="text-sm text-gray-400">{{ activeChat.title }}</span>
          </div>
          <div class="pointer-events-auto">
            <NButton size="small" secondary type="primary" class="!bg-brand/10 !text-brand hover:!bg-brand/20" @click="showSettings = true">
              设置
            </NButton>
          </div>
        </header>

        <!-- 消息列表 -->
        <div ref="messagesScrollRef" class="flex-1 overflow-y-auto p-4 pt-20 pb-4 scroll-smooth custom-scrollbar">
          <div class="max-w-4xl mx-auto space-y-8">
            <div v-for="m in activeChat.messages" :key="m.id" class="flex gap-4 group" :class="m.role === 'user' ? 'flex-row-reverse' : 'flex-row'">
              
              <!-- 头像 -->
              <div class="flex-shrink-0 mt-1">
                 <div v-if="m.role === 'system'" class="w-10 h-10 rounded-full bg-yellow-500/20 flex items-center justify-center text-yellow-500">
                   ⚙
                 </div>
                 <ModernAvatar 
                   v-else
                   :src="getMessageAvatar(m.role)"
                   :name="getMessageLabel(m.role)"
                   :size="40"
                   aspect="1"
                   rounded="rounded-xl"
                   class="shadow-sm"
                 />
              </div>

              <!-- 消息体 -->
              <div class="flex flex-col max-w-[85%] min-w-0" :class="m.role === 'user' ? 'items-end' : 'items-start'">
                <div class="flex items-center gap-2 mb-1 px-1">
                  <span class="text-xs font-bold" :class="m.role === 'user' ? 'text-brand-300' : 'text-gray-400'">
                    {{ getMessageLabel(m.role) }}
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
                placeholder="发送消息..."
                :autosize="{ minRows: 2, maxRows: 8 }"
                class="!bg-transparent !border-0 text-base"
                style="--n-border: none; --n-box-shadow-focus: none;"
                @keydown.ctrl.enter="sendUserMessage"
              />
              
              <div class="flex items-center justify-between pt-2 border-t border-white/5">
                 <div class="text-xs text-red-400 truncate max-w-[300px]">{{ streamError }}</div>
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
                      :disabled="!draftMessage.trim() || isGenerating"
                      @click="sendUserMessage"
                    >
                      {{ isGenerating ? '生成中...' : '发送' }}
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
              <NFormItem label="名称">
                <NInput v-model:value="editingCharacter.name" placeholder="角色名称" />
              </NFormItem>
              <NFormItem label="简介">
                <NInput v-model:value="editingCharacter.description" type="textarea" :autosize="{ minRows: 2, maxRows: 3 }" placeholder="简短描述" />
              </NFormItem>
           </div>
        </div>

        <NFormItem label="Personality（性格/外貌）">
          <NInput v-model:value="editingCharacter.personality" type="textarea" :autosize="{ minRows: 2, maxRows: 5 }" placeholder="详细设定..." />
        </NFormItem>

        <NFormItem label="Scenario（情景/世界观）">
          <NInput v-model:value="editingCharacter.scenario" type="textarea" :autosize="{ minRows: 2, maxRows: 4 }" placeholder="世界背景..." />
        </NFormItem>

        <NFormItem label="系统提示词">
          <NInput v-model:value="editingCharacter.systemPrompt" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" placeholder="回复格式要求..." />
        </NFormItem>

        <NFormItem>
          <template #label>
            <span>首句</span>
            <span class="opacity-60 text-xs ml-2">支持 {<!-- -->{user}} 占位符</span>
          </template>
          <NInput v-model:value="editingCharacter.firstMessage" type="textarea" :autosize="{ minRows: 2, maxRows: 4 }" placeholder="开场白..." />
        </NFormItem>

        <NSpace justify="end">
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
