<script setup lang="ts">
/**
 * ChatSidebar - 侧边栏组件
 *
 * 组件职责：
 * - 显示用户身份列表，支持选择、创建、编辑、删除身份
 * - 显示角色列表，支持选择、创建、编辑、删除角色
 * - 显示聊天会话历史列表（单聊和群聊），支持选择、创建、重命名、删除会话
 * - 支持侧边栏折叠/展开
 *
 * Props说明：
 * - collapsed: 是否折叠
 * - personas: 用户身份列表（来自types/models.ts的UserPersona[]类型）
 * - selectedPersonaId: 当前选中的身份ID
 * - effectivePureAiMode: 是否纯AI模式
 * - characters: 角色列表（来自types/models.ts的CharacterCard[]类型）
 * - selectedCharacterId: 当前选中的角色ID
 * - chatList: 单聊列表（来自types/models.ts的Chat[]类型）
 * - groupList: 群聊列表（来自types/models.ts的Chat[]类型）
 * - activeChatId: 当前激活的聊天ID
 * - editingChatId: 正在编辑标题的聊天ID
 * - editingTitle: 正在编辑的标题
 *
 * Emits说明：
 * - update:collapsed: 更新折叠状态
 * - update:selectedCharacterId: 更新选中的角色ID
 * - update:editingTitle: 更新编辑中的标题
 * - select-persona: 选择身份
 * - edit-persona: 编辑身份
 * - create-persona: 创建身份
 * - delete-persona: 删除身份
 * - edit-character: 编辑角色
 * - create-character: 创建角色
 * - delete-character: 删除角色
 * - select-chat: 选择单聊
 * - select-group: 选择群聊
 * - create-chat: 创建单聊
 * - create-group: 创建群聊
 * - start-edit-title: 开始编辑标题
 * - save-title: 保存标题
 * - cancel-edit-title: 取消编辑标题
 * - delete-chat: 删除聊天
 *
 * 使用的Composables：
 * 无
 *
 * 使用的Stores：
 * 无（通过props接收数据）
 *
 * 文件关系：
 *    - 被导入：被components/chat/index.ts导出，被views/ChatPage.vue使用
 *    - 导入：导入types/models.ts的类型、components/ModernAvatar.vue组件
 *    - 依赖：依赖vue、types/models.ts
 *    - 位置：组件层，提供侧边栏功能
 */
import type { CharacterCard, UserPersona, Chat } from '../../types/models'
import { computed, ref } from 'vue'
import ModernAvatar from '../ModernAvatar.vue'

import { Pencil, Trash2, Users, Check, X, ChevronRight, ChevronLeft } from 'lucide-vue-next'

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

/**
 * 获取角色信息
 *
 * 根据角色ID从角色列表中查找角色。
 *
 * @param {string} id - 角色ID
 * @returns {CharacterCard | null} 角色信息，如果未找到则返回null
 */
function getCharacterById(id: string): CharacterCard | null {
  return props.characters.find(c => c.id === id) ?? null
}

/**
 * 获取用户身份信息
 *
 * 根据身份ID从身份列表中查找身份。
 *
 * @param {string | null | undefined} id - 身份ID
 * @returns {UserPersona | null} 身份信息，如果未找到或ID为空则返回null
 */
function getPersonaById(id: string | null | undefined): UserPersona | null {
  if (!id) return null
  return props.personas.find(p => p.id === id) ?? null
}

/**
 * 获取会话的头像列表
 *
 * 根据聊天会话类型（单聊/群聊）和模式（纯AI/普通）获取要显示的头像列表。
 * 对于单聊，返回用户和角色的头像；对于群聊，返回用户和所有成员的头像。
 *
 * @param {Chat} chat - 聊天会话（来自types/models.ts）
 * @returns {{ src: string | null; name: string }[]} 头像列表，包含src和name
 */
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

/**
 * 切换侧边栏折叠状态
 *
 * 切换侧边栏的折叠/展开状态。
 */
const toggleCollapsed = () => emit('update:collapsed', !props.collapsed)

/**
 * 确认删除身份
 *
 * 弹出确认对话框，确认后删除指定身份。
 *
 * @param {string} id - 身份ID
 */
const deleteConfirm = ref<{
  type: 'persona' | 'character' | 'chat'
  id: string
  label: string
  isGroup?: boolean
} | null>(null)

const deleteConfirmTitle = computed(() => {
  const target = deleteConfirm.value
  if (!target) return ''
  if (target.type === 'persona') return '删除身份'
  if (target.type === 'character') return '删除角色'
  return target.isGroup ? '删除群聊' : '删除会话'
})

const deleteConfirmMessage = computed(() => {
  const target = deleteConfirm.value
  if (!target) return ''
  if (target.type === 'persona') return `确定删除身份“${target.label}”？此操作无法撤销。`
  if (target.type === 'character') return `确定删除角色“${target.label}”？此操作无法撤销。`
  return target.isGroup
    ? `确定删除群聊“${target.label}”？此操作无法撤销。`
    : `确定删除会话“${target.label}”？此操作无法撤销。`
})

function confirmDeletePersona(persona: UserPersona) {
  deleteConfirm.value = { type: 'persona', id: persona.id, label: persona.name || '未命名身份' }
}

/**
 * 确认删除角色
 *
 * 弹出确认对话框，确认后删除指定角色。
 *
 * @param {string} id - 角色ID
 */
function confirmDeleteCharacter(character: CharacterCard) {
  deleteConfirm.value = { type: 'character', id: character.id, label: character.name || '未命名角色' }
}

/**
 * 确认删除聊天
 *
 * 弹出确认对话框，确认后删除指定聊天会话。
 *
 * @param {string} id - 聊天ID
 * @param {boolean} isGroup - 是否为群聊
 */
function confirmDeleteChat(chat: Chat) {
  deleteConfirm.value = {
    type: 'chat',
    id: chat.id,
    label: chat.title || '未命名会话',
    isGroup: chat.isGroup,
  }
}

function cancelDelete() {
  deleteConfirm.value = null
}

function confirmDelete() {
  const target = deleteConfirm.value
  if (!target) return
  if (target.type === 'persona') emit('delete-persona', target.id)
  if (target.type === 'character') emit('delete-character', target.id)
  if (target.type === 'chat') emit('delete-chat', target.id)
  deleteConfirm.value = null
}
</script>

<template>
  <aside 
    class="flex flex-col glass-panel-floating rounded-2xl transition-all duration-300 relative flex-shrink-0 my-4 h-[calc(100vh-2rem)]"
    :class="collapsed ? '-ml-[21rem] w-80 opacity-0 pointer-events-none' : 'ml-4 w-80 opacity-100'"
    style="contain: content; will-change: margin-left, opacity;"
  >
    <div class="flex flex-col h-full overflow-hidden rounded-2xl">
      
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
            class="group flex items-center gap-3 p-2 rounded-xl transition-all duration-200 border-y border-r border-transparent border-l-2"
            :class="selectedPersonaId === p.id ? 'bg-brand/10 border-l-brand' : 'border-l-transparent hover:bg-white/5'"
            style="border: 1px solid rgba(255, 255, 255, 0.1);"
            @click="emit('select-persona', p.id)"
          >
            <ModernAvatar :src="p.avatar ? `/api/avatars/${p.avatar}` : null" :name="p.name" :size="36" aspect="1" />
            <div class="flex-1 min-w-0">
              <div class="font-medium text-sm truncate" :class="selectedPersonaId === p.id ? 'text-brand' : 'text-gray-300'">{{ p.name }}</div>
            </div>
            <div class="opacity-60 group-hover:opacity-100 flex gap-1 transition-opacity ml-auto bg-black/40 rounded-lg backdrop-blur-sm p-0.5">
              <button class="p-1 hover:text-white text-gray-400 transition-colors" @click.stop="emit('edit-persona', p)">
                <Pencil class="w-3.5 h-3.5" />
              </button>
              <button class="p-1 hover:text-red-400 text-gray-400 transition-colors" @click.stop="confirmDeletePersona(p)">
                <Trash2 class="w-3.5 h-3.5" />
              </button>
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
            class="group relative flex items-start gap-3 p-3 rounded-2xl transition-all duration-200 border-y border-r border-transparent border-l-2"
            :class="selectedCharacterId === c.id ? 'bg-white/5 border-l-brand shadow-sm' : 'border-l-transparent hover:bg-white/5'"
            style="border: 1px solid rgba(255, 255, 255, 0.1);"
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

            <div class="absolute top-3 right-2 opacity-60 group-hover:opacity-100 transition-opacity bg-black/40 rounded-lg backdrop-blur-sm p-0.5 flex gap-1">
              <button class="p-1.5 hover:text-white text-gray-400 transition-colors" @click.stop="emit('edit-character', c)">
                <Pencil class="w-4 h-4" />
              </button>
              <button class="p-1.5 hover:text-red-400 text-gray-400 transition-colors" @click.stop="confirmDeleteCharacter(c)">
                <Trash2 class="w-4 h-4" />
              </button>
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
              <Users class="w-3 h-3" /> 群聊
            </div>
            <div 
              v-for="c in groupList"
              :key="c.id"
              class="group flex items-center justify-between p-2 rounded-lg cursor-pointer text-sm mb-1 transition-colors border-l-2"
              :class="activeChatId === c.id ? 'bg-purple-500/10 text-purple-400 border-l-purple-400' : 'text-gray-400 border-l-transparent hover:bg-white/5 hover:text-gray-200'"
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
                  <button class="text-purple-400 hover:text-white" @click="emit('save-title')">
                    <Check class="w-3 h-3" />
                  </button>
                  <button class="text-gray-500 hover:text-white" @click="emit('cancel-edit-title')">
                    <X class="w-3 h-3" />
                  </button>
                </div>
                <div v-else class="truncate flex-1">{{ c.title }}</div>
                <span class="text-[10px] text-gray-600 shrink-0">({{ c.memberIds.length }}人)</span>
              </div>
              
              <div v-if="editingChatId !== c.id" class="flex gap-1 shrink-0 ml-auto bg-black/40 rounded-md backdrop-blur-sm opacity-60 group-hover:opacity-100 transition-opacity">
                <button class="p-1 hover:text-white text-gray-300 transition-colors" @click.stop="emit('start-edit-title', c.id, c.title)">
                  <Pencil class="w-3.5 h-3.5" />
                </button>
                <button class="p-1 hover:text-red-400 text-gray-300 transition-colors" @click.stop="confirmDeleteChat(c)">
                  <Trash2 class="w-3.5 h-3.5" />
                </button>
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
              class="group flex items-center justify-between p-2 rounded-lg cursor-pointer text-sm mb-1 transition-colors border-l-2"
              :class="activeChatId === c.id ? 'bg-brand/10 text-brand border-l-brand' : 'text-gray-400 border-l-transparent hover:bg-white/5 hover:text-gray-200'"
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
                    <button class="text-brand hover:text-white" @click="emit('save-title')">
                      <Check class="w-3 h-3" />
                    </button>
                    <button class="text-gray-500 hover:text-white" @click="emit('cancel-edit-title')">
                      <X class="w-3 h-3" />
                    </button>
                  </div>
                  <div v-else class="truncate">{{ c.title }}</div>
                </div>
              </div>
              
              <div v-if="editingChatId !== c.id" class="flex gap-1 shrink-0 ml-auto bg-black/40 rounded-md backdrop-blur-sm opacity-60 group-hover:opacity-100 transition-opacity">
                <button class="p-1 hover:text-white text-gray-300 transition-colors" @click.stop="emit('start-edit-title', c.id, c.title)">
                  <Pencil class="w-3.5 h-3.5" />
                </button>
                <button class="p-1 hover:text-red-400 text-gray-300 transition-colors" @click.stop="confirmDeleteChat(c)">
                  <Trash2 class="w-3.5 h-3.5" />
                </button>
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

  <!-- 删除确认弹窗 -->
  <div v-if="deleteConfirm" class="fixed inset-0 z-[60] flex items-center justify-center bg-slate-950/40 backdrop-blur-sm">
    <div class="w-[320px] rounded-2xl border border-white/10 bg-slate-900/70 backdrop-blur-xl shadow-2xl p-4 text-gray-200">
      <div class="text-sm font-semibold text-slate-50">{{ deleteConfirmTitle }}</div>
      <div class="text-xs text-slate-400 mt-2 leading-relaxed">{{ deleteConfirmMessage }}</div>
      <div class="mt-4 flex justify-end gap-2">
        <button class="px-3 py-1.5 rounded-lg bg-white/5 hover:bg-white/10 text-slate-300 transition-colors" @click="cancelDelete">
          取消
        </button>
        <button class="px-3 py-1.5 rounded-lg bg-red-500/20 hover:bg-red-500/30 text-red-300 transition-colors" @click="confirmDelete">
          删除
        </button>
      </div>
    </div>
  </div>

  <!-- 侧边栏开关 -->
  <div 
    class="fixed top-1/2 -translate-y-1/2 z-50 cursor-pointer p-2 bg-brand/30 hover:bg-brand/50 rounded-r-lg backdrop-blur-sm transition-all duration-300 border border-l-0 border-brand/40 shadow-lg"
    :class="collapsed ? 'left-0' : 'left-[21rem]'"
    @click="toggleCollapsed"
    title="切换侧边栏"
  >
    <component :is="collapsed ? ChevronRight : ChevronLeft" class="w-3 h-3 text-white" />
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
