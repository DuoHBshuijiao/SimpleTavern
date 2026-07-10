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
import { computed, onBeforeUnmount, onMounted, ref, watch, nextTick, type ComponentPublicInstance } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useCharacterSidebarRecencyStore, useCharactersStore, useChatsStore, useSettingsStore, useUiStore, useMvuStore } from '../stores'
import type { SettingsDrawerTab } from '../stores/ui'
import type { ApiPreset, AssistantAttachment, CharacterCard, ChatContentRegexRule, ChatImageAttachment, ChatMessage, ChatOverrides, ChatMvuMode, GroupMemberSettings, Chat, MainChatRole, TtsSessionConfig, GroupMvuPreset } from '../types/models'
// Composables
import { 
  useStreamOutput, 
  useMessageVersions, 
  useGroupChat, 
  useAssistant,
  useChatActions,
  useSettingsImport,
} from '../composables'
import { useEmbeddedAvatarImport, type AvatarCropSavePayload } from '../composables/useEmbeddedAvatarImport'
import { useGenerationDeferState } from '../composables/useGenerationDeferState'
import { usePageBackground } from '../composables/usePageBackground'
import { useWebGpuBackground } from '../composables/useWebGpuBackground'
import { useWebGpuBackgroundRuntime } from '../composables/useWebGpuBackgroundRuntime'
import { useViewportNarrowPortrait } from '../composables/useViewportNarrowPortrait'
import { useChatSearch } from '../composables/useChatSearch'
import { useImageStickyBinding } from '../composables/useImageStickyBinding'
import { useForkLineage } from '../composables/useForkLineage'
import { useMessageListEnterAnimations } from '../composables/useMessageListEnterAnimations'
import { useMainChatReasoning } from '../composables/useMainChatReasoning'
import { createCloseTopOverlayHandler, useGlobalEscapeStack } from '../composables/useGlobalEscapeStack'
import { useChatHeaderLayout } from '../composables/useChatHeaderLayout'
import { useChatFabSeparation } from '../composables/useChatFabSeparation'

// 子组件
import { ChatSidebar, MessageList, ChatInput, AssistantPanel, MvuPanel } from '../components/chat'
import ForkLineageBanner from '../components/chat/ForkLineageBanner.vue'
import StateVariablesBar from '../components/chat/StateVariablesBar.vue'
import {
  GroupCreatorModal,
  MessageEditorModal,
  MemberSettingsModal,
  GroupSettingsModal,
  ChatExportModal,
  ChatImportModal,
  CharacterEditorModal,
  PersonaEditorModal,
  PersonaSwitchConfirmModal,
  EmbeddedCardConfirmModal,
  AssistantSettingsModal,
} from '../components/modals'
import ErrorModal from '../components/modals/ErrorModal.vue'
import KnowledgeGraphModal from '../components/modals/KnowledgeGraphModal.vue'
import SettingsDrawer from '../components/SettingsDrawer.vue'
import AvatarCropper from '../components/AvatarCropper.vue'
import ModernAvatar from '../components/ModernAvatar.vue'
import TtsPlaybackFab from '../components/chat/TtsPlaybackFab.vue'
import { useTtsPlaybackQueue } from '../composables/useTtsPlaybackQueue'
import { Users, Settings, MoreHorizontal, Search } from 'lucide-vue-next'

// API
import { postAndConsumeSse } from '../api/sse'
import { apiPost, apiGet } from '../api/http'
import { useErrorStack } from '../composables/useErrorStack'
import { notifyConfirm, notifyMessage } from '../composables/useNotify'
import { isTtsApiPreset, resolveTtsProvider } from '../utils/apiPresetKind'
import { validateFilesForTarget } from '../utils/attachmentPolicy'
import { resolveRichPaste } from '../utils/richPaste'
import { formatApiError } from '../utils/worldBookValidation'
import { resolveBumpCharacterId } from '../utils/characterSidebarBump'
import { isChatMvuRuntimeEnabled } from '../utils/groupMvu'

// ========== Stores ==========
const settings = useSettingsStore()
const characters = useCharactersStore()
const chats = useChatsStore()
const characterSidebarRecency = useCharacterSidebarRecencyStore()
const uiStore = useUiStore()
const route = useRoute()
const router = useRouter()
const { refreshDataAfterImport } = useSettingsImport()
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
const draftImages = ref<DraftImageItem[]>([])
const workspaceAssistantTextareaRef = ref<HTMLTextAreaElement | null>(null)
/** 角色编辑页内嵌助手消息列表滚动容器（与侧栏 AssistantPanel 分离） */
const workspaceAssistantMessagesListRef = ref<HTMLElement | null>(null)
const characterEditorModalRef = ref<InstanceType<typeof CharacterEditorModal> | null>(null)

function bindWorkspaceMessagesListRef(el: Element | ComponentPublicInstance | null) {
  workspaceAssistantMessagesListRef.value = el instanceof HTMLElement ? el : null
}

function bindWorkspaceTextareaRef(el: Element | ComponentPublicInstance | null) {
  workspaceAssistantTextareaRef.value = el instanceof HTMLTextAreaElement ? el : null
}
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
/** 主内容区与 FAB 宿主 ref（须在 composable 前声明） */
const chatMainRef = ref<HTMLElement | null>(null)
const chatInputRef = ref<InstanceType<typeof ChatInput> | null>(null)
const ttsPlaybackFabRef = ref<InstanceType<typeof TtsPlaybackFab> | null>(null)

const chatHeaderLayout = useChatHeaderLayout({
  sidebarCollapsed,
  isNarrowPortrait,
  isTtsEnabled: () => settings.settings?.ttsEnabled === true,
})

const {
  headerMorphPhase,
  chatHeaderStyle,
  chatHeaderHeightPx,
  chatAssistantFabMinTopPx,
  ttsInputSinkActive,
  ttsTopBarControlsVisible,
  agentTopBarControlsVisible,
} = chatHeaderLayout

const {
  contentAreaLeftPx,
  updateContentAreaLeft,
  runChatFabSeparation,
} = useChatFabSeparation({
  chatMainRef,
  chatInputRef,
  ttsPlaybackFabRef,
  chatAssistantFabMinTopPx,
  sidebarCollapsed,
  isNarrowPortrait,
  isTtsEnabled: () => settings.settings?.ttsEnabled === true,
})

/** 顶栏变形阶段供 WebGPU 背景同步 */
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

const editingChatId = ref<string | null>(null)
const editingTitle = ref('')
const aborter = ref<AbortController | null>(null)
const stopRequested = ref(false)
const stopStreamingHold = ref(false)
const {
  rewriteMergeCtx,
  clearAll: clearGenerationDeferState,
  beginSaveSendDefer,
  beginRewriteDefer,
  getSaveSendDeferForChat,
  clearSaveSendDeferForChat,
  clearRewriteAndVisibility,
  finalizeRewriteAfterGeneration,
  filterVisibleMessages,
  finalizeSaveSendAfterGeneration,
} = useGenerationDeferState()

watch(() => uiStore.settingsDrawerRequestNonce, (nonce) => {
  if (!nonce) return
  settingsTab.value = uiStore.requestedSettingsTab
  showSettings.value = true
})

function shouldIgnoreStreamingEventWhileStopping(eventName: string): boolean {
  return stopRequested.value && eventName === 'delta'
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

const {
  chatReasoningMessageId,
  chatReasoningContent,
  chatReasoningBlocks,
  chatReasoningStreamActive,
  chatReasoningElapsedSec,
  markReasoningStreamPhaseStart,
  clearReasoningPhaseTiming,
  onAssistantContentDeltaStarted,
  finalizeReasoningElapsedBeforeStop,
  pushCurrentReasoningToBlocks,
  getReasoningForMessageId,
  clearReasoningForChatSwitch,
} = useMainChatReasoning({
  getActiveChat: () => activeChat.value,
})

/** 占位符重试成功后：在同一会话且同模型+同 API 预设下自动对上游使用 [image] 占位，直到切换模型/预设或换会话（localStorage 按 chatId 持久化） */
const {
  imageStickyBinding,
  resolveImageBindingKey,
  isImageStickyActive,
  saveImageStickyBindingRow,
  imageFallbackDialog,
  openImageFallback,
} = useImageStickyBinding({
  getActiveChat: () => activeChat.value,
  getDefaultModel: () => settings.settings?.llm?.defaultModel,
})

/** MessageList 用：延后删除时在 UI 中隐藏仍会占上下文的消息 */
const messageListMessages = computed((): ChatMessage[] => {
  const chat = activeChat.value
  if (!chat?.messages?.length) return []
  return filterVisibleMessages(chat.messages)
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

let postSwitchIdleHandle: number | null = null
let postSwitchDeferTimer: ReturnType<typeof setTimeout> | null = null
let mvuConnectDeferTimer: ReturnType<typeof setTimeout> | null = null

function cancelDeferredPostSwitchWork() {
  if (postSwitchIdleHandle != null) {
    if (typeof cancelIdleCallback === 'function') {
      cancelIdleCallback(postSwitchIdleHandle)
    }
    postSwitchIdleHandle = null
  }
  if (postSwitchDeferTimer) {
    clearTimeout(postSwitchDeferTimer)
    postSwitchDeferTimer = null
  }
}

function cancelDeferredMvuConnect() {
  if (mvuConnectDeferTimer) {
    clearTimeout(mvuConnectDeferTimer)
    mvuConnectDeferTimer = null
  }
}

function scheduleDeferredPostSwitchWork(chatId: string) {
  cancelDeferredPostSwitchWork()
  const run = () => {
    postSwitchIdleHandle = null
    postSwitchDeferTimer = null
    const ac = activeChat.value
    if (!ac || ac.id !== chatId) return
    void flushAutoReadTtsAfterChatReload()
    scheduleMaybeTriggerAutoMemorySummary(chatId)
    syncForkLineageForLoadedChat(chatId)
  }
  if (typeof requestIdleCallback === 'function') {
    postSwitchIdleHandle = requestIdleCallback(run, { timeout: 2000 })
  } else {
    postSwitchDeferTimer = setTimeout(run, 0)
  }
}

async function afterChatReload(chatId: string) {
  scheduleDeferredPostSwitchWork(chatId)
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

const chatMvuRuntimeEnabledForPanel = computed(() => {
  const ac = chats.activeChat
  if (!ac) return false
  return isChatMvuRuntimeEnabled(ac, (id) => characters.list.find((c) => c.id === id))
})

const showMvuStateBar = computed(
  () => chatMvuRuntimeEnabledForPanel.value && mvuStore.capsuleData.length > 0,
)

const knowledgeGraphEnabledEffective = computed(
  () => chats.activeChat?.overrides?.knowledgeGraphEnabled !== false,
)

async function onKnowledgeGraphEnabledChange(enabled: boolean) {
  if (!chats.activeChat) return
  const overrides = {
    ...chats.activeChat.overrides,
    knowledgeGraphEnabled: enabled,
  }
  await chats.updateOverrides(chats.activeChat.id, overrides, { skipLoadList: true })
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

const chatSearchInputRef = ref<HTMLInputElement | null>(null)
const {
  showChatSearch,
  holdSearchChipUntilSearchPanelClosed,
  chatSearchExpandOpen,
  chatSearchContentRevealed,
  SEARCH_OPEN_EXPAND_MS,
  SEARCH_CLOSE_CONTENT_MS,
  SEARCH_EXPAND_COLLAPSE_MS,
  chatSearchQuery,
  chatSearchLoading,
  chatSearchCursor,
  chatSearchChipsGridOpen,
  chatSearchChipsCollapsing,
  chatSearchChipsDisplayHits,
  chatSearchHitsForNav,
  runChatSearch,
  goToNextSearchResult,
  goToPrevSearchResult,
  jumpToSearchResult,
  openChatSearchBar,
  closeChatSearchBar,
  resetChatSearchForChatSwitch,
} = useChatSearch({
  getActiveChat: () => activeChat.value,
  jumpToMessageIndex,
  chatSearchInputRef,
  beforeOpen: () => {
    showHeaderMoreMenu.value = false
  },
})
const {
  entrancingUserMessageId,
  entrancingAssistantMessageId,
  armUserMessageEnterAnimation,
  armAssistantRowEnterAnimation,
  clearMessageListEnterAnimations,
} = useMessageListEnterAnimations()
const showHeaderMoreMenu = ref(false)
const headerMoreMenuRef = ref<HTMLElement | null>(null)
const headerMoreButtonRef = ref<HTMLElement | null>(null)

/** 主聊天网络搜索开关：为 true 时每次生成请求挂载搜索工具，直至用户关闭；需全局配置 Tavily/博查 API Key */
const webSearchSessionEnabled = ref(false)

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
  draftHelperAborter.value?.abort()
  clearDraftImages()
  errorStack.clearAll()
  window.removeEventListener('keydown', handleGlobalKeydown)
  window.removeEventListener('pointerdown', handleHeaderPointerdown)
  mvuStore.disconnect()
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

const embeddedAvatarImport = useEmbeddedAvatarImport({
  getEditingCharacter: () => actions.editingCharacter.value,
  saveCharacterAvatar: (imageData, focusX, focusY) =>
    actions.handleCharacterAvatarSave(imageData, focusX, focusY),
  applyAssistantCard: (card) => actions.applyAssistantCard(card),
  reloadWorldbooks: () => characterEditorModalRef.value?.reloadWorldbooks(),
  pushError: (payload) => errorStack.pushError(payload),
})

const {
  showEmbeddedCardConfirmModal,
  embeddedCardPreview,
  embeddedCardImporting,
  avatarEmbeddedStPreview,
  avatarEmbeddedStExpiresAt,
  avatarEmbeddedEnableMvu,
  avatarEmbeddedMvuMode,
  avatarEmbeddedMvuModeOptions,
  avatarEmbeddedDetectedMvu,
  embeddedCardConfirmLabel,
  clearEmbeddedCardPreviewState,
  handleCharacterAvatarSave,
  confirmImportEmbeddedCard,
  updateAvatarEmbeddedMvuMode,
} = embeddedAvatarImport

async function handlePersonaAvatarSave(payload: AvatarCropSavePayload) {
  await actions.handlePersonaAvatarSave(payload.imageData)
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
  () => [activeChat.value?.id ?? null, showMvuStateBar.value] as const,
  ([chatId, visible], [oldChatId]) => {
    if (chatId !== oldChatId || !visible) {
      mvuStateBarWrapExtraHeightPx.value = 0
    }
  },
)

function scrollToBottom(instant = false, force = false) {
  nextTick(() => {
    messageListRef.value?.scrollToBottom(instant, force)
  })
}

/** 切换会话：等 MessageList 批量行高落盘后再单次贴底 */
function scrollToBottomAfterLayout(instant = true, force = true) {
  nextTick(() => {
    messageListRef.value?.scrollToBottomAfterLayout?.(instant, force)
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

function hasActiveNotifyHost(): boolean {
  return typeof document !== 'undefined' && document.querySelector('.app-notify-host') !== null
}

const closeTopOverlayFromEscape = createCloseTopOverlayHandler({
  hasActiveNotifyHost,
  tryCloseErrorStack: () => {
    const latestError = errorStack.items.value[errorStack.items.value.length - 1]
    if (!latestError) return false
    errorStack.removeError(latestError.id)
    return true
  },
  overlayClosers: [
    () => {
      if (!imageFallbackDialog.value.visible) return false
      imageFallbackDialog.value.visible = false
      return true
    },
    () => {
      if (!actions.showCharacterAvatarCropper.value) return false
      actions.showCharacterAvatarCropper.value = false
      return true
    },
    () => {
      if (!actions.showPersonaAvatarCropper.value) return false
      actions.showPersonaAvatarCropper.value = false
      return true
    },
    () => {
      if (!actions.showMessageEditor.value) return false
      actions.showMessageEditor.value = false
      return true
    },
    () => {
      if (!assistant.showAssistantMessageEditor.value) return false
      assistant.showAssistantMessageEditor.value = false
      return true
    },
    () => {
      if (!actions.editingMemberId.value) return false
      actions.closeMemberSettingsEditor()
      return true
    },
    () => {
      if (!showGroupSettings.value) return false
      showGroupSettings.value = false
      return true
    },
    () => {
      if (!showGroupCreator.value) return false
      onGroupCreatorShow(false)
      return true
    },
    () => {
      if (!showExportModal.value) return false
      showExportModal.value = false
      return true
    },
    () => {
      if (!showImportModal.value) return false
      showImportModal.value = false
      return true
    },
    () => {
      if (!knowledgeGraphModalOpen.value) return false
      knowledgeGraphModalOpen.value = false
      return true
    },
    () => {
      if (!showEmbeddedCardConfirmModal.value) return false
      clearEmbeddedCardPreviewState()
      return true
    },
    () => {
      if (!actions.showPersonaSwitchConfirm.value) return false
      actions.cancelSwitchPersona()
      return true
    },
    () => {
      if (!assistant.showAssistantSettings.value) return false
      assistant.showAssistantSettings.value = false
      return true
    },
    () => {
      if (!actions.showPersonaEditor.value) return false
      actions.showPersonaEditor.value = false
      return true
    },
    () => {
      if (!actions.showCharacterEditor.value) return false
      cancelCharacterEdit()
      return true
    },
  ],
})

const { handleGlobalKeydown: handleGlobalEscapeKeydown } = useGlobalEscapeStack({
  closeTopOverlay: closeTopOverlayFromEscape,
  onEscapeFallback: () => {
    closeHeaderMoreMenu()
    if (showChatSearch.value) closeChatSearchBar()
  },
})

function handleGlobalKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') {
    handleGlobalEscapeKeydown(e)
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
    if (shouldConnect && next.id) {
      cancelDeferredMvuConnect()
      const connectId = next.id
      mvuConnectDeferTimer = setTimeout(() => {
        mvuConnectDeferTimer = null
        const ac = activeChat.value
        if (!ac || ac.id !== connectId) return
        const on = isChatMvuRuntimeEnabled(ac, (id) => characters.list.find((c) => c.id === id))
        if (on) mvuStore.connect(connectId)
      }, 80)
    }
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

/** 群聊校正 selectedCharacterId 时跳过「自动打开最新单聊」，但仍刷新侧栏列表 */
let skipNextCharacterListLoad = false

watch(
  () => selectedCharacterId.value,
  async (cid) => {
    if (!cid) return
    if (skipNextCharacterListLoad) {
      skipNextCharacterListLoad = false
      await chats.loadList(cid)
      return
    }
    const acBefore = chats.activeChat
    if (
      acBefore?.isGroup &&
      chats.activeChatId &&
      acBefore.memberIds?.includes(cid)
    ) {
      return
    }
    await chats.loadList(cid)
    const ac = chats.activeChat
    // 仅当当前群聊包含该角色时留在群聊；点击群外角色（如 A）应跳到该角色最新单聊
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
    if (first) {
      skipNextCharacterListLoad = true
      selectedCharacterId.value = first
    }
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
      scrollToBottomAfterLayout(true, true)
    }
    if (prev != null && next !== prev) {
      clearMessageListEnterAnimations()
      clearReasoningForChatSwitch()
      versions.clearAll()
      clearGenerationDeferState()
    }
    // 切换会话时自动关闭搜索面板并重置搜索状态
    showHeaderMoreMenu.value = false
    resetChatSearchForChatSwitch()
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
    clearEmbeddedCardPreviewState()
  }
})

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
  const deferredForInterject = getSaveSendDeferForChat(chatId)
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
  
  let generationHadError = false
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
              generationHadError = true
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
        generationHadError = true
        streamError.value = res.error || 'unknown error'
      }
    }
  } catch (e: any) {
    if (!isAbortError(e)) {
      generationHadError = true
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
      const hadSaveSendDefer = !!getSaveSendDeferForChat(chatId)
      await finalizeSaveSendAfterGeneration(chatId, generationHadError, finalizeDeferredTailDelete)
      if (!hadSaveSendDefer && !generationHadError) {
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
  finalizeReasoningElapsedBeforeStop()
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

  const saveSendSnapshot = getSaveSendDeferForChat(chatId)
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
    clearSaveSendDeferForChat(chatId)

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
      clearRewriteAndVisibility()
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
  clearRewriteAndVisibility()
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
  beginRewriteDefer(
    { chatId, anchorId, anchorTs, originalMessageId },
    [...omitMessageIds],
    tailDeleteIds,
  )

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

  let generationHadError = false
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
                generationHadError = true
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
          generationHadError = true
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
                generationHadError = true
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
          generationHadError = true
          streamError.value = res.error || 'unknown error'
        }
      }
    }
  } catch (e: any) {
    if (!isAbortError(e)) {
      generationHadError = true
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
      await finalizeRewriteAfterGeneration(chatId, generationHadError, finalizeDeferredTailDelete)
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

const forkSubmitting = ref(false)
const {
  forkLineage,
  forkLineageLoading,
  outgoingForksByMessageId,
  refreshForkLineage,
  syncForkLineageForLoadedChat,
  resetForkLineage,
} = useForkLineage({
  getActiveChat: () => activeChat.value,
  fetchForkLineage: (chatId, signal) => chats.fetchForkLineage(chatId, signal),
})

watch(
  () => chats.activeChatId,
  () => {
    cancelDeferredPostSwitchWork()
    cancelDeferredMvuConnect()
    resetForkLineage()
  },
)

async function onForkMessage(m: ChatMessage) {
  const chat = activeChat.value
  if (!chat || forkSubmitting.value) return
  forkSubmitting.value = true
  try {
    const created = await chats.forkChat(chat.id, m.id)
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
    void refreshForkLineage(origin.chatId)
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

async function restoreSettingsDrawerChat(chatId: string) {
  try {
    await chats.load(chatId)
    await afterChatReload(chatId)
  } catch (e: unknown) {
    await notifyMessage(e instanceof Error ? e.message : String(e), { title: '无法恢复原会话' })
  }
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

function closePersonaEditor() {
  actions.showPersonaEditor.value = false
}

function closeAssistantSettings() {
  assistant.showAssistantSettings.value = false
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
    beginSaveSendDefer({
      chatId,
      tailIdsToDeleteOnSuccess,
      singleAssistantTailMergeId,
      mode: 'group',
    })

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

  beginSaveSendDefer({
    chatId,
    tailIdsToDeleteOnSuccess,
    singleAssistantTailMergeId,
    mode: 'single',
  })

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

  let generationHadError = false
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
                generationHadError = true
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
          generationHadError = true
          streamError.value = res.error || 'unknown error'
        }
      }
  } catch (e: any) {
    if (!isAbortError(e)) {
      generationHadError = true
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

      await finalizeSaveSendAfterGeneration(chatId, generationHadError, finalizeDeferredTailDelete)
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
            :ref="(el) => { chatHeaderLayout.chatHeaderRef.value = el as HTMLElement | null }"
            class="relative flex flex-col pointer-events-none"
            :style="chatHeaderStyle"
          >
            <div
              class="pointer-events-none absolute inset-0 z-0 overflow-hidden theme-header-bg backdrop-blur-[var(--glass-blur-soft)] backdrop-saturate-[1.75]"
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
                      <span class="shrink-0 rounded-full border border-[var(--color-border-subtle)] bg-surface-muted/70 px-2 py-0.5 text-2xs text-[var(--color-text-muted)]">
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
                      class="header-more-menu backdrop-blur-[var(--glass-blur-popover)]"
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
              role="search"
              aria-label="会话内搜索"
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
                          <div class="text-2xs text-[var(--color-text-muted)]">
                            {{ chatSearchHitsForNav.length ? (chatSearchCursor < 0 ? `—/${chatSearchHitsForNav.length}` : `${chatSearchCursor + 1}/${chatSearchHitsForNav.length}`) : (chatSearchLoading ? '搜索中...' : '输入后定位消息') }}
                          </div>
                        </div>
                      </div>

                      <input
                        ref="chatSearchInputRef"
                        v-model="chatSearchQuery"
                        class="min-w-0 flex-1 bg-transparent text-sm outline-none"
                        placeholder="搜索当前会话"
                        aria-label="搜索当前会话"
                        @keydown.enter.prevent="runChatSearch"
                        @keydown.esc.prevent="closeChatSearchBar"
                      />

                      <button type="button" class="btn btn-xs btn-secondary shrink-0" aria-label="上一个搜索结果" @click="goToPrevSearchResult">上一个</button>
                      <button type="button" class="btn btn-xs btn-secondary shrink-0" aria-label="下一个搜索结果" @click="goToNextSearchResult">下一个</button>
                      <button type="button" class="btn btn-xs btn-secondary shrink-0" aria-label="关闭会话搜索" @click="closeChatSearchBar">
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
                <div class="shrink-0 text-2xs tracking-[0.08em] text-[var(--color-text-muted)]">
                  成员
                </div>
                <div 
                  v-for="(member, idx) in groupMembers" 
                  :key="member.id"
                  class="flex items-center gap-1.5 shrink-0 rounded-full border border-[var(--color-border-subtle)] bg-surface-muted/80 px-2.5 py-1 transition-colors group/member"
                  :class="group.canInterject.value ? 'cursor-pointer hover:bg-[var(--color-purple-bg)]' : ''"
                  @click="group.canInterject.value && triggerInterject(member.id)"
                >
                  <span class="text-2xs text-[var(--color-text-muted)]">{{ idx + 1 }}</span>
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
                    class="rounded-full border border-[var(--color-warning)]/20 bg-[var(--color-warning-bg)] px-1.5 py-0.5 text-2xs leading-none text-[var(--color-warning-text)]"
                  >
                    {{ Math.round(group.getMemberSettings(member.id).probability * 100) }}%
                  </span>
                </div>
                <div v-if="!group.effectivePureAiMode.value" class="flex items-center gap-1.5 shrink-0 rounded-full border border-brand-a20 bg-brand-a10 px-2.5 py-1">
                  <ModernAvatar :src="userAvatarUrl" :name="userName" :size="20" aspect="1" rounded="rounded" />
                  <span class="max-w-[72px] truncate text-xs text-brand">{{ userName }}</span>
                  <span class="text-2xs text-brand-a60">你</span>
                </div>
              </div>
            </div>
            </Transition>
            </div>
          </header>

          <!-- 消息列表：MVU 状态条叠在列表与输入区交界处（贴底），正文滚动从其下方穿过 -->
          <div class="relative flex min-h-0 min-w-0 flex-1 flex-col overflow-visible">
            <!-- z-[45] 须高于 chat-input-shell 的 z-40，避免侧栏收起 sink 时透明输入壳挡住 MVU 状态条按钮 -->
            <Transition name="mvu-state-bar">
              <div
                v-if="showMvuStateBar"
                key="mvu-state-bar"
                class="pointer-events-none absolute inset-x-0 bottom-0 z-[45] overflow-visible"
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
            </Transition>
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
            :is-forking="forkSubmitting"
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
      :mvu-runtime-enabled="chatMvuRuntimeEnabledForPanel"
      :knowledge-graph-enabled="knowledgeGraphEnabledEffective"
      :has-knowledge-graph="mvuStore.hasKnowledgeGraph"
      :running="mvuStore.isRunning"
      :mvu-model="settings.settings?.mvuModel ?? null"
      :model-options="chatModelOptions"
      :resolved-mvu-model="mvuResolvedModelForPanel"
      @update:is-open="mvuPanelOpen = $event"
      @update:knowledge-graph-enabled="onKnowledgeGraphEnabledChange"
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

    <div v-if="imageFallbackDialog.visible" class="fixed inset-0 z-[1400] flex items-center justify-center p-4">
      <div class="absolute inset-0 bg-overlay-heavy backdrop-blur-[var(--glass-blur-soft)]" @click="imageFallbackDialog.visible = false"></div>
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="image-fallback-title"
        class="modal-content modal-surface relative w-[min(640px,calc(100vw-2rem))] border-[color-mix(in_srgb,var(--color-error)_30%,transparent)]"
      >
        <div class="px-4 py-3 border-b border-[color-mix(in_srgb,var(--color-error)_20%,transparent)]">
          <h3 id="image-fallback-title" class="text-sm font-semibold text-[var(--color-error-text)]">模型不支持图片或图片请求失败</h3>
        </div>
        <div class="px-4 py-3">
          <pre class="text-xs leading-5 text-[var(--color-error-text)] whitespace-pre-wrap break-words max-h-[260px] overflow-auto custom-scrollbar">{{ imageFallbackDialog.error }}</pre>
        </div>
        <div class="px-4 pb-4 flex justify-end gap-2">
          <button type="button" class="btn btn-sm btn-secondary" @click="imageFallbackDialog.visible = false">返回</button>
          <button
            type="button"
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
      @restore-chat-selection="restoreSettingsDrawerChat"
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

    <CharacterEditorModal
      ref="characterEditorModalRef"
      :show="actions.showCharacterEditor.value"
      :is-new-character="actions.isNewCharacter.value"
      :character="actions.editingCharacter.value"
      :avatar-url="editingCharacterAvatarUrl"
      :is-narrow-portrait="isNarrowPortrait"
      :assistant="assistant"
      :assistant-current-model="assistantCurrentModel"
      :chat-model-options="chatModelOptions"
      :is-workspace-assistant-drag-over="isWorkspaceAssistantDragOver"
      :build-assistant-attachment-url="buildAssistantAttachmentUrl"
      :get-assistant-attachment-label="getAssistantAttachmentLabel"
      :get-assistant-attachment-ext="getAssistantAttachmentExt"
      :bind-workspace-messages-list-ref="bindWorkspaceMessagesListRef"
      :bind-workspace-textarea-ref="bindWorkspaceTextareaRef"
      :on-workspace-paste="handleWorkspaceAssistantPaste"
      :on-workspace-drag-enter="handleWorkspaceAssistantDragEnter"
      :on-workspace-drag-leave="handleWorkspaceAssistantDragLeave"
      :on-workspace-drag-over="handleWorkspaceAssistantDragOver"
      :on-workspace-drop="handleWorkspaceAssistantDrop"
      :apply-assistant-card="actions.applyAssistantCard"
      @cancel="cancelCharacterEdit"
      @save="saveCharacter"
      @export="actions.exportCharacterCard"
      @open-avatar-cropper="actions.showCharacterAvatarCropper.value = true"
      @open-assistant-settings="assistant.showAssistantSettings.value = true"
    />

    <PersonaEditorModal
      :show="actions.showPersonaEditor.value"
      :is-new-persona="actions.isNewPersona.value"
      :persona="actions.editingPersona.value"
      :avatar-url="editingPersonaAvatarUrl"
      :user-name="userName"
      @cancel="closePersonaEditor"
      @save="actions.savePersona"
      @open-avatar-cropper="actions.showPersonaAvatarCropper.value = true"
    />

    <PersonaSwitchConfirmModal
      :show="actions.showPersonaSwitchConfirm.value"
      @cancel="actions.cancelSwitchPersona"
      @continue-chat="confirmSwitchPersonaContinue"
      @new-session="confirmSwitchPersonaNewSession"
    />

    <AssistantSettingsModal
      :show="assistant.showAssistantSettings.value"
      :settings="assistant.assistantSettings.value"
      :allow-web-search="assistant.allowWebSearchEnabled.value"
      :allow-write-memory="assistant.allowWriteMemoryEnabled.value"
      :allow-destructive-tools="assistant.allowDestructiveToolsEnabled.value"
      @cancel="closeAssistantSettings"
      @save="assistant.saveSettingsAndClose"
      @update:allow-web-search="assistant.setAllowWebSearch"
      @update:allow-write-memory="setAssistantWriteMemoryEnabled"
      @update:allow-destructive-tools="setAssistantDestructiveToolsEnabled"
    />

    <EmbeddedCardConfirmModal
      :show="showEmbeddedCardConfirmModal"
      :embedded-card-preview="embeddedCardPreview"
      :st-preview="avatarEmbeddedStPreview"
      :st-expires-at="avatarEmbeddedStExpiresAt"
      :enable-mvu="avatarEmbeddedEnableMvu"
      :mvu-mode="avatarEmbeddedMvuMode"
      :mvu-mode-options="avatarEmbeddedMvuModeOptions"
      :detected-mvu="avatarEmbeddedDetectedMvu"
      :importing="embeddedCardImporting"
      :confirm-label="embeddedCardConfirmLabel"
      @cancel="clearEmbeddedCardPreviewState"
      @confirm="confirmImportEmbeddedCard"
      @update:enable-mvu="avatarEmbeddedEnableMvu = $event"
      @update:mvu-mode="updateAvatarEmbeddedMvuMode"
    />

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
  border-radius: var(--radius-lg);
  border: 1px solid var(--color-border-subtle);
  background-color: var(--color-chrome-widget);
  background-image: none;
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
  background-color: var(--color-popover-surface);
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
  background-color: var(--color-chat-dock);
}

.header-action-shortcut {
  padding: 0.15rem 0.35rem;
  border-radius: 999px;
  background-color: var(--color-surface-muted);
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
  border-radius: var(--radius-xl);
  border: 1px solid var(--color-border);
  background-color: var(--color-popover-surface);
  background-image: none;
  box-shadow: var(--shadow-glass-popover);
  transform-origin: top right;
  /* 磨砂用模板上的 glass blur token（避免手写 backdrop-filter 经构建压缩失效，且勿嵌套在父级 backdrop 内） */
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
  transition: grid-template-rows var(--motion-duration-expand) cubic-bezier(0.4, 0, 0.2, 1);
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
    opacity var(--motion-duration-expand) cubic-bezier(0.4, 0, 0.2, 1),
    transform var(--motion-duration-expand) cubic-bezier(0.25, 1, 0.5, 1);
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

/* MVU 状态条：从输入区方向滑入/滑出（锚点在底边） */
.mvu-state-bar-enter-active,
.mvu-state-bar-leave-active {
  transition:
    opacity 300ms cubic-bezier(0.4, 0, 0.2, 1),
    transform 320ms cubic-bezier(0.25, 1, 0.5, 1);
  transform-origin: bottom center;
}

.mvu-state-bar-enter-from,
.mvu-state-bar-leave-to {
  opacity: 0;
  transform: translateY(12px);
}

.mvu-state-bar-enter-to,
.mvu-state-bar-leave-from {
  opacity: 1;
  transform: translateY(0);
}

/* 会话搜索命中 chip 行：与主搜索区相同 grid 手法，顶栏高度随 ResizeObserver 连续变化 */
.chat-search-chips-expand {
  display: grid;
  grid-template-rows: 0fr;
  transition: grid-template-rows var(--chat-search-chips-ms, var(--motion-duration-expand)) cubic-bezier(0.4, 0, 0.2, 1);
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
    transform var(--chat-search-chips-ms, var(--motion-duration-expand)) cubic-bezier(0.25, 1, 0.5, 1),
    opacity var(--chat-search-chips-ms, var(--motion-duration-expand)) cubic-bezier(0.4, 0, 0.2, 1);
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
  .chat-header-groupstrip-leave-active,
  .mvu-state-bar-enter-active,
  .mvu-state-bar-leave-active {
    transition-duration: 0.01ms !important;
  }

  .header-search-trigger-enter-from,
  .header-search-trigger-leave-to,
  .header-more-pop-enter-from,
  .header-more-pop-leave-to,
  .chat-header-groupstrip-enter-from,
  .chat-header-groupstrip-leave-to,
  .mvu-state-bar-enter-from,
  .mvu-state-bar-leave-to {
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
  border-radius: var(--radius-lg);
  color: var(--color-text-secondary);
  text-align: left;
  transition: background-color 160ms ease, color 160ms ease;
}

.header-more-menu__item:hover:not(:disabled),
.header-more-menu__item:focus-visible {
  background-color: var(--color-surface-hover);
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
</style>
