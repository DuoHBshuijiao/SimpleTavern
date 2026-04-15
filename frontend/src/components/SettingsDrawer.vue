<script setup lang="ts">
/**
 * SettingsDrawer - 设置抽屉组件
 *
 * 组件职责：
 * - 提供应用设置的编辑界面
 * - 管理全局设置（LLM配置、API预设、生成参数等）
 * - 管理聊天覆盖设置（提示词、长期记忆、生成参数等）
 * - 底部「保存设置」一次提交全局草稿与当前会话覆盖（若适用）
 * - 支持导入导出设置
 * - 支持API预设管理
 * - 支持模型候选列表管理
 *
 * Props说明：
 * - show: 是否显示抽屉（v-model:show）
 * - chat: 当前聊天会话（来自types/models.ts的Chat类型，用于编辑聊天覆盖设置）
 * - initialTab: 初始标签页（'global'、'presets'或'chat'）
 *
 * Emits说明：
 * - update:show: 更新显示状态（v-model:show）
 * - open-member-settings: 打开成员设置编辑，传递成员ID
 *
 * 使用的Composables：
 * 无
 *
 * 使用的Stores：
 * - useSettingsStore: 来自stores/settings.ts，用于管理设置
 * - useChatsStore: 来自stores/chats.ts，用于更新聊天设置
 * - useCharactersStore: 来自stores/characters.ts，用于获取角色列表
 *
 * 文件关系：
 *    - 被导入：被views/ChatPage.vue使用
 *    - 导入：导入vue的computed、ref、watch、stores/index.ts的Store、types/models.ts的类型、components/ModernSelect.vue、components/ModelSelectorModal.vue、api/http.ts的apiPost
 *    - 依赖：依赖vue、stores、api/http.ts
 *    - 位置：组件层，提供设置管理功能
 */
import { computed, nextTick, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { useChatsStore, useCharactersStore, useSettingsStore } from '../stores'
import {
  normalizeReasoningEffort,
  normalizeThemeId,
  REASONING_EFFORT_OPTIONS,
  THEME_OPTIONS,
  type AutoReadScope,
  type ApiPreset,
  type ApiPresetVoice,
  type Chat,
  type ChatOverrides,
  type Settings,
  type TtsProvider,
  type TtsSessionConfig,
  type WorldBook,
  type WorldBookAttachment,
} from '../types/models'
import ModernSelect from './ModernSelect.vue'
import ThemedCheckbox from './ThemedCheckbox.vue'
import TtsVoiceInput from './TtsVoiceInput.vue'
import { apiDelete, apiGet, apiPost, apiPostFormData, apiPut } from '../api/http'
import { downloadUpdate, getManualUpdateCheck, runUpdate } from '../api/update'
import { useAppFont } from '../composables/useAppFont'
import { usePageBackground } from '../composables/usePageBackground'
import { useSettingsImport } from '../composables/useSettingsImport'
import {
  useWebGpuBackgroundRuntime,
  readWebGpuDraftSource,
  writeWebGpuDraftSource,
} from '../composables/useWebGpuBackgroundRuntime'
import { X, Eye, EyeOff, Check, Loader2, GripVertical, ChevronDown } from 'lucide-vue-next'
import WorldBookEditorModal from './modals/WorldBookEditorModal.vue'
import WorldBookSessionAttachModal from './modals/WorldBookSessionAttachModal.vue'
import { isTtsApiPreset, resolveTtsProvider } from '../utils/apiPresetKind'
import { getWebGpuUnavailableMessage, probeWebGpuAdapter } from '../utils/webgpuProbe'
import type { WebGpuUnavailableReason } from '../utils/webgpuProbe'
import { concatEnabledWorldBookContents, countTokensForText } from '../utils/tokenEstimate'
import { notifyConfirm, notifyMessage } from '../composables/useNotify'

const { applyFont } = useAppFont()

/** 当前应用版本，从后端 /api/update/version 获取 */
const appVersion = ref<string>('')

const props = defineProps<{
  show: boolean
  chat: Chat | null
  initialTab?: 'global' | 'presets' | 'chat'
}>()

const emit = defineEmits<{
  (e: 'update:show', v: boolean): void
  (e: 'open-member-settings', memberId: string): void
}>()

const settingsStore = useSettingsStore()
const chatsStore = useChatsStore()
const charactersStore = useCharactersStore()
const {
  importSettingsFile,
  refreshDataAfterImport,
  formatImportResultMessage,
} = useSettingsImport()

const tab = ref<'global' | 'presets' | 'chat'>('global')
const preloaded = ref(false)
const chatTabEverOpened = ref(false)
const pageBackgroundInputRef = ref<HTMLInputElement | null>(null)
const savedPageBackgroundImage = ref<string | null>(null)
const pendingPageBackgroundUploads = new Set<string>()
const { setRuntime: setWebGpuRuntime, clearRuntime: clearWebGpuRuntime, runtimeState: webgpuRuntimeState } =
  useWebGpuBackgroundRuntime()
const webgpuPresetEditorSource = ref('')
const webgpuPresetSourceDirty = ref(false)
const webgpuPresetCompileError = ref<string | null>(null)
const webgpuPresetCompiledHash = ref<string | null>(null)
const webgpuPresetCompileBusy = ref(false)
const webgpuPresetSaveBusy = ref(false)
const webgpuPresetCreateBusy = ref(false)
const webgpuPresetDeleteBusy = ref(false)
const webgpuAvailability = ref<'unknown' | 'available' | 'unavailable'>('unknown')
const webgpuLastProbeMessage = ref<string | null>(null)

watch(() => props.initialTab, (newTab) => {
  if (newTab) tab.value = newTab
}, { immediate: true })

watch(tab, (t) => {
  if (t === 'chat') chatTabEverOpened.value = true
})

const worldBookCreateExpanded = ref(false)
const worldBookNewNameDraft = ref('')

/** 全局设置 Tab 内折叠区块（不用原生 details，否则关闭时子树被立刻隐藏，grid 高度过渡无法反复播放） */
const globalAccordionOpen = reactive({
  connection: false,
  prompts: false,
  appearance: false,
  tts: false,
  app: false,
})

const globalDraft = ref<Settings | null>(null)
const chatDraft = ref<ChatOverrides | null>(null)
const isSaving = ref(false)

const showApiKey = ref(false)
const editingPresetId = ref<string | null>(null)
const editingPresetShowApiKey = ref(false)
const presetModelsLoading = ref(false)
const presetVoicesLoading = ref(false)
/** 预设「模型列表」区内多选，仅用于批量删除（非通用 API 工具） */
const presetModelListSelection = ref<Set<string>>(new Set())
const presetVoiceListSelection = ref<Set<string>>(new Set())
const importInputRef = ref<HTMLInputElement | null>(null)
const worldbooks = ref<WorldBook[]>([])
/** 全部世界书列表：按书 ID 缓存启用条目正文的 token 估测 */
const worldbookTokenTotals = ref<Record<string, number | null>>({})
const worldbookTokensLoading = ref(false)
const addWorldBookId = ref('')
const showWorldBookEditor = ref(false)
const worldBookEditorId = ref<string | null>(null)

const allWorldBooksSectionOpen = ref(false)
const allWorldBooksListExpanded = ref(false)
const sessionAttachModalShow = ref(false)
const sessionAttachIdx = ref<number | null>(null)
const ttsCloneSourceInputRef = ref<HTMLInputElement | null>(null)
const ttsClonePromptInputRef = ref<HTMLInputElement | null>(null)
const ttsCloneSourceFile = ref<File | null>(null)
const ttsClonePromptFile = ref<File | null>(null)
const ttsCloneLoading = ref(false)
const ttsClonePreviewUrl = ref<string | null>(null)
const ttsCloneDraft = reactive({
  voiceId: '',
  model: '',
  previewText: '',
  promptText: '',
  needNoiseReduction: false,
  needVolumeNormalization: false,
})
const ttsDesignLoading = ref(false)
const ttsDesignPreviewUrl = ref<string | null>(null)
const ttsDesignDraft = reactive({
  prompt: '',
  previewText: '',
  voiceId: '',
})

// GLM-TTS（本地）参考音色新增草稿
const glmLocalVoiceDraft = reactive({
  voiceId: '',
  name: '',
  promptText: '',
  promptAudioPath: '',
})

const qwen3LocalVoiceDraft = reactive({
  voiceId: '',
  name: '',
  instruction: '',
  promptText: '',
  promptAudioPath: '',
})

const omniVoiceLocalVoiceDraft = reactive({
  voiceId: '',
  name: '',
  promptText: '',
  promptAudioPath: '',
  instruction: '',
})

function addGlmLocalVoice() {
  const id = glmLocalVoiceDraft.voiceId.trim()
  if (!id) return
  upsertEditingPresetVoiceCatalog([{
    voiceId: id,
    name: glmLocalVoiceDraft.name.trim() || id,
    voiceType: 'local',
    promptText: glmLocalVoiceDraft.promptText.trim() || null,
    promptAudioPath: glmLocalVoiceDraft.promptAudioPath.trim() || null,
  }])
  glmLocalVoiceDraft.voiceId = ''
  glmLocalVoiceDraft.name = ''
  glmLocalVoiceDraft.promptText = ''
  glmLocalVoiceDraft.promptAudioPath = ''
}

function updateGlmLocalVoiceField(voiceId: string, field: 'promptText' | 'promptAudioPath', value: string) {
  const preset = editingPreset.value
  if (!preset?.voiceCatalog) return
  const voice = preset.voiceCatalog.find((v) => v.voiceId === voiceId)
  if (voice) {
    voice[field] = value.trim() || null
  }
}

function addQwen3LocalVoice() {
  const speaker = qwen3LocalVoiceDraft.voiceId.trim()
  if (!speaker) return
  upsertEditingPresetVoiceCatalog([{
    voiceId: speaker,
    name: qwen3LocalVoiceDraft.name.trim() || speaker,
    voiceType: 'local',
    instruction: qwen3LocalVoiceDraft.instruction.trim() || null,
    promptText: qwen3LocalVoiceDraft.promptText.trim() || null,
    promptAudioPath: qwen3LocalVoiceDraft.promptAudioPath.trim() || null,
  }])
  qwen3LocalVoiceDraft.voiceId = ''
  qwen3LocalVoiceDraft.name = ''
  qwen3LocalVoiceDraft.instruction = ''
  qwen3LocalVoiceDraft.promptText = ''
  qwen3LocalVoiceDraft.promptAudioPath = ''
}

function updateQwen3LocalVoiceField(
  voiceId: string,
  field: 'name' | 'instruction' | 'promptText' | 'promptAudioPath',
  value: string,
) {
  const preset = editingPreset.value
  if (!preset?.voiceCatalog) return
  const voice = preset.voiceCatalog.find((v) => v.voiceId === voiceId)
  if (!voice) return
  if (field === 'name') {
    voice.name = value.trim() || voice.voiceId
    return
  }
  if (field === 'instruction') {
    voice.instruction = value.trim() || null
    return
  }
  voice[field] = value.trim() || null
}

function onQwen3VoiceClonePortInput(e: Event) {
  const preset = editingPreset.value
  if (!preset) return
  const raw = (e.target as HTMLInputElement).value
  if (raw === '') {
    preset.ttsQwen3LocalVoiceClonePort = null
    return
  }
  const n = Number.parseInt(raw, 10)
  preset.ttsQwen3LocalVoiceClonePort = Number.isFinite(n) ? n : null
}

function addOmniVoiceLocalVoice() {
  const id = omniVoiceLocalVoiceDraft.voiceId.trim()
  if (!id) return
  upsertEditingPresetVoiceCatalog([{
    voiceId: id,
    name: omniVoiceLocalVoiceDraft.name.trim() || id,
    voiceType: 'local',
    promptText: omniVoiceLocalVoiceDraft.promptText.trim() || null,
    promptAudioPath: omniVoiceLocalVoiceDraft.promptAudioPath.trim() || null,
    instruction: omniVoiceLocalVoiceDraft.instruction.trim() || null,
  }])
  omniVoiceLocalVoiceDraft.voiceId = ''
  omniVoiceLocalVoiceDraft.name = ''
  omniVoiceLocalVoiceDraft.promptText = ''
  omniVoiceLocalVoiceDraft.promptAudioPath = ''
  omniVoiceLocalVoiceDraft.instruction = ''
}

function updateOmniVoiceLocalVoiceField(
  voiceId: string,
  field: 'name' | 'promptText' | 'promptAudioPath' | 'instruction',
  value: string,
) {
  const preset = editingPreset.value
  if (!preset?.voiceCatalog) return
  const voice = preset.voiceCatalog.find((v) => v.voiceId === voiceId)
  if (!voice) return
  if (field === 'name') {
    voice.name = value.trim() || voice.voiceId
    return
  }
  voice[field] = value.trim() || null
}

const TTS_AUTO_READ_OPTIONS: Array<{ label: string; value: AutoReadScope }> = [
  { label: '关', value: 'off' },
  { label: '角色', value: 'assistant_only' },
  { label: '用户', value: 'user_only' },
  { label: '全部', value: 'all' },
]

const TTS_PROVIDER_OPTIONS: Array<{ label: string; value: TtsProvider }> = [
  { label: 'MiniMax（兼容）', value: 'minimax' },
  { label: 'GLM TTS（智谱）', value: 'glm' },
  { label: 'GLM-TTS（本地）', value: 'glm_local' },
  { label: 'Qwen3-TTS（本地）', value: 'qwen3_local' },
  { label: 'OmniVoice（本地）', value: 'omnivoice_local' },
]

// --- TTS 缓存统计（轮询后端 GET /api/tts/cache/stats） ---
const ttsCacheStats = ref<{ usedBytes: number; limitBytes: number; lastPatrolAt: string; prunedFiles: number } | null>(null)
let ttsCachePollTimer: ReturnType<typeof setInterval> | null = null

function startTtsCachePoll() {
  fetchTtsCacheStats()
  if (ttsCachePollTimer) clearInterval(ttsCachePollTimer)
  ttsCachePollTimer = setInterval(fetchTtsCacheStats, 30_000)
}
function stopTtsCachePoll() {
  if (ttsCachePollTimer) { clearInterval(ttsCachePollTimer); ttsCachePollTimer = null }
}
async function fetchTtsCacheStats() {
  try {
    const res = await apiGet<{ usedBytes: number; limitBytes: number; lastPatrolAt: string; prunedFiles: number }>('/api/tts/cache/stats')
    ttsCacheStats.value = res
    console.log('[TTS][cache]', JSON.stringify(res))
  } catch { /* ignore when TTS disabled */ }
}
const ttsCachePercent = computed(() => {
  if (!ttsCacheStats.value || !ttsCacheStats.value.limitBytes) return 0
  return Math.min(100, Math.max(0, (ttsCacheStats.value.usedBytes / ttsCacheStats.value.limitBytes) * 100))
})
function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1048576).toFixed(1)} MB`
}

// 打开设置抽屉时从后端获取版本号（仅请求一次）；依赖 globalDraft / TTS 轮询，须放在其后避免 TDZ
watch(
  () => props.show,
  (visible) => {
    if (visible && !appVersion.value) {
      apiGet<{ version: string }>('/api/update/version')
        .then((res) => { appVersion.value = res.version })
        .catch(() => { appVersion.value = '' })
    }
    if (!visible) {
      worldBookCreateExpanded.value = false
      worldBookNewNameDraft.value = ''
      void deletePendingPageBackgrounds(savedPageBackgroundImage.value)
      stopTtsCachePoll()
    } else {
      // 打开时如果 TTS 已启用，开始轮询缓存统计
      if (globalDraft.value?.ttsEnabled) startTtsCachePoll()
    }
  },
  { immediate: true }
)

watch(
  () => [props.show, globalDraft.value?.ttsEnabled] as const,
  ([visible, enabled]) => {
    if (!visible) return
    if (enabled) startTtsCachePoll()
    else stopTtsCachePoll()
  },
)

// 检查更新
const checkUpdateLoading = ref(false)
const checkUpdateMessage = ref('')
const fontList = ref<string[]>([])
const fontInputRef = ref<HTMLInputElement | null>(null)

// Model Selector Modal State
const showModelSelector = ref(false)
const candidateModels = ref<string[]>([])
const selectedCandidateModels = ref<Set<string>>(new Set())
const modelSelectorQuery = ref('')

// Voice Selector Modal State（与「从 API 获取并筛选」模型列表同交互）
const showVoiceSelector = ref(false)
const candidateVoices = ref<ApiPresetVoice[]>([])
const selectedCandidateVoiceIds = ref<Set<string>>(new Set())
const voiceSelectorQuery = ref('')

// Token 估算（长期记忆 / 对话长度）
const memoryTokenEstimate = ref<number | null>(null)
const chatTokenEstimate = ref<number | null>(null)
const messagesSinceLastMemoryUpdate = ref<number | null>(null)
const tokensSinceLastMemoryUpdate = ref<number | null>(null)
const memoryTokenLoading = ref(false)
const chatTokenLoading = ref(false)
const suppressTokenEstimates = ref(false)
let memoryDebounceTimer: ReturnType<typeof setTimeout> | null = null
const worldbookTokenEstimateCache = new Map<string, { updatedAt: string | null; tokens: number | null }>()

/**
 * 关闭抽屉
 *
 * 触发update:show事件，传递false。
 */
function close() {
  emit('update:show', false)
}

async function deletePageBackgroundFile(filename: string | null | undefined) {
  const normalized = filename?.trim()
  if (!normalized) return
  try {
    await apiDelete(`/api/page-backgrounds/${encodeURIComponent(normalized)}`)
  } catch {
    // 后台文件清理失败不应阻塞设置流程；下次同名资源也不会再被引用。
  }
}

function markSavedPageBackground(filename: string | null | undefined) {
  const normalized = filename?.trim() || null
  savedPageBackgroundImage.value = normalized
  if (normalized) pendingPageBackgroundUploads.delete(normalized)
}

async function deletePendingPageBackgrounds(exceptFilename: string | null | undefined = null) {
  const keep = exceptFilename?.trim() || null
  const stale = [...pendingPageBackgroundUploads].filter((name) => name !== keep)
  stale.forEach((name) => pendingPageBackgroundUploads.delete(name))
  await Promise.allSettled(stale.map((name) => deletePageBackgroundFile(name)))
}

function formatSaveError(prefix: string, error: unknown): string {
  return `${prefix}: ${error instanceof Error ? error.message : String(error)}`
}

/**
 * 一次保存设置抽屉内的全部变更：先全局草稿，再当前会话覆盖（若适用）。
 */
async function handleSaveAll() {
  if (isSaving.value) return
  isSaving.value = true
  suppressTokenEstimates.value = true
  try {
    await saveGlobal()
    await saveChatOverrides()
    close()
  } catch (error) {
    await notifyMessage(formatSaveError('保存设置失败', error))
  } finally {
    suppressTokenEstimates.value = false
    isSaving.value = false
  }
}

/**
 * 深拷贝对象
 *
 * 使用JSON序列化和反序列化实现深拷贝。
 *
 * @template T - 对象类型
 * @param {T} v - 要拷贝的对象
 * @returns {T} 拷贝后的对象
 */
function clone<T>(v: T): T {
  return JSON.parse(JSON.stringify(v)) as T
}

/**
 * 确保覆盖设置格式正确
 *
 * 确保返回的ChatOverrides对象包含所有必需字段，缺失字段使用null。
 *
 * @param {Partial<ChatOverrides> | null | undefined} v - 部分覆盖设置
 * @returns {ChatOverrides} 完整的覆盖设置对象（来自types/models.ts）
 */
function ensureOverrides(v?: Partial<ChatOverrides> | null): ChatOverrides {
  let attachments: WorldBookAttachment[] = [...(v?.worldBookAttachments || [])]
  const ids = v?.worldBookIds || []
  if (attachments.length === 0 && ids.length > 0) {
    attachments = ids.map((id) => ({
      worldBookId: id,
      scanDepth: null,
      insertDepth: 5,
    }))
  }
  const worldBookIds = attachments.map((a) => a.worldBookId)
  return {
    prompt: v?.prompt ?? null,
    sessionSystemPromptMode: v?.sessionSystemPromptMode === 'override' ? 'override' : 'append',
    longTermMemory: v?.longTermMemory ?? null,
    contextStartMessageId: v?.contextStartMessageId ?? null,
    presetId: v?.presetId ?? null,
    pureAiMode: v?.pureAiMode ?? null,
    worldBookIds,
    worldBookAttachments: attachments,
    worldBookGlobalExclusions: [...(v?.worldBookGlobalExclusions || [])],
    params: {
      model: v?.params?.model ?? null,
      temperature: v?.params?.temperature ?? null,
      top_p: v?.params?.top_p ?? null,
      max_tokens: v?.params?.max_tokens ?? null,
      context_size: v?.params?.context_size ?? null,
    },
    draftHelp: {
      context_message_limit: v?.draftHelp?.context_message_limit ?? null,
    },
    memberSettings: v?.memberSettings ? { ...v.memberSettings } : undefined,
    tts: ensureTtsSessionConfig(v?.tts),
    autoMemorySummaryEveryN:
      typeof v?.autoMemorySummaryEveryN === 'number' &&
      Number.isFinite(v.autoMemorySummaryEveryN) &&
      v.autoMemorySummaryEveryN >= 1
        ? Math.floor(v.autoMemorySummaryEveryN)
        : null,
    lastAutoMemorySummaryAfterMessageId: v?.lastAutoMemorySummaryAfterMessageId ?? null,
    autoMemorySummarySilent: v?.autoMemorySummarySilent === true,
    autoMemorySummaryNextAskTier:
      typeof v?.autoMemorySummaryNextAskTier === 'number' &&
      Number.isFinite(v.autoMemorySummaryNextAskTier) &&
      v.autoMemorySummaryNextAskTier >= 1
        ? Math.floor(v.autoMemorySummaryNextAskTier)
        : 1,
  }
}

function normalizeVoiceMap(source?: Record<string, string> | null): Record<string, string> {
  const next: Record<string, string> = {}
  for (const [key, value] of Object.entries(source || {})) {
    const normalizedKey = String(key || '').trim()
    const normalizedValue = String(value || '').trim()
    if (!normalizedKey || !normalizedValue) continue
    next[normalizedKey] = normalizedValue
  }
  return next
}

function ensureTtsSessionConfig(source?: TtsSessionConfig | null): TtsSessionConfig {
  return {
    autoReadScope: source?.autoReadScope ?? 'off',
    readGapSeconds: typeof source?.readGapSeconds === 'number' && Number.isFinite(source.readGapSeconds)
      ? Math.max(0, source.readGapSeconds)
      : 0,
    model: source?.model?.trim() || null,
    voiceByCharacterId: normalizeVoiceMap(source?.voiceByCharacterId),
    voiceByPersonaId: normalizeVoiceMap(source?.voiceByPersonaId),
    presetId: source?.presetId?.trim() || null,
    preprocessEnabled: source?.preprocessEnabled === true,
    preprocessModel: source?.preprocessModel?.trim() || null,
    preprocessPresetId: source?.preprocessPresetId?.trim() || null,
    preprocessTargetLanguage: source?.preprocessTargetLanguage?.trim() || null,
    injectEmotionTags: source?.injectEmotionTags === true,
  }
}

function ensureChatTtsConfig(): TtsSessionConfig | null {
  if (!chatDraft.value) return null
  chatDraft.value.tts = ensureTtsSessionConfig(chatDraft.value.tts)
  return chatDraft.value.tts
}

function updateChatTtsAutoReadScope(scope: AutoReadScope) {
  const tts = ensureChatTtsConfig()
  if (!tts) return
  tts.autoReadScope = scope
}

function updateChatTtsReadGapSeconds(rawValue: string | number) {
  const tts = ensureChatTtsConfig()
  if (!tts) return
  const numeric = Number(rawValue)
  tts.readGapSeconds = Number.isFinite(numeric) ? Math.max(0, numeric) : 0
}

function updateChatTtsModel(option: { value: string; presetId?: string | null }) {
  const tts = ensureChatTtsConfig()
  if (!tts) return
  tts.model = option.value?.trim() || null
  tts.presetId = option.presetId ?? tts.presetId ?? null
}

function updateChatTtsPreprocessEnabled(enabled: boolean) {
  const tts = ensureChatTtsConfig()
  if (!tts) return
  tts.preprocessEnabled = enabled
}

function updateChatTtsInjectEmotionTags(enabled: boolean) {
  const tts = ensureChatTtsConfig()
  if (!tts) return
  tts.injectEmotionTags = selectedChatTtsProvider.value === 'minimax' ? enabled : false
}

function updateChatTtsPreprocessTargetLanguage(rawValue: string) {
  const tts = ensureChatTtsConfig()
  if (!tts) return
  const v = rawValue.trim()
  tts.preprocessTargetLanguage = v || null
}

function updateChatTtsPreprocessModel(option: { value: string; presetId?: string | null }) {
  const tts = ensureChatTtsConfig()
  if (!tts) return
  tts.preprocessModel = option.value?.trim() || null
  tts.preprocessPresetId = option.presetId ?? null
}

function getCharacterVoiceValue(characterId: string): string {
  return chatDraft.value?.tts?.voiceByCharacterId?.[characterId] ?? ''
}

function updateCharacterVoiceValue(characterId: string, rawValue: string) {
  const tts = ensureChatTtsConfig()
  if (!tts) return
  const value = rawValue.trim()
  const next = { ...tts.voiceByCharacterId }
  if (value) next[characterId] = value
  else delete next[characterId]
  tts.voiceByCharacterId = next
}

function getPersonaVoiceValue(personaId: string): string {
  return chatDraft.value?.tts?.voiceByPersonaId?.[personaId] ?? ''
}

function updatePersonaVoiceValue(personaId: string, rawValue: string) {
  const tts = ensureChatTtsConfig()
  if (!tts) return
  const value = rawValue.trim()
  const next = { ...tts.voiceByPersonaId }
  if (value) next[personaId] = value
  else delete next[personaId]
  tts.voiceByPersonaId = next
}

function isTtsPreset(preset?: ApiPreset | null): boolean {
  return isTtsApiPreset(preset)
}

function normalizePresetDraft(preset: ApiPreset): ApiPreset {
  const isTts = isTtsApiPreset(preset)
  return {
    ...preset,
    presetKind: isTts ? 'tts' : (preset.presetKind ?? null),
    ttsProvider: isTts ? resolveTtsProvider(preset) : null,
    voiceCatalog: normalizeVoiceCatalog(preset.voiceCatalog),
  }
}

function resetTtsPresetTransientUi() {
  presetVoiceListSelection.value = new Set()
  candidateVoices.value = []
  selectedCandidateVoiceIds.value = new Set()
  showVoiceSelector.value = false
  ttsClonePreviewUrl.value = null
  ttsDesignPreviewUrl.value = null
  ttsClonePromptFile.value = null
  ttsCloneDraft.promptText = ''
  ttsCloneDraft.needNoiseReduction = false
  ttsCloneDraft.needVolumeNormalization = false
}

function applyPresetTtsProvider(
  preset: ApiPreset,
  provider: TtsProvider,
  options?: { notifyOnSwitch?: boolean },
) {
  const nextProvider: TtsProvider = provider === 'glm'
    ? 'glm'
    : provider === 'glm_local'
      ? 'glm_local'
      : provider === 'qwen3_local'
        ? 'qwen3_local'
        : provider === 'omnivoice_local'
          ? 'omnivoice_local'
        : 'minimax'
  const previousProvider = resolveTtsProvider(preset)
  preset.presetKind = 'tts'
  preset.ttsProvider = nextProvider
  if (previousProvider === nextProvider) return
  preset.voiceCatalog = []
  resetTtsPresetTransientUi()
  if (nextProvider === 'glm' && !preset.models.includes('glm-tts')) {
    preset.models = ['glm-tts', ...preset.models.filter((modelName) => modelName !== 'glm-tts')]
  }
  if (nextProvider === 'glm_local') {
    // 本地模式初始化默认字段
    if (!preset.ttsGlmLocalPort) preset.ttsGlmLocalPort = 8088
    if (preset.ttsGlmLocalManaged === undefined) preset.ttsGlmLocalManaged = false
    if (!preset.baseUrl || preset.baseUrl === 'https://api.openai.com') {
      preset.baseUrl = `http://127.0.0.1:${preset.ttsGlmLocalPort}`
    }
  }
  if (nextProvider === 'qwen3_local') {
    if (!preset.ttsQwen3LocalPort) preset.ttsQwen3LocalPort = 8080
    if (preset.ttsQwen3LocalManaged === undefined) preset.ttsQwen3LocalManaged = false
    if (!preset.ttsQwen3LocalModelId?.trim()) preset.ttsQwen3LocalModelId = 'Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice'
    if (!preset.ttsQwen3LocalBaseModelId?.trim()) preset.ttsQwen3LocalBaseModelId = 'Qwen/Qwen3-TTS-12Hz-1.7B-Base'
    if (!preset.ttsQwen3LocalDevice?.trim()) preset.ttsQwen3LocalDevice = 'cuda:0'
    if (!preset.ttsQwen3LocalDefaultLanguage?.trim()) preset.ttsQwen3LocalDefaultLanguage = 'Auto'
    if (!preset.baseUrl || preset.baseUrl === 'https://api.openai.com') {
      preset.baseUrl = `http://127.0.0.1:${preset.ttsQwen3LocalPort}`
    }
  }
  if (nextProvider === 'omnivoice_local') {
    if (!preset.ttsOmniVoiceLocalPort) preset.ttsOmniVoiceLocalPort = 8089
    if (preset.ttsOmniVoiceLocalManaged === undefined) preset.ttsOmniVoiceLocalManaged = false
    if (!preset.ttsOmniVoiceLocalModelId?.trim()) preset.ttsOmniVoiceLocalModelId = 'k2-fsa/OmniVoice'
    if (preset.ttsOmniVoiceLocalDevice === undefined || preset.ttsOmniVoiceLocalDevice === null) preset.ttsOmniVoiceLocalDevice = 'cuda:0'
    if (!preset.models.includes('omnivoice-tts')) {
      preset.models = ['omnivoice-tts', ...preset.models.filter((modelName) => modelName !== 'omnivoice-tts')]
    }
    if (!preset.baseUrl || preset.baseUrl === 'https://api.openai.com') {
      preset.baseUrl = `http://127.0.0.1:${preset.ttsOmniVoiceLocalPort}`
    }
  }
  if (options?.notifyOnSwitch !== false) {
    void notifyMessage('已切换 TTS 提供商，请重新配置音色。')
  }
}

function setPresetTtsService(preset: ApiPreset, enabled: boolean) {
  if (!enabled) {
    preset.presetKind = null
    preset.ttsProvider = null
    preset.voiceCatalog = []
    resetTtsPresetTransientUi()
    return
  }
  applyPresetTtsProvider(preset, resolveTtsProvider(preset), { notifyOnSwitch: false })
}

function setPresetTtsProvider(preset: ApiPreset, provider: TtsProvider) {
  applyPresetTtsProvider(preset, provider)
}

function onEditingPresetTtsProviderChange(v: string) {
  const preset = editingPreset.value
  if (!preset) return
  setPresetTtsProvider(preset, v as TtsProvider)
}

function normalizeVoiceCatalog(voices?: ApiPresetVoice[] | null): ApiPresetVoice[] {
  const next = new Map<string, ApiPresetVoice>()
  for (const voice of voices || []) {
    const voiceId = String(voice.voiceId || '').trim()
    if (!voiceId) continue
    const promptText =
      voice.promptText != null && String(voice.promptText).trim()
        ? String(voice.promptText).trim()
        : null
    const promptAudioPath =
      voice.promptAudioPath != null && String(voice.promptAudioPath).trim()
        ? String(voice.promptAudioPath).trim()
        : null
    const instruction =
      voice.instruction != null && String(voice.instruction).trim()
        ? String(voice.instruction).trim()
        : null
    next.set(voiceId, {
      voiceId,
      name: String(voice.name || voiceId).trim() || voiceId,
      voiceType: String(voice.voiceType || 'system').trim() || 'system',
      promptText,
      promptAudioPath,
      instruction,
    })
  }
  return [...next.values()]
}

function ensureDraftHelpDefaults(target?: { context_message_limit?: number | null } | null) {
  return {
    context_message_limit: target?.context_message_limit ?? null,
  }
}

const pageBackground = usePageBackground(() => globalDraft.value)

const pageBackgroundOpacityModel = computed({
  get: () => Math.round(pageBackground.opacity.value * 100),
  set: (value: number | string) => {
    if (!globalDraft.value) return
    const numeric = Number(value)
    if (!Number.isFinite(numeric)) {
      globalDraft.value.pageBackgroundOpacity = null
      return
    }
    const clamped = Math.max(0, Math.min(100, numeric))
    globalDraft.value.pageBackgroundOpacity = clamped >= 100 ? null : Number((clamped / 100).toFixed(2))
  },
})

const pageBackgroundBlurModel = computed({
  get: () => Math.round(pageBackground.blurPx.value),
  set: (value: number | string) => {
    if (!globalDraft.value) return
    const numeric = Number(value)
    if (!Number.isFinite(numeric)) {
      globalDraft.value.pageBackgroundBlurPx = null
      return
    }
    const clamped = Math.max(0, Math.min(64, Math.round(numeric)))
    globalDraft.value.pageBackgroundBlurPx = clamped <= 0 ? null : clamped
  },
})

const webgpuPresets = computed(() => globalDraft.value?.webgpuBackgroundPresets || [])
const activeWebgpuPresetId = computed({
  get: () => globalDraft.value?.webgpuBackgroundActivePresetId ?? null,
  set: (value: string | null) => {
    if (!globalDraft.value) return
    globalDraft.value.webgpuBackgroundActivePresetId = value
  },
})
const activeWebgpuPreset = computed(() => {
  const id = activeWebgpuPresetId.value
  if (!id) return null
  return webgpuPresets.value.find((item) => item.id === id) || null
})
const webgpuCanRunFromEditor = computed(() => {
  const preset = activeWebgpuPreset.value
  if (!preset) return false
  if (webgpuPresetSourceDirty.value) return false
  if (webgpuPresetCompileBusy.value) return false
  return webgpuPresetCompiledHash.value === buildSourceHash(preset.wgslFile, webgpuPresetEditorSource.value)
})

function ensureWebgpuSettingsShape(target: Settings) {
  if (target.webgpuBackgroundEnabled === undefined) target.webgpuBackgroundEnabled = false
  if (!target.webgpuBackgroundPresets) target.webgpuBackgroundPresets = []
  if (target.webgpuBackgroundActivePresetId === undefined) target.webgpuBackgroundActivePresetId = null
  target.webgpuBackgroundPresets = (target.webgpuBackgroundPresets || [])
    .filter((item) => item && item.id && item.wgslFile)
    .map((item) => ({
      id: String(item.id),
      name: String(item.name || 'WebGPU 预设').trim() || 'WebGPU 预设',
      wgslFile: String(item.wgslFile),
    }))
  if (target.webgpuBackgroundActivePresetId) {
    const exists = target.webgpuBackgroundPresets.some((item) => item.id === target.webgpuBackgroundActivePresetId)
    if (!exists) target.webgpuBackgroundActivePresetId = null
  }
}

function buildSourceHash(filename: string, source: string): string {
  return `${filename}:${source.length}:${source.slice(0, 32)}:${source.slice(-32)}`
}

async function ensureWebGpuAvailability() {
  if (webgpuAvailability.value !== 'unknown') return
  const result = await probeWebGpuAdapter()
  if (result.ok) {
    webgpuAvailability.value = 'available'
    webgpuLastProbeMessage.value = null
  } else {
    webgpuAvailability.value = 'unavailable'
    webgpuLastProbeMessage.value = getWebGpuUnavailableMessage(
      result.reason as WebGpuUnavailableReason,
    )
  }
}

async function loadWebGpuPresetSource(presetId: string | null) {
  if (!presetId) {
    webgpuPresetEditorSource.value = ''
    webgpuPresetSourceDirty.value = false
    webgpuPresetCompileError.value = null
    webgpuPresetCompiledHash.value = null
    return
  }
  const preset = webgpuPresets.value.find((item) => item.id === presetId)
  if (!preset) return
  const cached = readWebGpuDraftSource(preset.id)
  if (cached != null) {
    webgpuPresetEditorSource.value = cached
    webgpuPresetSourceDirty.value = true
    webgpuPresetCompileError.value = null
    webgpuPresetCompiledHash.value = null
    return
  }
  try {
    const response = await fetch(`/api/shader-presets/${encodeURIComponent(preset.wgslFile)}`, {
      method: 'GET',
      headers: { Accept: 'text/plain' },
    })
    if (!response.ok) throw new Error(await response.text())
    const source = await response.text()
    webgpuPresetEditorSource.value = source
    webgpuPresetSourceDirty.value = false
    webgpuPresetCompileError.value = null
    webgpuPresetCompiledHash.value = null
  } catch (error) {
    webgpuPresetEditorSource.value = ''
    webgpuPresetSourceDirty.value = false
    webgpuPresetCompileError.value = error instanceof Error ? error.message : String(error)
  }
}

function onWebGpuEditorInput(value: string) {
  webgpuPresetEditorSource.value = value
  const preset = activeWebgpuPreset.value
  if (!preset) return
  webgpuPresetSourceDirty.value = true
  webgpuPresetCompileError.value = null
  webgpuPresetCompiledHash.value = null
  writeWebGpuDraftSource(preset.id, value)
}

function onWebGpuEditorInputEvent(event: Event) {
  onWebGpuEditorInput((event.target as HTMLTextAreaElement).value)
}

async function saveWebGpuPresetSource() {
  const preset = activeWebgpuPreset.value
  if (!preset) return
  webgpuPresetSaveBusy.value = true
  try {
    const response = await fetch(`/api/shader-presets/${encodeURIComponent(preset.wgslFile)}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ source: webgpuPresetEditorSource.value }),
    })
    if (!response.ok) throw new Error(await response.text())
    webgpuPresetSourceDirty.value = false
    writeWebGpuDraftSource(preset.id, null)
    webgpuPresetCompiledHash.value = null
    await notifyMessage('WGSL 已保存。')
  } catch (error) {
    await notifyMessage('保存 WGSL 失败：' + String(error))
  } finally {
    webgpuPresetSaveBusy.value = false
  }
}

async function compileWebGpuPreset() {
  const preset = activeWebgpuPreset.value
  if (!preset) return
  await ensureWebGpuAvailability()
  if (webgpuAvailability.value !== 'available') {
    webgpuPresetCompileError.value =
      webgpuLastProbeMessage.value ?? getWebGpuUnavailableMessage('unknown')
    return
  }
  webgpuPresetCompileBusy.value = true
  webgpuPresetCompileError.value = null
  try {
    const gpu = navigator.gpu
    if (!gpu) throw new Error('WebGPU unavailable')
    const adapter = await gpu.requestAdapter()
    if (!adapter) throw new Error('WebGPU adapter unavailable')
    const device = await adapter.requestDevice()
    const module = device.createShaderModule({ code: webgpuPresetEditorSource.value })
    const info = await module.getCompilationInfo()
    const errors = info.messages.filter((item: any) => item.type === 'error')
    if (errors.length > 0) {
      throw new Error(errors.map((item: any) => item.message).join('\n'))
    }
    webgpuPresetCompiledHash.value = buildSourceHash(preset.wgslFile, webgpuPresetEditorSource.value)
    await notifyMessage('编译通过，可点击「运行（仅本次）」应用。')
  } catch (error) {
    webgpuPresetCompiledHash.value = null
    webgpuPresetCompileError.value = error instanceof Error ? error.message : String(error)
  } finally {
    webgpuPresetCompileBusy.value = false
  }
}

function runWebGpuPresetInRuntime() {
  const preset = activeWebgpuPreset.value
  if (!preset || !webgpuCanRunFromEditor.value) return
  setWebGpuRuntime({
    enabled: globalDraft.value?.webgpuBackgroundEnabled === true,
    activePresetId: preset.id,
  })
  void notifyMessage('已应用到主界面（仅运行态，未写入后端）。')
}

function stopWebGpuRuntime() {
  clearWebGpuRuntime()
  void notifyMessage('已退出 WebGPU 运行态，主界面恢复使用已保存设置。')
}

async function createWebGpuPreset() {
  if (!globalDraft.value) return
  webgpuPresetCreateBusy.value = true
  try {
    const response = await fetch('/api/shader-presets', { method: 'POST' })
    if (!response.ok) throw new Error(await response.text())
    const created = (await response.json()) as { filename: string }
    const filename = String(created.filename || '').trim()
    if (!filename) throw new Error('invalid server response')
    const preset = {
      id: crypto.randomUUID().replace(/-/g, ''),
      name: `WebGPU 预设 ${globalDraft.value.webgpuBackgroundPresets!.length + 1}`,
      wgslFile: filename,
    }
    globalDraft.value.webgpuBackgroundPresets!.push(preset)
    globalDraft.value.webgpuBackgroundActivePresetId = preset.id
    await loadWebGpuPresetSource(preset.id)
  } catch (error) {
    await notifyMessage('创建 WebGPU 预设失败：' + String(error))
  } finally {
    webgpuPresetCreateBusy.value = false
  }
}

async function deleteActiveWebGpuPreset() {
  const preset = activeWebgpuPreset.value
  if (!globalDraft.value || !preset) return
  const ok = await notifyConfirm({
    title: '删除 WebGPU 预设',
    message: `确定删除「${preset.name}」及其 WGSL 文件吗？`,
    variant: 'danger',
  })
  if (!ok) return
  webgpuPresetDeleteBusy.value = true
  try {
    await apiDelete(`/api/shader-presets/${encodeURIComponent(preset.wgslFile)}`)
    globalDraft.value.webgpuBackgroundPresets = globalDraft.value.webgpuBackgroundPresets!.filter(
      (item) => item.id !== preset.id,
    )
    if (globalDraft.value.webgpuBackgroundActivePresetId === preset.id) {
      globalDraft.value.webgpuBackgroundActivePresetId =
        globalDraft.value.webgpuBackgroundPresets[0]?.id ?? null
    }
    writeWebGpuDraftSource(preset.id, null)
    if (webgpuRuntimeState.activePresetId === preset.id) {
      clearWebGpuRuntime()
    }
    await loadWebGpuPresetSource(globalDraft.value.webgpuBackgroundActivePresetId ?? null)
  } catch (error) {
    await notifyMessage('删除 WebGPU 预设失败：' + String(error))
  } finally {
    webgpuPresetDeleteBusy.value = false
  }
}

watch(activeWebgpuPresetId, (nextId) => {
  void loadWebGpuPresetSource(nextId)
})

function findLatestMemorySavedMessageId(chat: Chat | null): string | null {
  if (!chat?.messages?.length) return null
  for (let i = chat.messages.length - 1; i >= 0; i--) {
    const m = chat.messages[i]
    if (m?.memoryUpdatedAfterThis) return m.id
  }
  return null
}

async function hideSavedFloors() {
  if (!props.chat?.id || !chatDraft.value) return
  const anchorId = findLatestMemorySavedMessageId(props.chat)
  if (!anchorId) {
    await notifyMessage('当前会话未找到「已保存记忆」标记消息，无法从该处截断上下文。')
    return
  }
  chatDraft.value.contextStartMessageId = anchorId
  await saveChatOverrides()
}

async function resetHiddenFloors() {
  if (!props.chat?.id || !chatDraft.value) return
  chatDraft.value.contextStartMessageId = null
  await saveChatOverrides()
}

async function fetchMemoryTokenCount() {
  if (suppressTokenEstimates.value) return
  memoryTokenLoading.value = true
  memoryTokenEstimate.value = null
  try {
    const text = chatDraft.value?.longTermMemory ?? ''
    const res = await apiPost<{ tokens: number | null }>('/api/tokenizer/count', { text })
    memoryTokenEstimate.value = res.tokens
  } catch {
    memoryTokenEstimate.value = null
  } finally {
    memoryTokenLoading.value = false
  }
}

async function fetchChatTokenCount() {
  if (suppressTokenEstimates.value) return
  const c = props.chat
  if (!c?.id) {
    chatTokenEstimate.value = null
    messagesSinceLastMemoryUpdate.value = null
    tokensSinceLastMemoryUpdate.value = null
    return
  }
  chatTokenLoading.value = true
  chatTokenEstimate.value = null
  messagesSinceLastMemoryUpdate.value = null
  tokensSinceLastMemoryUpdate.value = null
  try {
    const res = await apiGet<{
      tokens: number | null
      messagesSinceLastMemoryUpdate: number | null
      tokensSinceLastMemoryUpdate: number | null
    }>(`/api/tokenizer/chat-count?chatId=${encodeURIComponent(c.id)}`)
    chatTokenEstimate.value = res.tokens
    messagesSinceLastMemoryUpdate.value = res.messagesSinceLastMemoryUpdate ?? null
    tokensSinceLastMemoryUpdate.value = res.tokensSinceLastMemoryUpdate ?? null
  } catch {
    chatTokenEstimate.value = null
    messagesSinceLastMemoryUpdate.value = null
    tokensSinceLastMemoryUpdate.value = null
  } finally {
    chatTokenLoading.value = false
  }
}

onMounted(() => {
  setTimeout(async () => {
    if (!settingsStore.settings) await settingsStore.load()
    await ensureWebGpuAvailability()
    if (fontList.value.length === 0) {
      try {
        fontList.value = await apiGet<string[]>('/api/fonts')
      } catch {
        fontList.value = []
      }
    }
    preloaded.value = true
  }, 150)
})

async function refreshWorldbookTokenTotals() {
  const list = worldbooks.value
  if (list.length === 0) {
    worldbookTokenTotals.value = {}
    return
  }
  const map: Record<string, number | null> = {}
  const staleBooks: WorldBook[] = []
  for (const book of list) {
    const cached = worldbookTokenEstimateCache.get(book.id)
    const updatedAt = book.updatedAt ?? null
    if (cached && cached.updatedAt === updatedAt) {
      map[book.id] = cached.tokens
    } else {
      staleBooks.push(book)
    }
  }
  if (staleBooks.length === 0) {
    worldbookTokenTotals.value = map
    return
  }
  worldbookTokensLoading.value = true
  try {
    const results = await Promise.all(
      staleBooks.map(async (b) => {
        const text = concatEnabledWorldBookContents(b)
        const n = await countTokensForText(text)
        return [b.id, n] as const
      }),
    )
    for (const [id, n] of results) {
      map[id] = n
      const book = staleBooks.find((item) => item.id === id)
      worldbookTokenEstimateCache.set(id, {
        updatedAt: book?.updatedAt ?? null,
        tokens: n,
      })
    }
    worldbookTokenTotals.value = map
  } finally {
    worldbookTokensLoading.value = false
  }
}

async function loadWorldBooks(options?: { refreshTokenTotals?: boolean }) {
  try {
    worldbooks.value = await apiGet<WorldBook[]>('/api/worldbooks')
  } catch {
    worldbooks.value = []
  }
  if (options?.refreshTokenTotals !== false) {
    await refreshWorldbookTokenTotals()
  }
}

function worldbookTokenHint(bookId: string): string {
  if (worldbookTokensLoading.value) return '约 …'
  const v = worldbookTokenTotals.value[bookId]
  if (v === undefined) return ''
  if (v === null) return '无法估算'
  return `约 ${v} tokens`
}

function openWorldBookEditor(worldbookId: string) {
  worldBookEditorId.value = worldbookId
  showWorldBookEditor.value = true
}

async function confirmCreateWorldBook() {
  const name = worldBookNewNameDraft.value.trim()
  if (!name) {
    await notifyMessage('请输入世界书名称')
    return
  }
  const now = new Date().toISOString()
  const payload: WorldBook = {
    id: crypto.randomUUID().replace(/-/g, ''),
    name,
    entries: [],
    globalActive: false,
    sessionChatIds: [],
    createdAt: now,
    updatedAt: now,
  }
  try {
    const created = await apiPost<WorldBook>('/api/worldbooks', payload)
    await loadWorldBooks()
    worldBookCreateExpanded.value = false
    worldBookNewNameDraft.value = ''
    openWorldBookEditor(created.id)
  } catch (e) {
    await notifyMessage('创建世界书失败: ' + String(e))
  }
}

async function onWorldBookEditorDeleted(worldbookId: string) {
  await loadWorldBooks()
  removeWorldBookFromOrder(worldbookId)
  if (chatDraft.value?.worldBookGlobalExclusions?.includes(worldbookId)) {
    chatDraft.value.worldBookGlobalExclusions = chatDraft.value.worldBookGlobalExclusions.filter((id) => id !== worldbookId)
  }
}

function cancelWorldBookCreate() {
  worldBookCreateExpanded.value = false
  worldBookNewNameDraft.value = ''
}

watch(
  () => props.show,
  async (open) => {
    if (!open) return
    if (!settingsStore.settings) await settingsStore.load()
    const s = clone(settingsStore.settings!)
    if (s.streamEnabled === undefined) s.streamEnabled = true
    if ((s as Settings).pureAiMode === undefined) (s as Settings).pureAiMode = false
    ;(s as Settings).reasoningEffort = normalizeReasoningEffort(
      (s as Settings).reasoningEffort,
      (s as Settings).thinkingMode,
    )
    if ((s as Settings).themeId === undefined || (s as Settings).themeId === null) {
      (s as Settings).themeId = 'rose'
    } else {
      ;(s as Settings).themeId = normalizeThemeId((s as Settings).themeId as string)
    }
    if (!s.apiPresets) s.apiPresets = []
    s.apiPresets = s.apiPresets.map((preset) => normalizePresetDraft(preset))
    if (!(s as Settings).draftHelpDefaults) (s as Settings).draftHelpDefaults = ensureDraftHelpDefaults()
    if (s.selectedFont === undefined) (s as Settings).selectedFont = null
    if ((s as Settings).pageBackgroundImage === undefined) (s as Settings).pageBackgroundImage = null
    if ((s as Settings).pageBackgroundOpacity === undefined) (s as Settings).pageBackgroundOpacity = null
    if ((s as Settings).pageBackgroundBlurPx === undefined) (s as Settings).pageBackgroundBlurPx = null
    ensureWebgpuSettingsShape(s as Settings)
    if ((s as Settings).messageFontSize === undefined) (s as Settings).messageFontSize = null
    if (!s.prompts) {
      s.prompts = { globalSystem: '', globalPrefill: '', globalPrefillEnabled: true }
    } else {
      if (s.prompts.globalSystem === undefined) s.prompts.globalSystem = ''
      if (s.prompts.globalPrefill === undefined) s.prompts.globalPrefill = ''
      if (s.prompts.globalPrefillEnabled === undefined) s.prompts.globalPrefillEnabled = true
    }

    pendingPageBackgroundUploads.clear()
    markSavedPageBackground((s as Settings).pageBackgroundImage ?? null)
    globalDraft.value = s
    await loadWebGpuPresetSource((s as Settings).webgpuBackgroundActivePresetId ?? null)
    chatDraft.value = ensureOverrides(props.chat ? clone(props.chat.overrides) : undefined)
    if (s.ttsEnabled) startTtsCachePoll()
    else stopTtsCachePoll()

    if (fontList.value.length === 0) {
      try {
        fontList.value = await apiGet<string[]>('/api/fonts')
      } catch {
        fontList.value = []
      }
    }
    await loadWorldBooks()
    if (props.chat && chatDraft.value) {
      mergeGlobalWorldBooksIntoDraft()
    }

    if (s.apiPresets.length > 0 && !editingPresetId.value) {
        editingPresetId.value = s.apiPresets[0]?.id ?? null
    }

    memoryTokenEstimate.value = null
    chatTokenEstimate.value = null
    messagesSinceLastMemoryUpdate.value = null
    tokensSinceLastMemoryUpdate.value = null
    if (tab.value === 'chat') {
      fetchMemoryTokenCount()
      if (props.chat?.id) fetchChatTokenCount()
    }
  },
)

watch(
  () => [props.show, tab.value, props.chat?.id] as const,
  async ([open, t, chatId]) => {
    if (!open || t !== 'chat' || !chatId) return
    await loadWorldBooks()
    if (chatDraft.value) mergeGlobalWorldBooksIntoDraft()
  },
)

const worldBookAddOptions = computed(() => {
  return worldbooks.value.map((b) => ({ label: b.name || b.id, value: b.id }))
})

/** 与当前会话相关的世界书：服务端已绑定（全局 / sessionChatIds）或已写入本会话顺序草稿（加入顺序） */
const currentChatWorldbooks = computed(() => {
  const chatId = props.chat?.id
  if (!chatId) return []
  const fromServer = worldbooks.value.filter((book) => {
    if (book.globalActive) return true
    return (book.sessionChatIds || []).includes(chatId)
  })
  const seen = new Set(fromServer.map((b) => b.id))
  const merged = [...fromServer]
  for (const att of chatDraft.value?.worldBookAttachments || []) {
    if (seen.has(att.worldBookId)) continue
    const b = worldbooks.value.find((x) => x.id === att.worldBookId)
    if (b) {
      seen.add(b.id)
      merged.push(b)
    }
  }
  return merged
})

/** 将未在排除列表中的全局世界书追加到会话顺序末尾（打开设置或切换会话时调用） */
function mergeGlobalWorldBooksIntoDraft() {
  if (!chatDraft.value) return
  ensureWorldBookAttachments()
  const excl = new Set(chatDraft.value.worldBookGlobalExclusions || [])
  const att = chatDraft.value.worldBookAttachments!
  const have = new Set(att.map((a) => a.worldBookId))
  for (const book of worldbooks.value) {
    if (!book.globalActive) continue
    if (excl.has(book.id)) continue
    if (have.has(book.id)) continue
    att.push({
      worldBookId: book.id,
      scanDepth: null,
      insertDepth: 5,
    })
    have.add(book.id)
  }
  syncWorldBookIdsFromAttachments()
}

function syncWorldBookIdsFromAttachments() {
  if (!chatDraft.value?.worldBookAttachments) return
  chatDraft.value.worldBookIds = chatDraft.value.worldBookAttachments.map((a) => a.worldBookId)
}

function ensureWorldBookAttachments() {
  if (!chatDraft.value) return
  if (!Array.isArray(chatDraft.value.worldBookAttachments)) chatDraft.value.worldBookAttachments = []
  const ids = chatDraft.value.worldBookIds || []
  if (chatDraft.value.worldBookAttachments.length === 0 && ids.length > 0) {
    chatDraft.value.worldBookAttachments = ids.map((id) => ({
      worldBookId: id,
      scanDepth: null,
      insertDepth: 5,
    }))
  }
  syncWorldBookIdsFromAttachments()
}

function addWorldBookToOrder() {
  if (!chatDraft.value || !addWorldBookId.value) return
  ensureWorldBookAttachments()
  const id = addWorldBookId.value
  chatDraft.value.worldBookGlobalExclusions = (chatDraft.value.worldBookGlobalExclusions || []).filter(
    (x) => x !== id,
  )
  const att = chatDraft.value.worldBookAttachments!
  if (!att.some((a) => a.worldBookId === id)) {
    att.push({
      worldBookId: id,
      scanDepth: null,
      insertDepth: 5,
    })
  }
  syncWorldBookIdsFromAttachments()
  addWorldBookId.value = ''
}

function removeWorldBookFromOrder(worldbookId: string) {
  if (!chatDraft.value) return
  ensureWorldBookAttachments()
  chatDraft.value.worldBookAttachments = (chatDraft.value.worldBookAttachments || []).filter(
    (a) => a.worldBookId !== worldbookId,
  )
  syncWorldBookIdsFromAttachments()
  const wb = worldbooks.value.find((b) => b.id === worldbookId)
  if (wb?.globalActive) {
    const ex = chatDraft.value.worldBookGlobalExclusions || []
    if (!ex.includes(worldbookId)) {
      chatDraft.value.worldBookGlobalExclusions = [...ex, worldbookId]
    }
  }
}

function moveWorldBookOrder(worldbookId: string, direction: -1 | 1) {
  if (!chatDraft.value) return
  ensureWorldBookAttachments()
  const att = [...(chatDraft.value.worldBookAttachments || [])]
  const idx = att.findIndex((a) => a.worldBookId === worldbookId)
  if (idx < 0) return
  const next = idx + direction
  if (next < 0 || next >= att.length) return
  const current = att[idx]
  const target = att[next]
  if (current == null || target == null) return
  att[idx] = target
  att[next] = current
  chatDraft.value.worldBookAttachments = att
  syncWorldBookIdsFromAttachments()
}

const worldBookOrderDraggingIdx = ref<number | null>(null)

function handleWorldBookOrderDragStart(idx: number) {
  worldBookOrderDraggingIdx.value = idx
}

function handleWorldBookOrderDragOver(e: DragEvent, idx: number) {
  e.preventDefault()
  if (!chatDraft.value) return
  ensureWorldBookAttachments()
  const from = worldBookOrderDraggingIdx.value
  if (from === null || from === idx) return
  const att = [...(chatDraft.value.worldBookAttachments || [])]
  const item = att.splice(from, 1)[0]
  if (item) {
    att.splice(idx, 0, item)
    chatDraft.value.worldBookAttachments = att
    worldBookOrderDraggingIdx.value = idx
    syncWorldBookIdsFromAttachments()
  }
}

function handleWorldBookOrderDragEnd() {
  worldBookOrderDraggingIdx.value = null
}

const apiPresetOrderDraggingIdx = ref<number | null>(null)

function handleApiPresetOrderDragStart(idx: number) {
  if (!globalDraft.value) return
  apiPresetOrderDraggingIdx.value = idx
}

function handleApiPresetOrderDragOver(e: DragEvent, idx: number) {
  e.preventDefault()
  if (!globalDraft.value) return
  const from = apiPresetOrderDraggingIdx.value
  if (from === null || from === idx) return
  const arr = [...globalDraft.value.apiPresets]
  const item = arr.splice(from, 1)[0]
  if (item) {
    arr.splice(idx, 0, item)
    globalDraft.value.apiPresets = arr
    apiPresetOrderDraggingIdx.value = idx
  }
}

function handleApiPresetOrderDragEnd() {
  apiPresetOrderDraggingIdx.value = null
}

const drawerScrollRef = ref<HTMLElement | null>(null)
const presetListHeaderRef = ref<HTMLElement | null>(null)
const presetListMaxHeightPx = ref<number | null>(null)

const PRESET_LIST_SCROLL_GAP_PX = 4
const PRESET_LIST_MIN_HEIGHT_PX = 120

let presetListHeightRaf = 0
function schedulePresetListMaxHeight() {
  if (presetListHeightRaf) cancelAnimationFrame(presetListHeightRaf)
  presetListHeightRaf = requestAnimationFrame(() => {
    presetListHeightRaf = 0
    updatePresetListMaxHeight()
  })
}

function updatePresetListMaxHeight() {
  if (!props.show || tab.value !== 'presets' || !preloaded.value) {
    presetListMaxHeightPx.value = null
    return
  }
  const scroll = drawerScrollRef.value
  const header = presetListHeaderRef.value
  if (!scroll || !header) {
    presetListMaxHeightPx.value = null
    return
  }
  const scrollRect = scroll.getBoundingClientRect()
  const headerRect = header.getBoundingClientRect()
  if (scrollRect.height <= 0 || headerRect.height <= 0) {
    presetListMaxHeightPx.value = null
    return
  }
  const h = scrollRect.bottom - headerRect.bottom - PRESET_LIST_SCROLL_GAP_PX
  presetListMaxHeightPx.value = Math.max(PRESET_LIST_MIN_HEIGHT_PX, Math.floor(h))
}

let presetListResizeObserver: ResizeObserver | null = null

function teardownPresetListHeightObservers() {
  if (presetListResizeObserver) {
    presetListResizeObserver.disconnect()
    presetListResizeObserver = null
  }
  const el = drawerScrollRef.value
  if (el) {
    el.removeEventListener('scroll', schedulePresetListMaxHeight)
  }
  window.removeEventListener('resize', schedulePresetListMaxHeight)
}

function setupPresetListHeightObservers() {
  teardownPresetListHeightObservers()
  if (!props.show || tab.value !== 'presets' || !preloaded.value) return
  const el = drawerScrollRef.value
  if (!el) return
  presetListResizeObserver = new ResizeObserver(() => schedulePresetListMaxHeight())
  presetListResizeObserver.observe(el)
  el.addEventListener('scroll', schedulePresetListMaxHeight, { passive: true })
  window.addEventListener('resize', schedulePresetListMaxHeight)
  nextTick(() => schedulePresetListMaxHeight())
}

watch([() => props.show, tab, preloaded], () => {
  if (!props.show || tab.value !== 'presets' || !preloaded.value) {
    teardownPresetListHeightObservers()
    presetListMaxHeightPx.value = null
    return
  }
  nextTick(() => setupPresetListHeightObservers())
}, { flush: 'post' })

onUnmounted(() => {
  teardownPresetListHeightObservers()
})

function worldBookName(worldbookId: string): string {
  return worldbooks.value.find((b) => b.id === worldbookId)?.name || worldbookId
}

function scanDepthDisplay(scanDepth: number | null | undefined): string {
  if (scanDepth != null && scanDepth >= 1) return String(scanDepth)
  const d = globalDraft.value?.worldBookEntryScanDepthDefault
  if (d != null && d >= 0) return `默认(${d})`
  return '默认'
}

function openSessionAttachEdit(idx: number) {
  if (!chatDraft.value) return
  ensureWorldBookAttachments()
  const a = chatDraft.value.worldBookAttachments![idx]
  if (!a) return
  sessionAttachIdx.value = idx
  sessionAttachModalShow.value = true
}

function onSessionAttachSave(payload: { scanDepth: number | null; insertDepth: number }) {
  if (!chatDraft.value || sessionAttachIdx.value == null) return
  ensureWorldBookAttachments()
  const i = sessionAttachIdx.value
  const list = chatDraft.value.worldBookAttachments!
  if (!list[i]) return
  list[i] = {
    ...list[i]!,
    scanDepth: payload.scanDepth,
    insertDepth: payload.insertDepth,
  }
  sessionAttachModalShow.value = false
  sessionAttachIdx.value = null
}

const sessionAttachModalBookName = computed(() => {
  if (sessionAttachIdx.value == null || !chatDraft.value?.worldBookAttachments) return ''
  const a = chatDraft.value.worldBookAttachments[sessionAttachIdx.value]
  return a ? worldBookName(a.worldBookId) : ''
})

const sessionAttachModalScan = computed(() => {
  if (sessionAttachIdx.value == null || !chatDraft.value?.worldBookAttachments) return null
  const a = chatDraft.value.worldBookAttachments[sessionAttachIdx.value]
  return a?.scanDepth ?? null
})

const sessionAttachModalInsert = computed(() => {
  if (sessionAttachIdx.value == null || !chatDraft.value?.worldBookAttachments) return 5
  const a = chatDraft.value.worldBookAttachments[sessionAttachIdx.value]
  return a?.insertDepth != null && a.insertDepth >= 1 ? a.insertDepth : 5
})

const worldBooksListVisible = computed(() => {
  const list = worldbooks.value
  if (!allWorldBooksSectionOpen.value) return []
  if (allWorldBooksListExpanded.value || list.length <= 5) return list
  return list.slice(0, 5)
})

function toggleAllWorldBooksSection() {
  allWorldBooksSectionOpen.value = !allWorldBooksSectionOpen.value
  if (!allWorldBooksSectionOpen.value) allWorldBooksListExpanded.value = false
}

async function setWorldBookGlobalActive(book: WorldBook, active: boolean) {
  const payload: WorldBook = {
    ...book,
    globalActive: active,
    sessionChatIds: active ? [] : [...(book.sessionChatIds || [])],
  }
  await apiPut<WorldBook>(`/api/worldbooks/${book.id}`, payload)
  await loadWorldBooks()
  if (!chatDraft.value) return
  if (active) {
    chatDraft.value.worldBookGlobalExclusions = (chatDraft.value.worldBookGlobalExclusions || []).filter(
      (id) => id !== book.id,
    )
    mergeGlobalWorldBooksIntoDraft()
  } else {
    chatDraft.value.worldBookGlobalExclusions = (chatDraft.value.worldBookGlobalExclusions || []).filter(
      (id) => id !== book.id,
    )
  }
}

async function detachWorldBookFromCurrentChat(book: WorldBook) {
  if (!props.chat?.id) return
  const chatId = props.chat.id
  const payload: WorldBook = {
    ...book,
    globalActive: false,
    sessionChatIds: (book.sessionChatIds || []).filter((id) => id !== chatId),
  }
  await apiPut<WorldBook>(`/api/worldbooks/${book.id}`, payload)
  await loadWorldBooks()
  removeWorldBookFromOrder(book.id)
}

/** 仅清除当前会话内对该世界书的激活/绑定，不物理删除世界书 */
async function clearWorldBookSessionActivation(book: WorldBook) {
  const chatId = props.chat?.id
  if (book.globalActive) {
    removeWorldBookFromOrder(book.id)
    return
  }
  if (chatId && (book.sessionChatIds || []).includes(chatId)) {
    await detachWorldBookFromCurrentChat(book)
    return
  }
  removeWorldBookFromOrder(book.id)
}

async function clearWorldBookSessionActivationById(worldbookId: string) {
  const b = worldbooks.value.find((x) => x.id === worldbookId)
  if (!b) {
    removeWorldBookFromOrder(worldbookId)
    return
  }
  await clearWorldBookSessionActivation(b)
}

watch(
  () => chatDraft.value?.longTermMemory,
  () => {
    if (suppressTokenEstimates.value) return
    if (memoryDebounceTimer) clearTimeout(memoryDebounceTimer)
    memoryDebounceTimer = setTimeout(() => {
      memoryDebounceTimer = null
      if (suppressTokenEstimates.value) return
      if (props.show && tab.value === 'chat') fetchMemoryTokenCount()
    }, 400)
  },
)

watch(
  () => [props.chat?.id, tab.value] as const,
  ([chatId, t]) => {
    if (suppressTokenEstimates.value) return
    if (props.show && t === 'chat') {
      fetchMemoryTokenCount()
      if (chatId) fetchChatTokenCount()
    }
  },
)

// 当当前会话的长期记忆被外部更新（如助手通过记忆工具写入）时，同步到草稿，使设置抽屉内「长期记忆」框无需关闭重开即可显示最新内容
watch(
  () => props.chat?.overrides?.longTermMemory,
  (newVal) => {
    if (tab.value === 'chat' && chatDraft.value != null && newVal !== undefined) {
      chatDraft.value.longTermMemory = newVal ?? null
    }
  },
)

/**
 * 计算当前编辑的预设
 *
 * 根据editingPresetId从全局草稿的API预设列表中查找预设。
 */
const editingPreset = computed(() => {
  if (!globalDraft.value) return null
  return globalDraft.value.apiPresets.find(p => p.id === editingPresetId.value) || null
})

const editingPresetTtsProvider = computed<TtsProvider>(() => resolveTtsProvider(editingPreset.value))

const editingPresetIsGlmLocal = computed(() => editingPresetTtsProvider.value === 'glm_local')

const editingPresetIsQwen3Local = computed(() => editingPresetTtsProvider.value === 'qwen3_local')

const editingPresetIsOmniVoiceLocal = computed(() => editingPresetTtsProvider.value === 'omnivoice_local')

const editingPresetSupportsVoiceDesign = computed(() => editingPresetTtsProvider.value === 'minimax')

const editingPresetSupportsPromptAudio = computed(() => editingPresetTtsProvider.value === 'minimax')

const editingPresetSupportsVoiceFetch = computed(() => !['glm_local', 'qwen3_local', 'omnivoice_local'].includes(editingPresetTtsProvider.value))

const editingPresetBaseUrlPlaceholder = computed(() => {
  if (!editingPreset.value) return 'https://api.openai.com 或 …/v1/chat/completions'
  if (!isTtsPreset(editingPreset.value)) return 'https://api.openai.com 或 …/v1/chat/completions'
  if (editingPresetTtsProvider.value === 'glm_local') return 'http://127.0.0.1:8088'
  if (editingPresetTtsProvider.value === 'qwen3_local') return 'http://127.0.0.1:8080'
  if (editingPresetTtsProvider.value === 'omnivoice_local') return 'http://127.0.0.1:8089'
  return editingPresetTtsProvider.value === 'glm'
    ? 'https://open.bigmodel.cn/api 或 …/api/paas/v4/audio/speech'
    : 'https://api.minimaxi.com 或 MiniMax TTS 完整接口地址'
})

const editingPresetBaseUrlHint = computed(() => {
  if (!editingPreset.value) return '支持 Base（如 …/v1 或 …/v1/）或完整 chat/completions 地址；末尾有无 / 均可。'
  if (!isTtsPreset(editingPreset.value)) {
    return '支持 Base（如 …/v1 或 …/v1/）或完整 chat/completions 地址；末尾有无 / 均可。'
  }
  if (editingPresetTtsProvider.value === 'glm_local') {
    return '本地 GLM-TTS API 地址，通常为 http://127.0.0.1:<端口>；启用托管时会根据端口自动生成。'
  }
  if (editingPresetTtsProvider.value === 'qwen3_local') {
    return '本地 Qwen3-TTS FastAPI 网关地址，通常为 http://127.0.0.1:<端口>；启用托管时会根据端口自动生成。'
  }
  if (editingPresetTtsProvider.value === 'omnivoice_local') {
    return '本地 OmniVoice FastAPI 地址，通常为 http://127.0.0.1:<端口>；启用托管时会根据端口自动生成。'
  }
  return editingPresetTtsProvider.value === 'glm'
    ? 'GLM TTS 推荐填写 https://open.bigmodel.cn/api，也兼容完整 /api/paas/v4/... 接口地址。'
    : 'MiniMax 兼容基础域名、/v1、或完整 TTS 接口地址。'
})

watch(editingPresetId, () => {
  presetModelListSelection.value = new Set()
  presetVoiceListSelection.value = new Set()
  ttsClonePreviewUrl.value = null
  ttsDesignPreviewUrl.value = null
})

watch(
  () => editingPreset.value?.models,
  (models) => {
    if (!models?.length) {
      presetModelListSelection.value = new Set()
      return
    }
    const allowed = new Set(models)
    const next = new Set<string>()
    for (const name of presetModelListSelection.value) {
      if (allowed.has(name)) next.add(name)
    }
    if (next.size !== presetModelListSelection.value.size) {
      presetModelListSelection.value = next
    }
  },
  { deep: true },
)

watch(
  () => editingPreset.value?.voiceCatalog,
  (voices) => {
    if (!voices?.length) {
      presetVoiceListSelection.value = new Set()
      return
    }
    const allowed = new Set(voices.map((voice) => voice.voiceId))
    const next = new Set<string>()
    for (const voiceId of presetVoiceListSelection.value) {
      if (allowed.has(voiceId)) next.add(voiceId)
    }
    if (next.size !== presetVoiceListSelection.value.size) {
      presetVoiceListSelection.value = next
    }
  },
  { deep: true },
)

const memoryTokenDisplay = computed(() => {
  if (memoryTokenLoading.value) return '…'
  if (memoryTokenEstimate.value === null) return '—'
  return String(memoryTokenEstimate.value)
})

const chatTokenDisplay = computed(() => {
  if (chatTokenLoading.value) return '…'
  if (chatTokenEstimate.value === null) return '—'
  return String(chatTokenEstimate.value)
})

/**
 * 创建新预设
 *
 * 创建一个新的API预设，使用默认值，并设置为当前编辑的预设。
 */
function createPreset() {
  if (!globalDraft.value) return
  const newPreset: ApiPreset = {
    id: crypto.randomUUID().replace(/-/g, ''),
    name: '新 API 预设',
    baseUrl: 'https://api.openai.com',
    apiKey: '',
    models: [],
    presetKind: null,
    ttsProvider: null,
    voiceCatalog: [],
  }
  globalDraft.value.apiPresets.push(newPreset)
  editingPresetId.value = newPreset.id
}

const ttsSessionModelOptions = computed(() => {
  return (globalDraft.value?.apiPresets || [])
    .filter((preset) => isTtsPreset(preset) && (preset.models?.length || 0) > 0)
    .map((preset) => ({
      label: preset.name,
      options: (preset.models || []).map((modelName) => ({
        label: modelName,
        value: modelName,
        presetId: preset.id,
      })),
    }))
})

const ttsPreprocessModelOptions = computed(() => {
  return (globalDraft.value?.apiPresets || [])
    .filter((preset) => !isTtsPreset(preset) && (preset.models?.length || 0) > 0)
    .map((preset) => ({
      label: preset.name,
      options: (preset.models || []).map((modelName) => ({
        label: modelName,
        value: modelName,
        presetId: preset.id,
      })),
    }))
})

const selectedChatTtsPreset = computed(() => {
  const presetId = chatDraft.value?.tts?.presetId
  if (!presetId) return null
  return globalDraft.value?.apiPresets.find((preset) => preset.id === presetId) || null
})

const selectedChatTtsProvider = computed<TtsProvider>(() => resolveTtsProvider(selectedChatTtsPreset.value))

watch(selectedChatTtsProvider, (provider) => {
  if (provider === 'minimax') return
  const tts = chatDraft.value?.tts
  if (tts?.injectEmotionTags) {
    tts.injectEmotionTags = false
  }
})

const availableTtsVoices = computed(() => {
  const selectedPreset = selectedChatTtsPreset.value
  if (selectedPreset?.voiceCatalog?.length) return selectedPreset.voiceCatalog
  const merged = (globalDraft.value?.apiPresets || [])
    .filter((preset) => isTtsPreset(preset))
    .flatMap((preset) => preset.voiceCatalog || [])
  return normalizeVoiceCatalog(merged)
})

const currentChatCharacterVoiceRows = computed(() => {
  const chat = props.chat
  if (!chat) return [] as Array<{ id: string; name: string }>
  const ids = chat.isGroup ? chat.memberIds : [chat.characterId]
  return [...new Set(ids.filter(Boolean))].map((id) => ({
    id,
    name: charactersStore.list.find((character) => character.id === id)?.name || id,
  }))
})

const currentChatPersonaVoiceRows = computed(() => {
  const chat = props.chat
  if (!chat?.userPersonaId) return [] as Array<{ id: string; name: string }>
  const personaId = chat.userPersonaId
  const personas = globalDraft.value?.userPersonas || []
  const name = personas.find((p) => p.id === personaId)?.name || personaId
  return [{ id: personaId, name }]
})

const editingPresetVoiceCatalog = computed(() => normalizeVoiceCatalog(editingPreset.value?.voiceCatalog))

function upsertEditingPresetVoiceCatalog(voices: ApiPresetVoice[]) {
  const preset = editingPreset.value
  if (!preset) return
  const merged = normalizeVoiceCatalog([...(preset.voiceCatalog || []), ...voices])
  preset.voiceCatalog = merged
}

function togglePresetVoiceSelection(voiceId: string) {
  const next = new Set(presetVoiceListSelection.value)
  if (next.has(voiceId)) next.delete(voiceId)
  else next.add(voiceId)
  presetVoiceListSelection.value = next
}

function selectAllPresetVoices() {
  presetVoiceListSelection.value = new Set(editingPresetVoiceCatalog.value.map((voice) => voice.voiceId))
}

function clearPresetVoiceSelection() {
  presetVoiceListSelection.value = new Set()
}

function removeSelectedPresetVoices() {
  const preset = editingPreset.value
  if (!preset?.voiceCatalog?.length || !presetVoiceListSelection.value.size) return
  preset.voiceCatalog = preset.voiceCatalog.filter((voice) => !presetVoiceListSelection.value.has(voice.voiceId))
  presetVoiceListSelection.value = new Set()
}

async function clearAllPresetVoices() {
  const preset = editingPreset.value
  if (!preset?.voiceCatalog?.length) return
  const ok = await notifyConfirm({
    title: '清空音色列表',
    message: '确定删除该预设中的全部音色条目？',
    variant: 'danger',
  })
  if (!ok) return
  preset.voiceCatalog = []
  presetVoiceListSelection.value = new Set()
}

/**
 * 打开音色选择器：拉取 MiniMax 音色列表，在弹窗中筛选并勾选后写入预设（与模型列表「从 API 获取并筛选」一致）。
 * 预设中已有但本次 API 未返回的音色会并入候选列表，避免仅打开弹窗就丢失本地条目。
 */
async function openVoiceSelector(preset: ApiPreset) {
  if (!isTtsPreset(preset) || presetVoicesLoading.value) return
  presetVoicesLoading.value = true
  try {
    const res = await apiPost<{ voices: ApiPresetVoice[] }>('/api/tts/test-voices', {
      baseUrl: preset.baseUrl,
      apiKey: preset.apiKey,
      provider: resolveTtsProvider(preset),
      voice_type: 'all',
    })
    const apiNorm = normalizeVoiceCatalog(res.voices)
    const apiIds = new Set(apiNorm.map((v) => v.voiceId))
    const extraFromPreset = normalizeVoiceCatalog(
      (preset.voiceCatalog || []).filter((v) => !apiIds.has(v.voiceId)),
    )
    candidateVoices.value = [...apiNorm, ...extraFromPreset]
    selectedCandidateVoiceIds.value = new Set((preset.voiceCatalog || []).map((v) => v.voiceId))
    voiceSelectorQuery.value = ''
    showVoiceSelector.value = true
  } catch (error) {
    await notifyMessage('获取音色失败: ' + String(error))
  } finally {
    presetVoicesLoading.value = false
  }
}

function toggleCandidateVoice(voiceId: string) {
  const next = new Set(selectedCandidateVoiceIds.value)
  if (next.has(voiceId)) next.delete(voiceId)
  else next.add(voiceId)
  selectedCandidateVoiceIds.value = next
}

function saveVoiceSelection() {
  const preset = editingPreset.value
  if (!preset) {
    showVoiceSelector.value = false
    return
  }
  preset.voiceCatalog = normalizeVoiceCatalog(
    candidateVoices.value.filter((v) => selectedCandidateVoiceIds.value.has(v.voiceId)),
  )
  showVoiceSelector.value = false
}

const filteredVoiceCandidates = computed(() => {
  const list = candidateVoices.value
  const q = voiceSelectorQuery.value.trim().toLowerCase()
  if (!q) return list
  return list.filter((v) => {
    return (
      v.voiceId.toLowerCase().includes(q) ||
      v.name.toLowerCase().includes(q) ||
      v.voiceType.toLowerCase().includes(q)
    )
  })
})

function pickTtsCloneSourceFile() {
  ttsCloneSourceInputRef.value?.click()
}

function pickTtsClonePromptFile() {
  ttsClonePromptInputRef.value?.click()
}

function onTtsCloneSourceChange(event: Event) {
  const input = event.target as HTMLInputElement | null
  ttsCloneSourceFile.value = input?.files?.[0] ?? null
}

function onTtsClonePromptChange(event: Event) {
  const input = event.target as HTMLInputElement | null
  ttsClonePromptFile.value = input?.files?.[0] ?? null
}

async function submitTtsClone() {
  const preset = editingPreset.value
  if (!preset || !isTtsPreset(preset)) return
  const provider = resolveTtsProvider(preset)
  if (!ttsCloneSourceFile.value) {
    await notifyMessage('请先选择待复刻音频文件')
    return
  }
  if (!ttsCloneDraft.voiceId.trim()) {
    await notifyMessage('请填写克隆后的 voice_id')
    return
  }

  const body = new FormData()
  body.append('baseUrl', preset.baseUrl)
  body.append('apiKey', preset.apiKey)
  body.append('provider', provider)
  body.append('voice_id', ttsCloneDraft.voiceId.trim())
  body.append('source_file', ttsCloneSourceFile.value)
  if (ttsCloneDraft.model.trim()) body.append('model', ttsCloneDraft.model.trim())
  if (ttsCloneDraft.previewText.trim()) body.append('text', ttsCloneDraft.previewText.trim())
  if (provider === 'minimax' && ttsClonePromptFile.value) body.append('prompt_file', ttsClonePromptFile.value)
  if (ttsCloneDraft.promptText.trim()) body.append('prompt_text', ttsCloneDraft.promptText.trim())
  if (provider === 'minimax') {
    body.append('need_noise_reduction', String(ttsCloneDraft.needNoiseReduction))
    body.append('need_volume_normalization', String(ttsCloneDraft.needVolumeNormalization))
  }

  ttsCloneLoading.value = true
  try {
    const res = await apiPostFormData<{ voiceId: string; previewUrl?: string | null; voiceType: string }>('/api/tts/clone', body)
    upsertEditingPresetVoiceCatalog([{ voiceId: res.voiceId, name: res.voiceId, voiceType: res.voiceType }])
    ttsClonePreviewUrl.value = res.previewUrl ?? null
  } catch (error) {
    await notifyMessage('音色复刻失败: ' + String(error))
  } finally {
    ttsCloneLoading.value = false
  }
}

async function submitTtsDesign() {
  const preset = editingPreset.value
  if (!preset || !isTtsPreset(preset)) return
  if (resolveTtsProvider(preset) !== 'minimax') {
    await notifyMessage('GLM TTS 暂不支持音色设计')
    return
  }
  if (!ttsDesignDraft.prompt.trim() || !ttsDesignDraft.previewText.trim()) {
    await notifyMessage('请填写音色描述和试听文本')
    return
  }
  ttsDesignLoading.value = true
  try {
    const res = await apiPost<{ voiceId: string; previewUrl?: string | null; voiceType: string }>('/api/tts/design', {
      baseUrl: preset.baseUrl,
      apiKey: preset.apiKey,
      provider: resolveTtsProvider(preset),
      prompt: ttsDesignDraft.prompt.trim(),
      preview_text: ttsDesignDraft.previewText.trim(),
      voice_id: ttsDesignDraft.voiceId.trim() || null,
    })
    upsertEditingPresetVoiceCatalog([{ voiceId: res.voiceId, name: res.voiceId, voiceType: res.voiceType }])
    ttsDesignPreviewUrl.value = res.previewUrl ?? null
    if (!ttsDesignDraft.voiceId.trim()) ttsDesignDraft.voiceId = res.voiceId
  } catch (error) {
    await notifyMessage('音色设计失败: ' + String(error))
  } finally {
    ttsDesignLoading.value = false
  }
}

interface ComparableTtsConfig {
  autoReadScope: AutoReadScope
  readGapSeconds: number
  model: string | null
  voiceByCharacterId: Record<string, string>
  voiceByPersonaId: Record<string, string>
  presetId: string | null
  preprocessEnabled: boolean
  preprocessModel: string | null
  preprocessPresetId: string | null
  preprocessTargetLanguage: string | null
  injectEmotionTags: boolean
}

function normalizeComparableTtsConfig(source?: TtsSessionConfig | null): ComparableTtsConfig | null {
  const normalized = ensureTtsSessionConfig(source)
  const comparable: ComparableTtsConfig = {
    autoReadScope: normalized.autoReadScope ?? 'off',
    readGapSeconds: Math.max(0, Number(normalized.readGapSeconds ?? 0)),
    model: normalized.model?.trim() || null,
    voiceByCharacterId: normalizeVoiceMap(normalized.voiceByCharacterId),
    voiceByPersonaId: normalizeVoiceMap(normalized.voiceByPersonaId),
    presetId: normalized.presetId?.trim() || null,
    preprocessEnabled: normalized.preprocessEnabled === true,
    preprocessModel: normalized.preprocessModel?.trim() || null,
    preprocessPresetId: normalized.preprocessPresetId?.trim() || null,
    preprocessTargetLanguage: normalized.preprocessTargetLanguage?.trim() || null,
    injectEmotionTags: normalized.injectEmotionTags === true,
  }
  const hasValue = comparable.autoReadScope !== 'off'
    || comparable.readGapSeconds > 0
    || comparable.model !== null
    || comparable.presetId !== null
    || comparable.preprocessEnabled
    || comparable.preprocessModel !== null
    || comparable.preprocessPresetId !== null
    || comparable.preprocessTargetLanguage !== null
    || comparable.injectEmotionTags
    || Object.keys(comparable.voiceByCharacterId).length > 0
    || Object.keys(comparable.voiceByPersonaId).length > 0
  return hasValue ? comparable : null
}

/**
 * 删除预设
 *
 * 弹出确认对话框，确认后删除指定的API预设。
 * 如果删除的是当前编辑的预设，则选择第一个预设。
 * 同时从「最近使用」中移除仅存在于被删预设中的模型，避免聊天界面仍显示已删除的模型。
 *
 * @param {string} id - 预设ID
 */
async function deletePreset(id: string) {
  if (!globalDraft.value) return
  const ok = await notifyConfirm({ title: '删除预设', message: '确定删除此预设？', variant: 'danger' })
  if (!ok) return
  globalDraft.value.apiPresets = globalDraft.value.apiPresets.filter(p => p.id !== id)
  if (editingPresetId.value === id) {
    editingPresetId.value = globalDraft.value.apiPresets[0]?.id || null
  }
  // 从「最近使用」中移除已不在任何非 TTS 预设（或全局候选）中的模型
  const presets = globalDraft.value.apiPresets
  const available = presets.length > 0
    ? new Set(presets.filter((p) => !isTtsApiPreset(p)).flatMap((p) => p.models || []))
    : new Set(globalDraft.value.llm.modelCandidates || [])
  globalDraft.value.llm.usedModels = (globalDraft.value.llm.usedModels || []).filter(m => available.has(m))
}

function togglePresetModelListSelection(name: string) {
  const next = new Set(presetModelListSelection.value)
  if (next.has(name)) next.delete(name)
  else next.add(name)
  presetModelListSelection.value = next
}

function selectAllPresetModelNames() {
  const models = editingPreset.value?.models
  if (!models?.length) return
  presetModelListSelection.value = new Set(models)
}

function clearPresetModelListSelection() {
  presetModelListSelection.value = new Set()
}

function removeSelectedPresetModelNames() {
  const p = editingPreset.value
  if (!p?.models?.length) return
  const sel = presetModelListSelection.value
  if (!sel.size) return
  p.models = p.models.filter((m) => !sel.has(m))
  presetModelListSelection.value = new Set()
}

async function clearAllPresetModelNames() {
  const p = editingPreset.value
  if (!p?.models?.length) return
  const ok = await notifyConfirm({
    title: '清空模型列表',
    message: '确定删除该预设中的全部模型名？',
    variant: 'danger',
  })
  if (!ok) return
  p.models = []
  presetModelListSelection.value = new Set()
}

function removeSinglePresetModelAt(idx: number) {
  const p = editingPreset.value
  if (!p?.models) return
  const removed = p.models.splice(idx, 1)[0]
  if (removed !== undefined) {
    const next = new Set(presetModelListSelection.value)
    next.delete(removed)
    presetModelListSelection.value = next
  }
}

/**
 * 打开模型选择器
 *
 * 测试预设的API连接，获取可用模型列表，然后打开模型选择器弹窗。
 * 使用apiPost函数（来自api/http.ts）发送POST请求到/api/llm/test-models。
 *
 * @param {ApiPreset} preset - API预设（来自types/models.ts）
 * @returns {Promise<void>} 完成时返回
 */
async function openModelSelector(preset: ApiPreset) {
    if (presetModelsLoading.value) return
    presetModelsLoading.value = true
    try {
        const models = await apiPost<string[]>('/api/llm/test-models', {
            baseUrl: preset.baseUrl,
            apiKey: preset.apiKey
        })
        candidateModels.value = models
        selectedCandidateModels.value = new Set(preset.models)
        modelSelectorQuery.value = ''
        showModelSelector.value = true
    } catch (e) {
        await notifyMessage('获取模型失败: ' + String(e))
    } finally {
        presetModelsLoading.value = false
    }
}

/**
 * 切换候选模型选择
 *
 * 切换指定模型的选中状态（选中/取消选中）。
 *
 * @param {string} m - 模型名称
 */
function toggleCandidate(m: string) {
    if (selectedCandidateModels.value.has(m)) {
        selectedCandidateModels.value.delete(m)
    } else {
        selectedCandidateModels.value.add(m)
    }
}

/**
 * 保存模型选择
 *
 * 将选中的模型列表保存到当前编辑的预设中，然后关闭模型选择器。
 */
function saveModelSelection() {
    if (editingPreset.value) {
        editingPreset.value.models = Array.from(selectedCandidateModels.value)
    }
    showModelSelector.value = false
}

/**
 * 计算过滤后的候选模型
 *
 * 根据搜索查询过滤候选模型列表，不区分大小写。
 */
const filteredCandidates = computed(() => {
    if (!modelSelectorQuery.value) return candidateModels.value
    const q = modelSelectorQuery.value.toLowerCase()
    return candidateModels.value.filter(m => m.toLowerCase().includes(q))
})

/**
 * 字体选项：系统默认 + 已导入的字体列表
 */
const fontOptions = computed(() => {
  const list = fontList.value.map((f) => ({
    label: f.replace(/\.[^.]+$/, '') || f,
    value: f,
  }))
  return [{ label: '系统默认', value: '' }, ...list]
})

/** 字体选择器 v-model：空字符串表示系统默认，与选项 value 一致 */
const fontModel = computed({
  get: () => globalDraft.value?.selectedFont ?? '',
  set: (v: string) => {
    if (globalDraft.value) globalDraft.value.selectedFont = v || null
  },
})

/**
 * 应用字体：抽屉打开时始终使用草稿中的 selectedFont（不随 tab 切换而变），
 * 避免在切换到 API 预设/当前会话时误设为默认字体导致闪烁与性能问题；
 * 抽屉关闭时使用已保存的 store 设置。
 */
watch(
  () =>
    props.show
      ? (globalDraft.value?.selectedFont ?? null)
      : (settingsStore.settings?.selectedFont ?? null),
  (v) => applyFont(v ?? null),
  { immediate: true }
)

/** 消息字号（仅作用于聊天窗口消息气泡），无默认值 */
const messageFontSizeModel = computed({
  get: () => globalDraft.value?.messageFontSize ?? '',
  set: (v: number | '' | unknown) => {
    if (!globalDraft.value) return
    if (v === '' || v == null || Number.isNaN(Number(v))) globalDraft.value.messageFontSize = null
    else globalDraft.value.messageFontSize = Math.max(8, Math.min(72, Number(v)))
  },
})

function stepMessageFontSize(delta: number) {
  if (!globalDraft.value) return
  const current = globalDraft.value.messageFontSize ?? 15
  const next = Math.max(8, Math.min(72, current + delta))
  globalDraft.value.messageFontSize = next
}

/**
 * 计算聊天模型选项
 *
 * 根据全局草稿中的API预设生成聊天模型选项列表，按预设分组。
 */
const chatModelOptions = computed(() => {
  const options: any[] = []
  if (!globalDraft.value) return []

  for (const preset of globalDraft.value.apiPresets) {
      if (isTtsApiPreset(preset)) continue
      if (preset.models && preset.models.length > 0) {
          options.push({
              label: preset.name,
              options: preset.models.map(m => ({ label: m, value: m, presetId: preset.id }))
          })
      }
  }
  
  return options
})

/**
 * 处理聊天模型选择
 *
 * 更新聊天覆盖设置中的模型和预设ID。
 *
 * @param {any} option - 模型选项，包含value和可选的presetId
 */
function handleChatModelSelect(option: any) {
  if (chatDraft.value) {
     chatDraft.value.params.model = option.value
     if (option.presetId) {
         chatDraft.value.presetId = option.presetId
     }
  }
}

/**
 * 保存全局设置
 *
 * 将全局设置草稿保存到服务器，然后关闭抽屉。
 * 使用settingsStore.save（来自stores/settings.ts）保存设置。
 *
 * @returns {Promise<void>} 完成时返回
 */
async function saveGlobal() {
  if (!globalDraft.value) return
  const previousSavedPageBackground = savedPageBackgroundImage.value
  const draft = {
    ...globalDraft.value,
    generationDefaults: { ...globalDraft.value.generationDefaults },
    draftHelpDefaults: { ...ensureDraftHelpDefaults(globalDraft.value.draftHelpDefaults) },
    apiPresets: globalDraft.value.apiPresets.map((preset) => normalizePresetDraft(preset)),
  }
  draft.generationDefaults.context_size = normalizeContextSize(draft.generationDefaults.context_size)
  draft.draftHelpDefaults.context_message_limit = normalizePositiveInteger(draft.draftHelpDefaults.context_message_limit)
  draft.pageBackgroundImage = draft.pageBackgroundImage ?? null
  draft.pageBackgroundOpacity = draft.pageBackgroundOpacity == null
    ? null
    : Math.max(0, Math.min(1, draft.pageBackgroundOpacity))
  draft.pageBackgroundBlurPx = draft.pageBackgroundBlurPx == null
    ? null
    : Math.max(0, Math.min(64, draft.pageBackgroundBlurPx))
  ensureWebgpuSettingsShape(draft)
  draft.webgpuBackgroundEnabled = draft.webgpuBackgroundEnabled === true
  draft.webgpuBackgroundActivePresetId = draft.webgpuBackgroundActivePresetId ?? null
  await settingsStore.save(draft)
  globalDraft.value.generationDefaults.context_size = draft.generationDefaults.context_size
  globalDraft.value.draftHelpDefaults = draft.draftHelpDefaults
  globalDraft.value.pageBackgroundImage = settingsStore.settings?.pageBackgroundImage ?? draft.pageBackgroundImage
  globalDraft.value.pageBackgroundOpacity = draft.pageBackgroundOpacity
  globalDraft.value.pageBackgroundBlurPx = draft.pageBackgroundBlurPx
  globalDraft.value.webgpuBackgroundEnabled = settingsStore.settings?.webgpuBackgroundEnabled ?? draft.webgpuBackgroundEnabled
  globalDraft.value.webgpuBackgroundPresets = settingsStore.settings?.webgpuBackgroundPresets || draft.webgpuBackgroundPresets
  globalDraft.value.webgpuBackgroundActivePresetId =
    settingsStore.settings?.webgpuBackgroundActivePresetId ?? draft.webgpuBackgroundActivePresetId
  markSavedPageBackground(globalDraft.value.pageBackgroundImage ?? null)
  await deletePendingPageBackgrounds(globalDraft.value.pageBackgroundImage ?? null)
  clearWebGpuRuntime()
  if (previousSavedPageBackground && previousSavedPageBackground !== globalDraft.value.pageBackgroundImage) {
    await deletePageBackgroundFile(previousSavedPageBackground)
  }
}

/**
 * 保存聊天覆盖设置
 *
 * 将聊天覆盖设置草稿保存到服务器，然后关闭抽屉。
 * 使用chatsStore.updateOverrides（来自stores/chats.ts）更新设置。
 *
 * @returns {Promise<void>} 完成时返回
 */
/** Context Size：0、NaN、undefined 视为“未启用”即 null */
function normalizeContextSize(v: number | null | undefined): number | null {
  if (v == null || Number.isNaN(v) || v < 1) return null
  return v
}

function normalizePositiveInteger(v: number | null | undefined): number | null {
  if (v == null || Number.isNaN(v) || v < 1) return null
  return Math.floor(v)
}

interface ComparableChatOverrides {
  prompt: string | null
  sessionSystemPromptMode: 'append' | 'override'
  longTermMemory: string | null
  contextStartMessageId: string | null
  presetId: string | null
  pureAiMode: boolean | null
  worldBookAttachments: Array<{
    worldBookId: string
    scanDepth: number | null
    insertDepth: number
  }>
  worldBookGlobalExclusions: string[]
  params: {
    model: string | null
    temperature: number | null
    top_p: number | null
    max_tokens: number | null
    context_size: number | null
  }
  draftHelp: {
    context_message_limit: number | null
  }
  tts: ComparableTtsConfig | null
  autoMemorySummaryEveryN: number | null
  lastAutoMemorySummaryAfterMessageId: string | null
  autoMemorySummarySilent: boolean
  autoMemorySummaryNextAskTier: number
}

function normalizeWorldBookGlobalExclusions(ids: string[] | undefined): string[] {
  return [...new Set((ids || []).filter((id) => Boolean(id)))]
}

function normalizeComparableChatOverrides(source?: Partial<ChatOverrides> | null): ComparableChatOverrides {
  const overrides = ensureOverrides(source)
  const draftHelp = ensureDraftHelpDefaults(overrides.draftHelp)
  return {
    prompt: overrides.prompt ?? null,
    sessionSystemPromptMode: overrides.sessionSystemPromptMode === 'override' ? 'override' : 'append',
    longTermMemory: overrides.longTermMemory ?? null,
    contextStartMessageId: overrides.contextStartMessageId ?? null,
    presetId: overrides.presetId ?? null,
    pureAiMode: overrides.pureAiMode ?? null,
    worldBookAttachments: (overrides.worldBookAttachments || []).map((attachment) => ({
      worldBookId: attachment.worldBookId,
      scanDepth: attachment.scanDepth ?? null,
      insertDepth: attachment.insertDepth && attachment.insertDepth >= 1 ? attachment.insertDepth : 5,
    })),
    worldBookGlobalExclusions: normalizeWorldBookGlobalExclusions(overrides.worldBookGlobalExclusions),
    params: {
      model: overrides.params.model ?? null,
      temperature: overrides.params.temperature ?? null,
      top_p: overrides.params.top_p ?? null,
      max_tokens: overrides.params.max_tokens ?? null,
      context_size: normalizeContextSize(overrides.params.context_size),
    },
    draftHelp: {
      context_message_limit: normalizePositiveInteger(draftHelp.context_message_limit),
    },
    tts: normalizeComparableTtsConfig(overrides.tts),
    autoMemorySummaryEveryN:
      typeof overrides.autoMemorySummaryEveryN === 'number' &&
      Number.isFinite(overrides.autoMemorySummaryEveryN) &&
      overrides.autoMemorySummaryEveryN >= 1
        ? Math.floor(overrides.autoMemorySummaryEveryN)
        : null,
    lastAutoMemorySummaryAfterMessageId: overrides.lastAutoMemorySummaryAfterMessageId ?? null,
    autoMemorySummarySilent: overrides.autoMemorySummarySilent === true,
    autoMemorySummaryNextAskTier:
      typeof overrides.autoMemorySummaryNextAskTier === 'number' &&
      Number.isFinite(overrides.autoMemorySummaryNextAskTier) &&
      overrides.autoMemorySummaryNextAskTier >= 1
        ? Math.floor(overrides.autoMemorySummaryNextAskTier)
        : 1,
  }
}

function comparableOverridesEqual(left: ComparableChatOverrides, right: ComparableChatOverrides): boolean {
  return JSON.stringify(left) === JSON.stringify(right)
}

function orderedWorldBookIdsFromComparable(source: ComparableChatOverrides): string[] {
  return source.worldBookAttachments.map((attachment) => attachment.worldBookId)
}

function sessionBoundWorldBookIdsFromComparable(source: ComparableChatOverrides): string[] {
  return source.worldBookAttachments
    .map((attachment) => attachment.worldBookId)
    .filter((worldBookId) => {
      const book = worldbooks.value.find((item) => item.id === worldBookId)
      return book ? !book.globalActive : true
    })
}

function stringArraysEqual(left: string[], right: string[]): boolean {
  return left.length === right.length && left.every((value, index) => value === right[index])
}

function applyNormalizedComparableToDraft(source: ComparableChatOverrides) {
  if (!chatDraft.value) return
  chatDraft.value.prompt = source.prompt
  chatDraft.value.sessionSystemPromptMode = source.sessionSystemPromptMode
  chatDraft.value.longTermMemory = source.longTermMemory
  chatDraft.value.contextStartMessageId = source.contextStartMessageId
  chatDraft.value.presetId = source.presetId
  chatDraft.value.pureAiMode = source.pureAiMode
  chatDraft.value.worldBookAttachments = source.worldBookAttachments.map((attachment) => ({ ...attachment }))
  syncWorldBookIdsFromAttachments()
  chatDraft.value.worldBookGlobalExclusions = [...source.worldBookGlobalExclusions]
  chatDraft.value.params = { ...source.params }
  chatDraft.value.draftHelp = { ...source.draftHelp }
  // 与 ensureOverrides 一致：Comparable 里「全默认」时 tts 为 null，但会话草稿必须始终持有 TtsSessionConfig，避免模板访问 chatDraft.tts.model 崩溃。
  chatDraft.value.tts = ensureTtsSessionConfig(source.tts)
  chatDraft.value.autoMemorySummaryEveryN = source.autoMemorySummaryEveryN
  chatDraft.value.lastAutoMemorySummaryAfterMessageId = source.lastAutoMemorySummaryAfterMessageId
  chatDraft.value.autoMemorySummarySilent = source.autoMemorySummarySilent
  chatDraft.value.autoMemorySummaryNextAskTier = source.autoMemorySummaryNextAskTier
}

async function ensureCharactersLoadedForSave() {
  if (charactersStore.list.length > 0) return
  try {
    await charactersStore.loadAll()
  } catch {
    // 保留极低频的后续单项兜底，避免列表加载失败阻塞保存。
  }
}

function updateDigitsOnlyField(rawValue: string, onValue: (value: number | null) => void, input: HTMLInputElement | null) {
  const digits = rawValue.replace(/\D/g, '')
  if (input && input.value !== digits) input.value = digits
  onValue(digits ? Number(digits) : null)
}

function handleGlobalDraftHelpLimitInput(e: Event) {
  const input = e.target as HTMLInputElement | null
  if (!globalDraft.value) return
  updateDigitsOnlyField(input?.value ?? '', (value) => {
    globalDraft.value!.draftHelpDefaults = ensureDraftHelpDefaults(globalDraft.value!.draftHelpDefaults)
    globalDraft.value!.draftHelpDefaults.context_message_limit = value
  }, input)
}

function setAutoMemorySummarySilent(v: boolean) {
  if (!chatDraft.value) return
  chatDraft.value.autoMemorySummarySilent = v
}

function onAutoMemorySummaryEveryNInput(e: Event) {
  const input = e.target as HTMLInputElement | null
  if (!chatDraft.value) return
  const raw = (input?.value ?? '').trim()
  if (raw === '') {
    chatDraft.value.autoMemorySummaryEveryN = null
    chatDraft.value.autoMemorySummaryNextAskTier = 1
    return
  }
  const n = Number.parseInt(raw, 10)
  if (!Number.isFinite(n) || n < 1) {
    chatDraft.value.autoMemorySummaryEveryN = null
    chatDraft.value.autoMemorySummaryNextAskTier = 1
    return
  }
  const prev = chatDraft.value.autoMemorySummaryEveryN
  chatDraft.value.autoMemorySummaryEveryN = n
  if (prev !== n) chatDraft.value.autoMemorySummaryNextAskTier = 1
}

function handleChatDraftHelpLimitInput(e: Event) {
  const input = e.target as HTMLInputElement | null
  if (!chatDraft.value) return
  updateDigitsOnlyField(input?.value ?? '', (value) => {
    chatDraft.value!.draftHelp = ensureDraftHelpDefaults(chatDraft.value!.draftHelp)
    chatDraft.value!.draftHelp.context_message_limit = value
  }, input)
}

/**
 * 将本会话 id 写入/移出非全局世界书的 sessionChatIds，与后端 collect_active_worldbooks 一致。
 */
async function syncWorldBookSessionChatIdsForChat(chatId: string, attachments: WorldBookAttachment[]) {
  await loadWorldBooks({ refreshTokenTotals: false })
  const boundIds = new Set((attachments || []).map((a) => a.worldBookId).filter(Boolean))
  for (const wb of worldbooks.value) {
    if (wb.globalActive) continue
    const ids = wb.sessionChatIds || []
    const hasChat = ids.includes(chatId)
    const shouldBind = boundIds.has(wb.id)
    if (shouldBind && !hasChat) {
      await apiPut<WorldBook>(`/api/worldbooks/${wb.id}`, {
        ...wb,
        sessionChatIds: [...ids, chatId],
      })
    } else if (!shouldBind && hasChat) {
      await apiPut<WorldBook>(`/api/worldbooks/${wb.id}`, {
        ...wb,
        sessionChatIds: ids.filter((id) => id !== chatId),
      })
    }
  }
  await loadWorldBooks({ refreshTokenTotals: false })
}

async function saveChatOverrides() {
  const chat = props.chat
  if (!chat || !chatDraft.value) return
  const draft = {
    ...chatDraft.value,
    params: { ...chatDraft.value.params },
    draftHelp: { ...ensureDraftHelpDefaults(chatDraft.value.draftHelp) },
    tts: ensureTtsSessionConfig(chatDraft.value.tts),
  }
  draft.params.context_size = normalizeContextSize(draft.params.context_size)
  draft.draftHelp.context_message_limit = normalizePositiveInteger(draft.draftHelp.context_message_limit)
  const normalizedDraft = normalizeComparableChatOverrides(draft)
  const normalizedCurrent = normalizeComparableChatOverrides(chat.overrides)
  const shouldSaveOverrides = !comparableOverridesEqual(normalizedDraft, normalizedCurrent)
  const shouldSyncWorldBookBindings = !stringArraysEqual(
    sessionBoundWorldBookIdsFromComparable(normalizedCurrent),
    sessionBoundWorldBookIdsFromComparable(normalizedDraft),
  )
  const shouldSyncCharacterWorldBookOrder = !stringArraysEqual(
    orderedWorldBookIdsFromComparable(normalizedCurrent),
    orderedWorldBookIdsFromComparable(normalizedDraft),
  )

  applyNormalizedComparableToDraft(normalizedDraft)

  if (!shouldSaveOverrides) {
    return
  }

  await chatsStore.updateOverrides(chat.id, chatDraft.value, { skipLoadList: true })

  if (shouldSyncWorldBookBindings) {
    try {
      await syncWorldBookSessionChatIdsForChat(chat.id, normalizedDraft.worldBookAttachments)
    } catch (e) {
      await notifyMessage('同步世界书会话绑定失败: ' + (e instanceof Error ? e.message : String(e)))
      await loadWorldBooks({ refreshTokenTotals: false })
      return
    }
  }

  // 单聊：将当前会话的世界书顺序同步到角色卡 attachedWorldBookIds，便于「含世界书」ZIP 导出一致
  if (!chat.isGroup && chat.characterId && shouldSyncCharacterWorldBookOrder) {
    const ordered: string[] = []
    const seen = new Set<string>()
    const wbOrder = normalizedDraft.worldBookAttachments.map((a) => a.worldBookId)
    for (const id of wbOrder) {
      if (id && !seen.has(id)) {
        seen.add(id)
        ordered.push(id)
      }
    }
    const characterId = chat.characterId
    await ensureCharactersLoadedForSave()
    let char = charactersStore.list.find((c) => c.id === characterId)
    if (!char) {
      try {
        char = await charactersStore.get(characterId)
      } catch {
        char = undefined
      }
    }
    if (char) {
      const prev = char.attachedWorldBookIds || []
      const same =
        prev.length === ordered.length && prev.every((x, i) => x === ordered[i])
      if (!same) {
        await charactersStore.update(characterId, {
          ...char,
          attachedWorldBookIds: ordered,
        })
      }
    }
  }
}

/**
 * 下载设置备份
 *
 * 下载设置备份文件（ZIP格式）。
 * 发送GET请求到/api/settings/backup?scope={scope}，下载返回的文件。
 *
 * @param {'basic' | 'with_characters' | 'with_chats'} scope - 备份范围（基础、包含角色、包含聊天）
 * @returns {Promise<void>} 完成时返回
 */
async function downloadSettingsBackup(scope: 'basic' | 'with_characters' | 'with_chats') {
  const r = await fetch(`/api/settings/backup?scope=${scope}`)
  if (!r.ok) {
    await notifyMessage(await r.text())
    return
  }
  const blob = await r.blob()
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = 'settings-backup.zip'
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
}

/**
 * 触发导入
 *
 * 程序化触发隐藏的文件输入框点击事件。
 */
function triggerImport() {
  importInputRef.value?.click()
}

/**
 * 触发导入字体
 */
function triggerFontImport() {
  fontInputRef.value?.click()
}

function triggerPageBackgroundImport() {
  pageBackgroundInputRef.value?.click()
}

/**
 * 处理导入字体：上传到 data/fonts，刷新列表并设为当前选中，实时应用。
 * 字体不随备份导出。
 */
async function handleFontImport(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  input.value = ''
  const fd = new FormData()
  fd.append('file', file)
  try {
    const r = await fetch('/api/fonts', { method: 'POST', body: fd })
    if (!r.ok) throw new Error(await r.text())
    const { filename } = (await r.json()) as { filename: string }
    fontList.value = await apiGet<string[]>('/api/fonts')
    if (globalDraft.value) {
      globalDraft.value.selectedFont = filename
      applyFont(filename)
    }
  } catch (err) {
    await notifyMessage('导入字体失败: ' + String(err))
  }
}

async function handlePageBackgroundImport(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  input.value = ''
  const previousDraftImage = globalDraft.value?.pageBackgroundImage ?? null
  const fd = new FormData()
  fd.append('file', file)
  try {
    const response = await fetch('/api/page-backgrounds', { method: 'POST', body: fd })
    if (!response.ok) throw new Error(await response.text())
    const { filename } = (await response.json()) as { filename: string }
    pendingPageBackgroundUploads.add(filename)
    if (globalDraft.value) globalDraft.value.pageBackgroundImage = filename
    if (previousDraftImage && previousDraftImage !== filename && pendingPageBackgroundUploads.has(previousDraftImage)) {
      pendingPageBackgroundUploads.delete(previousDraftImage)
      void deletePageBackgroundFile(previousDraftImage)
    }
  } catch (err) {
    await notifyMessage('导入页面背景失败: ' + String(err))
  }
}

async function clearPageBackground() {
  const filename = globalDraft.value?.pageBackgroundImage ?? null
  if (!globalDraft.value || !filename) return
  globalDraft.value.pageBackgroundImage = null
  if (pendingPageBackgroundUploads.has(filename)) {
    pendingPageBackgroundUploads.delete(filename)
    await deletePageBackgroundFile(filename)
  }
}

/**
 * 处理导入文件选择
 *
 * 当用户选择导入文件时，上传文件到服务器，然后重新加载所有数据。
 * 发送POST请求到/api/import，上传FormData格式的文件。
 * 导入成功后重新加载设置、角色列表和聊天列表。
 *
 * @param {Event} e - 文件选择事件
 * @returns {Promise<void>} 完成时返回
 */
async function handleImportChange(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  try {
    const result = await importSettingsFile(file)
    await refreshDataAfterImport()
    await notifyMessage(formatImportResultMessage(result))
  } catch (err) {
    await notifyMessage(err instanceof Error ? err.message : String(err))
  }
  input.value = ''
}

/**
 * 检查更新：请求后端对比云端 release，若有新版本则确认后保存设置、下载、触发更新脚本。
 */
async function checkUpdate() {
  if (checkUpdateLoading.value) return
  checkUpdateLoading.value = true
  checkUpdateMessage.value = '正在检查更新...'
  try {
    const res = await getManualUpdateCheck()
    if (!res.hasUpdate || !res.tagName) {
      checkUpdateMessage.value = '当前已是最新版本'
      return
    }
    const ok = await notifyConfirm({
      title: '检查更新',
      message: `发现新版本 ${res.latestVersion}，是否下载并安装？`,
      variant: 'default',
    })
    if (!ok) {
      checkUpdateMessage.value = ''
      return
    }
    checkUpdateMessage.value = '正在保存设置并下载...'
    if (globalDraft.value) {
      await saveGlobal()
    }
    await downloadUpdate(res.tagName)
    checkUpdateMessage.value = '正在启动更新...'
    await runUpdate()
    checkUpdateMessage.value = '更新已启动，请等待脚本执行完毕'
    setTimeout(() => close(), 1500)
  } catch (e) {
    checkUpdateMessage.value = ''
    await notifyMessage('检查更新失败: ' + String(e))
  } finally {
    checkUpdateLoading.value = false
  }
}
</script>

<template>
  <div>
  <div class="drawer-wrapper fixed inset-0 z-50 flex justify-end" :class="{ 'is-open': show }">
    <!-- Backdrop -->
    <div
      class="drawer-backdrop absolute inset-0 bg-overlay backdrop-blur-sm"
      style="backdrop-filter: blur(2px); background-clip: unset; -webkit-background-clip: unset; color: rgba(255, 255, 255, 0);"
      @click="close"
    ></div>

    <!-- Drawer Panel -->
    <div
      class="drawer-panel absolute right-4 top-4 bottom-4 w-[500px] max-w-[calc(90vw-32px)] theme-panel-bg backdrop-saturate-[1.8] border border-[var(--color-border)] rounded-2xl flex flex-col shadow-xl"
      style="backdrop-filter: blur(var(--blur-heavy)); -webkit-backdrop-filter: blur(var(--blur-heavy));"
    >
        <!-- Header -->
        <div class="flex items-center justify-between px-6 py-4 border-b border-[var(--color-border-subtle)] bg-[var(--color-border-subtle)] rounded-t-2xl">
          <h2 class="text-lg font-bold text-[var(--color-text)]">设置</h2>
          <button
            type="button"
            class="inline-flex min-h-11 min-w-11 shrink-0 items-center justify-center rounded-lg text-[var(--color-text-muted)] transition-colors hover:text-[var(--color-text)] touch-manipulation"
            @click="close"
          >
            <X class="w-5 h-5" />
          </button>
        </div>

        <!-- Tabs：整块可点；底层滑块平移承载高光，与 gap-1 / px-2 对齐 -->
        <div class="relative flex gap-1 border-b border-[var(--color-border-subtle)] bg-[var(--color-border-subtle)] px-2 py-2">
          <div
            class="pointer-events-none absolute left-2 top-2 bottom-2 rounded-lg bg-brand-a10 transition-transform duration-[400ms] ease-out"
            :style="{
              width: 'calc((100% - 1.5rem) / 3)',
              transform: `translateX(calc(${tab === 'global' ? 0 : tab === 'presets' ? 1 : 2} * (100% + 0.25rem)))`,
            }"
          />
          <button
            v-for="t in ['global', 'presets', 'chat']"
            :key="t"
            type="button"
            class="group relative z-10 flex min-h-11 min-w-0 flex-1 touch-manipulation items-center justify-center px-0.5 py-0.5 text-sm font-medium transition-colors duration-[400ms]"
            @click="tab = t as any"
          >
            <span
              class="block min-h-10 w-full rounded-lg py-2 text-center transition-colors duration-[400ms]"
              :class="
                tab === t
                  ? 'text-brand'
                  : 'text-[var(--color-text-muted)] group-hover:text-[var(--color-text)] group-hover:bg-surface-muted'
              "
            >
              {{ t === 'global' ? '全局设置' : t === 'presets' ? 'API 预设' : '当前会话' }}
            </span>
          </button>
        </div>

        <!-- Content -->
        <div
          ref="drawerScrollRef"
          class="drawer-scroll flex-1 min-h-0 overflow-y-auto p-6 custom-scrollbar bg-transparent"
        >
          <!-- Global Settings -->
          <div v-if="preloaded" v-show="tab === 'global'" class="space-y-6">
            <div v-if="!globalDraft" class="text-center text-[var(--color-text-muted)] py-8">加载中...</div>
            <div v-else class="space-y-4">
              <div class="text-xs text-[var(--color-text-muted)] bg-surface-muted p-3 rounded-lg border border-[var(--color-border-subtle)]">
                这里配置全局默认的 API 参数。如果配置了 "API 预设"，建议优先使用预设功能以便管理不同服务商。
              </div>

              <!-- 连接与默认模型（默认收起） -->
              <div class="rounded-xl border border-[var(--color-border-subtle)] bg-surface-muted/40 overflow-hidden">
                <button
                  type="button"
                  class="flex w-full cursor-pointer items-center justify-between gap-3 px-4 py-3.5 text-left text-sm font-semibold text-[var(--color-text-secondary)] select-none hover:bg-surface-hover/40"
                  :aria-expanded="globalAccordionOpen.connection"
                  @click="globalAccordionOpen.connection = !globalAccordionOpen.connection"
                >
                  <span>连接与默认模型</span>
                  <ChevronDown
                    class="h-4 w-4 shrink-0 text-[var(--color-text-muted)] transition-transform duration-[800ms] ease-in-out"
                    :class="globalAccordionOpen.connection ? 'rotate-180' : ''"
                  />
                </button>
                <div
                  class="grid transition-[grid-template-rows] duration-[800ms] ease-in-out"
                  :class="globalAccordionOpen.connection ? 'grid-rows-[1fr]' : 'grid-rows-[0fr]'"
                >
                  <div class="min-h-0 overflow-hidden">
                    <div class="space-y-5 border-t border-[var(--color-border-subtle)] px-4 pb-4 pt-4">
                  <!-- Stream Toggle -->
                  <div class="space-y-2">
                    <label class="block text-sm font-medium text-[var(--color-text-secondary)]">流式传输</label>
                    <button
                      type="button"
                      class="flex min-h-11 w-full cursor-pointer items-center gap-3 py-1 text-left group"
                      @click="globalDraft.streamEnabled = !globalDraft.streamEnabled"
                    >
                      <div
                        class="relative h-6 w-11 shrink-0 rounded-full transition-colors duration-200 ease-out"
                        :class="globalDraft.streamEnabled ? 'bg-brand' : 'bg-[var(--color-track)]'"
                      >
                        <div
                          class="absolute left-1 top-1 h-4 w-4 rounded-full bg-[var(--color-on-brand)]"
                          :style="{
                            transform: globalDraft.streamEnabled ? 'translateX(1.25rem)' : 'translateX(0)',
                            transition: 'transform 200ms ease-out',
                          }"
                        ></div>
                      </div>
                      <span class="text-xs text-[var(--color-text-secondary)]">
                        {{ globalDraft.streamEnabled ? '已开启' : '已关闭' }}
                      </span>
                    </button>
                  </div>

                  <!-- Pure AI Mode Toggle -->
                  <div class="space-y-2">
                    <label class="block text-sm font-medium text-[var(--color-text-secondary)]">纯 AI 模式</label>
                    <button
                      type="button"
                      class="flex min-h-11 w-full cursor-pointer items-center gap-3 py-1 text-left group"
                      @click="globalDraft.pureAiMode = !globalDraft.pureAiMode"
                    >
                      <div
                        class="relative h-6 w-11 shrink-0 rounded-full transition-colors duration-200 ease-out"
                        :class="globalDraft.pureAiMode ? 'bg-brand' : 'bg-[var(--color-track)]'"
                      >
                        <div
                          class="absolute left-1 top-1 h-4 w-4 rounded-full bg-[var(--color-on-brand)]"
                          :style="{
                            transform: globalDraft.pureAiMode ? 'translateX(1.25rem)' : 'translateX(0)',
                            transition: 'transform 200ms ease-out',
                          }"
                        ></div>
                      </div>
                      <span class="text-xs text-[var(--color-text-secondary)]">
                        {{ globalDraft.pureAiMode ? '已开启：不注入用户 Persona，用户发言将以「系统」角色影响世界' : '已关闭：正常对话模式' }}
                      </span>
                    </button>
                  </div>

                  <!-- Reasoning Effort -->
                  <div class="space-y-1.5">
                    <label class="block text-sm font-medium text-[var(--color-text-secondary)]">思考模式</label>
                    <ModernSelect
                      v-model="globalDraft.reasoningEffort"
                      :options="[...REASONING_EFFORT_OPTIONS]"
                      placeholder="选择思考深度..."
                      class="w-full"
                    />
                    <p class="text-xs text-[var(--color-text-muted)]">选「无」则关闭思考；其他档位会开启思考并请求更高推理深度。</p>
                  </div>

                  <!-- Base URL -->
                  <div class="space-y-1.5">
                    <label class="block text-sm font-medium text-[var(--color-text-secondary)]">默认 API 基础地址</label>
                    <input
                      v-model="globalDraft.llm.baseUrl"
                      type="text"
                      placeholder="https://api.openai.com 或 …/v1/chat/completions"
                      class="input w-full"
                    />
                    <p class="text-xs text-[var(--color-text-muted)]">支持 Base（如 https://api.openai.com 或 …/v1）或完整 chat/completions 地址；末尾有无 / 均可。</p>
                  </div>

                  <!-- API Key -->
                  <div class="space-y-1.5">
                    <label class="block text-sm font-medium text-[var(--color-text-secondary)]">默认 API Key</label>
                    <div class="relative">
                      <input
                        v-model="globalDraft.llm.apiKey"
                        :type="showApiKey ? 'text' : 'password'"
                        class="input w-full pr-11"
                      />
                      <button
                        type="button"
                        class="absolute right-1 top-1/2 flex min-h-10 min-w-10 -translate-y-1/2 items-center justify-center rounded-md text-[var(--color-text-muted)] hover:text-[var(--color-text-secondary)]"
                        @click="showApiKey = !showApiKey"
                      >
                        <component :is="showApiKey ? Eye : EyeOff" class="h-4 w-4" />
                      </button>
                    </div>
                  </div>

                  <div class="space-y-1.5">
                    <label class="block text-sm font-medium text-[var(--color-text-secondary)]">默认模型名称</label>
                    <input
                      v-model="globalDraft.llm.defaultModel"
                      type="text"
                      class="input w-full"
                      placeholder="例如: gpt-3.5-turbo"
                    />
                  </div>
                    </div>
                  </div>
                </div>
              </div>

              <!-- 提示词与生成参数（默认折叠） -->
              <div class="rounded-xl border border-[var(--color-border-subtle)] bg-surface-muted/40 overflow-hidden">
                <button
                  type="button"
                  class="flex w-full cursor-pointer items-center justify-between gap-3 px-4 py-3.5 text-left text-sm font-semibold text-[var(--color-text-secondary)] select-none hover:bg-surface-hover/40"
                  :aria-expanded="globalAccordionOpen.prompts"
                  @click="globalAccordionOpen.prompts = !globalAccordionOpen.prompts"
                >
                  <span>提示词与生成参数</span>
                  <ChevronDown
                    class="h-4 w-4 shrink-0 text-[var(--color-text-muted)] transition-transform duration-[800ms] ease-in-out"
                    :class="globalAccordionOpen.prompts ? 'rotate-180' : ''"
                  />
                </button>
                <div
                  class="grid transition-[grid-template-rows] duration-[800ms] ease-in-out"
                  :class="globalAccordionOpen.prompts ? 'grid-rows-[1fr]' : 'grid-rows-[0fr]'"
                >
                  <div class="min-h-0 overflow-hidden">
                    <div class="space-y-5 border-t border-[var(--color-border-subtle)] px-4 pb-4 pt-4">
                  <!-- Global System Prompt -->
                  <div class="space-y-1.5">
                    <label class="block text-sm font-medium text-[var(--color-text-secondary)]">全局系统提示词</label>
                    <textarea
                      v-model="globalDraft.prompts.globalSystem"
                      rows="4"
                      class="input textarea w-full resize-y"
                    ></textarea>
                  </div>

                  <div class="space-y-2">
                    <div class="flex items-center justify-between gap-3">
                      <label class="block text-sm font-medium text-[var(--color-text-secondary)]">预填内容</label>
                      <button
                        type="button"
                        class="flex min-h-11 cursor-pointer items-center gap-3 py-1 text-left group"
                        @click="globalDraft.prompts.globalPrefillEnabled = !globalDraft.prompts.globalPrefillEnabled"
                      >
                        <div
                          class="relative h-6 w-11 shrink-0 rounded-full transition-colors duration-200 ease-out"
                          :class="globalDraft.prompts.globalPrefillEnabled ? 'bg-brand' : 'bg-[var(--color-track)]'"
                        >
                          <div
                            class="absolute left-1 top-1 h-4 w-4 rounded-full bg-[var(--color-on-brand)]"
                            :style="{
                              transform: globalDraft.prompts.globalPrefillEnabled ? 'translateX(1.25rem)' : 'translateX(0)',
                              transition: 'transform 200ms ease-out',
                            }"
                          ></div>
                        </div>
                        <span class="text-xs text-[var(--color-text-secondary)]">
                          {{ globalDraft.prompts.globalPrefillEnabled ? '已开启：发送请求时附加预填' : '已关闭：保留文案但暂不生效' }}
                        </span>
                      </button>
                    </div>
                    <textarea
                      v-model="globalDraft.prompts.globalPrefill"
                      rows="2"
                      class="input textarea w-full resize-y"
                      placeholder="以助手身份附加在请求末尾，模型在其后续写；留空则不启用"
                    ></textarea>
                  </div>

                  <!-- Parameters (Ensured Visibility) -->
                  <div class="grid grid-cols-2 gap-4 pt-2">
                    <div class="space-y-1.5">
                      <label class="block text-sm font-medium text-[var(--color-text-secondary)]">Temperature</label>
                      <input
                        v-model.number="globalDraft.generationDefaults.temperature"
                        type="number"
                        step="0.1"
                        min="0"
                        max="2"
                        placeholder="默认"
                        class="input w-full"
                      />
                    </div>
                    <div class="space-y-1.5">
                      <label class="block text-sm font-medium text-[var(--color-text-secondary)]">Top P</label>
                      <input
                        v-model.number="globalDraft.generationDefaults.top_p"
                        type="number"
                        step="0.1"
                        min="0"
                        max="1"
                        placeholder="默认"
                        class="input w-full"
                      />
                    </div>
                    <div class="space-y-1.5">
                      <label class="block text-sm font-medium text-[var(--color-text-secondary)]">最大输出长度</label>
                      <input
                        v-model.number="globalDraft.generationDefaults.max_tokens"
                        type="number"
                        step="128"
                        min="1"
                        placeholder="默认"
                        class="input w-full"
                      />
                    </div>
                  </div>
                  <div class="space-y-2 pt-2">
                    <div class="text-sm font-medium text-[var(--color-text-secondary)]">上下文</div>
                    <div class="grid grid-cols-2 gap-4">
                      <div class="space-y-1.5">
                        <label class="block text-sm font-medium text-[var(--color-text-secondary)]">上下文长度</label>
                        <input
                          v-model.number="globalDraft.generationDefaults.context_size"
                          type="number"
                          min="0"
                          placeholder="未启用（默认不限制）"
                          class="input w-full"
                        />
                      </div>
                      <div class="space-y-1.5">
                        <label class="block text-sm font-medium text-[var(--color-text-secondary)]">草稿助手上下文条数限制</label>
                        <input
                          :value="globalDraft.draftHelpDefaults?.context_message_limit ?? ''"
                          type="text"
                          inputmode="numeric"
                          pattern="[0-9]*"
                          placeholder="未启用（跟随当前逻辑）"
                          class="input w-full"
                          @input="handleGlobalDraftHelpLimitInput"
                        />
                      </div>
                    </div>
                  </div>
                  <p class="text-xs text-[var(--color-text-muted)]">
                    实际上下文总限制长度为该「上下文长度」限制加上角色卡、用户信息、自定义系统提示词。草稿助手条数限制只统计最近消息条数，留空则回退到现有上下文逻辑。
                  </p>
                    </div>
                  </div>
                </div>
              </div>

              <!-- 外观与数据（默认折叠） -->
              <div class="rounded-xl border border-[var(--color-border-subtle)] bg-surface-muted/40 overflow-hidden">
                <button
                  type="button"
                  class="flex w-full cursor-pointer items-center justify-between gap-3 px-4 py-3.5 text-left text-sm font-semibold text-[var(--color-text-secondary)] select-none hover:bg-surface-hover/40"
                  :aria-expanded="globalAccordionOpen.appearance"
                  @click="globalAccordionOpen.appearance = !globalAccordionOpen.appearance"
                >
                  <span>外观与数据</span>
                  <ChevronDown
                    class="h-4 w-4 shrink-0 text-[var(--color-text-muted)] transition-transform duration-[800ms] ease-in-out"
                    :class="globalAccordionOpen.appearance ? 'rotate-180' : ''"
                  />
                </button>
                <div
                  class="grid transition-[grid-template-rows] duration-[800ms] ease-in-out"
                  :class="globalAccordionOpen.appearance ? 'grid-rows-[1fr]' : 'grid-rows-[0fr]'"
                >
                  <div class="min-h-0 overflow-hidden">
                    <div class="space-y-5 border-t border-[var(--color-border-subtle)] px-4 pb-4 pt-4">
                  <div class="space-y-3 rounded-xl border border-[var(--color-border-subtle)] bg-surface-overlay/35 p-3.5">
                    <div class="flex flex-wrap items-start justify-between gap-3">
                      <div class="min-w-0 space-y-1">
                        <div class="text-sm font-medium text-[var(--color-text-secondary)]">页面背景</div>
                        <p class="text-xs leading-relaxed text-[var(--color-text-muted)]">
                          图片只叠在主题底色之上；调低透明度时，底部主题渐变会继续透出。
                        </p>
                      </div>
                      <div class="flex flex-wrap gap-2">
                        <button
                          type="button"
                          class="min-h-10 rounded-lg bg-surface-muted px-4 py-2 text-sm text-[var(--color-text)] transition-colors whitespace-nowrap hover:bg-surface-hover"
                          @click="triggerPageBackgroundImport"
                        >
                          导入图片
                        </button>
                        <button
                          v-if="globalDraft.pageBackgroundImage"
                          type="button"
                          class="min-h-10 rounded-lg border border-[var(--color-border-subtle)] bg-transparent px-4 py-2 text-sm text-[var(--color-text-secondary)] transition-colors whitespace-nowrap hover:bg-surface-hover/30 hover:text-[var(--color-text)]"
                          @click="clearPageBackground"
                        >
                          清除
                        </button>
                      </div>
                      <input
                        ref="pageBackgroundInputRef"
                        type="file"
                        class="hidden"
                        accept="image/*,.png,.jpg,.jpeg,.webp,.gif"
                        @change="handlePageBackgroundImport"
                      />
                    </div>

                    <div
                      v-if="pageBackground.imageUrl.value"
                      class="w-1/2 min-w-[12rem] max-w-[22rem] overflow-hidden rounded-xl border border-[var(--color-border-subtle)] bg-surface-muted/70"
                    >
                      <div class="h-32 overflow-hidden">
                        <img
                          :src="pageBackground.imageUrl.value || ''"
                          alt="页面背景预览"
                          class="h-full w-full object-cover object-center"
                          :style="pageBackground.imageStyle.value"
                        />
                      </div>
                    </div>
                    <div
                      v-else
                      class="rounded-xl border border-dashed border-[var(--color-border-subtle)] bg-surface-muted/35 px-3 py-4 text-xs leading-relaxed text-[var(--color-text-muted)]"
                    >
                      还未导入页面背景。聊天页将继续仅使用当前主题渐变。
                    </div>

                    <div class="grid gap-3 md:grid-cols-2">
                      <label class="space-y-2">
                        <div class="flex items-center justify-between gap-2 text-xs text-[var(--color-text-secondary)]">
                          <span>透明度</span>
                          <span>{{ pageBackgroundOpacityModel }}%</span>
                        </div>
                        <input
                          v-model="pageBackgroundOpacityModel"
                          type="range"
                          min="0"
                          max="100"
                          step="1"
                          class="input-range"
                        />
                        <p class="text-xs text-[var(--color-text-muted)]">100% 为完整显示图片，降低后可透出主题底色。</p>
                      </label>

                      <label class="space-y-2">
                        <div class="flex items-center justify-between gap-2 text-xs text-[var(--color-text-secondary)]">
                          <span>模糊</span>
                          <span>{{ pageBackgroundBlurModel }} px</span>
                        </div>
                        <input
                          v-model="pageBackgroundBlurModel"
                          type="range"
                          min="0"
                          max="64"
                          step="1"
                          class="input-range"
                        />
                        <p class="text-xs text-[var(--color-text-muted)]">仅作用于图片层，不会影响主题底色与界面内容。</p>
                      </label>
                    </div>
                  </div>

                  <div class="space-y-3 rounded-xl border border-[var(--color-border-subtle)] bg-surface-overlay/35 p-3.5">
                    <div class="flex items-start justify-between gap-3">
                      <div class="min-w-0 space-y-1">
                        <div class="text-sm font-medium text-[var(--color-text-secondary)]">WebGPU 着色器背景</div>
                        <p class="text-xs leading-relaxed text-[var(--color-text-muted)]">
                          运行态可先编译并应用，不会自动写入后端；仅「保存设置」才持久化。
                        </p>
                      </div>
                      <button
                        type="button"
                        class="flex min-h-10 items-center gap-2 rounded-lg border border-[var(--color-border-subtle)] px-3 py-1.5 text-xs transition-colors hover:bg-surface-hover/30"
                        @click="globalDraft!.webgpuBackgroundEnabled = !globalDraft!.webgpuBackgroundEnabled"
                      >
                        <span
                          class="inline-block h-2.5 w-2.5 rounded-full"
                          :class="globalDraft!.webgpuBackgroundEnabled ? 'bg-emerald-400' : 'bg-[var(--color-text-muted)]'"
                        ></span>
                        <span>{{ globalDraft!.webgpuBackgroundEnabled ? '已启用' : '已关闭' }}</span>
                      </button>
                    </div>

                    <div class="flex flex-wrap items-center gap-2 text-xs">
                      <button
                        type="button"
                        class="min-h-9 rounded-lg bg-surface-muted px-3 py-1.5 transition-colors hover:bg-surface-hover disabled:opacity-50"
                        :disabled="webgpuPresetCreateBusy"
                        @click="createWebGpuPreset"
                      >
                        新建预设
                      </button>
                      <button
                        type="button"
                        class="min-h-9 rounded-lg border border-[var(--color-border-subtle)] px-3 py-1.5 transition-colors hover:bg-surface-hover/30 disabled:opacity-50"
                        :disabled="!activeWebgpuPreset || webgpuPresetSaveBusy || !webgpuPresetSourceDirty"
                        @click="saveWebGpuPresetSource"
                      >
                        保存源码
                      </button>
                      <button
                        type="button"
                        class="min-h-9 rounded-lg border border-[var(--color-border-subtle)] px-3 py-1.5 transition-colors hover:bg-surface-hover/30 disabled:opacity-50"
                        :disabled="!activeWebgpuPreset || webgpuPresetCompileBusy"
                        @click="compileWebGpuPreset"
                      >
                        编译
                      </button>
                      <button
                        type="button"
                        class="min-h-9 rounded-lg bg-brand-a20 px-3 py-1.5 text-brand transition-colors hover:bg-brand-a30 disabled:opacity-50"
                        :disabled="!webgpuCanRunFromEditor"
                        @click="runWebGpuPresetInRuntime"
                      >
                        运行（仅本次）
                      </button>
                      <button
                        type="button"
                        class="min-h-9 rounded-lg border border-[var(--color-border-subtle)] px-3 py-1.5 transition-colors hover:bg-surface-hover/30"
                        @click="stopWebGpuRuntime"
                      >
                        停止运行态
                      </button>
                      <button
                        type="button"
                        class="min-h-9 rounded-lg border border-red-500/40 px-3 py-1.5 text-red-300 transition-colors hover:bg-red-500/10 disabled:opacity-50"
                        :disabled="!activeWebgpuPreset || webgpuPresetDeleteBusy"
                        @click="deleteActiveWebGpuPreset"
                      >
                        删除
                      </button>
                    </div>

                    <div class="grid gap-3 md:grid-cols-[minmax(11rem,14rem)_1fr]">
                      <div class="space-y-2">
                        <label class="text-xs text-[var(--color-text-secondary)]">活动预设</label>
                        <div class="space-y-1 rounded-lg border border-[var(--color-border-subtle)] bg-surface-muted/35 p-2">
                          <button
                            v-for="item in webgpuPresets"
                            :key="item.id"
                            type="button"
                            class="flex min-h-9 w-full items-center justify-between rounded-md px-2 py-1 text-left text-xs transition-colors"
                            :class="item.id === activeWebgpuPresetId ? 'bg-brand-a20 text-brand' : 'hover:bg-surface-hover/40'"
                            @click="activeWebgpuPresetId = item.id"
                          >
                            <span class="truncate">{{ item.name }}</span>
                          </button>
                          <div v-if="webgpuPresets.length === 0" class="px-2 py-2 text-xs text-[var(--color-text-muted)]">
                            暂无预设
                          </div>
                        </div>
                      </div>

                      <div class="space-y-2">
                        <div class="flex flex-wrap items-center gap-2 text-xs text-[var(--color-text-muted)]">
                          <span>适配器状态：{{ webgpuAvailability === 'available' ? '可用' : webgpuAvailability === 'unavailable' ? '不可用' : '检测中' }}</span>
                          <span v-if="webgpuRuntimeState.hasOverride">· 运行态覆盖已启用</span>
                          <span v-if="webgpuPresetSourceDirty">· 当前源码含未保存改动</span>
                        </div>
                        <textarea
                          :value="webgpuPresetEditorSource"
                          class="input min-h-[14rem] w-full font-mono text-xs leading-relaxed"
                          :disabled="!activeWebgpuPreset"
                          placeholder="请选择或新建 WebGPU 预设后编辑 WGSL"
                          @input="onWebGpuEditorInputEvent"
                        ></textarea>
                        <p v-if="webgpuPresetCompileError" class="rounded-lg border border-red-500/35 bg-red-500/10 px-2.5 py-2 text-xs text-red-200 whitespace-pre-wrap">
                          {{ webgpuPresetCompileError }}
                        </p>
                        <p v-else class="text-xs text-[var(--color-text-muted)]">
                          Uniform 约定：`time`、`immersive`、`dpr`、`deltaTime`、`resolutionCss`、`resolutionPhysical`；主界面隐藏标签页时降频绘制。
                        </p>
                      </div>
                    </div>
                  </div>

                  <!-- 界面色系 -->
                  <div class="space-y-1.5">
                    <label class="block text-sm font-medium text-[var(--color-text-secondary)]">界面色系</label>
                    <ModernSelect
                      v-model="globalDraft.themeId"
                      :options="[...THEME_OPTIONS]"
                      placeholder="选择色系..."
                      class="w-full"
                    />
                    <p class="text-xs text-[var(--color-text-muted)]">暗色玻璃底，仅强调色随主题变化；未设置时默认为雾玫瑰。</p>
                  </div>

                  <!-- 字体自定义 -->
                  <div class="space-y-3">
                    <div class="text-sm font-medium text-[var(--color-text-secondary)]">字体</div>
                    <div class="flex flex-wrap gap-2 items-center">
                      <div class="relative group flex-1 min-w-0 max-w-[172px]">
                        <ModernSelect
                          v-model="fontModel"
                          :options="fontOptions"
                          placement="top"
                          searchable
                          placeholder="选择字体..."
                          class="w-full min-w-0"
                        />
                      </div>
                      <div class="flex h-10 items-center gap-0.5 rounded-lg border border-[var(--color-border)] bg-surface-muted px-1 py-0.5">
                        <button
                          type="button"
                          class="flex min-h-9 min-w-9 items-center justify-center rounded-md p-2 text-[var(--color-text-muted)] transition-colors hover:bg-surface-hover hover:text-[var(--color-text)]"
                          aria-label="减小字号"
                          @click="stepMessageFontSize(-1)"
                        >
                          <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="5" y1="12" x2="19" y2="12"/></svg>
                        </button>
                        <input
                          v-model.number="messageFontSizeModel"
                          type="number"
                          min="8"
                          max="72"
                          placeholder=""
                          class="w-10 bg-transparent border-0 text-center text-sm text-[var(--color-text)] focus:outline-none focus:ring-0 [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
                        />
                        <button
                          type="button"
                          class="flex min-h-9 min-w-9 items-center justify-center rounded-md p-2 text-[var(--color-text-muted)] transition-colors hover:bg-surface-hover hover:text-[var(--color-text)]"
                          aria-label="增大字号"
                          @click="stepMessageFontSize(1)"
                        >
                          <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
                        </button>
                      </div>
                      <button
                        type="button"
                        class="min-h-10 rounded-lg bg-surface-muted px-4 py-2 text-sm text-[var(--color-text)] transition-colors whitespace-nowrap hover:bg-surface-hover"
                        @click="triggerFontImport"
                      >
                        导入字体
                      </button>
                      <input
                        ref="fontInputRef"
                        type="file"
                        class="hidden"
                        accept=".ttf,.otf,.woff,.woff2"
                        @change="handleFontImport"
                      />
                    </div>
                  </div>

                  <div class="space-y-3">
                    <div class="text-sm font-medium text-[var(--color-text-secondary)]">数据备份与导入</div>
                    <div class="flex flex-col gap-2">
                      <div class="grid grid-cols-2 gap-2">
                        <button
                          type="button"
                          class="min-h-10 rounded-lg bg-surface-muted px-3 py-2 text-center text-sm leading-tight text-[var(--color-text)] transition-colors min-w-0 hover:bg-surface-hover"
                          @click="downloadSettingsBackup('basic')"
                        >
                          基本设置
                        </button>
                        <button
                          type="button"
                          class="min-h-10 rounded-lg bg-surface-muted px-3 py-2 text-center text-sm leading-tight text-[var(--color-text)] transition-colors min-w-0 hover:bg-surface-hover"
                          @click="downloadSettingsBackup('with_characters')"
                        >
                          包含角色卡
                        </button>
                      </div>
                      <div class="grid grid-cols-2 gap-2">
                        <button
                          type="button"
                          class="min-h-10 rounded-lg bg-surface-muted px-3 py-2 text-center text-sm leading-tight text-[var(--color-text)] transition-colors min-w-0 hover:bg-surface-hover"
                          @click="downloadSettingsBackup('with_chats')"
                        >
                          包含全部聊天记录
                        </button>
                        <button
                          type="button"
                          class="min-h-10 rounded-lg bg-surface-muted px-3 py-2 text-center text-sm leading-tight text-[var(--color-text)] transition-colors min-w-0 hover:bg-surface-hover"
                          @click="triggerImport"
                        >
                          导入数据
                        </button>
                      </div>
                      <input
                        ref="importInputRef"
                        type="file"
                        class="hidden"
                        accept=".txt,.json,.zip"
                        @change="handleImportChange"
                      />
                    </div>
                    <div class="text-xs text-[var(--color-text-muted)]">
                      备份会导出全部系统设置（含用户 Persona 头像）；“包含角色卡/包含全部聊天记录”同时包含世界书数据。
                    </div>
                  </div>
                    </div>
                  </div>
                </div>
              </div>

              <!-- 应用与更新（默认折叠） -->
              <div class="rounded-xl border border-[var(--color-border-subtle)] bg-surface-muted/40 overflow-hidden">
                <button
                  type="button"
                  class="flex w-full cursor-pointer items-center justify-between gap-3 px-4 py-3.5 text-left text-sm font-semibold text-[var(--color-text-secondary)] select-none hover:bg-surface-hover/40"
                  :aria-expanded="globalAccordionOpen.tts"
                  @click="globalAccordionOpen.tts = !globalAccordionOpen.tts"
                >
                  <span>文字转语音（TTS）</span>
                  <ChevronDown
                    class="h-4 w-4 shrink-0 text-[var(--color-text-muted)] transition-transform duration-[800ms] ease-in-out"
                    :class="globalAccordionOpen.tts ? 'rotate-180' : ''"
                  />
                </button>
                <div
                  class="grid transition-[grid-template-rows] duration-[800ms] ease-in-out"
                  :class="globalAccordionOpen.tts ? 'grid-rows-[1fr]' : 'grid-rows-[0fr]'"
                >
                  <div class="min-h-0 overflow-hidden">
                    <div class="space-y-3 border-t border-[var(--color-border-subtle)] px-4 pb-4 pt-4">
                      <!-- TTS 总开关 -->
                      <div class="space-y-2">
                        <label class="block text-sm font-medium text-[var(--color-text-secondary)]">启用文字转语音</label>
                        <button
                          type="button"
                          class="flex min-h-11 w-full cursor-pointer items-center gap-3 py-1 text-left group"
                          @click="globalDraft!.ttsEnabled = !globalDraft!.ttsEnabled; if (globalDraft!.ttsEnabled) startTtsCachePoll(); else stopTtsCachePoll()"
                        >
                          <div
                            class="relative h-6 w-11 shrink-0 rounded-full transition-colors duration-200 ease-out"
                            :class="globalDraft!.ttsEnabled ? 'bg-brand' : 'bg-[var(--color-track)]'"
                          >
                            <div
                              class="absolute left-1 top-1 h-4 w-4 rounded-full bg-[var(--color-on-brand)]"
                              :style="{
                                transform: globalDraft!.ttsEnabled ? 'translateX(1.25rem)' : 'translateX(0)',
                                transition: 'transform 200ms ease-out',
                              }"
                            ></div>
                          </div>
                          <span class="text-xs text-[var(--color-text-secondary)]">
                            {{ globalDraft!.ttsEnabled ? '已开启：启用语音合成功能' : '已关闭' }}
                          </span>
                        </button>
                      </div>

                      <!-- 缓存上限 -->
                      <div v-if="globalDraft!.ttsEnabled" class="space-y-2">
                        <label class="block text-sm font-medium text-[var(--color-text-secondary)]">缓存上限（MB）</label>
                        <input
                          v-model.number="globalDraft!.ttsAudioCacheLimitMb"
                          type="number"
                          min="10"
                          max="10000"
                          class="input w-full"
                        />
                        <!-- 缓存占比条 -->
                        <div class="space-y-1">
                          <div class="h-2 w-full rounded-full bg-[var(--color-track)] overflow-hidden">
                            <div
                              class="h-full rounded-full transition-[width] duration-500 ease-out"
                              :class="ttsCachePercent > 90 ? 'bg-red-500' : ttsCachePercent > 70 ? 'bg-amber-500' : 'bg-brand'"
                              :style="{ width: (ttsCacheStats ? ttsCachePercent : 0) + '%' }"
                            ></div>
                          </div>
                          <div class="flex items-center justify-between text-xs text-[var(--color-text-muted)]">
                            <span>{{ ttsCacheStats ? `${formatBytes(ttsCacheStats.usedBytes)} / ${formatBytes(ttsCacheStats.limitBytes)}` : '正在读取缓存占用...' }}</span>
                            <button
                              type="button"
                              class="rounded px-2 py-0.5 text-xs text-[var(--color-text-secondary)] hover:bg-surface-hover transition-colors"
                              :disabled="!ttsCacheStats"
                              @click="apiDelete('/api/tts/cache/clear').then(() => fetchTtsCacheStats())"
                            >
                              清空缓存
                            </button>
                          </div>
                        </div>
                      </div>

                      <p class="text-xs text-[var(--color-text-muted)]">
                        开启后可在聊天界面使用语音合成功能。需在 API 预设中至少配置一个 TTS 服务预设，可选 MiniMax 或 GLM TTS。
                      </p>
                    </div>
                  </div>
                </div>
              </div>

              <!-- 应用与更新（默认折叠） -->
              <div class="rounded-xl border border-[var(--color-border-subtle)] bg-surface-muted/40 overflow-hidden">
                <button
                  type="button"
                  class="flex w-full cursor-pointer items-center justify-between gap-3 px-4 py-3.5 text-left text-sm font-semibold text-[var(--color-text-secondary)] select-none hover:bg-surface-hover/40"
                  :aria-expanded="globalAccordionOpen.app"
                  @click="globalAccordionOpen.app = !globalAccordionOpen.app"
                >
                  <span>应用与更新</span>
                  <ChevronDown
                    class="h-4 w-4 shrink-0 text-[var(--color-text-muted)] transition-transform duration-[800ms] ease-in-out"
                    :class="globalAccordionOpen.app ? 'rotate-180' : ''"
                  />
                </button>
                <div
                  class="grid transition-[grid-template-rows] duration-[800ms] ease-in-out"
                  :class="globalAccordionOpen.app ? 'grid-rows-[1fr]' : 'grid-rows-[0fr]'"
                >
                  <div class="min-h-0 overflow-hidden">
                    <div class="space-y-3 border-t border-[var(--color-border-subtle)] px-4 pb-4 pt-4">
                      <div class="flex flex-wrap items-center gap-2">
                        <button
                          type="button"
                          class="min-h-10 rounded-lg bg-surface-muted px-4 py-2 text-sm text-[var(--color-text)] transition-colors whitespace-nowrap hover:bg-surface-hover"
                          :disabled="checkUpdateLoading"
                          @click="checkUpdate"
                        >
                          检查更新
                        </button>
                        <span v-if="checkUpdateMessage" class="text-xs text-[var(--color-text-secondary)]">{{ checkUpdateMessage }}</span>
                      </div>
                      <a
                        href="https://github.com/DuoHBshuijiao/SimpleTavern/releases"
                        target="_blank"
                        rel="noopener noreferrer"
                        class="block cursor-pointer text-center text-xs text-[var(--color-text-muted)] transition-colors hover:text-[var(--color-text-secondary)] hover:underline"
                      >{{ appVersion || '…' }}</a>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- Presets Management：主滚动与全局/会话 Tab 共用外层 drawer-scroll，避免内层窄栏+双滚动条 -->
          <div v-if="preloaded" v-show="tab === 'presets'" class="space-y-6">
              <div v-if="!globalDraft" class="text-center text-[var(--color-text-muted)] py-8">加载中...</div>
              <div v-else class="flex gap-3 items-start">
                  <!-- Preset List：sticky 吸附，右侧长表单滚动时左栏留在可视区；列表过长时仅内层滚动 -->
                  <div
                    class="sticky top-0 z-10 flex min-w-0 flex-[0_0_min(11rem,34%)] flex-col self-start border-r border-[var(--color-border-subtle)] pr-3"
                  >
                      <div ref="presetListHeaderRef" class="mb-2 flex items-center justify-between gap-1.5">
                          <span class="shrink-0 text-xs font-bold text-[var(--color-text-secondary)] sm:text-sm">预设列表</span>
                          <button
                            type="button"
                            class="inline-flex min-h-8 shrink-0 items-center rounded-md bg-brand-a20 px-2 py-0.5 text-[11px] font-medium leading-tight text-brand transition-colors hover:bg-brand-a30 touch-manipulation sm:px-2.5 sm:text-xs"
                            @click="createPreset"
                          >
                            + 新建
                          </button>
                      </div>
                      <div
                        class="drawer-scroll space-y-1 overflow-y-auto custom-scrollbar"
                        :style="
                          presetListMaxHeightPx != null
                            ? { maxHeight: `${presetListMaxHeightPx}px` }
                            : { maxHeight: 'min(55vh, 22rem)' }
                        "
                      >
                          <div
                              v-for="(p, idx) in globalDraft.apiPresets"
                              :key="p.id"
                              draggable="true"
                              class="group relative flex min-h-10 cursor-grab items-center rounded-lg py-1.5 pl-2 pr-1 text-sm transition-colors active:cursor-grabbing"
                              :class="[
                                editingPresetId === p.id ? 'bg-brand-a10 text-brand' : 'text-[var(--color-text-secondary)] hover:bg-surface-muted',
                                apiPresetOrderDraggingIdx === idx ? 'opacity-50 ring-1 ring-brand-a50' : '',
                              ]"
                              @click="editingPresetId = p.id"
                              @dragstart="handleApiPresetOrderDragStart(idx)"
                              @dragover="handleApiPresetOrderDragOver($event, idx)"
                              @dragend="handleApiPresetOrderDragEnd"
                          >
                              <span class="min-w-0 max-w-full truncate pr-7">{{ p.name }}</span>
                              <span
                                v-if="isTtsPreset(p)"
                                draggable="false"
                                class="absolute right-8 top-1.5 text-[11px] font-semibold leading-none text-brand"
                                aria-label="TTS 预设"
                                title="TTS 预设"
                              >t</span>
                              <button
                                type="button"
                                draggable="false"
                                class="absolute right-0.5 top-1/2 inline-flex min-h-8 min-w-8 -translate-y-1/2 items-center justify-center rounded-md text-[var(--color-text-muted)] opacity-0 pointer-events-none touch-manipulation hover:text-error group-hover:pointer-events-auto group-hover:opacity-100"
                                @click.stop="deletePreset(p.id)"
                              >
                                <X class="h-3.5 w-3.5" />
                              </button>
                          </div>
                           <div v-if="globalDraft.apiPresets.length === 0" class="text-xs text-[var(--color-text-muted)] text-center py-4">无预设</div>
                      </div>
                  </div>

                  <!-- Preset Editor -->
                  <div class="min-w-0 flex-1 flex flex-col" v-if="editingPreset">
                       <div class="min-w-0 space-y-4 pb-4">
                          <div class="space-y-1.5">
                              <div class="flex items-center justify-between gap-3">
                                <label class="block text-xs font-medium text-[var(--color-text-secondary)]">预设名称</label>
                                <button
                                  type="button"
                                  class="inline-flex items-center gap-2 text-xs text-[var(--color-text-secondary)] transition-colors hover:text-[var(--color-text)]"
                                  @click="setPresetTtsService(editingPreset!, !isTtsPreset(editingPreset))"
                                >
                                  <ThemedCheckbox :checked="isTtsPreset(editingPreset)" />
                                  <span>作为 TTS 服务</span>
                                </button>
                              </div>
                              <input 
                                  v-model="editingPreset.name" 
                                  type="text" 
                                  class="input input-sm w-full"
                              />
                              <div v-if="isTtsPreset(editingPreset)" class="space-y-1.5">
                                <label class="block text-[11px] font-medium text-[var(--color-text-muted)]">TTS 提供商</label>
                                <ModernSelect
                                  :model-value="editingPresetTtsProvider"
                                  :options="TTS_PROVIDER_OPTIONS"
                                  class="w-full"
                                  placeholder="选择 TTS 提供商…"
                                  @update:model-value="onEditingPresetTtsProviderChange"
                                />
                              </div>
                          </div>

                           <div class="space-y-1.5">
                              <label class="block text-xs font-medium text-[var(--color-text-secondary)]">API 基础地址</label>
                              <input 
                                  v-model="editingPreset.baseUrl" 
                                  type="text" 
                                  :placeholder="editingPresetBaseUrlPlaceholder"
                                  class="input input-sm w-full"
                              />
                              <p class="text-xs text-[var(--color-text-muted)]">{{ editingPresetBaseUrlHint }}</p>
                          </div>

                          <div class="space-y-1.5">
                              <label class="block text-xs font-medium text-[var(--color-text-secondary)]">API Key</label>
                               <div class="relative">
                                  <input 
                                      v-model="editingPreset.apiKey" 
                                      :type="editingPresetShowApiKey ? 'text' : 'password'"
                                      class="input input-sm w-full pr-8"
                                  />
                                  <button 
                                      type="button"
                                      class="absolute right-1.5 top-1/2 inline-flex min-h-9 min-w-9 -translate-y-1/2 items-center justify-center rounded-md text-[var(--color-text-muted)] touch-manipulation hover:text-[var(--color-text-secondary)]"
                                      @click="editingPresetShowApiKey = !editingPresetShowApiKey"
                                  >
                                      <component :is="editingPresetShowApiKey ? Eye : EyeOff" class="w-4 h-4" />
                                  </button>
                               </div>
                          </div>

                          <div class="space-y-2">
                               <div class="flex justify-between items-center gap-2 flex-wrap">
                                   <label class="block text-xs font-medium text-[var(--color-text-secondary)]">模型列表</label>
                                   <button 
                                      class="text-xs text-brand hover:text-brand-hover flex items-center gap-1 shrink-0" 
                                      :disabled="presetModelsLoading"
                                      @click="openModelSelector(editingPreset!)"
                                   >
                                      <Loader2 v-if="presetModelsLoading" class="animate-spin w-3 h-3" />
                                      <span>从 API 获取并筛选</span>
                                   </button>
                               </div>
                               <div
                                 v-if="editingPreset.models.length"
                                 class="flex flex-wrap items-center gap-x-1 gap-y-0.5 text-[10px] leading-tight text-[var(--color-text-secondary)]"
                               >
                                 <button
                                   type="button"
                                   class="min-h-0 rounded px-0.5 py-0 text-brand hover:underline disabled:pointer-events-none disabled:opacity-40"
                                   @click="selectAllPresetModelNames"
                                 >
                                   全选
                                 </button>
                                 <span class="select-none text-[var(--color-text-muted)]">·</span>
                                 <button
                                   type="button"
                                   class="min-h-0 rounded px-0.5 py-0 text-brand hover:underline disabled:pointer-events-none disabled:opacity-40"
                                   :disabled="presetModelListSelection.size === 0"
                                   @click="clearPresetModelListSelection"
                                 >
                                   清空选择
                                 </button>
                                 <span class="select-none text-[var(--color-text-muted)]">·</span>
                                 <button
                                   type="button"
                                   class="min-h-0 rounded px-0.5 py-0 text-error/90 hover:underline disabled:pointer-events-none disabled:opacity-40"
                                   :disabled="presetModelListSelection.size === 0"
                                   @click="removeSelectedPresetModelNames"
                                 >
                                   删除所选
                                 </button>
                                 <span class="select-none text-[var(--color-text-muted)]">·</span>
                                 <button
                                   type="button"
                                   class="min-h-0 rounded px-0.5 py-0 text-error/90 hover:underline disabled:pointer-events-none disabled:opacity-40"
                                   @click="clearAllPresetModelNames"
                                 >
                                   清空全部
                                 </button>
                               </div>
                               <div class="drawer-scroll bg-surface-overlay border border-[var(--color-border)] rounded-lg p-2 min-h-[100px] max-h-[200px] overflow-y-auto custom-scrollbar">
                                   <div class="flex flex-wrap gap-2">
                                       <div
                                         v-for="(m, idx) in editingPreset.models"
                                         :key="`${idx}-${m}`"
                                         role="button"
                                         tabindex="0"
                                         class="group relative inline-flex max-w-full cursor-pointer items-center gap-1 rounded-md border border-[var(--color-border-subtle)] bg-surface-overlay/55 px-2 py-1 text-xs text-[var(--color-text-secondary)] backdrop-blur-sm transition-[box-shadow,border-color] hover:bg-surface-overlay/80"
                                         :class="presetModelListSelection.has(m) ? 'ring-1 ring-brand/50 border-brand/35 shadow-[0_0_0_1px_color-mix(in_srgb,var(--color-brand)_25%,transparent)]' : ''"
                                         @click="togglePresetModelListSelection(m)"
                                         @keydown.enter.prevent="togglePresetModelListSelection(m)"
                                         @keydown.space.prevent="togglePresetModelListSelection(m)"
                                       >
                                           <span class="min-w-0 truncate">{{ m }}</span>
                                           <button
                                             type="button"
                                             class="shrink-0 rounded p-0.5 text-[var(--color-text-muted)] opacity-0 transition-opacity hover:text-error group-hover:opacity-100 focus:opacity-100 focus:outline-none"
                                             aria-label="移除此模型"
                                             @click.stop="removeSinglePresetModelAt(idx)"
                                           >
                                            <X class="w-3 h-3" />
                                           </button>
                                       </div>
                                        <div v-if="!editingPreset.models.length" class="text-xs text-[var(--color-text-muted)] w-full text-center py-4">
                                            点击上方「从 API 获取并筛选」或手动添加
                                        </div>
                                   </div>
                               </div>
                               <!-- 手动添加模型 -->
                                <div class="flex gap-2">
                                   <input 
                                      type="text" 
                                      placeholder="手动输入模型名..."
                                      class="input input-sm flex-1 rounded px-2 py-1 text-xs outline-none"
                                      @keydown.enter="(e) => {
                                          const val = (e.target as HTMLInputElement).value.trim();
                                          if(val && !editingPreset!.models.includes(val)) {
                                              editingPreset!.models.push(val);
                                              (e.target as HTMLInputElement).value = '';
                                          }
                                      }"
                                   />
                                </div>
                          </div>

                          <div v-if="isTtsPreset(editingPreset)" class="space-y-3 rounded-xl border border-[var(--color-border-subtle)] bg-surface-muted/35 p-3">
                            <p class="text-[11px] text-[var(--color-text-muted)]">
                              当前提供商：{{ editingPresetTtsProvider === 'glm_local' ? 'GLM-TTS（本地）' : editingPresetTtsProvider === 'qwen3_local' ? 'Qwen3-TTS（本地）' : editingPresetTtsProvider === 'omnivoice_local' ? 'OmniVoice（本地）' : editingPresetTtsProvider === 'glm' ? 'GLM TTS（智谱）' : 'MiniMax（兼容）' }}
                            </p>

                            <!-- GLM-TTS 本地专属配置 -->
                            <template v-if="editingPresetIsGlmLocal">
                              <div class="space-y-2">
                                <label class="block text-xs font-medium text-[var(--color-text-secondary)]">仓库路径</label>
                                <input v-model="editingPreset!.ttsGlmLocalRepoPath" type="text" class="input input-sm w-full" placeholder="E:\GLM-TTS（GLM-TTS 仓库根目录）" />
                                <p class="text-[10px] text-[var(--color-text-muted)]">指向包含 run_api_gpu.ps1 的已就绪 GLM-TTS 目录。</p>
                              </div>
                              <div class="flex items-center gap-3">
                                <div class="flex-1 space-y-1">
                                  <label class="block text-xs font-medium text-[var(--color-text-secondary)]">端口</label>
                                  <input v-model.number="editingPreset!.ttsGlmLocalPort" type="number" min="1" max="65535" class="input input-sm w-full" placeholder="8088" />
                                </div>
                                <div class="flex-1 space-y-1">
                                  <label class="block text-xs font-medium text-[var(--color-text-secondary)]">托管启动</label>
                                  <button type="button" class="btn btn-xs w-full" :class="editingPreset!.ttsGlmLocalManaged ? 'btn-primary' : 'btn-secondary'" @click="editingPreset!.ttsGlmLocalManaged = !editingPreset!.ttsGlmLocalManaged">
                                    {{ editingPreset!.ttsGlmLocalManaged ? '由程序启动' : '手动启动' }}
                                  </button>
                                </div>
                              </div>
                              <p class="text-[10px] text-[var(--color-text-muted)]">「由程序启动」会在首次合成前自动运行 run_api_gpu.ps1；「手动启动」需自行启动本地 API。</p>
                            </template>

                            <template v-else-if="editingPresetIsQwen3Local">
                              <div class="space-y-2">
                                <label class="block text-xs font-medium text-[var(--color-text-secondary)]">仓库路径</label>
                                <input v-model="editingPreset!.ttsQwen3LocalRepoPath" type="text" class="input input-sm w-full" placeholder="E:\Qwen3-TTS（Qwen3-TTS 仓库根目录）" />
                                <p class="text-[10px] text-[var(--color-text-muted)]">指向安装好 Qwen3-TTS 与 its gateway 的仓库目录；托管模式会从这里启动 uvicorn 网关。</p>
                              </div>
                              <div class="grid gap-3 md:grid-cols-2">
                                <div class="space-y-1">
                                  <label class="block text-xs font-medium text-[var(--color-text-secondary)]">主端口（CustomVoice 网关）</label>
                                  <input v-model.number="editingPreset!.ttsQwen3LocalPort" type="number" min="1" max="65535" class="input input-sm w-full" placeholder="8080" />
                                </div>
                                <div class="space-y-1">
                                  <label class="block text-xs font-medium text-[var(--color-text-secondary)]">语音克隆端口（Base 网关）</label>
                                  <input
                                    :value="editingPreset!.ttsQwen3LocalVoiceClonePort ?? ''"
                                    type="number"
                                    min="1"
                                    max="65535"
                                    class="input input-sm w-full"
                                    placeholder="留空 = 主端口 + 1"
                                    @input="onQwen3VoiceClonePortInput"
                                  />
                                </div>
                              </div>
                              <div class="grid gap-3 md:grid-cols-2">
                                <div class="space-y-1">
                                  <label class="block text-xs font-medium text-[var(--color-text-secondary)]">托管启动</label>
                                  <button type="button" class="btn btn-xs w-full" :class="editingPreset!.ttsQwen3LocalManaged ? 'btn-primary' : 'btn-secondary'" @click="editingPreset!.ttsQwen3LocalManaged = !editingPreset!.ttsQwen3LocalManaged">
                                    {{ editingPreset!.ttsQwen3LocalManaged ? '由程序启动' : '手动启动' }}
                                  </button>
                                </div>
                                <div class="space-y-1">
                                  <label class="block text-xs font-medium text-[var(--color-text-secondary)]">设备</label>
                                  <input v-model="editingPreset!.ttsQwen3LocalDevice" type="text" class="input input-sm w-full" placeholder="cuda:0" />
                                </div>
                              </div>
                              <div class="grid gap-3 md:grid-cols-2">
                                <div class="space-y-1">
                                  <label class="block text-xs font-medium text-[var(--color-text-secondary)]">CustomVoice 模型 ID（/custom_voice）</label>
                                  <input v-model="editingPreset!.ttsQwen3LocalModelId" type="text" class="input input-sm w-full" placeholder="Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice" />
                                </div>
                                <div class="space-y-1">
                                  <label class="block text-xs font-medium text-[var(--color-text-secondary)]">Base 模型 ID（/voice_clone）</label>
                                  <input v-model="editingPreset!.ttsQwen3LocalBaseModelId" type="text" class="input input-sm w-full" placeholder="Qwen/Qwen3-TTS-12Hz-1.7B-Base" />
                                </div>
                              </div>
                              <div class="space-y-1">
                                <label class="block text-xs font-medium text-[var(--color-text-secondary)]">默认语言</label>
                                <input v-model="editingPreset!.ttsQwen3LocalDefaultLanguage" type="text" class="input input-sm w-full" placeholder="Auto" />
                              </div>
                              <p class="text-[10px] text-[var(--color-text-muted)]">
                                托管模式会启动<strong>两个</strong> uvicorn：主端口加载 CustomVoice（仅 speaker → /v1/tts/custom_voice）；语音克隆端口加载 Base（参考音频+转写 → /v1/tts/voice_clone）。两端口必须不同；手动启动时需自行各启一个网关并填好 Base URL（主地址对应主端口）。
                              </p>
                            </template>

                            <template v-else-if="editingPresetIsOmniVoiceLocal">
                              <div class="space-y-2">
                                <label class="block text-xs font-medium text-[var(--color-text-secondary)]">仓库路径</label>
                                <input v-model="editingPreset!.ttsOmniVoiceLocalRepoPath" type="text" class="input input-sm w-full" placeholder="E:\OmniVoice（OmniVoice 仓库根目录）" />
                                <p class="text-[10px] text-[var(--color-text-muted)]">指向安装好 OmniVoice 与其 .venv 的仓库目录；托管模式会从这里启动 uvicorn。</p>
                              </div>
                              <div class="grid gap-3 md:grid-cols-2">
                                <div class="space-y-1">
                                  <label class="block text-xs font-medium text-[var(--color-text-secondary)]">端口</label>
                                  <input v-model.number="editingPreset!.ttsOmniVoiceLocalPort" type="number" min="1" max="65535" class="input input-sm w-full" placeholder="8089" />
                                </div>
                                <div class="space-y-1">
                                  <label class="block text-xs font-medium text-[var(--color-text-secondary)]">托管启动</label>
                                  <button type="button" class="btn btn-xs w-full" :class="editingPreset!.ttsOmniVoiceLocalManaged ? 'btn-primary' : 'btn-secondary'" @click="editingPreset!.ttsOmniVoiceLocalManaged = !editingPreset!.ttsOmniVoiceLocalManaged">
                                    {{ editingPreset!.ttsOmniVoiceLocalManaged ? '由程序启动' : '手动启动' }}
                                  </button>
                                </div>
                              </div>
                              <div class="grid gap-3 md:grid-cols-2">
                                <div class="space-y-1">
                                  <label class="block text-xs font-medium text-[var(--color-text-secondary)]">模型 ID / 路径</label>
                                  <input v-model="editingPreset!.ttsOmniVoiceLocalModelId" type="text" class="input input-sm w-full" placeholder="k2-fsa/OmniVoice" />
                                </div>
                                <div class="space-y-1">
                                  <label class="block text-xs font-medium text-[var(--color-text-secondary)]">设备</label>
                                  <input v-model="editingPreset!.ttsOmniVoiceLocalDevice" type="text" class="input input-sm w-full" placeholder="cuda:0（留空则交给 OmniVoice 自动选择）" />
                                </div>
                              </div>
                              <div class="space-y-1">
                                <label class="block text-xs font-medium text-[var(--color-text-secondary)]">默认语言</label>
                                <input v-model="editingPreset!.ttsOmniVoiceLocalDefaultLanguage" type="text" class="input input-sm w-full" placeholder="例如 zh、Chinese、English（可留空）" />
                              </div>
                              <p class="text-[10px] text-[var(--color-text-muted)]">托管模式会执行 python -m uvicorn omnivoice.api.server:app --host 127.0.0.1 --port &lt;port&gt;，并通过环境变量传入模型与 device；后端调用 JSON 接口 /v1/tts。</p>
                            </template>

                            <div class="flex items-center justify-between gap-2 flex-wrap">
                              <label class="block text-xs font-medium text-[var(--color-text-secondary)]">音色列表</label>
                              <button
                                v-if="editingPresetSupportsVoiceFetch"
                                type="button"
                                class="text-xs text-brand hover:text-brand-hover flex items-center gap-1 shrink-0"
                                :disabled="presetVoicesLoading"
                                @click="openVoiceSelector(editingPreset!)"
                              >
                                <Loader2 v-if="presetVoicesLoading" class="animate-spin w-3 h-3" />
                                <span>从 API 获取并筛选</span>
                              </button>
                            </div>

                            <div
                              v-if="editingPresetVoiceCatalog.length"
                              class="flex flex-wrap items-center gap-x-1 gap-y-0.5 text-[10px] leading-tight text-[var(--color-text-secondary)]"
                            >
                              <button type="button" class="min-h-0 rounded px-0.5 py-0 text-brand hover:underline" @click="selectAllPresetVoices">全选</button>
                              <span class="select-none text-[var(--color-text-muted)]">·</span>
                              <button type="button" class="min-h-0 rounded px-0.5 py-0 text-brand hover:underline disabled:pointer-events-none disabled:opacity-40" :disabled="presetVoiceListSelection.size === 0" @click="clearPresetVoiceSelection">清空选择</button>
                              <span class="select-none text-[var(--color-text-muted)]">·</span>
                              <button type="button" class="min-h-0 rounded px-0.5 py-0 text-error/90 hover:underline disabled:pointer-events-none disabled:opacity-40" :disabled="presetVoiceListSelection.size === 0" @click="removeSelectedPresetVoices">删除所选</button>
                              <span class="select-none text-[var(--color-text-muted)]">·</span>
                              <button type="button" class="min-h-0 rounded px-0.5 py-0 text-error/90 hover:underline disabled:pointer-events-none disabled:opacity-40" :disabled="editingPresetVoiceCatalog.length === 0" @click="clearAllPresetVoices">清空全部</button>
                            </div>

                            <div class="drawer-scroll bg-surface-overlay border border-[var(--color-border)] rounded-lg p-2 min-h-[96px] max-h-[200px] overflow-y-auto custom-scrollbar">
                              <div class="flex flex-wrap gap-2">
                                <button
                                  v-for="voice in editingPresetVoiceCatalog"
                                  :key="voice.voiceId"
                                  type="button"
                                  class="group relative inline-flex max-w-full cursor-pointer items-center gap-1 rounded-md border border-[var(--color-border-subtle)] bg-surface-overlay/55 px-2 py-1 text-xs text-[var(--color-text-secondary)] backdrop-blur-sm transition-[box-shadow,border-color] hover:bg-surface-overlay/80"
                                  :class="presetVoiceListSelection.has(voice.voiceId) ? 'ring-1 ring-brand/50 border-brand/35 shadow-[0_0_0_1px_color-mix(in_srgb,var(--color-brand)_25%,transparent)]' : ''"
                                  @click="togglePresetVoiceSelection(voice.voiceId)"
                                >
                                  <span class="min-w-0 truncate">{{ voice.name }}</span>
                                  <span class="rounded-full bg-surface-muted px-1.5 py-0.5 text-[10px] text-[var(--color-text-muted)]">{{ voice.voiceType }}</span>
                                </button>
                                <div v-if="!editingPresetVoiceCatalog.length" class="text-xs text-[var(--color-text-muted)] w-full text-center py-4">{{ editingPresetIsGlmLocal ? '请在下方添加本地参考音色' : editingPresetIsQwen3Local ? '请在下方添加 Qwen3 音色条目' : editingPresetIsOmniVoiceLocal ? '请在下方添加 OmniVoice 音色条目' : '点击上方「从 API 获取并筛选」或下方手动添加 voice_id' }}</div>
                              </div>
                            </div>

                            <div v-if="!editingPresetIsGlmLocal && !editingPresetIsQwen3Local && !editingPresetIsOmniVoiceLocal" class="flex gap-2">
                              <input
                                type="text"
                                placeholder="手动输入 voice_id 后按回车添加…"
                                class="input input-sm flex-1 rounded px-2 py-1 text-xs outline-none font-mono"
                                @keydown.enter="
                                  (e) => {
                                    const val = (e.target as HTMLInputElement).value.trim()
                                    if (val) {
                                      upsertEditingPresetVoiceCatalog([{ voiceId: val, name: val, voiceType: editingPresetTtsProvider === 'glm' ? 'private' : 'system' }])
                                      ;(e.target as HTMLInputElement).value = ''
                                    }
                                  }
                                "
                              />
                            </div>

                            <!-- GLM-TTS（本地）参考音色编辑 -->
                            <template v-if="editingPresetIsGlmLocal">
                              <div class="space-y-2 rounded-lg border border-[var(--color-border-subtle)] bg-surface-overlay px-3 py-3">
                                <div class="text-xs font-medium text-[var(--color-text-secondary)]">添加本地参考音色</div>
                                <input v-model="glmLocalVoiceDraft.voiceId" type="text" class="input input-sm w-full" placeholder="音色 ID（唯一标识）" />
                                <input v-model="glmLocalVoiceDraft.name" type="text" class="input input-sm w-full" placeholder="音色名称（显示用）" />
                                <input v-model="glmLocalVoiceDraft.promptAudioPath" type="text" class="input input-sm w-full font-mono" placeholder="参考音频路径（wav/flac 绝对路径）" />
                                <input v-model="glmLocalVoiceDraft.promptText" type="text" class="input input-sm w-full" placeholder="参考音频对应转写文本（推荐填写）" />
                                <p class="text-[10px] text-[var(--color-text-muted)]">每条音色需要一段参考音频和对应文本。路径为本机文件绝对路径。</p>
                                <button
                                  type="button"
                                  class="btn btn-sm btn-primary w-full"
                                  :disabled="!glmLocalVoiceDraft.voiceId.trim()"
                                  @click="addGlmLocalVoice"
                                >添加音色</button>
                              </div>

                              <!-- 已添加的音色详情编辑 -->
                              <div v-for="voice in editingPresetVoiceCatalog" :key="'detail-' + voice.voiceId" class="space-y-1 rounded-lg border border-[var(--color-border-subtle)] bg-surface-overlay/60 px-3 py-2 text-xs">
                                <div class="flex items-center justify-between">
                                  <span class="font-medium text-[var(--color-text-secondary)]">{{ voice.name }} <span class="text-[10px] text-[var(--color-text-muted)]">({{ voice.voiceId }})</span></span>
                                </div>
                                <input :value="voice.promptAudioPath ?? ''" type="text" class="input input-sm w-full font-mono text-[10px]" placeholder="参考音频路径" @change="(e) => updateGlmLocalVoiceField(voice.voiceId, 'promptAudioPath', (e.target as HTMLInputElement).value)" />
                                <input :value="voice.promptText ?? ''" type="text" class="input input-sm w-full text-[10px]" placeholder="参考转写文本" @change="(e) => updateGlmLocalVoiceField(voice.voiceId, 'promptText', (e.target as HTMLInputElement).value)" />
                              </div>
                            </template>

                            <template v-else-if="editingPresetIsQwen3Local">
                              <div class="space-y-2 rounded-lg border border-[var(--color-border-subtle)] bg-surface-overlay px-3 py-3">
                                <div class="text-xs font-medium text-[var(--color-text-secondary)]">添加 Qwen3 音色</div>
                                <input v-model="qwen3LocalVoiceDraft.voiceId" type="text" class="input input-sm w-full font-mono" placeholder="音色 ID（唯一标识；无参考音频时作为 speaker 传给 custom_voice）" />
                                <input v-model="qwen3LocalVoiceDraft.name" type="text" class="input input-sm w-full" placeholder="显示名称（可选）" />
                                <input v-model="qwen3LocalVoiceDraft.promptAudioPath" type="text" class="input input-sm w-full font-mono" placeholder="参考音频路径（wav/flac 绝对路径，语音克隆时填写）" />
                                <input v-model="qwen3LocalVoiceDraft.promptText" type="text" class="input input-sm w-full" placeholder="参考音频对应转写文本（语音克隆时推荐填写）" />
                                <input v-model="qwen3LocalVoiceDraft.instruction" type="text" class="input input-sm w-full" placeholder="instruction（可选，仅 custom_voice 模式）" />
                                <p class="text-[10px] text-[var(--color-text-muted)]">参考音频与转写走第二端口上的 Base 网关（/voice_clone）；仅 speaker 走主端口 CustomVoice（/custom_voice）。路径为本机绝对路径。</p>
                                <button
                                  type="button"
                                  class="btn btn-sm btn-primary w-full"
                                  :disabled="!qwen3LocalVoiceDraft.voiceId.trim()"
                                  @click="addQwen3LocalVoice"
                                >添加音色</button>
                              </div>

                              <div v-for="voice in editingPresetVoiceCatalog" :key="'detail-qwen-' + voice.voiceId" class="space-y-1 rounded-lg border border-[var(--color-border-subtle)] bg-surface-overlay/60 px-3 py-2 text-xs">
                                <div class="font-medium text-[var(--color-text-secondary)]">{{ voice.voiceId }}</div>
                                <input :value="voice.name" type="text" class="input input-sm w-full text-[10px]" placeholder="显示名称" @change="(e) => updateQwen3LocalVoiceField(voice.voiceId, 'name', (e.target as HTMLInputElement).value)" />
                                <input :value="voice.promptAudioPath ?? ''" type="text" class="input input-sm w-full font-mono text-[10px]" placeholder="参考音频路径" @change="(e) => updateQwen3LocalVoiceField(voice.voiceId, 'promptAudioPath', (e.target as HTMLInputElement).value)" />
                                <input :value="voice.promptText ?? ''" type="text" class="input input-sm w-full text-[10px]" placeholder="参考转写文本" @change="(e) => updateQwen3LocalVoiceField(voice.voiceId, 'promptText', (e.target as HTMLInputElement).value)" />
                                <input :value="voice.instruction ?? ''" type="text" class="input input-sm w-full text-[10px]" placeholder="instruction（可选）" @change="(e) => updateQwen3LocalVoiceField(voice.voiceId, 'instruction', (e.target as HTMLInputElement).value)" />
                              </div>
                            </template>

                            <template v-else-if="editingPresetIsOmniVoiceLocal">
                              <div class="space-y-2 rounded-lg border border-[var(--color-border-subtle)] bg-surface-overlay px-3 py-3">
                                <div class="text-xs font-medium text-[var(--color-text-secondary)]">添加 OmniVoice 音色条目</div>
                                <input v-model="omniVoiceLocalVoiceDraft.voiceId" type="text" class="input input-sm w-full font-mono" placeholder="音色 ID（用于会话里选择）" />
                                <input v-model="omniVoiceLocalVoiceDraft.name" type="text" class="input input-sm w-full" placeholder="显示名称（可选）" />
                                <input v-model="omniVoiceLocalVoiceDraft.promptAudioPath" type="text" class="input input-sm w-full font-mono" placeholder="参考音频路径（克隆模式，可选）" />
                                <input v-model="omniVoiceLocalVoiceDraft.promptText" type="text" class="input input-sm w-full" placeholder="参考音频转写文本（克隆模式，可选）" />
                                <input v-model="omniVoiceLocalVoiceDraft.instruction" type="text" class="input input-sm w-full" placeholder="instruction / instruct（音色设计模式，可选）" />
                                <p class="text-[10px] text-[var(--color-text-muted)]">优先级为：参考音频可读则走克隆；否则有 instruction 走音色设计；两者都留空时仅按文本自动生成音色。</p>
                                <button
                                  type="button"
                                  class="btn btn-sm btn-primary w-full"
                                  :disabled="!omniVoiceLocalVoiceDraft.voiceId.trim()"
                                  @click="addOmniVoiceLocalVoice"
                                >添加音色</button>
                              </div>

                              <div v-for="voice in editingPresetVoiceCatalog" :key="'detail-omnivoice-' + voice.voiceId" class="space-y-1 rounded-lg border border-[var(--color-border-subtle)] bg-surface-overlay/60 px-3 py-2 text-xs">
                                <div class="font-medium text-[var(--color-text-secondary)]">{{ voice.voiceId }}</div>
                                <input :value="voice.name" type="text" class="input input-sm w-full text-[10px]" placeholder="显示名称" @change="(e) => updateOmniVoiceLocalVoiceField(voice.voiceId, 'name', (e.target as HTMLInputElement).value)" />
                                <input :value="voice.promptAudioPath ?? ''" type="text" class="input input-sm w-full font-mono text-[10px]" placeholder="参考音频路径（可选）" @change="(e) => updateOmniVoiceLocalVoiceField(voice.voiceId, 'promptAudioPath', (e.target as HTMLInputElement).value)" />
                                <input :value="voice.promptText ?? ''" type="text" class="input input-sm w-full text-[10px]" placeholder="参考转写文本（可选）" @change="(e) => updateOmniVoiceLocalVoiceField(voice.voiceId, 'promptText', (e.target as HTMLInputElement).value)" />
                                <input :value="voice.instruction ?? ''" type="text" class="input input-sm w-full text-[10px]" placeholder="instruction / instruct（可选）" @change="(e) => updateOmniVoiceLocalVoiceField(voice.voiceId, 'instruction', (e.target as HTMLInputElement).value)" />
                              </div>
                            </template>

                            <!-- 非 glm_local：保留原有的手动添加 + 克隆 + 设计 -->
                            <template v-else>
                              <div class="flex flex-col gap-3">
                                <div class="space-y-2 rounded-lg border border-[var(--color-border-subtle)] bg-surface-overlay px-3 py-3">
                                  <div class="text-xs font-medium text-[var(--color-text-secondary)]">音色快速复刻</div>
                                <div class="flex flex-wrap gap-2">
                                  <button type="button" class="btn btn-xs btn-secondary" @click="pickTtsCloneSourceFile">选择源音频</button>
                                  <span class="text-[10px] text-[var(--color-text-muted)]">{{ ttsCloneSourceFile?.name || '未选择文件' }}</span>
                                </div>
                                <input ref="ttsCloneSourceInputRef" type="file" class="hidden" accept=".mp3,.wav,.m4a" @change="onTtsCloneSourceChange" />
                                <input v-model="ttsCloneDraft.voiceId" type="text" class="input input-sm w-full" placeholder="voice_id" />
                                <ModernSelect
                                  v-model="ttsCloneDraft.model"
                                  :options="ttsSessionModelOptions"
                                  searchable
                                  allow-create
                                  :placeholder="editingPresetTtsProvider === 'glm' ? '复刻模型（可选，默认 glm-tts-clone）' : '试听模型（可选）'"
                                  @select="(option) => { ttsCloneDraft.model = option.value }"
                                />
                                <textarea v-model="ttsCloneDraft.previewText" rows="2" class="input textarea w-full resize-y" :placeholder="editingPresetTtsProvider === 'glm' ? '试听文本（GLM 必填，留空则后端用默认试听文案）' : '试听文本（可选）'"></textarea>
                                <div v-if="editingPresetSupportsPromptAudio" class="flex flex-wrap gap-2">
                                  <button type="button" class="btn btn-xs btn-secondary" @click="pickTtsClonePromptFile">选择示例音频</button>
                                  <span class="text-[10px] text-[var(--color-text-muted)]">{{ ttsClonePromptFile?.name || '可选' }}</span>
                                </div>
                                <input v-if="editingPresetSupportsPromptAudio" ref="ttsClonePromptInputRef" type="file" class="hidden" accept=".mp3,.wav,.m4a" @change="onTtsClonePromptChange" />
                                <input v-model="ttsCloneDraft.promptText" type="text" class="input input-sm w-full" :placeholder="editingPresetTtsProvider === 'glm' ? '示例音频文本（可选）' : '示例音频对应文本（可选）'" />
                                <div v-if="editingPresetSupportsPromptAudio" class="flex flex-wrap gap-4 text-xs text-[var(--color-text-secondary)]">
                                  <button type="button" class="inline-flex items-center gap-2 transition-colors hover:text-[var(--color-text)]" @click="ttsCloneDraft.needNoiseReduction = !ttsCloneDraft.needNoiseReduction">
                                    <ThemedCheckbox :checked="ttsCloneDraft.needNoiseReduction" />
                                    <span>降噪</span>
                                  </button>
                                  <button type="button" class="inline-flex items-center gap-2 transition-colors hover:text-[var(--color-text)]" @click="ttsCloneDraft.needVolumeNormalization = !ttsCloneDraft.needVolumeNormalization">
                                    <ThemedCheckbox :checked="ttsCloneDraft.needVolumeNormalization" />
                                    <span>音量归一</span>
                                  </button>
                                </div>
                                <p v-if="editingPresetTtsProvider === 'glm'" class="text-[11px] text-[var(--color-text-muted)]">GLM 复刻会使用上传的源音频作为样本；额外示例音频与降噪/归一化参数不适用。</p>
                                <button type="button" class="btn btn-sm btn-primary w-full" :disabled="ttsCloneLoading" @click="submitTtsClone">{{ ttsCloneLoading ? '复刻中...' : '复刻并试听' }}</button>
                                <audio v-if="ttsClonePreviewUrl" :src="ttsClonePreviewUrl" controls class="w-full"></audio>
                              </div>

                              <div v-if="editingPresetSupportsVoiceDesign" class="space-y-2 rounded-lg border border-[var(--color-border-subtle)] bg-surface-overlay px-3 py-3">
                                <div class="text-xs font-medium text-[var(--color-text-secondary)]">音色设计</div>
                                <textarea v-model="ttsDesignDraft.prompt" rows="3" class="input textarea w-full resize-y" placeholder="用自然语言描述想要的声音"></textarea>
                                <textarea v-model="ttsDesignDraft.previewText" rows="2" class="input textarea w-full resize-y" placeholder="试听文本"></textarea>
                                <input v-model="ttsDesignDraft.voiceId" type="text" class="input input-sm w-full" placeholder="voice_id（可选，不填则自动生成）" />
                                <button type="button" class="btn btn-sm btn-primary w-full" :disabled="ttsDesignLoading" @click="submitTtsDesign">{{ ttsDesignLoading ? '设计中...' : '生成并试听' }}</button>
                                <audio v-if="ttsDesignPreviewUrl" :src="ttsDesignPreviewUrl" controls class="w-full"></audio>
                              </div>

                              <div v-else class="rounded-lg border border-dashed border-[var(--color-border-subtle)] bg-surface-overlay px-3 py-3 text-xs text-[var(--color-text-muted)]">
                                GLM TTS 暂不支持音色设计，当前仅支持音色列表、上传与音色复刻。
                              </div>
                            </div>
                            </template>
                          </div>
                       </div>
                  </div>
                  <div v-else class="flex min-h-[12rem] flex-1 items-center justify-center text-[var(--color-text-muted)] text-sm">
                      选择或创建一个预设
                  </div>
              </div>
          </div>

          <!-- Chat Specific Settings -->
          <div v-if="chatTabEverOpened" v-show="tab === 'chat'" class="space-y-6">
            <div v-if="!chat" class="text-center text-[var(--color-text-muted)] py-8">请先选择一个会话</div>
            <div v-else-if="chatDraft && globalDraft" class="space-y-5">
               <div class="text-xs text-[var(--color-text-muted)] bg-surface-muted p-3 rounded-lg border border-[var(--color-border-subtle)]">
                这些设置仅应用于当前会话，并会覆盖全局设置。模型选择将自动关联对应的 API 预设。
              </div>

              <div class="space-y-2">
                <div class="flex items-center justify-between gap-3">
                  <label class="block text-sm font-medium text-[var(--color-text-secondary)]">会话系统提示</label>
                  <div class="relative inline-flex shrink-0 gap-1 rounded-lg border border-[var(--color-border-subtle)] bg-surface-muted p-1">
                    <div
                      class="pointer-events-none absolute left-1 top-1 bottom-1 rounded-md bg-brand shadow-sm transition-transform duration-[400ms] ease-out"
                      :style="{
                        width: 'calc((100% - 0.75rem) / 2)',
                        transform: `translateX(calc(${chatDraft.sessionSystemPromptMode === 'override' ? 1 : 0} * (100% + 0.25rem)))`,
                      }"
                    />
                    <button
                      type="button"
                      class="relative z-10 min-w-[4.25rem] flex-1 rounded-md px-2 py-1 text-center text-xs font-medium transition-colors duration-[400ms] ease-out touch-manipulation"
                      :class="
                        chatDraft.sessionSystemPromptMode === 'append'
                          ? 'text-[var(--color-on-brand)]'
                          : 'text-[var(--color-text-muted)] hover:text-[var(--color-text-secondary)]'
                      "
                      @click="chatDraft.sessionSystemPromptMode = 'append'"
                    >追加全局</button>
                    <button
                      type="button"
                      class="relative z-10 min-w-[4.25rem] flex-1 rounded-md px-2 py-1 text-center text-xs font-medium transition-colors duration-[400ms] ease-out touch-manipulation"
                      :class="
                        chatDraft.sessionSystemPromptMode === 'override'
                          ? 'text-[var(--color-on-brand)]'
                          : 'text-[var(--color-text-muted)] hover:text-[var(--color-text-secondary)]'
                      "
                      @click="chatDraft.sessionSystemPromptMode = 'override'"
                    >覆盖全局</button>
                  </div>
                </div>
                <p class="text-xs text-[var(--color-text-muted)]">
                  追加全局会保留全局系统提示并在后面附加本会话内容；覆盖全局会在本会话提示非空时跳过全局系统提示。
                </p>
                <textarea 
                  v-model="chatDraft.prompt" 
                  rows="4"
                  placeholder="留空则使用角色默认提示词"
                  class="input textarea w-full resize-y"
                ></textarea>
              </div>

              <div class="space-y-1.5">
                <div class="flex items-center justify-between gap-4">
                  <label class="block text-sm font-medium text-[var(--color-text-secondary)]">长期记忆</label>
                  <div class="text-right text-xs text-[var(--color-text-secondary)] shrink-0">
                    <div>记忆长度估算：{{ memoryTokenDisplay }} tokens</div>
                    <div>对话长度估算：{{ chatTokenDisplay }} tokens</div>
                    <div v-if="messagesSinceLastMemoryUpdate != null && tokensSinceLastMemoryUpdate != null" class="text-[var(--color-text-muted)]">
                      距离上次保存记忆已过去了：~{{ messagesSinceLastMemoryUpdate }} 条消息，约 {{ tokensSinceLastMemoryUpdate }} tokens
                    </div>
                  </div>
                </div>
                <div class="flex items-center gap-2 pb-1">
                  <button class="btn btn-xs btn-secondary" @click="hideSavedFloors">从已存记忆处截断</button>
                  <button class="btn btn-xs btn-secondary" @click="resetHiddenFloors">恢复完整上下文</button>
                  <span v-if="chatDraft.contextStartMessageId" class="text-xs text-[var(--color-text-muted)]">
                    当前已设置上下文起点
                  </span>
                </div>
                <textarea 
                  v-model="chatDraft.longTermMemory"
                  rows="4"
                  placeholder="会插入系统提示词，留空则不启用"
                  class="input textarea w-full resize-y"
                ></textarea>
                <div class="flex flex-wrap items-end gap-3 pt-1">
                  <div class="space-y-1 min-w-[12rem] flex-1">
                    <label class="block text-xs font-medium text-[var(--color-text-secondary)]">每隔几条消息自动总结</label>
                    <input
                      :value="chatDraft.autoMemorySummaryEveryN ?? ''"
                      type="number"
                      min="1"
                      step="1"
                      placeholder="关闭"
                      class="input w-full"
                      @input="onAutoMemorySummaryEveryNInput"
                    />
                  </div>
                  <label class="flex items-center gap-2 cursor-pointer select-none pb-1.5 shrink-0">
                    <ThemedCheckbox
                      :checked="chatDraft.autoMemorySummarySilent === true"
                      @update:checked="setAutoMemorySummarySilent"
                    />
                    <span class="text-sm text-[var(--color-text-secondary)]">静默总结</span>
                  </label>
                </div>
                <p class="text-xs text-[var(--color-text-muted)]">
                  关闭「静默总结」时，达到阈值会先询问；若拒绝则下次在 n×2、n×3… 条时再问。达到条件时若主聊仍在生成回复，会等生成结束后再判断。
                </p>
              </div>

               <div class="space-y-1.5">
                <label class="block text-sm font-medium text-[var(--color-text-secondary)]">模型覆盖</label>
                <ModernSelect
                  v-model="chatDraft.params.model"
                  :selected-preset-id="chatDraft?.presetId ?? null"
                  :options="chatModelOptions"
                  searchable
                  allow-create
                  placeholder="选择模型 (自动关联预设)..."
                  @select="handleChatModelSelect"
                />
                <div v-if="chatDraft?.presetId" class="text-xs text-brand mt-1 flex items-center gap-1">
                    <span>🔗 已关联 API 预设:</span>
                    <span class="font-bold">{{ globalDraft?.apiPresets.find(p => p.id === chatDraft?.presetId)?.name || '未知预设' }}</span>
                </div>
              </div>

               <div class="grid grid-cols-2 gap-4">
                <div class="space-y-1.5">
                  <label class="block text-sm font-medium text-[var(--color-text-secondary)]">Temperature</label>
                  <input 
                    v-model.number="chatDraft.params.temperature" 
                    type="number" 
                    step="0.1" min="0" max="2"
                    placeholder="使用全局"
                    class="input w-full"
                  />
                </div>
                <div class="space-y-1.5">
                  <label class="block text-sm font-medium text-[var(--color-text-secondary)]">Top P</label>
                  <input 
                    v-model.number="chatDraft.params.top_p" 
                    type="number" 
                    step="0.1" min="0" max="1"
                    placeholder="使用全局"
                    class="input w-full"
                  />
                </div>
                <div class="space-y-1.5">
                  <label class="block text-sm font-medium text-[var(--color-text-secondary)]">最大输出长度</label>
                  <input 
                    v-model.number="chatDraft.params.max_tokens" 
                    type="number" 
                    step="128" min="1"
                    placeholder="使用全局"
                    class="input w-full"
                  />
                </div>
              </div>
              <div class="space-y-2">
                <div class="text-sm font-medium text-[var(--color-text-secondary)]">上下文</div>
                <div class="grid grid-cols-2 gap-4">
                <div class="space-y-1.5">
                  <label class="block text-sm font-medium text-[var(--color-text-secondary)]">上下文长度</label>
                  <input 
                    v-model.number="chatDraft.params.context_size" 
                    type="number" 
                    min="0"
                    placeholder="未启用（使用全局）"
                    class="input w-full"
                  />
                </div>
                  <div class="space-y-1.5">
                    <label class="block text-sm font-medium text-[var(--color-text-secondary)]">草稿助手上下文条数限制</label>
                    <input
                      :value="chatDraft.draftHelp?.context_message_limit ?? ''"
                      type="text"
                      inputmode="numeric"
                      pattern="[0-9]*"
                      placeholder="使用全局；留空则继续回退"
                      class="input w-full"
                      @input="handleChatDraftHelpLimitInput"
                    />
                  </div>
                </div>
              </div>
              <p class="text-xs text-[var(--color-text-muted)] mt-2">实际上下文总限制长度为该「上下文长度」限制加上角色卡、用户信息、自定义系统提示词。草稿助手优先使用当前会话的条数限制，其次全局，最后回退到现有上下文逻辑。</p>

              <div class="space-y-2">
                <div class="flex flex-wrap items-center justify-between gap-2">
                  <div class="text-sm font-medium text-[var(--color-text-secondary)]">世界书</div>
                  <template v-if="!worldBookCreateExpanded">
                    <button type="button" class="btn btn-xs btn-secondary" @click="worldBookCreateExpanded = true">
                      新建世界书
                    </button>
                  </template>
                  <div v-else class="flex flex-wrap items-center gap-2 justify-end flex-1 min-w-0">
                    <input
                      v-model="worldBookNewNameDraft"
                      type="text"
                      class="input input-sm flex-1 min-w-[140px] max-w-[240px]"
                      placeholder="世界书名称"
                      @keydown.enter.prevent="confirmCreateWorldBook"
                    />
                    <button type="button" class="btn btn-xs btn-primary" @click="confirmCreateWorldBook">创建</button>
                    <button type="button" class="btn btn-xs btn-secondary" @click="cancelWorldBookCreate">取消</button>
                  </div>
                </div>
                <div class="rounded-lg border border-[var(--color-border-subtle)] bg-surface-muted p-3 text-xs text-[var(--color-text-muted)]">
                  全局激活的世界书会自动对当前会话生效；你也可以把世界书仅绑定到当前会话。会话内顺序用于预算淘汰优先级（靠后更先被丢弃）。
                </div>
                <div class="flex items-center gap-2">
                  <ModernSelect
                    v-model="addWorldBookId"
                    :options="worldBookAddOptions"
                    placeholder="选择世界书加入会话顺序..."
                    class="flex-1"
                  />
                  <button class="btn btn-sm btn-secondary" @click="addWorldBookToOrder">加入顺序</button>
                </div>
                <div class="drawer-scroll max-h-[180px] space-y-2 overflow-y-auto rounded-lg border border-[var(--color-border-subtle)] bg-surface-overlay p-2">
                  <div
                    v-for="book in currentChatWorldbooks"
                    :key="book.id"
                    class="rounded-lg border border-[var(--color-border-subtle)] bg-surface-muted p-2"
                  >
                    <div class="flex items-center justify-between gap-2">
                      <div class="text-sm text-[var(--color-text)]">
                        {{ book.name }}
                        <span v-if="book.globalActive" class="ml-1 text-xs text-brand">{{
                          (chatDraft?.worldBookGlobalExclusions || []).includes(book.id)
                            ? '（全局，该会话禁用）'
                            : '（全局）'
                        }}</span>
                      </div>
                      <div class="flex items-center gap-1">
                        <button class="btn btn-xs btn-secondary" @click="setWorldBookGlobalActive(book, !book.globalActive)">
                          {{ book.globalActive ? '改为会话' : '设为全局' }}
                        </button>
                        <button class="btn btn-xs btn-secondary" @click="detachWorldBookFromCurrentChat(book)">移除会话</button>
                        <button class="btn btn-xs btn-secondary" @click="openWorldBookEditor(book.id)">编辑</button>
                      </div>
                    </div>
                  </div>
                  <div v-if="currentChatWorldbooks.length === 0" class="text-xs text-[var(--color-text-muted)]">
                    当前会话暂无已激活世界书。
                  </div>
                </div>
                <div class="rounded-lg border border-[var(--color-border-subtle)] bg-surface-overlay overflow-hidden">
                  <button
                    type="button"
                    class="w-full flex items-center justify-between gap-2 px-3 py-2 text-left text-xs font-medium text-[var(--color-text-secondary)] hover:bg-surface-muted transition-colors"
                    @click="toggleAllWorldBooksSection"
                  >
                    <span>全部世界书（{{ worldbooks.length }} 本）</span>
                    <span class="text-[var(--color-text-muted)]">{{ allWorldBooksSectionOpen ? '收起' : '展开' }}</span>
                  </button>
                  <div v-show="allWorldBooksSectionOpen" class="px-2 pb-2 space-y-1.5 border-t border-[var(--color-border-subtle)] pt-2">
                    <div
                      v-for="book in worldBooksListVisible"
                      :key="book.id"
                      class="flex items-center justify-between gap-2 rounded-md border border-[var(--color-border-subtle)] bg-surface-muted px-2 py-1.5"
                    >
                      <div class="min-w-0 flex-1">
                        <div class="text-xs text-[var(--color-text)] truncate">{{ book.name || book.id }}</div>
                        <div class="text-[10px] text-[var(--color-text-muted)] leading-tight mt-0.5">
                          {{ worldbookTokenHint(book.id) }}
                        </div>
                      </div>
                      <button type="button" class="btn btn-xs btn-secondary shrink-0" @click="openWorldBookEditor(book.id)">
                        编辑
                      </button>
                    </div>
                    <div v-if="worldbooks.length === 0" class="text-xs text-[var(--color-text-muted)] px-1 py-1">暂无世界书。</div>
                    <div v-else-if="worldbooks.length > 5" class="flex justify-center pt-1">
                      <button type="button" class="btn btn-xs btn-secondary" @click="allWorldBooksListExpanded = !allWorldBooksListExpanded">
                        {{ allWorldBooksListExpanded ? '收起列表' : `展开全部（${worldbooks.length} 本）` }}
                      </button>
                    </div>
                  </div>
                </div>
                <div class="space-y-1 rounded-lg border border-[var(--color-border-subtle)] bg-surface-overlay p-2">
                  <div class="text-xs text-[var(--color-text-muted)]">会话世界书顺序</div>
                  <p class="text-[10px] text-[var(--color-text-muted)] mb-1 leading-snug">
                    拖动条目或用上移/下移调整顺序（预算淘汰时靠后的书先被丢弃）。扫描深度与插入深度在「编辑」中设置（按会话）。
                  </p>
                  <div
                    v-for="(att, idx) in (chatDraft.worldBookAttachments || [])"
                    :key="`${att.worldBookId}-${idx}`"
                    class="flex items-center justify-between gap-2 rounded-md border border-[var(--color-border-subtle)] bg-surface-muted px-2 py-1 transition-all"
                    :class="worldBookOrderDraggingIdx === idx ? 'opacity-50 border-brand-a50' : ''"
                    draggable="true"
                    @dragstart="handleWorldBookOrderDragStart(idx)"
                    @dragover="handleWorldBookOrderDragOver($event, idx)"
                    @dragend="handleWorldBookOrderDragEnd"
                  >
                    <div class="flex min-w-0 flex-1 items-center gap-1.5">
                      <span class="shrink-0 cursor-grab text-[var(--color-text-muted)] active:cursor-grabbing" aria-hidden="true">
                        <GripVertical class="w-4 h-4" />
                      </span>
                      <div class="flex min-w-0 flex-1 flex-col gap-0.5">
                        <span class="truncate text-xs text-[var(--color-text)]">{{ idx + 1 }}. {{ worldBookName(att.worldBookId) }}</span>
                        <div class="text-[10px] text-[var(--color-text-muted)] leading-tight">
                          扫描：{{ scanDepthDisplay(att.scanDepth) }}　深度：{{ att.insertDepth ?? 5 }}
                        </div>
                      </div>
                    </div>
                    <div class="flex shrink-0 flex-wrap items-center gap-1 justify-end">
                      <button type="button" class="btn btn-xs btn-secondary" @click.stop="openSessionAttachEdit(idx)">编辑</button>
                      <button type="button" class="btn btn-xs btn-secondary" @click.stop="moveWorldBookOrder(att.worldBookId, -1)">上移</button>
                      <button type="button" class="btn btn-xs btn-secondary" @click.stop="moveWorldBookOrder(att.worldBookId, 1)">下移</button>
                      <button type="button" class="btn btn-xs btn-secondary" @click.stop="clearWorldBookSessionActivationById(att.worldBookId)">删除</button>
                    </div>
                  </div>
                </div>
              </div>

              <div class="space-y-3 rounded-xl border border-[var(--color-border-subtle)] bg-surface-muted/35 p-4">
                <div class="flex items-center justify-between gap-3">
                  <div>
                    <div class="text-sm font-medium text-[var(--color-text-secondary)]">文字转语音</div>
                    <p class="mt-1 text-xs text-[var(--color-text-muted)]">
                      会话级 TTS 设置挂在世界书之后保存；自动朗读范围使用“角色 / 用户 / 全部”语义。
                    </p>
                  </div>
                  <span
                    class="shrink-0 whitespace-nowrap rounded-full px-2 py-1 text-[11px] font-medium"
                    :class="globalDraft.ttsEnabled ? 'bg-brand-a20 text-brand' : 'bg-surface-overlay text-[var(--color-text-muted)]'"
                  >
                    {{ globalDraft.ttsEnabled ? '启用' : '禁用' }}
                  </span>
                </div>

                <div
                  class="space-y-3"
                  :class="globalDraft.ttsEnabled ? '' : 'opacity-55 pointer-events-none select-none'"
                >
                  <div v-if="!globalDraft.ttsEnabled" class="rounded-lg border border-dashed border-[var(--color-border-subtle)] bg-surface-overlay px-3 py-2 text-xs text-[var(--color-text-muted)]">
                    请先在“全局设置 → 文字转语音（TTS）”里开启 TTS，当前会话配置才会生效。
                  </div>

                  <div class="space-y-1.5">
                    <label class="block text-sm font-medium text-[var(--color-text-secondary)]">TTS 模型</label>
                    <ModernSelect
                      v-model="chatDraft.tts!.model"
                      :selected-preset-id="chatDraft.tts?.presetId ?? null"
                      :options="ttsSessionModelOptions"
                      searchable
                      allow-create
                      placeholder="选择 TTS 模型..."
                      :disabled="!globalDraft.ttsEnabled || ttsSessionModelOptions.length === 0"
                      @select="updateChatTtsModel"
                    />
                    <p class="text-xs text-[var(--color-text-muted)]">
                      先选模型，预设会自动关联到对应的 TTS 服务。
                      <span v-if="selectedChatTtsPreset" class="text-brand">当前预设：{{ selectedChatTtsPreset.name }} · {{ selectedChatTtsProvider === 'glm_local' ? 'GLM-TTS（本地）' : selectedChatTtsProvider === 'qwen3_local' ? 'Qwen3-TTS（本地）' : selectedChatTtsProvider === 'omnivoice_local' ? 'OmniVoice（本地）' : selectedChatTtsProvider === 'glm' ? 'GLM TTS' : 'MiniMax' }}</span>
                    </p>
                    <p v-if="ttsSessionModelOptions.length === 0" class="text-xs text-[var(--color-text-muted)]">
                      还没有可用的 TTS 模型。请先在 API 预设中把目标预设标记为 TTS 服务并获取模型列表。
                    </p>
                  </div>

                  <div class="space-y-2">
                    <div class="text-sm font-medium text-[var(--color-text-secondary)]">自动朗读范围</div>
                    <div class="relative inline-flex w-full gap-1 rounded-lg border border-[var(--color-border-subtle)] bg-surface-muted p-1">
                      <div
                        class="pointer-events-none absolute left-1 top-1 bottom-1 rounded-md bg-brand shadow-sm transition-transform duration-[400ms] ease-out"
                        :style="{
                          width: 'calc((100% - 1.25rem) / 4)',
                          transform: `translateX(calc(${Math.max(0, TTS_AUTO_READ_OPTIONS.findIndex((option) => option.value === (chatDraft!.tts?.autoReadScope ?? 'off')))} * (100% + 0.25rem)))`,
                        }"
                      />
                      <button
                        v-for="option in TTS_AUTO_READ_OPTIONS"
                        :key="option.value"
                        type="button"
                        class="relative z-10 min-h-[2.25rem] flex-1 rounded-md px-2 py-1 text-xs font-medium transition-colors duration-[400ms] ease-out"
                        :class="(chatDraft.tts?.autoReadScope ?? 'off') === option.value ? 'text-[var(--color-on-brand)]' : 'text-[var(--color-text-muted)] hover:text-[var(--color-text-secondary)]'"
                        @click="updateChatTtsAutoReadScope(option.value as AutoReadScope)"
                      >
                        {{ option.label }}
                      </button>
                    </div>
                  </div>

                  <div class="space-y-1.5">
                    <label class="block text-sm font-medium text-[var(--color-text-secondary)]">朗读间隔（秒）</label>
                    <input
                      type="number"
                      min="0"
                      step="0.1"
                      class="input w-full"
                      :value="chatDraft.tts?.readGapSeconds ?? 0"
                      @input="updateChatTtsReadGapSeconds(($event.target as HTMLInputElement).value)"
                    />
                  </div>

                  <div class="space-y-2 rounded-lg border border-[var(--color-border-subtle)] bg-surface-overlay px-3 py-3">
                    <div class="text-sm font-medium text-[var(--color-text-secondary)]">文本后处理</div>
                    <div class="flex flex-wrap gap-4 text-xs text-[var(--color-text-secondary)]">
                      <button type="button" class="inline-flex items-center gap-2 transition-colors hover:text-[var(--color-text)]" @click="updateChatTtsPreprocessEnabled(!(chatDraft.tts?.preprocessEnabled === true))">
                        <ThemedCheckbox :checked="chatDraft.tts?.preprocessEnabled === true" />
                        <span>启用文本后处理</span>
                      </button>
                      <button type="button" class="inline-flex items-center gap-2 transition-colors hover:text-[var(--color-text)]" :disabled="!(chatDraft.tts?.preprocessEnabled === true) || selectedChatTtsProvider !== 'minimax'" @click="updateChatTtsInjectEmotionTags(!(chatDraft.tts?.injectEmotionTags === true))">
                        <ThemedCheckbox :checked="chatDraft.tts?.injectEmotionTags === true" :disabled="!(chatDraft.tts?.preprocessEnabled === true) || selectedChatTtsProvider !== 'minimax'" />
                        <span>注入英文情绪标签</span>
                      </button>
                    </div>
                    <div v-if="chatDraft.tts?.preprocessEnabled" class="space-y-1.5">
                      <label class="block text-xs font-medium text-[var(--color-text-secondary)]">后处理目标语言</label>
                      <input
                        type="text"
                        class="input w-full"
                        :value="chatDraft.tts?.preprocessTargetLanguage ?? ''"
                        placeholder="例如 简体中文、English（留空则不按语言翻译）"
                        @input="updateChatTtsPreprocessTargetLanguage(($event.target as HTMLInputElement).value)"
                      />
                    </div>
                    <ModernSelect
                      v-if="chatDraft.tts?.preprocessEnabled"
                      v-model="chatDraft.tts!.preprocessModel"
                      :selected-preset-id="chatDraft.tts?.preprocessPresetId ?? null"
                      :options="ttsPreprocessModelOptions"
                      searchable
                      allow-create
                      placeholder="选择文本后处理模型..."
                      :disabled="ttsPreprocessModelOptions.length === 0"
                      @select="updateChatTtsPreprocessModel"
                    />
                    <p class="text-xs text-[var(--color-text-muted)]">
                      后处理请求会以 JSON 发送 language、raw_text、inject_emotion_tags；目标语言同时写入提示词占位符。留空则不翻译。模型从普通文本预设里选；英文情绪标签仅对 MiniMax TTS 生效。
                    </p>
                  </div>

                  <div class="space-y-2">
                    <div class="text-sm font-medium text-[var(--color-text-secondary)]">角色音色</div>
                    <div v-if="currentChatCharacterVoiceRows.length" class="space-y-2">
                      <div
                        v-for="row in currentChatCharacterVoiceRows"
                        :key="row.id"
                        class="grid items-center gap-2 rounded-lg border border-[var(--color-border-subtle)] bg-surface-overlay px-3 py-2 md:grid-cols-[minmax(0,11rem)_1fr]"
                      >
                        <div class="flex min-h-8 items-center text-xs text-[var(--color-text-secondary)]">{{ row.name }}</div>
                        <TtsVoiceInput
                          :model-value="getCharacterVoiceValue(row.id)"
                          :voices="availableTtsVoices"
                          placeholder="输入或下拉选择 voice_id"
                          @update:model-value="updateCharacterVoiceValue(row.id, $event)"
                        />
                      </div>
                    </div>
                    <div v-else class="text-xs text-[var(--color-text-muted)]">当前会话没有可配置的角色。</div>
                  </div>

                  <div class="space-y-2">
                    <div class="text-sm font-medium text-[var(--color-text-secondary)]">用户音色</div>
                    <div v-if="currentChatPersonaVoiceRows.length" class="space-y-2">
                      <div
                        v-for="row in currentChatPersonaVoiceRows"
                        :key="row.id"
                        class="grid items-center gap-2 rounded-lg border border-[var(--color-border-subtle)] bg-surface-overlay px-3 py-2 md:grid-cols-[minmax(0,11rem)_1fr]"
                      >
                        <div class="flex min-h-8 items-center text-xs text-[var(--color-text-secondary)]">{{ row.name }}</div>
                        <TtsVoiceInput
                          :model-value="getPersonaVoiceValue(row.id)"
                          :voices="availableTtsVoices"
                          placeholder="输入或下拉选择 voice_id"
                          @update:model-value="updatePersonaVoiceValue(row.id, $event)"
                        />
                      </div>
                    </div>
                    <div
                      v-else-if="chat && !chat.userPersonaId"
                      class="text-xs text-[var(--color-text-muted)]"
                    >
                      当前会话未绑定用户身份，请先在侧栏选择用户身份后再配置音色。
                    </div>
                    <div v-else class="text-xs text-[var(--color-text-muted)]">当前没有可用的用户身份音色入口。</div>
                    <p v-if="availableTtsVoices.length === 0" class="text-xs text-[var(--color-text-muted)]">
                      当前预设还没有已拉取的音色列表。你可以回到 API 预设里点击「从 API 获取并筛选」勾选音色，也可以直接手输 voice_id。
                    </p>
                  </div>
                </div>
              </div>

              <!-- Group Member Settings (Removed, moved to independent GroupSettingsModal) -->

            </div>
          </div>
        </div>

        <div class="shrink-0 flex justify-end gap-3 border-t border-[var(--color-border-subtle)] px-6 py-4 bg-[var(--color-border-subtle)] rounded-b-2xl">
          <button
            type="button"
            class="inline-flex min-h-11 items-center justify-center px-5 py-2 text-[var(--color-text-muted)] transition-colors hover:text-[var(--color-text)] touch-manipulation whitespace-nowrap"
            :disabled="isSaving"
            @click="close"
          >
            取消
          </button>
          <button
            type="button"
            class="inline-flex min-h-11 items-center justify-center rounded-lg bg-brand px-6 py-2 font-medium text-on-brand shadow-brand transition-all touch-manipulation hover:bg-brand-hover whitespace-nowrap"
            :disabled="isSaving"
            @click="handleSaveAll"
          >
            {{ isSaving ? '保存中...' : '保存设置' }}
          </button>
        </div>
      </div>
  </div>

  <!-- Model Selector Modal（Teleport 到 body 避免被父级 flex/窄容器限制宽度） -->
  <Teleport to="body">
    <div v-if="showModelSelector" class="fixed inset-0 z-[60] flex items-center justify-center">
      <!-- Backdrop -->
      <div class="absolute inset-0 bg-overlay-heavy backdrop-blur-sm" @click="showModelSelector = false"></div>
      
      <!-- Modal -->
      <div class="relative w-full max-w-lg min-w-[400px] glass-panel rounded-2xl shadow-2xl flex flex-col max-h-[85vh] m-4">
      <div class="p-4 border-b border-[var(--color-border)] flex justify-between items-center bg-surface-muted rounded-t-2xl">
        <h3 class="font-bold text-[var(--color-text)]">选择模型</h3>
        <button
          type="button"
          class="inline-flex min-h-11 min-w-11 shrink-0 items-center justify-center rounded-lg text-[var(--color-text-muted)] touch-manipulation hover:text-[var(--color-text)]"
          @click="showModelSelector = false"
        >
            <X class="w-5 h-5" />
        </button>
      </div>
      
      <div class="p-3 border-b border-[var(--color-border)] bg-transparent">
        <input 
          v-model="modelSelectorQuery" 
          placeholder="筛选模型..." 
          class="input w-full"
          autoFocus
        />
      </div>
      
      <div class="drawer-scroll flex-1 overflow-y-auto bg-transparent p-2">
        <div v-if="filteredCandidates.length === 0" class="text-center text-[var(--color-text-muted)] py-8 text-sm">
          未找到模型
        </div>
        <div v-else class="space-y-1">
          <div 
            v-for="m in filteredCandidates" 
            :key="m"
            class="flex min-h-11 cursor-pointer items-center gap-3 rounded-lg px-3 py-2 transition-colors hover:bg-surface-muted touch-manipulation"
            @click="toggleCandidate(m)"
          >
            <div 
              class="w-4 h-4 rounded border flex items-center justify-center transition-colors"
              :class="selectedCandidateModels.has(m) ? 'bg-brand border-brand' : 'border-[var(--color-border)]'"
            >
              <Check v-if="selectedCandidateModels.has(m)" class="text-on-brand w-2.5 h-2.5" />
            </div>
            <span class="text-sm text-[var(--color-text-secondary)]" :class="selectedCandidateModels.has(m) ? 'text-[var(--color-text)] font-medium' : ''">{{ m }}</span>
          </div>
        </div>
      </div>
      
      <div class="p-4 border-t border-[var(--color-border)] flex justify-between items-center bg-surface-muted rounded-b-2xl">
        <div class="text-xs text-[var(--color-text-muted)]">已选 {{ selectedCandidateModels.size }} 个模型</div>
        <div class="flex gap-2">
          <button type="button" class="inline-flex min-h-11 items-center justify-center px-4 py-2 text-sm text-[var(--color-text-muted)] touch-manipulation transition-colors hover:text-[var(--color-text)]" @click="showModelSelector = false">取消</button>
          <button type="button" class="inline-flex min-h-11 items-center justify-center rounded-lg bg-brand px-4 py-2 text-sm text-on-brand shadow-brand transition-all touch-manipulation hover:bg-brand-hover" @click="saveModelSelection">确认</button>
        </div>
      </div>
    </div>
  </div>
  </Teleport>

  <Teleport to="body">
    <div v-if="showVoiceSelector" class="fixed inset-0 z-[60] flex items-center justify-center">
      <div class="absolute inset-0 bg-overlay-heavy backdrop-blur-sm" @click="showVoiceSelector = false"></div>

      <div class="relative m-4 flex max-h-[85vh] min-h-0 w-full max-w-lg min-w-[400px] flex-col rounded-2xl glass-panel shadow-2xl">
        <div class="flex items-center justify-between rounded-t-2xl border-b border-[var(--color-border)] bg-surface-muted p-4">
          <h3 class="font-bold text-[var(--color-text)]">选择音色</h3>
          <button
            type="button"
            class="inline-flex min-h-11 min-w-11 shrink-0 items-center justify-center rounded-lg text-[var(--color-text-muted)] touch-manipulation hover:text-[var(--color-text)]"
            @click="showVoiceSelector = false"
          >
            <X class="w-5 h-5" />
          </button>
        </div>

        <div class="border-b border-[var(--color-border)] bg-transparent p-3">
          <input v-model="voiceSelectorQuery" placeholder="筛选音色（名称、ID、类型）..." class="input w-full" autofocus />
        </div>

        <div class="drawer-scroll min-h-0 flex-1 overflow-y-auto bg-transparent p-2">
          <div v-if="filteredVoiceCandidates.length === 0" class="py-8 text-center text-sm text-[var(--color-text-muted)]">
            未找到音色
          </div>
          <div v-else class="space-y-1">
            <div
              v-for="v in filteredVoiceCandidates"
              :key="v.voiceId"
              class="flex min-h-11 cursor-pointer items-center gap-3 rounded-lg px-3 py-2 transition-colors hover:bg-surface-muted touch-manipulation"
              @click="toggleCandidateVoice(v.voiceId)"
            >
              <div
                class="flex h-4 w-4 shrink-0 items-center justify-center rounded border transition-colors"
                :class="selectedCandidateVoiceIds.has(v.voiceId) ? 'border-brand bg-brand' : 'border-[var(--color-border)]'"
              >
                <Check v-if="selectedCandidateVoiceIds.has(v.voiceId)" class="h-2.5 w-2.5 text-on-brand" />
              </div>
              <div class="min-w-0 flex-1">
                <div
                  class="truncate text-sm text-[var(--color-text-secondary)]"
                  :class="selectedCandidateVoiceIds.has(v.voiceId) ? 'font-medium text-[var(--color-text)]' : ''"
                >
                  {{ v.name }}
                </div>
                <div class="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[11px] text-[var(--color-text-muted)]">
                  <span class="font-mono truncate">{{ v.voiceId }}</span>
                  <span
                    class="shrink-0 rounded-full bg-surface-muted px-1.5 py-0.5 text-[10px] text-[var(--color-text-muted)]"
                  >{{ v.voiceType }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div class="flex items-center justify-between rounded-b-2xl border-t border-[var(--color-border)] bg-surface-muted p-4">
          <div class="text-xs text-[var(--color-text-muted)]">已选 {{ selectedCandidateVoiceIds.size }} 个音色</div>
          <div class="flex gap-2">
            <button
              type="button"
              class="inline-flex min-h-11 items-center justify-center px-4 py-2 text-sm text-[var(--color-text-muted)] touch-manipulation transition-colors hover:text-[var(--color-text)]"
              @click="showVoiceSelector = false"
            >
              取消
            </button>
            <button
              type="button"
              class="inline-flex min-h-11 items-center justify-center rounded-lg bg-brand px-4 py-2 text-sm text-on-brand shadow-brand transition-all touch-manipulation hover:bg-brand-hover"
              @click="saveVoiceSelection"
            >
              确认
            </button>
          </div>
        </div>
      </div>
    </div>
  </Teleport>

  <WorldBookEditorModal
    :show="showWorldBookEditor"
    :world-book-id="worldBookEditorId"
    @update:show="(v) => (showWorldBookEditor = v)"
    @saved="loadWorldBooks"
    @deleted="onWorldBookEditorDeleted"
  />

  <WorldBookSessionAttachModal
    :show="sessionAttachModalShow"
    :book-name="sessionAttachModalBookName"
    :scan-depth="sessionAttachModalScan ?? null"
    :insert-depth="sessionAttachModalInsert"
    :scan-depth-default="globalDraft?.worldBookEntryScanDepthDefault ?? null"
    @update:show="(v) => (sessionAttachModalShow = v)"
    @save="onSessionAttachSave"
  />
  </div>
</template>

<style scoped>
.drawer-wrapper {
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.3s ease-out;
}
.drawer-wrapper.is-open {
  opacity: 1;
  pointer-events: auto;
}
.drawer-wrapper .drawer-panel {
  transition: transform 0.3s ease-out;
  transform: translateX(calc(100% + 1.5rem));
}
.drawer-wrapper.is-open .drawer-panel {
  transform: translateX(0);
}
.drawer-wrapper .drawer-backdrop {
  opacity: 0.4;
}
.drawer-wrapper:not(.is-open) .drawer-backdrop {
  opacity: 0;
}

.custom-scrollbar::-webkit-scrollbar {
  width: 4px;
}
.custom-scrollbar::-webkit-scrollbar-track {
  background: transparent;
}
.custom-scrollbar::-webkit-scrollbar-thumb {
  background: var(--color-border);
  border-radius: 2px;
}
.custom-scrollbar:hover::-webkit-scrollbar-thumb {
  background: var(--color-border-strong);
}

/* 触摸：纵向滚动更顺手，减少与页面手势冲突；iOS 惯性滚动 */
.drawer-scroll {
  touch-action: pan-y;
  -webkit-overflow-scrolling: touch;
  overscroll-behavior-y: contain;
  scrollbar-gutter: stable;
}
</style>
