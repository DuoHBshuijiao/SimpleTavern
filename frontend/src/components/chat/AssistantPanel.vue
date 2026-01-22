<script setup lang="ts">
/**
 * AssistantPanel - 聊天助手面板组件
 * 
 * 右侧滑出的聊天助手面板，用于与 AI 助手对话
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

// Markdown 渲染器
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
  if (window.confirm('确定删除？')) {
    emit('delete-message', m)
  }
}

function confirmReset() {
  if (window.confirm('确定清空与助理的所有上下文？')) {
    emit('reset')
  }
}
</script>

<template>
  <aside
    class="h-full bg-[#141418] border-l border-white/10 shadow-inner transition-all duration-300 overflow-hidden flex flex-col"
    :class="isOpen ? 'w-[360px] opacity-100' : 'w-0 opacity-0 pointer-events-none'"
  >
    <!-- 头部 -->
    <div class="flex items-center justify-between px-4 py-3 border-b border-white/10">
      <span class="text-xs font-bold text-gray-400 uppercase tracking-widest flex items-center gap-2">
        <span class="w-2 h-2 rounded-full bg-[#b76e79] animate-pulse"></span>
        聊天助手
      </span>
      <div class="flex items-center gap-2">
        <button class="text-gray-500 hover:text-white transition-colors" @click="emit('open-settings')">⋯</button>
        <button class="text-gray-500 hover:text-white transition-colors" @click="emit('update:isOpen', false)">×</button>
      </div>
    </div>

    <!-- 消息列表 -->
    <div class="flex-1 overflow-y-auto custom-scrollbar space-y-4 px-4 py-3">
      <div v-if="messages.length === 0" class="text-xs text-gray-600 text-center py-12 flex flex-col items-center gap-3">
        <div class="w-12 h-12 rounded-full bg-white/5 flex items-center justify-center text-xl">✨</div>
        开始和助手对话以获得帮助
      </div>
      <div
        v-for="m in messages"
        :key="m.id"
        class="flex flex-col gap-1 group"
        :class="m.role === 'user' ? 'items-end' : (m.role === 'system' ? 'items-center' : 'items-start')"
      >
        <div
          class="px-4 py-2.5 rounded-2xl text-sm leading-relaxed max-w-[90%] shadow-sm border transition-colors"
          :class="m.role === 'user'
            ? 'bg-[#b76e79]/20 border-[#b76e79]/30 text-gray-100 rounded-tr-sm'
            : (m.role === 'system'
              ? 'bg-[#0f0f12] border-white/10 text-gray-400 rounded-lg text-xs'
              : 'bg-white/5 border-white/5 text-gray-200 rounded-tl-sm')"
        >
          <div class="prose prose-invert prose-sm max-w-none" v-html="renderMarkdown(m.content)"></div>
        </div>
        <!-- 消息操作 -->
        <div v-if="m.role !== 'system'" class="flex items-center gap-3 px-1 opacity-0 group-hover:opacity-100 transition-opacity">
          <button
            v-if="m.role === 'assistant'"
            class="text-[10px] text-gray-600 hover:text-blue-400 transition-colors"
            @click="emit('rewrite-message', m)"
            :disabled="isGenerating"
          >
            重写
          </button>
          <button 
            class="text-[10px] text-gray-600 hover:text-brand transition-colors" 
            @click="emit('edit-message', m)" 
            :disabled="isGenerating"
          >
            编辑
          </button>
          <button 
            class="text-[10px] text-gray-600 hover:text-red-400 transition-colors" 
            :disabled="isGenerating"
            @click="confirmDelete(m)"
          >
            删除
          </button>
        </div>
      </div>
    </div>

    <!-- 输入区域 -->
    <div class="pt-4 pb-4 px-4 border-t border-white/10">
      <div class="relative">
        <textarea
          :value="draft"
          @input="emit('update:draft', ($event.target as HTMLTextAreaElement).value)"
          class="input textarea h-24 !bg-black/30 !border-white/5 focus:!border-[#b76e79]/40"
          placeholder="输入建议或要求 (Ctrl + Enter)..."
          :disabled="isGenerating"
          @keydown="handleKeydown"
        ></textarea>
      </div>
      <div class="flex items-center justify-between mt-3 gap-3">
        <ModernSelect
          :model-value="currentModel"
          :options="modelOptions"
          placement="top"
          placeholder="模型..."
          class="!w-[160px] !text-xs"
          dropdown-width="410"
          searchable
          allow-create
          @select="emit('select-model', $event)"
        />
        <div class="flex items-center gap-2">
          <button class="btn btn-sm btn-secondary" :disabled="isGenerating" @click="confirmReset">清空</button>
          <button 
            class="btn btn-sm btn-primary px-6" 
            :disabled="!draft.trim() || isGenerating" 
            @click="emit('send')"
          >
            <span v-if="isGenerating" class="animate-spin mr-2">⌛</span>
            发送
          </button>
        </div>
      </div>
      <div v-if="streamError" class="text-xs text-red-400 mt-2 bg-red-400/10 p-2 rounded-lg border border-red-400/20 truncate">
        {{ streamError }}
      </div>
    </div>
  </aside>
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
