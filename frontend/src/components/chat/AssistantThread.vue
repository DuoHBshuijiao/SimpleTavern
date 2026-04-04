<script setup lang="ts">
import MarkdownIt from 'markdown-it'
import { ref } from 'vue'
import type { AssistantMessage } from '../../composables/useAssistant'
import ConfirmPopover from '../ConfirmPopover.vue'

const STREAMING_REASONING_ID = '_streaming_pending'

const props = withDefaults(defineProps<{
  messages: AssistantMessage[]
  isGenerating: boolean
  reasoningBlocks?: Array<{ messageId: string; content: string }>
  streamingContent?: string
  streamingReasoning?: string
  showMessageActions?: boolean
}>(), {
  showMessageActions: true,
})

const emit = defineEmits<{
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
    },
  }
}

const expandedReasoningMessageId = ref<string | null>(null)

function isReasoningExpanded(messageId: string) {
  return expandedReasoningMessageId.value === messageId
}

function expandReasoning(messageId: string, e: MouseEvent) {
  if ((e.target as HTMLElement).closest('.reasoning-toggle-icon')) return
  expandedReasoningMessageId.value = messageId
}

function toggleReasoning(messageId: string, e: MouseEvent) {
  e.stopPropagation()
  expandedReasoningMessageId.value = expandedReasoningMessageId.value === messageId ? null : messageId
}

/** 从 API 恢复的 assistant 上的 reasoningContent，或旧版 reasoningBlocks */
function getPersistedReasoningForAssistant(m: AssistantMessage): string | undefined {
  const rc = typeof m.reasoningContent === 'string' ? m.reasoningContent.trim() : ''
  if (rc) return rc
  const blocks = props.reasoningBlocks
  if (!Array.isArray(blocks)) return undefined
  const block = blocks.find((entry) => entry.messageId === m.id)
  return block?.content?.trim() || undefined
}

function rowClass(message: AssistantMessage) {
  if (message.role === 'user') return 'items-end'
  if (message.role === 'system' || message.role === 'tool') return 'items-center'
  return 'items-start'
}

function showMainBubble(message: AssistantMessage): boolean {
  if (message.role === 'user' || message.role === 'system') return true
  if (message.role === 'assistant') return Boolean((message.content ?? '').trim())
  return true
}

function parseToolContent(raw: string): Record<string, unknown> | null {
  if (!raw.trim()) return null
  try {
    const parsed = JSON.parse(raw) as unknown
    return parsed && typeof parsed === 'object' ? (parsed as Record<string, unknown>) : null
  } catch {
    return null
  }
}

function getToolRecord(message: AssistantMessage): Record<string, unknown> | null {
  if (message.toolRecord && typeof message.toolRecord === 'object') return message.toolRecord
  const parsed = parseToolContent(message.content ?? '')
  if (parsed && typeof parsed.toolName === 'string') return parsed
  return null
}

function getToolStepTitle(message: AssistantMessage): string {
  const record = getToolRecord(message)
  const toolName = typeof record?.toolName === 'string' ? record.toolName : '未知工具'
  const loopIndex = typeof record?.loopIndex === 'number' ? record.loopIndex : null
  return loopIndex != null ? `步骤 ${loopIndex + 1} · ${toolName}` : toolName
}

function getToolMessage(message: AssistantMessage): string {
  const record = getToolRecord(message)
  if (typeof record?.message === 'string' && record.message.trim()) return record.message
  const parsed = parseToolContent(message.content ?? '')
  if (typeof parsed?.message === 'string' && parsed.message.trim()) return parsed.message
  return ''
}

function getToolArgsDigest(message: AssistantMessage): string {
  const record = getToolRecord(message)
  return typeof record?.argsDigest === 'string' ? record.argsDigest : ''
}

function isToolOk(message: AssistantMessage): boolean {
  const record = getToolRecord(message)
  if (typeof record?.ok === 'boolean') return record.ok
  const parsed = parseToolContent(message.content ?? '')
  return Boolean(parsed?.ok)
}

function getToolCode(message: AssistantMessage): string {
  const record = getToolRecord(message)
  if (typeof record?.code === 'string' && record.code.trim()) return record.code
  const parsed = parseToolContent(message.content ?? '')
  return typeof parsed?.code === 'string' ? parsed.code : ''
}

function getToolStatusLabel(message: AssistantMessage): string {
  return isToolOk(message) ? '成功' : (getToolCode(message) || '失败')
}

function getToolStatusClass(message: AssistantMessage): string {
  return isToolOk(message)
    ? 'bg-emerald-500/15 text-emerald-200 border border-emerald-400/30'
    : 'bg-amber-500/15 text-amber-100 border border-amber-400/30'
}

function getToolDetailContent(message: AssistantMessage): string {
  const raw = message.content ?? ''
  if (!raw.trim()) return ''
  const parsed = parseToolContent(raw)
  return parsed ? JSON.stringify(parsed, null, 2) : raw
}

const showStreamingOverlay = () =>
  props.isGenerating && ((props.streamingReasoning ?? '').trim() !== '' || (props.streamingContent ?? '') !== '')
</script>

<template>
  <div class="assistant-thread-contents flex w-full min-w-0 flex-col gap-4">
  <div
    v-for="message in messages"
    :key="message.id"
    class="flex w-full min-w-0 flex-col gap-1 group"
    :class="rowClass(message)"
  >
    <!-- 独立思考段（流式提交后的 role=reasoning） -->
    <template v-if="message.role === 'reasoning'">
      <div
        class="reasoning-bubble-surface w-full min-w-0 max-w-[90%] rounded-lg text-xs leading-relaxed relative transition-[max-height] duration-300"
        :class="isReasoningExpanded(message.id) ? 'max-h-[80vh] overflow-y-auto' : 'max-h-[100px] overflow-hidden cursor-pointer'"
        @click="expandReasoning(message.id, $event)"
      >
        <div class="pr-8 py-2.5 pl-3 whitespace-pre-wrap break-words">{{ message.content }}</div>
        <button
          type="button"
          class="reasoning-toggle-icon absolute top-2 right-2 w-6 h-6 flex items-center justify-center rounded hover:bg-white/10 transition-transform duration-200"
          :class="isReasoningExpanded(message.id) ? 'rotate-90' : ''"
          :aria-label="isReasoningExpanded(message.id) ? '收起思考' : '展开思考'"
          @click="toggleReasoning(message.id, $event)"
        >
          <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="15 18 9 12 15 6" />
          </svg>
        </button>
      </div>
    </template>

    <template v-else-if="message.role === 'tool'">
      <div
        class="min-w-0 max-w-[90%] px-4 py-2.5 rounded-2xl text-sm leading-relaxed shadow-sm border transition-colors bg-yellow-500/10 border-yellow-500/20 text-gray-300 rounded-lg text-xs"
      >
        <div class="flex items-start justify-between gap-3 mb-2">
          <div class="min-w-0">
            <div class="text-[10px] uppercase tracking-wider text-yellow-500/80">工具步骤</div>
            <div class="text-sm text-gray-100 break-words">{{ getToolStepTitle(message) }}</div>
          </div>
          <span class="shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold" :class="getToolStatusClass(message)">
            {{ getToolStatusLabel(message) }}
          </span>
        </div>
        <div v-if="getToolMessage(message)" class="text-xs text-gray-200 whitespace-pre-wrap break-words">
          {{ getToolMessage(message) }}
        </div>
        <div v-if="getToolArgsDigest(message)" class="mt-2 text-[10px] text-gray-400 break-all">
          argsDigest: {{ getToolArgsDigest(message) }}
        </div>
        <details class="mt-2 rounded-lg border border-white/8 bg-black/20 overflow-hidden">
          <summary class="cursor-pointer px-3 py-2 text-[11px] text-gray-300 select-none">查看结果 JSON</summary>
          <pre class="max-w-full overflow-x-auto px-3 pb-3 text-[11px] leading-relaxed text-gray-300 whitespace-pre-wrap break-all break-words">{{ getToolDetailContent(message) }}</pre>
        </details>
      </div>
    </template>

    <template v-else>
      <div
        v-if="message.role === 'assistant' && getPersistedReasoningForAssistant(message)"
        class="reasoning-bubble-surface w-full min-w-0 max-w-[90%] rounded-lg text-xs leading-relaxed relative transition-[max-height] duration-300"
        :class="isReasoningExpanded(message.id) ? 'max-h-[80vh] overflow-y-auto' : 'max-h-[100px] overflow-hidden cursor-pointer'"
        @click="expandReasoning(message.id, $event)"
      >
        <div class="pr-8 py-2.5 pl-3 whitespace-pre-wrap break-words">{{ getPersistedReasoningForAssistant(message) }}</div>
        <button
          type="button"
          class="reasoning-toggle-icon absolute top-2 right-2 w-6 h-6 flex items-center justify-center rounded hover:bg-white/10 transition-transform duration-200"
          :class="isReasoningExpanded(message.id) ? 'rotate-90' : ''"
          :aria-label="isReasoningExpanded(message.id) ? '收起思考' : '展开思考'"
          @click="toggleReasoning(message.id, $event)"
        >
          <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="15 18 9 12 15 6" />
          </svg>
        </button>
      </div>
      <div
        v-if="showMainBubble(message)"
        class="min-w-0 max-w-[90%] px-4 py-2.5 rounded-2xl text-sm leading-relaxed shadow-sm border transition-colors"
        :class="message.role === 'user'
          ? 'bg-brand-a20 backdrop-blur-sm border-brand-a20 text-gray-100 rounded-tr-sm'
          : (message.role === 'system'
            ? 'bg-yellow-500/10 border-yellow-500/20 text-gray-300 rounded-lg text-xs'
            : 'bg-white/5 backdrop-blur-md border-white/10 text-gray-200 rounded-tl-sm')"
      >
        <div
          class="prose prose-invert prose-sm max-w-none"
          v-html="renderMarkdown(message.content ?? '')"
        ></div>
      </div>
    </template>

    <div
      v-if="showMessageActions && message.role !== 'system' && message.role !== 'tool' && message.role !== 'reasoning'"
      class="flex items-center gap-3 px-1 opacity-0 group-hover:opacity-100 transition-opacity"
    >
      <button
        v-if="message.role === 'assistant'"
        class="text-[10px] text-gray-600 hover:text-blue-400 transition-colors"
        :disabled="isGenerating"
        @click="emit('rewrite-message', message)"
      >
        重写
      </button>
      <button
        class="text-[10px] text-gray-600 hover:text-brand transition-colors"
        :disabled="isGenerating"
        @click="emit('edit-message', message)"
      >
        编辑
      </button>
      <button
        class="text-[10px] text-gray-600 hover:text-red-400 transition-colors"
        :disabled="isGenerating"
        @click="confirmDelete(message, $event)"
      >
        删除
      </button>
    </div>
  </div>

  <!-- 当前轮次尚未提交到 messages 的流式思考 / 正文（顺序：思考在上） -->
  <div
    v-if="showStreamingOverlay()"
    class="flex w-full min-w-0 flex-col gap-1 items-start"
  >
    <div
      v-if="(streamingReasoning ?? '').trim()"
      class="reasoning-bubble-surface w-full min-w-0 max-w-[90%] rounded-lg text-xs leading-relaxed relative transition-[max-height] duration-300"
      :class="isReasoningExpanded(STREAMING_REASONING_ID) ? 'max-h-[80vh] overflow-y-auto' : 'max-h-[100px] overflow-hidden cursor-pointer'"
      @click="expandReasoning(STREAMING_REASONING_ID, $event)"
    >
      <div class="pr-8 py-2.5 pl-3 whitespace-pre-wrap break-words">{{ (streamingReasoning ?? '').trim() }}</div>
      <button
        type="button"
        class="reasoning-toggle-icon absolute top-2 right-2 w-6 h-6 flex items-center justify-center rounded hover:bg-white/10 transition-transform duration-200"
        :class="isReasoningExpanded(STREAMING_REASONING_ID) ? 'rotate-90' : ''"
        :aria-label="isReasoningExpanded(STREAMING_REASONING_ID) ? '收起思考' : '展开思考'"
        @click="toggleReasoning(STREAMING_REASONING_ID, $event)"
      >
        <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="15 18 9 12 15 6" />
        </svg>
      </button>
    </div>
    <div
      v-if="(streamingContent ?? '') !== ''"
      class="min-w-0 max-w-[90%] px-4 py-2.5 rounded-2xl text-sm leading-relaxed shadow-sm border transition-colors bg-white/5 backdrop-blur-md border-white/10 text-gray-200 rounded-tl-sm"
    >
      <div
        class="prose prose-invert prose-sm max-w-none"
        v-html="renderMarkdown(streamingContent ?? '')"
      ></div>
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
  </div>
</template>
