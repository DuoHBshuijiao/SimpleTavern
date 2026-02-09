<script setup lang="ts">
/**
 * AssistantPanel - 聊天助手面板组件
 *
 * 组件职责：
 * - 显示右侧滑出的聊天助手面板
 * - 显示助手对话消息列表
 * - 提供消息输入和发送功能
 * - 支持消息编辑、删除、重写操作
 * - 支持Markdown渲染
 * - 提供模型选择和重置功能
 *
 * Props说明：
 * - isOpen: 是否打开面板（v-model:isOpen）
 * - messages: 助手消息列表（来自composables/useAssistant.ts的AssistantMessage[]类型）
 * - draft: 输入草稿（v-model:draft）
 * - isGenerating: 是否正在生成
 * - streamError: 流式传输错误信息
 * - currentModel: 当前选中的模型
 * - modelOptions: 模型选项列表
 *
 * Emits说明：
 * - update:isOpen: 更新打开状态（v-model:isOpen）
 * - update:draft: 更新输入草稿（v-model:draft）
 * - send: 发送消息
 * - reset: 重置对话
 * - open-settings: 打开设置
 * - select-model: 选择模型
 * - edit-message: 编辑消息
 * - delete-message: 删除消息
 * - rewrite-message: 重写消息
 *
 * 使用的Composables：
 * 无（通过props接收数据）
 *
 * 使用的Stores：
 * 无
 *
 * 文件关系：
 *    - 被导入：被views/ChatPage.vue使用
 *    - 导入：导入markdown-it库、composables/useAssistant.ts的AssistantMessage类型、components/ModernSelect.vue
 *    - 依赖：依赖vue、markdown-it
 *    - 位置：组件层，提供聊天助手面板功能
 */
import MarkdownIt from 'markdown-it'
import type { AssistantMessage } from '../../composables/useAssistant'
import ModernSelect from '../ModernSelect.vue'
import ConfirmPopover from '../../components/ConfirmPopover.vue'
import { Sparkles, Loader2, MoreHorizontal, X } from 'lucide-vue-next'
import { ref } from 'vue'

interface ModelOption {
  label: string
  value: string
  presetId?: string | null
}

interface ModelOptionGroup {
  label: string
  options: ModelOption[]
}

type ModelOptions = (ModelOption | ModelOptionGroup | string)[]

const props = defineProps<{
  isOpen: boolean
  messages: AssistantMessage[]
  draft: string
  isGenerating: boolean
  streamError: string | null
  currentModel: string
  modelOptions: ModelOptions
  /** 思考链块列表：每项为 { messageId, content }，展示在对应消息之前 */
  reasoningBlocks?: Array<{ messageId: string; content: string }>
}>()

const emit = defineEmits<{
  'update:isOpen': [value: boolean]
  'update:draft': [value: string]
  'send': []
  'reset': []
  'open-settings': []
  'select-model': [option: { value: string; presetId?: string | null }]
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

/**
 * 渲染Markdown
 *
 * 使用MarkdownIt渲染Markdown文本为HTML。
 *
 * @param {string} text - Markdown文本
 * @returns {string} 渲染后的HTML
 */
function renderMarkdown(text: string) {
  return md.render(text ?? '')
}

/**
 * 处理键盘事件
 *
 * 当按下Ctrl+Enter时触发发送事件。
 *
 * @param {KeyboardEvent} e - 键盘事件
 */
function handleKeydown(e: KeyboardEvent) {
  if (e.ctrlKey && e.key === 'Enter') {
    emit('send')
  }
}

// 确认弹窗状态
const confirmState = ref<{
  show: boolean
  target: HTMLElement | null
  title: string
  message: string
  confirmText: string
  onConfirm: () => void
}>({
  show: false,
  target: null,
  title: '',
  message: '',
  confirmText: '确认',
  onConfirm: () => {}
})

function closeConfirm() {
  confirmState.value.show = false
  confirmState.value.target = null
}

/**
 * 确认删除消息
 *
 * 弹出确认对话框，确认后触发删除消息事件。
 *
 * @param {AssistantMessage} m - 要删除的消息
 * @param {Event} event - 点击事件
 */
function confirmDelete(m: AssistantMessage, event: Event) {
  confirmState.value = {
    show: true,
    target: event.currentTarget as HTMLElement,
    title: '删除消息',
    message: '确定删除这条消息？',
    confirmText: '删除',
    onConfirm: () => {
      emit('delete-message', m)
      closeConfirm()
    }
  }
}

/**
 * 确认重置对话
 *
 * 弹出确认对话框，确认后触发重置事件。
 *
 * @param {Event} event - 点击事件
 */
function confirmReset(event: Event) {
  confirmState.value = {
    show: true,
    target: event.currentTarget as HTMLElement,
    title: '清空对话',
    message: '确定清空与助理的所有上下文？',
    confirmText: '清空',
    onConfirm: () => {
      emit('reset')
      closeConfirm()
    }
  }
}

// 思考气泡：仅点击气泡体展开，仅点击图标收起
const expandedReasoningMessageId = ref<string | null>(null)

function isReasoningExpanded(messageId: string) {
  return expandedReasoningMessageId.value === messageId
}

function expandReasoning(messageId: string, e: MouseEvent) {
  if ((e.target as HTMLElement).closest('.reasoning-toggle-icon')) return
  expandedReasoningMessageId.value = messageId
}

function collapseReasoning(e: MouseEvent) {
  e.stopPropagation()
  expandedReasoningMessageId.value = null
}

/** 获取某条消息对应的思考链内容（用于显示在该消息上方） */
function getReasoningContentForMessage(messageId: string): string | undefined {
  const blocks = props.reasoningBlocks
  if (!Array.isArray(blocks)) return undefined
  const block = blocks.find((b) => b.messageId === messageId)
  return block?.content?.trim() || undefined
}
</script>

<template>
  <aside
    class="fixed right-4 top-4 bottom-4 bg-gradient-to-br from-slate-800/70 to-slate-700/50 backdrop-blur-xl backdrop-saturate-[1.8] border border-white/10 shadow-[0_8px_32px_rgba(0,0,0,0.3)] rounded-2xl transition-all duration-300 overflow-hidden flex flex-col z-20"
    :class="isOpen ? 'translate-x-0 w-[360px] opacity-100' : 'translate-x-[calc(100%+20px)] w-[360px] opacity-0 pointer-events-none'"
    style="contain: content; will-change: transform, opacity;"
  >
    <!-- 头部 -->
    <div class="flex items-center justify-between px-4 py-3 border-b border-white/5 shrink-0 bg-white/5 backdrop-blur-md">
      <span class="text-xs font-bold text-gray-400 uppercase tracking-widest flex items-center gap-2">
        <span class="w-2 h-2 rounded-full bg-[#b76e79] animate-pulse"></span>
        聊天助手
      </span>
      <div class="flex items-center gap-2">
        <button class="text-gray-500 hover:text-white transition-colors" @click="emit('open-settings')">
            <MoreHorizontal class="w-4 h-4" />
        </button>
        <button class="text-gray-500 hover:text-white transition-colors" @click="emit('update:isOpen', false)">
            <X class="w-4 h-4" />
        </button>
      </div>
    </div>

    <!-- 消息列表 -->
    <div class="flex-1 overflow-y-auto custom-scrollbar space-y-4 px-4 py-3">
      <div v-if="messages.length === 0" class="text-xs text-gray-600 text-center py-12 flex flex-col items-center gap-3">
        <div class="w-12 h-12 rounded-full bg-white/5 flex items-center justify-center text-xl">
            <Sparkles class="w-6 h-6 text-yellow-400" />
        </div>
        开始和助手对话以获得帮助
      </div>
      <div
        v-for="m in messages"
        :key="m.id"
        class="flex flex-col gap-1 group"
        :class="m.role === 'user' ? 'items-end' : (m.role === 'system' ? 'items-center' : 'items-start')"
      >
        <!-- 思考链气泡：在对应消息（助手或工具）上方，小圆角，默认折叠 100px，仅点击气泡展开、仅点击图标收起 -->
        <div
          v-if="getReasoningContentForMessage(m.id)"
          class="w-full max-w-[90%] rounded-lg border border-blue-500 bg-blue-800/25 text-gray-300 text-xs leading-relaxed relative transition-[max-height] duration-300"
          :class="isReasoningExpanded(m.id) ? 'max-h-[80vh] overflow-y-auto' : 'max-h-[100px] overflow-hidden cursor-pointer'"
          @click="expandReasoning(m.id, $event)"
        >
          <div class="pr-8 py-2.5 pl-3 whitespace-pre-wrap break-words">{{ getReasoningContentForMessage(m.id) }}</div>
          <button
            type="button"
            class="reasoning-toggle-icon absolute top-2 right-2 w-6 h-6 flex items-center justify-center rounded hover:bg-white/10 transition-transform duration-200"
            :class="isReasoningExpanded(m.id) ? 'rotate-90' : ''"
            aria-label="收起思考"
            @click="collapseReasoning"
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <polyline points="15 18 9 12 15 6" />
            </svg>
          </button>
        </div>
        <div
          class="px-4 py-2.5 rounded-2xl text-sm leading-relaxed max-w-[90%] shadow-sm border transition-colors"
          :class="m.role === 'user'
            ? 'bg-brand/20 backdrop-blur-sm border-brand/20 text-gray-100 rounded-tr-sm'
            : (m.role === 'system'
              ? 'bg-yellow-500/10 border-yellow-500/20 text-gray-300 rounded-lg text-xs'
              : 'bg-white/5 backdrop-blur-md border-white/10 text-gray-200 rounded-tl-sm')"
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
            @click="confirmDelete(m, $event)"
          >
            删除
          </button>
        </div>
      </div>
    </div>

    <!-- 输入区域 -->
    <div class="pt-4 pb-4 px-4 border-t border-white/5 bg-black/10 backdrop-blur-sm">
      <div class="relative">
        <textarea
          :value="draft"
          @input="emit('update:draft', ($event.target as HTMLTextAreaElement).value)"
          class="input textarea h-24 !bg-white/5 !border-white/10 focus:!border-brand/40 focus:!bg-white/10 backdrop-blur-md"
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
          <button class="btn btn-sm btn-secondary" :disabled="isGenerating" @click="confirmReset($event)">清空</button>
          <button 
            class="btn btn-sm btn-primary px-6" 
            :disabled="!draft.trim() || isGenerating" 
            @click="emit('send')"
          >
            <Loader2 v-if="isGenerating" class="animate-spin w-3 h-3 mr-2" />
            发送
          </button>
        </div>
      </div>
      <div v-if="streamError" class="text-xs text-red-400 mt-2 bg-red-400/10 p-2 rounded-lg border border-red-400/20 truncate">
        {{ streamError }}
      </div>
    </div>

    <!-- 确认弹窗 -->
    <ConfirmPopover
      :show="confirmState.show"
      :target="confirmState.target"
      :title="confirmState.title"
      :message="confirmState.message"
      :confirm-text="confirmState.confirmText"
      @confirm="confirmState.onConfirm"
      @cancel="closeConfirm"
      @update:show="(val) => !val && closeConfirm()"
    />
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
