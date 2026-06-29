<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { usePreferHoverChrome } from '../../composables/usePreferHoverChrome'
import { renderChatMarkdown } from '../../utils/markdownIt'
import type { AssistantMessage } from '../../composables/useAssistant'
import type { AssistantAttachment } from '../../types/models'
import ConfirmPopover from '../ConfirmPopover.vue'
import AnimatedClipHeight from './AnimatedClipHeight.vue'
import ReasoningBubble from './ReasoningBubble.vue'

const STREAMING_REASONING_ID = '_streaming_pending'

const { preferHoverChrome } = usePreferHoverChrome()

const props = withDefaults(defineProps<{
  messages: AssistantMessage[]
  isGenerating: boolean
  reasoningBlocks?: Array<{ messageId: string; content: string }>
  streamingContent?: string
  streamingReasoning?: string
  /** 是否仍处于思考流式阶段（首条正文 delta 前为 true；工具后轮次会再次为 true） */
  reasoningStreamPhaseActive: boolean
  /** 当前思考段流式已用秒数（一位小数），供 overlay ReasoningBubble duration */
  reasoningElapsedSec?: number | null
  showMessageActions?: boolean
  attachmentScope?: 'chat' | 'workspace'
  chatId?: string | null
}>(), {
  showMessageActions: true,
  attachmentScope: 'chat',
  reasoningElapsedSec: null,
})

const emit = defineEmits<{
  'edit-message': [m: AssistantMessage]
  'delete-message': [m: AssistantMessage]
  'rewrite-message': [m: AssistantMessage]
}>()

function renderMarkdown(text: string) {
  return renderChatMarkdown(text ?? '')
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
let activePreviewPointerId: number | null = null
let previewWindowIdSeed = 0
let previewWindowZSeed = 1300

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
  window.removeEventListener('pointermove', onPreviewDragMove)
  window.removeEventListener('pointerup', stopPreviewDrag)
  window.removeEventListener('pointercancel', stopPreviewDrag)
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
    activePreviewPointerId = null
    removePreviewDragListeners()
  }
  imagePreviews.value = imagePreviews.value.filter((item) => item.id !== id)
}

function closeTopImagePreviewFromEscape(event: KeyboardEvent) {
  if (event.key !== 'Escape' || imagePreviews.value.length === 0) return
  event.preventDefault()
  const top = [...imagePreviews.value].sort((a, b) => b.zIndex - a.zIndex)[0]
  if (top) closeImagePreview(top.id)
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

function startPreviewDrag(id: number, event: PointerEvent) {
  if (event.button !== 0) return
  const preview = getPreviewById(id)
  if (!preview) return
  event.preventDefault()
  activeDraggingPreviewId.value = id
  activePreviewPointerId = event.pointerId
  preview.isDragging = true
  preview.dragStart = { x: event.clientX, y: event.clientY }
  preview.positionAtDragStart = { ...preview.position }
  bringPreviewToFront(id)
  window.addEventListener('pointermove', onPreviewDragMove)
  window.addEventListener('pointerup', stopPreviewDrag)
  window.addEventListener('pointercancel', stopPreviewDrag)
}

function onPreviewDragMove(event: PointerEvent) {
  if (activeDraggingPreviewId.value == null || activePreviewPointerId !== event.pointerId) return
  const preview = getPreviewById(activeDraggingPreviewId.value)
  if (!preview || !preview.isDragging) return
  event.preventDefault()
  const offsetX = event.clientX - preview.dragStart.x
  const offsetY = event.clientY - preview.dragStart.y
  preview.position = {
    x: preview.positionAtDragStart.x + offsetX,
    y: preview.positionAtDragStart.y + offsetY,
  }
}

function stopPreviewDrag(event?: PointerEvent) {
  if (event != null && activePreviewPointerId !== event.pointerId) return
  if (activeDraggingPreviewId.value != null) {
    const preview = getPreviewById(activeDraggingPreviewId.value)
    if (preview) preview.isDragging = false
  }
  activeDraggingPreviewId.value = null
  activePreviewPointerId = null
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
    ? 'bg-[var(--color-success-bg)] text-[var(--color-success-text)] border border-[color-mix(in_srgb,var(--color-success)_30%,transparent)]'
    : 'bg-[var(--color-warning-bg)] text-[var(--color-warning-text)] border border-[color-mix(in_srgb,var(--color-warning)_30%,transparent)]'
}

function getToolDetailContent(message: AssistantMessage): string {
  const raw = message.content ?? ''
  if (!raw.trim()) return ''
  const parsed = parseToolContent(raw)
  return parsed ? JSON.stringify(parsed, null, 2) : raw
}

const showStreamingOverlay = () =>
  props.isGenerating &&
  ((props.streamingReasoning ?? '').trim() !== '' ||
    (props.streamingContent ?? '').trim() !== '' ||
    props.reasoningStreamPhaseActive)

onBeforeUnmount(() => {
  removePreviewDragListeners()
  window.removeEventListener('keydown', closeTopImagePreviewFromEscape)
})

onMounted(() => {
  window.addEventListener('keydown', closeTopImagePreviewFromEscape)
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
        class="flex w-full min-w-0 max-w-[90%] flex-col gap-1 self-start"
        data-chat-bubble-column
      >
        <ReasoningBubble
          class="mb-2"
          :content="message.content"
          :is-streaming="false"
          :duration-sec="typeof message.reasoningDurationSec === 'number' ? message.reasoningDurationSec : null"
          :expanded="isReasoningExpanded(message.id)"
          @update:expanded="(v) => (expandedReasoningMessageId = v ? message.id : null)"
        />
      </div>
    </template>

    <template v-else-if="message.role === 'tool'">
      <div
        class="surface-muted min-w-0 max-w-[90%] px-4 py-2.5 text-sm leading-relaxed shadow-sm transition-colors text-secondary rounded-lg text-xs"
      >
        <div class="flex items-start justify-between gap-3 mb-2">
          <div class="min-w-0">
            <div class="text-[10px] uppercase tracking-wider text-warning">工具步骤</div>
            <div class="text-sm text-primary break-words">{{ getToolStepTitle(message) }}</div>
          </div>
          <span class="shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold" :class="getToolStatusClass(message)">
            {{ getToolStatusLabel(message) }}
          </span>
        </div>
        <div v-if="getToolMessage(message)" class="text-xs text-secondary whitespace-pre-wrap break-words">
          {{ getToolMessage(message) }}
        </div>
        <div v-if="getToolArgsDigest(message)" class="mt-2 text-[10px] text-muted break-all">
          argsDigest: {{ getToolArgsDigest(message) }}
        </div>
        <details class="surface-inset mt-2 overflow-hidden">
          <summary class="cursor-pointer px-3 py-2 text-[11px] text-secondary select-none">查看结果 JSON</summary>
          <pre class="max-w-full overflow-x-auto px-3 pb-3 text-[11px] leading-relaxed text-secondary whitespace-pre-wrap break-all break-words">{{ getToolDetailContent(message) }}</pre>
        </details>
      </div>
    </template>

    <template v-else>
      <div
        class="flex w-full min-w-0 max-w-[90%] flex-col gap-1"
        data-chat-bubble-column
        :class="message.role === 'user' ? 'self-end' : 'self-start'"
      >
      <ReasoningBubble
        v-if="message.role === 'assistant' && getPersistedReasoningForAssistant(message)"
        class="mb-2"
        :content="getPersistedReasoningForAssistant(message) || ''"
        :is-streaming="false"
        :duration-sec="typeof message.reasoningDurationSec === 'number' ? message.reasoningDurationSec : null"
        :expanded="isReasoningExpanded(message.id)"
        @update:expanded="(v) => (expandedReasoningMessageId = v ? message.id : null)"
      />
      <div
        v-if="showMainBubble(message)"
        data-chat-bubble-shell
        class="message-bubble w-fit max-w-full min-w-0 px-4 py-2.5 text-sm leading-relaxed shadow-sm transition-colors"
        :class="message.role === 'user'
          ? 'message-bubble--user text-primary'
          : (message.role === 'system'
            ? 'message-bubble--system rounded-lg text-xs'
            : 'message-bubble--assistant text-primary')"
      >
        <AnimatedClipHeight mode="intrinsic-fullColumn">
          <div class="w-fit max-w-full min-w-0">
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
                class="group surface-inset relative flex max-w-[220px] items-start gap-2 px-3 py-2 text-left"
                @click="toggleTextAttachment(attachment)"
              >
                <span class="absolute right-2 top-1.5 rounded bg-[var(--color-surface-muted)] px-1.5 py-0.5 text-[10px] font-semibold uppercase text-secondary">{{ getAttachmentExt(attachment) }}</span>
                <span class="truncate pr-10 text-xs text-primary">{{ getAttachmentLabel(attachment) }}</span>
              </button>
            </div>
            <div
              v-if="expandedTextAttachmentId && getTextAttachments(message).some((attachment) => attachment.id === expandedTextAttachmentId)"
              class="surface-inset mt-3 h-48 overflow-auto p-3 text-xs leading-relaxed text-secondary"
            >
              <div v-if="loadingTextAttachmentIds[expandedTextAttachmentId]">读取中...</div>
              <div v-else-if="textAttachmentError[expandedTextAttachmentId]" class="text-warning">
                {{ textAttachmentError[expandedTextAttachmentId] }}
              </div>
              <pre v-else class="whitespace-pre-wrap break-words">{{ textAttachmentContent[expandedTextAttachmentId] }}</pre>
            </div>
            <div v-if="getImageAttachments(message).length" class="mt-3 grid grid-cols-2 gap-2">
              <button
                v-for="attachment in getImageAttachments(message)"
                :key="attachment.id"
                type="button"
                class="block overflow-hidden rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-inset)]"
                :aria-label="`预览图片 ${getAttachmentLabel(attachment)}`"
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
          <template #measure>
            <div class="w-fit max-w-full min-w-0">
              <div
                v-if="(message.content ?? '').trim()"
                class="prose prose-invert prose-sm max-w-none"
                v-html="renderMarkdown(message.content ?? '')"
              ></div>
              <div v-if="getTextAttachments(message).length" class="mt-3 flex flex-wrap gap-2">
                <div
                  v-for="attachment in getTextAttachments(message)"
                  :key="attachment.id"
                  class="group surface-inset relative flex max-w-[220px] items-start gap-2 px-3 py-2 text-left"
                >
                  <span class="absolute right-2 top-1.5 rounded bg-[var(--color-surface-muted)] px-1.5 py-0.5 text-[10px] font-semibold uppercase text-secondary">{{ getAttachmentExt(attachment) }}</span>
                  <span class="truncate pr-10 text-xs text-primary">{{ getAttachmentLabel(attachment) }}</span>
                </div>
              </div>
              <div
                v-if="expandedTextAttachmentId && getTextAttachments(message).some((attachment) => attachment.id === expandedTextAttachmentId)"
                class="surface-inset mt-3 h-48 overflow-auto p-3 text-xs leading-relaxed text-secondary"
              >
                <div v-if="loadingTextAttachmentIds[expandedTextAttachmentId]">读取中...</div>
                <div v-else-if="textAttachmentError[expandedTextAttachmentId]" class="text-warning">
                  {{ textAttachmentError[expandedTextAttachmentId] }}
                </div>
                <pre v-else class="whitespace-pre-wrap break-words">{{ textAttachmentContent[expandedTextAttachmentId] }}</pre>
              </div>
              <div v-if="getImageAttachments(message).length" class="mt-3 grid grid-cols-2 gap-2">
                <div
                  v-for="attachment in getImageAttachments(message)"
                  :key="attachment.id"
                  class="block overflow-hidden rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-inset)]"
                >
                  <img
                    :src="buildAttachmentUrl(attachment)"
                    :alt="getAttachmentLabel(attachment)"
                    class="h-24 w-full object-cover"
                    loading="lazy"
                    draggable="false"
                  />
                </div>
              </div>
            </div>
          </template>
        </AnimatedClipHeight>
      </div>
      </div>
    </template>

    <div
      v-if="showMessageActions && message.role !== 'system' && message.role !== 'tool' && message.role !== 'reasoning'"
      class="flex items-center gap-3 px-1 transition-opacity"
      :class="preferHoverChrome ? 'opacity-0 group-hover:opacity-100' : 'opacity-100'"
    >
      <button
        v-if="message.role === 'assistant'"
        class="btn btn-xs btn-ghost"
        :disabled="isGenerating"
        @click="emit('rewrite-message', message)"
      >
        重写
      </button>
      <button
        class="btn btn-xs btn-ghost"
        :disabled="isGenerating"
        @click="emit('edit-message', message)"
      >
        编辑
      </button>
      <button
        class="btn btn-xs btn-danger"
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
    class="flex w-full min-w-0 max-w-[90%] flex-col gap-1 items-start"
    data-chat-bubble-column
  >
    <ReasoningBubble
      v-if="(streamingReasoning ?? '').trim()"
      class="mb-2"
      :content="(streamingReasoning ?? '').trim()"
      :is-streaming="reasoningStreamPhaseActive"
      :duration-sec="
        typeof reasoningElapsedSec === 'number' && Number.isFinite(reasoningElapsedSec)
          ? reasoningElapsedSec
          : null
      "
      :expanded="isReasoningExpanded(STREAMING_REASONING_ID)"
      @update:expanded="(v) => (expandedReasoningMessageId = v ? STREAMING_REASONING_ID : null)"
    />
    <div
      v-if="(streamingContent ?? '') !== ''"
      data-chat-bubble-shell
      class="message-bubble message-bubble--assistant w-fit max-w-full min-w-0 px-4 py-2.5 text-sm leading-relaxed shadow-sm transition-colors text-primary"
    >
      <AnimatedClipHeight mode="intrinsic-fullColumn" :relax-height-dead-zone="true">
        <div class="w-fit max-w-full min-w-0">
          <div
            class="prose prose-invert prose-sm max-w-none"
            v-html="renderMarkdown(streamingContent ?? '')"
          ></div>
        </div>
        <template #measure>
          <div class="w-fit max-w-full min-w-0">
            <div
              class="prose prose-invert prose-sm max-w-none"
              v-html="renderMarkdown(streamingContent ?? '')"
            ></div>
          </div>
        </template>
      </AnimatedClipHeight>
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
          role="dialog"
          aria-modal="false"
          :aria-label="`图片预览：${preview.alt}`"
          :class="preview.isDragging ? 'cursor-grabbing' : 'cursor-grab'"
          :style="getPreviewDialogStyle(preview)"
          @wheel.prevent="(event) => handlePreviewWheel(preview.id, event)"
          @pointerdown="(event) => startPreviewDrag(preview.id, event)"
        >
          <button
            type="button"
            class="image-preview-close"
            aria-label="关闭图片预览"
            @click.stop="closeImagePreview(preview.id)"
            @pointerdown.stop
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
  z-index: var(--z-image-preview);
}

.image-preview-modal {
  position: fixed;
  left: 50%;
  top: 50%;
  pointer-events: auto;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-xl);
  background: var(--color-surface-panel);
  box-shadow: var(--shadow-heavy);
  padding: 12px;
  transform-origin: center center;
  user-select: none;
  touch-action: none;
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
  background: var(--color-overlay-heavy);
  color: var(--color-text);
  border: 1px solid var(--color-border);
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
