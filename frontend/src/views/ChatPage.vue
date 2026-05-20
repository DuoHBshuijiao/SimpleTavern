<script setup lang="ts">
/**
 * ChatPage - 聊天页面主组件
 *
 * 组件职责：
 * - 作为聊天页面的主容器，协调所有子组件和composables
 * - 管理页面级状态（选中的角色、草稿消息、生成状态等）
 * - 处理核心业务流程（消息发送、流式生成、群聊管理等）
 * - 处理用户身份和角色的选择与管理
 * - 处理聊天会话的创建、选择、删除等操作
 * - 集成聊天助手面板
 *
 * 主要功能：
 *    - 消息发送：处理用户消息发送，支持单聊和群聊
 *    - 流式生成：处理LLM流式响应，实现打字机效果
 *    - 群聊管理：处理群聊的创建、成员管理、插话等
 *    - 消息操作：处理消息编辑、删除、重写、版本切换
 *    - 角色管理：处理角色的创建、编辑、删除
 *    - 身份管理：处理用户身份的创建、编辑、删除、切换
 *    - 设置管理：打开设置抽屉，管理全局和聊天设置
 *
 * 主要函数：
 *    - sendUserMessage: 发送用户消息
 *    - runGroupGeneration: 运行群聊生成
 *    - continueGroupChat: 继续群聊
 *    - startNextRound: 开始下一轮群聊
 *    - triggerInterject: 触发插话
 *    - stopStreaming: 停止流式传输
 *    - handlePrimaryAction: 处理主要操作
 *    - handleRewriteMessage: 处理消息重写
 *    - handleSaveAndSend: 处理保存并发送
 *    - createChat: 创建聊天
 *    - selectChat: 选择聊天
 *    - deleteChat: 删除聊天
 *    - openCreateCharacter: 打开创建角色
 *    - openEditCharacter: 打开编辑角色
 *    - saveCharacter: 保存角色
 *    - deleteCharacter: 删除角色
 *    - handleCreateGroup: 处理群聊创建
 *    - handleGroupSettingsApply: 群聊设置弹窗一次保存（顺序、延迟、system 插入）
 *    - handleModelSelect: 处理模型选择
 *    - scrollToBottom: 滚动到底部
 *
 * 使用的Composables：
 *    - useStreamOutput: 来自composables/useStreamOutput.ts，处理流式输出
 *    - useMessageVersions: 来自composables/useMessageVersions.ts，管理消息版本
 *    - useGroupChat: 来自composables/useGroupChat.ts，处理群聊逻辑
 *    - useAssistant: 来自composables/useAssistant.ts，处理聊天助手
 *    - useChatActions: 来自composables/useChatActions.ts，处理聊天操作
 *
 * 使用的Stores：
 *    - useSettingsStore: 来自stores/settings.ts，管理设置
 *    - useCharactersStore: 来自stores/characters.ts，管理角色
 *    - useChatsStore: 来自stores/chats.ts，管理聊天会话
 *
 * 文件关系：
 *    - 被导入：被router/index.ts导入作为聊天页面路由组件
 *    - 导入：导入vue的computed、onMounted、ref、watch、nextTick、stores/index.ts的Store、types/models.ts的类型、composables/index.ts的composables、components下的所有组件、api/http.ts和api/sse.ts的API函数
 *    - 依赖：依赖vue、stores、composables、components、api
 *    - 位置：视图层，作为聊天页面的主组件
 */
import { computed, onBeforeUnmount, onMounted, ref, watch, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useCharacterSidebarRecencyStore, useCharactersStore, useChatsStore, useSettingsStore, useUiStore, useMvuStore } from '../stores'
import type { SettingsDrawerTab } from '../stores/ui'
import type { ApiPreset, AssistantAttachment, CharacterCard, ChatContentRegexRule, ChatImageAttachment, ChatMessage, ChatOverrides, ChatMvuMode, ExtraFirstMessageEntry, ForkLineageResponse, ForkSiblingSummary, GroupMemberSettings, Chat, MainChatRole, MvuMode, TtsSessionConfig, WorldBook, GroupMvuPreset } from '../types/models'
import { buildForkTitle, forkMessagePreview } from '../utils/chatFork'

// Composables
import { 
  useStreamOutput, 
  useMessageVersions, 
  useGroupChat, 
  useAssistant,
  useChatActions,
  useSettingsImport,
} from '../composables'
import type { SillyTavernImportPreview } from '../composables/useSettingsImport'
import { usePageBackground } from '../composables/usePageBackground'
import { useWebGpuBackground } from '../composables/useWebGpuBackground'
import { useWebGpuBackgroundRuntime } from '../composables/useWebGpuBackgroundRuntime'
import { useViewportNarrowPortrait } from '../composables/useViewportNarrowPortrait'

// 子组件
import { ChatSidebar, MessageList, ChatInput, AssistantPanel, AssistantThread, MvuCapabilityEditor, MvuPanel } from '../components/chat'
import ForkLineageBanner from '../components/chat/ForkLineageBanner.vue'
import StateVariablesBar from '../components/chat/StateVariablesBar.vue'
import {
  GroupCreatorModal,
  MessageEditorModal,
  MemberSettingsModal,
  GroupSettingsModal,
  ChatExportModal,
  ChatImportModal,
} from '../components/modals'
import ErrorModal from '../components/modals/ErrorModal.vue'
import KnowledgeGraphModal from '../components/modals/KnowledgeGraphModal.vue'
import MessageForkModal from '../components/modals/MessageForkModal.vue'
import SettingsDrawer from '../components/SettingsDrawer.vue'
import AvatarCropper from '../components/AvatarCropper.vue'
import ModernAvatar from '../components/ModernAvatar.vue'
import ModernSelect from '../components/ModernSelect.vue'
import ThemedCheckbox from '../components/ThemedCheckbox.vue'
import TtsPlaybackFab from '../components/chat/TtsPlaybackFab.vue'
import { useTtsPlaybackQueue } from '../composables/useTtsPlaybackQueue'
import {
  computeAssistantNonOverlapTop,
  computeTtsNonOverlapTop,
  FAB_COLLISION_GAP_PX,
  rectsOverlap,
} from '../composables/useFabCollision'
import { Users, Settings, Sparkles, Loader2, X, MoreHorizontal, GripVertical, Check, Plus, Search, Globe } from 'lucide-vue-next'

// API
import { postAndConsumeSse } from '../api/sse'
import { apiPost, apiGet, apiPut } from '../api/http'
import { useErrorStack } from '../composables/useErrorStack'
import { notifyConfirm, notifyMessage } from '../composables/useNotify'
import { isTtsApiPreset, resolveTtsProvider } from '../utils/apiPresetKind'
import { validateFilesForTarget } from '../utils/attachmentPolicy'
import { resolveRichPaste } from '../utils/richPaste'
import { formatApiError } from '../utils/worldBookValidation'
import { resolveBumpCharacterId } from '../utils/characterSidebarBump'
import { isChatMvuRuntimeEnabled } from '../utils/groupMvu'
import {
  HEADER_EXPAND_MS,
  HEADER_LIFT_EASE,
  HEADER_LIFT_MS,
  HEADER_SQUEEZE_EASE,
  HEADER_SQUEEZE_MS,
  MAIN_LAYOUT_TRANSITION_MS,
} from '../constants/chatHeaderMorph'

// ========== Stores ==========
const settings = useSettingsStore()
const characters = useCharactersStore()
const chats = useChatsStore()
const characterSidebarRecency = useCharacterSidebarRecencyStore()
const uiStore = useUiStore()
const route = useRoute()
const router = useRouter()
const { refreshDataAfterImport, previewSillyTavernImport, materializeSillyTavernPending } = useSettingsImport()
const pageBackground = usePageBackground(() => settings.settings)
const webgpuCanvasRef = ref<HTMLCanvasElement | null>(null)
const { runtimeState: webgpuRuntimeState } = useWebGpuBackgroundRuntime()
const persistedWebgpuEnabled = computed(() => settings.settings?.webgpuBackgroundEnabled === true)
const persistedWebgpuActivePresetId = computed(() => settings.settings?.webgpuBackgroundActivePresetId ?? null)
const persistedWebgpuTargetFps = computed(() => {
  const v = settings.settings?.webgpuBackgroundTargetFps
  const allowed = new Set([12, 24, 30, 45, 60, 90, 120])
  if (v != null && allowed.has(v)) return v
  return 60
})
const effectiveWebgpuEnabled = computed(() =>
  webgpuRuntimeState.hasOverride ? webgpuRuntimeState.enabled : persistedWebgpuEnabled.value,
)
const effectiveWebgpuActivePresetId = computed(() =>
  webgpuRuntimeState.hasOverride
    ? webgpuRuntimeState.activePresetId
    : persistedWebgpuActivePresetId.value,
)
const effectiveWebgpuShaderFilename = computed(() => {
  const presets = settings.settings?.webgpuBackgroundPresets || []
  const activeId = effectiveWebgpuActivePresetId.value
  if (!activeId) return null
  const active = presets.find((item) => item.id === activeId)
  return active?.wgslFile?.trim() || null
})
// ========== TTS 播放队列 / 主聊天错误栈（TTS 失败亦入栈）==========
const ttsQueue = useTtsPlaybackQueue()
const ttsIsDownloading = computed(() => ttsQueue.isDownloading.value)
const ttsIsPlaying = computed(() => ttsQueue.isPlaying.value)
const ttsAudioPaused = computed(() => ttsQueue.audioPaused.value)
const ttsQueuePanelItems = computed(() =>
  ttsQueue.queue.value.filter((i) => i.status !== 'done' && i.status !== 'aborted'),
)
const errorStack = useErrorStack(6000)

// ========== 页面级状态 ==========
const selectedCharacterId = ref<string | null>(null)
const draftMessage = ref('')
interface DraftImageItem {
  id: string
  file: File
  name: string
  previewUrl: string
}
interface EmbeddedCharacterCardPreview {
  card: CharacterCard
  worldbook?: WorldBook | null
}
interface AvatarCropSavePayload {
  imageData: string
  focusX?: number
  focusY?: number
}
const draftImages = ref<DraftImageItem[]>([])
const workspaceAssistantTextareaRef = ref<HTMLTextAreaElement | null>(null)
/** 角色编辑页内嵌助手消息列表滚动容器（与侧栏 AssistantPanel 分离） */
const workspaceAssistantMessagesListRef = ref<HTMLElement | null>(null)
const isWorkspaceAssistantDragOver = ref(false)
const showSettings = ref(false)
const showGroupSettings = ref(false)
const showExportModal = ref(false)
const showImportModal = ref(false)
/** 与 sessionStorage 同步，避免扩展跳转或仅带 janitorCharImport 的 URL 时丢失聊天暂存 id */
const JANITOR_CHAT_PENDING_STORAGE_KEY = 'simpletavern:janitorChatPendingId'
const janitorPendingId = ref<string | null>(null)
const janitorPendingReloadNonce = ref(0)
const settingsTab = ref<SettingsDrawerTab>('global')
const isGenerating = ref(false)
const streamError = ref<string | null>(null)
const sidebarCollapsed = ref(false)
const { isNarrowPortrait } = useViewportNarrowPortrait()
/** 主内容区左缘（用于助手 FAB 左贴边），随侧栏折叠与窗口变化测量 */
const chatMainRef = ref<HTMLElement | null>(null)
const contentAreaLeftPx = ref(0)
let contentAreaLeftRaf = 0
let contentAreaLeftLayoutRaf = 0
let contentAreaLeftSepDebounce: ReturnType<typeof setTimeout> | null = null
function updateContentAreaLeft() {
  contentAreaLeftPx.value = chatMainRef.value?.getBoundingClientRect().left ?? 0
}
function scheduleContentAreaLeft() {
  if (contentAreaLeftRaf) cancelAnimationFrame(contentAreaLeftRaf)
  contentAreaLeftRaf = requestAnimationFrame(() => {
    contentAreaLeftRaf = 0
    updateContentAreaLeft()
  })
}
function cancelContentAreaLeftLayoutSync() {
  if (contentAreaLeftLayoutRaf) {
    cancelAnimationFrame(contentAreaLeftLayoutRaf)
    contentAreaLeftLayoutRaf = 0
  }
}
/** 侧栏 padding 过渡期间每帧测量主区左缘，贴左 FAB 与主区同帧，避免对 left 做 CSS 插值带来的相位差 */
function syncContentAreaLeftDuringLayoutTransition() {
  cancelContentAreaLeftLayoutSync()
  const start = performance.now()
  const duration = MAIN_LAYOUT_TRANSITION_MS + 40
  const tick = () => {
    updateContentAreaLeft()
    if (performance.now() - start < duration) {
      contentAreaLeftLayoutRaf = requestAnimationFrame(() => {
        contentAreaLeftLayoutRaf = 0
        tick()
      })
    } else {
      updateContentAreaLeft()
      runChatFabSeparation()
    }
  }
  tick()
}
/** 顶栏变形：inset 悬浮条 → lifting 仅上移贴顶 → full 拉满宽并直角 */
const headerMorphPhase = ref<'inset' | 'lifting' | 'full'>('inset')
let webgpuUnavailablePrompted = false
const webgpuBackground = useWebGpuBackground({
  canvasRef: webgpuCanvasRef,
  enabled: effectiveWebgpuEnabled,
  shaderFilename: effectiveWebgpuShaderFilename,
  headerMorphPhase,
  targetFps: persistedWebgpuTargetFps,
  onUnavailable: (detail) => {
    if (webgpuUnavailablePrompted) return
    webgpuUnavailablePrompted = true
    void notifyMessage(`${detail.message} 已回退到图片背景（如已设置）或主题底色。`, {
      title: 'WebGPU 不可用',
    })
  },
})
watch(effectiveWebgpuEnabled, (on) => {
  if (!on) webgpuUnavailablePrompted = false
})

/** WebGPU 已确认可用且可绘制时，隐藏图片层避免叠在错误层上 */
const webgpuPaintVisible = computed(
  () => effectiveWebgpuEnabled.value && webgpuBackground.isSupported.value === true,
)
const showImageLayer = computed(() => pageBackground.hasImage.value && !webgpuPaintVisible.value)

/** 展开侧栏时恢复原状用较短过渡（ms） */
const headerEasingMs = ref(320)

let headerCompactDelayTimer: ReturnType<typeof setTimeout> | null = null
let headerLiftChainTimer: ReturnType<typeof setTimeout> | null = null

watch(sidebarCollapsed, (collapsed) => {
  if (headerCompactDelayTimer) {
    clearTimeout(headerCompactDelayTimer)
    headerCompactDelayTimer = null
  }
  if (headerLiftChainTimer) {
    clearTimeout(headerLiftChainTimer)
    headerLiftChainTimer = null
  }
  if (!collapsed) {
    headerEasingMs.value = HEADER_EXPAND_MS
    headerMorphPhase.value = 'inset'
    window.setTimeout(() => {
      headerEasingMs.value = 320
    }, 220)
    return
  }
  headerMorphPhase.value = 'inset'
  headerCompactDelayTimer = window.setTimeout(() => {
    headerMorphPhase.value = 'lifting'
    headerCompactDelayTimer = null
    headerLiftChainTimer = window.setTimeout(() => {
      headerMorphPhase.value = 'full'
      headerLiftChainTimer = null
    }, HEADER_LIFT_MS)
  }, 1000)
})

watch(sidebarCollapsed, () => {
  nextTick(() => {
    updateContentAreaLeft()
    runChatFabSeparation()
    syncContentAreaLeftDuringLayoutTransition()
  })
})

watch(isNarrowPortrait, () => {
  nextTick(() => scheduleContentAreaLeft())
})

const chatHeaderStyle = computed(() => {
  const phase = headerMorphPhase.value
  const collapsed = sidebarCollapsed.value
  const ms = headerEasingMs.value
  /** 竖屏 overlay：顶栏 left 用收起态量级；宽屏且侧栏展开仍用 21rem 与流式侧栏对齐 */
  const insetLeft =
    collapsed || isNarrowPortrait.value ? 'calc(1rem + 0.75rem)' : 'calc(21rem + 0.75rem)'
  const insetRight = '0.75rem'
  const insetTop = '0.75rem'
  const radiusOpen = 'var(--radius-2xl)'

  if (phase === 'full') {
    return {
      position: 'fixed' as const,
      left: '0',
      right: '0',
      top: '0',
      zIndex: 10,
      borderRadius: '0',
      transition: `left ${HEADER_SQUEEZE_MS}ms ${HEADER_SQUEEZE_EASE}, right ${HEADER_SQUEEZE_MS}ms ${HEADER_SQUEEZE_EASE}, border-radius ${HEADER_SQUEEZE_MS}ms ${HEADER_SQUEEZE_EASE}`,
    }
  }

  if (phase === 'lifting') {
    return {
      position: 'fixed' as const,
      left: insetLeft,
      right: insetRight,
      top: '0',
      zIndex: 10,
      borderRadius: radiusOpen,
      transition: `top ${HEADER_LIFT_MS}ms ${HEADER_LIFT_EASE}`,
    }
  }

  const transition = `left ${ms}ms ease, right ${ms}ms ease, top ${ms}ms ease, border-radius ${ms}ms ease`
  return {
    position: 'fixed' as const,
    left: insetLeft,
    right: insetRight,
    top: insetTop,
    zIndex: 10,
    borderRadius: radiusOpen,
    transition,
  }
})

const editingChatId = ref<string | null>(null)
const editingTitle = ref('')
const aborter = ref<AbortController | null>(null)
const stopRequested = ref(false)
const stopStreamingHold = ref(false)
/** 流式延后删除期间从列表隐藏的磁盘消息 id（与 omitMessageIds 对齐） */
const streamHiddenMessageIds = ref<string[]>([])
/** 流式成功后应从磁盘删除的消息 id（非 local_*） */
const streamDeferDeleteIds = ref<string[]>([])
/** 重写中断：local_rewrite 半截合并到该锚点气泡 */
const rewriteMergeCtx = ref<{
  chatId: string
  anchorId: string
  anchorTs: string
  originalMessageId: string
} | null>(null)
/** 保存并发送：已更新用户消息后延后截断尾巴；中断时按尾巴形态保留半成品 */
const saveSendDeferCtx = ref<{
  chatId: string
  tailIdsToDeleteOnSuccess: string[]
  singleAssistantTailMergeId?: string | null
  mode: 'single' | 'group'
} | null>(null)

const showEmbeddedCardConfirmModal = ref(false)
const embeddedCardPreview = ref<EmbeddedCharacterCardPreview | null>(null)
const embeddedCardImporting = ref(false)
/** 头像裁剪上传 PNG 后，与完整 ST 导入一致的预览 pending（用于 MVU 选项） */
const avatarEmbeddedStPendingId = ref('')
const avatarEmbeddedStExpiresAt = ref('')
const avatarEmbeddedStPreview = ref<SillyTavernImportPreview | null>(null)
const avatarEmbeddedEnableMvu = ref(false)
const avatarEmbeddedMvuMode = ref<MvuMode>('regex')
const avatarEmbeddedMvuModeOptions = [
  { label: 'Regex 兼容', value: 'regex' },
  { label: '指令模式', value: 'directive' },
] as const

const avatarEmbeddedDetectedMvu = computed(() => {
  const mvu = avatarEmbeddedStPreview.value?.mvu
  return Boolean(mvu?.hasTavernHelper || mvu?.hasRegexScripts || mvu?.characterBookCandidateCount)
})

const embeddedCardConfirmLabel = computed(() => {
  if (!embeddedCardImporting.value) return '覆盖当前编辑'
  return avatarEmbeddedEnableMvu.value && avatarEmbeddedMvuMode.value === 'directive'
    ? 'MVU Agent 分析中...'
    : '导入中...'
})

function imageDataUrlToPngFile(imageData: string, filename: string): File {
  const base64 = imageData.includes(',') ? imageData.split(',')[1]! : imageData
  const bin = atob(base64)
  const bytes = new Uint8Array(bin.length)
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i)
  return new File([bytes], filename, { type: 'image/png' })
}

function resetAvatarEmbeddedStState() {
  avatarEmbeddedStPendingId.value = ''
  avatarEmbeddedStExpiresAt.value = ''
  avatarEmbeddedStPreview.value = null
  avatarEmbeddedEnableMvu.value = false
  avatarEmbeddedMvuMode.value = 'regex'
}

function updateAvatarEmbeddedMvuMode(value: string) {
  avatarEmbeddedMvuMode.value = value === 'directive' ? 'directive' : 'regex'
}
/** 主聊天当前展示思考链的消息 ID（仅前端临时，刷新后消失） */
const chatReasoningMessageId = ref<string | null>(null)
/** 主聊天思考链内容（当前正在流式接收的一条） */
const chatReasoningContent = ref('')
/** 主聊天多轮思考链块：每项为 { messageId, content }，仅前端临时展示，不写进上下文 */
const chatReasoningBlocks = ref<Array<{ messageId: string; content: string }>>([])
/** 首条正文 delta 之前为 true；收到 delta 或 done/清空后为 false（用于 ReasoningBubble 流式态） */
const chatReasoningStreamActive = ref(false)
/** 本条流式思考阶段开始时间（ms），用于收起小卡时显示「已思考 x.x 秒」 */
const reasoningPhaseStartedAt = ref<number | null>(null)
/** 思考阶段结束时写入的秒数（1 位小数），供 MessageList 覆盖直至消息持久化带 reasoningDurationSec */
const chatReasoningElapsedSec = ref<number | null>(null)

function markReasoningStreamPhaseStart() {
  reasoningPhaseStartedAt.value = Date.now()
  chatReasoningElapsedSec.value = null
}

function clearReasoningPhaseTiming() {
  reasoningPhaseStartedAt.value = null
  chatReasoningElapsedSec.value = null
}

/** 首条正文 delta：结束思考流式阶段并写入已用时长（秒） */
function onAssistantContentDeltaStarted() {
  if (chatReasoningStreamActive.value && reasoningPhaseStartedAt.value != null) {
    chatReasoningElapsedSec.value = Math.round((Date.now() - reasoningPhaseStartedAt.value) / 100) / 10
  }
  chatReasoningStreamActive.value = false
}

watch(() => uiStore.settingsDrawerRequestNonce, (nonce) => {
  if (!nonce) return
  settingsTab.value = uiStore.requestedSettingsTab
  showSettings.value = true
})

function shouldIgnoreStreamingEventWhileStopping(eventName: string): boolean {
  return stopRequested.value && eventName === 'delta'
}

/** 将当前思考内容写入 blocks 并清空当前（在 stream done 或非流响应后调用，便于多轮保留） */
function pushCurrentReasoningToBlocks(finalMessageId?: string | null, localAliasId?: string | null) {
  const primary = finalMessageId ?? chatReasoningMessageId.value
  const content = chatReasoningContent.value.trim()
  const ids = new Set<string>()
  if (primary) ids.add(primary)
  if (localAliasId && localAliasId !== primary) ids.add(localAliasId)

  const elapsed = chatReasoningElapsedSec.value
  if (typeof elapsed === 'number' && Number.isFinite(elapsed) && chats.activeChat && ids.size > 0) {
    for (const messageId of ids) {
      const msg = chats.activeChat.messages.find((m) => m.id === messageId)
      if (msg && msg.role === 'assistant') {
        msg.reasoningDurationSec = elapsed
      }
    }
  }

  if (content && ids.size > 0 && chats.activeChat) {
    for (const messageId of ids) {
      const msg = chats.activeChat.messages.find((m) => m.id === messageId)
      if (msg && msg.role === 'assistant') {
        msg.reasoningContent = content
      }
    }
    let blocks = chatReasoningBlocks.value
    for (const messageId of ids) {
      blocks = [...blocks, { messageId, content }]
    }
    chatReasoningBlocks.value = blocks
  }
  chatReasoningContent.value = ''
  chatReasoningMessageId.value = null
  chatReasoningStreamActive.value = false
  clearReasoningPhaseTiming()
}

/** 根据消息 ID 获取当前关联的思考内容（流式当前条或 blocks 中已保存的） */
function getReasoningForMessageId(messageId: string): string {
  if (messageId === chatReasoningMessageId.value && chatReasoningContent.value) {
    return chatReasoningContent.value
  }
  const block = chatReasoningBlocks.value.find((b) => b.messageId === messageId)
  if (block?.content?.trim()) return block.content.trim()
  const msg = activeChat.value?.messages.find((m) => m.id === messageId)
  return msg?.reasoningContent?.trim() ?? ''
}

/**
 * 计算选中的角色
 *
 * 根据selectedCharacterId从角色列表中查找角色。
 */
const selectedCharacter = computed(() => {
  if (!selectedCharacterId.value) return null
  return characters.list.find((c) => c.id === selectedCharacterId.value) ?? null
})

/**
 * 计算当前激活的聊天
 *
 * 从chatsStore获取当前激活的聊天会话。
 */
const activeChat = computed(() => chats.activeChat)

/** 占位符重试成功后：在同一会话且同模型+同 API 预设下自动对上游使用 [image] 占位，直到切换模型/预设或换会话（localStorage 按 chatId 持久化） */
const IMAGE_STICKY_STORAGE_KEY = 'SimpleTavern:imageStickyBinding:v1'

type ImageStickyPersistRow = { model: string; presetId: string | null }

function loadImageStickyMap(): Record<string, ImageStickyPersistRow> {
  if (typeof window === 'undefined') return {}
  try {
    const raw = localStorage.getItem(IMAGE_STICKY_STORAGE_KEY)
    if (!raw) return {}
    const o = JSON.parse(raw) as unknown
    if (!o || typeof o !== 'object' || Array.isArray(o)) return {}
    return o as Record<string, ImageStickyPersistRow>
  } catch {
    return {}
  }
}

function persistImageStickyMap(map: Record<string, ImageStickyPersistRow>) {
  if (typeof window === 'undefined') return
  try {
    localStorage.setItem(IMAGE_STICKY_STORAGE_KEY, JSON.stringify(map))
  } catch {
    /* quota / 隐私模式 */
  }
}

function saveImageStickyBindingRow(bind: { chatId: string; model: string; presetId: string | null }) {
  const map = loadImageStickyMap()
  map[bind.chatId] = { model: bind.model, presetId: bind.presetId }
  persistImageStickyMap(map)
}

function removeImageStickyBindingRow(chatId: string) {
  const map = loadImageStickyMap()
  if (!(chatId in map)) return
  delete map[chatId]
  persistImageStickyMap(map)
}

function parseImageBindingWatchKey(key: string): { chatId: string; model: string; preset: string } | null {
  if (!key) return null
  const parts = key.split('\0')
  if (parts.length < 2) return null
  const chatId = parts[0] ?? ''
  const model = parts[1] ?? ''
  const preset = parts[2] ?? ''
  return { chatId, model, preset }
}

const imageStickyBinding = ref<{ chatId: string; model: string; presetId: string | null } | null>(null)

function resolveImageBindingKey(): { chatId: string; model: string; presetId: string | null } | null {
  const chat = activeChat.value
  if (!chat?.id) return null
  const model = chat.overrides?.params?.model || settings.settings?.llm?.defaultModel || ''
  const presetId = chat.overrides?.presetId ?? null
  return { chatId: chat.id, model, presetId }
}

function isImageStickyActive(): boolean {
  const cur = resolveImageBindingKey()
  const sticky = imageStickyBinding.value
  if (!cur || !sticky) return false
  return sticky.chatId === cur.chatId && sticky.model === cur.model && sticky.presetId === cur.presetId
}

function hydrateImageStickyFromStorage() {
  if (typeof window === 'undefined') return
  const cur = resolveImageBindingKey()
  if (!cur) return
  const map = loadImageStickyMap()
  const row = map[cur.chatId]
  if (!row || typeof row.model !== 'string') return
  const p = row.presetId == null || row.presetId === '' ? null : String(row.presetId)
  if (cur.model === row.model && cur.presetId === p) {
    imageStickyBinding.value = { chatId: cur.chatId, model: row.model, presetId: p }
  } else {
    delete map[cur.chatId]
    persistImageStickyMap(map)
  }
}

const imageBindingWatchKey = computed(() => {
  const chat = activeChat.value
  if (!chat) return ''
  return `${chat.id}\0${chat.overrides?.params?.model ?? ''}\0${chat.overrides?.presetId ?? ''}`
})

watch(imageBindingWatchKey, (newKey, oldKey) => {
  imageStickyBinding.value = null
  const oldP = oldKey ? parseImageBindingWatchKey(oldKey) : null
  const newP = newKey ? parseImageBindingWatchKey(newKey) : null
  if (
    oldP &&
    newP &&
    oldP.chatId === newP.chatId &&
    (oldP.model !== newP.model || oldP.preset !== newP.preset)
  ) {
    removeImageStickyBindingRow(newP.chatId)
  }
  hydrateImageStickyFromStorage()
})

/** MessageList 用：延后删除时在 UI 中隐藏仍会占上下文的消息 */
const messageListMessages = computed((): ChatMessage[] => {
  const chat = activeChat.value
  if (!chat?.messages?.length) return []
  const hid = streamHiddenMessageIds.value
  if (!hid.length) return chat.messages
  const hide = new Set(hid)
  return chat.messages.filter((m) => !hide.has(m.id))
})

/** 侧栏角色列表：按会话活跃度置顶（与 characters.list 内容一致，仅顺序不同） */
const sidebarCharacters = computed(() => {
  void characterSidebarRecency.lastActiveAt
  return characterSidebarRecency.sortedList(characters.list)
})

function pickLatestChatByUpdatedAt(list: Chat[]): Chat | null {
  if (!list.length) return null
  return [...list].sort((a, b) => Date.parse(b.updatedAt || '') - Date.parse(a.updatedAt || ''))[0] ?? null
}

function bumpSidebarForActiveChat() {
  characterSidebarRecency.bump(resolveBumpCharacterId(activeChat.value, selectedCharacterId.value))
}

let observedTtsChatId: string | null = null
let observedTtsMessageIds = new Set<string>()

/** 自动朗读已入队的内容指纹（按会话），避免本地 id 入队后 chats.load 换成服务端 id 时重复入队 */
const ttsAutoReadFingerprintsByChat = new Map<string, Set<string>>()

/** 手动朗读：入队完成前同步占位，避免连点两次都通过「队列尚无此项」检测 */
const manualTtsReadInFlight = new Set<string>()

/**
 * 等待补绑到服务端消息的 TTS 合成结果。
 * key = contentFingerprint（与 makeTtsAutoReadContentFingerprint 同源），
 * value = 合成产出的 assetId + spokenText。
 * 在 chats.load 完成后，遍历当前消息用指纹匹配并调用 bind-message。
 */
const pendingTtsBinds = new Map<string, { assetId: string; spokenText: string }>()

function getTtsAutoReadFingerprintSet(chatId: string): Set<string> {
  let s = ttsAutoReadFingerprintsByChat.get(chatId)
  if (!s) {
    s = new Set()
    ttsAutoReadFingerprintsByChat.set(chatId, s)
  }
  return s
}

function makeTtsAutoReadContentFingerprint(chatId: string, message: ChatMessage, displayText: string): string {
  const text = normalizeTtsCompareText(displayText)
  const charKey =
    message.role === 'assistant'
      ? message.characterId || activeChat.value?.characterId || ''
      : ''
  const personaKey =
    message.role === 'user'
      ? message.senderPersonaId || activeChat.value?.userPersonaId || selectedPersona.value?.id || ''
      : ''
  return `${chatId}\0${message.role}\0${charKey}\0${personaKey}\0${text}`
}

/**
 * 计算助手聊天ID
 *
 * 获取当前激活聊天的ID，用于助手作用域。
 */
const assistantChatId = computed(() => activeChat.value?.id ?? null)

/**
 * 计算角色头像URL
 *
 * 根据选中角色的头像字段生成头像URL。
 */
const characterAvatarUrl = computed(() => {
  if (!selectedCharacter.value?.avatar) return null
  return `/api/avatars/${selectedCharacter.value.avatar}`
})

/**
 * 计算用户头像URL
 *
 * 根据选中身份的头像字段生成头像URL。
 */
const userAvatarUrl = computed(() => {
  if (!selectedPersona.value?.avatar) return null
  return `/api/avatars/${selectedPersona.value.avatar}`
})

/**
 * 计算用户名称
 *
 * 返回选中身份的名称，如果没有则返回"你"。
 */
const userName = computed(() => {
  return selectedPersona.value?.name || '你'
})

function normalizeTtsSessionConfig(source?: TtsSessionConfig | null): TtsSessionConfig {
  return {
    autoReadScope: source?.autoReadScope ?? 'off',
    readGapSeconds: typeof source?.readGapSeconds === 'number' && Number.isFinite(source.readGapSeconds)
      ? Math.max(0, source.readGapSeconds)
      : 0,
    model: source?.model?.trim() || null,
    voiceByCharacterId: { ...(source?.voiceByCharacterId || {}) },
    voiceByPersonaId: { ...(source?.voiceByPersonaId || {}) },
    presetId: source?.presetId?.trim() || null,
    preprocessEnabled: source?.preprocessEnabled === true,
    preprocessModel: source?.preprocessModel?.trim() || null,
    preprocessPresetId: source?.preprocessPresetId?.trim() || null,
    preprocessTargetLanguage: source?.preprocessTargetLanguage?.trim() || null,
    injectEmotionTags: source?.injectEmotionTags === true,
  }
}

function getTtsPresets(): ApiPreset[] {
  return (settings.settings?.apiPresets || []).filter((preset) => isTtsApiPreset(preset))
}

function resolveTtsPreset(tts: TtsSessionConfig): ApiPreset | null {
  if (tts.presetId) {
    const matched = getTtsPresets().find((preset) => preset.id === tts.presetId)
    if (matched) return matched
  }
  return getTtsPresets()[0] || null
}

function resolveTtsModel(tts: TtsSessionConfig, preset: ApiPreset | null): string {
  if (tts.model?.trim()) return tts.model.trim()
  if (preset?.models?.[0]?.trim()) return preset.models[0]!.trim()
  const provider = resolveTtsProvider(preset)
  if (provider === 'glm' || provider === 'glm_local') return 'glm-tts'
  if (provider === 'qwen3_local') return 'qwen3-tts'
  if (provider === 'omnivoice_local') return 'omnivoice-tts'
  if (provider === 'openrouter') return 'google/gemini-3.1-flash-tts-preview'
  if (provider === 'siliconflow') return 'FunAudioLLM/CosyVoice2-0.5B'
  return 'speech-2.8-hd'
}

function resolveTtsVoiceId(message: ChatMessage, tts: TtsSessionConfig): string | null {
  if (message.role === 'assistant') {
    const characterId = message.characterId || activeChat.value?.characterId || null
    return characterId ? tts.voiceByCharacterId?.[characterId]?.trim() || null : null
  }
  if (message.role === 'user') {
    const personaId = message.senderPersonaId || activeChat.value?.userPersonaId || selectedPersona.value?.id || null
    return personaId ? tts.voiceByPersonaId?.[personaId]?.trim() || null : null
  }
  return null
}

function rememberTtsAsset(messageId: string, assetId: string, spokenText: string, contentFingerprint?: string) {
  const message = activeChat.value?.messages.find((item) => item.id === messageId)
  if (message) {
    message.ttsAudioAssetId = assetId
    message.ttsAudioSourceText = spokenText
  }
  // 若使用 local_ id 合成，将结果存入 pending 等待 load 后补绑到服务端消息
  if (contentFingerprint && messageId.startsWith('local_')) {
    pendingTtsBinds.set(contentFingerprint, { assetId, spokenText })
  }
  // 合成完成往往晚于 chats.load 触发的 flushPendingTtsBinds，需在 pending 写入后立即再尝试补绑
  void flushPendingTtsBinds()
  // TTS 成功绑定到当前会话即视为会话更新（含新合成与缓存复用后的落库）
  if (message || (contentFingerprint && messageId.startsWith('local_'))) {
    bumpSidebarForActiveChat()
  }
}

function clearTtsAsset(message?: ChatMessage | null) {
  if (!message) return
  message.ttsAudioAssetId = null
  message.ttsAudioSourceText = null
}

/** 与合成/存档比对时统一换行与 Unicode，避免仅空白差异导致重复请求 */
function normalizeTtsCompareText(s: string): string {
  return s.replace(/\r\n/g, '\n').replace(/\r/g, '\n').trim().normalize('NFKC')
}

function invalidateTtsCacheIfTextChanged(
  message: ChatMessage | null | undefined,
  previousText: string,
  nextText: string,
) {
  if (!message) return
  if (normalizeTtsCompareText(previousText) === normalizeTtsCompareText(nextText)) return
  clearTtsAsset(message)
}

/**
 * 复用音频：用持久化的 message.content 与当前展示原文比对（不另存规范化副本）。
 * ttsAudioSourceText 为朗读稿（可含翻译），不参与此比较；旧存档曾把原文误存进 source 时走兼容分支。
 */
function canReuseTtsCache(message: ChatMessage, originalText: string): boolean {
  const assetId = message.ttsAudioAssetId?.trim()
  if (!assetId) return false
  const currentContent = normalizeTtsCompareText(originalText)
  if (normalizeTtsCompareText(message.content || '') === currentContent) return true
  const rawCached = message.ttsAudioSourceText
  const hasStoredSource =
    rawCached != null && String(rawCached).replace(/\s+/g, '').length > 0
  if (hasStoredSource) {
    return normalizeTtsCompareText(String(rawCached)) === currentContent
  }
  // 兼容旧缓存：历史记录可能只写入了 assetId；消息内容变更时会主动清空缓存字段，因此仍保留的 assetId 可直接复用。
  return originalText.trim().length > 0
}

async function preprocessMessageForTts(text: string, tts: TtsSessionConfig): Promise<string> {
  const raw = text.trim()
  if (!raw || !tts.preprocessEnabled || !tts.preprocessModel?.trim()) return raw
  const preset = resolveTtsPreset(tts)
  const response = await apiPost<{ processedText: string }>('/api/tts/preprocess', {
    text: raw,
    model: tts.preprocessModel,
    preset_id: tts.preprocessPresetId ?? null,
    provider: resolveTtsProvider(preset),
    inject_emotion_tags: tts.injectEmotionTags === true,
    target_language: tts.preprocessTargetLanguage?.trim() || null,
  })
  return response.processedText?.trim() || raw
}

async function enqueueMessageReadAloud(message: ChatMessage, mode: 'manual' | 'auto' = 'manual') {
  const chat = activeChat.value
  if (!chat) return false
  const live = chat.messages.find((item) => item.id === message.id) ?? message
  if (!settings.settings?.ttsEnabled) {
    if (mode === 'manual') await notifyMessage('请先在全局设置里开启 TTS。')
    return false
  }
  if (live.role !== 'assistant' && live.role !== 'user') return false

  const tts = normalizeTtsSessionConfig(chat.overrides?.tts)
  const preset = resolveTtsPreset(tts)
  const voiceId = resolveTtsVoiceId(live, tts)
  if (!voiceId) {
    if (mode === 'manual') {
      await notifyMessage(live.role === 'assistant' ? '当前角色未配置音色。' : '当前用户身份未配置音色。')
    }
    return false
  }

  const originalText = versions.getDisplayContent(live).trim()
  if (!originalText) {
    if (mode === 'manual') await notifyMessage('当前消息没有可朗读的文本。')
    return false
  }

  /** 手动：同一条消息已在队列中则忽略重复点击（done/aborted 已出队后可再点） */
  if (mode === 'manual') {
    const alreadyQueued = ttsQueue.queue.value.some(
      (i) => i.messageId === live.id && i.status !== 'done' && i.status !== 'aborted',
    )
    if (alreadyQueued) return false
    if (manualTtsReadInFlight.has(live.id)) return false
    manualTtsReadInFlight.add(live.id)
  }

  try {
    /** 在任意 await 之前登记，避免 flush 入队尚未完成时 chats.load 触发 runAutoRead 重复入队 */
    let autoReadFingerprint: string | null = null
    if (mode === 'auto') {
      const fp = makeTtsAutoReadContentFingerprint(chat.id, live, originalText)
      const fpSet = getTtsAutoReadFingerprintSet(chat.id)
      if (fpSet.has(fp)) return false
      fpSet.add(fp)
      autoReadFingerprint = fp
    }

    const chars = [...originalText]
    const previewLabel =
      chars.length > 8 ? `${chars.slice(0, 8).join('')}...` : chars.join('')

    const existingAssetId = canReuseTtsCache(live, originalText)
      ? (live.ttsAudioAssetId?.trim() ?? undefined)
      : undefined

    if (existingAssetId) {
      await ttsQueue.enqueue(live.id, originalText, voiceId, {
        previewLabel,
        model: resolveTtsModel(tts, preset),
        existingAssetId,
        chatId: chat.id,
        presetId: preset?.id ?? tts.presetId ?? null,
        gapSeconds: tts.readGapSeconds ?? 0,
        enqueueMode: mode === 'manual' ? 'manual' : 'auto',
        manualPlacement: mode === 'manual' ? 'cachedJump' : 'tail',
      })
      return true
    }

    const needsPreprocess =
      originalText.trim().length > 0 &&
      tts.preprocessEnabled === true &&
      !!tts.preprocessModel?.trim()

    let spokenText = originalText
    if (needsPreprocess) {
      ttsQueue.beginPreprocessing(live.id, previewLabel)
    }
    try {
      spokenText = await preprocessMessageForTts(originalText, tts)
    } catch (error) {
      errorStack.pushError({
        message: `${formatApiError(error)}（已回退为原始文本）`,
        source: 'main',
        title: 'TTS 文本后处理失败',
      })
    } finally {
      if (needsPreprocess) {
        ttsQueue.endPreprocessing(live.id)
      }
    }

    await ttsQueue.enqueue(live.id, spokenText, voiceId, {
      previewLabel,
      model: resolveTtsModel(tts, preset),
      existingAssetId,
      chatId: chat.id,
      contentText: originalText,
      presetId: preset?.id ?? tts.presetId ?? null,
      gapSeconds: tts.readGapSeconds ?? 0,
      enqueueMode: mode === 'manual' ? 'manual' : 'auto',
      manualPlacement: mode === 'manual' ? 'second' : 'tail',
      onReady: (assetId) => rememberTtsAsset(live.id, assetId, spokenText, autoReadFingerprint ?? undefined),
      onSynthesizeError: (e) => {
        if (autoReadFingerprint) {
          getTtsAutoReadFingerprintSet(chat.id).delete(autoReadFingerprint)
        }
        errorStack.pushError({
          message: formatApiError(e),
          source: 'main',
          title: 'TTS 合成失败',
        })
      },
    })
    return true
  } finally {
    if (mode === 'manual') manualTtsReadInFlight.delete(live.id)
  }
}

async function handleReadAloudMessage(message: ChatMessage) {
  await enqueueMessageReadAloud(message, 'manual')
}

/**
 * 根据「已见过的消息 id」增量处理自动朗读；在服务端 reload 后由 flush 显式调用，避免仅依赖 watch 时漏触发。
 */
async function runAutoReadTtsForNewMessages() {
  const chat = activeChat.value
  if (!chat) return
  if (observedTtsChatId !== chat.id) {
    observedTtsChatId = chat.id
    observedTtsMessageIds = new Set(chat.messages.map((message) => message.id))
    return
  }

  const tts = normalizeTtsSessionConfig(chat.overrides?.tts)
  const newMessages = chat.messages.filter((message) => !observedTtsMessageIds.has(message.id))
  for (const message of newMessages) observedTtsMessageIds.add(message.id)

  if (!settings.settings?.ttsEnabled || tts.autoReadScope === 'off' || newMessages.length === 0) return

  for (const message of newMessages) {
    const displayText =
      message.role === 'assistant' ? versions.getDisplayContent(message) : message.content || ''
    if (
      getTtsAutoReadFingerprintSet(chat.id).has(
        makeTtsAutoReadContentFingerprint(chat.id, message, displayText),
      )
    )
      continue
    if (message.id.startsWith('local_')) continue
    if (tts.autoReadScope === 'assistant_only' && message.role !== 'assistant') continue
    if (tts.autoReadScope === 'user_only' && message.role !== 'user') continue
    if (tts.autoReadScope === 'all' && message.role !== 'assistant' && message.role !== 'user') continue
    await enqueueMessageReadAloud(message, 'auto')
  }
}

async function flushAutoReadTtsAfterChatReload() {
  await nextTick()
  // 补绑阶段：chats.load 已完成，消息 id 为服务端 UUID，将 pending 合成结果写回
  await flushPendingTtsBinds()
  await runAutoReadTtsForNewMessages()
}

/** 自动记忆总结：防抖调度（在 useAssistant 初始化后赋值） */
let scheduleMaybeTriggerAutoMemorySummary: (chatId: string) => void = () => {}
const autoMemorySummaryInFlight = ref(false)
let memSummaryDebounceTimer: ReturnType<typeof setTimeout> | null = null

async function afterChatReload(chatId: string) {
  await flushAutoReadTtsAfterChatReload()
  scheduleMaybeTriggerAutoMemorySummary(chatId)
}

/** 遍历 pendingTtsBinds，按内容指纹匹配当前消息并调用 bind-message 写回 TTS 字段 */
async function flushPendingTtsBinds() {
  const chat = activeChat.value
  if (!chat || pendingTtsBinds.size === 0) return

  for (const message of chat.messages) {
    if (message.id.startsWith('local_')) continue
    const displayText = message.role === 'assistant' ? versions.getDisplayContent(message) : message.content || ''
    const fp = makeTtsAutoReadContentFingerprint(chat.id, message, displayText)
    const pending = pendingTtsBinds.get(fp)
    if (!pending) continue

    // 内存立即更新
    message.ttsAudioAssetId = pending.assetId
    message.ttsAudioSourceText = pending.spokenText
    pendingTtsBinds.delete(fp)

    // 异步写回磁盘，不阻塞后续
    apiPost('/api/tts/bind-message', {
      chat_id: chat.id,
      message_id: message.id,
      asset_id: pending.assetId,
      spoken_text: pending.spokenText,
    }).catch((e) => {
      console.warn('[TTS] bind-message failed', e)
    })
  }
}

watch(
  () => activeChat.value?.id,
  () => {
    observedTtsChatId = activeChat.value?.id ?? null
    observedTtsMessageIds = new Set((activeChat.value?.messages || []).map((message) => message.id))
  },
  { immediate: true },
)

watch(
  () => activeChat.value?.messages?.map((message) => message.id).join('|') ?? '',
  () => {
    void runAutoReadTtsForNewMessages()
  },
)

// ========== 初始化 Composables ==========
// 流式输出
const stream = useStreamOutput(
  { appendLocalMessageContent: chats.appendLocalMessageContent },
  () => scrollToBottom(true, true),
)

// 消息版本
const versions = useMessageVersions()

/** 用户消息落库后立即尝试自动朗读（无「输出完成」事件） */
async function tryAutoReadUserMessage(localUserId: string) {
  const chat = activeChat.value
  if (!chat) return
  if (!settings.settings?.ttsEnabled) return
  const tts = normalizeTtsSessionConfig(chat.overrides?.tts)
  if (tts.autoReadScope === 'off') return
  if (tts.autoReadScope !== 'user_only' && tts.autoReadScope !== 'all') return
  await nextTick()
  const msg = chat.messages.find((m) => m.id === localUserId)
  if (!msg || msg.role !== 'user') return
  void enqueueMessageReadAloud(msg, 'auto')
}

/** 单个角色流式/非流式输出结束（flush 后内容已写入 store）时尝试自动朗读 */
async function tryAutoReadAssistantAfterStreamFlush(localAssistantId: string) {
  const chat = activeChat.value
  if (!chat) return
  if (!settings.settings?.ttsEnabled) return
  const tts = normalizeTtsSessionConfig(chat.overrides?.tts)
  if (tts.autoReadScope === 'off') return
  if (tts.autoReadScope !== 'assistant_only' && tts.autoReadScope !== 'all') return
  await nextTick()
  const msg = chat.messages.find((m) => m.id === localAssistantId)
  if (!msg || msg.role !== 'assistant') return
  if (!versions.getDisplayContent(msg).trim()) return
  void enqueueMessageReadAloud(msg, 'auto')
}

// 群聊逻辑
const group = useGroupChat({
  activeChat,
  isGenerating,
  settings: settings as any,
})

/** 是否启用流式传输（与全局设置一致），供助手与生成共用 */
const isStreamEnabled = computed(() => settings.settings?.streamEnabled !== false)

// MVU Store
const mvuStore = useMvuStore()
const mvuPanelOpen = ref(false)
const knowledgeGraphModalOpen = ref(false)

function openKnowledgeGraphModal() {
  knowledgeGraphModalOpen.value = true
}
/** 与后端 mvu_model_resolve 一致：全局 mvuModel → 默认模型 → 候选首项 */
const mvuResolvedModelForPanel = computed(() => {
  const s = settings.settings
  if (!s) return null
  const explicit = (s.mvuModel || '').trim()
  if (explicit) return explicit
  const def = (s.llm.defaultModel || '').trim()
  if (def) return def
  for (const c of s.llm.modelCandidates || []) {
    const t = (c || '').trim()
    if (t) return t
  }
  return null
})

async function onMvuPanelMvuModelSelect(payload: { value: string; presetId?: string | null }) {
  if (!settings.settings) {
    try {
      await settings.load()
    } catch {
      return
    }
  }
  if (!settings.settings) return
  try {
    await settings.save({
      ...settings.settings,
      mvuModel: payload.value?.trim() || null,
    })
  } catch (e) {
    console.error('Failed to save global MVU model:', e)
  }
}

// 版本切换延迟持久化：切换版本时仅更新内存，记录脏状态，在发送消息前统一落盘
const pendingGreetingVersion = ref<{
  chatId: string
  messageId: string
  role: string
  content: string
  characterId?: string | null
  greetingVariantIndex: number
  greetingVariants: string[]
  greetingVariantReasoningContents: string[]
  greetingVariantReasoningDurations: (number | null)[]
  reasoningContent: string | null
} | null>(null)

async function flushPendingGreetingVersion() {
  const p = pendingGreetingVersion.value
  if (!p) return
  pendingGreetingVersion.value = null
  try {
    await chats.updateMessage(p.chatId, p.messageId, p.role as MainChatRole, p.content, p.characterId, {
      greetingVariantIndex: p.greetingVariantIndex,
      greetingVariants: p.greetingVariants,
      greetingVariantReasoningContents: p.greetingVariantReasoningContents,
      greetingVariantReasoningDurations: p.greetingVariantReasoningDurations,
      reasoningContent: p.reasoningContent,
    })
  } catch (e) {
    console.error('Failed to persist greeting version:', e)
  }
}

function switchFromMvuToAssistantPanel() {
  mvuPanelOpen.value = false
  assistant.isAssistantPanelOpen.value = true
}

function switchFromAssistantToMvuPanel() {
  assistant.isAssistantPanelOpen.value = false
  mvuPanelOpen.value = true
}

// 聊天助手（助手写入长期记忆后通过 SSE 推送 chat_memory_updated，此处回调使当前会话状态立即刷新，无需切换窗口即可看到「当前会话」长期记忆与「已保存」标记）
const assistant = useAssistant({
  chatId: assistantChatId,
  streamEnabled: isStreamEnabled,
  onChatMemoryUpdated: (chat) => chats.applyChatPayload(chat),
  onChatOverridesUpdated: (p) => {
    const id = p.chatId
    if (id && id === chats.activeChatId) {
      void chats.load(id).then(async () => {
        await afterChatReload(id)
      })
    }
  },
})

async function maybeTriggerAutoMemorySummary(chatId: string) {
  if (chatId !== activeChat.value?.id) return
  if (isGenerating.value) return
  if (assistant.isAssistantGenerating.value) return
  if (autoMemorySummaryInFlight.value) return

  const chat = activeChat.value
  if (!chat) return

  const rawN = chat.overrides?.autoMemorySummaryEveryN
  const effectiveN =
    typeof rawN === 'number' && Number.isFinite(rawN) && rawN >= 1 ? Math.floor(rawN) : 0
  if (effectiveN < 1) return

  const silent = chat.overrides?.autoMemorySummarySilent === true
  let tier = chat.overrides?.autoMemorySummaryNextAskTier
  if (typeof tier !== 'number' || !Number.isFinite(tier) || tier < 1) tier = 1
  if (silent) tier = 1

  const anchorId = chat.overrides?.lastAutoMemorySummaryAfterMessageId ?? null
  const messages = chat.messages ?? []
  let anchorIdx = -1
  if (anchorId) {
    anchorIdx = messages.findIndex((m) => m.id === anchorId)
  }
  const count = anchorIdx >= 0 ? messages.length - anchorIdx - 1 : messages.length
  const threshold = effectiveN * tier

  if (count < threshold) return

  if (!silent) {
    const ok = await notifyConfirm({
      title: '自动总结长期记忆',
      message: '未总结消息已达阈值，是否现在让助手阅读近期对话并写入长期记忆？',
    })
    if (!ok) {
      await chats.updateOverrides(
        chatId,
        {
          ...chat.overrides,
          autoMemorySummaryNextAskTier: tier + 1,
        },
        { skipLoadList: true },
      )
      return
    }
  }

  const lastMsgId = messages[messages.length - 1]?.id
  if (!lastMsgId) return

  autoMemorySummaryInFlight.value = true
  try {
    const ok = await assistant.runAutoMemorySummaryPrompt()
    if (!ok) return
    const chatAfter = activeChat.value
    if (!chatAfter || chatAfter.id !== chatId) return
    await chats.updateOverrides(
      chatId,
      {
        ...chatAfter.overrides,
        lastAutoMemorySummaryAfterMessageId: lastMsgId,
        autoMemorySummaryNextAskTier: 1,
      },
      { skipLoadList: true },
    )
  } finally {
    autoMemorySummaryInFlight.value = false
  }
}

scheduleMaybeTriggerAutoMemorySummary = (chatId: string) => {
  if (memSummaryDebounceTimer) clearTimeout(memSummaryDebounceTimer)
  memSummaryDebounceTimer = setTimeout(() => {
    memSummaryDebounceTimer = null
    void maybeTriggerAutoMemorySummary(chatId)
  }, 80)
}

async function setAssistantWriteMemoryEnabled(checked: boolean) {
  await assistant.setAllowWriteMemory(checked)
}

async function setAssistantDestructiveToolsEnabled(checked: boolean) {
  await assistant.setAllowDestructiveTools(checked)
}

const imageFallbackDialog = ref<{
  visible: boolean
  error: string
  retryAction: null | (() => Promise<void>)
}>({
  visible: false,
  error: '',
  retryAction: null,
})

const draftHelper = ref<{
  mode: 'write' | 'enhance' | null
  status: 'reasoning' | 'writing' | 'done' | null
  sourceDraft: string
  lastGenerated: string
}>({
  mode: null,
  status: null,
  sourceDraft: '',
  lastGenerated: '',
})
const draftHelperAborter = ref<AbortController | null>(null)
const draftHelperStopRequested = ref(false)

type DraftHelpConversationMessage = Pick<ChatMessage, 'id' | 'role' | 'content' | 'characterId' | 'senderName'>

function buildDraftHelperConversation(): DraftHelpConversationMessage[] {
  const chat = activeChat.value
  if (!chat) return []
  return chat.messages.map((msg) => ({
    id: msg.id,
    role: msg.role,
    content: msg.role === 'assistant' ? versions.getDisplayContent(msg) : msg.content,
    characterId: msg.characterId ?? null,
    senderName: msg.senderName ?? null,
  }))
}

const showChatSearch = ref(false)
/** 关闭搜索栏时先跑完面板离场动画再显示「搜索」chip，避免与收起动画抢布局造成顿挫 */
const holdSearchChipUntilSearchPanelClosed = ref(false)
/** 顶栏搜索区向下拓展（grid 0fr→1fr） */
const chatSearchExpandOpen = ref(false)
/** 拓展占位完成后「带出」搜索 UI（opacity / translate） */
const chatSearchContentRevealed = ref(false)

const SEARCH_OPEN_EXPAND_MS = 320
const SEARCH_REVEAL_DELAY_MS = 500
const SEARCH_CLOSE_CONTENT_MS = 280
const SEARCH_EXPAND_COLLAPSE_MS = 320

let chatSearchOpenRevealTimer: ReturnType<typeof setTimeout> | null = null
let chatSearchCloseTimers: ReturnType<typeof setTimeout>[] = []

function prefersReducedMotion(): boolean {
  if (typeof window === 'undefined') return false
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

/** 仅清理搜索面板展开/收起与 reveal 的定时器，不碰 chip 状态（关闭动画需与 chip 同场） */
function clearChatSearchPanelAnimTimers() {
  if (chatSearchOpenRevealTimer != null) {
    clearTimeout(chatSearchOpenRevealTimer)
    chatSearchOpenRevealTimer = null
  }
  chatSearchCloseTimers.forEach(clearTimeout)
  chatSearchCloseTimers = []
}

/** 面板定时器 + chip 展开状态，用于切会话、卸载等完整重置 */
function clearChatSearchAnimTimers() {
  clearChatSearchPanelAnimTimers()
  clearChatSearchChipsExpandState()
}
const chatSearchQuery = ref('')
const chatSearchLoading = ref(false)
const chatSearchResults = ref<Array<{ messageId: string; messageIndex: number; snippet: string }>>([])
/** 当前高亮的搜索结果 chip；-1 表示未选中（搜索成功后不再默认选中首条） */
const chatSearchCursor = ref(-1)
/** chip 行：grid 展开；清空结果时先收起再延迟清 DOM，以便高度过渡 */
const chatSearchChipsGridOpen = ref(false)
const chatSearchChipsCollapsing = ref(false)
const chatSearchChipsDisplayHits = ref<Array<{ messageId: string; messageIndex: number; snippet: string }>>([])
let chatSearchChipsClearTimer: ReturnType<typeof setTimeout> | null = null

function clearChatSearchChipsExpandState() {
  if (chatSearchChipsClearTimer != null) {
    clearTimeout(chatSearchChipsClearTimer)
    chatSearchChipsClearTimer = null
  }
  chatSearchChipsDisplayHits.value = []
  chatSearchChipsGridOpen.value = false
  chatSearchChipsCollapsing.value = false
}

function syncChatSearchChipsRow(options?: { forceExpandAnimation?: boolean }) {
  const hits = chatSearchResults.value
  if (hits.length > 0) {
    if (chatSearchChipsClearTimer != null) {
      clearTimeout(chatSearchChipsClearTimer)
      chatSearchChipsClearTimer = null
    }
    chatSearchChipsCollapsing.value = false
    const wasEmpty = chatSearchChipsDisplayHits.value.length === 0
    chatSearchChipsDisplayHits.value = hits.map((h) => ({ ...h }))
    const shouldAnimateExpand =
      !prefersReducedMotion() && (options?.forceExpandAnimation === true || wasEmpty)
    if (shouldAnimateExpand) {
      chatSearchChipsGridOpen.value = false
      nextTick(() => {
        requestAnimationFrame(() => {
          requestAnimationFrame(() => {
            chatSearchChipsGridOpen.value = true
          })
        })
      })
    } else {
      chatSearchChipsGridOpen.value = true
    }
  } else {
    if (chatSearchChipsDisplayHits.value.length === 0) {
      chatSearchChipsGridOpen.value = false
      return
    }
    if (prefersReducedMotion()) {
      clearChatSearchChipsExpandState()
      return
    }
    chatSearchChipsCollapsing.value = true
    chatSearchChipsGridOpen.value = false
    if (chatSearchChipsClearTimer != null) {
      clearTimeout(chatSearchChipsClearTimer)
      chatSearchChipsClearTimer = null
    }
    chatSearchChipsClearTimer = setTimeout(() => {
      chatSearchChipsDisplayHits.value = []
      chatSearchChipsCollapsing.value = false
      chatSearchChipsClearTimer = null
    }, SEARCH_CLOSE_CONTENT_MS)
  }
}

const chatSearchHitsForNav = computed(() =>
  chatSearchResults.value.length > 0 ? chatSearchResults.value : chatSearchChipsDisplayHits.value
)

watch(chatSearchResults, () => syncChatSearchChipsRow(), { deep: true })

const chatSearchInputRef = ref<HTMLInputElement | null>(null)
const showHeaderMoreMenu = ref(false)
const headerMoreMenuRef = ref<HTMLElement | null>(null)
const headerMoreButtonRef = ref<HTMLElement | null>(null)
/** 固定顶栏实际高度（px），供消息列表滚动区顶部留白，使滚动条从顶栏下缘起算 */
const chatHeaderRef = ref<HTMLElement | null>(null)
const chatHeaderHeightPx = ref(72)
/** 顶栏下缘视口 y（px）+ 间距，助手 FAB 的 top 不得小于此值（顶栏展开变高时自动下移） */
const chatAssistantFabMinTopPx = ref(0)
let chatHeaderResizeObserver: ResizeObserver | null = null

const ASSISTANT_FAB_HEADER_GAP_PX = 8

watch(
  () => chatHeaderRef.value,
  (el) => {
    chatHeaderResizeObserver?.disconnect()
    chatHeaderResizeObserver = null
    if (!el) return
    const apply = () => {
      const rect = el.getBoundingClientRect()
      const h = rect.height
      if (h > 0) chatHeaderHeightPx.value = Math.round(h * 100) / 100
      chatAssistantFabMinTopPx.value = Math.round((rect.bottom + ASSISTANT_FAB_HEADER_GAP_PX) * 100) / 100
    }
    apply()
    chatHeaderResizeObserver = new ResizeObserver(() => {
      apply()
    })
    chatHeaderResizeObserver.observe(el)
  },
  { flush: 'post' }
)

/** 助手 FAB 与 TTS FAB 碰撞分离（useFabCollision 需在页面层调用两组件 getRect） */
const chatInputRef = ref<InstanceType<typeof ChatInput> | null>(null)
/** 主聊天网络搜索开关：为 true 时每次生成请求挂载搜索工具，直至用户关闭；需全局配置 Tavily/博查 API Key */
const webSearchSessionEnabled = ref(false)
const ttsPlaybackFabRef = ref<InstanceType<typeof TtsPlaybackFab> | null>(null)

/**
 * 重叠时只移动「被锚定」的一侧：拖动助手则只挪助手，拖动 TTS 则只挪 TTS；布局类事件（挂载、resize、顶栏）默认只挪 TTS。
 */
function runChatFabSeparation(anchor: 'assistant' | 'tts' | null = null) {
  if (!settings.settings?.ttsEnabled) return
  nextTick(() => {
    const a = chatInputRef.value?.getAssistantFabRect?.()
    const t = ttsPlaybackFabRef.value?.getRect?.()
    if (!a || !t) return
    if (!rectsOverlap(a, t, FAB_COLLISION_GAP_PX)) return
    const minTop = chatAssistantFabMinTopPx.value

    if (anchor === 'assistant') {
      const newTop = computeAssistantNonOverlapTop(t, a, minTop)
      if (Math.abs(newTop - a.top) < 0.5) return
      chatInputRef.value?.setAssistantTopPx?.(newTop)
      return
    }
    const newTop = computeTtsNonOverlapTop(a, t, minTop)
    if (Math.abs(newTop - t.top) < 0.5) return
    ttsPlaybackFabRef.value?.setTtsTopPx?.(newTop)
  })
}

watch(contentAreaLeftPx, () => {
  if (contentAreaLeftSepDebounce) clearTimeout(contentAreaLeftSepDebounce)
  contentAreaLeftSepDebounce = setTimeout(() => {
    contentAreaLeftSepDebounce = null
    runChatFabSeparation()
  }, 48)
})
watch(chatAssistantFabMinTopPx, () => runChatFabSeparation())
watch(
  () => settings.settings?.ttsEnabled,
  () => {
    nextTick(() => nextTick(runChatFabSeparation))
  },
)

/** TTS FAB：与输入栏下沉同相；顶栏 full 且 squeeze 结束后显示顶栏下替代控制条 */
const ttsInputSinkActive = computed(
  () =>
    sidebarCollapsed.value &&
    (headerMorphPhase.value === 'lifting' || headerMorphPhase.value === 'full')
)

const ttsTopBarControlsVisible = ref(false)
let ttsTopBarRevealTimer: ReturnType<typeof setTimeout> | null = null

function clearTtsTopBarRevealTimer() {
  if (ttsTopBarRevealTimer != null) {
    clearTimeout(ttsTopBarRevealTimer)
    ttsTopBarRevealTimer = null
  }
}

watch(
  () => [sidebarCollapsed.value, headerMorphPhase.value, settings.settings?.ttsEnabled] as const,
  () => {
    clearTtsTopBarRevealTimer()
    if (!sidebarCollapsed.value || !settings.settings?.ttsEnabled) {
      ttsTopBarControlsVisible.value = false
      return
    }
    if (headerMorphPhase.value === 'full') {
      ttsTopBarRevealTimer = setTimeout(() => {
        ttsTopBarControlsVisible.value = true
        ttsTopBarRevealTimer = null
      }, HEADER_SQUEEZE_MS + 40)
    } else {
      ttsTopBarControlsVisible.value = false
    }
  },
  { flush: 'post' },
)

const agentTopBarControlsVisible = ref(false)
let agentTopBarRevealTimer: ReturnType<typeof setTimeout> | null = null

function clearAgentTopBarRevealTimer() {
  if (agentTopBarRevealTimer != null) {
    clearTimeout(agentTopBarRevealTimer)
    agentTopBarRevealTimer = null
  }
}

watch(
  () => [sidebarCollapsed.value, headerMorphPhase.value] as const,
  () => {
    clearAgentTopBarRevealTimer()
    if (!sidebarCollapsed.value) {
      agentTopBarControlsVisible.value = false
      return
    }
    if (headerMorphPhase.value === 'full') {
      agentTopBarRevealTimer = setTimeout(() => {
        agentTopBarControlsVisible.value = true
        agentTopBarRevealTimer = null
      }, HEADER_SQUEEZE_MS + 40)
    } else {
      agentTopBarControlsVisible.value = false
    }
  },
  { flush: 'post' },
)

watch(streamError, (value) => {
  if (!value) return
  errorStack.pushError({ message: value, source: 'main', title: '主聊天错误' })
  streamError.value = null
})

watch(
  () => assistant.assistantStreamError.value,
  (value) => {
    if (!value) return
    errorStack.pushError({ message: value, source: 'assistant', title: '助手错误' })
    assistant.assistantStreamError.value = null
  }
)

watch(
  () => assistant.workspaceAssistantStreamError.value,
  (value) => {
    if (!value) return
    errorStack.pushError({ message: value, source: 'assistant', title: '工作区助手错误' })
    assistant.workspaceAssistantStreamError.value = null
  }
)

onBeforeUnmount(() => {
  clearMessageListEnterAnimations()
  draftHelperAborter.value?.abort()
  clearDraftImages()
  errorStack.clearAll()
  window.removeEventListener('keydown', handleGlobalKeydown)
  window.removeEventListener('pointerdown', handleHeaderPointerdown)
  if (chatSearchTimer) clearTimeout(chatSearchTimer)
  if (headerCompactDelayTimer) clearTimeout(headerCompactDelayTimer)
  if (headerLiftChainTimer) clearTimeout(headerLiftChainTimer)
  clearTtsTopBarRevealTimer()
  clearAgentTopBarRevealTimer()
  clearChatSearchChipsExpandState()
  chatHeaderResizeObserver?.disconnect()
  chatHeaderResizeObserver = null
})

/**
 * 获取用户身份信息
 *
 * 根据身份ID从设置中的身份列表查找身份。
 *
 * @param {string | null | undefined} id - 身份ID
 * @returns {UserPersona | null} 身份信息，如果未找到或ID为空则返回null
 */
function getPersonaById(id: string | null | undefined) {
  if (!id || !settings.settings?.userPersonas) return null
  return settings.settings.userPersonas.find(p => p.id === id) ?? null
}

function replaceInputPlaceholders(raw: string): string {
  const user = userName.value || '用户'
  const char = selectedCharacter.value?.name || '角色'
  return raw.replace(/\{\{user\}\}/g, user).replace(/\{\{char\}\}/g, char)
}

async function fileToDataUrl(file: File): Promise<string> {
  return await new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result || ''))
    reader.onerror = () => reject(reader.error || new Error('read file failed'))
    reader.readAsDataURL(file)
  })
}

async function uploadDraftImages(chatId: string, images: DraftImageItem[]): Promise<ChatImageAttachment[]> {
  if (!images.length) return []
  const payloadImages = await Promise.all(images.map(async (img) => ({
    imageData: await fileToDataUrl(img.file),
    mimeType: img.file.type || 'image/png',
    originalName: img.name,
  })))
  const res = await apiPost<{ images: ChatImageAttachment[] }>(`/api/chats/${chatId}/images`, { images: payloadImages })
  return res.images || []
}

function getAssistantAttachmentLabel(attachment: AssistantAttachment): string {
  return attachment.originalName || attachment.filename
}

function getAssistantAttachmentExt(attachment: AssistantAttachment): string {
  const label = getAssistantAttachmentLabel(attachment)
  const index = label.lastIndexOf('.')
  if (index < 0) return attachment.kind === 'text' ? 'txt' : 'img'
  return label.slice(index + 1).toLowerCase() || (attachment.kind === 'text' ? 'txt' : 'img')
}

function buildAssistantAttachmentUrl(scope: 'chat' | 'workspace', attachment: AssistantAttachment): string {
  const params = new URLSearchParams({ scope })
  if (scope === 'chat' && activeChat.value?.id) {
    params.set('chatId', activeChat.value.id)
  }
  params.set('storageScope', attachment.storageScope)
  params.set('storageKey', attachment.storageKey)
  params.set('filename', attachment.filename)
  params.set('mimeType', attachment.mimeType)
  params.set('kind', attachment.kind)
  return `/api/assistant/attachments/${encodeURIComponent(attachment.id)}?${params.toString()}`
}

async function notifyAssistantAttachmentRejections(
  rejected: Array<{ file: File; reason: 'unsupported' | 'too-large'; kind?: 'image' | 'text' | null }>,
) {
  const tooLargeImages = rejected.filter((item) => item.reason === 'too-large' && item.kind === 'image').length
  const tooLargeTexts = rejected.filter((item) => item.reason === 'too-large' && item.kind === 'text').length
  if (!tooLargeImages && !tooLargeTexts) return
  const parts: string[] = []
  if (tooLargeTexts) parts.push(`文本附件单文件不能超过 2MB（已拒绝 ${tooLargeTexts} 个）`)
  if (tooLargeImages) parts.push(`图片附件单文件不能超过 100MB（已拒绝 ${tooLargeImages} 个）`)
  await notifyMessage(parts.join('；'), { title: '附件过大' })
}

async function handleAssistantDraftFiles(scope: 'chat' | 'workspace', files: File[]) {
  if (!files.length) return
  const { accepted, rejected } = validateFilesForTarget(files, 'assistant')
  await notifyAssistantAttachmentRejections(rejected)
  if (!accepted.length) return
  try {
    await assistant.ingestDraftFiles(scope, accepted.map((item) => item.file))
  } catch (error) {
    await notifyMessage(error instanceof Error ? error.message : '附件导入失败', { title: '附件导入失败' })
  }
}

function insertWorkspaceAssistantTextAtCursor(text: string) {
  const el = workspaceAssistantTextareaRef.value
  if (!el) {
    assistant.workspaceAssistantDraft.value += text
    return
  }
  const start = el.selectionStart
  const end = el.selectionEnd
  const current = assistant.workspaceAssistantDraft.value
  assistant.workspaceAssistantDraft.value = current.slice(0, start) + text + current.slice(end)
  nextTick(() => {
    const pos = start + text.length
    el.setSelectionRange(pos, pos)
    el.focus()
  })
}

async function handleWorkspaceAssistantPaste(event: ClipboardEvent) {
  const resolved = await resolveRichPaste(event.clipboardData)
  if (!resolved) return
  if (resolved.files.length > 0 || resolved.text) {
    event.preventDefault()
  }
  if (resolved.files.length > 0) {
    await handleAssistantDraftFiles('workspace', resolved.files)
  }
  if (resolved.text) {
    insertWorkspaceAssistantTextAtCursor(resolved.text)
  }
}

function handleWorkspaceAssistantDragEnter(event: DragEvent) {
  if (!event.dataTransfer?.types.includes('Files')) return
  isWorkspaceAssistantDragOver.value = true
}

function handleWorkspaceAssistantDragLeave(event: DragEvent) {
  const nextTarget = event.relatedTarget as Node | null
  if (nextTarget && (event.currentTarget as HTMLElement | null)?.contains(nextTarget)) return
  isWorkspaceAssistantDragOver.value = false
}

function handleWorkspaceAssistantDragOver(event: DragEvent) {
  if (!event.dataTransfer?.types.includes('Files')) return
  event.preventDefault()
  isWorkspaceAssistantDragOver.value = true
}

async function handleWorkspaceAssistantDrop(event: DragEvent) {
  const files = Array.from(event.dataTransfer?.files || [])
  isWorkspaceAssistantDragOver.value = false
  if (!files.length) return
  event.preventDefault()
  await handleAssistantDraftFiles('workspace', files)
}

function clearDraftImages() {
  for (const img of draftImages.value) {
    URL.revokeObjectURL(img.previewUrl)
  }
  draftImages.value = []
}

function openImageFallback(error: string, retryAction: () => Promise<void>) {
  imageFallbackDialog.value = { visible: true, error, retryAction }
}

async function runDraftHelper(mode: 'write' | 'enhance', sourceDraft: string) {
  if (!activeChat.value) return
  if (isGenerating.value) return
  draftHelperAborter.value?.abort()
  const controller = new AbortController()
  draftHelperAborter.value = controller
  draftHelperStopRequested.value = false
  draftHelper.value.mode = mode
  draftHelper.value.status = 'reasoning'
  draftHelper.value.sourceDraft = sourceDraft
  draftHelper.value.lastGenerated = ''
  draftMessage.value = ''
  const conversation = buildDraftHelperConversation()

  const useStream = settings.settings?.streamEnabled !== false
  try {
    if (useStream) {
      let gotDelta = false
      let sseError: string | null = null
      await postAndConsumeSse('/api/generate/draft-help', {
        chatId: activeChat.value.id,
        mode,
        draft: mode === 'enhance' ? sourceDraft : null,
        conversation,
      }, (evt) => {
        if (evt.event === 'reasoning') {
          draftHelper.value.status = 'reasoning'
        } else if (evt.event === 'delta') {
          const data = evt.data as { text?: string } | undefined
          const t = data?.text
          if (typeof t === 'string') {
            if (!gotDelta) {
              draftHelper.value.status = 'writing'
              gotDelta = true
            }
            draftMessage.value += t
            draftHelper.value.lastGenerated = draftMessage.value
          }
        } else if (evt.event === 'done') {
          draftHelper.value.status = 'done'
        } else if (evt.event === 'error') {
          const data = evt.data as { message?: string } | undefined
          sseError = String(data?.message ?? 'unknown error')
        }
      }, controller.signal)
      if (sseError) {
        draftHelper.value.status = null
        throw new Error(sseError)
      }
      return
    }

    const res = await apiPost<{ ok: boolean; content: string; reasoningContent?: string; error?: string }>('/api/generate/draft-help', {
      chatId: activeChat.value.id,
      mode,
      draft: mode === 'enhance' ? sourceDraft : null,
      conversation,
    }, controller.signal)
    if (!res.ok) {
      draftHelper.value.status = null
      throw new Error(res.error || 'unknown error')
    }
    if (typeof res.reasoningContent === 'string' && res.reasoningContent.trim()) {
      draftHelper.value.status = 'reasoning'
    }
    draftMessage.value = res.content || ''
    draftHelper.value.lastGenerated = draftMessage.value
    draftHelper.value.status = 'done'
  } catch (e) {
    if (isAbortError(e) && draftHelperStopRequested.value) {
      draftHelper.value.status = null
      draftHelper.value.lastGenerated = draftMessage.value
      return
    }
    // 非用户终止的失败（如 HTTP 400）：复位 UI，避免状态栏卡在「思考中」且终止无效（aborter 已在 finally 清空）
    if (draftHelperAborter.value === controller) {
      draftHelper.value.status = null
      draftHelper.value.mode = null
      draftHelper.value.lastGenerated = ''
    }
    throw e
  } finally {
    if (draftHelperAborter.value === controller) {
      draftHelperAborter.value = null
    }
    draftHelperStopRequested.value = false
  }
}

async function handleOpenDraftHelper(mode: 'write' | 'enhance') {
  if (mode === 'enhance' && !draftMessage.value.trim()) {
    streamError.value = '润色前请先输入草稿内容'
    return
  }
  try {
    const sourceDraft = draftMessage.value
    await runDraftHelper(mode, sourceDraft)
  } catch (e: any) {
    if (mode === 'enhance') {
      // 润色失败时恢复原草稿，避免用户内容意外丢失
      draftMessage.value = draftHelper.value.sourceDraft
    }
    streamError.value = e?.message ?? String(e)
  }
}

async function handleDraftHelperRewrite() {
  if (!draftHelper.value.mode) return
  try {
    await runDraftHelper(draftHelper.value.mode, draftHelper.value.sourceDraft)
  } catch (e: any) {
    streamError.value = e?.message ?? String(e)
  }
}

function handleDraftHelperKeep() {
  draftHelper.value.status = null
}

function handleDraftHelperStop() {
  if (!draftHelperAborter.value) return
  draftHelperStopRequested.value = true
  draftHelperAborter.value.abort()
}

function handleDraftHelperDiscard() {
  if (draftHelper.value.mode === 'enhance') {
    draftMessage.value = draftHelper.value.sourceDraft
  } else {
    draftMessage.value = ''
  }
  draftHelper.value.status = null
  draftHelper.value.mode = null
  draftHelper.value.sourceDraft = ''
  draftHelper.value.lastGenerated = ''
}

/**
 * 从聊天中获取最后一个用户消息的身份ID
 *
 * 遍历聊天消息，找到最后一个用户消息的身份ID（用于身份切换时保持历史消息显示）。
 *
 * @param {Chat | null | undefined} chat - 聊天会话（来自types/models.ts）
 * @returns {string | null} 身份ID，如果未找到则返回null
 */
function getLastUserPersonaIdFromChat(chat: Chat | null | undefined) {
  if (!chat?.messages?.length) return null
  for (let i = chat.messages.length - 1; i >= 0; i--) {
    const m = chat.messages[i]
    if (m?.role === 'user' && m.senderPersonaId) return m.senderPersonaId
  }
  return null
}

/**
 * 计算有效的选中身份ID
 *
 * 优先使用聊天会话的身份ID，其次使用聊天中最后一个用户消息的身份ID，
 * 再次使用全局设置中的选中身份ID。如果为纯AI模式则返回null。
 */
const effectiveSelectedPersonaId = computed(() => {
  if (group.effectivePureAiMode.value) return null
  const chat = activeChat.value
  return chat?.userPersonaId
    ?? getLastUserPersonaIdFromChat(chat)
    ?? settings.settings?.selectedPersonaId
    ?? null
})

/**
 * 计算选中的身份
 *
 * 根据effectiveSelectedPersonaId获取身份信息。
 */
const selectedPersona = computed(() => {
  return getPersonaById(effectiveSelectedPersonaId.value)
})

// 聊天操作
const actions = useChatActions({
  activeChat,
  isGenerating,
  selectedPersona,
  userName,
  selectedCharacterId,
  chatsStore: chats as any,
  settingsStore: settings as any,
  charactersStore: characters as any,
})

/** 角色编辑弹窗：绑定世界书（attachedWorldBookIds），供「角色+世界书」ZIP 等使用 */
const characterEditorWorldbooks = ref<WorldBook[]>([])
const addCharacterEditorWbId = ref('')
const characterEditorWbDraggingIdx = ref<number | null>(null)
/** 角色编辑：额外首句草稿（对号/加号写入列表，底部保存才持久化） */
const extraFirstMessageDraft = ref('')

/** 全部额外首句条目（含 chip:false 与空文本），便于删除错误数据 */
const extraFirstMessageEntriesIndexed = computed(() => {
  const ec = actions.editingCharacter.value
  if (!ec?.extraFirstMessageEntries?.length) return [] as Array<ExtraFirstMessageEntry & { index: number }>
  return ec.extraFirstMessageEntries.map((e, index) => ({ ...e, index }))
})

const hasAnyExtraFirstEntries = computed(() => extraFirstMessageEntriesIndexed.value.length > 0)

function displayExtraEntryLabel(entry: ExtraFirstMessageEntry): string {
  const t = (entry.text ?? '').trim()
  return t || '（空）'
}

function extraEntryIsEmpty(entry: ExtraFirstMessageEntry): boolean {
  return !(entry.text ?? '').trim()
}

function appendExtraFirstMessageCheck() {
  const ec = actions.editingCharacter.value
  if (!ec) return
  const t = extraFirstMessageDraft.value.trim()
  if (!t) return
  if (!Array.isArray(ec.extraFirstMessageEntries)) ec.extraFirstMessageEntries = []
  ec.extraFirstMessageEntries.push({ text: t, chip: false })
}

function appendExtraFirstMessagePlus() {
  const ec = actions.editingCharacter.value
  if (!ec) return
  const t = extraFirstMessageDraft.value.trim()
  if (!t) return
  if (!Array.isArray(ec.extraFirstMessageEntries)) ec.extraFirstMessageEntries = []
  ec.extraFirstMessageEntries.push({ text: t, chip: true })
  extraFirstMessageDraft.value = ''
}

function removeExtraFirstMessageAt(index: number) {
  const ec = actions.editingCharacter.value
  if (!ec?.extraFirstMessageEntries) return
  ec.extraFirstMessageEntries.splice(index, 1)
}

function fillExtraFirstDraft(text: string) {
  extraFirstMessageDraft.value = text
}

function clearEmbeddedCardPreviewState() {
  showEmbeddedCardConfirmModal.value = false
  embeddedCardPreview.value = null
  embeddedCardImporting.value = false
  resetAvatarEmbeddedStState()
}

function avatarObjectPositionByFocus(focusX?: number | null, focusY?: number | null): string {
  const x = typeof focusX === 'number' ? focusX : 50
  const y = typeof focusY === 'number' ? focusY : 50
  return `${x}% ${y}%`
}

async function handleCharacterAvatarSave(payload: AvatarCropSavePayload) {
  resetAvatarEmbeddedStState()
  const embedded = await actions.handleCharacterAvatarSave(payload.imageData, payload.focusX ?? null, payload.focusY ?? null)
  if (embedded?.card) {
    embeddedCardPreview.value = embedded
    try {
      const file = imageDataUrlToPngFile(payload.imageData, 'avatar.png')
      const prev = await previewSillyTavernImport(file)
      avatarEmbeddedStPendingId.value = prev.pendingId
      avatarEmbeddedStExpiresAt.value = prev.expiresAt
      avatarEmbeddedStPreview.value = prev.preview
      avatarEmbeddedMvuMode.value = prev.preview.mvu.suggestedMode || 'regex'
      avatarEmbeddedEnableMvu.value = Boolean(
        prev.preview.mvu.hasTavernHelper
        || prev.preview.mvu.hasRegexScripts
        || prev.preview.mvu.characterBookCandidateCount,
      )
    } catch {
      resetAvatarEmbeddedStState()
    }
    showEmbeddedCardConfirmModal.value = true
  }
}

async function handlePersonaAvatarSave(payload: AvatarCropSavePayload) {
  await actions.handlePersonaAvatarSave(payload.imageData)
}

async function confirmImportEmbeddedCard() {
  if (!actions.editingCharacter.value || !embeddedCardPreview.value?.card) {
    clearEmbeddedCardPreviewState()
    return
  }
  embeddedCardImporting.value = true
  try {
    const current = actions.editingCharacter.value
    let incoming: CharacterCard
    let worldbookPayload: WorldBook | undefined
    let mergeWarnings: string[] | undefined

    if (avatarEmbeddedStPendingId.value) {
      const built = await materializeSillyTavernPending({
        pendingId: avatarEmbeddedStPendingId.value,
        enableMvuCompatibility: avatarEmbeddedEnableMvu.value,
        mvuMode: avatarEmbeddedMvuMode.value,
        avatarFilename: current.avatar || null,
      })
      incoming = built.character as unknown as CharacterCard
      worldbookPayload = built.worldbook ? (built.worldbook as unknown as WorldBook) : undefined
      mergeWarnings = built.warnings
    } else {
      incoming = embeddedCardPreview.value.card
      worldbookPayload = embeddedCardPreview.value.worldbook ?? undefined
    }

    let attachedWorldBookIds: string[] = []
    if (worldbookPayload) {
      const savedBook = await apiPost<WorldBook>('/api/worldbooks', worldbookPayload)
      attachedWorldBookIds = [savedBook.id]
      await loadCharacterEditorWorldbooks()
    }
    const mergedCard: CharacterCard = {
      ...current,
      name: incoming.name,
      description: incoming.description,
      personality: incoming.personality,
      scenario: incoming.scenario,
      firstMessage: incoming.firstMessage,
      exampleDialogue: incoming.exampleDialogue,
      systemPrompt: incoming.systemPrompt,
      extraFirstMessageEntries: Array.isArray(incoming.extraFirstMessageEntries) ? incoming.extraFirstMessageEntries : [],
      mvuEnabled: incoming.mvuEnabled === true,
      mvuMode: incoming.mvuMode === 'directive' ? 'directive' : 'regex',
      mvuDirective: typeof incoming.mvuDirective === 'string' ? incoming.mvuDirective : null,
      contentRegexRules: Array.isArray(incoming.contentRegexRules) ? incoming.contentRegexRules : [],
      initialStateTables: Array.isArray(incoming.initialStateTables)
        ? incoming.initialStateTables
        : current.initialStateTables,
      attachedWorldBookIds,
      avatar: current.avatar || incoming.avatar,
      avatarFocusX: current.avatarFocusX ?? incoming.avatarFocusX ?? null,
      avatarFocusY: current.avatarFocusY ?? incoming.avatarFocusY ?? null,
    }
    await apiPut<CharacterCard>('/api/assistant/workspace/character-card', mergedCard)
    actions.applyAssistantCard(mergedCard)
    clearEmbeddedCardPreviewState()
    if (mergeWarnings?.length) {
      void notifyMessage(mergeWarnings.join('；'), { title: '内嵌卡合并提示' })
    }
  } catch (error) {
    errorStack.pushError({ message: error, source: 'main', title: '导入 PNG 内嵌角色数据失败' })
    embeddedCardImporting.value = false
  }
}

async function loadCharacterEditorWorldbooks() {
  try {
    characterEditorWorldbooks.value = await apiGet<WorldBook[]>('/api/worldbooks')
  } catch {
    characterEditorWorldbooks.value = []
  }
}

function ensureCharacterAttachedWbIds() {
  const c = actions.editingCharacter.value
  if (!c) return
  if (!Array.isArray(c.attachedWorldBookIds)) c.attachedWorldBookIds = []
}

function characterEditorWorldBookName(id: string) {
  return characterEditorWorldbooks.value.find((b) => b.id === id)?.name || id
}

const characterEditorWorldBookSelectOptions = computed(() => {
  const c = actions.editingCharacter.value
  if (!c) return []
  const taken = new Set(c.attachedWorldBookIds || [])
  return characterEditorWorldbooks.value
    .filter((b) => !taken.has(b.id))
    .map((b) => ({ label: b.name || b.id, value: b.id }))
})

function addCharacterEditorWorldBook() {
  if (!actions.editingCharacter.value || !addCharacterEditorWbId.value) return
  ensureCharacterAttachedWbIds()
  const ids = actions.editingCharacter.value.attachedWorldBookIds!
  if (!ids.includes(addCharacterEditorWbId.value)) ids.push(addCharacterEditorWbId.value)
  addCharacterEditorWbId.value = ''
}

function removeCharacterEditorWorldBook(worldbookId: string) {
  if (!actions.editingCharacter.value?.attachedWorldBookIds) return
  actions.editingCharacter.value.attachedWorldBookIds = actions.editingCharacter.value.attachedWorldBookIds.filter(
    (id) => id !== worldbookId,
  )
}

function moveCharacterEditorWorldBook(worldbookId: string, direction: -1 | 1) {
  const c = actions.editingCharacter.value
  if (!c?.attachedWorldBookIds) return
  const ids = [...c.attachedWorldBookIds]
  const idx = ids.indexOf(worldbookId)
  if (idx < 0) return
  const next = idx + direction
  if (next < 0 || next >= ids.length) return
  const a = ids[idx]
  const b = ids[next]
  if (a == null || b == null) return
  ids[idx] = b
  ids[next] = a
  c.attachedWorldBookIds = ids
}

function handleCharacterEditorWbDragStart(idx: number) {
  characterEditorWbDraggingIdx.value = idx
}

function handleCharacterEditorWbDragOver(e: DragEvent, idx: number) {
  e.preventDefault()
  const c = actions.editingCharacter.value
  if (!c?.attachedWorldBookIds) return
  const from = characterEditorWbDraggingIdx.value
  if (from === null || from === idx) return
  const ids = [...c.attachedWorldBookIds]
  const item = ids.splice(from, 1)[0]
  if (item) {
    ids.splice(idx, 0, item)
    c.attachedWorldBookIds = ids
    characterEditorWbDraggingIdx.value = idx
  }
}

function handleCharacterEditorWbDragEnd() {
  characterEditorWbDraggingIdx.value = null
}

/**
 * 处理成员ID更新
 *
 * 更新群聊的成员顺序。
 * 使用chatsStore.updateMemberOrder（来自stores/chats.ts）更新。
 *
 * @param {string[]} memberIds - 新的成员ID顺序列表
 * @returns {Promise<void>} 完成时返回
 */
async function handleGroupSettingsApply(payload: {
  memberIds: string[]
  groupDelay: number
  groupSystemInjectDepth: number
  groupSystemAlwaysAtBottom: boolean
  groupMvuEnabled: boolean
  groupMvuAnchorCharacterId: string | null
  groupMvuTemplateCharacterId: string | null
  mvuMode: ChatMvuMode
  mvuDirective: string | null
  contentRegexRules: ChatContentRegexRule[]
  stateTables: import('../types/models').StatusTableDef[]
}) {
  if (!activeChat.value) return
  // 不能直接对 Pinia 响应式 Proxy 用 structuredClone（会抛 DataCloneError），
  // 使用 JSON 深拷贝即可——overrides 本身已是纯 JSON 数据。
  const base = JSON.parse(JSON.stringify(activeChat.value.overrides)) as ChatOverrides
  base.groupMvuEnabled = payload.groupMvuEnabled
  base.groupMvuAnchorCharacterId = payload.groupMvuAnchorCharacterId
  base.groupMvuTemplateCharacterId = payload.groupMvuTemplateCharacterId
  base.mvuMode = payload.mvuMode
  base.mvuDirective = payload.mvuDirective
  base.contentRegexRules = payload.contentRegexRules.map((r, i) => ({ ...r, order: i }))
  const currentState = activeChat.value.stateVariables
  const stateVariables = {
    version: currentState?.version ?? 1,
    updatedAt: new Date().toISOString(),
    source: (currentState?.source ?? 'chat_assistant') as 'mvu_agent' | 'chat_assistant',
    tables: payload.stateTables,
  }
  await chats.updateGroupSettings(activeChat.value.id, {
    memberIds: payload.memberIds,
    groupDelay: payload.groupDelay,
    groupSystemInjectDepth: payload.groupSystemInjectDepth,
    groupSystemAlwaysAtBottom: payload.groupSystemAlwaysAtBottom,
    overrides: base,
    stateVariables,
  })
  showGroupSettings.value = false
}

interface ModelOption {
  label: string
  value: string
  presetId: string | null
}

interface ModelOptionGroup {
  label: string
  options: ModelOption[]
}

/**
 * 计算当前可用的模型集合（来自所有预设或全局候选），用于过滤「最近使用」中已删除的模型。
 */
const availableModelSet = computed(() => {
  if (!settings.settings) return new Set<string>()
  const presets = settings.settings.apiPresets
  if (presets && presets.length > 0) {
    return new Set(presets.filter((p) => !isTtsApiPreset(p)).flatMap((p) => p.models || []))
  }
  return new Set(settings.settings.llm.modelCandidates || [])
})

/**
 * 计算聊天模型选项
 *
 * 根据设置生成聊天模型选项列表，包括"最近使用"、各API预设的模型、全局配置的模型候选。
 * 「最近使用」仅显示当前仍存在于某预设或全局候选中的模型，避免显示已删除预设/模型。
 * 按预设分组，每个选项包含label、value和presetId。
 */
const chatModelOptions = computed(() => {
  const options: ModelOptionGroup[] = []
  if (!settings.settings) return []

  const recentModels = (settings.settings.llm.usedModels || []).filter(m => availableModelSet.value.has(m))
  if (recentModels.length > 0) {
    options.push({
      label: '最近使用',
      options: recentModels.map(m => {
        let preset = null
        if (settings.settings?.apiPresets) {
          preset = settings.settings.apiPresets.find(
            (p) => !isTtsApiPreset(p) && p.models.includes(m),
          )
        }
        return { label: m, value: m, presetId: preset ? preset.id : null }
      })
    })
  }

  if (settings.settings.apiPresets) {
    for (const preset of settings.settings.apiPresets) {
      if (isTtsApiPreset(preset)) continue
      if (preset.models && preset.models.length > 0) {
        options.push({
          label: preset.name,
          options: preset.models.map(m => ({ label: m, value: m, presetId: preset.id }))
        })
      }
    }
  }

  if ((!settings.settings.apiPresets || settings.settings.apiPresets.length === 0) && 
      settings.settings.llm.modelCandidates && settings.settings.llm.modelCandidates.length > 0) {
    options.push({
      label: '全局配置',
      options: settings.settings.llm.modelCandidates.map(m => ({ label: m, value: m, presetId: null }))
    })
  }

  return options
})

/** 当前会话生效的正则规则：合并全局库与会话级角色规则，同 ID 全局优先 */
const effectiveContentRegexRules = computed(() => {
  const seen = new Set<string>()
  const rules: ChatContentRegexRule[] = []
  const globalLib = settings.settings?.contentRegexRuleLibrary || []
  for (const r of globalLib) {
    rules.push(r)
    seen.add(r.id)
  }
  const chatRules = activeChat.value?.overrides?.contentRegexRules || []
  for (const r of chatRules) {
    if (!seen.has(r.id)) {
      rules.push(r)
      seen.add(r.id)
    }
  }
  return rules.sort((a, b) => (a.order ?? 0) - (b.order ?? 0) || a.id.localeCompare(b.id))
})

/**
 * 计算当前聊天模型
 *
 * 优先使用聊天覆盖设置中的模型，其次使用全局默认模型，都没有则返回"未设置"。
 */
const currentModel = computed(() => {
  return chats.activeChat?.overrides?.params?.model || settings.settings?.llm.defaultModel || '未设置'
})

/**
 * 计算助手当前模型
 *
 * 优先使用助手设置中的模型，其次使用全局默认模型，都没有则返回"未设置"。
 */
const assistantCurrentModel = computed(() => {
  return assistant.assistantSettings.value.model || settings.settings?.llm.defaultModel || '未设置'
})

/**
 * 处理模型选择
 *
 * 更新聊天会话的模型设置。
 * 如果选项包含presetId，则使用该presetId；否则从API预设中查找匹配的预设。
 * 使用chatsStore.updateOverrides（来自stores/chats.ts）更新设置。
 *
 * @param {any} option - 模型选项，包含value和可选的presetId
 * @returns {Promise<void>} 完成时返回
 */
async function handleModelSelect(option: any) {
  if (!chats.activeChat) return
  await flushPendingGreetingVersion()
  const overrides = { ...chats.activeChat.overrides }
  overrides.params = { ...overrides.params, model: option.value }
  
  if (option.presetId) {
    overrides.presetId = option.presetId
  } else {
    const found = settings.settings?.apiPresets.find(
      (p) => !isTtsApiPreset(p) && p.models.includes(option.value),
    )
    if (found) overrides.presetId = found.id
    else overrides.presetId = null
  }
  
  await chats.updateOverrides(chats.activeChat.id, overrides)
}

/**
 * 滚动到底部
 *
 * 滚动消息列表到底部，用于显示最新消息。
 * 使用nextTick确保DOM更新后再滚动。
 */
const messageListRef = ref<InstanceType<typeof MessageList> | null>(null)
const mvuStateBarWrapExtraHeightPx = ref(0)

function updateMvuStateBarWrapExtraHeight(px: number) {
  mvuStateBarWrapExtraHeightPx.value = Math.max(0, Math.ceil(px))
}

watch(
  () => [activeChat.value?.id ?? null, mvuStore.capsuleData.length] as const,
  ([chatId, capsuleCount], [oldChatId]) => {
    if (chatId !== oldChatId || capsuleCount <= 0) {
      mvuStateBarWrapExtraHeightPx.value = 0
    }
  },
)

/** 本次发送的用户消息 id，供 MessageList 播放一次性入场动画 */
const entrancingUserMessageId = ref<string | null>(null)
let entrancingUserClearTimer: ReturnType<typeof setTimeout> | null = null
const USER_BUBBLE_ENTER_ANIM_MS = 480

function armUserMessageEnterAnimation(messageId: string) {
  entrancingUserMessageId.value = messageId
  if (entrancingUserClearTimer != null) clearTimeout(entrancingUserClearTimer)
  entrancingUserClearTimer = setTimeout(() => {
    entrancingUserClearTimer = null
    if (entrancingUserMessageId.value === messageId) entrancingUserMessageId.value = null
  }, USER_BUBBLE_ENTER_ANIM_MS)
}

function clearUserMessageEnterAnimation() {
  if (entrancingUserClearTimer != null) {
    clearTimeout(entrancingUserClearTimer)
    entrancingUserClearTimer = null
  }
  entrancingUserMessageId.value = null
}

/** 重写 / 保存并发送等路径插入的助手占位行，弱化整行挂载跳变 */
const entrancingAssistantMessageId = ref<string | null>(null)
let entrancingAssistantClearTimer: ReturnType<typeof setTimeout> | null = null
const ASSISTANT_ROW_ENTER_ANIM_MS = 480

function armAssistantRowEnterAnimation(messageId: string) {
  entrancingAssistantMessageId.value = messageId
  if (entrancingAssistantClearTimer != null) clearTimeout(entrancingAssistantClearTimer)
  entrancingAssistantClearTimer = setTimeout(() => {
    entrancingAssistantClearTimer = null
    if (entrancingAssistantMessageId.value === messageId) entrancingAssistantMessageId.value = null
  }, ASSISTANT_ROW_ENTER_ANIM_MS)
}

function clearAssistantRowEnterAnimation() {
  if (entrancingAssistantClearTimer != null) {
    clearTimeout(entrancingAssistantClearTimer)
    entrancingAssistantClearTimer = null
  }
  entrancingAssistantMessageId.value = null
}

function clearMessageListEnterAnimations() {
  clearUserMessageEnterAnimation()
  clearAssistantRowEnterAnimation()
}

function scrollToBottom(instant = false, force = false) {
  nextTick(() => {
    messageListRef.value?.scrollToBottom(instant, force)
  })
}

/**
 * 仅用于「用户发送消息」时对齐到底部：MessageList 内以 rAF 驱动一段 ~420ms 的平滑滚动，
 * 与气泡入场关键帧同步，让新消息从视口下方抬入视野。流式 / 重写 / 切聊天等其它场景
 * 继续使用原有的 scrollToBottom，避免干扰既有稳定体验。
 */
function scrollToBottomAnimated() {
  nextTick(() => {
    messageListRef.value?.scrollToBottomAnimated?.()
  })
}

function jumpToMessageIndex(index: number) {
  nextTick(() => {
    messageListRef.value?.scrollToMessage(index)
  })
}

async function runChatSearch() {
  const chat = activeChat.value
  const q = chatSearchQuery.value.trim()
  if (!chat || !q) {
    chatSearchResults.value = []
    chatSearchCursor.value = -1
    return
  }
  chatSearchLoading.value = true
  try {
    const res = await apiGet<{ query: string; total: number; hits: Array<{ messageId: string; messageIndex: number; snippet: string }> }>(
      `/api/chats/${encodeURIComponent(chat.id)}/search?q=${encodeURIComponent(q)}`
    )
    chatSearchResults.value = Array.isArray(res?.hits) ? res.hits : []
    chatSearchCursor.value = -1
  } finally {
    chatSearchLoading.value = false
  }
}

let chatSearchTimer: ReturnType<typeof setTimeout> | null = null

function goToNextSearchResult() {
  const list = chatSearchHitsForNav.value
  const total = list.length
  if (!total) return
  if (chatSearchCursor.value < 0) {
    chatSearchCursor.value = 0
  } else {
    chatSearchCursor.value = (chatSearchCursor.value + 1) % total
  }
  jumpToMessageIndex(list[chatSearchCursor.value]!.messageIndex)
}

function goToPrevSearchResult() {
  const list = chatSearchHitsForNav.value
  const total = list.length
  if (!total) return
  if (chatSearchCursor.value < 0) {
    chatSearchCursor.value = total - 1
  } else {
    chatSearchCursor.value = (chatSearchCursor.value - 1 + total) % total
  }
  jumpToMessageIndex(list[chatSearchCursor.value]!.messageIndex)
}

function jumpToSearchResult(idx: number) {
  const hit = chatSearchHitsForNav.value[idx]
  if (!hit) return
  chatSearchCursor.value = idx
  jumpToMessageIndex(hit.messageIndex)
}

function openChatSearchBar() {
  holdSearchChipUntilSearchPanelClosed.value = false
  showHeaderMoreMenu.value = false
  clearChatSearchPanelAnimTimers()
  chatSearchExpandOpen.value = false
  chatSearchContentRevealed.value = false
  showChatSearch.value = true
  nextTick(() => {
    if (prefersReducedMotion()) {
      chatSearchExpandOpen.value = true
      chatSearchContentRevealed.value = true
      nextTick(() => {
        if (chatSearchResults.value.length > 0) {
          syncChatSearchChipsRow({ forceExpandAnimation: true })
        }
        chatSearchInputRef.value?.focus()
        chatSearchInputRef.value?.select()
      })
      return
    }
    chatSearchExpandOpen.value = true
    chatSearchOpenRevealTimer = window.setTimeout(() => {
      chatSearchContentRevealed.value = true
      chatSearchOpenRevealTimer = null
      nextTick(() => {
        if (chatSearchResults.value.length > 0) {
          syncChatSearchChipsRow({ forceExpandAnimation: true })
        }
        chatSearchInputRef.value?.focus()
        chatSearchInputRef.value?.select()
      })
    }, SEARCH_REVEAL_DELAY_MS)
  })
}

function closeChatSearchBar() {
  if (!showChatSearch.value) return
  clearChatSearchPanelAnimTimers()
  holdSearchChipUntilSearchPanelClosed.value = true
  if (prefersReducedMotion()) {
    chatSearchExpandOpen.value = false
    chatSearchContentRevealed.value = false
    showChatSearch.value = false
    holdSearchChipUntilSearchPanelClosed.value = false
    return
  }
  chatSearchContentRevealed.value = false
  const half = SEARCH_CLOSE_CONTENT_MS / 2
  const tExpand = window.setTimeout(() => {
    chatSearchExpandOpen.value = false
  }, half)
  const totalEnd = Math.max(SEARCH_CLOSE_CONTENT_MS, half + SEARCH_EXPAND_COLLAPSE_MS)
  const tDone = window.setTimeout(() => {
    showChatSearch.value = false
    holdSearchChipUntilSearchPanelClosed.value = false
    chatSearchExpandOpen.value = false
    chatSearchContentRevealed.value = false
    chatSearchCloseTimers = []
  }, totalEnd)
  chatSearchCloseTimers = [tExpand, tDone]
}

function toggleHeaderMoreMenu() {
  showHeaderMoreMenu.value = !showHeaderMoreMenu.value
}

function closeHeaderMoreMenu() {
  showHeaderMoreMenu.value = false
}

function handleHeaderPointerdown(e: PointerEvent) {
  const target = e.target as Node | null
  if (!target) return
  if (headerMoreMenuRef.value?.contains(target) || headerMoreButtonRef.value?.contains(target)) return
  closeHeaderMoreMenu()
}

function handleGlobalKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') {
    closeHeaderMoreMenu()
    if (showChatSearch.value) closeChatSearchBar()
    return
  }
  if (!(e.ctrlKey && (e.key === 'f' || e.key === 'F'))) return
  if (!activeChat.value) return
  const target = e.target as HTMLElement | null
  const tag = (target?.tagName || '').toLowerCase()
  if (tag === 'input' || tag === 'textarea' || target?.isContentEditable) return
  e.preventDefault()
  openChatSearchBar()
}

/**
 * 计算群聊成员列表
 *
 * 如果是群聊，则根据memberIds从角色列表中查找对应的角色卡片。
 */
const groupMembers = computed(() => {
  if (!activeChat.value?.isGroup) return []
  return activeChat.value.memberIds
    .map(id => characters.list.find(c => c.id === id))
    .filter((c): c is CharacterCard => c !== null)
})

/**
 * 计算是否正在流式传输
 *
 * 检查是否启用流式传输且（正在生成或正在插话）。
 */
const isStreamingActive = computed(() => isStreamEnabled.value && (isGenerating.value || group.isInterjecting.value))

/**
 * 计算是否有草稿消息
 *
 * 检查输入框是否有非空内容。
 */
const hasDraftMessage = computed(() => !!draftMessage.value.trim())

/**
 * 检查是否为AbortError
 *
 * 判断错误是否为AbortError（请求被取消）。
 *
 * @param {any} e - 错误对象
 * @returns {boolean} 是否为AbortError
 */
function isAbortError(e: any) {
  return e?.name === 'AbortError'
}

/**
 * 组件挂载时的初始化
 *
 * 加载设置、角色列表和群聊列表。
 * 如果没有选中角色，则自动选中第一个角色。
 */
onMounted(async () => {
  if (!janitorPendingId.value) {
    const stored = sessionStorage.getItem(JANITOR_CHAT_PENDING_STORAGE_KEY)
    if (stored?.trim()) janitorPendingId.value = stored.trim()
  }
  if (!settings.settings) await settings.load()
  await characters.loadAll()
  await chats.loadGroupList()
  window.addEventListener('keydown', handleGlobalKeydown)
  window.addEventListener('pointerdown', handleHeaderPointerdown)

  if (!selectedCharacterId.value) {
    const first = sidebarCharacters.value[0]
    if (first) selectedCharacterId.value = first.id
  }
  nextTick(() => {
    updateContentAreaLeft()
    runChatFabSeparation()
    window.setTimeout(() => {
      updateContentAreaLeft()
      runChatFabSeparation()
    }, 320)
  })
  window.addEventListener('resize', scheduleContentAreaLeft, { passive: true })
})

onBeforeUnmount(() => {
  mvuStore.disconnect()
  clearChatSearchAnimTimers()
  window.removeEventListener('resize', scheduleContentAreaLeft)
  if (contentAreaLeftRaf) cancelAnimationFrame(contentAreaLeftRaf)
  cancelContentAreaLeftLayoutSync()
  if (contentAreaLeftSepDebounce) clearTimeout(contentAreaLeftSepDebounce)
})

/**
 * 监听助手面板打开状态
 *
 * 当助手面板打开时，加载聊天作用域的助手状态。
 */
watch(assistant.isAssistantPanelOpen, (next) => {
  if (next) void assistant.loadState('chat')
})

// MVU SSE 生命周期：切换聊天或群聊 MVU 开关时重连
watch(
  () => {
    const ac = activeChat.value
    if (!ac) return { id: null as string | null, on: false }
    return {
      id: ac.id,
      on: isChatMvuRuntimeEnabled(ac, (id) => characters.list.find((c) => c.id === id)),
    }
  },
  (next, prev) => {
    if (prev?.id && (prev.id !== next.id || (prev.on && !next.on))) {
      flushPendingGreetingVersion()
      mvuStore.disconnect()
    }
    const shouldConnect =
      Boolean(next.id && next.on) &&
      (prev?.id !== next.id || (!prev?.on && next.on))
    if (shouldConnect && next.id) mvuStore.connect(next.id)
  },
  { immediate: true },
)

function scrollWorkspaceAssistantListToBottom() {
  const run = () => {
    const el = workspaceAssistantMessagesListRef.value
    if (el) el.scrollTop = el.scrollHeight
  }
  nextTick(() => {
    run()
    requestAnimationFrame(run)
  })
}

watch(
  () => assistant.isWorkspaceAssistantGenerating.value,
  (next, prev) => {
    if (next && !prev) scrollWorkspaceAssistantListToBottom()
  },
)

/**
 * 监听选中角色ID变化
 *
 * 当选中角色变化时，加载该角色的聊天列表，并自动选择第一个聊天。
 * 使用immediate选项，在组件挂载时立即执行一次。
 */
watch(
  () => route.query.janitorPending,
  (pending) => {
    if (typeof pending !== 'string' || !pending.trim()) return
    const id = pending.trim()
    janitorPendingId.value = id
    try {
      sessionStorage.setItem(JANITOR_CHAT_PENDING_STORAGE_KEY, id)
    } catch {
      // ignore quota / private mode
    }
    showImportModal.value = true
    const query = { ...route.query }
    delete query.janitorPending
    void router.replace({ query })
  },
  { immediate: true },
)

watch(
  () => route.query.janitorCharImport,
  async (flag) => {
    if (flag !== '1' && flag !== 'ok') return
    if (!janitorPendingId.value) {
      try {
        const stored = sessionStorage.getItem(JANITOR_CHAT_PENDING_STORAGE_KEY)
        if (stored?.trim()) janitorPendingId.value = stored.trim()
      } catch {
        // ignore
      }
    }
    const cname = route.query.janitorCharName
    const wraw = route.query.janitorCharWarnings
    showImportModal.value = true
    const query = { ...route.query }
    delete query.janitorCharImport
    delete query.janitorCharId
    delete query.janitorCharName
    delete query.janitorCharWarnings
    void router.replace({ query })
    await refreshDataAfterImport()
    if (janitorPendingId.value) {
      janitorPendingReloadNonce.value++
    }
    let warnSuffix = ''
    if (typeof wraw === 'string' && wraw.trim()) {
      try {
        const arr = JSON.parse(wraw) as unknown
        if (Array.isArray(arr) && arr.length) {
          warnSuffix = '\n警告：' + arr.map((x) => String(x)).join('; ')
        }
      } catch {
        warnSuffix = '\n警告：' + wraw
      }
    }
    const name = typeof cname === 'string' && cname.trim() ? cname.trim() : '已创建角色'
    void notifyMessage(`角色导入完成：${name}${warnSuffix}`)
  },
  { immediate: true },
)

watch(
  () => selectedCharacterId.value,
  async (cid) => {
    if (!cid) return
    await chats.loadList(cid)
    const ac = chats.activeChat
    if (ac?.isGroup && ac.memberIds?.includes(cid)) {
      return
    }
    const latest = pickLatestChatByUpdatedAt(chats.list)
    if (latest) {
      await chats.load(latest.id)
    } else {
      chats.activeChatId = null
      chats.activeChat = null
    }
  },
  { immediate: true },
)

/** 激活群聊时若当前选中角色不在成员内，同步为群内第一个仍存在的成员（顺序同 memberIds） */
watch(
  () => activeChat.value?.id,
  () => {
    const chat = activeChat.value
    if (!chat?.isGroup || !chat.memberIds?.length) return
    const sel = selectedCharacterId.value
    if (sel && chat.memberIds.includes(sel)) return
    const first = chat.memberIds.find((id) => characters.list.some((c) => c.id === id))
    if (first) selectedCharacterId.value = first
  },
)

/**
 * 监听助手聊天ID变化
 *
 * 当助手聊天ID变化且助手面板打开时，重新加载聊天作用域的助手状态。
 */
watch(
  () => assistantChatId.value,
  (next, prev) => {
    if (next && next !== prev && assistant.isAssistantPanelOpen.value) {
      void assistant.loadState('chat')
    }
  },
)

/** 切换聊天时清空主聊天的思考链（仅前端临时，不持久化） */
watch(
  () => activeChat.value?.id,
  (next, prev) => {
    if (next && next !== prev) {
      scrollToBottom(true, true)
    }
    if (prev != null && next !== prev) {
      clearMessageListEnterAnimations()
      chatReasoningBlocks.value = []
      chatReasoningContent.value = ''
      chatReasoningMessageId.value = null
      chatReasoningStreamActive.value = false
      clearReasoningPhaseTiming()
      versions.clearAll()
      streamHiddenMessageIds.value = []
      streamDeferDeleteIds.value = []
      rewriteMergeCtx.value = null
      saveSendDeferCtx.value = null
    }
    // 切换会话时自动关闭搜索面板并重置搜索状态
    showHeaderMoreMenu.value = false
    clearChatSearchAnimTimers()
    holdSearchChipUntilSearchPanelClosed.value = false
    chatSearchExpandOpen.value = false
    chatSearchContentRevealed.value = false
    showChatSearch.value = false
    chatSearchQuery.value = ''
    chatSearchResults.value = []
    chatSearchCursor.value = -1
  },
)

watch(
  () => {
    const c = activeChat.value
    if (!c) return ''
    return [
      c.id,
      c.messages
        .filter((m) => m.role === 'assistant' && m.greetingVariants && m.greetingVariants.length > 1)
        .map(
          (m) =>
            `${m.id}:${(m.greetingVariantIndex ?? '')}:${(m.greetingVariants ?? []).join('\u001f')}:${m.content}`,
        )
        .join('|'),
    ].join('::')
  },
  () => {
    const chat = activeChat.value
    if (!chat) return
    for (const p of chat.messages) {
      if (p.role !== 'assistant') continue
      const gv = p.greetingVariants
      if (!gv || gv.length <= 1) continue
      versions.hydrateGreetingVariants(
        p.id,
        gv,
        p.content,
        p.greetingVariantIndex ?? null,
        p.greetingVariantReasoningContents ?? null,
        p.greetingVariantReasoningDurations ?? null,
      )
    }
  },
)

watch(chatSearchQuery, () => {
  if (!showChatSearch.value || !chatSearchContentRevealed.value) return
  if (chatSearchTimer) clearTimeout(chatSearchTimer)
  chatSearchTimer = setTimeout(() => {
    void runChatSearch()
  }, 180)
})

async function cleanupCharacterEditorAssistantContext() {
  await assistant.cleanupWorkspaceSession()
  await assistant.deleteWorkspaceChat()
  if (assistant.isAssistantPanelOpen.value) await assistant.loadState('chat')
}

/**
 * 监听角色编辑弹窗状态
 *
 * 当角色编辑弹窗关闭时，删除工作区助手聊天，如果助手面板打开则加载聊天作用域状态。
 */
watch(actions.showCharacterEditor, (next, prev) => {
  if (!next && prev) {
    void cleanupCharacterEditorAssistantContext()
    actions.editingCharacter.value = null
    actions.isNewCharacter.value = false
    characterEditorWbDraggingIdx.value = null
    addCharacterEditorWbId.value = ''
    clearEmbeddedCardPreviewState()
  }
})

watch(
  () => actions.showCharacterEditor.value,
  (open) => {
    if (open && actions.editingCharacter.value) {
      ensureCharacterAttachedWbIds()
      void loadCharacterEditorWorldbooks()
      extraFirstMessageDraft.value = ''
    }
  },
)

/**
 * 根据当前聊天窗口动态更新页面标题
 *
 * 无激活聊天时显示 SimpleTavern；
 * 单聊窗口显示 SimpleTavern-角色名；
 * 群聊窗口显示 SimpleTavern-群聊名。
 */
watch(
  () => {
    const chat = activeChat.value
    if (!chat) return 'SimpleTavern'
    if (chat.isGroup) return `SimpleTavern-${chat.title}`
    const char = characters.list.find((c) => c.id === chat.characterId)
    return char ? `SimpleTavern-${char.name}` : `SimpleTavern-${chat.title}`
  },
  (title) => {
    document.title = title
  },
  { immediate: true },
)

/**
 * 运行群聊生成
 *
 * 依次让群聊中的每个成员发言，支持流式和非流式两种模式。
 * 每个成员发言前会延迟指定时间（groupDelay）。
 * 支持暂停和继续功能。
 * 使用postAndConsumeSse函数（来自api/sse.ts）或apiPost函数（来自api/http.ts）发送请求。
 *
 * @param {string} chatId - 聊天ID
 * @param {string[]} memberIds - 要发言的成员ID列表
 * @param {boolean} useStream - 是否使用流式传输
 * @param {number} groupDelay - 成员发言之间的延迟时间（毫秒）
 * @param {number} startIndex - 开始索引（用于继续暂停的群聊）
 * @returns {Promise<void>} 完成时返回
 */
async function runGroupGeneration(
  chatId: string, 
  memberIds: string[], 
  useStream: boolean, 
  groupDelay: number,
  startIndex: number,
  imageFallbackMode = false
) {
  for (let i = startIndex; i < memberIds.length; i++) {
    const characterId = memberIds[i]
    if (!characterId) continue
    
    const actualIndex = activeChat.value?.memberIds ? activeChat.value.memberIds.indexOf(characterId) : -1
    group.currentSpeakerIndex.value = actualIndex
    
    if (i > startIndex) {
      await group.delay(groupDelay)
    }
    
    if (group.isPaused.value) {
      group.setPausedState(memberIds.slice(i))
      return
    }
    
    if (!activeChat.value) break
    
    const localAssistantId = `local_assistant_${Date.now()}_${i}`
    chatReasoningMessageId.value = localAssistantId
    chatReasoningContent.value = ''
    chatReasoningStreamActive.value = true
    markReasoningStreamPhaseStart()
    const localMsg = {
      version: 1,
      id: localAssistantId,
      role: 'assistant' as const,
      content: '',
      characterId,
      ts: new Date().toISOString()
    }
    chats.addLocalMessage(localMsg)
    scrollToBottom()

    if (useStream) {
      stream.registerStreamMessage(localAssistantId)
      let sseError: string | null = null
      try {
        await postAndConsumeSse(
          '/api/generate/group',
          { chatId, characterId, imageFallbackMode, webSearchEnabled: webSearchSessionEnabled.value },
          (evt) => {
            if (evt.event === 'delta') onAssistantContentDeltaStarted()
            if (shouldIgnoreStreamingEventWhileStopping(evt.event)) return
            if (evt.event === 'delta') {
              const data = evt.data as { text?: string } | undefined
              const t = data?.text
              if (typeof t === 'string') {
                stream.appendDeltaBuffered(localAssistantId, t)
              }
            } else if (evt.event === 'reasoning') {
              const data = evt.data as { text?: string } | undefined
              const t = data?.text
              if (typeof t === 'string') {
                chatReasoningContent.value += t
              }
            } else if (evt.event === 'done') {
              const data = evt.data as { assistantMessageId?: string } | undefined
              const serverId = data?.assistantMessageId
              if (serverId && chatReasoningContent.value) {
                chatReasoningMessageId.value = serverId
              }
              pushCurrentReasoningToBlocks(serverId ?? undefined, localAssistantId)
            } else if (evt.event === 'error') {
              chatReasoningStreamActive.value = false
              clearReasoningPhaseTiming()
              const data = evt.data as { message?: string } | undefined
              sseError = String(data?.message ?? 'unknown error')
            }
          },
          aborter.value?.signal,
        )
        if (sseError) {
          throw new Error(sseError)
        }
      } finally {
        stream.flushForMessage(localAssistantId)
        stopRequested.value = false
      }
      void tryAutoReadAssistantAfterStreamFlush(localAssistantId)
    } else {
      const res = await apiPost<{
        ok: boolean
        chatId: string
        assistantMessageId: string | null
        characterId: string
        content: string
        reasoningContent?: string
        error?: string
      }>('/api/generate/group', {
        chatId,
        characterId,
        imageFallbackMode,
        webSearchEnabled: webSearchSessionEnabled.value,
      })
      
      if (res.ok) {
        if (typeof res.reasoningContent === 'string') {
          chatReasoningContent.value = res.reasoningContent
        }
        pushCurrentReasoningToBlocks(res.assistantMessageId ?? undefined, localAssistantId)
        chats.appendLocalMessageContent(localAssistantId, res.content || '')
        scrollToBottom()
        void tryAutoReadAssistantAfterStreamFlush(localAssistantId)
      } else {
        throw new Error(res.error || 'unknown error')
      }
    }
    
    if (group.isPaused.value && i < memberIds.length - 1) {
      group.setPausedState(memberIds.slice(i + 1))
      return
    }
  }
  
  group.pendingMembers.value = []
  group.showContinueButton.value = false
}

function handleSelectImages(files: File[]) {
  // 仅由 ChatInput 在 validateFilesForTarget 通过后发出，此处不再重复校验与弹窗
  for (const file of files) {
    const id = `${Date.now()}_${Math.random().toString(36).slice(2, 8)}`
    draftImages.value.push({
      id,
      file,
      name: file.name,
      previewUrl: URL.createObjectURL(file),
    })
  }
}

function handleRemoveDraftImage(imageId: string) {
  const idx = draftImages.value.findIndex((x) => x.id === imageId)
  if (idx < 0) return
  URL.revokeObjectURL(draftImages.value[idx]!.previewUrl)
  draftImages.value.splice(idx, 1)
}

/**
 * 发送用户消息
 *
 * 发送用户消息并触发AI回复生成。
 * 支持单聊和群聊两种模式。
 * 支持流式和非流式两种生成方式。
 * 在发送前会清理消息版本历史。
 * 使用postAndConsumeSse函数（来自api/sse.ts）或apiPost函数（来自api/http.ts）发送请求。
 *
 * @returns {Promise<void>} 完成时返回
 */
async function sendUserMessage() {
  // 发送前先落盘待持久化的版本切换状态
  await flushPendingGreetingVersion()

  const rawText = draftMessage.value.trim()
  const pendingDraftImages = [...draftImages.value]
  const text = replaceInputPlaceholders(rawText)
  if (!text && pendingDraftImages.length === 0) return
  if (!activeChat.value) return
  if (isGenerating.value) return
  draftMessage.value = ''
  clearDraftImages()
  streamError.value = null
  
  const chatId = activeChat.value.id
  const isGroup = activeChat.value.isGroup
  const now = new Date().toISOString()
  const userRole = group.effectivePureAiMode.value ? ('system' as const) : ('user' as const)
  let uploadedImages: ChatImageAttachment[] = []

  // 处理暂停状态下的插话
  if (isGroup && group.showContinueButton.value) {
    const localUserId = `local_user_${Date.now()}`
    armUserMessageEnterAnimation(localUserId)
    chats.addLocalMessage({
      version: 1,
      id: localUserId,
      role: userRole,
      content: text,
      images: uploadedImages,
      senderPersonaId: userRole === 'user' ? (selectedPersona.value?.id ?? null) : null,
      senderName: userRole === 'user' ? (selectedPersona.value?.name ?? userName.value) : null,
      senderAvatar: userRole === 'user' ? (selectedPersona.value?.avatar ?? null) : null,
      ts: now,
    })
    scrollToBottomAnimated()
    void tryAutoReadUserMessage(localUserId)

    try {
      await apiPost(`/api/chats/${chatId}/messages`, {
        role: userRole,
        content: text,
        images: uploadedImages,
        senderPersonaId: userRole === 'user' ? (selectedPersona.value?.id ?? null) : null,
        senderName: userRole === 'user' ? (selectedPersona.value?.name ?? userName.value) : null,
        senderAvatar: userRole === 'user' ? (selectedPersona.value?.avatar ?? null) : null,
      })
      await chats.load(chatId)
      await afterChatReload(chatId)
      bumpSidebarForActiveChat()
    } catch (e: any) {
      streamError.value = e?.message ?? String(e)
    }
    return
  }

  // 清理版本历史（含持久化：清 greetingVariants，仅保留当前选中正文与推理）
  if (activeChat.value) {
    for (const msg of activeChat.value.messages) {
      if (msg.role !== 'assistant') continue
      if (
        Array.isArray(msg.greetingVariants) &&
        msg.greetingVariants.length > 1 &&
        !versions.hasMultipleVersions(msg)
      ) {
        versions.hydrateGreetingVariants(
          msg.id,
          msg.greetingVariants,
          msg.content,
          msg.greetingVariantIndex ?? null,
          msg.greetingVariantReasoningContents ?? null,
          msg.greetingVariantReasoningDurations ?? null,
        )
      }
      if (
        versions.hasMultipleVersions(msg) ||
        (Array.isArray(msg.greetingVariants) && msg.greetingVariants.length > 1)
      ) {
        const content = versions.cleanupVersions(msg)
        const r =
          (versions.getDisplayReasoning(msg) || msg.reasoningContent || '').trim() || null
        try {
          await chats.updateMessage(activeChat.value.id, msg.id, msg.role as MainChatRole, content, msg.characterId, {
            greetingVariants: null,
            greetingVariantReasoningContents: null,
            reasoningContent: r,
          })
        } catch (e) {
          console.error(e)
        }
        msg.content = content
        msg.reasoningContent = r
      }
    }
  }
  
  group.resetGroupState()

  isGenerating.value = true
  aborter.value?.abort()
  aborter.value = new AbortController()

  const useStream = settings.settings?.streamEnabled !== false

  try {
    uploadedImages = await uploadDraftImages(chatId, pendingDraftImages)
    if (isGroup) {
      const localUserId = `local_user_${Date.now()}`
      armUserMessageEnterAnimation(localUserId)
      chats.addLocalMessage({
        version: 1,
        id: localUserId,
        role: userRole,
        content: text,
        images: uploadedImages,
        senderPersonaId: userRole === 'user' ? (selectedPersona.value?.id ?? null) : null,
        senderName: userRole === 'user' ? (selectedPersona.value?.name ?? userName.value) : null,
        senderAvatar: userRole === 'user' ? (selectedPersona.value?.avatar ?? null) : null,
        ts: now,
      })
      scrollToBottomAnimated()
      void tryAutoReadUserMessage(localUserId)

      await apiPost(`/api/chats/${chatId}/messages`, {
        role: userRole,
        content: text,
        images: uploadedImages,
        senderPersonaId: userRole === 'user' ? (selectedPersona.value?.id ?? null) : null,
        senderName: userRole === 'user' ? (selectedPersona.value?.name ?? userName.value) : null,
        senderAvatar: userRole === 'user' ? (selectedPersona.value?.avatar ?? null) : null,
      })
      bumpSidebarForActiveChat()

      group.showInterject()
    } else {
      const localUserId = `local_user_${Date.now()}`
      const localAssistantId = `local_assistant_${Date.now()}`

      chatReasoningMessageId.value = localAssistantId
      chatReasoningContent.value = ''
      chatReasoningStreamActive.value = true
      markReasoningStreamPhaseStart()

      armUserMessageEnterAnimation(localUserId)
      chats.addLocalMessage({
        version: 1,
        id: localUserId,
        role: userRole,
        content: text,
        images: uploadedImages,
        senderPersonaId: userRole === 'user' ? (selectedPersona.value?.id ?? null) : null,
        senderName: userRole === 'user' ? (selectedPersona.value?.name ?? userName.value) : null,
        senderAvatar: userRole === 'user' ? (selectedPersona.value?.avatar ?? null) : null,
        ts: now,
      })
      void tryAutoReadUserMessage(localUserId)
      chats.addLocalMessage({ version: 1, id: localAssistantId, role: 'assistant', content: '', ts: now })
      scrollToBottomAnimated()

      if (useStream) {
        stream.registerStreamMessage(localAssistantId)
        let sseError: string | null = null
        try {
          await postAndConsumeSse(
            '/api/generate/stream',
            {
              chatId,
              userMessage: text,
              userImages: uploadedImages,
              imageFallbackMode: isImageStickyActive(),
              senderPersonaId: selectedPersona.value?.id ?? null,
              senderName: selectedPersona.value?.name ?? userName.value,
              senderAvatar: selectedPersona.value?.avatar ?? null,
              userPersona: selectedPersona.value ?? null,
              webSearchEnabled: webSearchSessionEnabled.value,
            },
            (evt) => {
              if (evt.event === 'delta') onAssistantContentDeltaStarted()
              if (shouldIgnoreStreamingEventWhileStopping(evt.event)) return
              if (evt.event === 'delta') {
                const data = evt.data as { text?: string } | undefined
                const t = data?.text
                if (typeof t === 'string') {
                  stream.appendDeltaBuffered(localAssistantId, t)
                }
              } else if (evt.event === 'reasoning') {
                const data = evt.data as { text?: string } | undefined
                const t = data?.text
                if (typeof t === 'string') {
                  chatReasoningContent.value += t
                }
              } else if (evt.event === 'done') {
                const data = evt.data as { assistantMessageId?: string } | undefined
                const serverId = data?.assistantMessageId
                if (serverId && chatReasoningContent.value) {
                  chatReasoningMessageId.value = serverId
                }
                pushCurrentReasoningToBlocks(serverId ?? undefined, localAssistantId)
              } else if (evt.event === 'error') {
                chatReasoningStreamActive.value = false
                clearReasoningPhaseTiming()
                const data = evt.data as { message?: string } | undefined
                sseError = String(data?.message ?? 'unknown error')
              }
            },
            aborter.value?.signal,
          )
          if (sseError) {
            throw new Error(sseError)
          }
        } finally {
          stream.flushForMessage(localAssistantId)
          stopRequested.value = false
        }
        void tryAutoReadAssistantAfterStreamFlush(localAssistantId)
      } else {
        const res = await apiPost<{
          ok: boolean
          chatId: string
          assistantMessageId: string | null
          content: string
          reasoningContent?: string
          error?: string
        }>('/api/generate/stream', {
          chatId,
          userMessage: text,
          userImages: uploadedImages,
          imageFallbackMode: isImageStickyActive(),
          senderPersonaId: selectedPersona.value?.id ?? null,
          senderName: selectedPersona.value?.name ?? userName.value,
          senderAvatar: selectedPersona.value?.avatar ?? null,
          userPersona: selectedPersona.value ?? null,
          webSearchEnabled: webSearchSessionEnabled.value,
        })
        
        if (res.ok) {
          if (typeof res.reasoningContent === 'string') {
            chatReasoningContent.value = res.reasoningContent
          }
          pushCurrentReasoningToBlocks(res.assistantMessageId ?? undefined, localAssistantId)
          chats.appendLocalMessageContent(localAssistantId, res.content || '')
          scrollToBottom()
          void tryAutoReadAssistantAfterStreamFlush(localAssistantId)
        } else {
          throw new Error(res.error || 'unknown error')
        }
      }
    }
  } catch (e: any) {
    if (!isAbortError(e)) {
      const errMsg = e?.message ?? String(e)
      if (uploadedImages.length > 0) {
        openImageFallback(errMsg, async () => {
          imageFallbackDialog.value.visible = false
          if (isGroup) {
            await chats.load(chatId)
            await afterChatReload(chatId)
          } else {
            const localAssistantId = `local_assistant_retry_${Date.now()}`
            chats.addLocalMessage({ version: 1, id: localAssistantId, role: 'assistant', content: '', ts: new Date().toISOString() })
            if (useStream) {
              stream.registerStreamMessage(localAssistantId)
              let retryErr: string | null = null
              try {
                await postAndConsumeSse('/api/generate/stream', {
                  chatId,
                  userMessage: text,
                  appendUserMessage: false,
                  imageFallbackMode: true,
                  userPersona: selectedPersona.value ?? null,
                  webSearchEnabled: webSearchSessionEnabled.value,
                }, (evt) => {
                  if (evt.event === 'delta') {
                    const data = evt.data as { text?: string } | undefined
                    if (typeof data?.text === 'string') stream.appendDeltaBuffered(localAssistantId, data.text)
                  } else if (evt.event === 'error') {
                    retryErr = String((evt.data as { message?: string } | undefined)?.message ?? 'unknown error')
                  }
                }, aborter.value?.signal)
                if (retryErr) throw new Error(retryErr)
              } finally {
                stream.flushForMessage(localAssistantId)
              }
              void tryAutoReadAssistantAfterStreamFlush(localAssistantId)
            } else {
              const retryRes = await apiPost<{ ok: boolean; content: string; error?: string }>('/api/generate/stream', {
                chatId,
                userMessage: text,
                appendUserMessage: false,
                imageFallbackMode: true,
                userPersona: selectedPersona.value ?? null,
                webSearchEnabled: webSearchSessionEnabled.value,
              })
              if (!retryRes.ok) throw new Error(retryRes.error || 'unknown error')
              chats.appendLocalMessageContent(localAssistantId, retryRes.content || '')
              void tryAutoReadAssistantAfterStreamFlush(localAssistantId)
            }
            await chats.load(chatId)
            await afterChatReload(chatId)
            const bind = resolveImageBindingKey()
            if (bind) {
              imageStickyBinding.value = bind
              saveImageStickyBindingRow(bind)
            }
          }
        })
      } else {
        streamError.value = errMsg
      }
    }
  } finally {
    isGenerating.value = false
    group.currentSpeakerIndex.value = -1
    if (stopStreamingHold.value) {
      await persistLocalStreamingMessages(chatId)
      stopStreamingHold.value = false
    } else {
      await chats.load(chatId)
      await afterChatReload(chatId)
      if (!isGroup && !streamError.value) bumpSidebarForActiveChat()
    }
    await settings.load()
  }
}

/**
 * 继续群聊
 *
 * 继续之前暂停的群聊，让剩余成员继续发言。
 * 使用runGroupGeneration函数继续生成。
 *
 * @returns {Promise<void>} 完成时返回
 */
async function continueGroupChat() {
  if (!activeChat.value || group.pendingMembers.value.length === 0) return
  
  group.showContinueButton.value = false
  group.isPaused.value = false
  isGenerating.value = true
  
  const chatId = activeChat.value.id
  const useStream = settings.settings?.streamEnabled !== false
  const groupDelay = activeChat.value.groupDelay || 1500
  
  try {
    await runGroupGeneration(chatId, group.pendingMembers.value, useStream, groupDelay, 0)
    
    if (group.isPaused.value) return
    
    group.currentSpeakerIndex.value = -1
    group.showInterject()
  } catch (e: any) {
    if (!isAbortError(e)) {
      streamError.value = e?.message ?? String(e)
    }
  } finally {
    const skippedReload = stopStreamingHold.value
    if (skippedReload) {
      await persistLocalStreamingMessages(chatId)
      stopStreamingHold.value = false
    }
    if (!group.isPaused.value) {
      isGenerating.value = false
      group.currentSpeakerIndex.value = -1
      group.pendingMembers.value = []
      if (!skippedReload) {
        await chats.load(chatId)
        await afterChatReload(chatId)
        if (!streamError.value) bumpSidebarForActiveChat()
        await settings.load()
      } else {
        await settings.load()
      }
    }
  }
}

/**
 * 开始下一轮群聊
 *
 * 在群聊中开始新的一轮对话，让所有成员依次发言。
 * 根据成员的概率设置筛选参与本轮对话的成员。
 * 使用runGroupGeneration函数生成回复。
 *
 * @returns {Promise<void>} 完成时返回
 */
async function startNextRound() {
  if (!activeChat.value) return
  if (!activeChat.value.isGroup) return
  if (isGenerating.value) return

  streamError.value = null
  group.resetGroupState()

  const chatId = activeChat.value.id
  const useStream = settings.settings?.streamEnabled !== false
  const groupDelay = activeChat.value.groupDelay || 1500

  isGenerating.value = true
  aborter.value?.abort()
  aborter.value = new AbortController()

  try {
    const allMemberIds = [...activeChat.value.memberIds]
    const memberIds = group.filterMembersByProbability(allMemberIds)

    await runGroupGeneration(chatId, memberIds, useStream, groupDelay, 0)
    if (group.isPaused.value) return

    group.showInterject()
  } catch (e: any) {
    streamError.value = e?.message ?? String(e)
  } finally {
    isGenerating.value = false
    group.currentSpeakerIndex.value = -1
    const skippedReload = stopStreamingHold.value
    if (skippedReload) {
      await persistLocalStreamingMessages(chatId)
      stopStreamingHold.value = false
    }
    if (!group.isPaused.value) {
      if (!skippedReload) {
        await chats.load(chatId)
        await afterChatReload(chatId)
        if (!streamError.value) bumpSidebarForActiveChat()
      }
      await settings.load()
    }
  }
}

/**
 * 触发插话
 *
 * 在群聊中触发指定角色的插话（在非轮次时间发言）。
 * 支持流式和非流式两种模式。
 * 使用postAndConsumeSse函数（来自api/sse.ts）或apiPost函数（来自api/http.ts）发送请求到/api/generate/interject。
 *
 * @param {string} characterId - 要插话的角色ID
 * @returns {Promise<void>} 完成时返回
 */
async function triggerInterject(characterId: string) {
  if (!activeChat.value || isGenerating.value || group.isInterjecting.value) return
  
  const chatId = activeChat.value.id
  group.isInterjecting.value = true
  streamError.value = null
  aborter.value?.abort()
  aborter.value = new AbortController()
  
  const useStream = settings.settings?.streamEnabled !== false
  const deferredForInterject =
    saveSendDeferCtx.value?.chatId === chatId ? saveSendDeferCtx.value : null
  const omitMessageIds = deferredForInterject?.tailIdsToDeleteOnSuccess ?? []
  
  const localAssistantId = `local_interject_${Date.now()}`
  chatReasoningMessageId.value = localAssistantId
  chatReasoningContent.value = ''
  chatReasoningStreamActive.value = true
  markReasoningStreamPhaseStart()
  const localMsg = { 
    version: 1, 
    id: localAssistantId, 
    role: 'assistant' as const, 
    content: '', 
    characterId,
    ts: new Date().toISOString() 
  }
  chats.addLocalMessage(localMsg)
  scrollToBottom()
  
  try {
    if (useStream) {
      stream.registerStreamMessage(localAssistantId)
      try {
        await postAndConsumeSse(
          '/api/generate/interject',
          { chatId, characterId, omitMessageIds, webSearchEnabled: webSearchSessionEnabled.value },
          (evt) => {
            if (evt.event === 'delta') onAssistantContentDeltaStarted()
            if (shouldIgnoreStreamingEventWhileStopping(evt.event)) return
            if (evt.event === 'delta') {
              const data = evt.data as { text?: string } | undefined
              const t = data?.text
              if (typeof t === 'string') {
                stream.appendDeltaBuffered(localAssistantId, t)
              }
            } else if (evt.event === 'reasoning') {
              const data = evt.data as { text?: string } | undefined
              const t = data?.text
              if (typeof t === 'string') {
                chatReasoningContent.value += t
              }
            } else if (evt.event === 'done') {
              const data = evt.data as { assistantMessageId?: string } | undefined
              const serverId = data?.assistantMessageId
              if (serverId && chatReasoningContent.value) {
                chatReasoningMessageId.value = serverId
              }
              pushCurrentReasoningToBlocks(serverId ?? undefined, localAssistantId)
            } else if (evt.event === 'error') {
              chatReasoningStreamActive.value = false
              clearReasoningPhaseTiming()
              const data = evt.data as { message?: string } | undefined
              streamError.value = String(data?.message ?? 'unknown error')
            }
          },
          aborter.value?.signal,
        )
      } finally {
        stream.flushForMessage(localAssistantId)
        stopRequested.value = false
      }
      void tryAutoReadAssistantAfterStreamFlush(localAssistantId)
    } else {
      const res = await apiPost<{
        ok: boolean
        chatId: string
        assistantMessageId: string | null
        characterId: string
        content: string
        reasoningContent?: string
        error?: string
      }>('/api/generate/interject', {
        chatId,
        characterId,
        omitMessageIds,
        webSearchEnabled: webSearchSessionEnabled.value,
      })
      
      if (res.ok) {
        if (typeof res.reasoningContent === 'string') {
          chatReasoningContent.value = res.reasoningContent
        }
        pushCurrentReasoningToBlocks(res.assistantMessageId ?? undefined, localAssistantId)
        chats.appendLocalMessageContent(localAssistantId, res.content || '')
        scrollToBottom()
        void tryAutoReadAssistantAfterStreamFlush(localAssistantId)
      } else {
        streamError.value = res.error || 'unknown error'
      }
    }
  } catch (e: any) {
    if (!isAbortError(e)) {
      streamError.value = e?.message ?? String(e)
    }
  } finally {
    group.isInterjecting.value = false
    if (stopStreamingHold.value) {
      await persistLocalStreamingMessages(chatId)
      stopStreamingHold.value = false
    } else {
      await chats.load(chatId)
      await afterChatReload(chatId)
      const ss = saveSendDeferCtx.value
      if (ss?.chatId === chatId && !streamError.value) {
        saveSendDeferCtx.value = null
        streamHiddenMessageIds.value = []
        streamDeferDeleteIds.value = []
        await finalizeDeferredTailDelete(chatId, ss.tailIdsToDeleteOnSuccess)
      } else if (ss?.chatId === chatId) {
        saveSendDeferCtx.value = null
        streamHiddenMessageIds.value = []
        streamDeferDeleteIds.value = []
      } else if (!streamError.value) {
        bumpSidebarForActiveChat()
      }
    }
  }
}

/**
 * 停止流式传输
 *
 * 停止当前正在进行的流式生成。
 * 取消请求，刷新所有流式缓冲，但不重新加载聊天数据。
 */
function stopStreaming() {
  if (!aborter.value) return
  stopRequested.value = true
  stopStreamingHold.value = true
  aborter.value.abort()
  stream.flushAll()
  /** 与首条正文 delta 一致：在 isGenerating 仍为 true 时结束思考阶段，便于 ReasoningBubble 闭合过渡 */
  if (chatReasoningStreamActive.value && reasoningPhaseStartedAt.value != null) {
    chatReasoningElapsedSec.value = Math.round((Date.now() - reasoningPhaseStartedAt.value) / 100) / 10
  }
  const rid = chatReasoningMessageId.value
  const sec = chatReasoningElapsedSec.value
  if (rid && typeof sec === 'number' && Number.isFinite(sec) && chats.activeChat) {
    const msg = chats.activeChat.messages.find((m) => m.id === rid)
    if (msg && msg.role === 'assistant') {
      msg.reasoningDurationSec = sec
    }
  }
  chatReasoningStreamActive.value = false
}

/**
 * 将当前会话中未持久化的本地流式消息（被截断的内容）保存到后端并重新加载
 * 用于用户点击终止后：打字机缓冲已通过 flushAll 写入本地消息，此处持久化并同步为可编辑的服务器消息
 */
async function persistLocalStreamingMessages(chatId: string) {
  const chat = activeChat.value
  if (!chat?.messages?.length) return

  const saveSendSnapshot = saveSendDeferCtx.value?.chatId === chatId ? saveSendDeferCtx.value : null
  const capturedReasoningMessageId = chatReasoningMessageId.value
  const capturedReasoningFromRef = chatReasoningContent.value.trim()
  const blocksSnapshot = [...chatReasoningBlocks.value]
  const capturedElapsed = chatReasoningElapsedSec.value

  const reasoningTextForLocalId = (localId: string): string => {
    if (capturedReasoningMessageId === localId && capturedReasoningFromRef) {
      return capturedReasoningFromRef
    }
    const fromBlock = blocksSnapshot.find((b) => b.messageId === localId)?.content?.trim()
    return fromBlock || ''
  }

  const durationSecForLocalId = (localId: string): number | null => {
    if (capturedReasoningMessageId !== localId) return null
    const lm = chat.messages.find((x) => x.id === localId)
    if (
      lm &&
      typeof lm.reasoningDurationSec === 'number' &&
      Number.isFinite(lm.reasoningDurationSec)
    ) {
      return lm.reasoningDurationSec
    }
    if (typeof capturedElapsed === 'number' && Number.isFinite(capturedElapsed)) {
      return capturedElapsed
    }
    return null
  }

  const localAssistantMessages = chat.messages
    .filter((m) => m.role === 'assistant' && m.id.startsWith('local_'))
    .map((m) => ({
      localId: m.id,
      content: (m.content || '').trim(),
      characterId: m.characterId ?? null,
    }))
    .filter((m) => {
      if (m.content) return true
      return !!reasoningTextForLocalId(m.localId)
    })

  await chats.load(chatId)
  let serverMessages = activeChat.value?.messages ?? []

  const rewriteSnapshot = rewriteMergeCtx.value

  if (saveSendSnapshot) {
    saveSendDeferCtx.value = null
    streamHiddenMessageIds.value = []
    streamDeferDeleteIds.value = []

    if (!saveSendSnapshot.singleAssistantTailMergeId) {
      for (const id of saveSendSnapshot.tailIdsToDeleteOnSuccess) {
        if (!id.startsWith('local_')) {
          try {
            await chats.deleteMessage(chatId, id, { skipReload: true })
          } catch (e) {
            console.error(e)
          }
        }
      }
      await chats.load(chatId)
      serverMessages = activeChat.value?.messages ?? []
    }
  }

  const normReasoning = (s: string | null | undefined) =>
    typeof s === 'string' ? s.trim() : ''

  const durationMatches = (serverSec: unknown, localSec: number | null) => {
    if (localSec == null || !Number.isFinite(localSec)) return true
    return (
      typeof serverSec === 'number' &&
      Number.isFinite(serverSec) &&
      Math.abs(serverSec - localSec) < 0.05
    )
  }

  for (const candidate of localAssistantMessages) {
    const reasoningForThis = reasoningTextForLocalId(candidate.localId) || null
    const durationForThis = durationSecForLocalId(candidate.localId)

    if (saveSendSnapshot?.singleAssistantTailMergeId) {
      await mergePartialAssistantIntoExistingMessage({
        chatId,
        targetMessageId: saveSendSnapshot.singleAssistantTailMergeId,
        partialBody: candidate.content,
        reasoningForThis,
        durationForThis,
      })
      serverMessages = activeChat.value?.messages ?? []
      continue
    }

    if (
      rewriteSnapshot &&
      rewriteSnapshot.chatId === chatId &&
      candidate.localId.startsWith('local_rewrite_')
    ) {
      await mergeRewriteInterruptedIntoAnchor({
        chatId,
        anchorId: rewriteSnapshot.anchorId,
        originalMessageId: rewriteSnapshot.originalMessageId,
        partialBody: candidate.content,
        reasoningForThis,
        durationForThis,
      })
      rewriteMergeCtx.value = null
      streamHiddenMessageIds.value = []
      streamDeferDeleteIds.value = []
      serverMessages = activeChat.value?.messages ?? []
      continue
    }

    const serverAssistantsSameBody = serverMessages.filter(
      (m) =>
        !m.id.startsWith('local_') &&
        m.role === 'assistant' &&
        (m.characterId ?? null) === candidate.characterId &&
        (m.content || '').trim() === candidate.content,
    )

    if (
      serverAssistantsSameBody.some(
        (m) =>
          normReasoning(m.reasoningContent) === normReasoning(reasoningForThis) &&
          durationMatches(m.reasoningDurationSec, durationForThis),
      )
    ) {
      continue
    }

    const serverMatch = serverAssistantsSameBody[0]

    if (serverMatch) {
      const needReason =
        !!reasoningForThis &&
        normReasoning(serverMatch.reasoningContent) !== normReasoning(reasoningForThis)
      const needDur =
        typeof durationForThis === 'number' &&
        Number.isFinite(durationForThis) &&
        (typeof serverMatch.reasoningDurationSec !== 'number' ||
          !Number.isFinite(serverMatch.reasoningDurationSec))

      if (needReason || needDur) {
        const updatedChat = await chats.updateMessage(
          chatId,
          serverMatch.id,
          'assistant',
          serverMatch.content,
          serverMatch.characterId ?? undefined,
          {
            ...(needReason ? { reasoningContent: reasoningForThis } : {}),
            ...(needDur ? { reasoningDurationSec: durationForThis } : {}),
          },
        )
        serverMessages = updatedChat.messages
      }
      continue
    }

    const appendOpts: {
      characterId?: string
      reasoningContent?: string | null
      reasoningDurationSec?: number | null
    } = {}
    if (candidate.characterId != null) appendOpts.characterId = candidate.characterId
    if (reasoningForThis) appendOpts.reasoningContent = reasoningForThis
    if (typeof durationForThis === 'number' && Number.isFinite(durationForThis)) {
      appendOpts.reasoningDurationSec = durationForThis
    }
    const updatedChat = await chats.appendMessage(
      chatId,
      'assistant',
      candidate.content,
      Object.keys(appendOpts).length ? appendOpts : undefined,
    )
    serverMessages = updatedChat.messages
  }
  chatReasoningContent.value = ''
  chatReasoningMessageId.value = null
  chatReasoningStreamActive.value = false
  rewriteMergeCtx.value = null
  streamHiddenMessageIds.value = []
  streamDeferDeleteIds.value = []
  clearReasoningPhaseTiming()
  await chats.load(chatId)
  await afterChatReload(chatId)
}

async function finalizeDeferredTailDelete(chatId: string, tailIds: string[]) {
  if (!tailIds.length) return
  for (const id of tailIds) {
    if (!id.startsWith('local_')) {
      try {
        await chats.deleteMessage(chatId, id, { skipReload: true })
      } catch (e) {
        console.error(e)
      }
    }
  }
  await chats.load(chatId)
  await afterChatReload(chatId)
  bumpSidebarForActiveChat()
}

/**
 * 处理主要操作
 *
 * 根据当前状态执行相应的主要操作：
 * - 如果正在流式传输，则停止
 * - 如果显示继续按钮且有草稿，则发送消息
 * - 如果显示继续按钮且无草稿，则继续群聊
 * - 如果是群聊且无草稿，则开始下一轮
 * - 否则发送消息
 */
function handlePrimaryAction() {
  if (isStreamingActive.value) {
    stopStreaming()
    return
  }
  if (group.showContinueButton.value && activeChat.value?.isGroup) {
    if (hasDraftMessage.value) {
      sendUserMessage()
    } else {
      continueGroupChat()
    }
    return
  }
  if (activeChat.value?.isGroup && !hasDraftMessage.value) {
    startNextRound()
    return
  }
  sendUserMessage()
}

/**
 * 切换到上一个版本
 *
 * 使用versions.switchToPreviousVersion（来自composables/useMessageVersions.ts）切换到消息的上一个版本。
 *
 * @param {ChatMessage} m - 消息对象（来自types/models.ts）
 */
function handleSwitchPreviousVersion(m: ChatMessage) {
  const previousContent = versions.getDisplayContent(m)
  const newContent = versions.switchToPreviousVersion(m)
  if (newContent !== null && activeChat.value) {
    const msg = activeChat.value.messages.find((msg) => msg.id === m.id)
    if (msg) {
      invalidateTtsCacheIfTextChanged(msg, previousContent, newContent)
      msg.content = newContent
      const idx = versions.getCurrentVersionIndex(m)
      msg.greetingVariantIndex = idx
      const snap = versions.getVariantArraysForMessage(m)
      if (snap && idx >= 0 && idx < snap.reasonings.length) {
        msg.reasoningContent = snap.reasonings[idx]?.trim() || null
        msg.reasoningDurationSec = snap.durations[idx] ?? undefined
      }
    }
    const needPersist =
      !m.id.startsWith('local_') &&
      activeChat.value &&
      m.role !== 'tool' &&
      (versions.hasMultipleVersions(m) || (Array.isArray(msg?.greetingVariants) && msg.greetingVariants.length > 1))
    if (needPersist) {
      const idx = versions.getCurrentVersionIndex(m)
      const snap = versions.getVariantArraysForMessage(m)
      if (snap) {
        pendingGreetingVersion.value = {
          chatId: activeChat.value.id,
          messageId: m.id,
          role: m.role,
          content: newContent,
          characterId: m.characterId,
          greetingVariantIndex: idx,
          greetingVariants: snap.contents,
          greetingVariantReasoningContents: snap.reasonings,
          greetingVariantReasoningDurations: snap.durations,
          reasoningContent: (snap.reasonings[idx]?.trim() || null),
        }
      }
    }
  }
}

/**
 * 切换到下一个版本
 *
 * 使用versions.switchToNextVersion（来自composables/useMessageVersions.ts）切换到消息的下一个版本。
 *
 * @param {ChatMessage} m - 消息对象（来自types/models.ts）
 */
function handleSwitchNextVersion(m: ChatMessage) {
  const previousContent = versions.getDisplayContent(m)
  const newContent = versions.switchToNextVersion(m)
  if (newContent !== null && activeChat.value) {
    const msg = activeChat.value.messages.find((msg) => msg.id === m.id)
    if (msg) {
      invalidateTtsCacheIfTextChanged(msg, previousContent, newContent)
      msg.content = newContent
      const idx = versions.getCurrentVersionIndex(m)
      msg.greetingVariantIndex = idx
      const snap = versions.getVariantArraysForMessage(m)
      if (snap && idx >= 0 && idx < snap.reasonings.length) {
        msg.reasoningContent = snap.reasonings[idx]?.trim() || null
        msg.reasoningDurationSec = snap.durations[idx] ?? undefined
      }
    }
    const needPersist =
      !m.id.startsWith('local_') &&
      activeChat.value &&
      m.role !== 'tool' &&
      (versions.hasMultipleVersions(m) || (Array.isArray(msg?.greetingVariants) && msg.greetingVariants.length > 1))
    if (needPersist) {
      const idx = versions.getCurrentVersionIndex(m)
      const snap = versions.getVariantArraysForMessage(m)
      if (snap) {
        pendingGreetingVersion.value = {
          chatId: activeChat.value.id,
          messageId: m.id,
          role: m.role,
          content: newContent,
          characterId: m.characterId,
          greetingVariantIndex: idx,
          greetingVariants: snap.contents,
          greetingVariantReasoningContents: snap.reasonings,
          greetingVariantReasoningDurations: snap.durations,
          reasoningContent: (snap.reasonings[idx]?.trim() || null),
        }
      }
    }
  }
}

/**
 * 将半截助手输出合入指定助手消息的多版本字段；允许正文为空但推理非空
 */
async function mergePartialAssistantIntoExistingMessage(payload: {
  chatId: string
  targetMessageId: string
  originalMessageId?: string
  partialBody: string
  reasoningForThis: string | null
  durationForThis: number | null
}) {
  const { chatId, targetMessageId, partialBody, reasoningForThis, durationForThis } = payload
  await chats.load(chatId)
  const targetMsg = activeChat.value?.messages.find((x) => x.id === targetMessageId)
  if (!targetMsg || targetMsg.role !== 'assistant') return

  const originalMessageId = payload.originalMessageId ?? versions.getOriginalMessageId(targetMsg.id)
  const gv = targetMsg.greetingVariants
  if (gv && gv.length > 1) {
    versions.hydrateGreetingVariants(
      targetMsg.id,
      gv,
      targetMsg.content,
      targetMsg.greetingVariantIndex ?? null,
      targetMsg.greetingVariantReasoningContents ?? null,
      targetMsg.greetingVariantReasoningDurations ?? null,
    )
  } else {
    versions.saveVersion(
      originalMessageId,
      targetMsg.content,
      targetMsg.reasoningContent ?? undefined,
      targetMsg.reasoningDurationSec ?? null,
    )
  }

  versions.addNewVersion(
    originalMessageId,
    targetMessageId,
    partialBody,
    reasoningForThis ?? undefined,
    durationForThis,
  )

  const snap = versions.getVariantArraysForPersist(targetMsg)
  if (!snap) return

  const idx = versions.getCurrentVersionIndex(targetMsg)
  const display = versions.getDisplayContent(targetMsg) || partialBody
  const reason =
    (versions.getDisplayReasoning(targetMsg) || reasoningForThis || '').trim() || null

  await chats.updateMessage(chatId, targetMessageId, 'assistant', display, targetMsg.characterId, {
    greetingVariantIndex: idx,
    greetingVariants: snap.contents,
    greetingVariantReasoningContents: snap.reasonings,
    greetingVariantReasoningDurations: snap.durations,
    reasoningContent: reason,
    ...(durationForThis != null && Number.isFinite(durationForThis)
      ? { reasoningDurationSec: durationForThis }
      : {}),
  })
}

/**
 * 重写流式中断：将半截生成合并进仍为磁盘上的锚点助手消息的多版本字段
 */
async function mergeRewriteInterruptedIntoAnchor(payload: {
  chatId: string
  anchorId: string
  originalMessageId: string
  partialBody: string
  reasoningForThis: string | null
  durationForThis: number | null
}) {
  await mergePartialAssistantIntoExistingMessage({
    chatId: payload.chatId,
    targetMessageId: payload.anchorId,
    originalMessageId: payload.originalMessageId,
    partialBody: payload.partialBody,
    reasoningForThis: payload.reasoningForThis,
    durationForThis: payload.durationForThis,
  })
}

/**
 * 处理消息重写
 *
 * 重写指定的助手消息：先 saveVersion（内存），流式结束前不在磁盘删除该条及尾部；
 * 借助 omitMessageIds 从本轮上下文排除这些消息；成功后再批量删除并让新版本落库。
 *
 * @param {ChatMessage} m - 要重写的消息（来自types/models.ts）
 * @returns {Promise<void>} 完成时返回
 */
async function handleRewriteMessage(m: ChatMessage) {
  if (!activeChat.value) return
  if (isGenerating.value) return
  if (m.id.startsWith('local_')) return
  if (m.role !== 'assistant') return

  // 先落盘待持久化的版本切换状态
  await flushPendingGreetingVersion()

  const chatId = activeChat.value.id
  const messageIndex = activeChat.value.messages.findIndex(msg => msg.id === m.id)
  if (messageIndex === -1) return

  let lastUserMessage: ChatMessage | null = null
  for (let i = messageIndex - 1; i >= 0; i--) {
    const msg = activeChat.value.messages[i]
    if (msg && (msg.role === 'user' || msg.role === 'system')) {
      lastUserMessage = msg
      break
    }
  }
  if (!lastUserMessage) return

  const anchorId = m.id
  const anchorTs = m.ts

  const originalMessageId = versions.getOriginalMessageId(m.id)
  const displayContent = versions.getDisplayContent(m)
  const currentReasoning = getReasoningForMessageId(m.id)
  const currentDuration = m.reasoningDurationSec ?? null
  versions.saveVersion(originalMessageId, displayContent, currentReasoning, currentDuration)

  const messagesToDelete = activeChat.value.messages.slice(messageIndex)
  const omitMessageIds = messagesToDelete.map((x) => x.id).filter((id) => !id.startsWith('local_'))
  const tailDeleteIds = activeChat.value.messages
    .slice(messageIndex + 1)
    .map((x) => x.id)
    .filter((id) => !id.startsWith('local_'))
  streamDeferDeleteIds.value = tailDeleteIds
  streamHiddenMessageIds.value = [...omitMessageIds]
  rewriteMergeCtx.value = { chatId, anchorId, anchorTs, originalMessageId }

  const listElBeforeLoad = messageListRef.value?.scrollRef ?? null
  const oldListScrollHeight = listElBeforeLoad?.scrollHeight ?? 0
  const oldListScrollTop = listElBeforeLoad?.scrollTop ?? 0

  isGenerating.value = true
  streamError.value = null
  aborter.value?.abort()
  aborter.value = new AbortController()

  const useStream = settings.settings?.streamEnabled !== false
  const isGroup = activeChat.value.isGroup
  const characterId = m.characterId || activeChat.value.characterId || ''

  try {
    const localAssistantId = `local_rewrite_${Date.now()}`
    chatReasoningMessageId.value = localAssistantId
    chatReasoningContent.value = ''
    chatReasoningStreamActive.value = true
    markReasoningStreamPhaseStart()
    const localMsg = {
      version: 1,
      id: localAssistantId,
      role: 'assistant' as const,
      content: '',
      characterId,
      ts: new Date().toISOString()
    }
    armAssistantRowEnterAnimation(localAssistantId)
    chats.addLocalMessage(localMsg)
    await nextTick()
    const listElAfter = messageListRef.value?.scrollRef ?? null
    if (listElAfter && oldListScrollHeight > 0) {
      const delta = listElAfter.scrollHeight - oldListScrollHeight
      listElAfter.scrollTop = Math.max(0, oldListScrollTop + delta)
    }
    scrollToBottom(false, true)

    if (isGroup) {
      if (useStream) {
        stream.registerStreamMessage(localAssistantId)
        try {
          await postAndConsumeSse(
            '/api/generate/group',
            {
              chatId,
              characterId,
              omitMessageIds,
              mergeAssistantIntoMessageId: anchorId,
              webSearchEnabled: webSearchSessionEnabled.value,
            },
            (evt) => {
              if (evt.event === 'delta') onAssistantContentDeltaStarted()
              if (shouldIgnoreStreamingEventWhileStopping(evt.event)) return
              if (evt.event === 'delta') {
                const data = evt.data as { text?: string } | undefined
                const t = data?.text
                if (typeof t === 'string') {
                  stream.appendDeltaBuffered(localAssistantId, t)
                }
              } else if (evt.event === 'reasoning') {
                const data = evt.data as { text?: string } | undefined
                const t = data?.text
                if (typeof t === 'string') {
                  chatReasoningContent.value += t
                }
              } else if (evt.event === 'done') {
                const data = evt.data as { assistantMessageId?: string } | undefined
                const serverId = data?.assistantMessageId
                if (serverId && chatReasoningContent.value) {
                  chatReasoningMessageId.value = serverId
                }
                pushCurrentReasoningToBlocks(serverId ?? undefined, localAssistantId)
              } else if (evt.event === 'error') {
                chatReasoningStreamActive.value = false
                clearReasoningPhaseTiming()
                const data = evt.data as { message?: string } | undefined
                streamError.value = String(data?.message ?? 'unknown error')
              }
            },
            aborter.value?.signal,
          )
        } finally {
          stream.flushForMessage(localAssistantId)
          stopRequested.value = false
        }
        void tryAutoReadAssistantAfterStreamFlush(localAssistantId)
      } else {
        const res = await apiPost<{
          ok: boolean
          content: string
          assistantMessageId?: string | null
          reasoningContent?: string
          error?: string
        }>('/api/generate/group', {
          chatId,
          characterId,
          omitMessageIds,
          mergeAssistantIntoMessageId: anchorId,
          webSearchEnabled: webSearchSessionEnabled.value,
        })
        
        if (res.ok) {
          if (typeof res.reasoningContent === 'string') {
            chatReasoningContent.value = res.reasoningContent
          }
          pushCurrentReasoningToBlocks(res.assistantMessageId ?? undefined, localAssistantId)
          chats.appendLocalMessageContent(localAssistantId, res.content || '')
          scrollToBottom()
          void tryAutoReadAssistantAfterStreamFlush(localAssistantId)
        } else {
          streamError.value = res.error || 'unknown error'
        }
      }
    } else {
      if (useStream) {
        stream.registerStreamMessage(localAssistantId)
        try {
          await postAndConsumeSse(
            '/api/generate/stream',
            {
              chatId,
              userMessage: lastUserMessage.content,
              appendUserMessage: false,
              imageFallbackMode: isImageStickyActive(),
              senderPersonaId: lastUserMessage.senderPersonaId ?? selectedPersona.value?.id ?? null,
              senderName: lastUserMessage.senderName ?? selectedPersona.value?.name ?? userName.value,
              senderAvatar: lastUserMessage.senderAvatar ?? selectedPersona.value?.avatar ?? null,
              userPersona: selectedPersona.value ?? null,
              omitMessageIds,
              mergeAssistantIntoMessageId: anchorId,
              webSearchEnabled: webSearchSessionEnabled.value,
            },
            (evt) => {
              if (evt.event === 'delta') onAssistantContentDeltaStarted()
              if (shouldIgnoreStreamingEventWhileStopping(evt.event)) return
              if (evt.event === 'delta') {
                const data = evt.data as { text?: string } | undefined
                const t = data?.text
                if (typeof t === 'string') {
                  stream.appendDeltaBuffered(localAssistantId, t)
                }
              } else if (evt.event === 'reasoning') {
                const data = evt.data as { text?: string } | undefined
                const t = data?.text
                if (typeof t === 'string') {
                  chatReasoningContent.value += t
                }
              } else if (evt.event === 'done') {
                const data = evt.data as { assistantMessageId?: string } | undefined
                const serverId = data?.assistantMessageId
                if (serverId && chatReasoningContent.value) {
                  chatReasoningMessageId.value = serverId
                }
                pushCurrentReasoningToBlocks(serverId ?? undefined, localAssistantId)
              } else if (evt.event === 'error') {
                chatReasoningStreamActive.value = false
                clearReasoningPhaseTiming()
                const data = evt.data as { message?: string } | undefined
                streamError.value = String(data?.message ?? 'unknown error')
              }
            },
            aborter.value?.signal,
          )
        } finally {
          stream.flushForMessage(localAssistantId)
          stopRequested.value = false
        }
        void tryAutoReadAssistantAfterStreamFlush(localAssistantId)
      } else {
        const res = await apiPost<{
          ok: boolean
          content: string
          assistantMessageId?: string | null
          reasoningContent?: string
          error?: string
        }>('/api/generate/stream', {
          chatId,
          userMessage: lastUserMessage.content,
          appendUserMessage: false,
          imageFallbackMode: isImageStickyActive(),
          userPersona: selectedPersona.value ?? null,
          omitMessageIds,
          mergeAssistantIntoMessageId: anchorId,
          webSearchEnabled: webSearchSessionEnabled.value,
        })
        
        if (res.ok) {
          if (typeof res.reasoningContent === 'string') {
            chatReasoningContent.value = res.reasoningContent
          }
          pushCurrentReasoningToBlocks(res.assistantMessageId ?? undefined, localAssistantId)
          chats.appendLocalMessageContent(localAssistantId, res.content || '')
          scrollToBottom()
          void tryAutoReadAssistantAfterStreamFlush(localAssistantId)
        } else {
          streamError.value = res.error || 'unknown error'
        }
      }
    }
  } catch (e: any) {
    if (!isAbortError(e)) {
      streamError.value = e?.message ?? String(e)
    }
  } finally {
    isGenerating.value = false
    const skippedReload = stopStreamingHold.value
    if (skippedReload) {
      await persistLocalStreamingMessages(chatId)
      stopStreamingHold.value = false
    } else {
      await chats.load(chatId)
      await afterChatReload(chatId)
    }
    await settings.load()

    // 成功后：后端已将新版本原位写入锚点；前端只 hydrate 并删除尾部
    if (!skippedReload && activeChat.value) {
      const anchorMsg = activeChat.value.messages.find((msg) => msg.id === anchorId && msg.role === 'assistant')
      if (anchorMsg?.greetingVariants && anchorMsg.greetingVariants.length > 1) {
        versions.hydrateGreetingVariants(
          anchorMsg.id,
          anchorMsg.greetingVariants,
          anchorMsg.content,
          anchorMsg.greetingVariantIndex ?? null,
          anchorMsg.greetingVariantReasoningContents ?? null,
          anchorMsg.greetingVariantReasoningDurations ?? null,
        )
      }
      const drop = [...streamDeferDeleteIds.value]
      streamDeferDeleteIds.value = []
      streamHiddenMessageIds.value = []
      rewriteMergeCtx.value = null
      if (drop.length) {
        await finalizeDeferredTailDelete(chatId, drop)
      }
    }
  }
}

/**
 * 开始编辑标题
 *
 * 设置正在编辑的聊天ID和标题，用于内联编辑。
 *
 * @param {string} chatId - 聊天ID
 * @param {string} currentTitle - 当前标题
 */
function startEditTitle(chatId: string, currentTitle: string) {
  editingChatId.value = chatId
  editingTitle.value = currentTitle
}

/**
 * 保存标题
 *
 * 保存编辑后的聊天标题。
 * 使用chatsStore.rename（来自stores/chats.ts）更新标题。
 *
 * @returns {Promise<void>} 完成时返回
 */
async function saveTitle() {
  if (!editingChatId.value || !editingTitle.value.trim()) return
  const renamedId = editingChatId.value
  await chats.rename(renamedId, editingTitle.value.trim())
  if (renamedId === activeChat.value?.id) bumpSidebarForActiveChat()
  editingChatId.value = null
  editingTitle.value = ''
}

/**
 * 取消编辑标题
 *
 * 取消标题编辑，清空编辑状态。
 */
function cancelEditTitle() {
  editingChatId.value = null
  editingTitle.value = ''
}

/**
 * 创建聊天
 *
 * 为当前选中的角色创建新的聊天会话。
 * 使用chatsStore.create（来自stores/chats.ts）创建聊天。
 *
 * @returns {Promise<void>} 完成时返回
 */
async function createChat() {
  if (!selectedCharacterId.value) return
  await chats.create(selectedCharacterId.value)
}

/**
 * 删除聊天
 *
 * 删除指定的聊天会话。
 * 使用chatsStore.remove（来自stores/chats.ts）删除聊天。
 *
 * @param {string} chatId - 聊天ID
 * @returns {Promise<void>} 完成时返回
 */
async function deleteChat(chatId: string) {
  await chats.remove(chatId)
}

async function handleBranchChat(chat: Chat) {
  try {
    const br = await chats.branchChat(chat.id)
    await afterChatReload(br.id)
  } catch (e: unknown) {
    await notifyMessage(e instanceof Error ? e.message : String(e), { title: '创建分支失败' })
  }
}

const showForkModal = ref(false)
const forkTargetMessage = ref<ChatMessage | null>(null)
const forkSubmitting = ref(false)
const forkLineage = ref<ForkLineageResponse | null>(null)
const forkLineageLoading = ref(false)

const outgoingForksByMessageId = computed(() => {
  const map: Record<string, { count: number; chats: ForkSiblingSummary[] }> = {}
  for (const g of forkLineage.value?.outgoingForks ?? []) {
    map[g.messageId] = { count: g.count, chats: g.chats }
  }
  return map
})

const forkModalDefaultTitle = computed(() => {
  const chat = activeChat.value
  if (!chat) return '分叉：新对话'
  return buildForkTitle(chat.title, chat.isGroup)
})

const forkModalPreview = computed(() => {
  const m = forkTargetMessage.value
  if (!m) return ''
  return forkMessagePreview(versions.getDisplayContent(m))
})

async function refreshForkLineage(chatId: string) {
  forkLineageLoading.value = true
  try {
    forkLineage.value = await chats.fetchForkLineage(chatId)
  } catch {
    forkLineage.value = null
  } finally {
    forkLineageLoading.value = false
  }
}

watch(
  () => chats.activeChatId,
  (id) => {
    if (id) void refreshForkLineage(id)
    else forkLineage.value = null
  },
  { immediate: true },
)

function onForkMessage(m: ChatMessage) {
  forkTargetMessage.value = m
  showForkModal.value = true
}

async function onConfirmFork(newChatName: string) {
  const chat = activeChat.value
  const msg = forkTargetMessage.value
  if (!chat || !msg) return
  forkSubmitting.value = true
  try {
    const created = await chats.forkChat(chat.id, msg.id, newChatName || undefined)
    showForkModal.value = false
    forkTargetMessage.value = null
    await afterChatReload(created.id)
    await nextTick()
    chatInputRef.value?.focusComposer?.()
  } catch (e: unknown) {
    await notifyMessage(e instanceof Error ? e.message : String(e), { title: '分叉失败' })
  } finally {
    forkSubmitting.value = false
  }
}

async function onNavigateForkSource() {
  const origin = forkLineage.value?.origin
  if (!origin) return
  try {
    await chats.load(origin.chatId)
    await afterChatReload(origin.chatId)
  } catch (e: unknown) {
    await notifyMessage(e instanceof Error ? e.message : String(e), { title: '无法打开源会话' })
  }
}

async function onSelectForkChild(chatId: string) {
  try {
    await chats.load(chatId)
    await afterChatReload(chatId)
  } catch (e: unknown) {
    await notifyMessage(e instanceof Error ? e.message : String(e), { title: '无法打开分叉会话' })
  }
}

/**
 * 选择聊天
 *
 * 加载并选择指定的聊天会话。
 * 使用chatsStore.load（来自stores/chats.ts）加载聊天数据。
 *
 * @param {Chat} chat - 聊天会话（来自types/models.ts）
 * @returns {Promise<void>} 完成时返回
 */
async function selectChat(chat: Chat) {
  await chats.load(chat.id)
  await afterChatReload(chat.id)
}

async function handleJanitorImported(payload: { chatId: string; characterId: string | null; openAfterImport: boolean }) {
  janitorPendingId.value = null
  try {
    sessionStorage.removeItem(JANITOR_CHAT_PENDING_STORAGE_KEY)
  } catch {
    // ignore
  }
  if (!payload.openAfterImport) return
  if (payload.characterId) {
    selectedCharacterId.value = payload.characterId
    await chats.loadList(payload.characterId)
  }
  await chats.load(payload.chatId)
  await afterChatReload(payload.chatId)
}

/**
 * 处理群聊创建
 *
 * 根据GroupCreatorModal传递的数据创建群聊。
 * 为每个成员创建默认设置，包括是否包含性格和场景描述。
 * 使用chatsStore.createGroup（来自stores/chats.ts）创建群聊。
 *
 * @param {object} data - 群聊创建数据
 * @param {string} data.title - 群聊标题
 * @param {string[]} data.memberIds - 成员ID列表
 * @param {boolean} data.pureAiMode - 是否纯AI模式
 * @param {string | null} data.firstMessageCharacterId - 首句发言角色ID
 * @param {Record<string, { includePersonality: boolean; includeScenario: boolean }>} data.memberInclusions - 成员包含项设置
 * @returns {Promise<void>} 完成时返回
 */
const showGroupCreator = ref(false)
/** 从单聊「转为群聊」时非空，用于 GroupCreatorModal 预选与 promote API */
const promoteSourceChat = ref<Chat | null>(null)

function openPromoteToGroup(chat: Chat) {
  promoteSourceChat.value = chat
  showGroupCreator.value = true
}

function onGroupCreatorShow(v: boolean) {
  showGroupCreator.value = v
  if (!v) promoteSourceChat.value = null
}

async function handleCreateGroup(data: {
  title: string
  memberIds: string[]
  pureAiMode: boolean
  firstMessageCharacterId: string | null
  memberInclusions: Record<string, { includePersonality: boolean; includeScenario: boolean }>
  groupSystemInjectDepth: number
  groupSystemAlwaysAtBottom: boolean
  groupMvuPreset: GroupMvuPreset
  groupMvuPresetCharacterId: string | null
  mvuMode: ChatMvuMode
  mvuDirective: string | null
  contentRegexRules: ChatContentRegexRule[]
  initialStateTables: import('../types/models').StatusTableDef[]
}) {
  const firstMember = data.memberIds[0]
  if (!firstMember) return

  const memberSettings: Record<string, GroupMemberSettings> = {}
  for (const id of data.memberIds) {
    const inc = data.memberInclusions[id] ?? { includePersonality: true, includeScenario: true }
    memberSettings[id] = {
      model: null,
      presetId: null,
      temperature: null,
      top_p: null,
      probability: 1.0,
      includePersonality: inc.includePersonality,
      includeScenario: inc.includeScenario,
    }
  }

  const personaId = data.pureAiMode ? null : effectiveSelectedPersonaId.value
  const src = promoteSourceChat.value
  if (src) {
    await chats.promoteToGroup(src.id, {
      title: data.title,
      memberIds: data.memberIds,
      pureAiMode: data.pureAiMode,
      memberSettings,
      userPersonaId: personaId ?? null,
      groupSystemInjectDepth: data.groupSystemInjectDepth,
      groupSystemAlwaysAtBottom: data.groupSystemAlwaysAtBottom,
    })
    promoteSourceChat.value = null
    return
  }

  await chats.createGroup(
    firstMember,
    data.memberIds,
    data.title,
    data.pureAiMode,
    data.firstMessageCharacterId,
    memberSettings,
    personaId ?? null,
    data.groupSystemInjectDepth,
    data.groupSystemAlwaysAtBottom,
    data.groupMvuPreset,
    data.groupMvuPresetCharacterId,
    {
      mvuMode: data.mvuMode,
      mvuDirective: data.mvuDirective,
      contentRegexRules: data.contentRegexRules,
      initialStateTables: data.initialStateTables,
    },
  )
}

/**
 * 打开创建角色
 *
 * 打开角色编辑弹窗，设置为新建模式。
 * 重置工作区助手聊天，加载助手状态，并尝试获取工作区中的角色卡数据。
 * 使用actions.openCreateCharacter（来自composables/useChatActions.ts）打开编辑。
 * 使用assistant.resetWorkspaceChat和loadState（来自composables/useAssistant.ts）管理助手状态。
 * 使用apiGet函数（来自api/http.ts）获取工作区角色卡。
 *
 * @returns {Promise<void>} 完成时返回
 */
async function openCreateCharacter() {
  actions.openCreateCharacter()
  await assistant.resetWorkspaceChat()
  void assistant.loadState('workspace')
  
  try {
    const res = await apiGet<{ ok: boolean; card: any }>('/api/assistant/workspace/character-card')
    if (res.ok && res.card) {
      actions.applyAssistantCard(res.card)
    }
  } catch (e) {
    console.log('No existing character card in workspace:', e)
  }
}

/**
 * 打开编辑角色
 *
 * 打开角色编辑弹窗，设置为编辑模式，加载角色数据。
 * 重置工作区助手聊天，加载助手状态。
 * 使用actions.openEditCharacter（来自composables/useChatActions.ts）打开编辑。
 * 使用assistant.resetWorkspaceChat和loadState（来自composables/useAssistant.ts）管理助手状态。
 *
 * @param {CharacterCard} card - 要编辑的角色卡片（来自types/models.ts）
 * @returns {Promise<void>} 完成时返回
 */
async function openEditCharacter(card: CharacterCard) {
  actions.openEditCharacter(card)
  await assistant.resetWorkspaceChat()
  void assistant.loadState('workspace')
}

/**
 * 保存角色
 *
 * 保存角色卡片，如果保存成功则选中该角色。
 * 删除工作区助手聊天，如果助手面板打开则加载聊天作用域状态。
 * 使用actions.saveCharacter（来自composables/useChatActions.ts）保存角色。
 * 使用assistant.deleteWorkspaceChat和loadState（来自composables/useAssistant.ts）管理助手状态。
 *
 * @returns {Promise<void>} 完成时返回
 */
async function saveCharacter() {
  const id = await actions.saveCharacter()
  if (id) {
    selectedCharacterId.value = id
  }
}

/**
 * 取消角色编辑
 *
 * 取消角色编辑，删除工作区助手聊天，如果助手面板打开则加载聊天作用域状态。
 * 使用actions.cancelCharacterEdit（来自composables/useChatActions.ts）取消编辑。
 * 使用assistant.deleteWorkspaceChat和loadState（来自composables/useAssistant.ts）管理助手状态。
 *
 * @returns {Promise<void>} 完成时返回
 */
async function cancelCharacterEdit() {
  actions.cancelCharacterEdit()
}

/**
 * 删除角色
 *
 * 删除指定的角色卡片。
 * 如果删除的是当前选中的角色，则选中第一个可用角色。
 * 使用actions.deleteCharacter（来自composables/useChatActions.ts）删除角色。
 *
 * @param {string} id - 角色ID
 * @returns {Promise<void>} 完成时返回
 */
async function deleteCharacter(id: string) {
  const nextId = await actions.deleteCharacter(id)
  if (selectedCharacterId.value === id) {
    selectedCharacterId.value = nextId
  }
}

/**
 * 确认切换身份（新建会话）
 *
 * 切换用户身份，并创建新的聊天会话。
 * 保存新的选中身份，然后基于当前聊天创建新会话（标题添加"（新建会话）"）。
 * 使用settingsStore.save（来自stores/settings.ts）保存设置。
 * 使用chatsStore.create或createGroup（来自stores/chats.ts）创建新会话。
 *
 * @returns {Promise<void>} 完成时返回
 */
async function confirmSwitchPersonaNewSession() {
  if (!settings.settings) return
  if (!actions.pendingPersonaId.value) return
  const targetId = actions.pendingPersonaId.value
  actions.showPersonaSwitchConfirm.value = false
  actions.pendingPersonaId.value = null

  await settings.save({ ...settings.settings, selectedPersonaId: targetId })
  if (!activeChat.value) return

  const title = `${activeChat.value.title}（新建会话）`
  const pure = group.effectivePureAiMode.value
  const personaId = pure ? null : targetId
  if (activeChat.value.isGroup) {
    await chats.createGroup(
      activeChat.value.characterId,
      [...activeChat.value.memberIds],
      title,
      pure,
      null,
      activeChat.value.memberSettings || null,
      personaId,
    )
  } else {
    await chats.create(activeChat.value.characterId, title, pure, personaId)
  }
}

/**
 * 确认切换身份（继续对话）
 *
 * 切换用户身份，但继续当前对话。
 * 先固化历史user消息的发送者快照，然后保存新的选中身份，更新聊天会话的身份ID。
 * 使用actions.freezeUserMessagesSenderSnapshot（来自composables/useChatActions.ts）固化快照。
 * 使用settingsStore.save（来自stores/settings.ts）保存设置。
 * 使用chatsStore.updateUserPersonaId（来自stores/chats.ts）更新聊天身份。
 *
 * @returns {Promise<void>} 完成时返回
 */
async function confirmSwitchPersonaContinue() {
  if (!settings.settings) return
  if (!actions.pendingPersonaId.value) return
  const targetId = actions.pendingPersonaId.value
  actions.showPersonaSwitchConfirm.value = false
  actions.pendingPersonaId.value = null
  
  await actions.freezeUserMessagesSenderSnapshot()
  await settings.save({ ...settings.settings, selectedPersonaId: targetId })
  if (activeChat.value) {
    await chats.updateUserPersonaId(activeChat.value.id, targetId)
  }
}

/**
 * 处理仅保存编辑的消息
 *
 * 保存编辑后的消息到服务器；若该消息有多版本，则同步更新当前版本内容与本地消息显示。
 *
 * @returns {Promise<void>} 完成时返回
 */
async function handleSaveEditedMessage() {
  const messageId = actions.editingMessageId.value
  const newContent = actions.editingMessageContent.value
  if (messageId && activeChat.value && newContent !== undefined) {
    const msg = activeChat.value.messages.find(m => m.id === messageId)
    if (msg) {
      const previousContent = versions.getDisplayContent(msg)
      if (versions.hasMultipleVersions(msg)) {
        versions.updateCurrentVersionContent(messageId, newContent)
      }
      invalidateTtsCacheIfTextChanged(msg, previousContent, newContent)
      msg.content = newContent
    }
  }
  await actions.saveEditedMessage()
}

/**
 * 处理保存并发送
 *
 * 保存编辑后的消息，删除该消息之后的所有消息，然后重新生成回复。
 * 支持单聊和群聊两种模式，支持流式和非流式两种生成方式。
 * 使用chatsStore.updateMessage和deleteMessage（来自stores/chats.ts）更新和删除消息。
 * 使用postAndConsumeSse函数（来自api/sse.ts）或apiPost函数（来自api/http.ts）发送请求。
 *
 * @returns {Promise<void>} 完成时返回
 */
async function handleSaveAndSend() {
  if (!activeChat.value) return
  if (!actions.editingMessageId.value) return
  if (isGenerating.value) return
  if (actions.editingMessageRole.value === 'assistant') return

  const chatId = activeChat.value.id
  const messageId = actions.editingMessageId.value
  const messageIndex = activeChat.value.messages.findIndex(msg => msg.id === messageId)
  if (messageIndex === -1) return

  const editedRole = actions.editingMessageRole.value
  const editedContent = replaceInputPlaceholders(actions.editingMessageContent.value)
  const originalMessage = activeChat.value.messages[messageIndex]
  if (!originalMessage) return

  const useStream = settings.settings?.streamEnabled !== false
  const isGroup = activeChat.value.isGroup
  const now = new Date().toISOString()
  const tailMessagesToDefer = activeChat.value.messages
    .slice(messageIndex + 1)
    .filter((m) => !m.id.startsWith('local_'))
  const tailIdsToDeleteOnSuccess = tailMessagesToDefer.map((x) => x.id)
  const singleAssistantTailMergeId =
    tailMessagesToDefer.length === 1 && tailMessagesToDefer[0]?.role === 'assistant'
      ? tailMessagesToDefer[0].id
      : null

  if (isGroup) {
    saveSendDeferCtx.value = {
      chatId,
      tailIdsToDeleteOnSuccess,
      singleAssistantTailMergeId,
      mode: 'group',
    }
    streamDeferDeleteIds.value = tailIdsToDeleteOnSuccess
    streamHiddenMessageIds.value = [...tailIdsToDeleteOnSuccess]

    await chats.updateMessage(chatId, messageId, editedRole, editedContent, originalMessage.characterId, {
      images: originalMessage.images ?? [],
      senderPersonaId: originalMessage.senderPersonaId ?? null,
      senderName: originalMessage.senderName ?? null,
      senderAvatar: originalMessage.senderAvatar ?? null,
    })
    bumpSidebarForActiveChat()

    actions.closeEditMessage()
    group.resetGroupState()

    group.showInterject()
    try {
      await chats.load(chatId)
      await afterChatReload(chatId)
      scrollToBottom(true, true)
    } catch {
      /* ignore */
    }
    await settings.load()
    return
  }

  const omitMessageIds = tailIdsToDeleteOnSuccess

  saveSendDeferCtx.value = {
    chatId,
    tailIdsToDeleteOnSuccess,
    singleAssistantTailMergeId,
    mode: 'single',
  }
  streamDeferDeleteIds.value = tailIdsToDeleteOnSuccess
  streamHiddenMessageIds.value = [...tailIdsToDeleteOnSuccess]

  await chats.updateMessage(chatId, messageId, editedRole, editedContent, originalMessage.characterId, {
    images: originalMessage.images ?? [],
    senderPersonaId: originalMessage.senderPersonaId ?? null,
    senderName: originalMessage.senderName ?? null,
    senderAvatar: originalMessage.senderAvatar ?? null,
  })
  bumpSidebarForActiveChat()

  actions.closeEditMessage()
  group.resetGroupState()

  streamError.value = null
  isGenerating.value = true
  aborter.value?.abort()
  aborter.value = new AbortController()

  try {
    const localAssistantId = `local_assistant_${Date.now()}`
    chatReasoningMessageId.value = localAssistantId
    chatReasoningContent.value = ''
    chatReasoningStreamActive.value = true
    markReasoningStreamPhaseStart()
    armAssistantRowEnterAnimation(localAssistantId)
    chats.addLocalMessage({ version: 1, id: localAssistantId, role: 'assistant', content: '', ts: now })
    scrollToBottom(false, true)

    if (useStream) {
        stream.registerStreamMessage(localAssistantId)
        try {
          await postAndConsumeSse(
            '/api/generate/stream',
            {
              chatId,
              userMessage: editedContent,
              appendUserMessage: false,
              imageFallbackMode: isImageStickyActive(),
              userPersona: selectedPersona.value ?? null,
              omitMessageIds,
              webSearchEnabled: webSearchSessionEnabled.value,
            },
            (evt) => {
              if (evt.event === 'delta') onAssistantContentDeltaStarted()
              if (shouldIgnoreStreamingEventWhileStopping(evt.event)) return
              if (evt.event === 'delta') {
                const data = evt.data as { text?: string } | undefined
                const t = data?.text
                if (typeof t === 'string') {
                  stream.appendDeltaBuffered(localAssistantId, t)
                }
              } else if (evt.event === 'reasoning') {
                const data = evt.data as { text?: string } | undefined
                const t = data?.text
                if (typeof t === 'string') {
                  chatReasoningContent.value += t
                }
              } else if (evt.event === 'done') {
                const data = evt.data as { assistantMessageId?: string } | undefined
                const serverId = data?.assistantMessageId
                if (serverId && chatReasoningContent.value) {
                  chatReasoningMessageId.value = serverId
                }
                pushCurrentReasoningToBlocks(serverId ?? undefined, localAssistantId)
              } else if (evt.event === 'error') {
                chatReasoningStreamActive.value = false
                clearReasoningPhaseTiming()
                const data = evt.data as { message?: string } | undefined
                streamError.value = String(data?.message ?? 'unknown error')
              }
            },
            aborter.value?.signal,
          )
        } finally {
          stream.flushForMessage(localAssistantId)
          stopRequested.value = false
        }
        void tryAutoReadAssistantAfterStreamFlush(localAssistantId)
      } else {
        const res = await apiPost<{ ok: boolean; content: string; reasoningContent?: string; assistantMessageId?: string | null; error?: string }>('/api/generate/stream', {
          chatId,
          userMessage: editedContent,
          appendUserMessage: false,
          imageFallbackMode: isImageStickyActive(),
          userPersona: selectedPersona.value ?? null,
          omitMessageIds,
          webSearchEnabled: webSearchSessionEnabled.value,
        })

        if (res.ok) {
          if (typeof res.reasoningContent === 'string') {
            chatReasoningContent.value = res.reasoningContent
          }
          pushCurrentReasoningToBlocks(res.assistantMessageId ?? undefined, localAssistantId)
          chats.appendLocalMessageContent(localAssistantId, res.content || '')
          scrollToBottom()
          void tryAutoReadAssistantAfterStreamFlush(localAssistantId)
        } else {
          streamError.value = res.error || 'unknown error'
        }
      }
  } catch (e: any) {
    if (!isAbortError(e)) {
      streamError.value = e?.message ?? String(e)
    }
  } finally {
    isGenerating.value = false
    group.currentSpeakerIndex.value = -1
    if (stopStreamingHold.value) {
      await persistLocalStreamingMessages(chatId)
      stopStreamingHold.value = false
    } else {
      await chats.load(chatId)
      await afterChatReload(chatId)

      const ss = saveSendDeferCtx.value
      if (
        ss &&
        ss.chatId === chatId &&
        ss.tailIdsToDeleteOnSuccess.length &&
        !streamError.value
      ) {
        saveSendDeferCtx.value = null
        streamHiddenMessageIds.value = []
        streamDeferDeleteIds.value = []
        await finalizeDeferredTailDelete(chatId, ss.tailIdsToDeleteOnSuccess)
      } else if (saveSendDeferCtx.value?.chatId === chatId) {
        saveSendDeferCtx.value = null
        streamHiddenMessageIds.value = []
        streamDeferDeleteIds.value = []
      }
    }
    await settings.load()
  }
}

/**
 * 计算编辑中的角色头像URL
 *
 * 根据编辑中的角色头像字段生成头像URL。
 */
const editingCharacterAvatarUrl = computed(() => {
  if (!actions.editingCharacter.value?.avatar) return null
  return `/api/avatars/${actions.editingCharacter.value.avatar}`
})

/**
 * 计算编辑中的身份头像URL
 *
 * 根据编辑中的身份头像字段生成头像URL。
 */
const editingPersonaAvatarUrl = computed(() => {
  if (!actions.editingPersona.value?.avatar) return null
  return `/api/avatars/${actions.editingPersona.value.avatar}`
})
</script>

<template>
  <div class="relative h-screen w-full overflow-hidden font-sans text-[var(--color-text)]">
    <div class="absolute inset-0 theme-page-bg"></div>
    <canvas
      v-if="effectiveWebgpuEnabled"
      ref="webgpuCanvasRef"
      class="pointer-events-none absolute inset-0 z-[1] h-full w-full"
      aria-hidden="true"
    ></canvas>
    <div v-if="showImageLayer" class="pointer-events-none absolute inset-0 z-[1] overflow-hidden">
      <img
        :src="pageBackground.imageUrl.value || ''"
        alt=""
        aria-hidden="true"
        class="page-background-image"
        :style="pageBackground.imageStyle.value"
      />
    </div>
    <div class="relative z-10 flex h-full w-full overflow-hidden">

    <!-- 左侧侧边栏 -->
    <ChatSidebar
      :is-narrow-portrait="isNarrowPortrait"
      :collapsed="sidebarCollapsed"
      :personas="settings.settings?.userPersonas || []"
      :selected-persona-id="effectiveSelectedPersonaId"
      :effective-pure-ai-mode="group.effectivePureAiMode.value"
      :characters="sidebarCharacters"
      :selected-character-id="selectedCharacterId"
      :chat-list="chats.list"
      :group-list="chats.groupList"
      :active-chat-id="chats.activeChatId"
      :editing-chat-id="editingChatId"
      :editing-title="editingTitle"
      @update:collapsed="sidebarCollapsed = $event"
      @update:selected-character-id="selectedCharacterId = $event"
      @update:editing-title="editingTitle = $event"
      @select-persona="actions.selectPersona"
      @edit-persona="actions.openEditPersona"
      @create-persona="actions.openCreatePersona"
      @delete-persona="actions.deletePersona"
      @edit-character="openEditCharacter"
      @create-character="openCreateCharacter"
      @delete-character="deleteCharacter"
      @select-chat="selectChat"
      @select-group="selectChat"
      @create-chat="createChat"
      @create-group="showGroupCreator = true"
      @promote-to-group="openPromoteToGroup"
      @branch-chat="handleBranchChat"
      @start-edit-title="startEditTitle"
      @save-title="saveTitle"
      @cancel-edit-title="cancelEditTitle"
      @delete-chat="deleteChat"
    />

    <!-- 右侧主区域 + 助手面板（侧栏折叠时保留与展开时 ml-4 一致的左侧留白；竖屏 overlay 时不再 pl-4 以免与 translate 重叠） -->
    <div class="flex-1 flex min-w-0 relative min-h-0 flex-col">
      <div
        class="flex-1 flex min-w-0 min-h-0 transition-[padding,transform] duration-300 ease-in-out overflow-x-hidden"
        :class="{ 'pl-4': sidebarCollapsed && !isNarrowPortrait }"
        :style="
          isNarrowPortrait && !sidebarCollapsed ? { transform: 'translateX(21rem)' } : {}
        "
      >
      <main ref="chatMainRef" class="flex-1 flex flex-col relative min-w-0 bg-transparent">
      
        <!-- 聊天内容区 -->
        <div v-if="(selectedCharacter || activeChat?.isGroup) && activeChat" class="flex flex-col h-full relative">
          <!-- 顶部标题栏 -->
          <!-- 磨砂仅放在独立底层；下拉菜单在上层，否则嵌套在父级 backdrop-filter 内时子级 backdrop 往往完全不生效 -->
          <header 
            ref="chatHeaderRef"
            class="relative flex flex-col pointer-events-none"
            :style="chatHeaderStyle"
          >
            <div
              class="pointer-events-none absolute inset-0 z-0 overflow-hidden theme-header-bg backdrop-blur-[var(--blur-heavy)] backdrop-saturate-[1.75]"
              :style="{
                borderRadius: chatHeaderStyle.borderRadius,
                transition: chatHeaderStyle.transition,
              }"
              aria-hidden="true"
            />
            <div class="relative z-[1] flex min-w-0 flex-col">
            <div class="flex items-start justify-between gap-4 px-6 pt-3 pb-2">
              <div class="pointer-events-auto flex min-w-0 flex-1 items-start gap-3">
                <div
                  v-if="activeChat.isGroup"
                  class="mt-1 shrink-0 text-[var(--color-purple)]"
                >
                  <Users class="w-4 h-4" />
                </div>
                <div class="min-w-0 flex-1">
                  <template v-if="activeChat.isGroup">
                    <div class="flex min-w-0 items-center gap-2">
                      <h2 class="truncate text-lg font-bold text-[var(--color-purple-text)]">{{ activeChat.title }}</h2>
                      <span class="shrink-0 rounded-full border border-[var(--color-border-subtle)] bg-surface-muted/70 px-2 py-0.5 text-[11px] text-[var(--color-text-muted)]">
                        {{ activeChat.memberIds.length }} 个角色
                      </span>
                    </div>
                  </template>
                  <template v-else>
                    <div class="flex min-w-0 items-center gap-2">
                      <h2 class="truncate text-lg font-bold text-[var(--color-text)]">{{ selectedCharacter?.name }}</h2>
                      <span class="text-[var(--color-text-muted)]">/</span>
                      <span class="truncate text-sm text-[var(--color-text-muted)]">{{ activeChat.title }}</span>
                    </div>
                  </template>
                </div>
              </div>

              <div class="pointer-events-auto shrink-0 flex items-start gap-2">
                <Transition name="header-search-trigger">
                  <button
                    v-if="!showChatSearch && !holdSearchChipUntilSearchPanelClosed"
                    key="hdr-search-trigger"
                    :class="['header-action-chip', { 'header-action-chip--icon': isNarrowPortrait }]"
                    :disabled="!activeChat"
                    @click="openChatSearchBar"
                  >
                    <Search class="w-3.5 h-3.5" />
                    <span v-if="isNarrowPortrait" class="sr-only">搜索当前会话，快捷键 Ctrl+F</span>
                    <span v-if="!isNarrowPortrait">搜索</span>
                    <span v-if="!isNarrowPortrait" class="header-action-shortcut">Ctrl+F</span>
                  </button>
                </Transition>
                <button
                  v-if="activeChat.isGroup"
                  :class="['header-action-chip', { 'header-action-chip--icon': isNarrowPortrait }]"
                  @click="showGroupSettings = true"
                >
                  <Settings class="w-3.5 h-3.5" />
                  <span v-if="isNarrowPortrait" class="sr-only">群聊设置</span>
                  <span v-if="!isNarrowPortrait">群聊</span>
                </button>
                <button
                  :class="['header-action-chip', { 'header-action-chip--icon': isNarrowPortrait }]"
                  @click="settingsTab = 'global'; showSettings = true"
                >
                  <Settings class="w-3.5 h-3.5" />
                  <span v-if="isNarrowPortrait" class="sr-only">设置</span>
                  <span v-if="!isNarrowPortrait">设置</span>
                </button>
                <div class="relative">
                  <button
                    ref="headerMoreButtonRef"
                    class="header-action-chip header-action-chip--icon"
                    :class="showHeaderMoreMenu ? 'header-action-chip--active' : ''"
                    :aria-expanded="showHeaderMoreMenu"
                    @click="toggleHeaderMoreMenu"
                  >
                    <MoreHorizontal class="w-4 h-4" />
                    <span class="sr-only">更多操作</span>
                  </button>
                  <Transition name="header-more-pop">
                    <div
                      v-if="showHeaderMoreMenu"
                      key="hdr-more-menu"
                      ref="headerMoreMenuRef"
                      class="header-more-menu backdrop-blur-[var(--blur-heavy)]"
                      role="menu"
                      aria-label="更多操作"
                    >
                      <button class="header-more-menu__item" role="menuitem" :disabled="!activeChat" @click="showExportModal = true; closeHeaderMoreMenu()">
                        <span class="header-more-menu__label">导出当前会话</span>
                        <span class="header-more-menu__meta">聊天记录</span>
                      </button>
                      <button class="header-more-menu__item" role="menuitem" @click="showImportModal = true; closeHeaderMoreMenu()">
                        <span class="header-more-menu__label">导入会话</span>
                        <span class="header-more-menu__meta">JSON / 扩展来源</span>
                      </button>
                    </div>
                  </Transition>
                </div>
              </div>
            </div>

            <div
              v-if="showChatSearch"
              class="px-6 pb-2 pointer-events-auto"
            >
              <div
                class="chat-header-search-expand"
                :class="{ 'chat-header-search-expand--open': chatSearchExpandOpen }"
                :style="{
                  '--chat-search-expand-ms': `${SEARCH_OPEN_EXPAND_MS}ms`,
                  '--chat-search-collapse-ms': `${SEARCH_EXPAND_COLLAPSE_MS}ms`,
                  '--chat-search-content-ms': `${SEARCH_CLOSE_CONTENT_MS}ms`,
                }"
              >
                <div class="chat-header-search-expand-inner">
                  <div
                    class="chat-header-search-reveal-layer"
                    :class="{ 'chat-header-search-reveal-layer--visible': chatSearchContentRevealed }"
                  >
                    <div class="chat-header-search-panel-inner flex items-center gap-3 py-1.5">
                      <div class="flex shrink-0 items-center gap-2 border-r border-[var(--color-border-subtle)] pr-3">
                        <span class="flex h-7 w-7 items-center justify-center rounded-lg bg-surface-muted/80 text-[var(--color-text-secondary)]">
                          <Search class="w-4 h-4" />
                        </span>
                        <div class="leading-tight">
                          <div class="text-xs text-[var(--color-text-secondary)]">会话搜索</div>
                          <div class="text-[11px] text-[var(--color-text-muted)]">
                            {{ chatSearchHitsForNav.length ? (chatSearchCursor < 0 ? `—/${chatSearchHitsForNav.length}` : `${chatSearchCursor + 1}/${chatSearchHitsForNav.length}`) : (chatSearchLoading ? '搜索中...' : '输入后定位消息') }}
                          </div>
                        </div>
                      </div>

                      <input
                        ref="chatSearchInputRef"
                        v-model="chatSearchQuery"
                        class="min-w-0 flex-1 bg-transparent text-sm outline-none"
                        placeholder="搜索当前会话"
                        @keydown.enter.prevent="runChatSearch"
                        @keydown.esc.prevent="closeChatSearchBar"
                      />

                      <button class="btn btn-xs btn-secondary shrink-0" @click="goToPrevSearchResult">上一个</button>
                      <button class="btn btn-xs btn-secondary shrink-0" @click="goToNextSearchResult">下一个</button>
                      <button class="btn btn-xs btn-secondary shrink-0" @click="closeChatSearchBar">
                        关闭
                      </button>
                    </div>

                    <div
                      v-if="chatSearchChipsDisplayHits.length > 0 || chatSearchChipsCollapsing"
                      class="chat-search-chips-expand mt-2"
                      :class="{ 'chat-search-chips-expand--open': chatSearchChipsGridOpen }"
                      :style="{ '--chat-search-chips-ms': `${SEARCH_CLOSE_CONTENT_MS}ms` }"
                    >
                      <div class="chat-search-chips-expand-inner">
                        <div
                          v-if="chatSearchChipsDisplayHits.length > 0"
                          class="flex items-stretch gap-2 overflow-x-auto overflow-y-hidden max-h-48 py-1"
                        >
                          <button
                            v-for="(hit, idx) in chatSearchChipsDisplayHits"
                            :key="`${hit.messageId}_${hit.messageIndex}`"
                            class="inline-flex w-[220px] shrink-0 items-start rounded-lg border border-[var(--color-border-subtle)] px-3 py-2 text-left text-xs transition-colors hover:bg-surface-muted"
                            :class="idx === chatSearchCursor ? 'bg-surface-muted' : 'bg-surface-muted/55'"
                            @click="jumpToSearchResult(idx)"
                          >
                            {{ hit.snippet }}
                          </button>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <!-- 群成员头像行 -->
            <Transition name="chat-header-groupstrip">
            <div v-if="activeChat.isGroup && groupMembers.length > 0" key="hdr-group-strip" class="px-6 pb-2 pointer-events-auto">
              <div class="flex items-center gap-3 overflow-x-auto rounded-xl border border-[var(--color-border-subtle)] bg-surface-overlay/55 px-3 py-2">
                <div class="shrink-0 text-[11px] tracking-[0.08em] text-[var(--color-text-muted)]">
                  成员
                </div>
                <div 
                  v-for="(member, idx) in groupMembers" 
                  :key="member.id"
                  class="flex items-center gap-1.5 shrink-0 rounded-full border border-[var(--color-border-subtle)] bg-surface-muted/80 px-2.5 py-1 transition-colors group/member"
                  :class="group.canInterject.value ? 'cursor-pointer hover:bg-[var(--color-purple-bg)]' : ''"
                  @click="group.canInterject.value && triggerInterject(member.id)"
                >
                  <span class="text-[10px] text-[var(--color-text-muted)]">{{ idx + 1 }}</span>
                  <ModernAvatar 
                    :src="member.avatar ? `/api/avatars/${member.avatar}` : null" 
                    :name="member.name" 
                    :size="20" 
                    aspect="1"
                    rounded="rounded"
                  />
                  <span class="max-w-[72px] truncate text-xs text-[var(--color-text-secondary)]">{{ member.name }}</span>
                  <span 
                    v-if="group.getMemberSettings(member.id).probability < 1" 
                    class="rounded-full border border-[var(--color-warning)]/20 bg-[var(--color-warning-bg)] px-1.5 py-0.5 text-[10px] leading-none text-[var(--color-warning-text)]"
                  >
                    {{ Math.round(group.getMemberSettings(member.id).probability * 100) }}%
                  </span>
                </div>
                <div v-if="!group.effectivePureAiMode.value" class="flex items-center gap-1.5 shrink-0 rounded-full border border-brand-a20 bg-brand-a10 px-2.5 py-1">
                  <ModernAvatar :src="userAvatarUrl" :name="userName" :size="20" aspect="1" rounded="rounded" />
                  <span class="max-w-[72px] truncate text-xs text-brand">{{ userName }}</span>
                  <span class="text-[10px] text-brand-a60">你</span>
                </div>
              </div>
            </div>
            </Transition>
            </div>
          </header>

          <!-- 消息列表：MVU 状态条叠在列表与输入区交界处（贴底），正文滚动从其下方穿过 -->
          <div class="relative flex min-h-0 min-w-0 flex-1 flex-col overflow-visible">
            <div
              v-if="mvuStore.capsuleData.length > 0"
              class="pointer-events-none absolute inset-x-0 bottom-0 z-30 overflow-visible"
            >
              <div class="pointer-events-auto mx-auto w-full max-w-4xl px-4">
                <StateVariablesBar
                  :capsules="mvuStore.capsuleData"
                  :is-running="mvuStore.isRunning"
                  :chat-id="activeChat.id"
                  @toggle-panel="mvuPanelOpen = !mvuPanelOpen"
                  @wrap-extra-height-change="updateMvuStateBarWrapExtraHeight"
                />
              </div>
            </div>
          <ForkLineageBanner
            :lineage="forkLineage"
            :loading="forkLineageLoading"
            @navigate-source="onNavigateForkSource"
          />
          <MessageList
            ref="messageListRef"
            :chat-id="activeChat.id"
            :messages="messageListMessages"
            :is-group="activeChat.isGroup"
            :selected-character="selectedCharacter"
            :characters="characters.list"
            :selected-persona="selectedPersona"
            :user-name="userName"
            :user-avatar-url="userAvatarUrl"
            :character-avatar-url="characterAvatarUrl"
            :is-generating="isGenerating"
            :is-interjecting="group.isInterjecting.value"
            :reasoning-message-id="chatReasoningMessageId"
            :reasoning-content="chatReasoningContent"
            :reasoning-stream-active="chatReasoningStreamActive"
            :reasoning-duration-sec-override="chatReasoningElapsedSec"
            :reasoning-blocks="chatReasoningBlocks"
            :get-display-content="versions.getDisplayContent"
            :get-display-reasoning="versions.getDisplayReasoning"
            :has-multiple-versions="versions.hasMultipleVersions"
            :get-current-version-index="versions.getCurrentVersionIndex"
            :get-version-count="versions.getVersionCount"
            :header-inset-px="chatHeaderHeightPx"
            :bottom-scroll-extra-px="mvuStateBarWrapExtraHeightPx"
            :sidebar-collapsed="sidebarCollapsed"
            :entrancing-user-message-id="entrancingUserMessageId"
            :entrancing-assistant-message-id="entrancingAssistantMessageId"
            :content-regex-rules="effectiveContentRegexRules"
            :outgoing-forks-by-message-id="outgoingForksByMessageId"
            @edit-message="(m) => actions.openEditMessage(m, versions.getDisplayContent(m))"
            @delete-message="actions.deleteMessage"
            @read-aloud-message="handleReadAloudMessage"
            @rewrite-message="handleRewriteMessage"
            @switch-previous-version="handleSwitchPreviousVersion"
            @switch-next-version="handleSwitchNextVersion"
            @fork-message="onForkMessage"
            @select-fork-child="onSelectForkChild"
          />
          </div>

          <!-- 输入区域 -->
          <ChatInput
            ref="chatInputRef"
            v-model="draftMessage"
            :sidebar-collapsed="sidebarCollapsed"
            :is-narrow-portrait="isNarrowPortrait"
            :header-morph-phase="headerMorphPhase"
            :show-agent-top-bar-controls="agentTopBarControlsVisible"
            :tts-enabled="!!settings.settings?.ttsEnabled"
            :tts-top-bar-controls-visible="ttsTopBarControlsVisible"
            :content-area-left-px="contentAreaLeftPx"
            :assistant-fab-min-top-px="chatAssistantFabMinTopPx"
            :on-assistant-fab-layout="() => runChatFabSeparation(null)"
            :on-assistant-fab-drag-end="() => runChatFabSeparation('assistant')"
            :on-assistant-fab-snap-end="() => runChatFabSeparation('assistant')"
            :is-generating="isGenerating"
            :stream-error="streamError"
            :draft-images="draftImages"
            :draft-helper-status="draftHelper.status"
            :is-group="activeChat.isGroup"
            :group-members="groupMembers"
            :current-speaker-index="group.currentSpeakerIndex.value"
            :is-paused="group.isPaused.value"
            :show-continue-button="group.showContinueButton.value"
            :pending-members-count="group.pendingMembers.value.length"
            :can-interject="group.canInterject.value"
            :is-interjecting="group.isInterjecting.value"
            :effective-pure-ai-mode="group.effectivePureAiMode.value"
            :is-streaming-active="isStreamingActive"
            :user-avatar-url="userAvatarUrl"
            :user-name="userName"
            :current-model="currentModel"
            :current-preset-id="activeChat?.overrides?.presetId ?? null"
            :model-options="chatModelOptions"
            :get-member-settings="group.getMemberSettings"
            @send="sendUserMessage"
            @primary-action="handlePrimaryAction"
            @pause-group="group.pauseGroupChat"
            @continue-group="continueGroupChat"
            @trigger-interject="triggerInterject"
            @select-model="handleModelSelect"
            @toggle-assistant="assistant.isAssistantPanelOpen.value = !assistant.isAssistantPanelOpen.value"
            @focus-assistant-panel="switchFromMvuToAssistantPanel"
            @select-images="handleSelectImages"
            @remove-image="handleRemoveDraftImage"
            @open-draft-helper="handleOpenDraftHelper"
            @draft-helper-keep="handleDraftHelperKeep"
            @draft-helper-rewrite="handleDraftHelperRewrite"
            @draft-helper-discard="handleDraftHelperDiscard"
            @draft-helper-stop="handleDraftHelperStop"
            @toggle-mvu-panel="mvuPanelOpen = !mvuPanelOpen"
            :web-search-enabled="webSearchSessionEnabled"
            @update:web-search-enabled="webSearchSessionEnabled = $event"
          />

          <!-- TTS 播放/下载 FAB（仅在 TTS 启用时显示） -->
          <TtsPlaybackFab
            v-if="settings.settings?.ttsEnabled"
            ref="ttsPlaybackFabRef"
            :is-downloading="ttsIsDownloading"
            :is-playing="ttsIsPlaying"
            :audio-paused="ttsAudioPaused"
            :queue-items="ttsQueuePanelItems"
            :content-area-left-px="contentAreaLeftPx"
            :min-top-px="chatAssistantFabMinTopPx"
            :input-sink-active="ttsInputSinkActive"
            :show-top-bar-controls="ttsTopBarControlsVisible"
            :on-tts-fab-layout="() => runChatFabSeparation(null)"
            :on-tts-fab-drag-end="() => runChatFabSeparation('tts')"
            :on-tts-fab-snap-end="() => runChatFabSeparation('tts')"
            @abort-download="ttsQueue.abortAllDownloads()"
            @toggle-play-pause="ttsQueue.togglePlayPause()"
          />
        </div>

        <!-- 空状态：勿用整层 opacity 压暗（子元素无法抵消）；弱化用语义色，保证文字清晰、不糊 -->
        <div v-else class="relative flex flex-col items-center justify-center h-full text-center p-8">
          <div class="absolute top-4 right-4 pointer-events-auto flex items-center gap-2">
            <button class="btn btn-sm btn-secondary" disabled>
              导出
            </button>
            <button class="btn btn-sm btn-secondary" @click="showImportModal = true">
              导入
            </button>
            <button class="btn btn-sm btn-secondary" @click="settingsTab = 'global'; showSettings = true">
              设置
            </button>
          </div>
          <div class="flex flex-col items-center">
            <h3 class="text-xl font-bold text-[var(--color-text-secondary)] mb-2">未打开会话</h3>
            <p class="text-[var(--color-text-muted)] mb-8 leading-relaxed px-4 max-w-[468px] w-full">从左侧选择角色以进入现有会话或新建会话。如果还没有角色，先创建一个。</p>
            <button class="bg-brand text-on-brand px-6 py-2 rounded-xl hover:bg-brand-hover transition-colors" @click="openCreateCharacter">
              创建角色
            </button>
          </div>
        </div>
      </main>
      </div>

    <!-- 聊天助手面板 -->
    <AssistantPanel
      :show-tool-permission-toggles="true"
      :is-open="assistant.isAssistantPanelOpen.value"
      :messages="assistant.assistantMessages.value"
      :draft="assistant.assistantDraft.value"
      :draft-attachments="assistant.assistantDraftAttachments.value"
      :chat-id="activeChat?.id ?? null"
      :is-generating="assistant.isAssistantGenerating.value"
      :stream-error="assistant.assistantStreamError.value"
      :streaming-content="assistant.assistantStreamingContent.value"
      :streaming-reasoning="assistant.assistantStreamingReasoning.value"
      :reasoning-stream-phase-active="assistant.assistantReasoningStreamPhaseActive.value"
      :reasoning-elapsed-sec="assistant.assistantReasoningElapsedSec.value"
      :allow-write-memory="assistant.allowWriteMemoryEnabled.value"
      :allow-destructive-tools="assistant.allowDestructiveToolsEnabled.value"
      :allow-web-search="assistant.allowWebSearchEnabled.value"
      :current-model="assistantCurrentModel"
      :current-preset-id="assistant.assistantSettings.value.presetId ?? null"
      :model-options="chatModelOptions"
      @update:is-open="assistant.isAssistantPanelOpen.value = $event"
      @update:draft="assistant.assistantDraft.value = $event"
      @attach-files="handleAssistantDraftFiles('chat', $event)"
      @remove-attachment="assistant.removeDraftAttachment('chat', $event)"
      @toggle-write-memory="assistant.toggleAllowWriteMemory"
      @toggle-destructive="assistant.toggleAllowDestructiveTools"
      @toggle-web-search="assistant.toggleAllowWebSearch"
      @send="assistant.sendMessage('chat')"
      @reset="assistant.resetChat"
      @open-settings="assistant.showAssistantSettings.value = true"
      @select-model="assistant.handleModelSelect"
      @edit-message="(m) => assistant.openEditMessage(m, 'chat')"
      @delete-message="(m) => assistant.deleteMessage(m, 'chat')"
      @rewrite-message="(m) => assistant.rewriteMessage(m, 'chat')"
      @switch-to-mvu="switchFromAssistantToMvuPanel"
    />

    <MvuPanel
      :is-open="mvuPanelOpen"
      :logs="mvuStore.workLogs"
      :has-knowledge-graph="mvuStore.hasKnowledgeGraph"
      :running="mvuStore.isRunning"
      :mvu-model="settings.settings?.mvuModel ?? null"
      :model-options="chatModelOptions"
      :resolved-mvu-model="mvuResolvedModelForPanel"
      @update:is-open="mvuPanelOpen = $event"
      @select-mvu-model="onMvuPanelMvuModelSelect"
      @switch-to-assistant="switchFromMvuToAssistantPanel"
      @open-knowledge-graph="openKnowledgeGraphModal"
    />

    <KnowledgeGraphModal
      v-model:show="knowledgeGraphModalOpen"
      :chat-id="activeChat?.id ?? null"
    />

    </div>

    <ErrorModal
      v-for="(item, index) in errorStack.items.value"
      :key="item.id"
      :item="item"
      :offset-y="(errorStack.items.value.length - 1 - Number(index)) * 14"
      :z-index="1200 + Number(index)"
      @close="errorStack.removeError"
      @pause="errorStack.pauseTimer"
      @resume="errorStack.resumeTimer"
    />

    <div v-if="imageFallbackDialog.visible" class="fixed inset-0 z-[1400] flex items-center justify-center">
      <div class="absolute inset-0 bg-overlay-heavy backdrop-blur-sm" @click="imageFallbackDialog.visible = false"></div>
      <div class="relative w-[min(640px,calc(100vw-2rem))] rounded-xl border border-red-500/30 bg-red-500/10 p-4">
        <h3 class="text-sm font-bold text-red-200 mb-2">模型不支持图片或图片请求失败</h3>
        <pre class="text-xs text-red-100 whitespace-pre-wrap break-words max-h-[260px] overflow-auto">{{ imageFallbackDialog.error }}</pre>
        <div class="mt-4 flex justify-end gap-2">
          <button class="btn btn-sm btn-secondary" @click="imageFallbackDialog.visible = false">返回</button>
          <button
            class="btn btn-sm btn-primary"
            @click="imageFallbackDialog.retryAction && imageFallbackDialog.retryAction()"
          >
            清除图片重试
          </button>
        </div>
      </div>
    </div>

    <!-- 助手设置抽屉 -->
          <!-- 消息编辑弹窗 -->
    <MessageForkModal
      v-model:show="showForkModal"
      :message-preview="forkModalPreview"
      :default-title="forkModalDefaultTitle"
      :is-submitting="forkSubmitting"
      @confirm="onConfirmFork"
    />

    <MessageEditorModal
      :show="actions.showMessageEditor.value"
      :message-id="actions.editingMessageId.value"
      :message-role="actions.editingMessageRole.value"
      :message-content="actions.editingMessageContent.value"
      :character-avatar-url="characterAvatarUrl"
      :user-avatar-url="userAvatarUrl"
      :is-generating="isGenerating"
      @update:show="actions.showMessageEditor.value = $event"
      @update:message-role="actions.editingMessageRole.value = $event"
      @update:message-content="actions.editingMessageContent.value = $event"
      @save="handleSaveEditedMessage"
      @save-and-send="handleSaveAndSend"
    />

    <!-- 助手消息编辑弹窗 -->
    <MessageEditorModal
      :show="assistant.showAssistantMessageEditor.value"
      :message-id="assistant.editingAssistantMessage.value?.id || null"
      :message-role="(assistant.editingAssistantMessage.value?.role === 'tool' || assistant.editingAssistantMessage.value?.role === 'reasoning' ? 'assistant' : assistant.editingAssistantMessage.value?.role) || 'user'"
      :message-content="assistant.editingAssistantMessageContent.value"
      :character-avatar-url="null"
      :user-avatar-url="null"
      :is-generating="assistant.isAssistantGenerating.value || assistant.isWorkspaceAssistantGenerating.value"
      @update:show="assistant.showAssistantMessageEditor.value = $event"
      @update:message-role="(r) => { if (assistant.editingAssistantMessage.value) assistant.editingAssistantMessage.value.role = r }"
      @update:message-content="assistant.editingAssistantMessageContent.value = $event"
      @save="assistant.saveEditedMessage"
      @save-and-send="assistant.saveEditedMessageAndSend" 
    />

    <!-- 设置抽屉 -->
    <SettingsDrawer 
      v-model:show="showSettings" 
      :chat="activeChat" 
      :initial-tab="settingsTab" 
      @open-member-settings="actions.openMemberSettingsEditor"
      @open-knowledge-graph="openKnowledgeGraphModal"
    />

    <ChatExportModal
      v-model:show="showExportModal"
      :disabled="!activeChat"
      @export="(format) => {
        if (format === 'character') actions.exportCharacter(false)
        else if (format === 'character_with_worldbooks') actions.exportCharacter(true)
        else actions.exportChat(format)
        showExportModal = false
      }"
    />

    <ChatImportModal
      v-model:show="showImportModal"
      :characters="characters.list"
      :personas="settings.settings?.userPersonas || []"
      :pending-id="janitorPendingId"
      :pending-reload-nonce="janitorPendingReloadNonce"
      :push-error="(p) => errorStack.pushError(p)"
      @janitor-imported="handleJanitorImported"
    />

    <!-- 群聊创建弹窗 -->
    <GroupCreatorModal
      :show="showGroupCreator"
      :characters="characters.list"
      :migrate-from-chat-id="promoteSourceChat?.id ?? null"
      :initial-member-ids="promoteSourceChat ? [promoteSourceChat.characterId] : []"
      :initial-title="promoteSourceChat?.title ?? ''"
      :locked-member-ids="promoteSourceChat ? [promoteSourceChat.characterId] : []"
      @update:show="onGroupCreatorShow"
      @create="handleCreateGroup"
    />

    <!-- 成员设置弹窗 -->
    <GroupSettingsModal
      v-model:show="showGroupSettings"
      :chat="activeChat"
      :characters="characters.list"
      @apply="handleGroupSettingsApply"
      @open-member-settings="actions.openMemberSettingsEditor"
    />

    <MemberSettingsModal
      :show="!!actions.editingMemberId.value"
      :member-id="actions.editingMemberId.value"
      :settings="actions.editingMemberSettings.value"
      :character="actions.editingMemberId.value ? characters.list.find(c => c.id === actions.editingMemberId.value) || null : null"
      :model-options="chatModelOptions"
      @update:show="(v) => !v && actions.closeMemberSettingsEditor()"
      @update:settings="actions.editingMemberSettings.value = $event"
      @save="actions.saveMemberSettings"
    />
    </div>
  </div>

<!-- 角色编辑弹窗 -->
  <div v-if="actions.showCharacterEditor.value" class="modal">
    <div class="modal-backdrop" @click="cancelCharacterEdit"></div>
    <div class="modal-content chat-modal-width-1200-90 glass-panel theme-panel-bg backdrop-blur-2xl backdrop-saturate-[1.8] border border-[var(--color-border)]">
      <div class="modal-header">
        <h3 class="modal-title">{{ actions.isNewCharacter.value ? '新建角色' : '编辑角色' }}</h3>
        <button class="modal-close" @click="cancelCharacterEdit">
            <X class="w-5 h-5" />
        </button>
      </div>
      <div
        class="modal-body"
        :class="isNarrowPortrait ? 'max-h-[min(90dvh,800px)] min-h-0 overflow-x-hidden overflow-y-auto' : ''"
      >
        <div
          v-if="actions.editingCharacter.value"
          class="flex min-h-0 min-w-0"
          :class="isNarrowPortrait ? 'flex-col gap-4' : 'gap-6 h-[70vh]'"
        >
          <div
            class="min-h-0 min-w-0 pr-2 custom-scrollbar"
            :class="
              isNarrowPortrait
                ? 'shrink-0'
                : 'min-w-[min(50%,18rem)] flex-1 basis-0 overflow-y-auto'
            "
          >
            <div class="space-y-6">
              <div class="flex gap-6">
                <div class="flex flex-col items-center gap-3">
                  <ModernAvatar 
                    :src="editingCharacterAvatarUrl"
                    :size="120"
                    aspect="auto"
                    object-fit="cover"
                    :object-position="avatarObjectPositionByFocus(actions.editingCharacter.value.avatarFocusX, actions.editingCharacter.value.avatarFocusY)"
                    rounded="rounded-xl"
                    class="border-2 border-brand-a40 shadow-heavy bg-surface-overlay"
                  />
                  <button class="btn btn-sm btn-secondary" @click="actions.showCharacterAvatarCropper.value = true">更换头像</button>
                </div>
                <div class="flex-1 space-y-4">
                  <div class="form-group">
                    <label class="label">
                      <span>名称</span>
                      <span class="opacity-60 text-xs ml-2 text-brand">该项参与对话</span>
                    </label>
                    <input v-model="actions.editingCharacter.value.name" class="input" placeholder="角色名称" />
                  </div>
                  <div class="form-group">
                    <label class="label">简介</label>
                    <textarea v-model="actions.editingCharacter.value.description" class="input textarea h-20" placeholder="简短描述"></textarea>
                  </div>
                </div>
              </div>

              <div class="form-group">
                <label class="label">
                  <span>Personality（性格/外貌）</span>
                  <span class="opacity-60 text-xs ml-2 text-brand">该项参与对话</span>
                </label>
                <textarea v-model="actions.editingCharacter.value.personality" class="input textarea h-32" placeholder="详细设定..."></textarea>
              </div>

              <div class="form-group">
                <label class="label">
                  <span>Scenario（情景/世界观）</span>
                  <span class="opacity-60 text-xs ml-2 text-brand">该项参与对话</span>
                </label>
                <textarea v-model="actions.editingCharacter.value.scenario" class="input textarea h-24" placeholder="世界背景..."></textarea>
              </div>

              <div class="form-group">
                <label class="label">
                  <span>系统提示词</span>
                  <span class="opacity-60 text-xs ml-2 text-brand">该项参与对话</span>
                </label>
                <textarea v-model="actions.editingCharacter.value.systemPrompt" class="input textarea h-32" placeholder="回复格式要求..."></textarea>
              </div>

              <div class="form-group rounded-xl border border-[var(--color-border-subtle)] bg-surface-overlay/80 p-4 space-y-3">
                <label class="label">
                  <span>MVU 能力</span>
                </label>
                <label class="inline-flex items-center gap-2 text-sm text-[var(--color-text-secondary)] cursor-pointer select-none">
                  <ThemedCheckbox
                    :checked="actions.editingCharacter.value.mvuEnabled === true"
                    @update:checked="(v) => (actions.editingCharacter.value!.mvuEnabled = v)"
                  />
                  <span>启用 MVU 管线</span>
                </label>
                <MvuCapabilityEditor
                  :mvu-mode="actions.editingCharacter.value.mvuMode ?? 'regex'"
                  :mvu-directive="actions.editingCharacter.value.mvuDirective ?? ''"
                  :content-regex-rules="actions.editingCharacter.value.contentRegexRules || []"
                  :initial-state-tables="actions.editingCharacter.value.initialStateTables || []"
                  :allow-inherit="false"
                  tables-subtitle="新会话自动写入"
                  tables-empty-hint="暂无状态表格。新建表格后，新会话将自带初始状态栏。"
                  @update:mvu-mode="(v) => { if (actions.editingCharacter.value) actions.editingCharacter.value.mvuMode = (v ?? 'regex') as MvuMode }"
                  @update:mvu-directive="(v) => { if (actions.editingCharacter.value) actions.editingCharacter.value.mvuDirective = v }"
                  @update:content-regex-rules="(v) => { if (actions.editingCharacter.value) actions.editingCharacter.value.contentRegexRules = v }"
                  @update:initial-state-tables="(v) => { if (actions.editingCharacter.value) actions.editingCharacter.value.initialStateTables = v }"
                />
              </div>

              <div class="form-group">
                <label class="label">
                  <span>首句</span>
                  <span class="opacity-60 text-xs ml-2" v-pre>支持 {{user}} 占位符</span>
                  <span class="opacity-60 text-xs ml-2 text-brand">该项参与对话</span>
                </label>
                <textarea v-model="actions.editingCharacter.value.firstMessage" class="input textarea h-24" placeholder="开场白..."></textarea>
              </div>

              <div class="form-group">
                <label class="label">
                  <span>额外首句</span>
                  <span class="opacity-60 text-xs ml-2" v-pre>支持 {{user}} 占位符</span>
                  <span class="opacity-60 text-xs ml-2 text-brand">该项参与对话</span>
                </label>
                <div class="overflow-x-auto custom-scrollbar rounded-lg border border-[var(--color-border-subtle)] bg-surface-overlay/50 p-2">
                  <div class="flex w-full min-w-0 min-h-[6.5rem] flex-nowrap items-stretch gap-2">
                    <textarea
                      v-model="extraFirstMessageDraft"
                      class="input textarea h-24 max-w-full shrink-0"
                      :style="{
                        width: hasAnyExtraFirstEntries ? 'min(50%, 18rem)' : 'min(70%, 28rem)',
                      }"
                      placeholder="其他开场情景..."
                    />
                    <div class="flex shrink-0 flex-col justify-center gap-1.5">
                      <button
                        type="button"
                        class="inline-flex h-9 w-9 items-center justify-center rounded-md border border-[var(--color-border-subtle)] bg-surface-overlay text-[var(--color-text-secondary)] hover:bg-surface-muted transition-colors"
                        aria-label="追加为草稿（保留输入框）"
                        @click="appendExtraFirstMessageCheck"
                      >
                        <Check class="w-[18px] h-[18px]" />
                      </button>
                      <button
                        type="button"
                        class="inline-flex h-9 w-9 items-center justify-center rounded-md border border-[var(--color-border-subtle)] bg-surface-overlay text-[var(--color-text-secondary)] hover:bg-surface-muted transition-colors"
                        aria-label="追加为已保存并清空输入"
                        @click="appendExtraFirstMessagePlus"
                      >
                        <Plus class="w-[18px] h-[18px]" />
                      </button>
                    </div>
                    <div
                      v-if="extraFirstMessageEntriesIndexed.length"
                      class="flex shrink-0 items-stretch gap-2"
                    >
                      <div
                        v-for="entry in extraFirstMessageEntriesIndexed"
                        :key="entry.index"
                        class="flex shrink-0 items-start gap-1"
                      >
                        <button
                          type="button"
                          class="shrink-0 inline-flex flex-col items-start text-left px-3 py-2 text-xs border rounded-md hover:bg-surface-muted transition-colors w-[200px] min-h-[4.5rem] max-h-28 overflow-y-auto custom-scrollbar bg-surface-muted/80 text-[var(--color-text)]"
                          :class="
                            extraEntryIsEmpty(entry)
                              ? 'border-dashed border-[var(--color-border)] text-[var(--color-text-muted)]'
                              : 'border-[var(--color-border-subtle)]'
                          "
                          @click="fillExtraFirstDraft(entry.text)"
                        >
                          <span
                            v-if="entry.chip"
                            class="mb-1 shrink-0 rounded px-1 py-0.5 text-[10px] bg-brand-a10 text-brand border border-brand-a20"
                          >已保存</span>
                          <span
                            v-else
                            class="mb-1 shrink-0 rounded px-1 py-0.5 text-[10px] text-[var(--color-text-muted)] border border-[var(--color-border-subtle)]"
                          >草稿</span>
                          <span class="whitespace-pre-wrap break-words">{{ displayExtraEntryLabel(entry) }}</span>
                        </button>
                        <button
                          type="button"
                          class="shrink-0 inline-flex h-7 w-7 items-center justify-center rounded border border-[var(--color-border-subtle)] text-[var(--color-text-muted)] hover:bg-surface-muted hover:text-[var(--color-text)]"
                          aria-label="从列表移除此条"
                          @click.stop="removeExtraFirstMessageAt(entry.index)"
                        >
                          <X class="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </div>
                  </div>
                </div>
                <p class="text-xs text-[var(--color-text-muted)] mt-1.5 leading-relaxed">
                  对号：追加为草稿并保留输入；加号：追加为「已保存」并清空输入。仅「已保存」的额外首句会进入单聊开场变体；草稿仅本地编辑用。下方列出全部条目（含「（空）」），均可删除。保存角色时会去掉空文本；占位符替换后为空也不会写入变体。
                </p>
              </div>

              <div class="form-group">
                <label class="label">
                  <span>示例对话</span>
                  <span class="opacity-60 text-xs ml-2 text-brand">该项参与对话</span>
                </label>
                <textarea v-model="actions.editingCharacter.value.exampleDialogue" class="input textarea h-48" placeholder="示例对话..."></textarea>
              </div>

              <div class="form-group rounded-xl border border-[var(--color-border-subtle)] bg-surface-overlay/80 p-4">
                <label class="label">
                  <span>绑定世界书</span>
                  <span class="opacity-60 text-xs ml-2 text-brand">随角色保存；「角色+世界书」ZIP 导出用此顺序</span>
                </label>
                <p class="text-xs text-[var(--color-text-muted)] mb-3 leading-relaxed">
                  与「设置 → 当前会话」中的会话世界书顺序独立；保存后写入角色卡上的绑定列表，供含世界书 ZIP 等使用。
                </p>
                <div class="flex flex-wrap items-center gap-2 mb-3">
                  <ModernSelect
                    v-model="addCharacterEditorWbId"
                    :options="characterEditorWorldBookSelectOptions"
                    placeholder="选择世界书加入列表..."
                    class="flex-1 min-w-[200px]"
                  />
                  <button type="button" class="btn btn-sm btn-secondary shrink-0" @click="addCharacterEditorWorldBook">加入</button>
                </div>
                <div class="space-y-1.5 max-h-[200px] overflow-y-auto custom-scrollbar pr-1">
                  <div
                    v-for="(wbId, idx) in (actions.editingCharacter.value.attachedWorldBookIds || [])"
                    :key="`${wbId}-${idx}`"
                    class="flex items-center justify-between gap-2 rounded-lg border border-[var(--color-border-subtle)] bg-surface-muted px-2 py-1.5 transition-all"
                    :class="characterEditorWbDraggingIdx === idx ? 'opacity-50 border-brand-a50' : ''"
                    draggable="true"
                    @dragstart="handleCharacterEditorWbDragStart(idx)"
                    @dragover="handleCharacterEditorWbDragOver($event, idx)"
                    @dragend="handleCharacterEditorWbDragEnd"
                  >
                    <div class="flex min-w-0 flex-1 items-center gap-1.5">
                      <span class="shrink-0 cursor-grab text-[var(--color-text-muted)] active:cursor-grabbing" aria-hidden="true">
                        <GripVertical class="w-4 h-4" />
                      </span>
                      <span class="truncate text-xs text-[var(--color-text)]">{{ idx + 1 }}. {{ characterEditorWorldBookName(wbId) }}</span>
                    </div>
                    <div class="flex shrink-0 items-center gap-1">
                      <button type="button" class="btn btn-xs btn-secondary" @click.stop="moveCharacterEditorWorldBook(wbId, -1)">上移</button>
                      <button type="button" class="btn btn-xs btn-secondary" @click.stop="moveCharacterEditorWorldBook(wbId, 1)">下移</button>
                      <button type="button" class="btn btn-xs btn-secondary" @click.stop="removeCharacterEditorWorldBook(wbId)">移除</button>
                    </div>
                  </div>
                  <div v-if="!(actions.editingCharacter.value.attachedWorldBookIds || []).length" class="text-xs text-[var(--color-text-muted)] py-2 text-center border border-dashed border-[var(--color-border-subtle)] rounded-lg">
                    未绑定世界书
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- 角色编辑助手 -->
          <div
            class="flex min-h-0 min-w-0 flex-col glass-panel rounded-2xl p-4 shadow-inner"
            :class="
              isNarrowPortrait
                ? 'min-h-[28rem] h-[min(36rem,72vh)] shrink-0 max-h-[min(576px,72vh)]'
                : 'max-w-[50%] flex-[0.66] basis-0'
            "
          >
            <div class="flex items-center justify-between mb-4 px-1">
              <span class="text-sm font-bold text-[var(--color-text-secondary)] uppercase tracking-widest flex items-center gap-2">
                <span class="w-2 h-2 rounded-full bg-brand animate-pulse"></span>
                聊天助手
              </span>
              <button class="text-[var(--color-text-muted)] hover:text-[var(--color-text)] transition-colors" @click="assistant.showAssistantSettings.value = true">
                <MoreHorizontal class="w-4 h-4" />
              </button>
            </div>
            <div
              ref="workspaceAssistantMessagesListRef"
              class="min-h-0 min-w-0 flex-1 overflow-x-auto overflow-y-auto custom-scrollbar space-y-4 pr-2 mb-4"
            >
              <div v-if="assistant.workspaceAssistantMessages.value.length === 0" class="text-xs text-[var(--color-text-muted)] text-center py-12 flex flex-col items-center gap-3">
                <div class="w-12 h-12 rounded-full bg-surface-muted flex items-center justify-center text-xl">
                    <Sparkles class="w-6 h-6 text-[var(--color-warning)]" />
                </div>
                开始和助手对话以完善你的角色卡
              </div>
              <AssistantThread
                :messages="assistant.workspaceAssistantMessages.value"
                :is-generating="assistant.isWorkspaceAssistantGenerating.value"
                :attachment-scope="'workspace'"
                :streaming-content="assistant.workspaceStreamingContent.value"
                :streaming-reasoning="assistant.workspaceStreamingReasoning.value"
                :reasoning-stream-phase-active="assistant.workspaceReasoningStreamPhaseActive.value"
                :reasoning-elapsed-sec="assistant.workspaceReasoningElapsedSec.value"
                :show-message-actions="false"
              />
            </div>
            <div
              class="relative pt-4 border-t border-[var(--color-border-subtle)] transition-colors"
              @dragenter.prevent="handleWorkspaceAssistantDragEnter"
              @dragover.prevent="handleWorkspaceAssistantDragOver"
              @dragleave="handleWorkspaceAssistantDragLeave"
              @drop.prevent="handleWorkspaceAssistantDrop"
            >
              <div class="flex flex-wrap gap-2 mb-2 items-center">
                <button
                  type="button"
                  disabled
                  aria-label="记忆写入，仅聊天会话中可用"
                  class="text-xs px-2.5 py-1 rounded-lg border cursor-not-allowed opacity-50 border-[var(--color-border-subtle)] text-[var(--color-text-muted)]"
                >
                  记忆写入
                </button>
                <button
                  type="button"
                  class="text-xs px-2.5 py-1 rounded-lg border transition-colors"
                  :class="assistant.allowDestructiveToolsEnabled.value
                    ? 'bg-amber-500/15 border-amber-500/50 text-amber-200'
                    : 'border-[var(--color-border-subtle)] text-[var(--color-text-muted)]'"
                  @click="assistant.toggleAllowDestructiveTools"
                >
                  破坏性工具
                </button>
                <button
                  type="button"
                  class="inline-flex items-center gap-1 text-xs px-2.5 py-1 rounded-lg border transition-colors"
                  :class="assistant.allowWebSearchEnabled.value
                    ? 'bg-brand/15 border-brand/50 text-brand-foreground'
                    : 'border-[var(--color-border-subtle)] text-[var(--color-text-muted)]'"
                  @click="assistant.toggleAllowWebSearch"
                >
                  <Globe class="h-3 w-3" />
                  网络搜索
                </button>
                <span class="text-[10px] text-[var(--color-text-muted)]">工作区不写长期记忆</span>
              </div>
              <div v-if="assistant.workspaceAssistantDraftAttachments.value.length" class="mb-3 flex flex-wrap gap-2">
                <template v-for="attachment in assistant.workspaceAssistantDraftAttachments.value" :key="attachment.id">
                  <div
                    v-if="attachment.kind === 'image'"
                    class="relative h-20 w-20 overflow-hidden rounded-lg border border-[var(--color-border)] bg-surface-muted"
                  >
                    <img :src="buildAssistantAttachmentUrl('workspace', attachment)" :alt="getAssistantAttachmentLabel(attachment)" class="h-full w-full object-cover" />
                    <button
                      type="button"
                      class="absolute right-1 top-1 flex h-5 w-5 items-center justify-center rounded-full bg-black/60 text-white"
                      @click="assistant.removeDraftAttachment('workspace', attachment.id)"
                    >
                      <X class="h-3 w-3" />
                    </button>
                  </div>
                  <button
                    v-else
                    type="button"
                    class="group relative flex max-w-[220px] items-start gap-2 rounded-xl border border-[var(--color-border)] bg-surface-muted px-3 py-2 text-left"
                    @click="assistant.removeDraftAttachment('workspace', attachment.id)"
                  >
                    <span class="rounded bg-black/20 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-[var(--color-text-secondary)]">{{ getAssistantAttachmentExt(attachment) }}</span>
                    <span class="truncate text-xs text-[var(--color-text)]">{{ getAssistantAttachmentLabel(attachment) }}</span>
                    <X class="ml-auto mt-0.5 h-3 w-3 shrink-0 text-[var(--color-text-muted)] transition-colors group-hover:text-[var(--color-text)]" />
                  </button>
                </template>
              </div>
              <textarea
                ref="workspaceAssistantTextareaRef"
                v-model="assistant.workspaceAssistantDraft.value"
                class="input textarea h-24"
                placeholder="输入建议或要求 (Ctrl + Enter)..."
                :disabled="assistant.isWorkspaceAssistantGenerating.value"
                @paste="handleWorkspaceAssistantPaste"
                @keydown.ctrl.enter="assistant.sendMessage('workspace', true, actions.applyAssistantCard)"
              ></textarea>
              <div class="flex items-center justify-between mt-3 gap-3">
                <ModernSelect
                  :model-value="assistantCurrentModel"
                  :selected-preset-id="assistant.assistantSettings.value.presetId ?? null"
                  :options="chatModelOptions"
                  placement="top"
                  placeholder="模型..."
                  class="!w-[160px] !text-xs"
                  dropdown-width="410"
                  searchable
                  allow-create
                  @select="assistant.handleModelSelect"
                />
                <button 
                  class="btn btn-primary relative px-6" 
                  :disabled="(!assistant.workspaceAssistantDraft.value.trim() && !assistant.workspaceAssistantDraftAttachments.value.length) || assistant.isWorkspaceAssistantGenerating.value" 
                  :aria-busy="assistant.isWorkspaceAssistantGenerating.value"
                  @click="assistant.sendMessage('workspace', true, actions.applyAssistantCard)"
                >
                  <Loader2
                    v-if="assistant.isWorkspaceAssistantGenerating.value"
                    class="pointer-events-none absolute left-3 top-1/2 h-3 w-3 -translate-y-1/2 animate-spin"
                  />
                  发送
                </button>
              </div>
              <div
                v-show="isWorkspaceAssistantDragOver"
                class="pointer-events-none absolute inset-0 z-[21] rounded-xl bg-white/25 backdrop-blur-[2px] ring-1 ring-inset ring-white/40 transition-opacity duration-150"
                aria-hidden="true"
              />
            </div>
          </div>
        </div>
      </div>
      <div class="modal-footer">
        <button class="btn btn-secondary" @click="actions.exportCharacterCard" :disabled="!actions.editingCharacter.value">导出角色 JSON</button>
        <button class="btn btn-secondary" @click="cancelCharacterEdit">取消</button>
        <button class="btn btn-primary" @click="saveCharacter">保存</button>
      </div>
    </div>
  </div>

  <!-- Persona 编辑弹窗 -->
  <div v-if="actions.showPersonaEditor.value" class="modal">
    <div class="modal-backdrop" @click="actions.showPersonaEditor.value = false"></div>
    <div class="modal-content chat-modal-width-500-90 glass-panel theme-panel-bg backdrop-blur-2xl backdrop-saturate-[1.8] border border-[var(--color-border)]">
      <div class="modal-header">
        <h3 class="modal-title">{{ actions.isNewPersona.value ? '新建身份' : '编辑身份' }}</h3>
        <button class="modal-close" @click="actions.showPersonaEditor.value = false">
            <X class="w-5 h-5" />
        </button>
      </div>
      <div class="modal-body">
        <div v-if="actions.editingPersona.value" class="space-y-6">
          <div class="flex items-center gap-4 mb-2">
            <ModernAvatar 
              :src="editingPersonaAvatarUrl"
              :size="80"
              aspect="1"
              rounded="rounded-xl"
              class="border-2 border-brand-a40"
            />
            <button class="btn btn-sm btn-secondary" @click="actions.showPersonaAvatarCropper.value = true">更换头像</button>
          </div>

          <div class="form-group">
            <label class="label">姓名（{{userName}}）</label>
            <input v-model="actions.editingPersona.value.name" class="input" placeholder="你的角色名称" />
          </div>

          <div class="form-group">
            <label class="label">简介</label>
            <textarea
              v-model="actions.editingPersona.value.description"
              class="input textarea h-32"
              placeholder="你的角色身份、背景等"
            ></textarea>
          </div>
        </div>
      </div>
      <div class="modal-footer">
        <button class="btn btn-secondary" @click="actions.showPersonaEditor.value = false">取消</button>
        <button class="btn btn-primary" @click="actions.savePersona">保存</button>
      </div>
    </div>
  </div>

  <!-- Persona 切换确认弹窗 -->
  <div v-if="actions.showPersonaSwitchConfirm.value" class="modal">
    <div class="modal-backdrop" @click="actions.cancelSwitchPersona"></div>
    <div class="modal-content chat-modal-width-520-92">
      <div class="modal-header">
        <h3 class="modal-title">切换用户身份</h3>
        <button class="modal-close" @click="actions.cancelSwitchPersona">
            <X class="w-5 h-5" />
        </button>
      </div>
      <div class="modal-body">
        <div class="space-y-4">
          <div class="text-sm text-[var(--color-text-secondary)]">
            你正在尝试切换用户身份，请选择"新建会话"或"仍然继续对话"。
          </div>
          <div class="text-xs text-[var(--color-text-muted)]">
            提示：继续对话时，历史消息会保持原身份显示；后续新发送的 user 消息将使用新身份。
          </div>
        </div>
      </div>
      <div class="modal-footer">
        <button class="btn btn-secondary" @click="actions.cancelSwitchPersona">取消</button>
        <button class="btn btn-secondary" @click="confirmSwitchPersonaContinue">仍然继续对话</button>
        <button class="btn btn-primary" @click="confirmSwitchPersonaNewSession">新建会话</button>
      </div>
    </div>
  </div>

  <!-- 助手设置弹窗 -->
  <div v-if="assistant.showAssistantSettings.value" class="modal">
    <div class="modal-backdrop" @click="assistant.showAssistantSettings.value = false"></div>
    <div
      class="modal-content chat-modal-width-520-92 glass-panel bg-gradient-to-br from-slate-900/30 to-slate-800/25 backdrop-blur-2xl backdrop-saturate-[1.8] border border-white/10"
    >
      <div class="modal-header">
        <h3 class="modal-title text-slate-50">聊天助手设置</h3>
        <button class="modal-close" @click="assistant.showAssistantSettings.value = false">
            <X class="w-5 h-5" />
        </button>
      </div>
      <div class="modal-body">
        <div class="space-y-6">
          <div class="form-group">
            <label class="label">温度</label>
            <input
              v-model.number="assistant.assistantSettings.value.temperature"
              type="number"
              min="0"
              max="2"
              step="0.1"
              class="input w-full"
            />
          </div>
          <div class="form-group">
            <label class="label">上下文长度</label>
            <input
              v-model.number="assistant.assistantSettings.value.context_size"
              type="number"
              min="0"
              class="input w-full"
              placeholder="未启用（不限制）"
            />
            <p class="text-xs text-[var(--color-text-muted)] mt-1">填 0 或留空表示未启用。实际上下文总限制长度为该「上下文长度」限制加上角色卡、用户信息、自定义系统提示词。</p>
          </div>
          <div class="form-group">
            <label class="label">助手读取消息条数上限</label>
            <input
              v-model.number="assistant.assistantSettings.value.tool_read_max_messages"
              type="number"
              min="1"
              class="input w-full"
              placeholder="未限制（仅受服务端硬上限）"
            />
            <p class="text-xs text-[var(--color-text-muted)] mt-1">限制「读取会话」工具返回的最大消息条数；留空表示不额外限制。</p>
          </div>
          <div class="form-group">
            <label class="label">助手读取消息 token 上限（估算）</label>
            <input
              v-model.number="assistant.assistantSettings.value.tool_read_max_tokens"
              type="number"
              min="1"
              class="input w-full"
              placeholder="未限制"
            />
            <p class="text-xs text-[var(--color-text-muted)] mt-1">对返回的消息列表做 token 估算裁剪（保留最新）；留空表示不启用。</p>
          </div>
          <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div class="form-group">
              <label class="label">最大工具轮次</label>
              <input
                v-model.number="assistant.assistantSettings.value.maxToolTurns"
                type="number"
                min="1"
                class="input w-full"
                placeholder="默认 8"
              />
              <p class="text-xs text-[var(--color-text-muted)] mt-1">限制单次助手请求可进入多少轮 tool_calls。</p>
            </div>
            <div class="form-group">
              <label class="label">单轮工具数上限</label>
              <input
                v-model.number="assistant.assistantSettings.value.maxToolsPerTurn"
                type="number"
                min="1"
                class="input w-full"
                placeholder="未限制"
              />
              <p class="text-xs text-[var(--color-text-muted)] mt-1">超出部分会写入「超出限制」占位结果并跳过执行。</p>
            </div>
          </div>
          <div class="form-group border-t border-[var(--color-border-subtle)] pt-6">
            <p class="label mb-3">工具权限</p>
            <p class="text-xs text-[var(--color-text-muted)] mb-4">
              以下开关与侧栏消息列表底部的权限按钮同步，变更后立即写入本机偏好。
            </p>
            <label class="flex items-start gap-3 cursor-pointer mb-4">
              <ThemedCheckbox
                class="mt-0.5"
                :checked="assistant.allowWebSearchEnabled.value"
                @update:checked="assistant.setAllowWebSearch"
              />
              <span>
                <span class="text-sm text-[var(--color-text)]">允许网络搜索</span>
                <span class="block text-xs text-[var(--color-text-muted)] mt-1">
                  开启后聊天助手与工具区助手可调用全局设置里的 Tavily / 博查搜索；MVU Agent 不会挂载此工具。
                </span>
              </span>
            </label>
            <label class="flex items-start gap-3 cursor-pointer mb-4">
              <ThemedCheckbox
                class="mt-0.5"
                :checked="assistant.allowWriteMemoryEnabled.value"
                @update:checked="setAssistantWriteMemoryEnabled"
              />
              <span>
                <span class="text-sm text-[var(--color-text)]">允许记忆写入</span>
                <span class="block text-xs text-[var(--color-text-muted)] mt-1">
                  开启后助手可在当前聊天会话中追加或覆盖长期记忆；仅作用于「聊天助手」，工作区助手不可用。
                </span>
              </span>
            </label>
            <label class="flex items-start gap-3 cursor-pointer">
              <ThemedCheckbox
                class="mt-0.5"
                :checked="assistant.allowDestructiveToolsEnabled.value"
                @update:checked="setAssistantDestructiveToolsEnabled"
              />
              <span>
                <span class="text-sm text-[var(--color-text)]">允许破坏性工具</span>
                <span class="block text-xs text-[var(--color-text-muted)] mt-1">
                  开启后助手可执行删除文件、删除世界书、覆盖整卡与覆盖全部记忆等不可逆操作。
                </span>
              </span>
            </label>
          </div>
        </div>
      </div>
      <div class="modal-footer">
        <button class="btn btn-secondary" @click="assistant.showAssistantSettings.value = false">取消</button>
        <button class="btn btn-primary" @click="assistant.saveSettingsAndClose">保存</button>
      </div>
    </div>
  </div>

  <div v-if="showEmbeddedCardConfirmModal" class="modal">
    <div class="modal-backdrop" @click="clearEmbeddedCardPreviewState"></div>
    <div class="modal-content chat-modal-width-568-90 min-w-0 glass-panel theme-panel-bg backdrop-blur-2xl backdrop-saturate-[1.8] border border-[var(--color-border)]">
      <div class="modal-header border-b border-[var(--color-border-subtle)]">
        <h3 class="modal-title text-[var(--color-text)]">检测到 PNG 内嵌角色卡</h3>
        <button class="modal-close text-[var(--color-text-muted)] hover:text-[var(--color-text)]" @click="clearEmbeddedCardPreviewState">×</button>
      </div>
      <div class="modal-body max-h-[min(70vh,520px)] overflow-y-auto pr-1 space-y-3">
        <div class="rounded-xl border border-[var(--color-border-subtle)] bg-[var(--color-surface-muted)] p-4 text-sm text-[var(--color-text-secondary)] space-y-2">
          <p>是否用内嵌角色数据覆盖当前编辑内容？</p>
          <p class="text-xs text-[var(--color-text-muted)]">
            确认后将覆盖简介、Personality、Scenario、首句、示例对话、系统提示词、额外首句与 MVU 相关字段，并重置世界书绑定为内嵌角色卡对应世界书（若存在）；当前上传图片会保留为头像。
          </p>
          <p class="text-xs text-[var(--color-text-muted)]">
            检测结果：角色名「{{ avatarEmbeddedStPreview?.characterName || embeddedCardPreview?.card?.name || '未命名角色' }}」，
            世界书：{{
              embeddedCardPreview?.worldbook || (avatarEmbeddedStPreview && avatarEmbeddedStPreview.worldBookEntryCount > 0)
                ? '有（将新建并绑定）'
                : '无（将清空绑定）'
            }}。
          </p>
        </div>
        <div
          v-if="avatarEmbeddedStPreview"
          class="rounded-xl border border-[var(--color-border-subtle)] bg-[var(--color-surface-overlay)] p-4 text-xs text-[var(--color-text-muted)] space-y-2"
        >
          <div class="text-[var(--color-text-secondary)]">SillyTavern / MVU 预览</div>
          <div class="grid grid-cols-1 gap-2 sm:grid-cols-2">
            <div>世界书条目：<span class="text-[var(--color-text)]">{{ avatarEmbeddedStPreview.worldBookEntryCount }}</span></div>
            <div>tavern_helper：<span class="text-[var(--color-text)]">{{ avatarEmbeddedStPreview.mvu.hasTavernHelper ? '已检测到' : '未检测到' }}</span></div>
            <div>regex_scripts：<span class="text-[var(--color-text)]">{{ avatarEmbeddedStPreview.mvu.regexScriptCount }}</span></div>
          </div>
          <label class="flex items-center gap-2">
            <ThemedCheckbox :checked="avatarEmbeddedEnableMvu" @update:checked="avatarEmbeddedEnableMvu = $event" />
            启用 MVU 兼容
            <span v-if="avatarEmbeddedDetectedMvu" class="text-[var(--color-text-secondary)]">已检测到候选结构</span>
          </label>
          <p class="text-[var(--color-text-muted)]">
            指令模式会把完整 ST 卡上下文交给 MVU Agent，生成角色卡 MVU 指令与初始状态栏后再合并到当前编辑内容。
          </p>
          <div>
            <div class="mb-1 text-[var(--color-text-muted)]">MVU 模式</div>
            <ModernSelect
              :model-value="avatarEmbeddedMvuMode"
              :options="[...avatarEmbeddedMvuModeOptions]"
              placeholder="选择 MVU 模式"
              @update:model-value="updateAvatarEmbeddedMvuMode"
            />
          </div>
          <p v-if="avatarEmbeddedStExpiresAt" class="text-[var(--color-text-muted)]">预览暂存至：{{ avatarEmbeddedStExpiresAt }}</p>
        </div>
      </div>
      <div class="modal-footer">
        <button class="btn btn-secondary" :disabled="embeddedCardImporting" @click="clearEmbeddedCardPreviewState">仅使用头像</button>
        <button class="btn btn-primary" :disabled="embeddedCardImporting" @click="confirmImportEmbeddedCard">
          {{ embeddedCardConfirmLabel }}
        </button>
      </div>
    </div>
  </div>

  <!-- 头像裁剪 -->
  <AvatarCropper
    v-model:show="actions.showCharacterAvatarCropper.value"
    :preserve-original="true"
    :focus-aspect="1"
    @save="handleCharacterAvatarSave"
  />

  <AvatarCropper
    v-model:show="actions.showPersonaAvatarCropper.value"
    @save="handlePersonaAvatarSave"
  />
</template>

<style scoped>
.page-background-image {
  width: 100%;
  height: 100%;
  object-fit: cover;
  object-position: center;
  transform-origin: center;
  transition: opacity 160ms ease, filter 160ms ease, transform 160ms ease;
  user-select: none;
}

.header-action-chip {
  display: inline-flex;
  align-items: center;
  gap: 0.45rem;
  min-height: 2rem;
  padding: 0.4rem 0.7rem;
  border-radius: 0.85rem;
  border: 1px solid var(--color-border-subtle);
  background: color-mix(in srgb, var(--color-surface-overlay, rgba(18, 22, 30, 0.72)) 88%, transparent);
  color: var(--color-text-secondary);
  font-size: 0.75rem;
  line-height: 1;
  transition:
    background-color 200ms cubic-bezier(0.25, 1, 0.5, 1),
    border-color 200ms cubic-bezier(0.25, 1, 0.5, 1),
    color 200ms cubic-bezier(0.25, 1, 0.5, 1),
    transform 180ms cubic-bezier(0.25, 1, 0.5, 1);
  backdrop-filter: blur(var(--blur-light));
  -webkit-backdrop-filter: blur(var(--blur-light));
}

@media (prefers-reduced-motion: no-preference) {
  .header-action-chip:active:not(:disabled) {
    transform: scale(0.97);
  }
}

.header-action-chip:hover:not(:disabled),
.header-action-chip:focus-visible {
  background: color-mix(in srgb, var(--color-surface-overlay, rgba(18, 22, 30, 0.72)) 96%, var(--color-border-subtle) 4%);
  border-color: var(--color-border);
  color: var(--color-text);
}

.header-action-chip:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.header-action-chip--icon {
  padding-inline: 0.6rem;
}

.header-action-chip--active {
  border-color: var(--color-border);
  color: var(--color-text);
  background: color-mix(in srgb, var(--color-surface-overlay, rgba(18, 22, 30, 0.72)) 92%, var(--color-border-subtle) 8%);
}

.header-action-shortcut {
  padding: 0.15rem 0.35rem;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.04);
  color: var(--color-text-muted);
  font-size: 0.65rem;
  letter-spacing: 0.04em;
}

.header-more-menu {
  position: absolute;
  z-index: 20;
  top: calc(100% + 0.45rem);
  right: 0;
  width: 14rem;
  padding: 0.45rem;
  border-radius: 1rem;
  border: 1px solid var(--color-border);
  background: color-mix(in srgb, var(--color-surface-overlay, rgba(18, 22, 30, 0.86)) 94%, transparent);
  box-shadow: var(--shadow-glass-panel, 0 16px 40px rgba(0, 0, 0, 0.24));
  transform-origin: top right;
  /* 磨砂用模板上的 backdrop-blur-[var(--blur-heavy)]（避免手写 backdrop-filter 经构建压缩失效，且勿嵌套在父级 backdrop 内） */
}

/* 与顶栏吸顶 morph（320 / 420 / 520ms）同气质的过渡：分层入场 / 退场 */

.header-search-trigger-enter-active,
.header-search-trigger-leave-active {
  transition:
    opacity 200ms cubic-bezier(0.25, 1, 0.5, 1),
    transform 200ms cubic-bezier(0.25, 1, 0.5, 1);
}

.header-search-trigger-enter-from,
.header-search-trigger-leave-to {
  opacity: 0;
  transform: translateY(-4px) scale(0.96);
}

.header-more-pop-enter-active,
.header-more-pop-leave-active {
  transition:
    opacity 200ms cubic-bezier(0.25, 1, 0.5, 1),
    transform 200ms cubic-bezier(0.25, 1, 0.5, 1);
}

.header-more-pop-enter-from,
.header-more-pop-leave-to {
  opacity: 0;
  transform: translateY(-6px) scale(0.96);
}

/* 会话搜索：先 grid 向下拓展占位，再 reveal 层带出内容；关闭时先收内容，半程再收拓展 */
.chat-header-search-expand {
  display: grid;
  grid-template-rows: 0fr;
  transition: grid-template-rows var(--chat-search-expand-ms, 320ms) cubic-bezier(0.4, 0, 0.2, 1);
}

.chat-header-search-expand--open {
  grid-template-rows: 1fr;
}

.chat-header-search-expand-inner {
  overflow: hidden;
  min-height: 0;
}

.chat-header-search-reveal-layer {
  opacity: 0;
  transform: translateY(6px);
  transition:
    opacity var(--chat-search-content-ms, 280ms) cubic-bezier(0.4, 0, 0.2, 1),
    transform var(--chat-search-content-ms, 280ms) cubic-bezier(0.25, 1, 0.5, 1);
  pointer-events: none;
}

.chat-header-search-reveal-layer--visible {
  opacity: 1;
  transform: translateY(0);
  pointer-events: auto;
}

.chat-header-groupstrip-enter-active,
.chat-header-groupstrip-leave-active {
  transition:
    opacity 300ms cubic-bezier(0.4, 0, 0.2, 1),
    transform 300ms cubic-bezier(0.4, 0, 0.2, 1);
}

.chat-header-groupstrip-enter-from,
.chat-header-groupstrip-leave-to {
  opacity: 0;
  transform: translateY(6px);
}

/* 会话搜索命中 chip 行：与主搜索区相同 grid 手法，顶栏高度随 ResizeObserver 连续变化 */
.chat-search-chips-expand {
  display: grid;
  grid-template-rows: 0fr;
  transition: grid-template-rows var(--chat-search-chips-ms, 280ms) cubic-bezier(0.4, 0, 0.2, 1);
}

.chat-search-chips-expand--open {
  grid-template-rows: 1fr;
}

.chat-search-chips-expand-inner {
  overflow: hidden;
  min-height: 0;
  transform: translateY(8px);
  opacity: 0;
  transition:
    transform var(--chat-search-chips-ms, 280ms) cubic-bezier(0.25, 1, 0.5, 1),
    opacity var(--chat-search-chips-ms, 280ms) cubic-bezier(0.4, 0, 0.2, 1);
}

.chat-search-chips-expand--open .chat-search-chips-expand-inner {
  transform: translateY(0);
  opacity: 1;
}

@media (prefers-reduced-motion: reduce) {
  .header-search-trigger-enter-active,
  .header-search-trigger-leave-active,
  .header-more-pop-enter-active,
  .header-more-pop-leave-active,
  .chat-header-groupstrip-enter-active,
  .chat-header-groupstrip-leave-active {
    transition-duration: 0.01ms !important;
  }

  .header-search-trigger-enter-from,
  .header-search-trigger-leave-to,
  .header-more-pop-enter-from,
  .header-more-pop-leave-to,
  .chat-header-groupstrip-enter-from,
  .chat-header-groupstrip-leave-to {
    opacity: 1;
    transform: none;
  }

  .chat-search-chips-expand {
    transition: none;
  }

  .chat-search-chips-expand-inner {
    transform: none;
    opacity: 1;
    transition: none;
  }

  .chat-header-search-expand {
    transition: none;
  }

  .chat-header-search-reveal-layer {
    transition: none;
  }
}

.header-more-menu__item {
  display: flex;
  width: 100%;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.1rem;
  padding: 0.65rem 0.75rem;
  border-radius: 0.8rem;
  color: var(--color-text-secondary);
  text-align: left;
  transition: background-color 160ms ease, color 160ms ease;
}

.header-more-menu__item:hover:not(:disabled),
.header-more-menu__item:focus-visible {
  background: rgba(255, 255, 255, 0.045);
  color: var(--color-text);
}

.header-more-menu__item:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.header-more-menu__label {
  font-size: 0.8rem;
}

.header-more-menu__meta {
  font-size: 0.68rem;
  color: var(--color-text-muted);
}

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
