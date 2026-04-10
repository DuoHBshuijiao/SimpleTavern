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
 * - set-content-ref: 设置消息内容的DOM引用（用于流式输出，传递给composables/useStreamOutput.ts）
 *
 * 使用的Composables：
 * 无（通过props接收函数）
 *
 * 使用的Stores：
 * 无
 *
 * 文件关系：
 *    - 被导入：被views/ChatPage.vue使用
 *    - 导入：导入vue的ref和nextTick、types/models.ts的类型、components/ModernAvatar.vue、markdown-it库
 *    - 依赖：依赖vue、markdown-it
 *    - 位置：组件层，提供消息列表显示功能
 */
import { ref, nextTick, computed, onBeforeUnmount, onMounted, watch } from 'vue'
import type { ChatMessage, CharacterCard, UserPersona } from '../../types/models'
import { useSettingsStore } from '../../stores'
import ModernAvatar from '../ModernAvatar.vue'
import ConfirmPopover from '../ConfirmPopover.vue'
import MarkdownIt from 'markdown-it'
import { Settings, ChevronLeft, ChevronRight, ChevronDown, X } from 'lucide-vue-next'

const settingsStore = useSettingsStore()
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
  /** 多轮思考链块：每项为 { messageId, content }，仅前端临时展示 */
  reasoningBlocks?: Array<{ messageId: string; content: string }>
  // 版本相关
  getDisplayContent: (m: ChatMessage) => string
  /** 获取当前显示版本对应的思考内容（多版本时随版本切换） */
  getDisplayReasoning?: (m: ChatMessage) => string | undefined
  hasMultipleVersions: (m: ChatMessage) => boolean
  getCurrentVersionIndex: (m: ChatMessage) => number
  getVersionCount: (m: ChatMessage) => number
  /** 固定顶栏高度（px），用于滚动区上方占位，使滚动条从顶栏下缘起算 */
  headerInsetPx: number
  /** 侧栏是否折叠；用于侧栏宽度动画结束后合并重排补偿，降低抖动 */
  sidebarCollapsed?: boolean
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
  'set-content-ref': [messageId: string, el: HTMLElement | null]
}>()

// 滚动容器引用
const scrollRef = ref<HTMLElement | null>(null)
const contentRef = ref<HTMLElement | null>(null)
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
/** 用户曾用滚轮向上或拖动滚动条解除跟底；回到贴底带内或强制滚底时清除 */
const userDismissedAutoFollow = ref(false)
let contentResizeObserver: ResizeObserver | null = null
let pendingBottomSnapToken = 0
let pendingBottomSnapTimer: ReturnType<typeof setTimeout> | null = null
let pendingBottomSnapScrollEndCleanup: (() => void) | null = null
let pendingBottomSnapRefresh: (() => void) | null = null

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
let previewWindowIdSeed = 0
let previewWindowZSeed = 1200

function isReasoningExpanded(messageId: string) {
  return expandedReasoningMessageId.value === messageId
}

function expandReasoning(messageId: string, e: MouseEvent) {
  if ((e.target as HTMLElement).closest('.reasoning-toggle-icon')) return
  expandedReasoningMessageId.value = messageId
}

function toggleReasoning(messageId: string, e: MouseEvent) {
  e.stopPropagation()
  expandedReasoningMessageId.value =
    expandedReasoningMessageId.value === messageId ? null : messageId
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

function closeImagePreview(id: number) {
  const target = getPreviewById(id)
  if (target?.isDragging) {
    target.isDragging = false
    activeDraggingPreviewId.value = null
    removePreviewDragListeners()
  }
  imagePreviews.value = imagePreviews.value.filter((preview) => preview.id !== id)
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

function normalizeElement(el: unknown): HTMLElement | null {
  if (!el) return null
  if (el instanceof HTMLElement) return el
  const maybe = (el as { $el?: unknown }).$el
  return maybe instanceof HTMLElement ? maybe : null
}

function setContentRef(messageId: string, el: unknown) {
  emit('set-content-ref', messageId, normalizeElement(el))
}

function openAvatarPreview(m: ChatMessage) {
  const avatarUrl = getMessageAvatar(m)
  if (!avatarUrl) return
  openImagePreview(avatarUrl, `${getMessageLabel(m)}-avatar`)
}

onBeforeUnmount(() => {
  removePreviewDragListeners()
  window.removeEventListener('resize', updateViewport)
})

/** 获取某条助手消息对应的思考链内容：优先版本绑定的思考，再当前流式内容，否则从 reasoningBlocks 按 messageId 取 */
function getReasoningForMessage(m: ChatMessage): string | undefined {
  if (m.role !== 'assistant') return undefined
  // 多版本时优先使用当前版本绑定的思考内容
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
    return content || undefined
  }
  return undefined
}

// Markdown 渲染器
const md = new MarkdownIt({
  html: false,
  linkify: true,
  breaks: true,
})

/**
 * 规范化Markdown输入
 *
 * 将Markdown中的引用语法（[name]:）中的冒号替换为中文冒号，避免被解析为链接定义。
 *
 * @param {string} text - Markdown文本
 * @returns {string} 规范化后的文本
 */
function normalizeMarkdownInput(text: string) {
  return (text ?? '').replace(/(^|\n)\[([^\]\n]+)\]:(\s*)/g, (_m, p1, name, sp) => `${p1}[${name}]：${sp}`)
}

/**
 * 渲染Markdown
 *
 * 使用MarkdownIt渲染Markdown文本为HTML。
 *
 * @param {string} text - Markdown文本
 * @returns {string} 渲染后的HTML
 */
function renderMarkdown(text: string) {
  return md.render(normalizeMarkdownInput(text))
}

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

function setMessageRowRefById(messageId: string, el: unknown) {
  const domEl = normalizeElement(el)
  if (!domEl) return
  const measured = Math.ceil(domEl.getBoundingClientRect().height)
  const rowHeight = (measured > 0 ? measured : DEFAULT_ROW_HEIGHT - MESSAGE_ROW_GAP) + MESSAGE_ROW_GAP
  if ((measuredHeights.value[messageId] ?? DEFAULT_ROW_HEIGHT) !== rowHeight) {
    measuredHeights.value = { ...measuredHeights.value, [messageId]: rowHeight }
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
    userDismissedAutoFollow.value = false
    nextTick(() => {
      updateViewport()
      if (!scrollRef.value) return
      syncScrollMetrics(scrollRef.value)
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

// 暴露滚动方法
defineExpose({ scrollToBottom, scrollToMessage, scrollRef })

onMounted(() => {
  updateViewport()
  window.addEventListener('resize', updateViewport)
  if (typeof ResizeObserver !== 'undefined') {
    contentResizeObserver = new ResizeObserver(() => {
      const el = scrollRef.value
      if (!el) return
      const canFollow = effectiveCanFollow(el)
      const outputPhase = props.isGenerating || props.isInterjecting
      if (outputPhase && canFollow) {
        alignToBottom(el, true)
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
  cancelPendingBottomSnap()
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
      class="h-full overflow-y-auto px-4 pb-4 scroll-smooth custom-scrollbar"
      :style="{
        paddingTop: `${headerOverlayOffset}px`,
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
        :ref="(el) => setMessageRowRefById(m.id, el)"
        class="flex gap-4 group mb-8" 
        :class="m.role === 'user' ? 'flex-row-reverse' : 'flex-row'"
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
              class="shadow-sm bg-black/20"
            />
          </button>
        </div>

        <!-- 消息体 -->
        <div class="flex flex-col max-w-[85%] min-w-0" :class="m.role === 'user' ? 'items-end' : 'items-start'">
          <div class="flex items-center gap-2 mb-1 px-1">
            <span class="text-xs font-bold" :class="m.role === 'user' ? 'text-brand-fg-soft' : 'text-[var(--color-text-muted)]'">
              {{ getMessageLabel(m) }}
            </span>
            <span v-if="m.role === 'system'" class="text-[10px] bg-yellow-500/10 text-yellow-500 px-1.5 py-0.5 rounded">SYSTEM</span>
          </div>

          <!-- 思考链气泡：在角色名下方、正文上方，小圆角，默认折叠 80px；点击气泡或图标展开，展开时点击图标收起；多轮回复按 messageId 显示对应思考内容 -->
          <div
            v-if="m.role === 'assistant' && getReasoningForMessage(m)"
            class="reasoning-bubble-surface w-full max-w-full rounded-lg text-xs leading-relaxed relative transition-[max-height] duration-300 ease-in-out mb-2"
            :class="isReasoningExpanded(m.id) ? 'max-h-[80vh] overflow-hidden' : 'max-h-[80px] overflow-hidden cursor-pointer'"
            @click="expandReasoning(m.id, $event)"
          >
            <div
              class="pr-8 py-2.5 pl-3 whitespace-pre-wrap break-words transition-[max-height] duration-300 ease-in-out"
              :class="isReasoningExpanded(m.id) ? 'max-h-[80vh] overflow-y-auto' : 'max-h-[80px] overflow-hidden'"
            >
              {{ getReasoningForMessage(m) }}
            </div>
            <button
              type="button"
              class="reasoning-toggle-icon absolute top-2 right-2 z-10 w-6 h-6 flex items-center justify-center rounded hover:bg-white/10 transition-transform duration-200"
              :class="isReasoningExpanded(m.id) ? 'rotate-90' : ''"
              :aria-label="isReasoningExpanded(m.id) ? '收起思考' : '展开思考'"
              @click="toggleReasoning(m.id, $event)"
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <polyline points="15 18 9 12 15 6" />
              </svg>
            </button>
          </div>

          <!-- 气泡 -->
          <div 
            class="message-bubble relative px-5 py-3.5 rounded-2xl text-[15px] leading-7 shadow-sm transition-[background-color,border-color,box-shadow] duration-200 border max-w-full min-w-0"
            :class="[
              m.role === 'user' 
                ? 'bg-brand-a20 backdrop-blur-sm border-brand-a20 text-gray-100 rounded-tr-sm hover:border-brand-a30' 
                : m.role === 'assistant'
                  ? 'bg-white/5 backdrop-blur-md border-white/10 text-gray-200 rounded-tl-sm hover:bg-white/10'
                  : 'bg-yellow-500/10 border-yellow-500/20 text-gray-300',
            ]"
          >
            <div
              class="md prose prose-invert prose-sm max-w-none prose-p:my-1 prose-headings:my-2 prose-pre:bg-black/30 prose-pre:border prose-pre:border-white/5"
              :style="messageContentFontSizeStyle"
              :ref="(el) => setContentRef(m.id, el)"
            >
              <div class="stream-markdown" v-html="renderMarkdown(getDisplayContent(m))"></div>
            </div>
            <div v-if="m.images?.length" class="mt-3 grid grid-cols-2 md:grid-cols-3 gap-2">
              <button
                v-for="img in m.images"
                :key="img.id"
                type="button"
                class="block rounded-lg overflow-hidden border border-[var(--color-border)] bg-black/20"
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
            <!-- 长期记忆已保存标记：不受消息字体大小设置影响 -->
            <div
              v-if="m.memoryUpdatedAfterThis"
              class="absolute right-2 bottom-2 flex items-center gap-1 pointer-events-none"
              style="font-size: 10px; line-height: 1;"
            >
              <span class="w-1.5 h-1.5 rounded-full bg-green-500 shrink-0" aria-hidden="true"></span>
              <span class="text-gray-400" style="font-size: 10px;">已保存</span>
            </div>
          </div>

          <!-- 版本切换箭头 -->
          <div v-if="m.role === 'assistant' && hasMultipleVersions(m)" class="flex items-center justify-center gap-2 mt-1 px-1">
            <button 
              class="text-xs text-gray-500 hover:text-gray-300 transition-colors px-2 py-0.5 rounded hover:bg-white/5"
              @click="emit('switch-previous-version', m)"
              :title="`上一个版本 (${getCurrentVersionIndex(m) + 1}/${getVersionCount(m)})`"
            >
              <ChevronLeft class="w-3 h-3" />
            </button>
            <span class="text-xs text-gray-500">
              {{ getCurrentVersionIndex(m) + 1 }}/{{ getVersionCount(m) }}
            </span>
            <button 
              class="text-xs text-gray-500 hover:text-gray-300 transition-colors px-2 py-0.5 rounded hover:bg-white/5"
              @click="emit('switch-next-version', m)"
              :title="`下一个版本 (${getCurrentVersionIndex(m) + 1}/${getVersionCount(m)})`"
            >
              <ChevronRight class="w-3 h-3" />
            </button>
          </div>

          <!-- 底部操作栏 -->
          <div class="flex items-center gap-2 mt-1 px-1 transition-opacity opacity-0 group-hover:opacity-100">
            <button
              v-if="settingsStore.settings?.ttsEnabled && (m.role === 'assistant' || m.role === 'user') && !m.id.startsWith('local_') && getDisplayContent(m).trim()"
              class="text-xs text-gray-600 hover:text-brand transition-colors"
              @click="emit('read-aloud-message', m)"
            >
              朗读
            </button>
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

.image-preview-layer {
  position: fixed;
  inset: 0;
  pointer-events: none;
  /* 须高于 ChatPage 全屏背景图（含 blur/transform 的合成层），且低于 imageFallback(1400) 与通知(1500) */
  z-index: 1300;
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
  transition: background-color 0.2s ease;
}

.image-preview-close:hover {
  background: rgba(0, 0, 0, 0.78);
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
