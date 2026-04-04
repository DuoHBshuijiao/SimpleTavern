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
 *    - 导入：导入composables/useAssistant.ts的AssistantMessage类型、components/ModernSelect.vue、AssistantThread
 *    - 依赖：依赖vue
 *    - 位置：组件层，提供聊天助手面板功能
 */
import type { AssistantMessage } from '../../composables/useAssistant'
import ModernSelect from '../ModernSelect.vue'
import AssistantThread from './AssistantThread.vue'
import ConfirmPopover from '../../components/ConfirmPopover.vue'
import { Sparkles, Loader2, MoreHorizontal, X } from 'lucide-vue-next'
import { ref, watch, nextTick } from 'vue'

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
  currentPresetId?: string | null
  modelOptions: ModelOptions
  /** 当前正在流式接收的正文（用于打字机效果） */
  streamingContent?: string
  /** 当前正在流式接收的思考内容 */
  streamingReasoning?: string
  /** 是否显示记忆写入 / 破坏性工具开关（仅聊天作用域） */
  showToolPermissionToggles?: boolean
  allowWriteMemory?: boolean
  allowDestructiveTools?: boolean
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
  'toggle-write-memory': []
  'toggle-destructive': []
}>()

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
  onConfirm: () => {},
})

function closeConfirm() {
  confirmState.value.show = false
  confirmState.value.target = null
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
    message: '确定清空与助手的所有上下文？',
    confirmText: '清空',
    onConfirm: () => {
      emit('reset')
      closeConfirm()
    }
  }
}

// 消息列表滚动容器：打开面板时自动滚到底部
const messagesListEl = ref<HTMLElement | null>(null)

const PANEL_OPEN_DURATION_MS = 320

function scrollToBottom() {
  const run = () => {
    const el = messagesListEl.value
    if (el) el.scrollTop = el.scrollHeight
  }
  nextTick(() => {
    run()
    // 首次打开时面板尚未完成展开/布局，延迟再滚一次确保到底
    setTimeout(run, PANEL_OPEN_DURATION_MS)
  })
}

// 打开面板时滚到底部（含刷新后第一次打开）
watch(
  () => props.isOpen,
  (open) => {
    if (open) scrollToBottom()
  }
)

// 切换聊天后 messages 变化，若面板已打开则滚到底部，避免停在上一会话的滚动位置
watch(
  () => [props.messages.length, props.messages[props.messages.length - 1]?.id] as const,
  () => {
    if (props.isOpen) scrollToBottom()
  },
  { deep: false }
)
</script>

<template>
  <!-- Teleport 到 body，避免主聊天区（含 z-50 助手按钮等）的层叠上下文遮挡侧栏下半部分 -->
  <Teleport to="body">
  <aside
    class="fixed right-4 top-4 bottom-4 theme-panel-bg backdrop-blur-xl backdrop-saturate-[1.8] border border-[var(--color-border)] shadow-glass-panel rounded-2xl transition-all duration-300 overflow-hidden flex flex-col z-[100] pointer-events-auto"
    :class="isOpen ? 'translate-x-0 w-[360px] opacity-100' : 'translate-x-[calc(100%+20px)] w-[360px] opacity-0 pointer-events-none'"
    style="contain: content; will-change: transform, opacity;"
  >
    <!-- 头部 -->
    <div class="flex items-center justify-between px-4 py-3 border-b border-white/5 shrink-0 bg-white/5 backdrop-blur-md">
      <span class="text-xs font-bold text-gray-400 uppercase tracking-widest flex items-center gap-2 flex-wrap min-w-0">
        <span class="w-2 h-2 rounded-full bg-[#b76e79] animate-pulse shrink-0"></span>
        聊天助手
        <span
          v-if="allowWriteMemory"
          class="inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-semibold normal-case tracking-normal bg-brand/20 text-brand-foreground border border-brand/40"
          title="已允许记忆写入"
        >
          记忆
        </span>
        <span
          v-if="allowDestructiveTools"
          class="inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-semibold normal-case tracking-normal bg-amber-500/20 text-amber-100 border border-amber-500/40"
          title="已允许破坏性工具"
        >
          破坏
        </span>
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

    <!-- 消息列表：底部工具权限悬浮在列表之上（不占用独立条带） -->
    <div class="min-h-0 flex-1 relative flex flex-col overflow-hidden">
      <div
        ref="messagesListEl"
        class="min-h-0 min-w-0 flex-1 overflow-x-auto overflow-y-auto custom-scrollbar space-y-4 px-4 pt-3 pb-14"
      >
      <div v-if="messages.length === 0" class="text-xs text-gray-600 text-center py-12 flex flex-col items-center gap-3">
        <div class="w-12 h-12 rounded-full bg-white/5 flex items-center justify-center text-xl">
            <Sparkles class="w-6 h-6 text-yellow-400" />
        </div>
        开始和助手对话以获得帮助
      </div>
      <AssistantThread
        :messages="messages"
        :is-generating="isGenerating"
        :streaming-content="streamingContent"
        :streaming-reasoning="streamingReasoning"
        @edit-message="emit('edit-message', $event)"
        @delete-message="emit('delete-message', $event)"
        @rewrite-message="emit('rewrite-message', $event)"
      />
      </div>
      <div
        v-if="showToolPermissionToggles !== false"
        class="pointer-events-none absolute inset-x-0 bottom-0 z-10 flex flex-wrap items-end gap-2 px-4 pb-3 pt-2"
      >
        <div class="pointer-events-auto flex flex-wrap gap-2">
          <button
            type="button"
            class="text-xs px-2.5 py-1 rounded-lg border transition-colors shadow-lg backdrop-blur-sm"
            :class="allowWriteMemory
              ? 'bg-brand/30 border-brand text-brand-foreground shadow-[0_0_0_1px_rgba(183,110,121,0.35)]'
              : 'border-white/15 bg-black/40 text-gray-300 hover:border-white/25'"
            @click="emit('toggle-write-memory')"
          >
            记忆写入
          </button>
          <button
            type="button"
            class="text-xs px-2.5 py-1 rounded-lg border transition-colors shadow-lg backdrop-blur-sm"
            :class="allowDestructiveTools
              ? 'bg-amber-500/25 border-amber-500/60 text-amber-100 shadow-[0_0_0_1px_rgba(245,158,11,0.35)]'
              : 'border-white/15 bg-black/40 text-gray-300 hover:border-white/25'"
            @click="emit('toggle-destructive')"
          >
            破坏性工具
          </button>
        </div>
      </div>
    </div>

    <!-- 输入区域 -->
    <div
      class="shrink-0 pt-4 pb-4 px-4 border-t border-white/5 bg-black/10 backdrop-blur-sm shadow-[0_-12px_32px_-8px_rgba(0,0,0,0.35)] relative z-10"
    >
      <div class="relative">
        <textarea
          :value="draft"
          @input="emit('update:draft', ($event.target as HTMLTextAreaElement).value)"
          class="input textarea h-24 !bg-white/5 !border-white/10 focus:!border-brand-a40 focus:!bg-white/10 backdrop-blur-md"
          placeholder="输入建议或要求 (Ctrl + Enter)..."
          :disabled="isGenerating"
          @keydown="handleKeydown"
        ></textarea>
      </div>
      <div class="flex items-center justify-between mt-3 gap-3">
        <ModernSelect
          :model-value="currentModel"
          :selected-preset-id="currentPresetId ?? null"
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
    </div>

    <ConfirmPopover
      :show="confirmState.show"
      :target="confirmState.target"
      :title="confirmState.title"
      :message="confirmState.message"
      :confirm-text="confirmState.confirmText"
      @confirm="confirmState.onConfirm"
      @cancel="closeConfirm"
      @update:show="(value) => !value && closeConfirm()"
    />
  </aside>
  </Teleport>
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
