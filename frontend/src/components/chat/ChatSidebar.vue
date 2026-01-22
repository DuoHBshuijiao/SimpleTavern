<script setup lang="ts">
/**
 * ChatSidebar - 侧边栏组件
 * 
 * 包含：用户身份选择、角色列表、会话历史列表
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

// 辅助函数：获取角色信息
function getCharacterById(id: string): CharacterCard | null {
  return props.characters.find(c => c.id === id) ?? null
}

// 辅助函数：获取 Persona 信息
function getPersonaById(id: string | null | undefined): UserPersona | null {
  if (!id) return null
  return props.personas.find(p => p.id === id) ?? null
}

// 获取会话的头像列表
function getChatAvatars(chat: Chat): { src: string | null; name: string }[] {
  const avatars: { src: string | null; name: string }[] = []
  
  const chatPure = (chat.overrides?.pureAiMode ?? props.effectivePureAiMode) === true
  const chatPersona = getPersonaById(chat.userPersonaId)

  // 1. User（非纯 AI 模式才展示）
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
    class="flex flex-col border-r border-white/5 bg-[#141418] transition-all duration-300 relative flex-shrink-0"
    :class="collapsed ? '-ml-80 w-80' : 'w-80'"
  >
    <div class="flex flex-col h-full overflow-hidden">
      
      <!-- 用户身份区域 (头部) -->
      <div class="p-4 bg-black/10 border-b border-white/5 shrink-0">
        <div class="flex items-center justify-between mb-3">
          <span class="text-xs font-bold text-gray-400 uppercase tracking-wider">我的身份</span>
          <button 
            class="text-xs text-brand hover:text-brand-hover transition-colors px-2 py-0.5 rounded hover:bg-white/5" 
            @click="emit('create-persona')"
          >
            + 新建
          </button>
        </div>
        
        <div class="space-y-2 max-h-[140px] overflow-y-auto pr-1 custom-scrollbar">
          <div 
            v-for="p in personas"
            :key="p.id"
            class="group flex items-center gap-3 p-2 rounded-xl cursor-pointer transition-all duration-200 border border-transparent"
            :class="selectedPersonaId === p.id ? 'bg-brand/10 border-brand/20' : 'hover:bg-white/5'"
            @click="emit('select-persona', p.id)"
          >
            <ModernAvatar :src="p.avatar ? `/api/avatars/${p.avatar}` : null" :name="p.name" :size="36" aspect="1" />
            <div class="flex-1 min-w-0">
              <div class="font-medium text-sm truncate" :class="selectedPersonaId === p.id ? 'text-brand' : 'text-gray-300'">{{ p.name }}</div>
            </div>
            <div class="opacity-0 group-hover:opacity-100 flex gap-1 transition-opacity">
              <button class="p-1 hover:text-white text-gray-500" @click.stop="emit('edit-persona', p)">✏</button>
              <button class="p-1 hover:text-red-400 text-gray-500" @click.stop="confirmDeletePersona(p.id)">🗑</button>
            </div>
          </div>
          
          <div v-if="!personas.length" class="text-xs text-gray-500 text-center py-2">
            点击上方新建创建你的第一个身份
          </div>
        </div>
      </div>

      <!-- 角色列表区域 (中间，弹性伸缩) -->
      <div class="flex-1 overflow-y-auto min-h-0 custom-scrollbar p-3">
        <div class="flex items-center justify-between mb-2 px-1">
          <span class="text-xs font-bold text-gray-400 uppercase tracking-wider">角色列表</span>
          <button 
            class="text-xs text-brand hover:text-brand-hover transition-colors px-2 py-0.5 rounded hover:bg-white/5" 
            @click="emit('create-character')"
          >
            + 新建
          </button>
        </div>

        <div class="grid grid-cols-1 gap-2">
          <div 
            v-for="c in characters"
            :key="c.id"
            class="group relative flex items-start gap-3 p-3 rounded-2xl cursor-pointer transition-all duration-200 border border-transparent"
            :class="selectedCharacterId === c.id ? 'bg-white/5 border-brand/20 shadow-sm' : 'hover:bg-white/5'"
            @click="emit('update:selectedCharacterId', c.id)"
          >
            <ModernAvatar 
              :src="c.avatar ? `/api/avatars/${c.avatar}` : null" 
              :name="c.name" 
              :size="56" 
              aspect="auto"
              object-fit="contain"
              rounded="rounded-lg"
              class="shadow-md"
            />
            
            <div class="flex-1 min-w-0 flex flex-col h-[74px]">
              <div class="flex justify-between items-start">
                <div class="font-bold text-sm truncate" :class="selectedCharacterId === c.id ? 'text-brand-300' : 'text-gray-200'">{{ c.name }}</div>
              </div>
              <div class="text-xs text-gray-500 line-clamp-3 mt-1 leading-relaxed">{{ c.description || '暂无简介' }}</div>
            </div>

            <div class="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity bg-black/60 rounded-lg backdrop-blur-sm p-0.5 flex">
              <button class="p-1.5 hover:text-white text-gray-400" @click.stop="emit('edit-character', c)">✏</button>
              <button class="p-1.5 hover:text-red-400 text-gray-400" @click.stop="confirmDeleteCharacter(c.id)">🗑</button>
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
              :disabled="characters.length < 2" 
              @click="emit('create-group')"
              title="创建群聊"
            >
              + 群聊
            </button>
            <button 
              class="text-xs bg-brand/20 hover:bg-brand/30 text-brand px-2 py-1 rounded transition-colors disabled:opacity-50 disabled:cursor-not-allowed" 
              :disabled="!selectedCharacterId" 
              @click="emit('create-chat')"
            >
              新建会话
            </button>
          </div>
        </div>
        <div class="flex-1 overflow-y-auto p-2 custom-scrollbar">
          <!-- 群聊列表 -->
          <div v-if="groupList.length > 0" class="mb-3">
            <div class="text-[10px] text-purple-400 uppercase tracking-wider px-2 mb-1 flex items-center gap-1">
              <span>👥</span> 群聊
            </div>
            <div 
              v-for="c in groupList"
              :key="c.id"
              class="group flex items-center justify-between p-2 rounded-lg cursor-pointer text-sm mb-1 transition-colors"
              :class="activeChatId === c.id ? 'bg-purple-500/10 text-purple-400' : 'text-gray-400 hover:bg-white/5 hover:text-gray-200'"
              @click="emit('select-group', c)"
            >
              <div class="flex items-center gap-2 flex-1 min-w-0 pr-2 max-w-[calc(100%-60px)]">
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
                    :value="editingTitle"
                    @input="emit('update:editingTitle', ($event.target as HTMLInputElement).value)"
                    class="bg-black/20 border border-purple-500/50 rounded px-1 py-0.5 text-xs w-full text-white outline-none focus:border-purple-500"
                    @keyup.enter="emit('save-title')"
                    @keyup.escape="emit('cancel-edit-title')"
                    autofocus
                  />
                  <button class="text-purple-400 hover:text-white" @click="emit('save-title')">✓</button>
                  <button class="text-gray-500 hover:text-white" @click="emit('cancel-edit-title')">✕</button>
                </div>
                <div v-else class="truncate flex-1">{{ c.title }}</div>
                <span class="text-[10px] text-gray-600 shrink-0">({{ c.memberIds.length }}人)</span>
              </div>
              
              <div v-if="editingChatId !== c.id" class="flex gap-1 shrink-0 ml-auto bg-black/40 rounded-md backdrop-blur-sm">
                <button class="p-1 hover:text-white text-gray-300" @click.stop="emit('start-edit-title', c.id, c.title)" title="重命名">✏</button>
                <button class="p-1 hover:text-red-400 text-gray-300" @click.stop="confirmDeleteChat(c.id, true)" title="删除">🗑</button>
              </div>
            </div>
          </div>

          <!-- 单聊列表 -->
          <div v-if="chatList.filter(c => !c.isGroup).length > 0">
            <div v-if="groupList.length > 0" class="text-[10px] text-gray-500 uppercase tracking-wider px-2 mb-1">
              单聊
            </div>
            <div 
              v-for="c in chatList.filter(chat => !chat.isGroup)"
              :key="c.id"
              class="group flex items-center justify-between p-2 rounded-lg cursor-pointer text-sm mb-1 transition-colors"
              :class="activeChatId === c.id ? 'bg-brand/10 text-brand' : 'text-gray-400 hover:bg-white/5 hover:text-gray-200'"
              @click="emit('select-chat', c)"
            >
              <div class="flex items-center gap-2 flex-1 min-w-0 pr-2 max-w-[calc(100%-60px)]">
                <div class="flex -space-x-1.5 overflow-hidden shrink-0">
                  <template v-for="(avatar, i) in getChatAvatars(c).slice(0, 2)" :key="i">
                    <ModernAvatar :src="avatar.src" :name="avatar.name" :size="20" aspect="1" rounded="rounded-full" class="ring-1 ring-[#141418] bg-[#141418]" />
                  </template>
                </div>
                <div class="flex-1 min-w-0">
                  <div v-if="editingChatId === c.id" @click.stop class="flex gap-1">
                    <input 
                      :value="editingTitle"
                      @input="emit('update:editingTitle', ($event.target as HTMLInputElement).value)"
                      class="bg-black/20 border border-brand/50 rounded px-1 py-0.5 text-xs w-full text-white outline-none focus:border-brand"
                      @keyup.enter="emit('save-title')"
                      @keyup.escape="emit('cancel-edit-title')"
                      autofocus
                    />
                    <button class="text-brand hover:text-white" @click="emit('save-title')">✓</button>
                    <button class="text-gray-500 hover:text-white" @click="emit('cancel-edit-title')">✕</button>
                  </div>
                  <div v-else class="truncate">{{ c.title }}</div>
                </div>
              </div>
              
              <div v-if="editingChatId !== c.id" class="flex gap-1 shrink-0 ml-auto bg-black/40 rounded-md backdrop-blur-sm">
                <button class="p-1 hover:text-white text-gray-300" @click.stop="emit('start-edit-title', c.id, c.title)" title="重命名">✏</button>
                <button class="p-1 hover:text-red-400 text-gray-300" @click.stop="confirmDeleteChat(c.id, false)" title="删除">🗑</button>
              </div>
            </div>
          </div>
          <div v-if="!chatList.length && !groupList.length" class="text-center text-xs text-gray-600 py-4">
            无历史会话
          </div>
        </div>
      </div>
    </div>
  </aside>

  <!-- 侧边栏开关 -->
  <div 
    class="absolute left-0 top-1/2 -translate-y-1/2 z-50 cursor-pointer p-2 bg-brand/30 hover:bg-brand/50 rounded-r-lg backdrop-blur-sm transition-colors border border-l-0 border-brand/40 shadow-lg"
    @click="toggleCollapsed"
    title="切换侧边栏"
  >
    <span class="text-xs text-white">{{ collapsed ? '▶' : '◀' }}</span>
  </div>
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
