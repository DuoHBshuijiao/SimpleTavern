<script setup lang="ts">
/**
 * MessageList - 消息列表组件
 * 风格：Obsidian Brutalist (Pure Flow)
 */
import { ref, nextTick } from 'vue'
import type { ChatMessage, CharacterCard, UserPersona } from '../../types/models'
import ModernAvatar from '../ModernAvatar.vue'
import MarkdownIt from 'markdown-it'

const props = defineProps<{
  messages: ChatMessage[]
  isGroup: boolean
  selectedCharacter: CharacterCard | null
  characters: CharacterCard[]
  selectedPersona: UserPersona | null
  userName: string
  userAvatarUrl: string | null
  characterAvatarUrl: string | null
  isGenerating: boolean
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

const scrollRef = ref<HTMLElement | null>(null)
const md = new MarkdownIt({ html: false, linkify: true, breaks: true })

function renderMarkdown(text: string) {
  return md.render(text ?? '')
}

function getCharacterById(id: string): CharacterCard | null {
  return props.characters.find(c => c.id === id) ?? null
}

function getMessageLabel(m: ChatMessage): string {
  if (m.role === 'user') return (m.senderName || props.userName)
  if (m.role === 'assistant') {
    if (m.characterId) {
      const char = getCharacterById(m.characterId)
      return char?.name || 'ENTITY'
    }
    return props.selectedCharacter?.name || 'ENTITY'
  }
  return 'SYSTEM'
}

function getMessageAvatar(m: ChatMessage): string | null {
  if (m.role === 'user') {
    return m.senderAvatar ? `/api/avatars/${m.senderAvatar}` : props.userAvatarUrl
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

function scrollToBottom() {
  nextTick(() => {
    if (scrollRef.value) {
      scrollRef.value.scrollTop = scrollRef.value.scrollHeight
    }
  })
}

defineExpose({ scrollToBottom, scrollRef })
</script>

<template>
  <div 
    ref="scrollRef" 
    class="flex-1 overflow-y-auto p-6 md:p-12 pb-32 scroll-smooth custom-scrollbar" 
  >
    <div class="max-w-4xl mx-auto space-y-12">
      <div 
        v-for="m in messages" 
        :key="m.id" 
        class="flex gap-6 group animate-fade-in" 
        :class="m.role === 'user' ? 'flex-row-reverse' : 'flex-row'"
      >
        <!-- 头像 -->
        <div class="flex-shrink-0">
          <ModernAvatar 
            v-if="m.role !== 'system'"
            :src="getMessageAvatar(m)"
            :name="getMessageLabel(m)"
            :size="32"
            rounded="rounded-none"
            class="border border-strong bg-dark-surface"
          />
        </div>

        <!-- 消息 -->
        <div class="flex flex-col flex-1 min-w-0" :class="m.role === 'user' ? 'items-end' : 'items-start'">
          <div class="flex items-center gap-3 mb-2 px-1">
            <span class="text-[9px] font-black uppercase tracking-[0.2em]" :class="m.role === 'user' ? 'text-brand' : 'text-text-muted'">
              {{ getMessageLabel(m) }}
            </span>
          </div>

          <div 
            class="w-full transition-all"
            :class="[
              m.role === 'user' 
                ? 'bg-dark-surface border-l-2 border-brand p-4' 
                : m.role === 'assistant'
                  ? 'bg-transparent p-0'
                  : 'bg-white/5 border border-dashed border-white/10 p-4 text-text-muted text-xs italic',
            ]"
          >
            <div
              class="md prose prose-invert max-w-none"
              :class="m.role === 'assistant' ? 'prose-base' : 'prose-sm'"
              :ref="(el) => emit('set-content-ref', m.id, el as HTMLElement | null)"
            >
              <div v-html="renderMarkdown(getDisplayContent(m))"></div>
            </div>

            <!-- 操作栏 -->
            <div 
              v-if="!isGenerating && m.role !== 'system'"
              class="flex items-center gap-4 mt-4 opacity-0 group-hover:opacity-100 transition-opacity"
              :class="m.role === 'user' ? 'justify-end' : 'justify-start'"
            >
              <template v-if="m.role === 'assistant'">
                <button v-if="hasMultipleVersions(m)" class="text-[9px] font-bold text-text-muted hover:text-brand" @click="emit('switch-previous-version', m)">PREV</button>
                <span v-if="hasMultipleVersions(m)" class="text-[9px] font-mono text-text-muted">{{ getCurrentVersionIndex(m) + 1 }}/{{ getVersionCount(m) }}</span>
                <button v-if="hasMultipleVersions(m)" class="text-[9px] font-bold text-text-muted hover:text-brand" @click="emit('switch-next-version', m)">NEXT</button>
                <button class="text-[9px] font-bold text-text-muted hover:text-brand" @click="emit('rewrite-message', m)">REGEN</button>
              </template>
              <button class="text-[9px] font-bold text-text-muted hover:text-brand" @click="emit('edit-message', m)">EDIT</button>
              <button class="text-[9px] font-bold text-text-muted hover:text-error" @click="emit('delete-message', m)">DEL</button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.custom-scrollbar::-webkit-scrollbar { width: 1px; }
.md :deep(p) { margin-bottom: 1.2rem; line-height: 1.6; }
.md :deep(p:last-child) { margin-bottom: 0; }
.md :deep(pre) { border-radius: 0; background: #000; border: 1px solid var(--color-border-strong); padding: 1rem; }
</style>
