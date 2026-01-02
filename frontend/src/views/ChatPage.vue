<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import MarkdownIt from 'markdown-it'

import { useCharactersStore, useChatsStore, useSettingsStore } from '../stores'
import type { CharacterCard, ChatMessage, UserPersona } from '../types/models'
import SettingsDrawer from '../components/SettingsDrawer.vue'
import AvatarCropper from '../components/AvatarCropper.vue'
import { postAndConsumeSse } from '../api/sse'
import { apiPost } from '../api/http'

import {
  NAlert,
  NAvatar,
  NButton,
  NCard,
  NDivider,
  NDropdown,
  NForm,
  NFormItem,
  NInput,
  NLayout,
  NLayoutContent,
  NLayoutSider,
  NList,
  NListItem,
  NModal,
  NPopconfirm,
  NSpace,
  NTag,
  NText,
  NTooltip,
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

// 快速模型切换
const usedModelsOptions = computed(() => {
  const usedModels = settings.settings?.llm.usedModels ?? []
  return usedModels.map((m) => ({ label: m, key: m }))
})

const currentModel = computed(() => {
  return chats.activeChat?.overrides?.params?.model || settings.settings?.llm.defaultModel || '未设置'
})

async function selectModel(key: string) {
  if (!chats.activeChat) return
  const overrides = { ...chats.activeChat.overrides }
  overrides.params = { ...overrides.params, model: key }
  await chats.updateOverrides(chats.activeChat.id, overrides)
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
            if (typeof t === 'string') assistantMsg.content += t
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
  <div class="main-container">
    <NLayout has-sider class="centered-layout">
      <!-- 收起按钮 -->
      <div class="sidebar-toggle" @click="sidebarCollapsed = !sidebarCollapsed">
        <NTooltip trigger="hover" :placement="sidebarCollapsed ? 'right' : 'left'">
          <template #trigger>
            <div class="toggle-btn">
              {{ sidebarCollapsed ? '▶' : '◀' }}
            </div>
          </template>
          {{ sidebarCollapsed ? '展开侧栏' : '收起侧栏' }}
        </NTooltip>
      </div>

      <NLayoutSider
        v-show="!sidebarCollapsed"
        bordered
        width="320"
        style="padding: 12px; overflow-y: auto"
        class="sidebar-animated"
      >
        <NSpace vertical>
          <!-- 用户 Persona 区域 -->
          <NSpace justify="space-between" align="center">
            <NText strong>我的身份</NText>
            <NButton size="tiny" type="primary" @click="openCreatePersona">+新建</NButton>
          </NSpace>
          <NList bordered hoverable clickable size="small">
            <NListItem
              v-for="p in (settings.settings?.userPersonas || [])"
              :key="p.id"
              :style="{
                cursor: 'pointer',
                backgroundColor: settings.settings?.selectedPersonaId === p.id ? 'rgba(162, 48, 237, 0.15)' : 'transparent',
                transition: 'background-color 0.3s'
              }"
              @click="selectPersona(p.id)"
            >
              <NSpace align="center" justify="space-between" style="width: 100%">
                <NSpace align="center">
                  <NAvatar
                    v-if="p.avatar"
                    :src="`/api/avatars/${p.avatar}`"
                    :size="28"
                    round
                  />
                  <NAvatar v-else :size="28" round style="background: rgba(162, 48, 237, 0.3)">
                    {{ p.name[0] || '?' }}
                  </NAvatar>
                  <NText :style="{ color: settings.settings?.selectedPersonaId === p.id ? '#a230ed' : 'inherit' }">{{ p.name }}</NText>
                </NSpace>
                <NSpace size="small">
                  <NButton size="tiny" quaternary @click.stop="openEditPersona(p)">✏</NButton>
                  <NPopconfirm @positive-click="deletePersona(p.id)">
                    <template #trigger>
                      <NButton size="tiny" quaternary type="error" @click.stop>🗑</NButton>
                    </template>
                    确定删除这个身份？
                  </NPopconfirm>
                </NSpace>
              </NSpace>
            </NListItem>
            <NListItem v-if="!settings.settings?.userPersonas?.length" style="opacity: 0.6; font-size: 12px">
              点击"新建"创建你的第一个身份
            </NListItem>
          </NList>

          <NDivider style="margin: 8px 0" />

          <!-- 角色区域 -->
          <NSpace justify="space-between" align="center">
            <NText strong>角色</NText>
            <NButton size="tiny" type="primary" @click="openCreateCharacter">+新建</NButton>
          </NSpace>

          <NList bordered hoverable clickable>
            <NListItem
              v-for="c in characters.list"
              :key="c.id"
              :style="{
                cursor: 'pointer',
                backgroundColor: selectedCharacterId === c.id ? 'rgba(162, 48, 237, 0.15)' : 'transparent',
                transition: 'background-color 0.3s'
              }"
              @click="selectedCharacterId = c.id"
            >
              <NSpace align="center" justify="space-between" style="width: 100%">
                <NSpace align="center">
                  <NAvatar
                    v-if="c.avatar"
                    :src="`/api/avatars/${c.avatar}`"
                    :size="32"
                    round
                  />
                  <NAvatar v-else :size="32" round style="background: rgba(162, 48, 237, 0.3)">
                    {{ c.name[0] || '?' }}
                  </NAvatar>
                  <div style="flex: 1; min-width: 0">
                    <div><NText strong :style="{ color: selectedCharacterId === c.id ? '#a230ed' : 'inherit' }">{{ c.name }}</NText></div>
                    <div style="opacity: 0.65; font-size: 11px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 140px">{{ c.description }}</div>
                  </div>
                </NSpace>
                <NSpace size="small">
                  <NButton size="tiny" quaternary @click.stop="openEditCharacter(c)">✏</NButton>
                  <NPopconfirm @positive-click="deleteCharacter(c.id)">
                    <template #trigger>
                      <NButton size="tiny" quaternary type="error" @click.stop>🗑</NButton>
                    </template>
                    <div style="max-width: 200px">
                      <p style="margin: 0 0 4px 0">确定删除此角色？</p>
                      <p style="margin: 0; opacity: 0.7; font-size: 12px">将同时删除所有关联会话</p>
                    </div>
                  </NPopconfirm>
                </NSpace>
              </NSpace>
            </NListItem>
          </NList>

          <NDivider style="margin: 8px 0" />

          <!-- 会话区域 -->
          <NSpace justify="space-between" align="center">
            <NText strong>会话</NText>
            <NButton size="small" secondary type="primary" :disabled="!selectedCharacterId" @click="createChat">新建会话</NButton>
          </NSpace>
          <NList bordered hoverable clickable>
            <NListItem
              v-for="c in chats.list"
              :key="c.id"
              :style="{
                cursor: 'pointer',
                backgroundColor: chats.activeChatId === c.id ? 'rgba(162, 48, 237, 0.1)' : 'transparent',
                transition: 'background-color 0.3s'
              }"
              @click="chats.load(c.id)"
            >
              <NSpace justify="space-between" align="center" style="width: 100%">
                <div style="flex: 1; min-width: 0">
                  <div v-if="editingChatId === c.id" @click.stop>
                    <NSpace>
                      <NInput
                        v-model:value="editingTitle"
                        size="small"
                        style="width: 120px"
                        @keyup.enter="saveTitle"
                        @keyup.escape="cancelEditTitle"
                      />
                      <NButton size="tiny" type="primary" @click="saveTitle">✓</NButton>
                      <NButton size="tiny" @click="cancelEditTitle">✕</NButton>
                    </NSpace>
                  </div>
                  <div v-else :style="{ color: chats.activeChatId === c.id ? '#a230ed' : 'inherit', fontSize: '13px' }">
                    {{ c.title }}
                  </div>
                </div>
                <NSpace v-if="editingChatId !== c.id" align="center" size="small">
                  <NButton size="tiny" quaternary @click.stop="startEditTitle(c.id, c.title)">✏</NButton>
                  <NPopconfirm @positive-click="deleteChat(c.id)">
                    <template #trigger>
                      <NButton size="tiny" quaternary type="error" @click.stop>🗑</NButton>
                    </template>
                    确定要删除这个会话吗？
                  </NPopconfirm>
                </NSpace>
              </NSpace>
            </NListItem>
          </NList>
        </NSpace>
      </NLayoutSider>

      <NLayoutContent style="padding: 24px">
        <div style="max-width: 900px; margin: 0 auto">
          <NCard v-if="selectedCharacter && activeChat" :title="`${selectedCharacter.name} / ${activeChat.title}`" bordered>
            <template #header-extra>
              <NButton size="small" @click="showSettings = true">高级设置</NButton>
            </template>
            <div style="height: calc(100vh - 320px); overflow: auto; padding-right: 8px">
              <NSpace vertical size="large">
                <div v-for="m in activeChat.messages" :key="m.id" class="msg-row">
                  <!-- 头像：system 用固定图标，其余用 Persona/角色头像 -->
                  <NAvatar
                    v-if="m.role === 'system'"
                    :size="28"
                    round
                    class="msg-avatar"
                    style="background: rgba(245, 158, 11, 0.25); color: rgba(255,255,255,0.95)"
                  >
                    ⚙
                  </NAvatar>
                  <NAvatar
                    v-else-if="getMessageAvatar(m.role)"
                    :src="getMessageAvatar(m.role)!"
                    :size="28"
                    round
                    class="msg-avatar"
                  />
                  <NAvatar
                    v-else
                    :size="28"
                    round
                    class="msg-avatar"
                    :style="{ background: m.role === 'user' ? 'rgba(162, 48, 237, 0.3)' : 'rgba(124, 58, 237, 0.3)' }"
                  >
                    {{ getMessageLabel(m.role)[0] }}
                  </NAvatar>

                  <div class="msg-body">
                    <div class="msg-meta">
                      <NTag size="tiny" :type="roleTagType(m.role)" round :bordered="false">{{ getMessageLabel(m.role) }}</NTag>
                    </div>
                    <div class="msg-bubble" :class="m.role === 'user' ? 'is-user' : 'is-assistant'">
                      <div class="md" v-html="renderMarkdown(m.content)"></div>
                    </div>
                    <div class="msg-actions">
                      <NButton
                        size="tiny"
                        quaternary
                        :disabled="isGenerating || m.id.startsWith('local_')"
                        @click="openEditMessage(m)"
                      >
                        ✏
                      </NButton>
                      <NPopconfirm @positive-click="deleteMessage(m)">
                        <template #trigger>
                          <NButton
                            size="tiny"
                            quaternary
                            type="error"
                            :disabled="isGenerating || m.id.startsWith('local_')"
                          >
                            🗑
                          </NButton>
                        </template>
                        确定删除这条消息？
                      </NPopconfirm>
                    </div>
                  </div>
                </div>
              </NSpace>
            </div>

            <NDivider />

            <div class="chat-input-area">
              <NInput
                v-model:value="draftMessage"
                type="textarea"
                placeholder="输入你的消息…"
                :autosize="{ minRows: 3, maxRows: 8 }"
                class="chat-input"
              />
              <div class="chat-actions">
                <NText v-if="streamError" type="error" style="font-size: 12px; white-space: pre-wrap; flex: 1">{{ streamError }}</NText>
                <div style="flex: 1" v-else></div>
                <NSpace align="center">
                  <NDropdown
                    :options="usedModelsOptions"
                    trigger="click"
                    :disabled="usedModelsOptions.length === 0"
                    @select="selectModel"
                  >
                    <NButton size="small" secondary :disabled="usedModelsOptions.length === 0">
                      {{ currentModel }}
                    </NButton>
                  </NDropdown>
                  <NButton type="primary" :disabled="!draftMessage.trim() || isGenerating" @click="sendUserMessage">
                    {{ isGenerating ? '生成中…' : '发送' }}
                  </NButton>
                </NSpace>
              </div>
            </div>
          </NCard>

          <NCard v-else bordered title="开始聊天">
            <div v-if="!characters.list.length" style="text-align: center; padding: 40px 0">
              <NText depth="3" style="display: block; margin-bottom: 16px">还没有角色。请先创建一个角色。</NText>
              <NButton type="primary" @click="openCreateCharacter">创建角色</NButton>
            </div>
            <div v-else style="text-align: center; padding: 40px 0">
              <NText depth="3">请从左侧选择角色并点击"新建会话"开始聊天。</NText>
            </div>
          </NCard>
        </div>
      </NLayoutContent>
    </NLayout>
  </div>

  <SettingsDrawer v-model:show="showSettings" :chat="activeChat" />

  <!-- 消息编辑弹窗 -->
  <NModal v-model:show="showMessageEditor" preset="card" style="width: min(700px, 92vw)" title="编辑消息">
    <NForm label-placement="top">
      <NSpace vertical size="medium">
        <NFormItem label="发送者 / 头像（选择会直接改变该条消息的角色）">
          <NSpace size="small" wrap>
            <NButton
              size="tiny"
              :type="editingMessageRole === 'system' ? 'primary' : 'default'"
              @click="editingMessageRole = 'system'"
            >
              <NSpace align="center" size="small">
                <NAvatar :size="20" round style="background: rgba(245, 158, 11, 0.25)">⚙</NAvatar>
                <span>系统</span>
              </NSpace>
            </NButton>
            <NButton
              size="tiny"
              :type="editingMessageRole === 'assistant' ? 'primary' : 'default'"
              @click="editingMessageRole = 'assistant'"
            >
              <NSpace align="center" size="small">
                <NAvatar
                  v-if="characterAvatarUrl"
                  :src="characterAvatarUrl"
                  :size="20"
                  round
                />
                <NAvatar v-else :size="20" round style="background: rgba(124, 58, 237, 0.3)">
                  {{ (selectedCharacter?.name || 'A')[0] }}
                </NAvatar>
                <span>角色</span>
              </NSpace>
            </NButton>
            <NButton
              size="tiny"
              :type="editingMessageRole === 'user' ? 'primary' : 'default'"
              @click="editingMessageRole = 'user'"
            >
              <NSpace align="center" size="small">
                <NAvatar
                  v-if="userAvatarUrl"
                  :src="userAvatarUrl"
                  :size="20"
                  round
                />
                <NAvatar v-else :size="20" round style="background: rgba(162, 48, 237, 0.3)">
                  {{ (userName || '你')[0] }}
                </NAvatar>
                <span>用户</span>
              </NSpace>
            </NButton>
          </NSpace>
        </NFormItem>

        <NFormItem label="内容">
          <NInput
            v-model:value="editingMessageContent"
            type="textarea"
            :autosize="{ minRows: 6, maxRows: 18 }"
            placeholder="输入消息内容（支持 Markdown）"
            style="width: 100%"
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
  <NModal v-model:show="showCharacterEditor" preset="card" style="width: min(700px, 90vw)" :title="isNewCharacter ? '新建角色' : '编辑角色'">
    <NForm v-if="editingCharacter" label-placement="top">
      <NSpace vertical size="medium">
        <NFormItem label="头像">
          <NSpace align="center">
            <NAvatar
              v-if="editingCharacterAvatarUrl"
              :src="editingCharacterAvatarUrl"
              :size="56"
              round
              style="border: 2px solid rgba(162, 48, 237, 0.5)"
            />
            <NAvatar v-else :size="56" round style="background: rgba(162, 48, 237, 0.3)">
              {{ editingCharacter.name?.[0] || '?' }}
            </NAvatar>
            <NButton size="small" @click="showCharacterAvatarCropper = true">
              {{ editingCharacterAvatarUrl ? '更换' : '设置头像' }}
            </NButton>
          </NSpace>
        </NFormItem>

        <NFormItem label="名称">
          <NInput v-model:value="editingCharacter.name" placeholder="角色名称" style="width: 100%" />
        </NFormItem>

        <NFormItem label="简介">
          <NInput v-model:value="editingCharacter.description" type="textarea" :autosize="{ minRows: 2, maxRows: 3 }" placeholder="简短描述" style="width: 100%" />
        </NFormItem>

        <NFormItem label="Personality（性格/外貌）">
          <NInput v-model:value="editingCharacter.personality" type="textarea" :autosize="{ minRows: 2, maxRows: 5 }" placeholder="角色的性格、外貌等" style="width: 100%" />
        </NFormItem>

        <NFormItem label="Scenario（情景/世界观）">
          <NInput v-model:value="editingCharacter.scenario" type="textarea" :autosize="{ minRows: 2, maxRows: 4 }" placeholder="世界背景或谈话环境" style="width: 100%" />
        </NFormItem>

        <NFormItem label="系统提示词">
          <NInput v-model:value="editingCharacter.systemPrompt" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" placeholder="回复例句、格式要求等" style="width: 100%" />
        </NFormItem>

        <NFormItem>
          <template #label>
            <span>首句</span>
            <span style="opacity: 0.6; font-size: 11px; margin-left: 6px">支持 {<!-- -->{user}} 占位符</span>
          </template>
          <NInput v-model:value="editingCharacter.firstMessage" type="textarea" :autosize="{ minRows: 2, maxRows: 4 }" placeholder="新建会话时的第一条消息" style="width: 100%" />
        </NFormItem>

        <NSpace justify="end">
          <NButton @click="showCharacterEditor = false">取消</NButton>
          <NButton type="primary" @click="saveCharacter">保存</NButton>
        </NSpace>
      </NSpace>
    </NForm>
  </NModal>

  <!-- Persona 编辑弹窗 -->
  <NModal v-model:show="showPersonaEditor" preset="card" style="width: min(500px, 90vw)" :title="isNewPersona ? '新建身份' : '编辑身份'">
    <NForm v-if="editingPersona" label-placement="top">
      <NSpace vertical size="medium">
        <NAlert type="info" style="margin-bottom: 8px">
          用户身份用于在对话中标识你。姓名将替换角色首句中的 <code style="background: rgba(255,255,255,0.1); padding: 1px 4px; border-radius: 3px">{<!-- -->{user}}</code>，并在系统提示词中介绍你的身份。
        </NAlert>

        <NFormItem label="头像">
          <NSpace align="center">
            <NAvatar
              v-if="editingPersonaAvatarUrl"
              :src="editingPersonaAvatarUrl"
              :size="56"
              round
              style="border: 2px solid rgba(162, 48, 237, 0.5)"
            />
            <NAvatar v-else :size="56" round style="background: rgba(162, 48, 237, 0.3)">
              {{ editingPersona.name?.[0] || '?' }}
            </NAvatar>
            <NButton size="small" @click="showPersonaAvatarCropper = true">
              {{ editingPersonaAvatarUrl ? '更换' : '设置头像' }}
            </NButton>
          </NSpace>
        </NFormItem>

        <NFormItem label="姓名（{{user}}）">
          <NInput v-model:value="editingPersona.name" placeholder="你的角色名称" style="width: 100%" />
        </NFormItem>

        <NFormItem label="简介">
          <NInput
            v-model:value="editingPersona.description"
            type="textarea"
            :autosize="{ minRows: 3, maxRows: 6 }"
            placeholder="你的角色身份、背景等"
            style="width: 100%"
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
.main-container {
  display: flex;
  justify-content: center;
  width: 100%;
  height: 100vh;
  background-color: #101014;
}

.centered-layout {
  max-width: 1400px;
  width: 100%;
  height: 100%;
  border-left: 1px solid rgba(255, 255, 255, 0.1);
  border-right: 1px solid rgba(255, 255, 255, 0.1);
  position: relative;
}

.sidebar-toggle {
  position: absolute;
  left: 0;
  top: 50%;
  transform: translateY(-50%);
  z-index: 100;
  cursor: pointer;
}

.toggle-btn {
  background: rgba(162, 48, 237, 0.3);
  border: 1px solid rgba(162, 48, 237, 0.5);
  border-left: none;
  border-radius: 0 8px 8px 0;
  padding: 12px 6px;
  color: #fff;
  font-size: 12px;
  transition: all 0.3s;
}

.toggle-btn:hover {
  background: rgba(162, 48, 237, 0.5);
}

.sidebar-animated {
  transition: all 0.3s ease;
}

.chat-input-area {
  display: flex;
  flex-direction: column;
  gap: 12px;
  width: 100%;
}

.chat-input {
  width: 100%;
}

.chat-input :deep(textarea) {
  min-height: 80px !important;
}

.chat-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.msg-row {
  display: flex;
  align-items: flex-start;
  justify-content: flex-start;
  gap: 10px;
}

.msg-avatar {
  flex: 0 0 auto;
  margin-top: 2px;
}

.msg-body {
  flex: 1 1 auto;
  min-width: 0;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
}

.msg-meta {
  margin-bottom: 4px;
}

.msg-actions {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-top: 6px;
  opacity: 0;
  transition: opacity 0.15s ease;
}

.msg-row:hover .msg-actions {
  opacity: 1;
}

.msg-actions :deep(.n-button) {
  padding: 0 6px;
}

.msg-bubble {
  max-width: 80%;
  padding: 10px 14px;
  border-radius: 12px;
  color: rgba(255, 255, 255, 0.9);
  overflow: hidden;
}

.msg-bubble.is-user {
  background-color: rgba(162, 48, 237, 0.2);
  border: 1px solid rgba(162, 48, 237, 0.3);
}

.msg-bubble.is-assistant {
  background-color: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.1);
}

.md :deep(*) {
  margin: 0;
}

.md :deep(p) {
  margin: 0.2em 0;
  line-height: 1.65;
  word-break: break-word;
}

.md :deep(pre) {
  margin: 0.4em 0;
  padding: 10px 12px;
  border-radius: 10px;
  background: rgba(0, 0, 0, 0.35);
  border: 1px solid rgba(255, 255, 255, 0.08);
  overflow: auto;
}

.md :deep(code) {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace;
  font-size: 0.92em;
}

.md :deep(:not(pre) > code) {
  padding: 1px 6px;
  border-radius: 6px;
  background: rgba(0, 0, 0, 0.25);
  border: 1px solid rgba(255, 255, 255, 0.08);
}

.md :deep(ul),
.md :deep(ol) {
  margin: 0.2em 0 0.2em 1.2em;
  padding: 0;
}

.md :deep(blockquote) {
  margin: 0.35em 0;
  padding: 0.2em 0 0.2em 0.9em;
  border-left: 3px solid rgba(162, 48, 237, 0.6);
  color: rgba(255, 255, 255, 0.75);
}
</style>
