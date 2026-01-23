<script setup lang="ts">
/**
 * ChatSidebar - 侧边栏组件
 * 风格：Radical Swiss Modernism 2.0
 */
import type { CharacterCard, UserPersona, Chat } from '../../types/models'
import ModernAvatar from '../ModernAvatar.vue'

const props = defineProps<{
  collapsed: boolean
  // 身份相关
  personas: UserPersona[]
  selectedPersonaId: string | null
  effectivePureAiMode: boolean
  // 角色相关
  characters: CharacterCard[]
  selectedCharacterId: string | null
  // 会话相关
  chatList: Chat[]
  groupList: Chat[]
  activeChatId: string | null
  editingChatId: string | null
  editingTitle: string
}>()

const emit = defineEmits<{
  'update:collapsed': [value: boolean]
  'update:selectedCharacterId': [id: string]
  'update:editingTitle': [value: string]
  // 身份操作
  'select-persona': [id: string]
  'edit-persona': [persona: UserPersona]
  'create-persona': []
  'delete-persona': [id: string]
  // 角色操作
  'edit-character': [card: CharacterCard]
  'create-character': []
  'delete-character': [id: string]
  // 会话操作
  'select-chat': [chat: Chat]
  'select-group': [chat: Chat]
  'create-chat': []
  'create-group': []
  'start-edit-title': [chatId: string, title: string]
  'save-title': []
  'cancel-edit-title': []
  'delete-chat': [chatId: string]
}>()

function getCharacterById(id: string): CharacterCard | null {
  return props.characters.find(c => c.id === id) ?? null
}

function getPersonaById(id: string | null | undefined): UserPersona | null {
  if (!id) return null
  return props.personas.find(p => p.id === id) ?? null
}

function getChatAvatars(chat: Chat): { src: string | null; name: string }[] {
  const avatars: { src: string | null; name: string }[] = []
  
  const chatPure = (chat.overrides?.pureAiMode ?? props.effectivePureAiMode) === true
  const chatPersona = getPersonaById(chat.userPersonaId)

  if (!chatPure) {
    const seen = new Set<string>()
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
    if (avatars.length === 0) {
      if (chatPersona) {
        avatars.push({
          src: chatPersona.avatar ? `/api/avatars/${chatPersona.avatar}` : null,
          name: chatPersona.name || '你',
        })
      } else {
        avatars.push({ src: null, name: '你' })
      }
    }
  }

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

const toggleCollapsed = () => emit('update:collapsed', !props.collapsed)

function confirmDeletePersona(id: string) {
  if (window.confirm('确定删除这个身份？')) {
    emit('delete-persona', id)
  }
}

function confirmDeleteCharacter(id: string) {
  if (window.confirm('确定删除这个角色？')) {
    emit('delete-character', id)
  }
}

function confirmDeleteChat(id: string, isGroup: boolean) {
  if (window.confirm(isGroup ? '确定删除群聊？' : '确定删除会话？')) {
    emit('delete-chat', id)
  }
}
</script>

<template>
  <aside 
    class="flex flex-col border-r border-strong bg-dark-bg transition-all duration-300 relative flex-shrink-0"
    :class="collapsed ? '-ml-[320px] w-[320px]' : 'w-[320px]'"
  >
    <div class="flex flex-col h-full overflow-hidden">
      
      <!-- 用户身份区域 (头部) -->
      <div class="p-6 bg-surface border-b border-subtle shrink-0">
        <div class="flex items-center justify-between mb-4">
          <span class="text-xs font-black text-text-muted uppercase tracking-widest">User Persona</span>
          <button 
            class="text-[10px] font-bold text-brand hover:text-brand-hover transition-colors px-2 py-1 border border-brand/20 hover:border-brand" 
            @click="emit('create-persona')"
          >
            NEW
          </button>
        </div>
        
        <div class="space-y-1 max-h-[160px] overflow-y-auto pr-1 custom-scrollbar">
          <div 
            v-for="p in personas"
            :key="p.id"
            class="group flex items-center gap-3 p-2 rounded-sm cursor-pointer transition-all duration-100 border border-transparent"
            :class="selectedPersonaId === p.id ? 'bg-brand/5 border-brand/20' : 'hover:bg-white/5'"
            @click="emit('select-persona', p.id)"
          >
            <ModernAvatar :src="p.avatar ? `/api/avatars/${p.avatar}` : null" :name="p.name" :size="32" aspect="1" rounded="rounded-sm" />
            <div class="flex-1 min-w-0">
              <div class="font-bold text-sm truncate" :class="selectedPersonaId === p.id ? 'text-brand' : 'text-text-primary'">{{ p.name }}</div>
            </div>
            <div class="opacity-0 group-hover:opacity-100 flex gap-1 transition-opacity">
              <button class="p-1 hover:text-brand text-text-muted" @click.stop="emit('edit-persona', p)">✏</button>
              <button class="p-1 hover:text-error text-text-muted" @click.stop="confirmDeletePersona(p.id)">🗑</button>
            </div>
          </div>
          
          <div v-if="!personas.length" class="text-[10px] text-text-muted text-center py-4 uppercase tracking-widest">
            No personas defined
          </div>
        </div>
      </div>

      <!-- 角色列表区域 (中间，弹性伸缩) -->
      <div class="flex-1 overflow-y-auto min-h-0 custom-scrollbar p-4">
        <div class="flex items-center justify-between mb-4 px-2">
          <span class="text-xs font-black text-text-muted uppercase tracking-widest">Characters</span>
          <button 
            class="text-[10px] font-bold text-brand hover:text-brand-hover transition-colors px-2 py-1 border border-brand/20 hover:border-brand" 
            @click="emit('create-character')"
          >
            ADD
          </button>
        </div>

        <div class="grid grid-cols-1 gap-1">
          <div 
            v-for="c in characters"
            :key="c.id"
            class="group relative flex items-center gap-4 p-3 rounded-sm cursor-pointer transition-all duration-100 border border-transparent"
            :class="selectedCharacterId === c.id ? 'bg-surface border-subtle shadow-sm' : 'hover:bg-white/5'"
            @click="emit('update:selectedCharacterId', c.id)"
          >
            <ModernAvatar 
              :src="c.avatar ? `/api/avatars/${c.avatar}` : null" 
              :name="c.name" 
              :size="48" 
              aspect="auto"
              object-fit="contain"
              rounded="rounded-sm"
              class="bg-black/20"
            />
            
            <div class="flex-1 min-w-0 flex flex-col justify-center">
              <div class="font-black text-sm truncate uppercase tracking-tight" :class="selectedCharacterId === c.id ? 'text-brand' : 'text-text-primary'">{{ c.name }}</div>
              <div class="text-[10px] text-text-muted line-clamp-1 mt-0.5 leading-tight">{{ c.description || 'No description' }}</div>
            </div>

            <div class="absolute top-1/2 -translate-y-1/2 right-2 opacity-0 group-hover:opacity-100 transition-opacity flex">
              <button class="p-2 hover:text-brand text-text-muted" @click.stop="emit('edit-character', c)">✏</button>
              <button class="p-2 hover:text-error text-text-muted" @click.stop="confirmDeleteCharacter(c.id)">🗑</button>
            </div>
          </div>
        </div>
      </div>

      <!-- 会话列表区域 (底部) -->
      <div class="h-1/3 min-h-[200px] border-t border-strong bg-surface flex flex-col">
        <div class="p-4 pb-2 shrink-0 flex items-center justify-between">
          <span class="text-xs font-black text-text-muted uppercase tracking-widest">History</span>
          <div class="flex gap-2">
            <button 
              class="text-[10px] font-bold bg-brand/10 hover:bg-brand/20 text-brand px-2 py-1 rounded-sm border border-brand/20 transition-colors disabled:opacity-30" 
              :disabled="characters.length < 2" 
              @click="emit('create-group')"
            >
              + GROUP
            </button>
            <button 
              class="text-[10px] font-bold bg-brand/10 hover:bg-brand/20 text-brand px-2 py-1 rounded-sm border border-brand/20 transition-colors disabled:opacity-30" 
              :disabled="!selectedCharacterId" 
              @click="emit('create-chat')"
            >
              + CHAT
            </button>
          </div>
        </div>
        <div class="flex-1 overflow-y-auto p-2 custom-scrollbar">
          <!-- 群聊列表 -->
          <div v-if="groupList.length > 0" class="mb-4">
            <div class="text-[10px] font-black text-brand uppercase tracking-widest px-3 mb-2 flex items-center gap-2">
              <span class="w-1.5 h-1.5 bg-brand"></span> Group Chats
            </div>
            <div 
              v-for="c in groupList"
              :key="c.id"
              class="group flex items-center justify-between p-3 rounded-sm cursor-pointer text-xs mb-1 transition-colors border border-transparent"
              :class="activeChatId === c.id ? 'bg-dark-bg border-subtle text-brand' : 'text-text-secondary hover:bg-white/5'"
              @click="emit('select-group', c)"
            >
              <div class="flex items-center gap-3 flex-1 min-w-0">
                <div class="flex -space-x-2 overflow-hidden shrink-0">
                  <template v-for="(avatar, i) in getChatAvatars(c).slice(0, 3)" :key="i">
                    <ModernAvatar :src="avatar.src" :name="avatar.name" :size="20" aspect="1" rounded="rounded-sm" class="ring-1 ring-surface bg-surface" />
                  </template>
                </div>
                <div v-if="editingChatId === c.id" @click.stop class="flex gap-1 flex-1">
                  <input 
                    :value="editingTitle"
                    @input="emit('update:editingTitle', ($event.target as HTMLInputElement).value)"
                    class="bg-black/40 border border-brand/50 rounded-sm px-2 py-1 text-[10px] w-full text-white outline-none focus:border-brand"
                    @keyup.enter="emit('save-title')"
                    @keyup.escape="emit('cancel-edit-title')"
                    autofocus
                  />
                  <button class="text-brand hover:text-white" @click="emit('save-title')">✓</button>
                </div>
                <div v-else class="truncate font-bold uppercase tracking-tight flex-1">{{ c.title }}</div>
              </div>
              
              <div v-if="editingChatId !== c.id" class="flex gap-1 shrink-0 group-hover:opacity-100 transition-opacity">
                <button class="p-1 text-text-muted hover:text-brand" @click.stop="emit('start-edit-title', c.id, c.title)">✏</button>
                <button class="p-1 text-text-muted hover:text-error" @click.stop="confirmDeleteChat(c.id, true)">🗑</button>
              </div>
            </div>
          </div>

          <!-- 单聊列表 -->
          <div v-if="chatList.filter(c => !c.isGroup).length > 0">
            <div v-if="groupList.length > 0" class="text-[10px] font-black text-text-muted uppercase tracking-widest px-3 mb-2">
              Direct Messages
            </div>
            <div 
              v-for="c in chatList.filter(chat => !chat.isGroup)"
              :key="c.id"
              class="group flex items-center justify-between p-3 rounded-sm cursor-pointer text-xs mb-1 transition-colors border border-transparent"
              :class="activeChatId === c.id ? 'bg-dark-bg border-subtle text-brand' : 'text-text-secondary hover:bg-white/5'"
              @click="emit('select-chat', c)"
            >
              <div class="flex items-center gap-3 flex-1 min-w-0">
                <div class="flex -space-x-2 overflow-hidden shrink-0">
                  <template v-for="(avatar, i) in getChatAvatars(c).slice(0, 2)" :key="i">
                    <ModernAvatar :src="avatar.src" :name="avatar.name" :size="20" aspect="1" rounded="rounded-sm" class="ring-1 ring-surface bg-surface" />
                  </template>
                </div>
                <div class="flex-1 min-w-0">
                  <div v-if="editingChatId === c.id" @click.stop class="flex gap-1">
                    <input 
                      :value="editingTitle"
                      @input="emit('update:editingTitle', ($event.target as HTMLInputElement).value)"
                      class="bg-black/40 border border-brand/50 rounded-sm px-2 py-1 text-[10px] w-full text-white outline-none focus:border-brand"
                      @keyup.enter="emit('save-title')"
                      @keyup.escape="emit('cancel-edit-title')"
                      autofocus
                    />
                    <button class="text-brand hover:text-white" @click="emit('save-title')">✓</button>
                  </div>
                  <div v-else class="truncate font-bold uppercase tracking-tight">{{ c.title }}</div>
                </div>
              </div>
              
              <div v-if="editingChatId !== c.id" class="flex gap-1 shrink-0 group-hover:opacity-100 transition-opacity">
                <button class="p-1 text-text-muted hover:text-brand" @click.stop="emit('start-edit-title', c.id, c.title)">✏</button>
                <button class="p-1 text-text-muted hover:text-error" @click.stop="confirmDeleteChat(c.id, false)">🗑</button>
              </div>
            </div>
          </div>
          <div v-if="!chatList.length && !groupList.length" class="text-[10px] text-text-muted text-center py-8 uppercase tracking-widest">
            Empty history
          </div>
        </div>
      </div>
    </div>
  </aside>

  <!-- 侧边栏开关 -->
  <div 
    class="absolute left-0 top-1/2 -translate-y-1/2 z-50 cursor-pointer p-2 bg-brand text-white rounded-r-sm transition-transform duration-300"
    :class="collapsed ? 'translate-x-0' : 'translate-x-0'"
    @click="toggleCollapsed"
    title="Toggle Sidebar"
  >
    <span class="text-[10px] font-black">{{ collapsed ? '▶' : '◀' }}</span>
  </div>
</template>

<style scoped>
.custom-scrollbar::-webkit-scrollbar {
  width: 2px;
}
.custom-scrollbar::-webkit-scrollbar-track {
  background: transparent;
}
.custom-scrollbar::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.05);
}
.custom-scrollbar:hover::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.1);
}
</style>
