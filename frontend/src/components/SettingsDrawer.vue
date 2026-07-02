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
 *    - 导入：见 script 顶部 import（含 ModernSelect、LlmPresetNameCombobox、世界书/WebGPU 等 modal、api/http 与 update、若干 composables 与 utils）；API 预设「选择模型」多选弹窗在模板内以 Teleport 实现，非独立子组件
 *    - 依赖：依赖vue、stores、api/http.ts
 *    - 位置：组件层，提供设置管理功能
 */
import { computed, onMounted, onUnmounted, provide, reactive, ref, watch, type ComponentPublicInstance } from 'vue'
import { useChatsStore, useCharactersStore, useMvuStore, useSettingsStore } from '../stores'
import { isChatMvuRuntimeEnabled } from '../utils/groupMvu'
import { countActiveEntities, countRelations } from '../utils/kgVisNetwork'
import {
  normalizeReasoningEffort,
  normalizeThemeId,
  type AutoReadScope,
  type ApiPreset,
  type ApiPresetVoice,
  type Chat,
  type ChatContentRegexRule,
  type ChatMvuMode,
  type ChatOverrides,
  type KnowledgeGraphBeforeLastRole,
  type KnowledgeGraphInjectPosition,
  type Settings,
  type MvuMode,
  type StateVariables,
  type StatusTableDef,
  type TtsProvider,
  type TtsSessionConfig,
  type WorldBook,
  type WorldBookAttachment,
} from '../types/models'
import { apiDelete, apiGet, apiPost, apiPostFormData, apiPut } from '../api/http'
import { downloadUpdate, getManualUpdateCheck, runUpdate } from '../api/update'
import { useAppFont } from '../composables/useAppFont'
import { useViewportNarrowPortrait } from '../composables/useViewportNarrowPortrait'
import { usePageBackground } from '../composables/usePageBackground'
import { useSettingsImport } from '../composables/useSettingsImport'
import {
  useWebGpuBackgroundRuntime,
  readWebGpuDraftSource,
  writeWebGpuDraftSource,
} from '../composables/useWebGpuBackgroundRuntime'
import { X } from 'lucide-vue-next'
import WorldBookEditorModal from './modals/WorldBookEditorModal.vue'
import WebGpuShaderEditorModal from './modals/WebGpuShaderEditorModal.vue'
import WorldBookSessionAttachModal from './modals/WorldBookSessionAttachModal.vue'
import HttpLogViewerModal from './modals/HttpLogViewerModal.vue'
import SettingsDrawerModelSelectorModal from './settings-drawer/SettingsDrawerModelSelectorModal.vue'
import SettingsDrawerVoiceSelectorModal from './settings-drawer/SettingsDrawerVoiceSelectorModal.vue'
import SettingsDrawerRegexRuleEditorModal from './settings-drawer/SettingsDrawerRegexRuleEditorModal.vue'
import SettingsDrawerGlobalWebSearchSection from './settings-drawer/SettingsDrawerGlobalWebSearchSection.vue'
import SettingsDrawerGlobalConnectionSection from './settings-drawer/SettingsDrawerGlobalConnectionSection.vue'
import SettingsDrawerGlobalPromptsSection from './settings-drawer/SettingsDrawerGlobalPromptsSection.vue'
import SettingsDrawerGlobalAppearanceSection from './settings-drawer/SettingsDrawerGlobalAppearanceSection.vue'
import SettingsDrawerGlobalTtsSection from './settings-drawer/SettingsDrawerGlobalTtsSection.vue'
import SettingsDrawerGlobalAppSection from './settings-drawer/SettingsDrawerGlobalAppSection.vue'
import SettingsDrawerPresetsTab from './settings-drawer/SettingsDrawerPresetsTab.vue'
import SettingsDrawerChatTab from './settings-drawer/SettingsDrawerChatTab.vue'
import { isTtsApiPreset, resolveTtsProvider } from '../utils/apiPresetKind'
import { normalizeVoiceCatalog } from '../utils/voiceCatalog'
import { useSettingsDrawerPresetListHeight } from '../composables/useSettingsDrawerPresetListHeight'
import { SETTINGS_DRAWER_PRESETS_KEY } from '../composables/settingsDrawerPresetsKey'
import { SETTINGS_DRAWER_CHAT_KEY } from '../composables/settingsDrawerChatKey'
import { getWebGpuUnavailableMessage, probeWebGpuAdapter } from '../utils/webgpuProbe'
import type { WebGpuUnavailableReason } from '../utils/webgpuProbe'
import { concatEnabledWorldBookContents, countTokensForText } from '../utils/tokenEstimate'
import { normalizeWgslSource } from '../utils/normalizeWgslSource'
import { applyContentRegexDisplay } from '../utils/contentRegex'
import {
  compilationMessagesToDiagnostics,
  filterDiagnosticsBySeverity,
  type WgslDiagnostic,
} from '../utils/wgslCompilation'
import { notifyConfirm, notifyMessage } from '../composables/useNotify'
import type { LlmProviderPreset } from '../constants/llmProviderPresets'
import { useDialogBehavior } from '../composables/useDialogBehavior'
import { dialogAria } from '../utils/uiPrimitives'

const { applyFont } = useAppFont()
const { isNarrowPortrait } = useViewportNarrowPortrait()

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
  (e: 'open-knowledge-graph'): void
  (e: 'restore-chat-selection', chatId: string): void
}>()

const drawerTitleId = 'settings-drawer-title'
const drawerA11yAttrs = dialogAria(drawerTitleId)

const { dialogRef: drawerDialogRef } = useDialogBehavior(() => props.show, () => {
  void close()
}, {
  closeOnEscape: false,
})
void drawerDialogRef

const mvuStore = useMvuStore()

const chatMvuRuntimeEnabled = computed(() => {
  const chat = props.chat
  if (!chat) return false
  return isChatMvuRuntimeEnabled(chat, (id) => charactersStore.list.find((c) => c.id === id))
})

const kgStatsSummary = computed(() => {
  const kg = mvuStore.knowledgeGraph
  const n = countActiveEntities(kg)
  const m = countRelations(kg)
  if (n === 0) return '暂无数据，将由 MVU 自动维护或手动添加'
  return `${n} 个实体 · ${m} 条关系`
})

const settingsStore = useSettingsStore()
const chatsStore = useChatsStore()
const charactersStore = useCharactersStore()
const groupChatMvuAnchorSelectOptions = computed(() => {
  const chat = props.chat
  if (!chat?.isGroup) return [{ label: '（未选择）', value: '' }]
  const ids = [...(chat.memberIds || [])]
  const anchor = chatDraft.value?.groupMvuAnchorCharacterId ?? null
  if (anchor && !ids.includes(anchor)) {
    ids.unshift(anchor)
  }
  return [
    { label: '（未选择）', value: '' },
    ...ids.map((id) => ({
      value: id,
      label: charactersStore.list.find((c) => c.id === id)?.name || id,
    })),
  ]
})
const {
  importSettingsFile,
  previewSillyTavernImport,
  confirmSillyTavernImport,
  refreshDataAfterImport,
  formatImportResultMessage,
} = useSettingsImport()

const tab = ref<'global' | 'presets' | 'chat'>('global')
const preloaded = ref(false)
const chatTabEverOpened = ref(false)
const savedPageBackgroundImage = ref<string | null>(null)
const pendingPageBackgroundUploads = new Set<string>()
const { setRuntime: setWebGpuRuntime, clearRuntime: clearWebGpuRuntime, runtimeState: webgpuRuntimeState } =
  useWebGpuBackgroundRuntime()
const webgpuPresetEditorSource = ref('')
const webgpuPresetSourceDirty = ref(false)
const webgpuPresetCompileDiagnostics = ref<WgslDiagnostic[]>([])
const webgpuPresetCompileMessage = ref<string | null>(null)
const webgpuPresetCompiledHash = ref<string | null>(null)
const webgpuPresetCompileBusy = ref(false)
const webgpuPresetSaveBusy = ref(false)
const webgpuPresetCreateBusy = ref(false)
const webgpuPresetDeleteBusy = ref(false)
const showWebGpuShaderEditorModal = ref(false)
const webgpuAvailability = ref<'unknown' | 'available' | 'unavailable'>('unknown')
const webgpuLastProbeMessage = ref<string | null>(null)

watch(() => props.initialTab, (newTab) => {
  if (newTab) tab.value = newTab
}, { immediate: true })

watch(tab, (t) => {
  if (t === 'chat') chatTabEverOpened.value = true
})

watch(
  () => [tab.value, props.chat?.id, chatMvuRuntimeEnabled.value] as const,
  ([t, chatId, mvuOn]) => {
    if (t === 'chat' && chatId && mvuOn) {
      void mvuStore.fetchKnowledgeGraph(chatId)
    }
  },
)

const worldBookCreateExpanded = ref(false)
const worldBookNewNameDraft = ref('')

/** 全局设置 Tab 内折叠区块（不用原生 details，否则关闭时子树被立刻隐藏，grid 高度过渡无法反复播放） */
const globalAccordionOpen = reactive({
  connection: false,
  webSearch: false,
  prompts: false,
  appearance: false,
  tts: false,
  app: false,
})

const globalDraft = ref<Settings | null>(null)
/** GET /api/web-search/status 缓存（打开全局设置时刷新） */
const webSearchRemoteStatus = ref<Record<string, unknown> | null>(null)
/** 正在刷新用量：不清空已有快照，仅作弱提示与样式 */
const webSearchRemoteStatusFetching = ref(false)
const webSearchStatusFetchSeq = ref(0)
const chatDraft = ref<ChatOverrides | null>(null)
/** 会话设置抽屉里编辑的初始状态栏（顶层 chat.stateVariables.tables） */
const chatStateTablesDraft = ref<StatusTableDef[]>([])
const cleanGlobalDraftSnapshot = ref('')
const cleanChatDraftSnapshot = ref('')
const isSaving = ref(false)
const restoringChatId = ref<string | null>(null)
let chatSwitchConfirmSeq = 0
const savedThemePreviewId = ref(normalizeThemeId(null))
const regexEditorOpen = ref(false)
const regexEditorIndex = ref<number | null>(null)
const regexEditorDraft = ref<ChatContentRegexRule | null>(null)
const chatRegexAccordionOpen = ref(false)
const regexTrialSourceMode = ref<'manual' | 'latest_assistant'>('manual')
const regexTrialSourceOptions = [
  { label: '手动输入', value: 'manual' },
  { label: '最近一条 assistant', value: 'latest_assistant' },
] as const
const regexTrialManualText = ref('')

function ensureWebSearchSettingsShape(s: Settings) {
  if (!s.webSearch) {
    s.webSearch = {
      provider: 'tavily',
      tavily: { apiKey: '' },
      bocha: { apiKey: '', baseUrl: 'https://api.bocha.cn' },
    }
  }
  if (!s.webSearch.provider) s.webSearch.provider = 'tavily'
  if (!s.webSearch.tavily) s.webSearch.tavily = { apiKey: '' }
  if (!s.webSearch.bocha) s.webSearch.bocha = { apiKey: '', baseUrl: 'https://api.bocha.cn' }
  if (!s.webSearch.bocha.baseUrl) s.webSearch.bocha.baseUrl = 'https://api.bocha.cn'
}

function wsRecord(v: unknown): Record<string, unknown> | null {
  return v !== null && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : null
}

function tavilySuccessPayloadUnusable(data: Record<string, unknown>): boolean {
  const key = wsRecord(data.key)
  const account = wsRecord(data.account)
  const keyOk =
    key &&
    typeof key.usage === 'number' &&
    Number.isFinite(key.usage) &&
    typeof key.limit === 'number' &&
    Number.isFinite(key.limit)
  const accountOk =
    account &&
    typeof account.plan_usage === 'number' &&
    Number.isFinite(account.plan_usage) &&
    typeof account.plan_limit === 'number' &&
    Number.isFinite(account.plan_limit)
  return !keyOk && !accountOk
}

/** Tavily 用量偶发返回仅含 raw 的空壳或缺字段；触发一次短延迟重试，减轻「先提示无字段再恢复」的闪烁 */
function webSearchStatusBodyLooksIncomplete(body: Record<string, unknown>): boolean {
  const t = wsRecord(body.tavily)
  if (!t || t.ok !== true) return false
  const data = wsRecord(t.data)
  if (!data) return true
  const keys = Object.keys(data)
  if (keys.length === 0) return true
  if (keys.length === 1 && keys[0] === 'raw') return true
  return tavilySuccessPayloadUnusable(data)
}

async function refreshWebSearchRemoteStatus(): Promise<void> {
  const seq = ++webSearchStatusFetchSeq.value
  webSearchRemoteStatusFetching.value = true
  try {
    let data = await apiGet<Record<string, unknown>>('/api/web-search/status')
    if (seq !== webSearchStatusFetchSeq.value) return
    if (webSearchStatusBodyLooksIncomplete(data)) {
      await new Promise<void>((r) => setTimeout(r, 360))
      if (seq !== webSearchStatusFetchSeq.value) return
      data = await apiGet<Record<string, unknown>>('/api/web-search/status')
      if (seq !== webSearchStatusFetchSeq.value) return
    }
    webSearchRemoteStatus.value = data
  } catch {
    if (seq !== webSearchStatusFetchSeq.value) return
    /* 保留 webSearchRemoteStatus，避免抽屉打开时一闪清空 */
  } finally {
    if (seq === webSearchStatusFetchSeq.value) webSearchRemoteStatusFetching.value = false
  }
}

const regexTrialResult = ref<{
  beforeText: string
  afterText: string
  displayText: string
  changed: boolean
  extractedItems: Array<{ value: string; matchedText: string; ruleId: string }>
} | null>(null)

const showApiKey = ref(false)
const editingPresetId = ref<string | null>(null)
const editingPresetShowApiKey = ref(false)
const presetModelsLoading = ref(false)
const presetVoicesLoading = ref(false)
/** 预设「模型列表」区内多选，仅用于批量删除（非通用 API 工具） */
const presetModelListSelection = ref<Set<string>>(new Set())
const presetVoiceListSelection = ref<Set<string>>(new Set())
const stPendingId = ref('')
const stExpiresAt = ref('')
const stPreview = ref<Awaited<ReturnType<typeof previewSillyTavernImport>>['preview'] | null>(null)
const stEnableMvuCompatibility = ref(false)
const stMvuMode = ref<MvuMode>('regex')
const stPreviewLoading = ref(false)
const stConfirming = ref(false)

const stMvuModeOptions = [
  { label: 'Regex 兼容', value: 'regex' },
  { label: '指令模式', value: 'directive' },
]

const stDetectedMvu = computed(() => {
  const mvu = stPreview.value?.mvu
  return Boolean(mvu?.hasTavernHelper || mvu?.hasRegexScripts || mvu?.characterBookCandidateCount)
})

const stImportConfirmLabel = computed(() => {
  if (!stConfirming.value) return '确认导入 ST 角色'
  return stEnableMvuCompatibility.value && stMvuMode.value === 'directive'
    ? 'MVU Agent 分析中…'
    : '导入中…'
})

function resetStImportPreview() {
  stPendingId.value = ''
  stExpiresAt.value = ''
  stPreview.value = null
  stEnableMvuCompatibility.value = false
  stMvuMode.value = 'regex'
}

async function loadStImportPreviewFromFile(file: File): Promise<void> {
  stPreviewLoading.value = true
  try {
    const result = await previewSillyTavernImport(file)
    stPendingId.value = result.pendingId
    stExpiresAt.value = result.expiresAt
    stPreview.value = result.preview
    stMvuMode.value = result.preview.mvu.suggestedMode || 'regex'
    stEnableMvuCompatibility.value = Boolean(
      result.preview.mvu.hasTavernHelper
      || result.preview.mvu.hasRegexScripts
      || result.preview.mvu.characterBookCandidateCount,
    )
  } finally {
    stPreviewLoading.value = false
  }
}

async function handleStImportPick(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  try {
    await loadStImportPreviewFromFile(file)
  } catch (err) {
    resetStImportPreview()
    await notifyMessage(err instanceof Error ? err.message : String(err))
  } finally {
    input.value = ''
  }
}

async function confirmStImportFromSettings() {
  if (!stPendingId.value) {
    await notifyMessage('请先选择 SillyTavern PNG/JSON 并生成预览。')
    return
  }
  stConfirming.value = true
  try {
    const result = await confirmSillyTavernImport({
      pendingId: stPendingId.value,
      enableMvuCompatibility: stEnableMvuCompatibility.value,
      mvuMode: stMvuMode.value,
    })
    await refreshDataAfterImport()
    await notifyMessage(formatImportResultMessage(result))
    resetStImportPreview()
  } catch (err) {
    await notifyMessage(err instanceof Error ? err.message : String(err))
  } finally {
    stConfirming.value = false
  }
}
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
  { label: 'OpenRouter TTS', value: 'openrouter' },
  { label: '硅基流动', value: 'siliconflow' },
]

function formatTtsProviderLabel(provider: TtsProvider): string {
  switch (provider) {
    case 'glm_local':
      return 'GLM-TTS（本地）'
    case 'qwen3_local':
      return 'Qwen3-TTS（本地）'
    case 'omnivoice_local':
      return 'OmniVoice（本地）'
    case 'glm':
      return 'GLM TTS（智谱）'
    case 'openrouter':
      return 'OpenRouter TTS'
    case 'siliconflow':
      return '硅基流动'
    default:
      return 'MiniMax（兼容）'
  }
}

// --- TTS 缓存统计（打开设置抽屉或开启 TTS 时请求 GET /api/tts/cache/stats，不轮询） ---
const ttsCacheStats = ref<{ usedBytes: number; limitBytes: number; lastPatrolAt: string; prunedFiles: number } | null>(null)
async function fetchTtsCacheStats() {
  try {
    const res = await apiGet<{ usedBytes: number; limitBytes: number; lastPatrolAt: string; prunedFiles: number }>('/api/tts/cache/stats')
    ttsCacheStats.value = res
  } catch { /* ignore when TTS disabled */ }
}
const ttsCachePercent = computed(() => {
  if (!ttsCacheStats.value || !ttsCacheStats.value.limitBytes) return 0
  return Math.min(100, Math.max(0, (ttsCacheStats.value.usedBytes / ttsCacheStats.value.limitBytes) * 100))
})

function toggleGlobalTtsEnabled() {
  if (!globalDraft.value) return
  globalDraft.value.ttsEnabled = !globalDraft.value.ttsEnabled
  if (globalDraft.value.ttsEnabled) void fetchTtsCacheStats()
}

async function clearTtsCacheAndRefresh() {
  await apiDelete('/api/tts/cache/clear')
  await fetchTtsCacheStats()
}

// 打开设置抽屉时从后端获取版本号（仅请求一次）
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
    }
  },
  { immediate: true }
)

// 检查更新
const checkUpdateLoading = ref(false)
const checkUpdateMessage = ref('')

// HTTP 请求查看
const showHttpLogViewer = ref(false)
const fontList = ref<string[]>([])

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

function closeWithoutConfirm() {
  emit('update:show', false)
}

function setDocumentTheme(themeId: string) {
  if (typeof document === 'undefined') return
  const normalized = normalizeThemeId(themeId)
  document.documentElement.setAttribute('data-theme', normalized)
  document.body.setAttribute('data-theme', normalized)
  const appRoot = document.querySelector<HTMLElement>('#app > [data-theme]')
  appRoot?.setAttribute('data-theme', normalized)
}

function restoreSavedThemePreview() {
  setDocumentTheme(savedThemePreviewId.value)
}

function stableDraftString(value: unknown): string {
  return JSON.stringify(value ?? null)
}

function currentGlobalDraftSnapshot(): string {
  return stableDraftString(globalDraft.value)
}

function currentChatDraftSnapshot(): string {
  return stableDraftString({
    overrides: chatDraft.value ? normalizeComparableChatOverrides(chatDraft.value) : null,
    stateTables: chatStateTablesDraft.value,
  })
}

function markDraftsClean() {
  cleanGlobalDraftSnapshot.value = currentGlobalDraftSnapshot()
  cleanChatDraftSnapshot.value = currentChatDraftSnapshot()
}

function isChatDraftDirty(): boolean {
  return currentChatDraftSnapshot() !== cleanChatDraftSnapshot.value
}

const hasUnsavedChanges = computed(() => {
  if (!props.show) return false
  return currentGlobalDraftSnapshot() !== cleanGlobalDraftSnapshot.value || isChatDraftDirty()
})

async function close() {
  if (isSaving.value) return
  if (hasUnsavedChanges.value) {
    const ok = await notifyConfirm({
      title: '放弃未保存更改？',
      message: '设置抽屉中还有未保存的修改。关闭后这些修改会被丢弃。',
      variant: 'danger',
    })
    if (!ok) return
    await deletePendingPageBackgrounds(savedPageBackgroundImage.value)
  }
  closeWithoutConfirm()
}

function hasActiveNotifyHost(): boolean {
  return typeof document !== 'undefined' && document.querySelector('.app-notify-host') !== null
}

function handleDrawerKeydown(event: KeyboardEvent) {
  if (!props.show || event.key !== 'Escape' || hasActiveNotifyHost()) return
  event.preventDefault()
  if (showWebGpuShaderEditorModal.value) {
    showWebGpuShaderEditorModal.value = false
    return
  }
  if (sessionAttachModalShow.value) {
    sessionAttachModalShow.value = false
    return
  }
  if (showWorldBookEditor.value) {
    showWorldBookEditor.value = false
    return
  }
  if (showHttpLogViewer.value) {
    showHttpLogViewer.value = false
    return
  }
  if (regexEditorOpen.value) {
    regexEditorOpen.value = false
    return
  }
  if (showModelSelector.value) {
    showModelSelector.value = false
    return
  }
  if (showVoiceSelector.value) {
    showVoiceSelector.value = false
    return
  }
  void close()
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

async function clearKnowledgeGraph() {
  const chat = props.chat
  if (!chat) return
  const ok = await notifyConfirm({
    title: '清空知识图谱',
    message: '确定清空本会话的知识图谱？此操作不可撤销。',
    variant: 'danger',
  })
  if (!ok) return
  try {
    await apiDelete(`/api/mvu/${chat.id}/knowledge-graph`)
    mvuStore.knowledgeGraph = null
    await notifyMessage('知识图谱已清空')
  } catch (error) {
    await notifyMessage(formatSaveError('清空图谱失败', error))
  }
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
    await saveChatStateVariables()
    markDraftsClean()
    savedThemePreviewId.value = normalizeThemeId(settingsStore.settings?.themeId ?? globalDraft.value?.themeId)
    setDocumentTheme(savedThemePreviewId.value)
    closeWithoutConfirm()
  } catch (error) {
    await notifyMessage(formatSaveError('保存设置失败', error))
  } finally {
    suppressTokenEstimates.value = false
    isSaving.value = false
  }
}

async function saveChatStateVariables() {
  const chat = props.chat
  if (!chat) return
  const draftTables = JSON.parse(JSON.stringify(chatStateTablesDraft.value)) as StatusTableDef[]
  const currentTables: StatusTableDef[] = chat.stateVariables?.tables ?? []
  if (JSON.stringify(draftTables) === JSON.stringify(currentTables)) return
  const stateVariables: StateVariables = {
    version: chat.stateVariables?.version ?? 1,
    updatedAt: new Date().toISOString(),
    source: chat.stateVariables?.source ?? 'chat_assistant',
    tables: draftTables,
  }
  await apiPut(`/api/chats/${chat.id}`, { stateVariables })
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

function normalizeRegexRuleName(name: string | null | undefined, pattern: string): string {
  const trimmed = (name || '').trim()
  if (trimmed) return trimmed
  return (pattern || '').trim().slice(0, 50)
}

function normalizeRegexRule(
  source?: Partial<ChatContentRegexRule> | null,
  fallbackOrder = 0,
): ChatContentRegexRule {
  const pattern = String(source?.pattern || '')
  return {
    id: String(source?.id || crypto.randomUUID()),
    name: normalizeRegexRuleName(source?.name ?? null, pattern) || null,
    enabled: source?.enabled !== false,
    order: Number.isFinite(source?.order as number) ? Number(source!.order) : fallbackOrder,
    pattern,
    action:
      source?.action === 'replace' ||
      source?.action === 'extract' ||
      source?.action === 'extract_and_replace'
        ? source.action
        : 'remove',
    replacement: source?.replacement ?? null,
    matchMode: source?.matchMode === 'first' ? 'first' : 'global',
    extractSource: source?.extractSource === 'capture_group' ? 'capture_group' : 'whole_match',
    extractGroupIndex:
      typeof source?.extractGroupIndex === 'number' &&
      Number.isFinite(source.extractGroupIndex) &&
      source.extractGroupIndex >= 0
        ? Math.floor(source.extractGroupIndex)
        : null,
    scanDepthOverride:
      typeof source?.scanDepthOverride === 'number' &&
      Number.isFinite(source.scanDepthOverride) &&
      source.scanDepthOverride >= 1
        ? Math.floor(source.scanDepthOverride)
        : null,
  }
}

function normalizeRegexRules(
  rules?: Array<Partial<ChatContentRegexRule> | null> | null,
): ChatContentRegexRule[] {
  return (rules || []).map((rule, index) => normalizeRegexRule(rule || {}, index))
}

function normalizeChatMvuMode(raw: unknown): ChatMvuMode {
  if (raw === 'regex' || raw === 'directive') return raw
  return null
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
    contextStartKeepBeforeMessages: normalizePositiveInteger(v?.contextStartKeepBeforeMessages),
    presetId: v?.presetId ?? null,
    pureAiMode: v?.pureAiMode ?? null,
    worldBookIds,
    worldBookAttachments: attachments,
    worldBookGlobalExclusions: [...(v?.worldBookGlobalExclusions || [])],
    contentRegexScanDepthDefault:
      typeof v?.contentRegexScanDepthDefault === 'number' &&
      Number.isFinite(v.contentRegexScanDepthDefault) &&
      v.contentRegexScanDepthDefault >= 1
        ? Math.floor(v.contentRegexScanDepthDefault)
        : 50,
    contentRegexRules: normalizeRegexRules(v?.contentRegexRules as Array<Partial<ChatContentRegexRule> | null>),
    contentRegexEnabledByRuleId: { ...(v?.contentRegexEnabledByRuleId || {}) },
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
    mvuMode: normalizeChatMvuMode(v?.mvuMode),
    mvuDirective: typeof v?.mvuDirective === 'string' ? v.mvuDirective : null,
    groupMvuEnabled: v?.groupMvuEnabled ?? null,
    groupMvuAnchorCharacterId: v?.groupMvuAnchorCharacterId ?? null,
    groupMvuTemplateCharacterId: v?.groupMvuTemplateCharacterId ?? null,
    knowledgeGraphEnabled: v?.knowledgeGraphEnabled ?? null,
    knowledgeGraphInjectPosition: v?.knowledgeGraphInjectPosition ?? null,
    knowledgeGraphInjectDepth:
      typeof v?.knowledgeGraphInjectDepth === 'number' && v.knowledgeGraphInjectDepth >= 0
        ? Math.floor(v.knowledgeGraphInjectDepth)
        : 5,
    knowledgeGraphBeforeLastRole:
      v?.knowledgeGraphBeforeLastRole === 'system' || v?.knowledgeGraphBeforeLastRole === 'user'
        ? v.knowledgeGraphBeforeLastRole
        : 'assistant',
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
  tts.injectEmotionTags = enabled
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

function onLlmPresetSelect(p: LlmProviderPreset) {
  const ep = editingPreset.value
  if (!ep) return
  ep.baseUrl = p.baseUrl
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
          : provider === 'openrouter'
            ? 'openrouter'
            : provider === 'siliconflow'
              ? 'siliconflow'
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
  if (nextProvider === 'openrouter') {
    if (!preset.baseUrl || preset.baseUrl === 'https://api.openai.com') {
      preset.baseUrl = 'https://openrouter.ai/api/v1'
    }
    const seed = 'google/gemini-3.1-flash-tts-preview'
    if (!preset.models.includes(seed)) {
      preset.models = [seed, ...preset.models]
    }
  }
  if (nextProvider === 'siliconflow') {
    if (!preset.baseUrl || preset.baseUrl === 'https://api.openai.com') {
      preset.baseUrl = 'https://api.siliconflow.cn/v1'
    }
    const seed = 'FunAudioLLM/CosyVoice2-0.5B'
    if (!preset.models.includes(seed)) {
      preset.models = [seed, ...preset.models]
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

const WEBGPU_TARGET_FPS_LIST = [12, 24, 30, 45, 60, 90, 120] as const
const WEBGPU_TARGET_FPS_SET = new Set<number>(WEBGPU_TARGET_FPS_LIST)
const webgpuTargetFpsOptions = WEBGPU_TARGET_FPS_LIST.map((n) => ({
  label: `${n} 帧`,
  value: String(n),
}))

function normalizeWebgpuTargetFpsValue(v: unknown): number {
  if (v == null || typeof v !== 'number' || Number.isNaN(v)) return 60
  const rounded = Math.round(v)
  return WEBGPU_TARGET_FPS_SET.has(rounded) ? rounded : 60
}

const webgpuTargetFpsModel = computed({
  get: () => String(normalizeWebgpuTargetFpsValue(globalDraft.value?.webgpuBackgroundTargetFps)),
  set: (raw: string) => {
    if (!globalDraft.value) return
    const n = Number(raw)
    globalDraft.value.webgpuBackgroundTargetFps = normalizeWebgpuTargetFpsValue(Number.isFinite(n) ? n : 60)
  },
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
  target.webgpuBackgroundTargetFps = normalizeWebgpuTargetFpsValue(target.webgpuBackgroundTargetFps ?? null)
}

function buildSourceHash(filename: string, source: string): string {
  return `${filename}:${source.length}:${source.slice(0, 32)}:${source.slice(-32)}`
}

function clearWebgpuCompileUi() {
  webgpuPresetCompileDiagnostics.value = []
  webgpuPresetCompileMessage.value = null
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
    clearWebgpuCompileUi()
    webgpuPresetCompiledHash.value = null
    return
  }
  const preset = webgpuPresets.value.find((item) => item.id === presetId)
  if (!preset) return
  const cached = readWebGpuDraftSource(preset.id)
  if (cached != null) {
    const normalized = normalizeWgslSource(cached)
    if (normalized !== cached) {
      writeWebGpuDraftSource(preset.id, normalized)
    }
    webgpuPresetEditorSource.value = normalized
    webgpuPresetSourceDirty.value = true
    clearWebgpuCompileUi()
    webgpuPresetCompiledHash.value = null
    return
  }
  try {
    const response = await fetch(`/api/shader-presets/${encodeURIComponent(preset.wgslFile)}`, {
      method: 'GET',
      headers: { Accept: 'text/plain' },
    })
    if (!response.ok) throw new Error(await response.text())
    const source = normalizeWgslSource(await response.text())
    webgpuPresetEditorSource.value = source
    webgpuPresetSourceDirty.value = false
    clearWebgpuCompileUi()
    webgpuPresetCompiledHash.value = null
  } catch (error) {
    webgpuPresetEditorSource.value = ''
    webgpuPresetSourceDirty.value = false
    webgpuPresetCompileDiagnostics.value = []
    webgpuPresetCompileMessage.value = error instanceof Error ? error.message : String(error)
  }
}

function onWebGpuEditorInput(value: string) {
  webgpuPresetEditorSource.value = value
  const preset = activeWebgpuPreset.value
  if (!preset) return
  webgpuPresetSourceDirty.value = true
  clearWebgpuCompileUi()
  webgpuPresetCompiledHash.value = null
  writeWebGpuDraftSource(preset.id, value)
}

function ensureWebGpuPresetNameInDraft(presetId: string) {
  if (!globalDraft.value?.webgpuBackgroundPresets) return
  const list = globalDraft.value.webgpuBackgroundPresets
  const idx = list.findIndex((p) => p.id === presetId)
  if (idx < 0) return
  const cur = list[idx]
  if (!cur) return
  if (String(cur.name ?? '').trim()) return
  list[idx] = {
    id: cur.id,
    wgslFile: cur.wgslFile,
    name: `WebGPU 预设 ${idx + 1}`,
  }
}

function openWebGpuShaderEditorForPreset(presetId: string) {
  activeWebgpuPresetId.value = presetId
  ensureWebGpuPresetNameInDraft(presetId)
  showWebGpuShaderEditorModal.value = true
}

async function saveWebGpuPresetSource() {
  const preset = activeWebgpuPreset.value
  if (!preset) return
  webgpuPresetSaveBusy.value = true
  try {
    const normalized = normalizeWgslSource(webgpuPresetEditorSource.value)
    const response = await fetch(`/api/shader-presets/${encodeURIComponent(preset.wgslFile)}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ source: normalized }),
    })
    if (!response.ok) throw new Error(await response.text())
    if (response.status !== 204) {
      await response.json().catch(() => null)
    }
    webgpuPresetEditorSource.value = normalized
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
    clearWebgpuCompileUi()
    webgpuPresetCompileMessage.value =
      webgpuLastProbeMessage.value ?? getWebGpuUnavailableMessage('unknown')
    return
  }
  webgpuPresetCompileBusy.value = true
  clearWebgpuCompileUi()
  try {
    const gpu = navigator.gpu
    if (!gpu) throw new Error('WebGPU unavailable')
    const adapter = await gpu.requestAdapter()
    if (!adapter) throw new Error('WebGPU adapter unavailable')
    const device = await adapter.requestDevice()
    const code = normalizeWgslSource(webgpuPresetEditorSource.value)
    const module = device.createShaderModule({ code })
    const info = await module.getCompilationInfo()
    const all = compilationMessagesToDiagnostics(info.messages)
    const errors = filterDiagnosticsBySeverity(all, 'error')
    if (errors.length > 0) {
      webgpuPresetCompileDiagnostics.value = all
      webgpuPresetCompiledHash.value = null
      return
    }
    webgpuPresetEditorSource.value = code
    if (webgpuPresetSourceDirty.value) {
      writeWebGpuDraftSource(preset.id, code)
    }
    webgpuPresetCompiledHash.value = buildSourceHash(preset.wgslFile, code)
    await notifyMessage('编译通过，可在编辑窗口内点击「运行（仅本次）」应用。')
  } catch (error) {
    webgpuPresetCompiledHash.value = null
    webgpuPresetCompileDiagnostics.value = []
    webgpuPresetCompileMessage.value = error instanceof Error ? error.message : String(error)
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

/** 预设列表：将当前活动预设的已保存 WGSL 应用到主界面（不依赖编辑器内先编译） */
function runWebGpuPresetFromList() {
  const preset = activeWebgpuPreset.value
  if (!preset) return
  setWebGpuRuntime({
    enabled: globalDraft.value?.webgpuBackgroundEnabled === true,
    activePresetId: preset.id,
  })
  void notifyMessage('已应用到主界面（仅运行态，未写入后端）。')
}

/** 同步原始字符串；不在每次 input 时 trim 或回填默认名，否则会打断中文输入法且无法清空 */
function onWebGpuPresetNameInput(value: string) {
  const preset = activeWebgpuPreset.value
  if (!preset || !globalDraft.value?.webgpuBackgroundPresets) return
  const list = globalDraft.value.webgpuBackgroundPresets
  const idx = list.findIndex((p) => p.id === preset.id)
  if (idx < 0) return
  const cur = list[idx]
  if (!cur) return
  list[idx] = { id: cur.id, wgslFile: cur.wgslFile, name: value }
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
    const delUrl = `/api/shader-presets/${encodeURIComponent(preset.wgslFile)}`
    const delRes = await fetch(delUrl, { method: 'DELETE' })
    if (!delRes.ok && delRes.status !== 404) {
      throw new Error(await delRes.text())
    }
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
  window.addEventListener('keydown', handleDrawerKeydown)
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
    savedThemePreviewId.value = normalizeThemeId((s as Settings).themeId)
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
    if (!(s as Settings).contentRegexRuleLibrary) (s as Settings).contentRegexRuleLibrary = []
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
    ensureWebSearchSettingsShape(s as Settings)
    globalDraft.value = s
    setDocumentTheme(normalizeThemeId((s as Settings).themeId))
    await loadWebGpuPresetSource((s as Settings).webgpuBackgroundActivePresetId ?? null)
    chatDraft.value = ensureOverrides(props.chat ? clone(props.chat.overrides) : undefined)
    chatStateTablesDraft.value = cloneStateTables(props.chat?.stateVariables?.tables)
    if (s.ttsEnabled) void fetchTtsCacheStats()

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
    markDraftsClean()

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
  () => globalDraft.value?.themeId,
  (themeId) => {
    if (!props.show || themeId === undefined) return
    setDocumentTheme(normalizeThemeId(themeId))
  },
)

watch(
  () => props.show,
  (open) => {
    if (!open) restoreSavedThemePreview()
  },
)

watch(
  () => [props.show, tab.value] as const,
  async ([open, t]) => {
    if (!open || t !== 'global') return
    await refreshWebSearchRemoteStatus()
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

/** 抽屉已打开时切换当前会话，重载会话草稿，避免群聊 MVU 锚点等字段与 options 错位导致选择器空白 */
watch(
  () => props.chat?.id,
  async (chatId, prevId) => {
    if (!props.show || !chatId || chatId === prevId || !props.chat) return
    if (restoringChatId.value === chatId) {
      restoringChatId.value = null
      return
    }
    if (prevId && isChatDraftDirty()) {
      const seq = ++chatSwitchConfirmSeq
      const ok = await notifyConfirm({
        title: '放弃当前会话设置草稿？',
        message: '当前会话设置还有未保存修改。切换到其他会话前需要先确认是否丢弃这些修改。',
        variant: 'danger',
      })
      if (seq !== chatSwitchConfirmSeq || props.chat?.id !== chatId) return
      if (!ok) {
        restoringChatId.value = prevId
        emit('restore-chat-selection', prevId)
        return
      }
    }
    chatDraft.value = ensureOverrides(clone(props.chat.overrides))
    chatStateTablesDraft.value = cloneStateTables(props.chat.stateVariables?.tables)
    mergeGlobalWorldBooksIntoDraft()
    markDraftsClean()
  },
)

/** SSE / 父级刷新 overrides 时把群 MVU 等字段同步进 chatDraft，防止抽屉显示与服务端错位 */
watch(
  () => [
    props.chat?.overrides?.groupMvuEnabled ?? null,
    props.chat?.overrides?.groupMvuAnchorCharacterId ?? null,
    props.chat?.overrides?.groupMvuTemplateCharacterId ?? null,
    props.chat?.overrides?.mvuMode ?? null,
    props.chat?.overrides?.mvuDirective ?? null,
  ] as const,
  ([gEnabled, gAnchor, gTemplate, mMode, mDirective]) => {
    if (!props.show || !chatDraft.value) return
    if (isChatDraftDirty()) return
    chatDraft.value.groupMvuEnabled = gEnabled as ChatOverrides['groupMvuEnabled']
    chatDraft.value.groupMvuAnchorCharacterId = gAnchor as string | null
    chatDraft.value.groupMvuTemplateCharacterId = gTemplate as string | null
    chatDraft.value.mvuMode = mMode as ChatOverrides['mvuMode']
    chatDraft.value.mvuDirective = mDirective as string | null
    markDraftsClean()
  },
)

function cloneStateTables(tables: StatusTableDef[] | null | undefined): StatusTableDef[] {
  return (tables || []).map((t) => ({
    name: t.name,
    columns: [...t.columns],
    rows: t.rows.map((r) => ({ field: r.field, cells: { ...r.cells } })),
  }))
}

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

const { presetListHeaderRef, presetListMaxHeightPx } = useSettingsDrawerPresetListHeight({
  show: computed(() => props.show),
  tab,
  preloaded,
  drawerScrollRef,
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

const editingPresetIsSiliconflow = computed(() => editingPresetTtsProvider.value === 'siliconflow')

const editingPresetIsOpenrouter = computed(() => editingPresetTtsProvider.value === 'openrouter')

const editingPresetSupportsVoiceDesign = computed(() => editingPresetTtsProvider.value === 'minimax')

const editingPresetSupportsPromptAudio = computed(() => editingPresetTtsProvider.value === 'minimax')

const editingPresetSupportsVoiceFetch = computed(() => !['glm_local', 'qwen3_local', 'omnivoice_local'].includes(editingPresetTtsProvider.value))

const editingPresetBaseUrlPlaceholder = computed(() => {
  if (!editingPreset.value) return 'https://api.openai.com 或 …/v1/chat/completions'
  if (!isTtsPreset(editingPreset.value)) return 'https://api.openai.com 或 …/v1/chat/completions'
  if (editingPresetTtsProvider.value === 'glm_local') return 'http://127.0.0.1:8088'
  if (editingPresetTtsProvider.value === 'qwen3_local') return 'http://127.0.0.1:8080'
  if (editingPresetTtsProvider.value === 'omnivoice_local') return 'http://127.0.0.1:8089'
  if (editingPresetTtsProvider.value === 'openrouter') return 'https://openrouter.ai/api/v1'
  if (editingPresetTtsProvider.value === 'siliconflow') return 'https://api.siliconflow.cn/v1'
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
  if (editingPresetTtsProvider.value === 'openrouter') {
    return '填写 OpenRouter API 根路径，推荐 https://openrouter.ai/api/v1（不含 /audio/speech）。'
  }
  if (editingPresetTtsProvider.value === 'siliconflow') {
    return '填写硅基流动 OpenAI 兼容根路径，通常为 https://api.siliconflow.cn/v1。'
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

function bindPresetListHeader(el: Element | ComponentPublicInstance | null) {
  presetListHeaderRef.value = el instanceof HTMLElement ? el : null
}

function bindTtsCloneSourceInput(el: Element | ComponentPublicInstance | null) {
  ttsCloneSourceInputRef.value = el instanceof HTMLInputElement ? el : null
}

function bindTtsClonePromptInput(el: Element | ComponentPublicInstance | null) {
  ttsClonePromptInputRef.value = el instanceof HTMLInputElement ? el : null
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
    await notifyMessage(provider === 'siliconflow' ? '请填写自定义音色名称（customName）' : '请填写克隆后的 voice_id')
    return
  }
  if (provider === 'siliconflow' && !ttsCloneDraft.previewText.trim()) {
    await notifyMessage('硅基流动上传必须填写参考音频对应文本')
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

provide(
  SETTINGS_DRAWER_PRESETS_KEY,
  reactive({
    globalDraft,
    editingPresetId,
    editingPresetShowApiKey,
    presetModelsLoading,
    presetVoicesLoading,
    presetModelListSelection,
    presetVoiceListSelection,
    presetListMaxHeightPx,
    bindPresetListHeader,
    bindTtsCloneSourceInput,
    bindTtsClonePromptInput,
    apiPresetOrderDraggingIdx,
    glmLocalVoiceDraft,
    qwen3LocalVoiceDraft,
    omniVoiceLocalVoiceDraft,
    ttsCloneSourceFile,
    ttsClonePromptFile,
    ttsCloneLoading,
    ttsClonePreviewUrl,
    ttsCloneDraft,
    ttsDesignLoading,
    ttsDesignPreviewUrl,
    ttsDesignDraft,
    TTS_PROVIDER_OPTIONS,
    editingPreset,
    editingPresetTtsProvider,
    editingPresetIsGlmLocal,
    editingPresetIsQwen3Local,
    editingPresetIsOmniVoiceLocal,
    editingPresetIsSiliconflow,
    editingPresetIsOpenrouter,
    editingPresetSupportsVoiceDesign,
    editingPresetSupportsPromptAudio,
    editingPresetSupportsVoiceFetch,
    editingPresetBaseUrlPlaceholder,
    editingPresetBaseUrlHint,
    editingPresetVoiceCatalog,
    upsertEditingPresetVoiceCatalog,
    ttsSessionModelOptions,
    createPreset,
    deletePreset,
    isTtsPreset,
    setPresetTtsService,
    onLlmPresetSelect,
    onEditingPresetTtsProviderChange,
    handleApiPresetOrderDragStart,
    handleApiPresetOrderDragOver,
    handleApiPresetOrderDragEnd,
    openModelSelector,
    selectAllPresetModelNames,
    clearPresetModelListSelection,
    removeSelectedPresetModelNames,
    clearAllPresetModelNames,
    togglePresetModelListSelection,
    removeSinglePresetModelAt,
    openVoiceSelector,
    selectAllPresetVoices,
    clearPresetVoiceSelection,
    removeSelectedPresetVoices,
    clearAllPresetVoices,
    togglePresetVoiceSelection,
    formatTtsProviderLabel,
    pickTtsCloneSourceFile,
    pickTtsClonePromptFile,
    onTtsCloneSourceChange,
    onTtsClonePromptChange,
    submitTtsClone,
    submitTtsDesign,
    addGlmLocalVoice,
    updateGlmLocalVoiceField,
    addQwen3LocalVoice,
    updateQwen3LocalVoiceField,
    onQwen3VoiceClonePortInput,
    addOmniVoiceLocalVoice,
    updateOmniVoiceLocalVoiceField,
  }),
)

function setChatStateTablesDraft(value: StatusTableDef[]) {
  chatStateTablesDraft.value = value
}

function openKnowledgeGraphFromChatTab() {
  emit('open-knowledge-graph')
}

onUnmounted(() => {
  window.removeEventListener('keydown', handleDrawerKeydown)
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
  (v) => {
    void applyFont(v ?? null).catch(() => {})
  },
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

const globalAvailableModelSet = computed(() => {
  if (!globalDraft.value) return new Set<string>()
  const presets = globalDraft.value.apiPresets
  if (presets && presets.length > 0) {
    return new Set(presets.filter((p) => !isTtsApiPreset(p)).flatMap((p) => p.models || []))
  }
  return new Set(globalDraft.value.llm.modelCandidates || [])
})

/** 全局 MVU 模型下拉：与聊天页模型分组一致（最近使用 / 各预设 / 全局候选） */
const globalMvuModelOptions = computed(() => {
  const options: any[] = []
  if (!globalDraft.value) return []

  const recentModels = (globalDraft.value.llm.usedModels || []).filter((m) =>
    globalAvailableModelSet.value.has(m),
  )
  if (recentModels.length > 0) {
    options.push({
      label: '最近使用',
      options: recentModels.map((m) => {
        let preset = null
        if (globalDraft.value!.apiPresets) {
          preset = globalDraft.value!.apiPresets.find(
            (p) => !isTtsApiPreset(p) && p.models.includes(m),
          )
        }
        return { label: m, value: m, presetId: preset ? preset.id : null }
      }),
    })
  }

  for (const preset of globalDraft.value.apiPresets) {
    if (isTtsApiPreset(preset)) continue
    if (preset.models && preset.models.length > 0) {
      options.push({
        label: preset.name,
        options: preset.models.map((m) => ({ label: m, value: m, presetId: preset.id })),
      })
    }
  }

  if (
    (!globalDraft.value.apiPresets || globalDraft.value.apiPresets.length === 0) &&
    globalDraft.value.llm.modelCandidates &&
    globalDraft.value.llm.modelCandidates.length > 0
  ) {
    options.push({
      label: '全局配置',
      options: globalDraft.value.llm.modelCandidates.map((m) => ({ label: m, value: m, presetId: null })),
    })
  }

  return options
})

function handleGlobalMvuModelSelect(option: { value: string; presetId?: string | null }) {
  if (!globalDraft.value) return
  globalDraft.value.mvuModel = option.value?.trim() || null
}

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
  ensureWebSearchSettingsShape(draft)
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
  globalDraft.value.webgpuBackgroundTargetFps = normalizeWebgpuTargetFpsValue(
    settingsStore.settings?.webgpuBackgroundTargetFps ?? draft.webgpuBackgroundTargetFps,
  )
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
  contextStartKeepBeforeMessages: number | null
  presetId: string | null
  pureAiMode: boolean | null
  worldBookAttachments: Array<{
    worldBookId: string
    scanDepth: number | null
    insertDepth: number
  }>
  worldBookGlobalExclusions: string[]
  contentRegexScanDepthDefault: number
  contentRegexRules: ChatContentRegexRule[]
  contentRegexEnabledByRuleId: Record<string, boolean>
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
  mvuMode: ChatMvuMode
  mvuDirective: string | null
  groupMvuEnabled: boolean | null
  groupMvuAnchorCharacterId: string | null
  groupMvuTemplateCharacterId: string | null
  knowledgeGraphEnabled: boolean | null
  knowledgeGraphInjectPosition: KnowledgeGraphInjectPosition | null
  knowledgeGraphInjectDepth: number
  knowledgeGraphBeforeLastRole: KnowledgeGraphBeforeLastRole
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
    contextStartKeepBeforeMessages: normalizePositiveInteger(overrides.contextStartKeepBeforeMessages),
    presetId: overrides.presetId ?? null,
    pureAiMode: overrides.pureAiMode ?? null,
    worldBookAttachments: (overrides.worldBookAttachments || []).map((attachment) => ({
      worldBookId: attachment.worldBookId,
      scanDepth: attachment.scanDepth ?? null,
      insertDepth: attachment.insertDepth && attachment.insertDepth >= 1 ? attachment.insertDepth : 5,
    })),
    worldBookGlobalExclusions: normalizeWorldBookGlobalExclusions(overrides.worldBookGlobalExclusions),
    contentRegexScanDepthDefault:
      typeof overrides.contentRegexScanDepthDefault === 'number' &&
      Number.isFinite(overrides.contentRegexScanDepthDefault) &&
      overrides.contentRegexScanDepthDefault >= 1
        ? Math.floor(overrides.contentRegexScanDepthDefault)
        : 50,
    contentRegexRules: normalizeRegexRules(overrides.contentRegexRules),
    contentRegexEnabledByRuleId: { ...(overrides.contentRegexEnabledByRuleId || {}) },
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
    mvuMode: normalizeChatMvuMode(overrides.mvuMode),
    mvuDirective: typeof overrides.mvuDirective === 'string' ? overrides.mvuDirective : null,
    groupMvuEnabled: overrides.groupMvuEnabled ?? null,
    groupMvuAnchorCharacterId: overrides.groupMvuAnchorCharacterId ?? null,
    groupMvuTemplateCharacterId: overrides.groupMvuTemplateCharacterId ?? null,
    knowledgeGraphEnabled: overrides.knowledgeGraphEnabled ?? null,
    knowledgeGraphInjectPosition: overrides.knowledgeGraphInjectPosition ?? null,
    knowledgeGraphInjectDepth: overrides.knowledgeGraphInjectDepth ?? 5,
    knowledgeGraphBeforeLastRole: overrides.knowledgeGraphBeforeLastRole ?? 'assistant',
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
  chatDraft.value.contextStartKeepBeforeMessages = source.contextStartKeepBeforeMessages
  chatDraft.value.presetId = source.presetId
  chatDraft.value.pureAiMode = source.pureAiMode
  chatDraft.value.worldBookAttachments = source.worldBookAttachments.map((attachment) => ({ ...attachment }))
  syncWorldBookIdsFromAttachments()
  chatDraft.value.worldBookGlobalExclusions = [...source.worldBookGlobalExclusions]
  chatDraft.value.contentRegexScanDepthDefault = source.contentRegexScanDepthDefault
  chatDraft.value.contentRegexRules = source.contentRegexRules.map((rule) => ({ ...rule }))
  chatDraft.value.contentRegexEnabledByRuleId = { ...source.contentRegexEnabledByRuleId }
  chatDraft.value.params = { ...source.params }
  chatDraft.value.draftHelp = { ...source.draftHelp }
  // 与 ensureOverrides 一致：Comparable 里「全默认」时 tts 为 null，但会话草稿必须始终持有 TtsSessionConfig，避免模板访问 chatDraft.tts.model 崩溃。
  chatDraft.value.tts = ensureTtsSessionConfig(source.tts)
  chatDraft.value.autoMemorySummaryEveryN = source.autoMemorySummaryEveryN
  chatDraft.value.lastAutoMemorySummaryAfterMessageId = source.lastAutoMemorySummaryAfterMessageId
  chatDraft.value.autoMemorySummarySilent = source.autoMemorySummarySilent
  chatDraft.value.autoMemorySummaryNextAskTier = source.autoMemorySummaryNextAskTier
  chatDraft.value.mvuMode = source.mvuMode
  chatDraft.value.mvuDirective = source.mvuDirective
  chatDraft.value.groupMvuEnabled = source.groupMvuEnabled
  chatDraft.value.groupMvuAnchorCharacterId = source.groupMvuAnchorCharacterId
  chatDraft.value.groupMvuTemplateCharacterId = source.groupMvuTemplateCharacterId
  chatDraft.value.knowledgeGraphEnabled = source.knowledgeGraphEnabled
  chatDraft.value.knowledgeGraphInjectPosition = source.knowledgeGraphInjectPosition
  chatDraft.value.knowledgeGraphInjectDepth = source.knowledgeGraphInjectDepth
  chatDraft.value.knowledgeGraphBeforeLastRole = source.knowledgeGraphBeforeLastRole
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

function onContextStartKeepBeforeMessagesInput(e: Event) {
  const input = e.target as HTMLInputElement | null
  if (!chatDraft.value) return
  const raw = (input?.value ?? '').trim()
  if (raw === '') {
    chatDraft.value.contextStartKeepBeforeMessages = null
    return
  }
  const n = Number.parseInt(raw, 10)
  chatDraft.value.contextStartKeepBeforeMessages = Number.isFinite(n) && n >= 2 ? n : null
}

const contentRegexRulesSorted = computed(() => {
  const seen = new Set<string>()
  const rules: (ChatContentRegexRule & { _origin?: string })[] = []

  const globalList = globalDraft.value?.contentRegexRuleLibrary || []
  for (const r of globalList) {
    rules.push({ ...r, _origin: 'global' })
    seen.add(r.id)
  }

  const chatList = chatDraft.value?.contentRegexRules || []
  for (const r of chatList) {
    if (!seen.has(r.id)) {
      rules.push({ ...r, _origin: 'character' })
      seen.add(r.id)
    }
  }

  return rules.sort((a, b) => (a.order - b.order) || a.id.localeCompare(b.id))
})

function openRegexRuleEditor(index: number | null = null) {
  if (!globalDraft.value) return
  regexEditorIndex.value = index
  if (index == null) {
    regexEditorDraft.value = normalizeRegexRule({ order: contentRegexRulesSorted.value.length }, contentRegexRulesSorted.value.length)
  } else {
    const found = contentRegexRulesSorted.value[index]
    regexEditorDraft.value = normalizeRegexRule(found, index)
  }
  regexTrialResult.value = null
  regexEditorOpen.value = true
}

async function removeRegexRule(index: number) {
  if (!globalDraft.value) return
  const list = contentRegexRulesSorted.value
  const target = list[index]
  if (!target) return
  const ok = await notifyConfirm({
    title: '删除规则',
    message: `确定删除规则「${target.name || target.pattern.slice(0, 20) || '未命名'}」？`,
    variant: 'danger',
  })
  if (!ok) return
  globalDraft.value.contentRegexRuleLibrary = list.filter((_, i) => i !== index).map((rule, i) => ({ ...rule, order: i }))
}

function moveRegexRule(index: number, direction: -1 | 1) {
  if (!globalDraft.value) return
  const list = contentRegexRulesSorted.value
  const target = index + direction
  if (target < 0 || target >= list.length) return
  const next = [...list]
  const currentRule = next[index]
  const targetRule = next[target]
  if (!currentRule || !targetRule) return
  next[index] = targetRule
  next[target] = currentRule
  globalDraft.value.contentRegexRuleLibrary = next.map((rule, i) => ({ ...rule, order: i }))
}

function toggleAllRegexRules(enabled: boolean) {
  if (!chatDraft.value) return
  const map = { ...(chatDraft.value.contentRegexEnabledByRuleId || {}) }
  const chatList = chatDraft.value.contentRegexRules || []
  for (const item of contentRegexRulesSorted.value) {
    if ((item as any)._origin === 'character') {
      const found = chatList.find((r) => r.id === item.id)
      if (found) found.enabled = enabled
    } else {
      map[item.id] = enabled
    }
  }
  chatDraft.value.contentRegexEnabledByRuleId = map
}

function setRegexRuleEnabled(index: number, enabled: boolean) {
  const item = contentRegexRulesSorted.value[index]
  if (!item) return
  if ((item as any)._origin === 'character') {
    if (chatDraft.value) {
      const chatList = chatDraft.value.contentRegexRules || []
      const found = chatList.find((r) => r.id === item.id)
      if (found) found.enabled = enabled
    }
    return
  }
  if (!chatDraft.value) return
  const map = { ...(chatDraft.value.contentRegexEnabledByRuleId || {}) }
  map[item.id] = enabled
  chatDraft.value.contentRegexEnabledByRuleId = map
}

function isRegexRuleEnabled(rule: ChatContentRegexRule & { _origin?: string }): boolean {
  if ((rule as any)._origin === 'character') return rule.enabled !== false
  const map = chatDraft.value?.contentRegexEnabledByRuleId || {}
  if (Object.prototype.hasOwnProperty.call(map, rule.id)) return !!map[rule.id]
  return false
}

function regexActionLabel(action?: string | null): string {
  if (action === 'replace') return '替换'
  if (action === 'extract') return '提取'
  if (action === 'extract_and_replace') return '提取并替换显示'
  return '删除'
}

function regexMatchModeLabel(mode?: string | null): string {
  return mode === 'first' ? '首个命中' : '全局命中'
}

function regexExtractSourceLabel(source?: string | null): string {
  return source === 'capture_group' ? '捕获分组' : '整段匹配'
}

let regexDragIndex = -1
function handleRegexRuleDragStart(index: number) {
  regexDragIndex = index
}
function handleRegexRuleDragOver(e: DragEvent, index: number) {
  e.preventDefault()
  if (!chatDraft.value || regexDragIndex < 0 || regexDragIndex === index) return
  if (!globalDraft.value) return
  const list = [...contentRegexRulesSorted.value]
  const [moving] = list.splice(regexDragIndex, 1)
  if (!moving) return
  list.splice(index, 0, moving)
  globalDraft.value.contentRegexRuleLibrary = list.map((rule, i) => ({ ...rule, order: i }))
  regexDragIndex = index
}
function handleRegexRuleDragEnd() {
  regexDragIndex = -1
}

function saveRegexRuleEditor() {
  if (!globalDraft.value || !regexEditorDraft.value) return
  const normalized = normalizeRegexRule(regexEditorDraft.value, regexEditorDraft.value.order)
  const list = [...contentRegexRulesSorted.value]
  if (regexEditorIndex.value == null) {
    list.push(normalized)
  } else {
    list[regexEditorIndex.value] = normalized
  }
  globalDraft.value.contentRegexRuleLibrary = list.map((rule, i) => ({ ...normalizeRegexRule(rule, i), order: i }))
  regexEditorOpen.value = false
}

function runRegexRuleTrial() {
  if (!regexEditorDraft.value) return
  const sourceMode = regexTrialSourceMode.value
  let before = ''
  if (sourceMode === 'latest_assistant') {
    const messages = props.chat?.messages
    if (messages) {
      for (let i = messages.length - 1; i >= 0; i--) {
        const m = messages[i]
        if (m && m.role === 'assistant' && (m.content || '').trim()) {
          before = m.content
          break
        }
      }
    }
  } else {
    before = regexTrialManualText.value || ''
  }
  if (before.length > 10000) before = before.slice(0, 10000)

  const rule = normalizeRegexRule(regexEditorDraft.value, regexEditorDraft.value.order)
  const displayText = applyContentRegexDisplay(before, [rule])
  const changed = displayText !== before

  regexTrialResult.value = {
    beforeText: before,
    afterText: displayText,
    displayText,
    changed,
    extractedItems: [],
  }
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

  // 将全局规则库中所有规则的启用状态显式写入 contentRegexEnabledByRuleId
  if (globalDraft.value?.contentRegexRuleLibrary) {
    const map = { ...(chatDraft.value.contentRegexEnabledByRuleId || {}) }
    for (const rule of globalDraft.value.contentRegexRuleLibrary) {
      if (!Object.prototype.hasOwnProperty.call(map, rule.id)) {
        map[rule.id] = isRegexRuleEnabled(rule)
      }
    }
    chatDraft.value.contentRegexEnabledByRuleId = map
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
      void applyFont(filename).catch(() => {})
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
  const lower = file.name.toLowerCase()

  if (lower.endsWith('.png')) {
    resetStImportPreview()
    try {
      await loadStImportPreviewFromFile(file)
    } catch (err) {
      resetStImportPreview()
      await notifyMessage(err instanceof Error ? err.message : String(err))
    } finally {
      input.value = ''
    }
    return
  }

  if (lower.endsWith('.json')) {
    resetStImportPreview()
    try {
      await loadStImportPreviewFromFile(file)
      input.value = ''
      return
    } catch {
      // 非 ST 角色卡 JSON 时走通用导入
    }
    try {
      const result = await importSettingsFile(file)
      await refreshDataAfterImport()
      await notifyMessage(formatImportResultMessage(result))
    } catch (err) {
      await notifyMessage(err instanceof Error ? err.message : String(err))
    } finally {
      input.value = ''
    }
    return
  }

  try {
    const result = await importSettingsFile(file)
    await refreshDataAfterImport()
    await notifyMessage(formatImportResultMessage(result))
  } catch (err) {
    await notifyMessage(err instanceof Error ? err.message : String(err))
  } finally {
    input.value = ''
  }
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

provide(
  SETTINGS_DRAWER_CHAT_KEY,
  reactive({
    chat: computed(() => props.chat),
    globalDraft,
    chatDraft,
    chatStateTablesDraft,
    setChatStateTablesDraft,
    isNarrowPortrait,
    memoryTokenDisplay,
    chatTokenDisplay,
    messagesSinceLastMemoryUpdate,
    tokensSinceLastMemoryUpdate,
    hideSavedFloors,
    resetHiddenFloors,
    onContextStartKeepBeforeMessagesInput,
    setAutoMemorySummarySilent,
    onAutoMemorySummaryEveryNInput,
    chatModelOptions,
    handleChatModelSelect,
    handleChatDraftHelpLimitInput,
    groupChatMvuAnchorSelectOptions,
    chatMvuRuntimeEnabled,
    kgStatsSummary,
    mvuStore,
    clearKnowledgeGraph,
    openKnowledgeGraph: openKnowledgeGraphFromChatTab,
    chatRegexAccordionOpen,
    contentRegexRulesSorted,
    toggleAllRegexRules,
    openRegexRuleEditor,
    isRegexRuleEnabled,
    setRegexRuleEnabled,
    handleRegexRuleDragStart,
    handleRegexRuleDragOver,
    handleRegexRuleDragEnd,
    regexActionLabel,
    regexMatchModeLabel,
    regexExtractSourceLabel,
    moveRegexRule,
    removeRegexRule,
    worldBookCreateExpanded,
    worldBookNewNameDraft,
    confirmCreateWorldBook,
    cancelWorldBookCreate,
    addWorldBookId,
    worldBookAddOptions,
    addWorldBookToOrder,
    currentChatWorldbooks,
    setWorldBookGlobalActive,
    detachWorldBookFromCurrentChat,
    openWorldBookEditor,
    toggleAllWorldBooksSection,
    allWorldBooksSectionOpen,
    worldbooks,
    worldBooksListVisible,
    worldbookTokenHint,
    allWorldBooksListExpanded,
    worldBookOrderDraggingIdx,
    handleWorldBookOrderDragStart,
    handleWorldBookOrderDragOver,
    handleWorldBookOrderDragEnd,
    worldBookName,
    scanDepthDisplay,
    openSessionAttachEdit,
    moveWorldBookOrder,
    clearWorldBookSessionActivationById,
    TTS_AUTO_READ_OPTIONS,
    ttsSessionModelOptions,
    ttsPreprocessModelOptions,
    selectedChatTtsPreset,
    selectedChatTtsProvider,
    formatTtsProviderLabel,
    updateChatTtsModel,
    updateChatTtsAutoReadScope,
    updateChatTtsReadGapSeconds,
    updateChatTtsPreprocessEnabled,
    updateChatTtsInjectEmotionTags,
    updateChatTtsPreprocessTargetLanguage,
    updateChatTtsPreprocessModel,
    currentChatCharacterVoiceRows,
    getCharacterVoiceValue,
    availableTtsVoices,
    updateCharacterVoiceValue,
    currentChatPersonaVoiceRows,
    getPersonaVoiceValue,
    updatePersonaVoiceValue,
  }),
)
</script>

<template>
  <div>
  <div class="drawer-wrapper fixed inset-0 z-drawer flex justify-end" :class="{ 'is-open': show }">
    <!-- Backdrop -->
    <div
      class="drawer-backdrop absolute inset-0 bg-overlay"
      style="background-clip: unset; -webkit-background-clip: unset; color: transparent;"
      @click="close"
    ></div>

    <!-- Drawer Panel -->
    <div
      ref="drawerDialogRef"
      v-bind="drawerA11yAttrs"
      tabindex="-1"
      class="drawer-panel drawer-surface absolute right-4 top-4 bottom-4 w-[min(500px,calc(100vw-2rem))] border border-[var(--color-border)] rounded-2xl flex flex-col shadow-xl"
    >
        <!-- Header -->
        <div class="flex items-center justify-between px-6 py-4 border-b border-[var(--color-border-subtle)] bg-[var(--color-settings-panel-bg)] rounded-t-2xl">
          <h2 :id="drawerTitleId" class="text-lg text-[var(--color-text)]">设置</h2>
          <button
            type="button"
            class="icon-button min-h-11 min-w-11 shrink-0 touch-manipulation"
            aria-label="关闭设置抽屉"
            @click="close"
          >
            <X class="w-5 h-5" />
          </button>
        </div>

        <!-- Tabs：整块可点；底层滑块平移承载高光，与 gap-1 / px-2 对齐 -->
        <div class="relative flex gap-1 border-b border-[var(--color-border-subtle)] bg-[var(--color-settings-control-bg)] px-2 py-2">
          <div
            class="pointer-events-none absolute left-2 top-2 bottom-2 rounded-lg bg-brand-a10 transition-transform duration-[var(--motion-duration-moderate)] ease-out"
            :style="{
              width: 'calc((100% - 1.5rem) / 3)',
              transform: `translateX(calc(${tab === 'global' ? 0 : tab === 'presets' ? 1 : 2} * (100% + 0.25rem)))`,
            }"
          />
          <button
            v-for="t in ['global', 'presets', 'chat']"
            :key="t"
            type="button"
            class="group relative z-10 flex min-h-11 min-w-0 flex-1 touch-manipulation items-center justify-center px-0.5 py-0.5 text-sm font-medium transition-colors duration-[var(--motion-duration-moderate)]"
            @click="tab = t as any"
          >
            <span
              class="block min-h-10 w-full rounded-lg py-2 text-center transition-colors duration-[var(--motion-duration-moderate)]"
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
          class="drawer-scroll flex-1 min-h-0 min-w-0 overflow-y-auto p-6 custom-scrollbar bg-transparent"
        >
          <!-- Global Settings -->
          <div v-if="preloaded" v-show="tab === 'global'" class="space-y-6">
            <div v-if="!globalDraft" class="text-center text-[var(--color-text-muted)] py-8">加载中...</div>
            <div v-else class="space-y-4">
              <div class="text-xs text-[var(--color-text-muted)] bg-surface-muted p-3 rounded-lg border border-[var(--color-border-subtle)]">
                这里配置全局默认的 API 参数。如果配置了 "API 预设"，建议优先使用预设功能以便管理不同服务商。
              </div>

              <SettingsDrawerGlobalConnectionSection
                v-if="globalDraft"
                v-model:open="globalAccordionOpen.connection"
                v-model:show-api-key="showApiKey"
                :draft="globalDraft"
                :mvu-model-options="globalMvuModelOptions"
                @mvu-model-select="handleGlobalMvuModelSelect"
              />

              <SettingsDrawerGlobalWebSearchSection
                v-if="globalDraft"
                v-model:open="globalAccordionOpen.webSearch"
                :draft="globalDraft"
                :remote-status="webSearchRemoteStatus"
                :remote-status-fetching="webSearchRemoteStatusFetching"
              />

              <SettingsDrawerGlobalPromptsSection
                v-if="globalDraft"
                v-model:open="globalAccordionOpen.prompts"
                :draft="globalDraft"
                @draft-help-limit-input="handleGlobalDraftHelpLimitInput"
              />

              <SettingsDrawerGlobalAppearanceSection
                v-if="globalDraft"
                v-model:open="globalAccordionOpen.appearance"
                v-model:page-background-opacity="pageBackgroundOpacityModel"
                v-model:page-background-blur="pageBackgroundBlurModel"
                v-model:active-webgpu-preset-id="activeWebgpuPresetId"
                v-model:webgpu-target-fps="webgpuTargetFpsModel"
                v-model:font-model="fontModel"
                v-model:message-font-size-model="messageFontSizeModel"
                v-model:st-enable-mvu-compatibility="stEnableMvuCompatibility"
                v-model:st-mvu-mode="stMvuMode"
                :draft="globalDraft"
                :is-narrow-portrait="isNarrowPortrait"
                :page-background-image-url="pageBackground.imageUrl.value"
                :page-background-image-style="pageBackground.imageStyle.value"
                :webgpu-presets="webgpuPresets"
                :webgpu-target-fps-options="webgpuTargetFpsOptions"
                :webgpu-availability="webgpuAvailability"
                :webgpu-has-runtime-override="webgpuRuntimeState.hasOverride"
                :webgpu-preset-source-dirty="webgpuPresetSourceDirty"
                :webgpu-preset-compile-diagnostics-count="webgpuPresetCompileDiagnostics.length"
                :webgpu-preset-compile-message="webgpuPresetCompileMessage"
                :webgpu-preset-create-busy="webgpuPresetCreateBusy"
                :webgpu-preset-delete-busy="webgpuPresetDeleteBusy"
                :font-options="fontOptions"
                :st-preview="stPreview"
                :st-preview-loading="stPreviewLoading"
                :st-detected-mvu="stDetectedMvu"
                :st-mvu-mode-options="stMvuModeOptions"
                :st-pending-id="stPendingId"
                :st-confirming="stConfirming"
                :st-import-confirm-label="stImportConfirmLabel"
                :st-expires-at="stExpiresAt"
                @clear-page-background="clearPageBackground"
                @page-background-file="handlePageBackgroundImport"
                @create-webgpu-preset="createWebGpuPreset"
                @open-webgpu-editor="openWebGpuShaderEditorForPreset"
                @run-webgpu-preset="runWebGpuPresetFromList"
                @delete-webgpu-preset="deleteActiveWebGpuPreset"
                @step-font-size="stepMessageFontSize"
                @font-file="handleFontImport"
                @backup="downloadSettingsBackup"
                @import-file="handleImportChange"
                @st-import-file="handleStImportPick"
                @reset-st-preview="resetStImportPreview"
                @confirm-st-import="confirmStImportFromSettings"
              />

              <SettingsDrawerGlobalTtsSection
                v-if="globalDraft"
                v-model:open="globalAccordionOpen.tts"
                :draft="globalDraft"
                :cache-stats="ttsCacheStats"
                :cache-percent="ttsCachePercent"
                @toggle-enabled="toggleGlobalTtsEnabled"
                @clear-cache="clearTtsCacheAndRefresh"
              />

              <SettingsDrawerGlobalAppSection
                v-model:open="globalAccordionOpen.app"
                :app-version="appVersion"
                :check-update-loading="checkUpdateLoading"
                :check-update-message="checkUpdateMessage"
                @check-update="checkUpdate"
                @open-http-log="showHttpLogViewer = true"
              />
            </div>
          </div>

          <SettingsDrawerPresetsTab v-if="preloaded" v-show="tab === 'presets'" />

          <SettingsDrawerChatTab v-if="chatTabEverOpened" v-show="tab === 'chat'" />
        </div>

        <div class="shrink-0 flex justify-end gap-3 border-t border-[var(--color-border-subtle)] px-6 py-4 bg-[var(--color-settings-panel-bg)] rounded-b-2xl">
          <button
            type="button"
            class="btn btn-secondary min-h-11 whitespace-nowrap"
            :disabled="isSaving"
            @click="close"
          >
            取消
          </button>
          <button
            type="button"
            class="btn btn-primary min-h-11 whitespace-nowrap"
            :disabled="isSaving"
            @click="handleSaveAll"
          >
            {{ isSaving ? '保存中...' : '保存设置' }}
          </button>
        </div>
      </div>
  </div>

  <SettingsDrawerRegexRuleEditorModal
    v-model:show="regexEditorOpen"
    v-model:draft="regexEditorDraft"
    v-model:trial-source-mode="regexTrialSourceMode"
    v-model:trial-manual-text="regexTrialManualText"
    :trial-result="regexTrialResult"
    :trial-source-options="regexTrialSourceOptions"
    @save="saveRegexRuleEditor"
    @run-trial="runRegexRuleTrial"
  />

  <SettingsDrawerModelSelectorModal
    v-model:show="showModelSelector"
    v-model:query="modelSelectorQuery"
    :candidates="filteredCandidates"
    :selected="selectedCandidateModels"
    @toggle="toggleCandidate"
    @confirm="saveModelSelection"
  />

  <SettingsDrawerVoiceSelectorModal
    v-model:show="showVoiceSelector"
    v-model:query="voiceSelectorQuery"
    :candidates="filteredVoiceCandidates"
    :selected="selectedCandidateVoiceIds"
    @toggle="toggleCandidateVoice"
    @confirm="saveVoiceSelection"
  />

  <WebGpuShaderEditorModal
    :show="showWebGpuShaderEditorModal"
    :model-value="webgpuPresetEditorSource"
    :preset-id="activeWebgpuPreset?.id ?? null"
    :preset-name="activeWebgpuPreset?.name ?? ''"
    :disabled="!activeWebgpuPreset"
    :adapter-status="webgpuAvailability"
    :has-runtime-override="webgpuRuntimeState.hasOverride"
    :source-dirty="webgpuPresetSourceDirty"
    :compile-diagnostics="webgpuPresetCompileDiagnostics"
    :compile-message="webgpuPresetCompileMessage"
    :save-disabled="webgpuPresetSaveBusy || !webgpuPresetSourceDirty"
    :compile-disabled="webgpuPresetCompileBusy"
    :run-disabled="!webgpuCanRunFromEditor"
    @update:show="(v) => (showWebGpuShaderEditorModal = v)"
    @update:model-value="onWebGpuEditorInput"
    @update:preset-name="onWebGpuPresetNameInput"
    @compile="compileWebGpuPreset"
    @save="saveWebGpuPresetSource"
    @run="runWebGpuPresetInRuntime"
  />

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

  <HttpLogViewerModal
    :show="showHttpLogViewer"
    @update:show="(v) => (showHttpLogViewer = v)"
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

/* 触摸：纵向滚动更顺手，减少与页面手势冲突；iOS 惯性滚动 */
.drawer-scroll {
  touch-action: pan-y;
  -webkit-overflow-scrolling: touch;
  overscroll-behavior-y: contain;
  scrollbar-gutter: stable;
}

</style>
