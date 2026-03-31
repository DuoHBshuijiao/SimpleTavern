<script setup lang="ts">
/**
 * SettingsDrawer - 设置抽屉组件
 *
 * 组件职责：
 * - 提供应用设置的编辑界面
 * - 管理全局设置（LLM配置、API预设、生成参数等）
 * - 管理聊天覆盖设置（提示词、长期记忆、生成参数等）
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
import { computed, onMounted, ref, watch } from 'vue'
import { useChatsStore, useCharactersStore, useSettingsStore } from '../stores'
import {
  normalizeReasoningEffort,
  normalizeThemeId,
  REASONING_EFFORT_OPTIONS,
  THEME_OPTIONS,
  type ApiPreset,
  type Chat,
  type ChatOverrides,
  type Settings,
  type WorldBook,
  type WorldBookAttachment,
} from '../types/models'
import ModernSelect from './ModernSelect.vue'
import { apiGet, apiPost, apiPut } from '../api/http'
import { useAppFont } from '../composables/useAppFont'
import { useSettingsImport } from '../composables/useSettingsImport'
import { X, Eye, EyeOff, Check, Loader2, GripVertical } from 'lucide-vue-next'
import WorldBookEditorModal from './modals/WorldBookEditorModal.vue'
import WorldBookSessionAttachModal from './modals/WorldBookSessionAttachModal.vue'
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

watch(() => props.initialTab, (newTab) => {
  if (newTab) tab.value = newTab
}, { immediate: true })

watch(tab, (t) => {
  if (t === 'chat') chatTabEverOpened.value = true
})

const worldBookCreateExpanded = ref(false)
const worldBookNewNameDraft = ref('')

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
    }
  },
  { immediate: true }
)

const globalDraft = ref<Settings | null>(null)
const chatDraft = ref<ChatOverrides | null>(null)

const showApiKey = ref(false)
const editingPresetId = ref<string | null>(null)
const editingPresetShowApiKey = ref(false)
const presetModelsLoading = ref(false)
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

// Token 估算（长期记忆 / 对话长度）
const memoryTokenEstimate = ref<number | null>(null)
const chatTokenEstimate = ref<number | null>(null)
const messagesSinceLastMemoryUpdate = ref<number | null>(null)
const tokensSinceLastMemoryUpdate = ref<number | null>(null)
const memoryTokenLoading = ref(false)
const chatTokenLoading = ref(false)
let memoryDebounceTimer: ReturnType<typeof setTimeout> | null = null

/**
 * 关闭抽屉
 *
 * 触发update:show事件，传递false。
 */
function close() {
  emit('update:show', false)
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
  }
}

function ensureDraftHelpDefaults(target?: { context_message_limit?: number | null } | null) {
  return {
    context_message_limit: target?.context_message_limit ?? null,
  }
}

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
    await notifyMessage('当前会话尚未找到“已保存记忆”标记消息，无法执行 hide。')
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
  worldbookTokenTotals.value = {}
  const list = worldbooks.value
  if (list.length === 0) return
  worldbookTokensLoading.value = true
  try {
    const results = await Promise.all(
      list.map(async (b) => {
        const text = concatEnabledWorldBookContents(b)
        const n = await countTokensForText(text)
        return [b.id, n] as const
      }),
    )
    const map: Record<string, number | null> = {}
    for (const [id, n] of results) map[id] = n
    worldbookTokenTotals.value = map
  } finally {
    worldbookTokensLoading.value = false
  }
}

async function loadWorldBooks() {
  try {
    worldbooks.value = await apiGet<WorldBook[]>('/api/worldbooks')
  } catch {
    worldbooks.value = []
  }
  await refreshWorldbookTokenTotals()
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
      (s as Settings).themeId = 'blue'
    } else {
      ;(s as Settings).themeId = normalizeThemeId((s as Settings).themeId as string)
    }
    if (!s.apiPresets) s.apiPresets = []
    if (!(s as Settings).draftHelpDefaults) (s as Settings).draftHelpDefaults = ensureDraftHelpDefaults()
    if (s.selectedFont === undefined) (s as Settings).selectedFont = null
    if ((s as Settings).messageFontSize === undefined) (s as Settings).messageFontSize = null
    if (!s.prompts) {
      s.prompts = { globalSystem: '', globalPrefill: '' }
    } else {
      if (s.prompts.globalSystem === undefined) s.prompts.globalSystem = ''
      if (s.prompts.globalPrefill === undefined) s.prompts.globalPrefill = ''
    }

    globalDraft.value = s
    chatDraft.value = ensureOverrides(props.chat ? clone(props.chat.overrides) : undefined)

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
    if (memoryDebounceTimer) clearTimeout(memoryDebounceTimer)
    memoryDebounceTimer = setTimeout(() => {
      memoryDebounceTimer = null
      if (props.show && tab.value === 'chat') fetchMemoryTokenCount()
    }, 400)
  },
)

watch(
  () => [props.chat?.id, tab.value] as const,
  ([chatId, t]) => {
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
    models: []
  }
  globalDraft.value.apiPresets.push(newPreset)
  editingPresetId.value = newPreset.id
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
  // 从「最近使用」中移除已不在任何预设（或全局候选）中的模型
  const presets = globalDraft.value.apiPresets
  const available = presets.length > 0
    ? new Set(presets.flatMap(p => p.models || []))
    : new Set(globalDraft.value.llm.modelCandidates || [])
  globalDraft.value.llm.usedModels = (globalDraft.value.llm.usedModels || []).filter(m => available.has(m))
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
  const draft = {
    ...globalDraft.value,
    generationDefaults: { ...globalDraft.value.generationDefaults },
    draftHelpDefaults: { ...ensureDraftHelpDefaults(globalDraft.value.draftHelpDefaults) },
  }
  draft.generationDefaults.context_size = normalizeContextSize(draft.generationDefaults.context_size)
  draft.draftHelpDefaults.context_message_limit = normalizePositiveInteger(draft.draftHelpDefaults.context_message_limit)
  await settingsStore.save(draft)
  globalDraft.value.generationDefaults.context_size = draft.generationDefaults.context_size
  globalDraft.value.draftHelpDefaults = draft.draftHelpDefaults
  close()
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
  await loadWorldBooks()
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
  await loadWorldBooks()
}

async function saveChatOverrides() {
  const chat = props.chat
  if (!chat || !chatDraft.value) return
  const draft = {
    ...chatDraft.value,
    params: { ...chatDraft.value.params },
    draftHelp: { ...ensureDraftHelpDefaults(chatDraft.value.draftHelp) },
  }
  draft.params.context_size = normalizeContextSize(draft.params.context_size)
  draft.draftHelp.context_message_limit = normalizePositiveInteger(draft.draftHelp.context_message_limit)
  await chatsStore.updateOverrides(chat.id, draft)
  chatDraft.value.params.context_size = draft.params.context_size
  chatDraft.value.draftHelp = draft.draftHelp

  try {
    await syncWorldBookSessionChatIdsForChat(chat.id, draft.worldBookAttachments || [])
  } catch (e) {
    await notifyMessage('同步世界书会话绑定失败: ' + (e instanceof Error ? e.message : String(e)))
    await loadWorldBooks()
    return
  }

  // 单聊：将当前会话的世界书顺序同步到角色卡 attachedWorldBookIds，便于「含世界书」ZIP 导出一致
  if (!chat.isGroup && chat.characterId) {
    const ordered: string[] = []
    const seen = new Set<string>()
    const wbOrder = (draft.worldBookAttachments || []).map((a) => a.worldBookId)
    for (const id of wbOrder) {
      if (id && !seen.has(id)) {
        seen.add(id)
        ordered.push(id)
      }
    }
    const characterId = chat.characterId
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

  close()
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
    const res = await apiGet<{
      currentVersion: string
      latestVersion: string | null
      hasUpdate: boolean
      tagName: string | null
      zipUrl: string | null
    }>('/api/update/check')
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
      const draft = { ...globalDraft.value, generationDefaults: { ...globalDraft.value.generationDefaults } }
      draft.generationDefaults.context_size = normalizeContextSize(draft.generationDefaults.context_size)
      await settingsStore.save(draft)
    }
    await apiPost('/api/update/download', { tagName: res.tagName })
    checkUpdateMessage.value = '正在启动更新...'
    await apiPost('/api/update/run', {})
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
          <button class="text-[var(--color-text-muted)] hover:text-[var(--color-text)] transition-colors" @click="close">
            <X class="w-5 h-5" />
          </button>
        </div>

        <!-- Tabs -->
        <div class="flex border-b border-[var(--color-border-subtle)] bg-[var(--color-border-subtle)]" style="opacity: 1; color: transparent;">
          <button
            v-for="t in ['global', 'presets', 'chat']"
            :key="t"
            class="flex-1 py-3 text-sm font-medium transition-colors relative"
            :class="tab === t ? 'text-brand bg-brand-a10 rounded-lg' : 'text-[var(--color-text-muted)] hover:text-[var(--color-text)] hover:bg-surface-muted rounded-lg'"
            :style="tab === t ? 'opacity: 1; margin-top: 6px; margin-bottom: 6px;' : 'opacity: 1; margin-top: 6px; margin-bottom: 6px;'"
            @click="tab = t as any"
          >
            {{ t === 'global' ? '全局设置' : t === 'presets' ? 'API 预设' : '当前会话' }}
          </button>
        </div>

        <!-- Content -->
        <div class="flex-1 overflow-y-auto p-6 custom-scrollbar bg-transparent">
          <!-- Global Settings -->
          <div v-if="preloaded" v-show="tab === 'global'" class="space-y-6">
            <div v-if="!globalDraft" class="text-center text-[var(--color-text-muted)] py-8">加载中...</div>
            <div v-else class="space-y-5">
              <div class="text-xs text-[var(--color-text-muted)] bg-surface-muted p-3 rounded-lg border border-[var(--color-border-subtle)]">
                这里配置全局默认的 API 参数。如果配置了 "API 预设"，建议优先使用预设功能以便管理不同服务商。
              </div>

              <!-- Stream Toggle -->
              <div class="space-y-2">
                <label class="block text-sm font-medium text-[var(--color-text-secondary)]">流式传输 (Streaming)</label>
                <button 
                  class="flex items-center gap-3 group cursor-pointer w-full text-left"
                  @click="globalDraft.streamEnabled = !globalDraft.streamEnabled"
                >
                  <div 
                    class="w-10 h-5 rounded-full relative transition-colors duration-200"
                    :class="globalDraft.streamEnabled ? 'bg-brand' : 'bg-[var(--color-track)]'"
                  >
                    <div 
                      class="absolute top-1 w-3 h-3 rounded-full bg-[var(--color-on-brand)] transition-transform duration-200"
                      :class="globalDraft.streamEnabled ? 'left-6' : 'left-1'"
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
                  class="flex items-center gap-3 group cursor-pointer w-full text-left"
                  @click="globalDraft.pureAiMode = !globalDraft.pureAiMode"
                >
                  <div
                    class="w-10 h-5 rounded-full relative transition-colors duration-200"
                    :class="globalDraft.pureAiMode ? 'bg-brand' : 'bg-[var(--color-track)]'"
                  >
                    <div
                      class="absolute top-1 w-3 h-3 rounded-full bg-[var(--color-on-brand)] transition-transform duration-200"
                      :class="globalDraft.pureAiMode ? 'left-6' : 'left-1'"
                    ></div>
                  </div>
                  <span class="text-xs text-[var(--color-text-secondary)]">
                    {{ globalDraft.pureAiMode ? '已开启：不注入用户 Persona，用户发言将以 system 影响世界' : '已关闭：正常对话模式' }}
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
                <p class="text-xs text-[var(--color-text-muted)]">none 为关闭思考；其他档位会开启思考并请求更高推理深度。</p>
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
                <p class="text-xs text-[var(--color-text-muted)]">均为暗色玻璃底 + 柔和强调色，整体保持接近默认蓝色的轻盈阅读体验；未设置时默认蓝色系。</p>
              </div>

              <!-- Base URL -->
              <div class="space-y-1.5">
                <label class="block text-sm font-medium text-[var(--color-text-secondary)]">默认 API Base URL</label>
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
                    class="input w-full pr-10"
                  />
                  <button 
                    class="absolute right-2 top-1/2 -translate-y-1/2 text-[var(--color-text-muted)] hover:text-[var(--color-text-secondary)] p-1"
                    @click="showApiKey = !showApiKey"
                  >
                    <component :is="showApiKey ? Eye : EyeOff" class="w-4 h-4" />
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

              <div class="h-px bg-[var(--color-border-subtle)] my-4"></div>

              <!-- Global System Prompt -->
              <div class="space-y-1.5">
                <label class="block text-sm font-medium text-[var(--color-text-secondary)]">全局 System Prompt</label>
                <textarea 
                  v-model="globalDraft.prompts.globalSystem" 
                  rows="4"
                  class="input textarea w-full resize-none"
                ></textarea>
              </div>

              <div class="space-y-1.5">
                <label class="block text-sm font-medium text-[var(--color-text-secondary)]">Prefill 设置</label>
                <textarea 
                  v-model="globalDraft.prompts.globalPrefill" 
                  rows="2"
                  class="input textarea w-full resize-none"
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
                    step="0.1" min="0" max="2"
                    placeholder="默认"
                    class="input w-full"
                  />
                </div>
                <div class="space-y-1.5">
                  <label class="block text-sm font-medium text-[var(--color-text-secondary)]">Top P</label>
                  <input 
                    v-model.number="globalDraft.generationDefaults.top_p" 
                    type="number" 
                    step="0.1" min="0" max="1"
                    placeholder="默认"
                    class="input w-full"
                  />
                </div>
                <div class="space-y-1.5">
                  <label class="block text-sm font-medium text-[var(--color-text-secondary)]">Max Tokens</label>
                  <input 
                    v-model.number="globalDraft.generationDefaults.max_tokens" 
                    type="number" 
                    step="128" min="1"
                    placeholder="默认"
                    class="input w-full"
                  />
                </div>
              </div>
              <div class="space-y-2 pt-2">
                <div class="text-sm font-medium text-[var(--color-text-secondary)]">上下文</div>
                <div class="grid grid-cols-2 gap-4">
                <div class="space-y-1.5">
                  <label class="block text-sm font-medium text-[var(--color-text-secondary)]">Context Size</label>
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
              <p class="text-xs text-[var(--color-text-muted)] mt-2">实际上下文总限制长度为该 Context Size 限制加上角色卡、用户信息、自定义系统提示词。草稿助手条数限制只统计最近消息条数，留空则回退到现有上下文逻辑。</p>

              <div class="h-px bg-[var(--color-border-subtle)] my-4"></div>

              <!-- 字体自定义 -->
              <div class="space-y-3">
                <div class="text-sm font-medium text-[var(--color-text-secondary)]">字体</div>
                <div class="flex gap-2 items-center">
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
                  <div class="flex items-center gap-1 h-9 bg-surface-muted border border-[var(--color-border)] rounded-lg px-1 py-0.5">
                    <button
                      type="button"
                      class="p-1.5 text-[var(--color-text-muted)] hover:text-[var(--color-text)] hover:bg-surface-hover rounded transition-colors"
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
                      class="p-1.5 text-[var(--color-text-muted)] hover:text-[var(--color-text)] hover:bg-surface-hover rounded transition-colors"
                      aria-label="增大字号"
                      @click="stepMessageFontSize(1)"
                    >
                      <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
                    </button>
                  </div>
                  <button
                    type="button"
                    class="px-4 py-2 bg-surface-muted hover:bg-surface-hover text-[var(--color-text)] rounded-lg text-sm transition-colors whitespace-nowrap"
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
                      class="px-3 py-2 bg-surface-muted hover:bg-surface-hover text-[var(--color-text)] rounded-lg text-sm transition-colors text-center leading-tight min-w-0"
                      @click="downloadSettingsBackup('basic')"
                    >
                      基本设置
                    </button>
                    <button 
                      type="button"
                      class="px-3 py-2 bg-surface-muted hover:bg-surface-hover text-[var(--color-text)] rounded-lg text-sm transition-colors text-center leading-tight min-w-0"
                      @click="downloadSettingsBackup('with_characters')"
                    >
                      包含角色卡
                    </button>
                  </div>
                  <div class="grid grid-cols-2 gap-2">
                    <button 
                      type="button"
                      class="px-3 py-2 bg-surface-muted hover:bg-surface-hover text-[var(--color-text)] rounded-lg text-sm transition-colors text-center leading-tight min-w-0"
                      @click="downloadSettingsBackup('with_chats')"
                    >
                      包含全部聊天记录
                    </button>
                    <button 
                      type="button"
                      class="px-3 py-2 bg-surface-muted hover:bg-surface-hover text-[var(--color-text)] rounded-lg text-sm transition-colors text-center leading-tight min-w-0"
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

               <div class="pt-4 flex justify-end">
                <button 
                  class="px-6 py-2 bg-brand hover:bg-brand-hover text-on-brand rounded-lg font-medium shadow-brand transition-all whitespace-nowrap"
                  @click="saveGlobal"
                >
                  保存全局设置
                </button>
              </div>

              <div class="h-px bg-[var(--color-border-subtle)] my-4"></div>
              <div class="flex justify-start gap-2 items-center">
                <button
                  type="button"
                  class="px-4 py-2 bg-surface-muted hover:bg-surface-hover text-[var(--color-text)] rounded-lg text-sm transition-colors whitespace-nowrap"
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
                class="text-xs text-[var(--color-text-muted)] text-center block cursor-pointer hover:text-[var(--color-text-secondary)] hover:underline transition-colors"
              >{{ appVersion || '…' }}</a>
            </div>
          </div>

          <!-- Presets Management -->
          <div v-if="preloaded" v-show="tab === 'presets'" class="space-y-6 h-full flex flex-col">
              <div v-if="!globalDraft" class="text-center text-[var(--color-text-muted)] py-8">加载中...</div>
              <div v-else class="flex flex-1 min-h-0 gap-4">
                  <!-- Preset List -->
                  <div class="w-1/3 flex flex-col border-r border-[var(--color-border-subtle)] pr-4">
                      <div class="flex justify-between items-center mb-3">
                          <span class="text-sm font-bold text-[var(--color-text-secondary)]">预设列表</span>
                          <button class="text-xs bg-brand-a20 text-brand px-2 py-1 rounded hover:bg-brand-a30 transition-colors" @click="createPreset">+ 新建</button>
                      </div>
                      <div class="flex-1 overflow-y-auto space-y-1 custom-scrollbar">
                          <div 
                              v-for="p in globalDraft.apiPresets" 
                              :key="p.id"
                              class="px-3 py-2 rounded-lg cursor-pointer text-sm transition-colors flex justify-between items-center group"
                              :class="editingPresetId === p.id ? 'bg-brand-a10 text-brand' : 'text-[var(--color-text-secondary)] hover:bg-surface-muted'"
                              @click="editingPresetId = p.id"
                          >
                              <span class="truncate">{{ p.name }}</span>
                              <button class="opacity-0 group-hover:opacity-100 text-[var(--color-text-muted)] hover:text-error px-1" @click.stop="deletePreset(p.id)">
                                <X class="w-3 h-3" />
                              </button>
                          </div>
                           <div v-if="globalDraft.apiPresets.length === 0" class="text-xs text-[var(--color-text-muted)] text-center py-4">无预设</div>
                      </div>
                  </div>

                  <!-- Preset Editor -->
                  <div class="flex-1 flex flex-col min-w-0" v-if="editingPreset">
                       <div class="space-y-4 overflow-y-auto custom-scrollbar pr-2 pb-4">
                          <div class="space-y-1.5">
                              <label class="block text-xs font-medium text-[var(--color-text-secondary)]">预设名称</label>
                              <input 
                                  v-model="editingPreset.name" 
                                  type="text" 
                                  class="input input-sm w-full"
                              />
                          </div>

                           <div class="space-y-1.5">
                              <label class="block text-xs font-medium text-[var(--color-text-secondary)]">Base URL</label>
                              <input 
                                  v-model="editingPreset.baseUrl" 
                                  type="text" 
                                  placeholder="https://api.openai.com 或 …/v1/chat/completions"
                                  class="input input-sm w-full"
                              />
                              <p class="text-xs text-[var(--color-text-muted)]">支持 Base（如 …/v1 或 …/v1/）或完整 chat/completions 地址；末尾有无 / 均可。</p>
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
                                      class="absolute right-2 top-1/2 -translate-y-1/2 text-[var(--color-text-muted)] hover:text-[var(--color-text-secondary)]"
                                      @click="editingPresetShowApiKey = !editingPresetShowApiKey"
                                  >
                                      <component :is="editingPresetShowApiKey ? Eye : EyeOff" class="w-4 h-4" />
                                  </button>
                               </div>
                          </div>

                          <div class="space-y-2">
                               <div class="flex justify-between items-center">
                                   <label class="block text-xs font-medium text-[var(--color-text-secondary)]">模型列表</label>
                                   <button 
                                      class="text-xs text-brand hover:text-brand-hover flex items-center gap-1" 
                                      :disabled="presetModelsLoading"
                                      @click="openModelSelector(editingPreset!)"
                                   >
                                      <Loader2 v-if="presetModelsLoading" class="animate-spin w-3 h-3" />
                                      <span>从 API 获取并筛选</span>
                                   </button>
                               </div>
                               <div class="bg-surface-overlay border border-[var(--color-border)] rounded-lg p-2 min-h-[100px] max-h-[200px] overflow-y-auto custom-scrollbar">
                                   <div class="flex flex-wrap gap-2">
                                       <div v-for="(m, idx) in editingPreset.models" :key="m" class="bg-surface-muted rounded px-2 py-1 text-xs text-[var(--color-text-secondary)] flex items-center gap-1">
                                           {{ m }}
                                           <button class="hover:text-error" @click="editingPreset!.models.splice(idx, 1)">
                                            <X class="w-3 h-3" />
                                           </button>
                                       </div>
                                        <div v-if="!editingPreset.models.length" class="text-xs text-[var(--color-text-muted)] w-full text-center py-4">
                                            点击上方“从 API 获取”或手动添加
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
                       </div>
                  </div>
                  <div v-else class="flex-1 flex items-center justify-center text-[var(--color-text-muted)] text-sm">
                      选择或创建一个预设
                  </div>
              </div>
              
               <div class="pt-2 flex justify-end">
                <button 
                  class="px-6 py-2 bg-brand hover:bg-brand-hover text-on-brand rounded-lg font-medium shadow-brand transition-all whitespace-nowrap"
                  @click="saveGlobal"
                >
                  保存所有配置
                </button>
              </div>

              <div class="h-px bg-[var(--color-border-subtle)] my-4"></div>
              <a
                href="https://github.com/DuoHBshuijiao/SimpleTavern/releases"
                target="_blank"
                rel="noopener noreferrer"
                class="text-xs text-[var(--color-text-muted)] text-center block cursor-pointer hover:text-[var(--color-text-secondary)] hover:underline transition-colors"
              >{{ appVersion || '…' }}</a>
          </div>

          <!-- Chat Specific Settings -->
          <div v-if="chatTabEverOpened" v-show="tab === 'chat'" class="space-y-6">
            <div v-if="!chat" class="text-center text-[var(--color-text-muted)] py-8">请先选择一个会话</div>
            <div v-else-if="chatDraft && globalDraft" class="space-y-5">
               <div class="text-xs text-[var(--color-text-muted)] bg-surface-muted p-3 rounded-lg border border-[var(--color-border-subtle)]">
                这些设置仅应用于当前会话，并会覆盖全局设置。模型选择将自动关联对应的 API 预设。
              </div>

              <div class="space-y-1.5">
                <label class="block text-sm font-medium text-[var(--color-text-secondary)]">会话 System Prompt (Override)</label>
                <textarea 
                  v-model="chatDraft.prompt" 
                  rows="4"
                  placeholder="留空则使用角色默认Prompt"
                  class="input textarea w-full resize-none"
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
                  <button class="btn btn-xs btn-secondary" @click="hideSavedFloors">hide（隐藏已保存楼层）</button>
                  <button class="btn btn-xs btn-secondary" @click="resetHiddenFloors">恢复全部隐藏楼层</button>
                  <span v-if="chatDraft.contextStartMessageId" class="text-xs text-[var(--color-text-muted)]">
                    当前已设置上下文起点
                  </span>
                </div>
                <textarea 
                  v-model="chatDraft.longTermMemory"
                  rows="4"
                  placeholder="会插入 System Prompt，留空则不启用"
                  class="input textarea w-full resize-none"
                ></textarea>
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
                    <span class="font-bold">{{ globalDraft?.apiPresets.find(p => p.id === chatDraft?.presetId)?.name || 'Unknown' }}</span>
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
                  <label class="block text-sm font-medium text-[var(--color-text-secondary)]">Max Tokens</label>
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
                  <label class="block text-sm font-medium text-[var(--color-text-secondary)]">Context Size</label>
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
              <p class="text-xs text-[var(--color-text-muted)] mt-2">实际上下文总限制长度为该 Context Size 限制加上角色卡、用户信息、自定义系统提示词。草稿助手优先使用当前会话的条数限制，其次全局，最后回退到现有上下文逻辑。</p>

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
                <div class="max-h-[180px] space-y-2 overflow-y-auto rounded-lg border border-[var(--color-border-subtle)] bg-surface-overlay p-2">
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
                    <div class="flex min-w-0 flex-1 flex-col gap-0.5">
                      <div class="flex items-center gap-1.5">
                        <span class="shrink-0 cursor-grab text-[var(--color-text-muted)] active:cursor-grabbing" title="拖动排序" aria-hidden="true">
                          <GripVertical class="w-4 h-4" />
                        </span>
                        <span class="truncate text-xs text-[var(--color-text)]">{{ idx + 1 }}. {{ worldBookName(att.worldBookId) }}</span>
                      </div>
                      <div class="text-[10px] text-[var(--color-text-muted)] pl-6">
                        扫描：{{ scanDepthDisplay(att.scanDepth) }}　深度：{{ att.insertDepth ?? 5 }}
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

              <!-- Group Member Settings (Removed, moved to independent GroupSettingsModal) -->

               <div class="pt-4 flex justify-end gap-3">
                <button 
                  class="px-4 py-2 text-[var(--color-text-muted)] hover:text-[var(--color-text)] transition-colors whitespace-nowrap"
                  @click="close"
                >
                  取消
                </button>
                <button 
                  class="px-6 py-2 bg-brand hover:bg-brand-hover text-on-brand rounded-lg font-medium shadow-brand transition-all whitespace-nowrap"
                  @click="saveChatOverrides(); saveGlobal()"
                >
                  保存设置
                </button>
              </div>

              <div class="h-px bg-[var(--color-border-subtle)] my-4"></div>
              <a
                href="https://github.com/DuoHBshuijiao/SimpleTavern/releases"
                target="_blank"
                rel="noopener noreferrer"
                class="text-xs text-[var(--color-text-muted)] text-center block cursor-pointer hover:text-[var(--color-text-secondary)] hover:underline transition-colors"
              >{{ appVersion || '…' }}</a>
            </div>
          </div>
        </div>
      </div>
  </div>

  <!-- Model Selector Modal（Teleport 到 body 避免被父级 flex/窄容器限制宽度） -->
  <Teleport to="body">
    <div v-if="showModelSelector" class="fixed inset-0 z-[60] flex items-center justify-center">
      <!-- Backdrop -->
      <div class="absolute inset-0 bg-overlay-heavy backdrop-blur-sm" @click="showModelSelector = false"></div>
      
      <!-- Modal -->
      <div class="relative w-full max-w-lg min-w-[300px] glass-panel rounded-2xl shadow-2xl flex flex-col max-h-[85vh] m-4">
      <div class="p-4 border-b border-[var(--color-border)] flex justify-between items-center bg-surface-muted rounded-t-2xl">
        <h3 class="font-bold text-[var(--color-text)]">选择模型</h3>
        <button class="text-[var(--color-text-muted)] hover:text-[var(--color-text)]" @click="showModelSelector = false">
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
      
      <div class="flex-1 overflow-y-auto p-2 bg-transparent">
        <div v-if="filteredCandidates.length === 0" class="text-center text-[var(--color-text-muted)] py-8 text-sm">
          未找到模型
        </div>
        <div v-else class="space-y-1">
          <div 
            v-for="m in filteredCandidates" 
            :key="m"
            class="flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-surface-muted cursor-pointer transition-colors"
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
          <button class="px-4 py-2 text-sm text-[var(--color-text-muted)] hover:text-[var(--color-text)] transition-colors" @click="showModelSelector = false">取消</button>
          <button class="px-4 py-2 text-sm bg-brand hover:bg-brand-hover text-on-brand rounded-lg shadow-brand transition-all" @click="saveModelSelection">确认</button>
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
</style>
