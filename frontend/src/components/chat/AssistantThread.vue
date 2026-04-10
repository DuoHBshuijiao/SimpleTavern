<script setup lang="ts">
import MarkdownIt from 'markdown-it'
import { onBeforeUnmount, ref } from 'vue'
import type { AssistantMessage } from '../../composables/useAssistant'
import type { AssistantAttachment } from '../../types/models'
import ConfirmPopover from '../ConfirmPopover.vue'

const STREAMING_REASONING_ID = '_streaming_pending'

const props = withDefaults(defineProps<{
  messages: AssistantMessage[]
  isGenerating: boolean
  reasoningBlocks?: Array<{ messageId: string; content: string }>
  streamingContent?: string
  streamingReasoning?: string
  showMessageActions?: boolean
  attachmentScope?: 'chat' | 'workspace'
  chatId?: string | null
}>(), {
  showMessageActions: true,
  attachmentScope: 'chat',
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
const expandedTextAttachmentId = ref<string | null>(null)
const textAttachmentContent = ref<Record<string, string>>({})
const textAttachmentError = ref<Record<string, string>>({})
const loadingTextAttachmentIds = ref<Record<string, boolean>>({})

type ImagePreviewWindow = {
  id: number
  src: string
  alt: string
  scale: number
  position: { x: number; y: number }
  dragStart: { x: number; y: number }
  positionAtDragStart: { x: number; y: number }
  isDragging: boolean
  zIndex: number
}

const imagePreviews = ref<ImagePreviewWindow[]>([])
const activeDraggingPreviewId = ref<number | null>(null)
let previewWindowIdSeed = 0
let previewWindowZSeed = 1450

function isReasoningExpanded(messageId: string) {
  return expandedReasoningMessageId.value === messageId
}

function buildAttachmentUrl(attachment: AssistantAttachment): string {
  const params = new URLSearchParams({ scope: props.attachmentScope })
  if (props.chatId) params.set('chatId', props.chatId)
  params.set('storageScope', attachment.storageScope)
  params.set('storageKey', attachment.storageKey)
  params.set('filename', attachment.filename)
  params.set('mimeType', attachment.mimeType)
  params.set('kind', attachment.kind)
  return `/api/assistant/attachments/${encodeURIComponent(attachment.id)}?${params.toString()}`
}

function getAttachmentLabel(attachment: AssistantAttachment): string {
  return attachment.originalName || attachment.filename
}

function getAttachmentExt(attachment: AssistantAttachment): string {
  const label = getAttachmentLabel(attachment)
  const index = label.lastIndexOf('.')
  if (index < 0) return attachment.kind === 'text' ? 'txt' : 'img'
  return label.slice(index + 1).toLowerCase() || (attachment.kind === 'text' ? 'txt' : 'img')
}

function getMessageAttachments(message: AssistantMessage): AssistantAttachment[] {
  return Array.isArray(message.attachments) ? message.attachments : []
}

function getTextAttachments(message: AssistantMessage): AssistantAttachment[] {
  return getMessageAttachments(message).filter((attachment) => attachment.kind === 'text')
}

function getImageAttachments(message: AssistantMessage): AssistantAttachment[] {
  return getMessageAttachments(message).filter((attachment) => attachment.kind === 'image')
}

function hasAnyAttachment(message: AssistantMessage): boolean {
  return getMessageAttachments(message).length > 0
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
  if (message.role === 'user') return Boolean((message.content ?? '').trim()) || hasAnyAttachment(message)
  if (message.role === 'system') return true
  if (message.role === 'assistant') return Boolean((message.content ?? '').trim())
  return true
}

async function toggleTextAttachment(attachment: AssistantAttachment) {
  const nextExpanded = expandedTextAttachmentId.value === attachment.id ? null : attachment.id
  expandedTextAttachmentId.value = nextExpanded
  if (nextExpanded !== attachment.id) return
  if (textAttachmentContent.value[attachment.id] || loadingTextAttachmentIds.value[attachment.id]) return
  loadingTextAttachmentIds.value = { ...loadingTextAttachmentIds.value, [attachment.id]: true }
  try {
    const res = await fetch(buildAttachmentUrl(attachment))
    if (!res.ok) {
      throw new Error(props.attachmentScope === 'workspace' ? '附件已随工作区清理' : '附件不可用')
    }
    const text = await res.text()
    textAttachmentContent.value = { ...textAttachmentContent.value, [attachment.id]: text }
    textAttachmentError.value = { ...textAttachmentError.value, [attachment.id]: '' }
  } catch (error) {
    textAttachmentError.value = {
      ...textAttachmentError.value,
      [attachment.id]: error instanceof Error ? error.message : '附件不可用',
    }
  } finally {
    loadingTextAttachmentIds.value = { ...loadingTextAttachmentIds.value, [attachment.id]: false }
  }
}

function removePreviewDragListeners() {
  window.removeEventListener('mousemove', onPreviewDragMove)
  window.removeEventListener('mouseup', stopPreviewDrag)
}

function getPreviewById(id: number) {
  return imagePreviews.value.find((preview) => preview.id === id)
}

function bringPreviewToFront(id: number) {
  const preview = getPreviewById(id)
  if (!preview) return
  previewWindowZSeed += 1
  preview.zIndex = previewWindowZSeed
}

function openImagePreview(src: string, alt: string) {
  previewWindowIdSeed += 1
  previewWindowZSeed += 1
  const offset = ((previewWindowIdSeed - 1) % 6) * 24
  imagePreviews.value.push({
    id: previewWindowIdSeed,
    src,
    alt,
    scale: 1,
    position: { x: offset, y: offset },
    dragStart: { x: 0, y: 0 },
    positionAtDragStart: { x: 0, y: 0 },
    isDragging: false,
    zIndex: previewWindowZSeed,
  })
}

function closeImagePreview(id: number) {
  const preview = getPreviewById(id)
  if (preview?.isDragging) {
    preview.isDragging = false
    activeDraggingPreviewId.value = null
    removePreviewDragListeners()
  }
  imagePreviews.value = imagePreviews.value.filter((item) => item.id !== id)
}

function getPreviewDialogStyle(preview: ImagePreviewWindow) {
  return {
    zIndex: preview.zIndex,
    transform: `translate(-50%, -50%) translate(${preview.position.x}px, ${preview.position.y}px) scale(${preview.scale})`,
  }
}

function handlePreviewWheel(id: number, event: WheelEvent) {
  event.preventDefault()
  const preview = getPreviewById(id)
  if (!preview) return
  bringPreviewToFront(id)
  const oldScale = preview.scale
  const delta = event.deltaY < 0 ? 0.1 : -0.1
  const nextScale = Math.min(5, Math.max(0.3, Number((oldScale + delta).toFixed(3))))
  if (nextScale === oldScale) return
  const viewportCenterX = window.innerWidth / 2
  const viewportCenterY = window.innerHeight / 2
  const pointerFromCenterX = event.clientX - viewportCenterX
  const pointerFromCenterY = event.clientY - viewportCenterY
  const ratio = nextScale / oldScale
  preview.position = {
    x: ratio * preview.position.x + (1 - ratio) * pointerFromCenterX,
    y: ratio * preview.position.y + (1 - ratio) * pointerFromCenterY,
  }
  preview.scale = nextScale
}

function startPreviewDrag(id: number, event: MouseEvent) {
  if (event.button !== 0) return
  const preview = getPreviewById(id)
  if (!preview) return
  event.preventDefault()
  activeDraggingPreviewId.value = id
  preview.isDragging = true
  preview.dragStart = { x: event.clientX, y: event.clientY }
  preview.positionAtDragStart = { ...preview.position }
  bringPreviewToFront(id)
  window.addEventListener('mousemove', onPreviewDragMove)
  window.addEventListener('mouseup', stopPreviewDrag)
}

function onPreviewDragMove(event: MouseEvent) {
  if (activeDraggingPreviewId.value == null) return
  const preview = getPreviewById(activeDraggingPreviewId.value)
  if (!preview || !preview.isDragging) return
  const offsetX = event.clientX - preview.dragStart.x
  const offsetY = event.clientY - preview.dragStart.y
  preview.position = {
    x: preview.positionAtDragStart.x + offsetX,
    y: preview.positionAtDragStart.y + offsetY,
  }
}

function stopPreviewDrag() {
  if (activeDraggingPreviewId.value != null) {
    const preview = getPreviewById(activeDraggingPreviewId.value)
    if (preview) preview.isDragging = false
  }
  activeDraggingPreviewId.value = null
  removePreviewDragListeners()
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

onBeforeUnmount(() => {
  removePreviewDragListeners()
})
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
        class="reasoning-bubble-surface w-full min-w-0 max-w-[90%] rounded-lg text-xs leading-relaxed relative transition-[max-height] duration-300 ease-in-out"
        :class="isReasoningExpanded(message.id) ? 'max-h-[80vh] overflow-hidden' : 'max-h-[100px] overflow-hidden cursor-pointer'"
        @click="expandReasoning(message.id, $event)"
      >
        <div
          class="pr-8 py-2.5 pl-3 whitespace-pre-wrap break-words transition-[max-height] duration-300 ease-in-out"
          :class="isReasoningExpanded(message.id) ? 'max-h-[80vh] overflow-y-auto' : 'max-h-[100px] overflow-hidden'"
        >
          {{ message.content }}
        </div>
        <button
          type="button"
          class="reasoning-toggle-icon absolute top-2 right-2 z-10 w-6 h-6 flex items-center justify-center rounded hover:bg-white/10 transition-transform duration-200"
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
        class="reasoning-bubble-surface w-full min-w-0 max-w-[90%] rounded-lg text-xs leading-relaxed relative transition-[max-height] duration-300 ease-in-out"
        :class="isReasoningExpanded(message.id) ? 'max-h-[80vh] overflow-hidden' : 'max-h-[100px] overflow-hidden cursor-pointer'"
        @click="expandReasoning(message.id, $event)"
      >
        <div
          class="pr-8 py-2.5 pl-3 whitespace-pre-wrap break-words transition-[max-height] duration-300 ease-in-out"
          :class="isReasoningExpanded(message.id) ? 'max-h-[80vh] overflow-y-auto' : 'max-h-[100px] overflow-hidden'"
        >
          {{ getPersistedReasoningForAssistant(message) }}
        </div>
        <button
          type="button"
          class="reasoning-toggle-icon absolute top-2 right-2 z-10 w-6 h-6 flex items-center justify-center rounded hover:bg-white/10 transition-transform duration-200"
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
          v-if="(message.content ?? '').trim()"
          class="prose prose-invert prose-sm max-w-none"
          v-html="renderMarkdown(message.content ?? '')"
        ></div>
        <div v-if="getTextAttachments(message).length" class="mt-3 flex flex-wrap gap-2">
          <button
            v-for="attachment in getTextAttachments(message)"
            :key="attachment.id"
            type="button"
            class="group relative flex max-w-[220px] items-start gap-2 rounded-xl border border-white/10 bg-black/20 px-3 py-2 text-left"
            @click="toggleTextAttachment(attachment)"
          >
            <span class="absolute right-2 top-1.5 rounded bg-white/10 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-gray-300">{{ getAttachmentExt(attachment) }}</span>
            <span class="truncate pr-10 text-xs text-gray-100">{{ getAttachmentLabel(attachment) }}</span>
          </button>
        </div>
        <div
          v-if="expandedTextAttachmentId && getTextAttachments(message).some((attachment) => attachment.id === expandedTextAttachmentId)"
          class="mt-3 h-48 overflow-auto rounded-xl border border-white/10 bg-black/25 p-3 text-xs leading-relaxed text-gray-200"
        >
          <div v-if="loadingTextAttachmentIds[expandedTextAttachmentId]">读取中...</div>
          <div v-else-if="textAttachmentError[expandedTextAttachmentId]" class="text-amber-200">
            {{ textAttachmentError[expandedTextAttachmentId] }}
          </div>
          <pre v-else class="whitespace-pre-wrap break-words">{{ textAttachmentContent[expandedTextAttachmentId] }}</pre>
        </div>
        <div v-if="getImageAttachments(message).length" class="mt-3 grid grid-cols-2 gap-2">
          <button
            v-for="attachment in getImageAttachments(message)"
            :key="attachment.id"
            type="button"
            class="block overflow-hidden rounded-lg border border-white/10 bg-black/20"
            @click="openImagePreview(buildAttachmentUrl(attachment), getAttachmentLabel(attachment))"
          >
            <img
              :src="buildAttachmentUrl(attachment)"
              :alt="getAttachmentLabel(attachment)"
              class="h-24 w-full object-cover"
              loading="lazy"
              draggable="false"
            />
          </button>
        </div>
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
      class="reasoning-bubble-surface w-full min-w-0 max-w-[90%] rounded-lg text-xs leading-relaxed relative transition-[max-height] duration-300 ease-in-out"
      :class="isReasoningExpanded(STREAMING_REASONING_ID) ? 'max-h-[80vh] overflow-hidden' : 'max-h-[100px] overflow-hidden cursor-pointer'"
      @click="expandReasoning(STREAMING_REASONING_ID, $event)"
    >
      <div
        class="pr-8 py-2.5 pl-3 whitespace-pre-wrap break-words transition-[max-height] duration-300 ease-in-out"
        :class="isReasoningExpanded(STREAMING_REASONING_ID) ? 'max-h-[80vh] overflow-y-auto' : 'max-h-[100px] overflow-hidden'"
      >
        {{ (streamingReasoning ?? '').trim() }}
      </div>
      <button
        type="button"
        class="reasoning-toggle-icon absolute top-2 right-2 z-10 w-6 h-6 flex items-center justify-center rounded hover:bg-white/10 transition-transform duration-200"
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

  <Teleport to="body">
    <div class="image-preview-layer">
      <TransitionGroup name="image-preview-fade">
        <div
          v-for="preview in imagePreviews"
          :key="preview.id"
          class="image-preview-modal"
          :class="preview.isDragging ? 'cursor-grabbing' : 'cursor-grab'"
          :style="getPreviewDialogStyle(preview)"
          @wheel.prevent="(event) => handlePreviewWheel(preview.id, event)"
          @mousedown="(event) => startPreviewDrag(preview.id, event)"
        >
          <button
            type="button"
            class="image-preview-close"
            aria-label="关闭图片预览"
            @click.stop="closeImagePreview(preview.id)"
            @mousedown.stop
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M18 6 6 18" />
              <path d="m6 6 12 12" />
            </svg>
          </button>
          <img :src="preview.src" :alt="preview.alt" class="image-preview-img" draggable="false" />
        </div>
      </TransitionGroup>
    </div>
  </Teleport>
  </div>
</template>

<style scoped>
.image-preview-layer {
  position: fixed;
  inset: 0;
  pointer-events: none;
  z-index: 1450;
}

.image-preview-modal {
  position: fixed;
  left: 50%;
  top: 50%;
  pointer-events: auto;
  border: 1px solid rgba(255, 255, 255, 0.16);
  border-radius: 12px;
  background: rgba(15, 15, 18, 0.75);
  box-shadow: 0 18px 56px rgba(0, 0, 0, 0.45);
  padding: 12px;
  transform-origin: center center;
  user-select: none;
}

.image-preview-close {
  position: absolute;
  top: 8px;
  right: 8px;
  width: 28px;
  height: 28px;
  border-radius: 9999px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.55);
  color: rgba(255, 255, 255, 0.95);
  border: 1px solid rgba(255, 255, 255, 0.22);
}

.image-preview-img {
  display: block;
  height: 50vh;
  width: auto;
  max-width: min(85vw, 1200px);
  object-fit: contain;
  border-radius: 8px;
  pointer-events: none;
}

.image-preview-fade-enter-active,
.image-preview-fade-leave-active {
  transition: opacity 0.18s ease;
}

.image-preview-fade-enter-from,
.image-preview-fade-leave-to {
  opacity: 0;
}
</style>
