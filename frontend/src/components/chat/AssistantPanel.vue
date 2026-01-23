<script setup lang="ts">
/**
 * AssistantPanel - 聊天助手面板组件
 * 风格：Radical Swiss Modernism 2.0 (Sharp, High Contrast)
 */
import MarkdownIt from 'markdown-it'
import type { AssistantMessage } from '../../composables/useAssistant'
import ModernSelect from '../ModernSelect.vue'

const props = defineProps<{
  isOpen: boolean
  messages: AssistantMessage[]
  draft: string
  isGenerating: boolean
  streamError: string | null
  currentModel: string
  modelOptions: any[]
}>()

const emit = defineEmits<{
  'update:isOpen': [value: boolean]
  'update:draft': [value: string]
  'send': []
  'reset': []
  'open-settings': []
  'select-model': [option: any]
  'edit-message': [m: AssistantMessage]
  'delete-message': [m: AssistantMessage]
  'rewrite-message': [m: AssistantMessage]
}>()

const md = new MarkdownIt({
  html: false,
  linkify: true,
  breaks: true,
})

function renderMarkdown(text: string) {
  return md.render(text ?? '')
}

function handleKeydown(e: KeyboardEvent) {
  if (e.ctrlKey && e.key === 'Enter') {
    emit('send')
  }
}

function confirmDelete(m: AssistantMessage) {
  if (window.confirm('Delete this entry?')) {
    emit('delete-message', m)
  }
}

function confirmReset() {
  if (window.confirm('Clear all assistant protocol context?')) {
    emit('reset')
  }
}
</script>

<template>
  <aside
    class="h-full bg-dark-bg border-l border-strong shadow-2xl transition-all duration-300 overflow-hidden flex flex-col"
    :class="isOpen ? 'w-[400px] opacity-100' : 'w-0 opacity-0 pointer-events-none'"
  >
    <!-- Header - Bold Swiss -->
    <div class="flex items-center justify-between px-6 py-4 border-b border-strong bg-surface">
      <span class="text-xs font-black text-brand uppercase tracking-[0.3em] flex items-center gap-3">
        <span class="w-2 h-2 bg-brand animate-pulse"></span>
        Assistant Protocol
      </span>
      <div class="flex items-center gap-4">
        <button class="text-text-muted hover:text-brand transition-colors text-lg" @click="emit('open-settings')">⚙</button>
        <button class="text-text-muted hover:text-error transition-colors text-lg" @click="emit('update:isOpen', false)">✕</button>
      </div>
    </div>

    <!-- Message List -->
    <div class="flex-1 overflow-y-auto custom-scrollbar space-y-8 px-6 py-6">
      <div v-if="messages.length === 0" class="text-[10px] font-black text-text-muted text-center py-20 flex flex-col items-center gap-4 uppercase tracking-[0.2em]">
        <div class="text-4xl text-brand">?</div>
        Initialize session to begin
      </div>
      <div
        v-for="m in messages"
        :key="m.id"
        class="flex flex-col gap-2 group"
        :class="m.role === 'user' ? 'items-end' : (m.role === 'system' ? 'items-center' : 'items-start')"
      >
        <span class="text-[8px] font-black uppercase tracking-widest text-text-muted">{{ m.role }}</span>
        <div
          class="p-4 rounded-sm text-sm leading-relaxed w-full border transition-all"
          :class="m.role === 'user'
            ? 'bg-brand/5 border-brand/30 text-text-primary'
            : (m.role === 'system'
              ? 'bg-dark-bg border-dashed border-subtle text-text-muted text-[10px] italic'
              : 'bg-surface border-subtle text-text-secondary')"
        >
          <div class="prose prose-invert prose-sm max-w-none" v-html="renderMarkdown(m.content)"></div>
        </div>
        <!-- Actions -->
        <div v-if="m.role !== 'system'" class="flex items-center gap-4 px-1 opacity-0 group-hover:opacity-100 transition-opacity">
          <button
            v-if="m.role === 'assistant'"
            class="text-[10px] font-black text-text-muted hover:text-brand uppercase tracking-widest"
            @click="emit('rewrite-message', m)"
            :disabled="isGenerating"
          >
            Regen
          </button>
          <button 
            class="text-[10px] font-black text-text-muted hover:text-brand uppercase tracking-widest" 
            @click="emit('edit-message', m)" 
            :disabled="isGenerating"
          >
            Edit
          </button>
          <button 
            class="text-[10px] font-black text-text-muted hover:text-error uppercase tracking-widest" 
            :disabled="isGenerating"
            @click="confirmDelete(m)"
          >
            Del
          </button>
        </div>
      </div>
    </div>

    <!-- Input Area -->
    <div class="p-6 border-t border-strong bg-surface">
      <div class="relative">
        <textarea
          :value="draft"
          @input="emit('update:draft', ($event.target as HTMLTextAreaElement).value)"
          class="input textarea h-32 !bg-dark-bg !border-strong font-mono text-xs uppercase tracking-tighter"
          placeholder="DISPATCH COMMAND..."
          :disabled="isGenerating"
          @keydown="handleKeydown"
        ></textarea>
      </div>
      <div class="flex items-center justify-between mt-4 gap-4">
        <ModernSelect
          :model-value="currentModel"
          :options="modelOptions"
          placement="top"
          class="!w-[180px] !text-[10px] font-black"
          @select="emit('select-model', $event)"
        />
        <div class="flex items-center gap-2">
          <button class="btn btn-xs btn-secondary font-black uppercase tracking-widest" :disabled="isGenerating" @click="confirmReset">Reset</button>
          <button 
            class="btn btn-sm btn-primary px-8 font-black uppercase tracking-widest" 
            :disabled="!draft.trim() || isGenerating" 
            @click="emit('send')"
          >
            {{ isGenerating ? 'WAIT' : 'SEND' }}
          </button>
        </div>
      </div>
      <div v-if="streamError" class="text-[10px] font-black uppercase tracking-widest text-error border border-error px-3 py-2 mt-4 truncate">
        PROTOCOL ERROR: {{ streamError }}
      </div>
    </div>
  </aside>
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
</style>
