<script setup lang="ts">
/**
 * MessageList - 消息列表组件
 *
 * 组件职责：
 * - 显示聊天消息列表，包括用户消息、助手消息和系统消息
 * - 支持消息版本切换（查看不同版本）
 * - 支持消息编辑、删除、重写操作
 * - 支持Markdown渲染
 * - 自动滚动到底部
 * - 为流式输出设置DOM引用
 *
 * 维护提醒：
 * - 2026-04 曾出现 MessageList 在固定滚动阈值处突然重定位的问题。触发点对每个会话是固定且唯一的，长会话往往更早命中。
 * - 根因不是随机竞态，而是“禁用浏览器原生 scroll anchoring + 用 ref/watch 间接驱动虚拟窗口 + 高度测量阶段手动改 scrollTop”叠加后，把一次窗口切换拆成了多轮更新。
 * - 这里依赖浏览器默认的 overflow-anchor 行为，以及直接 computed 的 windowStart/windowEnd，来保证高度写回与窗口切换尽量原子完成；不要轻易恢复手动锚点补偿或 window-clamp 一类实验逻辑。
 * - 当前选择是不再额外修饰原生滚动条与顶栏的重叠区域，先优先保证虚拟滚动几何稳定；后续若要彻底解决体验问题，建议直接上独立自绘滚动条，而不是再次改 scrollport 几何。
 *
 * Props说明：
 * - messages: 消息列表（来自types/models.ts的ChatMessage[]类型）
 * - isGroup: 是否为群聊
 * - selectedCharacter: 当前选中的角色（来自types/models.ts的CharacterCard类型）
 * - characters: 角色列表（来自types/models.ts的CharacterCard[]类型）
 * - selectedPersona: 当前选中的用户身份（来自types/models.ts的UserPersona类型）
 * - userName: 用户名称
 * - userAvatarUrl: 用户头像URL
 * - characterAvatarUrl: 角色头像URL
 * - isGenerating: 是否正在生成
 * - getDisplayContent: 获取消息显示内容的函数（来自composables/useMessageVersions.ts）
 * - hasMultipleVersions: 检查是否有多个版本的函数（来自composables/useMessageVersions.ts）
 * - getCurrentVersionIndex: 获取当前版本索引的函数（来自composables/useMessageVersions.ts）
 * - getVersionCount: 获取版本总数的函数（来自composables/useMessageVersions.ts）
 *
 * Emits说明：
 * - edit-message: 编辑消息
 * - delete-message: 删除消息
 * - rewrite-message: 重写消息
 * - switch-previous-version: 切换到上一个版本
 * - switch-next-version: 切换到下一个版本
 *
 * 使用的Composables：
 * 无（通过props接收函数）
 *
 * 使用的Stores：
 * 无
 *
 * 文件关系：
 *    - 被导入：被views/ChatPage.vue使用
 *    - 导入：导入vue的ref和nextTick、types/models.ts的类型、components/ModernAvatar.vue、utils/markdownIt
 *    - 依赖：依赖vue、markdown-it（经 markdownIt 工具封装）
 *    - 位置：组件层，提供消息列表显示功能
 */
import { ref, nextTick, computed, onBeforeUnmount, onMounted, onBeforeUpdate, onUpdated, watch } from 'vue'
import type {
  ChatContentRegexRule,
  ChatMessage,
  CharacterCard,
  ForkSiblingSummary,
  UserPersona,
} from '../../types/models'
import { useSettingsStore } from '../../stores'
import ModernAvatar from '../ModernAvatar.vue'
import ConfirmPopover from '../ConfirmPopover.vue'
import SelectDropdownSurface from '../SelectDropdownSurface.vue'
import ReasoningBubble from './ReasoningBubble.vue'
import AnimatedClipHeight from './AnimatedClipHeight.vue'
import { renderChatMarkdown, renderChatMarkdownStreaming } from '../../utils/markdownIt'
import { applyContentRegexDisplay } from '../../utils/contentRegex'
import { usePreferHoverChrome } from '../../composables/usePreferHoverChrome'
import { Settings, ChevronLeft, ChevronRight, ChevronDown, X } from 'lucide-vue-next'

const settingsStore = useSettingsStore()
const { preferHoverChrome } = usePreferHoverChrome()
/** 仅作用于消息气泡内文字的字号（来自全局设置） */
const messageContentFontSizeStyle = computed(() => {
  const px = settingsStore.settings?.messageFontSize
  return px != null ? { fontSize: `${px}px` } : {}
})

const props = defineProps<{
  chatId: string
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
  /** 群聊插话流式中（isGenerating 可能为 false，ResizeObserver 跟底仍应生效） */
  isInterjecting?: boolean
  /** 当前展示思考链的消息 ID（仅前端临时，刷新后消失） */
  reasoningMessageId?: string | null
  /** 思考链内容（当前正在流式接收的一条） */
  reasoningContent?: string
  /** 是否仍处于「思考流式」阶段（首条正文 delta 前为 true；与 chatReasoningStreamActive 对齐） */
  reasoningStreamActive: boolean
  /** 多轮思考链块：每项为 { messageId, content }，仅前端临时展示 */
  reasoningBlocks?: Array<{ messageId: string; content: string }>
  /** 思考阶段结束时前端估算的秒数（1 位小数），直至消息持久化带 reasoningDurationSec */
  reasoningDurationSecOverride?: number | null
  // 版本相关
  getDisplayContent: (m: ChatMessage) => string
  /** 获取当前显示版本对应的思考内容（多版本时随版本切换） */
  getDisplayReasoning?: (m: ChatMessage) => string | undefined
  hasMultipleVersions: (m: ChatMessage) => boolean
  getCurrentVersionIndex: (m: ChatMessage) => number
  getVersionCount: (m: ChatMessage) => number
  /** 固定顶栏高度（px），用于滚动区上方占位，使滚动条从顶栏下缘起算 */
  headerInsetPx: number
  /** 底部叠层额外占位（px）；只增加真实可滚动高度，不参与消息虚拟高度计算 */
  bottomScrollExtraPx?: number
  /** 侧栏是否折叠；用于侧栏宽度动画结束后合并重排补偿，降低抖动 */
  sidebarCollapsed?: boolean
  /** 本次发送的用户消息 id：播放一次性自下而上入场动画（纯 AI 模式为 system 角色） */
  entrancingUserMessageId?: string | null
  /** 重写/保存并发送等插入的助手占位行 id：弱化整行挂载跳变 */
  entrancingAssistantMessageId?: string | null
  /** 当前会话生效的正则规则（仅用于前端渲染替换，不修改持久化 content） */
  contentRegexRules?: ChatContentRegexRule[] | null
  /** 从本会话各消息拉出的子分叉（messageId -> 摘要） */
  outgoingForksByMessageId?: Record<string, { count: number; chats: ForkSiblingSummary[] }>
  /** 正在从此消息创建分支会话 */
  isForking?: boolean
}>()

function getChatImageUrl(imageId: string): string {
  return `/api/chats/${encodeURIComponent(props.chatId)}/images/${encodeURIComponent(imageId)}`
}

const emit = defineEmits<{
  'edit-message': [m: ChatMessage]
  'delete-message': [m: ChatMessage]
  'read-aloud-message': [m: ChatMessage]
  'rewrite-message': [m: ChatMessage]
  'switch-previous-version': [m: ChatMessage]
  'switch-next-version': [m: ChatMessage]
  'fork-message': [m: ChatMessage]
  'select-fork-child': [chatId: string]
}>()

function canForkMessage(m: ChatMessage): boolean {
  return !m.id.startsWith('local_') && m.role !== 'tool'
}

function getOutgoingFork(m: ChatMessage) {
  return props.outgoingForksByMessageId?.[m.id]
}

const forkListOpen = ref(false)
const forkListMessageId = ref<string | null>(null)
const forkListAnchorById = new Map<string, HTMLElement>()

function setForkListAnchor(messageId: string, el: unknown) {
  if (el instanceof HTMLElement) forkListAnchorById.set(messageId, el)
  else forkListAnchorById.delete(messageId)
}

const forkListAnchorRef = computed(() => {
  const id = forkListMessageId.value
  return id ? forkListAnchorById.get(id) ?? null : null
})

function toggleForkList(messageId: string) {
  if (forkListMessageId.value === messageId && forkListOpen.value) {
    forkListOpen.value = false
    forkListMessageId.value = null
  } else {
    forkListMessageId.value = messageId
    forkListOpen.value = true
  }
}

function onSelectForkChild(chatId: string) {
  forkListOpen.value = false
  forkListMessageId.value = null
  emit('select-fork-child', chatId)
}

// 滚动容器引用
const scrollRef = ref<HTMLElement | null>(null)
const contentRef = ref<HTMLElement | null>(null)
const rowEls = new Map<string, HTMLElement>()
let prevRowRects = new Map<string, DOMRect>()
const scrollTop = ref(0)
const viewportHeight = ref(0)
const realDistanceFromBottom = ref(0)
const wasNearBottomBeforeMutation = ref(true)
const measuredHeights = ref<Record<string, number>>({})
const MESSAGE_ROW_GAP = 32
const DEFAULT_ROW_HEIGHT = 220 + MESSAGE_ROW_GAP
/** 保持较大的 overscan，让未测量消息在接近视口前就已挂载并完成测量，避免长会话中累计估高误差突然命中视口。 */
const BUFFER_ITEMS = 26
const SCROLL_BOTTOM_SHOW_THRESHOLD = 200
const SCROLL_BOTTOM_NEAR_THRESHOLD = 24
const AUTO_FOLLOW_DISTANCE_THRESHOLD = 300
const SCROLL_TO_BOTTOM_SETTLE_MS = 140
const SCROLL_BOTTOM_BASE_PADDING_PX = 16
/** 用户发送消息时的动画滚动时长（与气泡入场关键帧时长对齐，产生「视口下移带入气泡 + 落地上浮」的一体化过渡） */
const USER_SEND_SCROLL_ANIM_MS = 420
/** 动画滚动的最大补偿距离；超过则直接瞬移兜底，避免从顶部发送时出现长时间滚动 */
const USER_SEND_SCROLL_MAX_DISTANCE = 2400
/** 用户曾用滚轮向上或拖动滚动条解除跟底；回到贴底带内或强制滚底时清除 */
const userDismissedAutoFollow = ref(false)
/** 正在播放「用户发送动画滚动」；期间 ResizeObserver 不做 instant 贴底，避免抢占平滑过渡 */
const userSendScrollActive = ref(false)
let userSendScrollRaf: number | null = null
let contentResizeObserver: ResizeObserver | null = null
let pendingBottomSnapToken = 0
let pendingBottomSnapTimer: ReturnType<typeof setTimeout> | null = null
let pendingBottomSnapScrollEndCleanup: (() => void) | null = null
let pendingBottomSnapRefresh: (() => void) | null = null

/** 进入会话首屏抑制 FLIP，避免估高收敛阶段对全部可见行做几何读取 */
const FLIP_SUPPRESS_MS = 400
let flipSuppressedUntil = 0
let lastFlipWindowStart = -1
let lastFlipWindowEnd = -1
let lastFlipSidebarCollapsed: boolean | undefined = undefined
let flipSnapshotPending = false

const pendingMeasureIds = new Set<string>()
let pendingHeightFlushRaf: number | null = null
let pendingAlignAfterHeightFlush = false
/** scrollToBottomAfterLayout 请求强制贴底，不受上一会话 wasNearBottom 影响 */
let pendingAlignForce = false

const MARKDOWN_HTML_CACHE_LIMIT = 400
const markdownHtmlCache = new Map<string, string>()

function rememberMarkdownHtml(key: string, html: string) {
  if (markdownHtmlCache.has(key)) markdownHtmlCache.delete(key)
  markdownHtmlCache.set(key, html)
  while (markdownHtmlCache.size > MARKDOWN_HTML_CACHE_LIMIT) {
    const oldestKey = markdownHtmlCache.keys().next().value
    if (typeof oldestKey !== 'string') break
    markdownHtmlCache.delete(oldestKey)
  }
}

// 删除确认状态
const deleteConfirm = ref<{
  message: ChatMessage
  target: HTMLElement
} | null>(null)

// 思考气泡：仅点击气泡体展开，仅点击图标收起
const expandedReasoningMessageId = ref<string | null>(null)
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

function closeImagePreview(id: number) {
  const target = getPreviewById(id)
  if (target?.isDragging) {
    target.isDragging = false
    activeDraggingPreviewId.value = null
    activePreviewPointerId = null
    removePreviewDragListeners()
  }
  imagePreviews.value = imagePreviews.value.filter((preview) => preview.id !== id)
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

function normalizeElement(el: unknown): HTMLElement | null {
  if (!el) return null
  if (el instanceof HTMLElement) return el
  const maybe = (el as { $el?: unknown }).$el
  return maybe instanceof HTMLElement ? maybe : null
}

/** 每条消息气泡的内容根元素（含 .stream-markdown 子节点），供流式末尾包裹使用 */
const contentEls = new Map<string, HTMLElement>()

function setContentRef(messageId: string, el: unknown) {
  const normalized = normalizeElement(el)
  if (normalized) {
    contentEls.set(messageId, normalized)
  } else {
    contentEls.delete(messageId)
    tailQueues.delete(messageId)
  }
}

function openAvatarPreview(m: ChatMessage) {
  const avatarUrl = getMessageAvatar(m)
  if (!avatarUrl) return
  openImagePreview(avatarUrl, `${getMessageLabel(m)}-avatar`)
}

onBeforeUnmount(() => {
  removePreviewDragListeners()
  window.removeEventListener('keydown', closeTopImagePreviewFromEscape)
  window.removeEventListener('resize', updateViewport)
  if (tailRafId != null) {
    cancelAnimationFrame(tailRafId)
    tailRafId = null
  }
  tailQueues.clear()
})

/** 获取某条助手消息对应的思考链内容：优先版本绑定的思考，再当前流式内容，否则从 reasoningBlocks 按 messageId 取，最后回退到磁盘快照 */
function getReasoningForMessage(m: ChatMessage): string | undefined {
  if (m.role !== 'assistant') return undefined
  if (props.getDisplayReasoning) {
    const versioned = props.getDisplayReasoning(m)
    if (versioned) return versioned
  }
  if (m.id === props.reasoningMessageId && props.reasoningContent) {
    return props.reasoningContent
  }
  const blocks = props.reasoningBlocks
  if (Array.isArray(blocks)) {
    const block = blocks.find((b) => b.messageId === m.id)
    const content = block?.content?.trim()
    if (content) return content
  }
  const persisted = typeof m.reasoningContent === 'string' ? m.reasoningContent.trim() : ''
  return persisted || undefined
}

/** 思考内容尚未到达时也挂载 ReasoningBubble，避免首包 reasoning 时整块突然出现 */
function shouldShowReasoningPlaceholder(m: ChatMessage): boolean {
  if (m.role !== 'assistant') return false
  const rid = props.reasoningMessageId
  if (rid == null || m.id !== rid) return false
  return !!(props.isGenerating || props.isInterjecting || props.reasoningStreamActive)
}

function isUserSendEntering(m: ChatMessage): boolean {
  const id = props.entrancingUserMessageId
  if (id == null || m.id !== id) return false
  return m.role === 'user' || m.role === 'system'
}

function isAssistantRowEntering(m: ChatMessage): boolean {
  const id = props.entrancingAssistantMessageId
  if (id == null || m.id !== id) return false
  return m.role === 'assistant'
}

/** 当前消息是否正在接收思考流式内容（控制 ReasoningBubble 的 streaming 模式） */
function isMessageReasoningStreaming(m: ChatMessage): boolean {
  if (!props.isGenerating && !props.isInterjecting) return false
  if (m.id !== props.reasoningMessageId) return false
  return props.reasoningStreamActive
}

/** 当前消息思考耗时（秒）；持久化字段优先，否则本条流式结束前可用 reasoningDurationSecOverride */
function getReasoningDurationForMessage(m: ChatMessage): number | null {
  const persisted = typeof m.reasoningDurationSec === 'number' ? m.reasoningDurationSec : null
  if (persisted != null && Number.isFinite(persisted)) return persisted
  if (
    m.id === props.reasoningMessageId &&
    typeof props.reasoningDurationSecOverride === 'number' &&
    Number.isFinite(props.reasoningDurationSecOverride)
  ) {
    return props.reasoningDurationSecOverride
  }
  return null
}

/**
 * 渲染 Markdown；当前正在流式输出的那条助手消息走「补虚闭合」版本，
 * 其它消息用稳定版本，避免为非流式消息付出不必要的补齐成本 / 潜在误判。
 */
function getDisplayText(m: ChatMessage): string {
  const raw = props.getDisplayContent(m)
  if (!raw) return raw
  return applyContentRegexDisplay(raw, props.contentRegexRules)
}

function markdownCacheKey(m: ChatMessage): string {
  const text = getDisplayText(m)
  const versionIdx = props.getCurrentVersionIndex(m)
  const rulesKey = (props.contentRegexRules ?? [])
    .map((r) => `${r.id}:${r.enabled}:${r.pattern}`)
    .join('|')
  return `${m.id}|v${versionIdx}|${text.length}|${text.slice(0, 80)}|${rulesKey}`
}

function renderMarkdown(m: ChatMessage) {
  const text = getDisplayText(m)
  const isStreaming =
    (props.isGenerating || props.isInterjecting) && m.id === props.reasoningMessageId
  if (isStreaming) return renderChatMarkdownStreaming(text)
  const key = markdownCacheKey(m)
  const cached = markdownHtmlCache.get(key)
  if (cached != null) {
    rememberMarkdownHtml(key, cached)
    return cached
  }
  const html = renderChatMarkdown(text)
  rememberMarkdownHtml(key, html)
  return html
}

function messageRowMemoDeps(m: ChatMessage): unknown[] {
  const streaming =
    (props.isGenerating || props.isInterjecting) && m.id === props.reasoningMessageId
  return [
    m.id,
    getDisplayText(m),
    props.getCurrentVersionIndex(m),
    streaming,
    props.reasoningMessageId,
    isReasoningExpanded(m.id),
    m.images?.length ?? 0,
  ]
}

function shouldRenderMainBubble(m: ChatMessage): boolean {
  const text = getDisplayText(m).trim()
  if (text) return true
  return Array.isArray(m.images) && m.images.length > 0
}

/**
 * 流式尾部渐变：队列记录最近到达字符的时间戳，双上限出队后按位置上色。
 *
 *   - 长度上限：≤ TAIL_MAX_LEN（16）
 *   - 时间上限：队头最早字符年龄 ≤ TAIL_MAX_AGE_MS（240ms）
 *
 * 快吐词稳定保持 16 字渐变；慢/暂停时尾部被时间上限压缩到最新 1~2 字。
 * opacity 从「最旧（靠左）1.0」到「最新（靠右）TAIL_OPACITY_MIN」线性插值。
 *
 * 仅影响内联叶子文本节点；遇到 pre/code/.katex-display/.katex 等原子块即止。
 */
const TAIL_MAX_LEN = 16
const TAIL_MAX_AGE_MS = 240
const TAIL_OPACITY_MIN = 0.15
const TAIL_OPACITY_MAX = 1.0
const TAIL_ATOMIC_SELECTOR = 'pre, code, st-math-island, .katex, .katex-display'

/** prevDecorLen：与 collectInlineTextNodes 一致的可装饰内联字符数（不含 pre/code 等原子块内文本） */
type TailQueue = { chars: number[]; prevDecorLen: number }
const tailQueues = new Map<string, TailQueue>()
let tailRafId: number | null = null

function resetTailForMessage(id: string) {
  tailQueues.delete(id)
  const host = contentEls.get(id)
  if (!host) return
  const el = host.querySelector('.stream-markdown') as HTMLElement | null
  if (el) restoreTailSpans(el)
}

function restoreTailSpans(root: HTMLElement) {
  const spans = root.querySelectorAll<HTMLSpanElement>('span.stream-tail-char')
  if (spans.length === 0) return
  spans.forEach((span) => {
    const parent = span.parentNode
    if (!parent) return
    const text = span.textContent ?? ''
    const next = document.createTextNode(text)
    parent.replaceChild(next, span)
  })
  // 合并兄弟文本节点，避免渐进累积碎片
  root.normalize()
}

/**
 * 从末尾向前采集 `tailLen` 个字符所在的文本节点片段，每字单独包裹成
 * <span class="stream-tail-char" style="opacity:...">；遇到原子块即止。
 */
function decorateStreamTail(root: HTMLElement, tailLen: number) {
  restoreTailSpans(root)
  if (tailLen <= 0) return

  const textNodes = collectInlineTextNodes(root)
  if (textNodes.length === 0) return

  // 从末尾向前切出恰好 tailLen 个字符的 Text 节点段
  type TailSegment = { node: Text; start: number; end: number }
  const segments: TailSegment[] = []
  let remaining = tailLen
  for (let i = textNodes.length - 1; i >= 0 && remaining > 0; i--) {
    const tn = textNodes[i]!
    const len = tn.data.length
    if (len === 0) continue
    if (len <= remaining) {
      segments.push({ node: tn, start: 0, end: len })
      remaining -= len
    } else {
      segments.push({ node: tn, start: len - remaining, end: len })
      remaining = 0
    }
  }
  if (segments.length === 0) return

  // 按从旧到新（DOM 正向）排序，用于计算 opacity
  segments.reverse()

  // 总尾长（可能不足 tailLen，若可用文本不够）
  let total = 0
  for (const s of segments) total += s.end - s.start
  if (total === 0) return

  const span = TAIL_OPACITY_MAX - TAIL_OPACITY_MIN
  let idx = 0
  for (const seg of segments) {
    const { node, start, end } = seg
    // 先把目标片段切分为独立 Text 节点（保留前后部分）
    let target: Text = node
    if (start > 0) target = target.splitText(start)
    // 现在 target.data.length === end - start
    if (target.data.length > (end - start)) {
      target.splitText(end - start)
    }

    const parent = target.parentNode
    if (!parent) {
      idx += end - start
      continue
    }

    // 逐字符切分并包裹
    const pieces = Array.from(target.data)
    const frag = document.createDocumentFragment()
    for (let j = 0; j < pieces.length; j++) {
      const ch = pieces[j]!
      const wrap = document.createElement('span')
      wrap.className = 'stream-tail-char'
      const ratio = total <= 1 ? 0 : idx / (total - 1)
      // idx=0 -> 最旧 -> TAIL_OPACITY_MAX；idx=total-1 -> 最新 -> TAIL_OPACITY_MIN
      const opacity = TAIL_OPACITY_MAX - span * ratio
      wrap.style.opacity = opacity.toFixed(3)
      wrap.textContent = ch
      frag.appendChild(wrap)
      idx += 1
    }
    parent.replaceChild(frag, target)
  }
}

/**
 * 采集流式容器下可参与尾部渐变的内联文本节点：跳过 pre/code/katex 等原子块及其子树。
 */
function collectInlineTextNodes(root: HTMLElement): Text[] {
  const out: Text[] = []
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT, {
    acceptNode(node) {
      if (node.nodeType === Node.ELEMENT_NODE) {
        if ((node as Element).matches(TAIL_ATOMIC_SELECTOR)) return NodeFilter.FILTER_REJECT
        return NodeFilter.FILTER_SKIP
      }
      return NodeFilter.FILTER_ACCEPT
    },
  })
  let n: Node | null
  while ((n = walker.nextNode())) {
    out.push(n as Text)
  }
  return out
}

function getDecoratableTextLength(root: HTMLElement): number {
  let n = 0
  for (const tn of collectInlineTextNodes(root)) n += tn.data.length
  return n
}

function advanceTailQueueFromTime(queue: TailQueue): boolean {
  const now = performance.now()
  let changed = false
  while (queue.chars.length > 0 && now - queue.chars[0]! > TAIL_MAX_AGE_MS) {
    queue.chars.shift()
    changed = true
  }
  return changed
}

function enforceLengthCap(queue: TailQueue) {
  while (queue.chars.length > TAIL_MAX_LEN) {
    queue.chars.shift()
  }
}

/** 对当前正在流式的消息刷新尾部装饰（不触发 Markdown 重解析，仅 DOM 操作）。 */
function applyTailForCurrentStreaming() {
  const id = props.reasoningMessageId
  if (!id) return
  if (!props.isGenerating && !props.isInterjecting) return
  const queue = tailQueues.get(id)
  if (!queue) return
  const host = contentEls.get(id)
  if (!host) return
  const el = host.querySelector('.stream-markdown') as HTMLElement | null
  if (!el) return
  decorateStreamTail(el, queue.chars.length)
}

function scheduleTailRaf() {
  if (tailRafId != null) return
  tailRafId = requestAnimationFrame(() => {
    tailRafId = null
    const id = props.reasoningMessageId
    if (!id) return
    const active = props.isGenerating || props.isInterjecting
    if (!active) return
    const queue = tailQueues.get(id)
    if (!queue) return
    const before = queue.chars.length
    advanceTailQueueFromTime(queue)
    if (queue.chars.length !== before) {
      applyTailForCurrentStreaming()
    }
    if (queue.chars.length > 0) scheduleTailRaf()
  })
}

watch(
  () => {
    const id = props.reasoningMessageId
    if (!id) return null
    if (!props.isGenerating && !props.isInterjecting) return null
    const msg = props.messages.find((x) => x.id === id)
    if (!msg || msg.role !== 'assistant') return null
    return { id, content: props.getDisplayContent(msg) }
  },
  (cur, prev) => {
    // 流式结束（cur=null）或换到其它消息：把上一个 id 的尾部渐变还原为纯文本
    if (prev && (!cur || cur.id !== prev.id)) {
      resetTailForMessage(prev.id)
    }
    if (!cur) return
    const host = contentEls.get(cur.id)
    if (!host) return
    const el = host.querySelector('.stream-markdown') as HTMLElement | null
    if (!el) return

    // v-html 已替换完毕，tail span 不存在；队列增量仅统计可装饰内联文本，避免 pre 内流式增长误灌队列。
    const decorLen = getDecoratableTextLength(el)
    let queue = tailQueues.get(cur.id)
    if (!queue) {
      queue = { chars: [], prevDecorLen: decorLen }
      tailQueues.set(cur.id, queue)
    }
    const now = performance.now()
    const delta = decorLen - queue.prevDecorLen
    if (delta > 0) {
      for (let i = 0; i < delta; i++) queue.chars.push(now)
    } else if (delta < 0) {
      // 结构变化使内联长度波动时，从队首保守收缩而不是清零
      const drop = Math.min(queue.chars.length, -delta)
      queue.chars.splice(0, drop)
    }
    queue.prevDecorLen = decorLen
    advanceTailQueueFromTime(queue)
    enforceLengthCap(queue)
    decorateStreamTail(el, queue.chars.length)
    if (queue.chars.length > 0) scheduleTailRaf()
  },
  { flush: 'post' },
)

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

/** 按 ID 从全局设置中的身份列表解析当前头像（更新 persona 后与消息内快照解耦） */
function getUserPersonaFromSettings(id: string | null | undefined): UserPersona | null {
  if (!id) return null
  return settingsStore.settings?.userPersonas?.find(p => p.id === id) ?? null
}

/**
 * 获取消息标签
 *
 * 根据消息角色和内容返回要显示的名称标签。
 * 用户消息显示发送者名称，助手消息显示角色名称，系统消息显示"系统"。
 *
 * @param {ChatMessage} m - 消息对象（来自types/models.ts）
 * @returns {string} 消息标签
 */
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

/**
 * 获取消息头像
 *
 * 根据消息角色和内容返回头像URL。
 * 用户消息：有 senderPersonaId 时优先用设置里该身份的当前头像，否则用消息快照 senderAvatar，再否则当前选中身份头像。
 * 助手消息优先使用角色头像。
 *
 * @param {ChatMessage} m - 消息对象（来自types/models.ts）
 * @returns {string | null} 头像URL，如果未找到则返回null
 */
function getMessageAvatar(m: ChatMessage): string | null {
  if (m.role === 'user') {
    if (m.senderPersonaId) {
      const live = getUserPersonaFromSettings(m.senderPersonaId)
      if (live?.avatar) return `/api/avatars/${live.avatar}`
    }
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

function getMessageAvatarObjectPosition(m: ChatMessage): string {
  if (m.role !== 'assistant') return '50% 50%'
  let char: CharacterCard | null = null
  if (m.characterId) {
    char = getCharacterById(m.characterId)
  } else {
    char = props.selectedCharacter
  }
  if (!char) return '50% 50%'
  const x = typeof char.avatarFocusX === 'number' ? char.avatarFocusX : 50
  const y = typeof char.avatarFocusY === 'number' ? char.avatarFocusY : 50
  return `${x}% ${y}%`
}

/**
 * 确认删除消息
 *
 * 弹出确认对话框，确认后触发删除消息事件。
 *
 * @param {ChatMessage} m - 要删除的消息（来自types/models.ts）
 * @param {Event} event - 点击事件
 */
function confirmDelete(m: ChatMessage, event: Event) {
  deleteConfirm.value = {
    message: m,
    target: event.currentTarget as HTMLElement
  }
}

function handleConfirmDelete() {
  if (deleteConfirm.value) {
    emit('delete-message', deleteConfirm.value.message)
    deleteConfirm.value = null
  }
}

function cancelDelete() {
  deleteConfirm.value = null
}

/**
 * 滚动到底部
 *
 * 滚动消息列表容器到底部，显示最新消息。
 * 使用nextTick确保DOM更新后再滚动。
 */
function getRealDistanceFromBottom(el: HTMLElement): number {
  return Math.max(0, el.scrollHeight - el.clientHeight - el.scrollTop)
}

function syncScrollMetrics(el: HTMLElement) {
  scrollTop.value = el.scrollTop
  viewportHeight.value = el.clientHeight
  realDistanceFromBottom.value = getRealDistanceFromBottom(el)
  wasNearBottomBeforeMutation.value = realDistanceFromBottom.value <= AUTO_FOLLOW_DISTANCE_THRESHOLD
}

function shouldAutoFollowBottom(el: HTMLElement): boolean {
  return getRealDistanceFromBottom(el) <= AUTO_FOLLOW_DISTANCE_THRESHOLD
}

function effectiveCanFollow(el: HTMLElement): boolean {
  if (userDismissedAutoFollow.value) return false
  return wasNearBottomBeforeMutation.value || shouldAutoFollowBottom(el)
}

/** 滚轮事件目标是否处于主列表内的嵌套纵向滚动区（如思考气泡），避免误解除跟底 */
function isWheelTargetInsideNestedScrollable(eventTarget: EventTarget | null, root: HTMLElement): boolean {
  let node: Node | null = eventTarget instanceof Node ? eventTarget : null
  while (node && node !== root) {
    if (node instanceof HTMLElement) {
      const st = window.getComputedStyle(node)
      const oy = st.overflowY
      if ((oy === 'auto' || oy === 'scroll') && node.scrollHeight > node.clientHeight + 1) {
        return true
      }
    }
    node = node.parentNode
  }
  return false
}

function handleListWheel(e: WheelEvent) {
  const root = scrollRef.value
  if (!root || e.currentTarget !== root) return
  cancelPendingBottomSnap()
  if (e.deltaY <= 0) return
  if (isWheelTargetInsideNestedScrollable(e.target, root)) return
  userDismissedAutoFollow.value = true
}

/** 经典滚动条区域（overlay 滚动条时宽度可能为 0，无法检测） */
function handleListPointerDown(e: PointerEvent) {
  const el = scrollRef.value
  if (!el || e.currentTarget !== el) return
  if (e.button !== 0) return
  cancelPendingBottomSnap()
  const barW = el.offsetWidth - el.clientWidth
  if (barW <= 0) return
  const rect = el.getBoundingClientRect()
  if (e.clientX >= rect.right - barW) {
    userDismissedAutoFollow.value = true
  }
}

function alignToBottom(el: HTMLElement, instant: boolean) {
  const previousBehavior = el.style.scrollBehavior
  if (instant) {
    el.style.scrollBehavior = 'auto'
  }
  const target = Math.max(0, el.scrollHeight - el.clientHeight)
  el.scrollTop = target
  syncScrollMetrics(el)
  if (instant) {
    el.style.scrollBehavior = previousBehavior
  }
}

function cancelPendingBottomSnap() {
  pendingBottomSnapToken += 1
  if (pendingBottomSnapTimer) {
    clearTimeout(pendingBottomSnapTimer)
    pendingBottomSnapTimer = null
  }
  if (pendingBottomSnapScrollEndCleanup) {
    pendingBottomSnapScrollEndCleanup()
    pendingBottomSnapScrollEndCleanup = null
  }
  pendingBottomSnapRefresh = null
}

function armBottomSnapAfterSmoothScroll(el: HTMLElement, force: boolean) {
  cancelPendingBottomSnap()
  const token = pendingBottomSnapToken

  const finalize = () => {
    if (token !== pendingBottomSnapToken) return
    cancelPendingBottomSnap()
    const current = scrollRef.value
    if (!current || current !== el) return
    if (!force && !effectiveCanFollow(current)) {
      syncScrollMetrics(current)
      return
    }
    alignToBottom(current, true)
    requestAnimationFrame(() => {
      const latest = scrollRef.value
      if (!latest || latest !== el) return
      if (!force && !effectiveCanFollow(latest)) {
        syncScrollMetrics(latest)
        return
      }
      alignToBottom(latest, true)
    })
  }

  const refresh = () => {
    if (token !== pendingBottomSnapToken) return
    if (pendingBottomSnapTimer) {
      clearTimeout(pendingBottomSnapTimer)
    }
    pendingBottomSnapTimer = setTimeout(() => {
      pendingBottomSnapTimer = null
      finalize()
    }, SCROLL_TO_BOTTOM_SETTLE_MS)
  }

  pendingBottomSnapRefresh = refresh

  if ('onscrollend' in el) {
    const onScrollEnd = () => {
      finalize()
    }
    el.addEventListener('scrollend', onScrollEnd as EventListener, { once: true })
    pendingBottomSnapScrollEndCleanup = () => {
      el.removeEventListener('scrollend', onScrollEnd as EventListener)
    }
  }

  refresh()
}

function buildPrefixHeights(heightMap: Record<string, number>, messages: ChatMessage[]): number[] {
  const out = new Array(messages.length + 1).fill(0)
  for (let i = 0; i < messages.length; i++) {
    const rowHeight = heightMap[messages[i]!.id] ?? DEFAULT_ROW_HEIGHT
    out[i + 1] = out[i] + rowHeight
  }
  return out
}

function findIndexByOffset(offset: number, prefix: number[] = prefixHeights.value): number {
  const count = Math.max(0, prefix.length - 1)
  if (count <= 0) return 0
  const target = Math.max(0, offset)
  let l = 0
  let r = count - 1
  while (l <= r) {
    const mid = (l + r) >> 1
    if ((prefix[mid + 1] ?? 0) <= target) l = mid + 1
    else r = mid - 1
  }
  return Math.max(0, Math.min(count - 1, l))
}

/**
 * 切换会话后贴底：先批量落盘行高，再单次 alignToBottom，避免与 ResizeObserver 多轨抢 scrollHeight。
 */
function scrollToBottomAfterLayout(instant = true, force = true) {
  if (force || instant) {
    userDismissedAutoFollow.value = false
  }
  if (force) {
    wasNearBottomBeforeMutation.value = true
  }
  cancelPendingBottomSnap()
  pendingAlignForce = force
  pendingAlignAfterHeightFlush = true
  nextTick(() => {
    schedulePendingHeightFlush(true)
  })
}

function scrollToBottom(instant = false, force = false) {
  nextTick(() => {
    const el = scrollRef.value
    if (!el) return
    if (force || instant) {
      userDismissedAutoFollow.value = false
    }
    const canAutoFollow = effectiveCanFollow(el)
    if (!force && !instant && !canAutoFollow) {
      syncScrollMetrics(el)
      return
    }
    if (force && !instant) {
      armBottomSnapAfterSmoothScroll(el, true)
    } else {
      cancelPendingBottomSnap()
    }
    alignToBottom(el, instant || !force)
    // 新消息刚插入时常会在下一帧完成真实高度测量，补一次贴底可避免 100~200px 回弹
    if (!force) {
      requestAnimationFrame(() => {
        const current = scrollRef.value
        if (!current) return
        if (effectiveCanFollow(current)) {
          alignToBottom(current, true)
        } else {
          syncScrollMetrics(current)
        }
      })
    }
  })
}

function prefersReducedMotionForSend(): boolean {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return false
  try {
    return window.matchMedia('(prefers-reduced-motion: reduce)').matches
  } catch {
    return false
  }
}

function cancelUserSendScrollAnim() {
  if (userSendScrollRaf != null) {
    cancelAnimationFrame(userSendScrollRaf)
    userSendScrollRaf = null
  }
  userSendScrollActive.value = false
}

/**
 * 用户发送消息时的动画滚动：rAF 驱动，cubic ease-out，固定时长（~420ms），
 * 让视口平滑下移带入新气泡，取代以往的瞬移 + 气泡内短 24px 上滑所产生的突变感。
 * 距离过大（滚到顶部发送等场景）或系统「减少动效」偏好开启时退化为 instant，
 * 保持发送反馈即时。
 */
function scrollToBottomAnimated(duration: number = USER_SEND_SCROLL_ANIM_MS) {
  nextTick(() => {
    const el = scrollRef.value
    if (!el) return
    userDismissedAutoFollow.value = false
    cancelPendingBottomSnap()
    cancelUserSendScrollAnim()

    const startTop = el.scrollTop
    const targetTop = Math.max(0, el.scrollHeight - el.clientHeight)
    const delta = targetTop - startTop
    if (Math.abs(delta) < 1) {
      syncScrollMetrics(el)
      return
    }
    if (Math.abs(delta) > USER_SEND_SCROLL_MAX_DISTANCE || prefersReducedMotionForSend()) {
      alignToBottom(el, true)
      requestAnimationFrame(() => {
        const latest = scrollRef.value
        if (!latest) return
        alignToBottom(latest, true)
      })
      return
    }

    userSendScrollActive.value = true
    const prevBehavior = el.style.scrollBehavior
    el.style.scrollBehavior = 'auto'
    const startTs = performance.now()
    const durMs = Math.max(1, duration)

    const step = (now: number) => {
      const current = scrollRef.value
      if (!current || current !== el) {
        userSendScrollRaf = null
        userSendScrollActive.value = false
        el.style.scrollBehavior = prevBehavior
        return
      }
      const t = Math.min(1, (now - startTs) / durMs)
      // cubic ease-out: 与气泡入场 cubic-bezier(0.16, 1, 0.3, 1) 观感接近
      const eased = 1 - Math.pow(1 - t, 3)
      const liveTarget = Math.max(0, current.scrollHeight - current.clientHeight)
      current.scrollTop = startTop + (liveTarget - startTop) * eased
      if (t < 1) {
        userSendScrollRaf = requestAnimationFrame(step)
      } else {
        userSendScrollRaf = null
        userSendScrollActive.value = false
        current.style.scrollBehavior = prevBehavior
        alignToBottom(current, true)
        requestAnimationFrame(() => {
          const latest = scrollRef.value
          if (!latest) return
          alignToBottom(latest, true)
        })
      }
    }
    userSendScrollRaf = requestAnimationFrame(step)
  })
}

function handleScroll() {
  const el = scrollRef.value
  if (!el) return
  const oldScrollTop = scrollTop.value
  const oldDist = Math.max(0, el.scrollHeight - el.clientHeight - oldScrollTop)
  syncScrollMetrics(el)
  pendingBottomSnapRefresh?.()
  const nowDist = realDistanceFromBottom.value
  // 从贴底带外重新滚入带内时恢复跟底；带内向上滚仅置位 dismiss，不会在仍 ≤300px 时被误清除
  if (nowDist <= AUTO_FOLLOW_DISTANCE_THRESHOLD && oldDist > AUTO_FOLLOW_DISTANCE_THRESHOLD) {
    userDismissedAutoFollow.value = false
  }
}

function updateViewport() {
  if (!scrollRef.value) return
  syncScrollMetrics(scrollRef.value)
}

const totalCount = computed(() => props.messages.length)
const headerOverlayOffset = computed(() => Math.max(0, props.headerInsetPx) + 16)
const bottomScrollPaddingPx = computed(() => {
  return SCROLL_BOTTOM_BASE_PADDING_PX + Math.max(0, Math.ceil(props.bottomScrollExtraPx ?? 0))
})
const prefixHeights = computed(() => buildPrefixHeights(measuredHeights.value, props.messages))
const totalHeight = computed(() => prefixHeights.value[totalCount.value] ?? 0)
const isNearBottom = computed(() => realDistanceFromBottom.value <= SCROLL_BOTTOM_NEAR_THRESHOLD)
const showScrollToBottom = computed(() => realDistanceFromBottom.value > SCROLL_BOTTOM_SHOW_THRESHOLD)

const startIndex = computed(() => findIndexByOffset(scrollTop.value, prefixHeights.value))
const visibleCount = computed(() => Math.max(1, Math.ceil((viewportHeight.value || 1) / DEFAULT_ROW_HEIGHT) + 1))
const windowStart = computed(() => Math.max(0, startIndex.value - BUFFER_ITEMS))
const windowEnd = computed(() => Math.max(0, Math.min(totalCount.value - 1, startIndex.value + visibleCount.value + BUFFER_ITEMS)))
const topSpacerHeight = computed(() => prefixHeights.value[windowStart.value] ?? 0)
const bottomSpacerHeight = computed(() => {
  if (totalCount.value <= 0) return 0
  return Math.max(0, totalHeight.value - (prefixHeights.value[windowEnd.value + 1] ?? 0))
})
const visibleMessages = computed(() => {
  if (totalCount.value <= 0) return [] as ChatMessage[]
  return props.messages.slice(windowStart.value, windowEnd.value + 1)
})

function alignAfterHeightFlush(instant = true, force = false) {
  const el = scrollRef.value
  if (!el) return
  if (userSendScrollActive.value) {
    syncScrollMetrics(el)
    return
  }
  if (force || effectiveCanFollow(el)) {
    alignToBottom(el, instant)
  } else {
    syncScrollMetrics(el)
  }
}

function flushPendingHeights() {
  const ids = [...pendingMeasureIds]
  pendingMeasureIds.clear()
  const patch: Record<string, number> = {}
  let changed = false
  for (const messageId of ids) {
    const domEl = rowEls.get(messageId)
    if (!domEl) continue
    const measured = Math.ceil(domEl.getBoundingClientRect().height)
    const rowHeight = (measured > 0 ? measured : DEFAULT_ROW_HEIGHT - MESSAGE_ROW_GAP) + MESSAGE_ROW_GAP
    if ((measuredHeights.value[messageId] ?? DEFAULT_ROW_HEIGHT) !== rowHeight) {
      patch[messageId] = rowHeight
      changed = true
    }
  }
  if (changed) {
    measuredHeights.value = { ...measuredHeights.value, ...patch }
  }
  if (pendingMeasureIds.size > 0) {
    schedulePendingHeightFlush(pendingAlignAfterHeightFlush)
    return
  }
  if (!pendingAlignAfterHeightFlush) return

  const visible = visibleMessages.value
  const awaitingRefs =
    visible.length > 0 && visible.some((m) => !rowEls.has(m.id))
  if (awaitingRefs) {
    schedulePendingHeightFlush(true)
    return
  }

  const force = pendingAlignForce
  pendingAlignForce = false
  pendingAlignAfterHeightFlush = false
  nextTick(() => alignAfterHeightFlush(true, force))
}

function schedulePendingHeightFlush(alignAfter = false) {
  if (alignAfter) pendingAlignAfterHeightFlush = true
  if (pendingHeightFlushRaf != null) return
  pendingHeightFlushRaf = requestAnimationFrame(() => {
    pendingHeightFlushRaf = null
    flushPendingHeights()
  })
}

function setMessageRowRefById(messageId: string, el: unknown) {
  const domEl = normalizeElement(el)
  if (!domEl) {
    rowEls.delete(messageId)
    pendingMeasureIds.delete(messageId)
    return
  }
  rowEls.set(messageId, domEl)
  pendingMeasureIds.add(messageId)
  schedulePendingHeightFlush()
}

function shouldRunRowFlip(): boolean {
  if (typeof performance !== 'undefined' && performance.now() < flipSuppressedUntil) {
    return false
  }
  const ws = windowStart.value
  const we = windowEnd.value
  const sidebar = props.sidebarCollapsed
  const windowChanged = ws !== lastFlipWindowStart || we !== lastFlipWindowEnd
  const sidebarChanged = sidebar !== lastFlipSidebarCollapsed
  return windowChanged || sidebarChanged
}

function maybeSnapshotRowRects() {
  if (!shouldRunRowFlip()) return
  flipSnapshotPending = true
  snapshotRowRects()
}

function maybePlayRowFlip() {
  if (!flipSnapshotPending) return
  flipSnapshotPending = false
  if (!shouldRunRowFlip()) return
  lastFlipWindowStart = windowStart.value
  lastFlipWindowEnd = windowEnd.value
  lastFlipSidebarCollapsed = props.sidebarCollapsed
  playRowFlip()
}

function snapshotRowRects() {
  prevRowRects = new Map()
  for (const [messageId, el] of rowEls.entries()) {
    prevRowRects.set(messageId, el.getBoundingClientRect())
  }
}

function shouldSkipRowFlip(messageId: string): boolean {
  return messageId === props.entrancingUserMessageId || messageId === props.entrancingAssistantMessageId
}

function playRowFlip() {
  for (const [messageId, el] of rowEls.entries()) {
    if (shouldSkipRowFlip(messageId)) continue
    const prev = prevRowRects.get(messageId)
    if (!prev) continue
    const next = el.getBoundingClientRect()
    const dx = prev.left - next.left
    const dy = prev.top - next.top
    if (Math.abs(dx) < 1 && Math.abs(dy) < 1) continue
    el.style.transition = 'none'
    el.style.transform = `translate(${dx}px, ${dy}px)`
    requestAnimationFrame(() => {
      el.style.transition = 'transform 420ms cubic-bezier(0.16, 1, 0.3, 1)'
      el.style.transform = ''
      const cleanup = () => {
        el.style.transition = ''
      }
      el.addEventListener('transitionend', cleanup, { once: true })
    })
  }
}

function scrollToMessage(messageIndex: number) {
  if (!scrollRef.value || totalCount.value <= 0) return
  const idx = Math.max(0, Math.min(totalCount.value - 1, messageIndex))
  const y = prefixHeights.value[idx] ?? 0
  scrollRef.value.scrollTop = y
  scrollTop.value = y
}

watch(
  () => props.chatId,
  () => {
    cancelPendingBottomSnap()
    measuredHeights.value = {}
    markdownHtmlCache.clear()
    pendingMeasureIds.clear()
    rowEls.clear()
    prevRowRects.clear()
    if (pendingHeightFlushRaf != null) {
      cancelAnimationFrame(pendingHeightFlushRaf)
      pendingHeightFlushRaf = null
    }
    flipSuppressedUntil =
      typeof performance !== 'undefined' ? performance.now() + FLIP_SUPPRESS_MS : 0
    lastFlipWindowStart = -1
    lastFlipWindowEnd = -1
    lastFlipSidebarCollapsed = undefined
    flipSnapshotPending = false
    userDismissedAutoFollow.value = false
    wasNearBottomBeforeMutation.value = true
    scrollTop.value = 0
    nextTick(() => {
      updateViewport()
      const el = scrollRef.value
      if (!el) return
      // 先用默认行高估算贴底，避免沿用上一会话 scrollTop 导致虚拟窗口错位
      alignToBottom(el, true)
      syncScrollMetrics(el)
    })
  },
)

watch(
  () => props.messages.map((message) => message.id),
  (ids) => {
    const validIds = new Set(ids)
    const nextMeasured: Record<string, number> = {}
    for (const [messageId, height] of Object.entries(measuredHeights.value)) {
      if (validIds.has(messageId)) {
        nextMeasured[messageId] = height
      }
    }
    if (Object.keys(nextMeasured).length !== Object.keys(measuredHeights.value).length) {
      measuredHeights.value = nextMeasured
    }
  },
)

watch(
  () => props.headerInsetPx,
  () => {
    nextTick(() => {
      if (!scrollRef.value) return
      syncScrollMetrics(scrollRef.value)
    })
  },
)

watch(
  () => props.bottomScrollExtraPx ?? 0,
  () => {
    nextTick(() => {
      const el = scrollRef.value
      if (!el) return
      if (userSendScrollActive.value) {
        syncScrollMetrics(el)
        return
      }
      if (!effectiveCanFollow(el)) {
        syncScrollMetrics(el)
        return
      }
      alignToBottom(el, true)
      requestAnimationFrame(() => {
        const latest = scrollRef.value
        if (!latest) return
        if (effectiveCanFollow(latest)) {
          alignToBottom(latest, true)
        } else {
          syncScrollMetrics(latest)
        }
      })
    })
  },
)

onBeforeUpdate(() => {
  maybeSnapshotRowRects()
})

onUpdated(() => {
  maybePlayRowFlip()
})

// 暴露滚动方法
defineExpose({
  scrollToBottom,
  scrollToBottomAfterLayout,
  scrollToBottomAnimated,
  scrollToMessage,
  scrollRef,
})

onMounted(() => {
  window.addEventListener('keydown', closeTopImagePreviewFromEscape)
  updateViewport()
  window.addEventListener('resize', updateViewport)
  if (typeof ResizeObserver !== 'undefined') {
    contentResizeObserver = new ResizeObserver(() => {
      const el = scrollRef.value
      if (!el) return
      // 「用户发送动画滚动」期间只同步度量，不做 instant 贴底，
      // 避免 isGenerating=true 激活的 outputPhase 把 rAF 平滑滚动抢回瞬移。
      if (userSendScrollActive.value) {
        syncScrollMetrics(el)
        return
      }
      const canFollow = effectiveCanFollow(el)
      const outputPhase = props.isGenerating || props.isInterjecting
      if (outputPhase && canFollow) {
        alignToBottom(el, true)
        requestAnimationFrame(() => {
          const e2 = scrollRef.value
          if (!e2) return
          if (!(props.isGenerating || props.isInterjecting)) return
          if (!effectiveCanFollow(e2)) return
          alignToBottom(e2, true)
        })
      } else {
        syncScrollMetrics(el)
      }
    })
    if (contentRef.value) {
      contentResizeObserver.observe(contentRef.value)
    }
  }
})

onBeforeUnmount(() => {
  contentEls.clear()
  tailQueues.clear()
  if (tailRafId != null) {
    cancelAnimationFrame(tailRafId)
    tailRafId = null
  }
  cancelPendingBottomSnap()
  cancelUserSendScrollAnim()
  pendingMeasureIds.clear()
  if (pendingHeightFlushRaf != null) {
    cancelAnimationFrame(pendingHeightFlushRaf)
    pendingHeightFlushRaf = null
  }
  markdownHtmlCache.clear()
  window.removeEventListener('resize', updateViewport)
  if (contentResizeObserver) {
    contentResizeObserver.disconnect()
    contentResizeObserver = null
  }
})
</script>

<template>
  <div class="relative flex-1 min-h-0">
    <div
      ref="scrollRef"
      class="h-full overflow-y-auto px-4 scroll-smooth custom-scrollbar"
      :style="{
        paddingTop: `${headerOverlayOffset}px`,
        paddingBottom: `${bottomScrollPaddingPx}px`,
        transform: 'translateZ(0)',
        contain: 'content',
      }"
      @scroll="handleScroll"
      @wheel.passive="handleListWheel"
      @pointerdown="handleListPointerDown"
    >
      <div ref="contentRef" class="max-w-4xl mx-auto">
      <div v-if="topSpacerHeight > 0" :style="{ height: `${topSpacerHeight}px` }"></div>
      <div
        v-for="m in visibleMessages"
        :key="m.id"
        v-memo="messageRowMemoDeps(m)"
        :ref="(el) => setMessageRowRefById(m.id, el)"
        class="flex gap-4 group mb-8" 
        :class="[
          m.role === 'user' ? 'flex-row-reverse' : 'flex-row',
          isAssistantRowEntering(m) ? 'message-row--assistant-enter' : '',
        ]"
      >
        <!-- 头像 -->
        <div class="flex-shrink-0 mt-1">
          <div v-if="m.role === 'system'" class="w-10 h-10 rounded-full bg-yellow-500/20 flex items-center justify-center text-yellow-500">
            <Settings class="w-6 h-6" />
          </div>
          <button
            v-else
            type="button"
            class="rounded-xl transition-transform hover:scale-[1.03] active:scale-100"
            :class="getMessageAvatar(m) ? 'cursor-zoom-in' : 'cursor-default'"
            :disabled="!getMessageAvatar(m)"
            :aria-label="getMessageAvatar(m) ? `预览 ${getMessageLabel(m)} 的头像` : `${getMessageLabel(m)} 头像`"
            @click="openAvatarPreview(m)"
          >
            <ModernAvatar 
              :src="getMessageAvatar(m)"
              :name="getMessageLabel(m)"
              :size="40"
              aspect="1"
              object-fit="cover"
              :object-position="getMessageAvatarObjectPosition(m)"
              rounded="rounded-xl"
              class="shadow-sm bg-[var(--color-surface-inset)]"
            />
          </button>
        </div>

        <!-- 消息体 -->
        <div
          class="flex flex-1 min-w-0 flex-col max-w-[85%]"
          data-chat-bubble-column
          :class="m.role === 'user' ? 'items-end' : 'items-start'"
        >
          <div class="flex items-center gap-2 mb-1 px-1 flex-wrap">
            <span class="text-xs font-bold" :class="m.role === 'user' ? 'text-brand-fg-soft' : 'text-[var(--color-text-muted)]'">
              {{ getMessageLabel(m) }}
            </span>
            <span v-if="m.role === 'system'" class="text-[10px] bg-yellow-500/10 text-yellow-500 px-1.5 py-0.5 rounded">SYSTEM</span>
            <div
              v-if="getOutgoingFork(m)"
              :ref="(el) => setForkListAnchor(m.id, el)"
              class="relative"
            >
              <button
                type="button"
                class="text-[10px] text-brand hover:underline"
                :aria-label="`已有 ${getOutgoingFork(m)?.count ?? 0} 个分叉，点击查看`"
                @click.stop="toggleForkList(m.id)"
              >
                已有 {{ getOutgoingFork(m)?.count }} 个分叉
              </button>
              <SelectDropdownSurface
                v-if="forkListMessageId === m.id"
                v-model:open="forkListOpen"
                :anchor-ref="forkListAnchorRef"
                placement="bottom"
                :auto-width="true"
                :gap-px="4"
                max-height-class="max-h-48"
                @update:open="(v) => { if (!v) forkListMessageId = null }"
              >
                <button
                  v-for="fc in getOutgoingFork(m)?.chats ?? []"
                  :key="fc.chatId"
                  type="button"
                  class="w-full text-left px-3 py-2 rounded-lg text-sm text-[var(--color-text-secondary)] hover:bg-surface-muted truncate"
                  role="menuitem"
                  @click="onSelectForkChild(fc.chatId)"
                >
                  {{ fc.title }}
                </button>
              </SelectDropdownSurface>
            </div>
          </div>

          <!-- 思考链气泡：流式未展开默认 100px 限高（streamingWindowHeight），超出内层滚动；结束后收起为「已思考 x.x 秒」小卡片 -->
          <ReasoningBubble
            v-if="m.role === 'assistant' && (getReasoningForMessage(m) || shouldShowReasoningPlaceholder(m))"
            class="mb-2"
            :content="getReasoningForMessage(m) || ''"
            :is-streaming="isMessageReasoningStreaming(m)"
            :duration-sec="getReasoningDurationForMessage(m)"
            :expanded="isReasoningExpanded(m.id)"
            @update:expanded="(v) => (expandedReasoningMessageId = v ? m.id : null)"
          />

          <!-- 气泡 -->
          <div
            v-if="shouldRenderMainBubble(m)"
            data-chat-bubble-shell
            class="message-bubble relative w-fit max-w-full min-w-0 shadow-sm"
            :class="[
              m.role === 'user' 
                ? 'message-bubble--user text-primary' 
                : m.role === 'assistant'
                  ? 'message-bubble--assistant text-primary'
                  : 'message-bubble--system',
              isUserSendEntering(m) ? 'message-bubble--user-send-enter' : '',
            ]"
          >
            <AnimatedClipHeight
              mode="intrinsic-fullColumn"
              :relax-height-dead-zone="
                (isGenerating || isInterjecting) && m.role === 'assistant' && m.id.startsWith('local_')
              "
            >
              <div class="w-fit max-w-full min-w-0">
                <div
                  class="md prose prose-invert prose-sm max-w-none prose-p:my-1 prose-headings:my-2 prose-pre:bg-[var(--color-surface-inset)] prose-pre:border prose-pre:border-[var(--color-border-subtle)]"
                  :style="messageContentFontSizeStyle"
                  :ref="(el) => setContentRef(m.id, el)"
                >
                  <div class="stream-markdown" v-html="renderMarkdown(m)"></div>
                </div>
                <div v-if="m.images?.length" class="mt-3 grid grid-cols-2 md:grid-cols-3 gap-2">
                  <button
                    v-for="img in m.images"
                    :key="img.id"
                    type="button"
                    class="block rounded-lg overflow-hidden border border-[var(--color-border)] bg-[var(--color-surface-inset)]"
                    :aria-label="`预览图片 ${img.originalName || 'chat-image'}`"
                    @click="openImagePreview(getChatImageUrl(img.id), img.originalName || 'chat-image')"
                  >
                    <img
                      :src="getChatImageUrl(img.id)"
                      :alt="img.originalName || 'chat-image'"
                      class="w-full h-24 object-cover"
                      loading="lazy"
                      draggable="false"
                    />
                  </button>
                </div>
              </div>
              <template #measure>
                <div class="w-fit max-w-full min-w-0">
                  <div
                    class="md prose prose-invert prose-sm max-w-none prose-p:my-1 prose-headings:my-2 prose-pre:bg-[var(--color-surface-inset)] prose-pre:border prose-pre:border-[var(--color-border-subtle)]"
                    :style="messageContentFontSizeStyle"
                  >
                    <div class="stream-markdown" v-html="renderMarkdown(m)"></div>
                  </div>
                  <div v-if="m.images?.length" class="mt-3 grid grid-cols-2 md:grid-cols-3 gap-2">
                    <div
                      v-for="img in m.images"
                      :key="img.id"
                      class="block rounded-lg overflow-hidden border border-[var(--color-border)] bg-[var(--color-surface-inset)]"
                    >
                      <img
                        :src="getChatImageUrl(img.id)"
                        :alt="img.originalName || 'chat-image'"
                        class="w-full h-24 object-cover"
                        loading="lazy"
                        draggable="false"
                      />
                    </div>
                  </div>
                </div>
              </template>
            </AnimatedClipHeight>
            <!-- 长期记忆已保存标记：不受消息字体大小设置影响 -->
            <div
              v-if="m.memoryUpdatedAfterThis"
              class="absolute right-2 bottom-2 flex items-center gap-1 pointer-events-none"
              style="font-size: 10px; line-height: 1;"
            >
              <span class="w-1.5 h-1.5 rounded-full bg-[var(--color-success)] shrink-0" aria-hidden="true"></span>
              <span class="text-muted" style="font-size: 10px;">已保存</span>
            </div>
          </div>

          <!-- 版本切换箭头 -->
          <div v-if="m.role === 'assistant' && hasMultipleVersions(m)" class="flex items-center justify-center gap-2 mt-1 px-1">
            <button 
              class="icon-button text-xs px-2 py-0.5"
              :aria-label="`上一个版本 (${getCurrentVersionIndex(m) + 1}/${getVersionCount(m)})`"
              @click="emit('switch-previous-version', m)"
            >
              <ChevronLeft class="w-3 h-3" />
            </button>
            <span class="text-xs text-muted">
              {{ getCurrentVersionIndex(m) + 1 }}/{{ getVersionCount(m) }}
            </span>
            <button 
              class="icon-button text-xs px-2 py-0.5"
              :aria-label="`下一个版本 (${getCurrentVersionIndex(m) + 1}/${getVersionCount(m)})`"
              @click="emit('switch-next-version', m)"
            >
              <ChevronRight class="w-3 h-3" />
            </button>
          </div>

          <!-- 底部操作栏：鼠标 hover 显示；触控/笔常驻（与侧栏列表一致） -->
          <div
            class="flex items-center gap-2 mt-1 px-1 transition-opacity"
            :class="preferHoverChrome ? 'opacity-0 group-hover:opacity-100' : 'opacity-100'"
          >
            <button
              v-if="settingsStore.settings?.ttsEnabled && (m.role === 'assistant' || m.role === 'user') && !m.id.startsWith('local_') && getDisplayContent(m).trim()"
              class="btn btn-xs btn-ghost"
              @click="emit('read-aloud-message', m)"
            >
              朗读
            </button>
            <button
              v-if="canForkMessage(m)"
              class="btn btn-xs btn-ghost"
              :disabled="isGenerating || isForking"
              @click="emit('fork-message', m)"
            >
              分支
            </button>
            <button 
              v-if="m.role === 'assistant' && !m.id.startsWith('local_')" 
              class="btn btn-xs btn-ghost" 
              @click="emit('rewrite-message', m)" 
              :disabled="isGenerating"
            >
              重写
            </button>
            <button 
              class="btn btn-xs btn-ghost" 
              @click="emit('edit-message', m)" 
              :disabled="isGenerating"
            >
              编辑
            </button>
            <button 
              class="btn btn-xs btn-danger" 
              :disabled="isGenerating"
              @click="confirmDelete(m, $event)"
            >
              删除
            </button>
          </div>
        </div>
      </div>
        <div v-if="bottomSpacerHeight > 0" :style="{ height: `${bottomSpacerHeight}px` }"></div>
      </div>
    </div>

    <button
      v-if="showScrollToBottom && !isNearBottom"
      type="button"
      class="scroll-to-bottom-btn glass-panel"
      aria-label="回到底部"
      @click="scrollToBottom(false, true)"
    >
      <ChevronDown class="w-4 h-4" />
    </button>

    <!-- 删除确认弹窗 -->
    <ConfirmPopover
      :show="!!deleteConfirm"
      :target="deleteConfirm?.target || null"
      message="确定删除这条消息？"
      confirm-text="删除"
      @confirm="handleConfirmDelete"
      @cancel="cancelDelete"
      @update:show="(val) => !val && cancelDelete()"
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
              <X class="w-4 h-4" />
            </button>
            <img
              :src="preview.src"
              :alt="preview.alt"
              class="image-preview-img"
              draggable="false"
            />
          </div>
        </TransitionGroup>
      </div>
    </Teleport>
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

.scroll-to-bottom-btn {
  position: absolute;
  right: 16px;
  bottom: 20px;
  width: 36px;
  height: 36px;
  border-radius: 9999px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: var(--color-text-muted);
  z-index: 20;
  transition: color var(--transition-fast), border-color var(--transition-fast), transform var(--transition-fast);
}

.scroll-to-bottom-btn:hover {
  color: var(--color-text);
  border-color: var(--color-border-default);
  transform: translateY(-1px);
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
  color: var(--color-purple-text);
  text-decoration: underline;
}

.message-bubble .md {
  width: 100%;
}
.message-bubble .md .stream-markdown {
  /* 勿用 hidden/auto 形成内层滚动区；块级 KaTeX 需完整铺开（宽公式由外层列宽与页面滚动处理） */
  overflow: visible;
  word-wrap: break-word;
}
/* 首块常为标题：prose-headings:my-2 会留顶距，与仅 p:first-child 置零不一致，导致顶隙并可能诱发 frame 高度少算 */
.message-bubble .md .stream-markdown > :first-child {
  margin-top: 0;
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
  transition: background-color var(--transition-fast), color var(--transition-fast);
}

.image-preview-close:hover {
  background: var(--color-surface-hover);
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

@keyframes message-bubble-user-send-enter {
  from {
    opacity: 0.6;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

/*
 * 与 scrollToBottomAnimated 搭配：视口平滑下移把气泡从下方卷入视野，
 * 气泡自身再做 ~10px 的细微落地上浮 + 透明度收束，形成一体化过渡。
 */
.message-bubble--user-send-enter {
  animation: message-bubble-user-send-enter 0.42s cubic-bezier(0.16, 1, 0.3, 1) both;
}

@keyframes message-row-assistant-enter {
  from {
    opacity: 0.55;
    transform: translateY(12px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.message-row--assistant-enter {
  animation: message-row-assistant-enter 0.45s cubic-bezier(0.16, 1, 0.3, 1) both;
}

@media (prefers-reduced-motion: reduce) {
  .message-bubble--user-send-enter,
  .message-row--assistant-enter {
    animation: none;
  }
}
</style>
