<script setup lang="ts">
/**
 * MessageList - 消息列表组件
 * 
 * 显示聊天消息列表，支持版本切换、编辑、删除、重写等操作
 */
import { ref, nextTick } from 'vue'
import type { ChatMessage, CharacterCard, UserPersona } from '../../types/models'
import ModernAvatar from '../ModernAvatar.vue'
import MarkdownIt from 'markdown-it'

const props = defineProps<{
  messages: ChatMessage[]
  isGroup: boolean
  // 角色相关
  selectedCharacter: CharacterCard | null
  characters: CharacterCard[]
  // 用户相关
  selectedPersona: UserPersona | null
  userName: string
  userAvatarUrl: string | null
  characterAvatarUrl: string | null
  // 状态
  isGenerating: boolean
  // 版本相关
  getDisplayContent: (m: ChatMessage) => string
  hasMultipleVersions: (m: ChatMessage) => boolean
  getCurrentVersionIndex: (m: ChatMessage) => number
  getVersionCount: (m: ChatMessage) => number
}>()

const emit = defineEmits<{
  'edit-message': [m: ChatMessage]
  'delete-message': [m: ChatMessage]
  'rewrite-message': [m: ChatMessage]
  'switch-previous-version': [m: ChatMessage]
  'switch-next-version': [m: ChatMessage]
  'set-content-ref': [messageId: string, el: HTMLElement | null]
}>()

// 滚动容器引用
const scrollRef = ref<HTMLElement | null>(null)

// Markdown 渲染器
const md = new MarkdownIt({
  html: false,
  linkify: true,
  breaks: true,
})

function normalizeMarkdownInput(text: string) {
  return (text ?? '').replace(/(^|\n)\[([^\]\n]+)\]:(\s*)/g, (_m, p1, name, sp) => `${p1}[${name}]：${sp}`)
}

function renderMarkdown(text: string) {
  return md.render(normalizeMarkdownInput(text))
}

// 获取角色信息
function getCharacterById(id: string): CharacterCard | null {
  return props.characters.find(c => c.id === id) ?? null
}

// 获取消息标签
function getMessageLabel(m: ChatMessage): string {
  if (m.role === 'user') return (m.senderName || props.userName)
  if (m.role === 'assistant') {
    if (m.characterId) {
      const char = getCharacterById(m.characterId)
      return char?.name || 'AI'
    }
    return props.selectedCharacter?.name || 'AI'
  }
  return '系统'
}

// 获取消息头像
function getMessageAvatar(m: ChatMessage): string | null {
  if (m.role === 'user') {
    if (m.senderAvatar) return `/api/avatars/${m.senderAvatar}`
    return props.userAvatarUrl
  }
  if (m.role === 'assistant') {
    if (m.characterId) {
      const char = getCharacterById(m.characterId)
      return char?.avatar ? `/api/avatars/${char.avatar}` : null
    }
    return props.characterAvatarUrl
  }
  return null
}

// 确认删除
function confirmDelete(m: ChatMessage) {
  if (window.confirm('确定删除？')) {
    emit('delete-message', m)
  }
}

// 滚动到底部
function scrollToBottom() {
  nextTick(() => {
    if (scrollRef.value) {
      scrollRef.value.scrollTop = scrollRef.value.scrollHeight
    }
  })
}

// 暴露滚动方法
defineExpose({ scrollToBottom, scrollRef })
</script>

<template>
  <div 
    ref="scrollRef" 
    class="flex-1 overflow-y-auto p-4 pb-4 scroll-smooth custom-scrollbar" 
    :class="isGroup ? 'pt-28' : 'pt-20'"
  >
    <div class="max-w-4xl mx-auto space-y-8">
      <div 
        v-for="m in messages" 
        :key="m.id" 
        class="flex gap-4 group" 
        :class="m.role === 'user' ? 'flex-row-reverse' : 'flex-row'"
      >
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
            <span v-if="m.role === 'system'" class="text-[10px] bg-yellow-500/10 text-yellow-500 px-1.5 py-0.5 rounded">SYSTEM</span>
          </div>

          <!-- 气泡 -->
          <div 
            class="message-bubble relative px-5 py-3.5 rounded-2xl text-[15px] leading-7 shadow-sm transition-all duration-200 border max-w-full min-w-0"
            :class="[
              m.role === 'user' 
                ? 'bg-brand/10 border-brand/20 text-gray-100 rounded-tr-sm hover:border-brand/30' 
                : m.role === 'assistant'
                  ? 'bg-[#1e1e24] border-white/5 text-gray-200 rounded-tl-sm hover:bg-[#232329]'
                  : 'bg-yellow-500/5 border-yellow-500/10 text-gray-300',
            ]"
          >
            <div
              class="md prose prose-invert prose-sm max-w-none prose-p:my-1 prose-headings:my-2 prose-pre:bg-black/30 prose-pre:border prose-pre:border-white/5"
              :ref="(el) => emit('set-content-ref', m.id, el as HTMLElement | null)"
            >
              <div class="stream-markdown" v-html="renderMarkdown(getDisplayContent(m))"></div>
            </div>
          </div>

          <!-- 版本切换箭头 -->
          <div v-if="m.role === 'assistant' && hasMultipleVersions(m)" class="flex items-center justify-center gap-2 mt-1 px-1">
            <button 
              class="text-xs text-gray-500 hover:text-gray-300 transition-colors px-2 py-0.5 rounded hover:bg-white/5"
              @click="emit('switch-previous-version', m)"
              :title="`上一个版本 (${getCurrentVersionIndex(m) + 1}/${getVersionCount(m)})`"
            >
              ◀
            </button>
            <span class="text-xs text-gray-500">
              {{ getCurrentVersionIndex(m) + 1 }}/{{ getVersionCount(m) }}
            </span>
            <button 
              class="text-xs text-gray-500 hover:text-gray-300 transition-colors px-2 py-0.5 rounded hover:bg-white/5"
              @click="emit('switch-next-version', m)"
              :title="`下一个版本 (${getCurrentVersionIndex(m) + 1}/${getVersionCount(m)})`"
            >
              ▶
            </button>
          </div>

          <!-- 底部操作栏 -->
          <div class="flex items-center gap-2 mt-1 px-1 opacity-0 group-hover:opacity-100 transition-opacity">
            <button 
              v-if="m.role === 'assistant' && !m.id.startsWith('local_')" 
              class="text-xs text-gray-600 hover:text-blue-400 transition-colors" 
              @click="emit('rewrite-message', m)" 
              :disabled="isGenerating"
            >
              重写
            </button>
            <button 
              class="text-xs text-gray-600 hover:text-brand transition-colors" 
              @click="emit('edit-message', m)" 
              :disabled="isGenerating"
            >
              编辑
            </button>
            <button 
              class="text-xs text-gray-600 hover:text-red-400 transition-colors" 
              :disabled="isGenerating"
              @click="confirmDelete(m)"
            >
              删除
            </button>
          </div>
        </div>
      </div>
    </div>
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

/* Markdown 内容样式 */
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

.message-bubble .md {
  width: 100%;
}
.message-bubble .md .stream-markdown {
  overflow: hidden;
  word-wrap: break-word;
}
.message-bubble .md :deep(pre) {
  overflow-x: auto;
  max-width: 100%;
  scrollbar-width: thin;
  scrollbar-color: rgba(255, 255, 255, 0.2) transparent;
}
.message-bubble .md :deep(pre)::-webkit-scrollbar {
  height: 6px;
}
.message-bubble .md :deep(pre)::-webkit-scrollbar-track {
  background: transparent;
}
.message-bubble .md :deep(pre)::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.15);
  border-radius: 3px;
}
.message-bubble .md :deep(pre):hover::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.25);
}
.message-bubble .md :deep(pre code) {
  display: block;
  white-space: pre;
}
.message-bubble .md :deep(code) {
  word-break: break-word;
}
</style>
