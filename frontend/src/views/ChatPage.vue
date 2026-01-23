<script setup lang="ts">
/**
 * ChatPage - 聊天主页面
 * 风格：Obsidian Brutalist (Hairline System)
 * 目标：完整功能恢复与极致 UI 体验
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
import ModernAvatar from '../components/ModernAvatar.vue'

// API
import { postAndConsumeSse } from '../api/sse'
import { apiPost } from '../api/http'

// ========== Stores ==========
const settings = useSettingsStore()
const characters = useCharactersStore()
const chats = useChatsStore()

// ========== 状态变量 ==========
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

const selectedCharacter = computed(() => selectedCharacterId.value ? characters.list.find(c => c.id === selectedCharacterId.value) || null : null)
const activeChat = computed(() => chats.activeChat)
const assistantChatId = computed(() => activeChat.value?.id ?? null)
const characterAvatarUrl = computed(() => selectedCharacter.value?.avatar ? `/api/avatars/${selectedCharacter.value.avatar}` : null)
const userName = computed(() => selectedPersona.value?.name || 'YOU')

// ========== 初始化 Composables ==========
const stream = useStreamOutput({ appendLocalMessageContent: chats.appendLocalMessageContent }, scrollToBottom)
const versions = useMessageVersions()
const group = useGroupChat({ activeChat, isGenerating, settings: settings as any })
const assistant = useAssistant({ chatId: assistantChatId })

function getPersonaById(id: string | null | undefined) {
  return settings.settings?.userPersonas?.find(p => p.id === id) || null
}

const effectiveSelectedPersonaId = computed(() => {
  if (group.effectivePureAiMode.value) return null
  return activeChat.value?.userPersonaId ?? settings.settings?.selectedPersonaId ?? null
})

const selectedPersona = computed(() => getPersonaById(effectiveSelectedPersonaId.value))
const userAvatarUrl = computed(() => selectedPersona.value?.avatar ? `/api/avatars/${selectedPersona.value.avatar}` : null)

const actions = useChatActions({
  activeChat, isGenerating, selectedPersona, userName,
  chatsStore: chats as any, settingsStore: settings as any, charactersStore: characters as any,
})

const chatModelOptions = computed(() => {
  const options: any[] = []
  if (!settings.settings) return []

  const recentModels = settings.settings.llm?.usedModels || []
  if (recentModels.length > 0) {
    options.push({
      label: 'RECENT',
      options: recentModels.map(m => {
        const preset = settings.settings?.apiPresets?.find(p => p.models.includes(m))
        return { label: m, value: m, presetId: preset?.id || null }
      })
    })
  }

  if (settings.settings.apiPresets) {
    for (const preset of settings.settings.apiPresets) {
      if (preset.models?.length > 0) {
        options.push({
          label: preset.name.toUpperCase(),
          options: preset.models.map(m => ({ label: m, value: m, presetId: preset.id }))
        })
      }
    }
  }

  return options
})

const messageListRef = ref<InstanceType<typeof MessageList> | null>(null)
function scrollToBottom() { nextTick(() => messageListRef.value?.scrollToBottom()) }

// ========== 核心业务逻辑 ==========

async function handleModelSelect(option: any) {
  if (!activeChat.value) return
  const overrides = { ...activeChat.value.overrides }
  overrides.params = { ...overrides.params, model: option.value }
  
  if (option.presetId) {
    overrides.presetId = option.presetId
  } else {
    const found = settings.settings?.apiPresets?.find(p => p.models.includes(option.value))
    if (found) overrides.presetId = found.id
    else overrides.presetId = null
  }
  
  await chats.updateOverrides(activeChat.value.id, overrides)
}

async function startEditTitle(chatId: string, currentTitle: string) {
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

async function deleteChat(chatId: string) {
  if (confirm('Delete this history record?')) {
    await chats.remove(chatId)
  }
}

async function handleUpdateMemberIds(memberIds: string[]) {
  if (activeChat.value) await chats.updateMemberOrder(activeChat.value.id, memberIds)
}

async function handleUpdateGroupDelay(delay: number) {
  if (activeChat.value) await chats.updateGroupDelay(activeChat.value.id, delay)
}

async function sendUserMessage() {
  const text = draftMessage.value.trim()
  if (!text || !activeChat.value || isGenerating.value) return
  draftMessage.value = ''
  streamError.value = null
  
  const chatId = activeChat.value.id
  const isGroup = activeChat.value.isGroup
  const userRole = group.effectivePureAiMode.value ? 'system' : 'user'

  isGenerating.value = true
  aborter.value = new AbortController()

  try {
    const localUserId = `local_user_${Date.now()}`
    chats.addLocalMessage({
      version: 1, id: localUserId, role: userRole as any, content: text,
      senderPersonaId: selectedPersona.value?.id,
      senderName: userName.value,
      senderAvatar: selectedPersona.value?.avatar,
      ts: new Date().toISOString()
    })
    scrollToBottom()
    
    await apiPost(`/api/chats/${chatId}/messages`, {
      role: userRole, content: text,
      senderPersonaId: selectedPersona.value?.id,
      senderName: userName.value,
      senderAvatar: selectedPersona.value?.avatar,
    })

    if (isGroup) {
      const memberIds = group.filterMembersByProbability([...activeChat.value.memberIds])
      await runGroupGeneration(chatId, memberIds)
    } else {
      await runSingleGeneration(chatId, text)
    }
  } catch (e: any) {
    if (e.name !== 'AbortError') streamError.value = e.message
  } finally {
    isGenerating.value = false
    await chats.load(chatId)
  }
}

async function runSingleGeneration(chatId: string, text: string) {
  const localAssistantId = `local_assistant_${Date.now()}`
  chats.addLocalMessage({ version: 1, id: localAssistantId, role: 'assistant', content: '', ts: new Date().toISOString() })
  scrollToBottom()

  stream.registerStreamMessage(localAssistantId)
  await postAndConsumeSse('/api/generate/stream', {
    chatId, userMessage: text,
    senderPersonaId: selectedPersona.value?.id,
    senderName: userName.value,
    senderAvatar: selectedPersona.value?.avatar,
  }, (evt) => {
    if (stopRequested.value) return
    if (evt.event === 'delta') stream.appendDeltaBuffered(localAssistantId, evt.data.text)
    else if (evt.event === 'error') streamError.value = evt.data.message
  }, aborter.value?.signal)
  stream.flushForMessage(localAssistantId)
}

async function runGroupGeneration(chatId: string, memberIds: string[]) {
  for (let i = 0; i < memberIds.length; i++) {
    const charId = memberIds[i]
    if (group.isPaused.value) break
    
    const localAssistantId = `local_group_${Date.now()}_${i}`
    chats.addLocalMessage({ version: 1, id: localAssistantId, role: 'assistant', content: '', characterId: charId, ts: new Date().toISOString() })
    scrollToBottom()

    stream.registerStreamMessage(localAssistantId)
    await postAndConsumeSse('/api/generate/group', { chatId, characterId: charId }, (evt) => {
      if (evt.event === 'delta') stream.appendDeltaBuffered(localAssistantId, evt.data.text)
    }, aborter.value?.signal)
    stream.flushForMessage(localAssistantId)
    
    if (i < memberIds.length - 1) await new Promise(r => setTimeout(r, activeChat.value?.groupDelay || 1000))
  }
}

onMounted(async () => {
  await settings.load()
  await characters.loadAll()
  await chats.loadGroupList()
  if (characters.list.length > 0) selectedCharacterId.value = characters.list[0].id
})

watch(() => selectedCharacterId.value, async (cid) => {
  if (!cid) return
  await chats.loadList(cid)
  if (chats.list.length > 0) { await chats.load(chats.list[0].id); scrollToBottom() }
}, { immediate: true })
</script>

<template>
  <div class="flex h-screen w-full bg-dark-bg text-text-primary overflow-hidden font-sans select-none border border-strong">
    
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
      @edit-character="actions.openEditCharacter"
      @create-character="actions.openCreateCharacter"
      @delete-character="actions.deleteCharacter"
      @select-chat="chats.load($event.id)"
      @select-group="chats.load($event.id)"
      @create-chat="chats.create(selectedCharacterId!)"
      @create-group="showGroupCreator = true"
      @start-edit-title="startEditTitle"
      @save-title="saveTitle"
      @cancel-edit-title="cancelEditTitle"
      @delete-chat="deleteChat"
    />

    <main class="flex-1 flex flex-col relative min-w-0 bg-dark-bg">
      <template v-if="activeChat">
        <!-- Obsidian Header -->
        <header class="sticky top-0 z-50 flex flex-col bg-dark-bg border-b border-strong">
          <div class="h-16 flex items-center justify-between px-8">
            <div class="flex items-center gap-6 min-w-0">
              <div class="flex flex-col min-w-0">
                <h2 class="text-lg font-black uppercase tracking-tighter truncate leading-none text-text-primary">
                  {{ activeChat.isGroup ? activeChat.title : (selectedCharacter?.name || 'ENTITY') }}
                </h2>
                <div class="flex items-center gap-2 mt-1">
                  <span class="text-[9px] font-black text-brand uppercase tracking-widest truncate">
                    {{ activeChat.isGroup ? `PROTOCOL: GROUP_COLLAB / ${activeChat.memberIds.length} NODES` : `PROTOCOL: DIRECT_LINK / ${activeChat.title}` }}
                  </span>
                </div>
              </div>
            </div>
            
            <div class="flex items-center gap-6">
              <div class="hidden md:flex gap-4">
                <button class="text-[9px] font-black text-text-muted hover:text-brand transition-colors tracking-widest" @click="actions.exportChat('txt')">EXPORT.TXT</button>
                <button class="text-[9px] font-black text-text-muted hover:text-brand transition-colors tracking-widest" @click="actions.exportChat('json')">EXPORT.JSON</button>
              </div>
              <div class="w-px h-4 bg-strong"></div>
              <button v-if="activeChat.isGroup" class="btn btn-xs btn-secondary px-4 text-brand border-brand/50 hover:border-brand" @click="showGroupSettings = true">GROUP.CFG</button>
              <button class="text-[9px] font-black text-text-muted hover:text-text-primary transition-colors tracking-widest" @click="showSettings = true">SYSTEM.CFG</button>
              <button class="btn btn-xs btn-primary px-6" @click="assistant.isAssistantPanelOpen.value = !assistant.isAssistantPanelOpen.value">A.I. PANEL</button>
            </div>
          </div>

          <!-- Group Status Sub-Header -->
          <div v-if="activeChat.isGroup" class="px-8 py-2 bg-brand/5 border-t border-strong flex items-center gap-6 overflow-x-auto custom-scrollbar">
             <span class="text-[8px] font-black text-brand uppercase tracking-[0.2em] shrink-0 italic">Active Nodes:</span>
             <div class="flex gap-3">
                <div v-for="m in groupMembers" :key="m.id" 
                  class="flex items-center gap-2 px-3 py-1 bg-dark-bg border border-brand/20 hover:border-brand transition-all cursor-pointer group/node"
                  @click="triggerInterject(m.id)"
                >
                   <ModernAvatar :name="m.name" :size="12" rounded="rounded-none" class="bg-brand/20" />
                   <span class="text-[9px] font-black uppercase text-text-secondary group-hover/node:text-brand">{{ m.name }}</span>
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
          @set-content-ref="stream.setMessageContentRef"
        />

        <!-- 输入控制 -->
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
          :is-streaming-active="isGenerating"
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
          @select-model="handleModelSelect"
          @toggle-assistant="assistant.isAssistantPanelOpen.value = !assistant.isAssistantPanelOpen.value"
        />
      </template>

      <!-- 空白页 -->
      <div v-else class="flex-1 flex flex-col items-center justify-center p-12 text-center">
        <div class="text-9xl font-black text-brand mb-12 italic tracking-tighter opacity-20">ST.2</div>
        <h3 class="text-2xl font-black uppercase tracking-[0.4em] mb-6 text-text-primary">Protocol Offline</h3>
        <p class="text-text-muted text-[10px] font-black uppercase tracking-[0.2em] mb-12 max-w-sm leading-relaxed">Select an entity node from the sidebar or initialize a new neural sequence.</p>
        <button class="btn btn-primary px-16 py-4 font-black tracking-widest" @click="actions.openCreateCharacter">NEW ENTITY</button>
      </div>
    </main>

    <AssistantPanel
      :is-open="assistant.isAssistantPanelOpen.value"
      :messages="assistant.assistantMessages.value"
      :draft="assistant.assistantDraft.value"
      :is-generating="assistant.isAssistantGenerating.value"
      :stream-error="assistant.assistantStreamError.value"
      :current-model="currentModel"
      :model-options="chatModelOptions"
      @update:is-open="assistant.isAssistantPanelOpen.value = $event"
      @update:draft="assistant.assistantDraft.value = $event"
      @send="assistant.sendMessage('chat')"
      @reset="assistant.resetChat"
    />

    <!-- MODALS -->
    <SettingsDrawer v-model:show="showSettings" :chat="activeChat" :initial-tab="settingsTab" @open-member-settings="actions.openMemberSettingsEditor" />
    <GroupCreatorModal v-if="showGroupCreator" :show="true" :characters="characters.list" @update:show="showGroupCreator = false" @create="handleCreateGroup" />
    <GroupSettingsModal v-if="showGroupSettings" :show="true" :chat="activeChat" :characters="characters.list" @update:show="showGroupSettings = false" @update:member-ids="handleUpdateMemberIds" @update:group-delay="handleUpdateGroupDelay" @open-member-settings="actions.openMemberSettingsEditor" @save="showGroupSettings = false" />
    <MemberSettingsModal v-if="actions.editingMemberId.value" :show="true" :member-id="actions.editingMemberId.value" :settings="actions.editingMemberSettings.value" :character="characters.list.find(c => c.id === actions.editingMemberId.value) || null" :model-options="chatModelOptions" @update:show="actions.closeMemberSettingsEditor" @save="actions.saveMemberSettings" />
    <MessageEditorModal v-if="actions.showMessageEditor.value" :show="true" :message-id="actions.editingMessageId.value" :message-role="actions.editingMessageRole.value" :message-content="actions.editingMessageContent.value" :character-avatar-url="characterAvatarUrl" :user-avatar-url="userAvatarUrl" :is-generating="isGenerating" @update:show="actions.closeEditMessage" @save="actions.saveEditedMessage" />
  </div>
</template>

<style scoped>
.custom-scrollbar::-webkit-scrollbar { width: 1px; }
</style>
