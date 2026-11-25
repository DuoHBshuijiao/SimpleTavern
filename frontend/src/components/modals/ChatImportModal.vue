<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { X } from 'lucide-vue-next'
import { apiGet, apiPost } from '../../api/http'
import { useSettingsImport, type ImportWarningItem, coerceImportWarningText } from '../../composables/useSettingsImport'
import { notifyMessage } from '../../composables/useNotify'
import type { CharacterCard, Chat, MvuMode, UserPersona } from '../../types/models'
import ModernSelect from '../ModernSelect.vue'
import SettingsField from '../settings-drawer/SettingsField.vue'
import SettingsSwitch from '../settings-drawer/SettingsSwitch.vue'
import SettingsHint from '../settings-drawer/SettingsHint.vue'
import { useDialogBehavior } from '../../composables/useDialogBehavior'
import { dialogAria } from '../../utils/uiPrimitives'

declare global {
  interface Window {
    __ST_JANITOR_BRIDGE_INSTALLED__?: boolean
    __ST_JANITOR_BRIDGE_VERSION__?: string
  }
}

const JANITOR_BRIDGE_EXT_REL_PATH = 'extensions/simpletavern-janitor-bridge'
const JANITOR_BRIDGE_MIN_VERSION = '0.1.11'
const JANITOR_BRIDGE_INSTALL_URL = 'https://github.com/DuoHBshuijiao/SimpleTavern#3-从-janitorai-迁移聊天记录可选'
const bridgeInstalled = ref(false)
const bridgeVersion = ref('')
const copiedExtensionUrl = ref(false)
const bridgeStatus = computed(() => {
  if (!bridgeInstalled.value) return 'missing'
  if (!/^\d+\.\d+\.\d+(?:\.\d+)?$/.test(bridgeVersion.value)) return 'outdated'
  const current = bridgeVersion.value.split('.').map(Number)
  const minimum = JANITOR_BRIDGE_MIN_VERSION.split('.').map(Number)
  for (const [i, required] of minimum.entries()) {
    if (current[i] !== required) return current[i]! > required ? 'ready' : 'outdated'
  }
  return 'ready'
})

function refreshBridgeStatus() {
  bridgeInstalled.value = window.__ST_JANITOR_BRIDGE_INSTALLED__ === true
  bridgeVersion.value = window.__ST_JANITOR_BRIDGE_VERSION__ || ''
}

onMounted(() => {
  refreshBridgeStatus()
  window.addEventListener('simpletavern:janitor-bridge-ready', refreshBridgeStatus)
})
onUnmounted(() => window.removeEventListener('simpletavern:janitor-bridge-ready', refreshBridgeStatus))

function getExtensionsManageUrlHint(): string {
  const ua = navigator.userAgent
  if (/\bEdg\//.test(ua) || /\bEdgA\//.test(ua) || /\bEdgiOS\//.test(ua)) return 'edge://extensions'
  return 'chrome://extensions'
}

async function copyExtensionManagerUrl() {
  try {
    await navigator.clipboard.writeText(getExtensionsManageUrlHint())
    copiedExtensionUrl.value = true
  } catch {
    await notifyMessage(`在浏览器地址栏打开 ${getExtensionsManageUrlHint()}。`)
  }
}

interface JanitorPendingPreviewMessage {
  role: 'assistant' | 'user'
  content: string
  ts?: string | null
}

interface JanitorPendingPreview {
  botName: string
  messageCount: number
  sampleMessages: JanitorPendingPreviewMessage[]
}

interface JanitorConfirmResult {
  chat: Chat
  imported: string[]
  warnings: ImportWarningItem[]
}

const props = defineProps<{
  show: boolean
  characters: CharacterCard[]
  personas: UserPersona[]
  pendingId?: string | null
  /** 父级在「仅角色导入完成」等场景递增，用于在不丢失 pendingId 时刷新聊天预览 */
  pendingReloadNonce?: number
  /** 与 ChatPage 的 errorStack.pushError 一致，用于未安装扩展时的右下角错误提示 */
  pushError?: (payload: { message: unknown; source: 'main' | 'assistant'; title?: string }) => void
}>()

const emit = defineEmits<{
  (e: 'update:show', value: boolean): void
  (e: 'janitor-imported', payload: { chatId: string; characterId: string | null; openAfterImport: boolean }): void
}>()

const {
  importSettingsFile,
  previewSillyTavernImport,
  confirmSillyTavernImport,
  refreshDataAfterImport,
  formatImportResultMessage,
} = useSettingsImport()

const importInputRef = ref<HTMLInputElement | null>(null)
const stImportInputRef = ref<HTMLInputElement | null>(null)

const janitorLink = ref('')
const openAfterImport = ref(true)
const pendingLoading = ref(false)
const pendingError = ref('')
const pendingPreview = ref<JanitorPendingPreview | null>(null)
const selectedCharacterId = ref('')
const selectedPersonaId = ref('')
const janitorConfirming = ref(false)
const jaiCharacterUrl = ref('')
const stPreviewLoading = ref(false)
const stConfirming = ref(false)
const stPendingId = ref('')
const stExpiresAt = ref('')
const stPreview = ref<Awaited<ReturnType<typeof previewSillyTavernImport>>['preview'] | null>(null)
const stPreviewWarnings = ref<ImportWarningItem[]>([])
const stEnableMvuCompatibility = ref(false)
const stMvuMode = ref<MvuMode>('regex')

const personaOptions = computed(() => [
  { label: '（不指定 Persona）', value: '' },
  ...props.personas.map((p) => ({ label: p.name || p.id, value: p.id })),
])

const characterOptions = computed(() =>
  props.characters.map((c) => ({ label: c.name || c.id, value: c.id })),
)

const stMvuModeOptions = [
  { label: '正则兼容', value: 'regex' },
  { label: '指令模式', value: 'directive' },
]

const stConfirmLabel = computed(() => {
  if (!stConfirming.value) return '确认导入 ST 角色'
  return stEnableMvuCompatibility.value && stMvuMode.value === 'directive'
    ? 'MVU Agent 分析中...'
    : '导入中...'
})

const characterListKey = computed(() => props.characters.map((c) => c.id).join(','))

let pendingPreviewController: AbortController | null = null

function clearPendingPreview() {
  pendingPreviewController?.abort()
  pendingPreviewController = null
  pendingLoading.value = false
  pendingError.value = ''
  pendingPreview.value = null
}

watch(
  () => [props.show, props.pendingId, props.pendingReloadNonce] as const,
  ([visible, pendingId]) => {
    clearPendingPreview()
    if (!visible) return
    refreshBridgeStatus()
    if (pendingId) void loadPendingPreview(pendingId)
  },
  { immediate: true },
)

watch([() => props.show, characterListKey], ([visible]) => {
  if (visible && !props.characters.some((character) => character.id === selectedCharacterId.value)) {
    selectedCharacterId.value = props.characters[0]?.id ?? ''
  }
}, { immediate: true })

function close() {
  clearPendingPreview()
  emit('update:show', false)
}

const titleId = 'chat-import-title'
const dialogAttrs = dialogAria(titleId)
const { dialogRef } = useDialogBehavior(() => props.show, close)
void dialogRef

function triggerImport() {
  importInputRef.value?.click()
}

function triggerStImport() {
  stImportInputRef.value?.click()
}

function resetStPreview() {
  stPendingId.value = ''
  stExpiresAt.value = ''
  stPreview.value = null
  stPreviewWarnings.value = []
  stEnableMvuCompatibility.value = false
  stMvuMode.value = 'regex'
}

function updateStMvuMode(value: string) {
  stMvuMode.value = value === 'directive' ? 'directive' : 'regex'
}

/** 与专用「导入 SillyTavern 数据」共用：预览成功后写入 pendingId / MVU 默认值 */
async function loadStPreviewFromFile(file: File): Promise<void> {
  stPreviewLoading.value = true
  try {
    const result = await previewSillyTavernImport(file)
    stPendingId.value = result.pendingId
    stExpiresAt.value = result.expiresAt
    stPreview.value = result.preview
    stPreviewWarnings.value = result.warnings || []
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

function notifyStPreviewError(err: unknown) {
  if (props.pushError) {
    props.pushError({ message: err instanceof Error ? err.message : String(err), source: 'main', title: 'SillyTavern 导入失败' })
  } else {
    void notifyMessage(err instanceof Error ? err.message : String(err))
  }
}

async function handleImportChange(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  const lower = file.name.toLowerCase()

  // PNG：一律走 ST 预览（与「导入 SillyTavern 数据」相同），否则 /api/import 会跳过 MVU 选项
  if (lower.endsWith('.png')) {
    resetStPreview()
    try {
      await loadStPreviewFromFile(file)
    } catch (err) {
      resetStPreview()
      notifyStPreviewError(err)
    } finally {
      input.value = ''
    }
    return
  }

  // JSON：先尝试 ST 角色卡预览；若不是 ST 卡则退回通用设置/数据导入
  if (lower.endsWith('.json')) {
    resetStPreview()
    try {
      await loadStPreviewFromFile(file)
      input.value = ''
      return
    } catch {
      // 非 SillyTavern 角色卡形状时继续走下方通用导入
    }
    try {
      const result = await importSettingsFile(file)
      if (!result) return
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
    if (!result) return
    await refreshDataAfterImport()
    await notifyMessage(formatImportResultMessage(result))
  } catch (err) {
    await notifyMessage(err instanceof Error ? err.message : String(err))
  } finally {
    input.value = ''
  }
}

async function handleStImportChange(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  try {
    await loadStPreviewFromFile(file)
  } catch (err) {
    resetStPreview()
    notifyStPreviewError(err)
  } finally {
    input.value = ''
  }
}

async function confirmStImport() {
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
    resetStPreview()
  } catch (err) {
    if (props.pushError) {
      props.pushError({ message: err instanceof Error ? err.message : String(err), source: 'main', title: 'SillyTavern 导入失败' })
    } else {
      await notifyMessage(err instanceof Error ? err.message : String(err))
    }
  } finally {
    stConfirming.value = false
  }
}

async function openJanitorLinkAndTryCapture() {
  refreshBridgeStatus()
  if (bridgeStatus.value !== 'ready') return
  const raw = janitorLink.value.trim()
  if (!raw) {
    await notifyMessage('请先填写 JanitorAI 聊天链接。')
    return
  }
  let parsed: URL
  try {
    parsed = new URL(raw)
  } catch {
    await notifyMessage('链接格式无效。')
    return
  }
  if (!/(\.|^)janitorai\.com$/i.test(parsed.hostname)) {
    await notifyMessage('仅支持 JanitorAI 链接。')
    return
  }
  parsed.searchParams.set('_st_import', '1')
  parsed.searchParams.set('_st_ts', String(Date.now()))
  parsed.searchParams.set('_st_app_base', window.location.origin)
  window.open(parsed.toString(), '_blank', 'noopener')
}

async function openJaiCharacterUrlAndCapture() {
  refreshBridgeStatus()
  if (bridgeStatus.value !== 'ready') return
  const raw = jaiCharacterUrl.value.trim()
  if (!raw) {
    await notifyMessage('请先填写 JanitorAI 角色页链接。')
    return
  }
  let parsed: URL
  try {
    parsed = new URL(raw)
  } catch {
    await notifyMessage('链接格式无效。')
    return
  }
  if (!/(\.|^)janitorai\.com$/i.test(parsed.hostname)) {
    await notifyMessage('仅支持 JanitorAI 链接。')
    return
  }
  parsed.searchParams.set('_st_char_html', '1')
  parsed.searchParams.set('_st_ts', String(Date.now()))
  parsed.searchParams.set('_st_app_base', window.location.origin)
  window.open(parsed.toString(), '_blank', 'noopener')
}

async function loadPendingPreview(pendingId: string) {
  const controller = new AbortController()
  pendingPreviewController = controller
  pendingLoading.value = true
  try {
    const data = await apiGet<{ preview: JanitorPendingPreview }>(
      `/api/import/janitor/pending/${encodeURIComponent(pendingId)}`,
      controller.signal,
    )
    if (pendingPreviewController === controller) pendingPreview.value = data.preview
  } catch (error) {
    if (pendingPreviewController === controller) {
      pendingError.value = error instanceof Error ? error.message : String(error)
    }
  } finally {
    if (pendingPreviewController === controller) {
      pendingLoading.value = false
      pendingPreviewController = null
    }
  }
}

async function confirmJanitorImport() {
  if (janitorConfirming.value || !pendingPreview.value) return
  const pendingId = props.pendingId
  const characterId = selectedCharacterId.value
  const shouldOpen = openAfterImport.value
  if (!pendingId || !characterId) return
  janitorConfirming.value = true
  try {
    const result = await apiPost<JanitorConfirmResult>('/api/import/janitor/confirm', {
      pendingId,
      characterId,
      userPersonaId: selectedPersonaId.value || null,
    })
    emit('janitor-imported', {
      chatId: result.chat.id,
      characterId: result.chat.characterId ?? null,
      openAfterImport: shouldOpen,
    })
    close()
    await refreshDataAfterImport()
    await notifyMessage(formatImportResultMessage(result))
  } catch (error) {
    await notifyMessage(error instanceof Error ? error.message : String(error))
  } finally {
    janitorConfirming.value = false
  }
}
</script>

<template>
  <Transition name="modal">
    <div v-if="show" class="modal">
      <!-- 背景模糊须用 Tailwind backdrop-*（见 README / glass.css：手写 backdrop-filter 经构建阶段的 CSS 优化后会失效） -->
      <div class="modal-backdrop backdrop-blur-[var(--glass-blur-soft)]" @click="close"></div>
      <div
        ref="dialogRef"
        v-bind="dialogAttrs"
        tabindex="-1"
        class="modal-content modal-surface chat-modal-width-568-90 min-w-0"
      >
        <div class="modal-header">
          <h3 :id="titleId" class="modal-title">导入</h3>
          <button type="button" class="modal-close" aria-label="关闭导入弹窗" @click="close">
            <X class="w-5 h-5" />
          </button>
        </div>
        <div class="modal-body custom-scrollbar">
          <section class="settings-group">
            <div class="settings-group-title">本地文件导入</div>
            <SettingsHint>SimpleTavern 数据支持 TXT、JSON、JSONL、ZIP。SillyTavern 角色卡支持 PNG、JSON。</SettingsHint>
            <div class="flex flex-wrap gap-2">
              <button class="btn btn-sm btn-secondary" @click="triggerImport">选择文件导入</button>
              <button class="btn btn-sm btn-secondary" :disabled="stPreviewLoading" @click="triggerStImport">
                {{ stPreviewLoading ? '读取预览中...' : '导入 SillyTavern 数据' }}
              </button>
              <input ref="importInputRef" type="file" class="hidden" accept=".txt,.json,.jsonl,.zip,.png" @change="handleImportChange" />
              <input ref="stImportInputRef" type="file" class="hidden" accept=".png,.json" @change="handleStImportChange" />
            </div>

            <template v-if="stPreview">
              <div class="settings-readout space-y-2">
                <div class="flex items-start justify-between gap-2">
                  <div class="min-w-0">
                    <div class="settings-label">SillyTavern 预览</div>
                    <div class="mt-1 break-words">
                      角色名：<span class="text-[var(--color-text)]">{{ stPreview.characterName || '未知' }}</span>
                    </div>
                  </div>
                  <button class="btn btn-xs btn-secondary shrink-0" :disabled="stConfirming" @click="resetStPreview">重新选择</button>
                </div>
                <div class="grid grid-cols-1 gap-x-3 gap-y-1 sm:grid-cols-2">
                  <div>世界书：<span class="text-[var(--color-text)]">{{ stPreview.worldBookName || '未检测到' }}</span></div>
                  <div>世界书条目：<span class="text-[var(--color-text)]">{{ stPreview.worldBookEntryCount }}</span></div>
                  <div>tavern_helper：<span class="text-[var(--color-text)]">{{ stPreview.mvu.hasTavernHelper ? '已检测到' : '未检测到' }}</span></div>
                  <div>regex_scripts：<span class="text-[var(--color-text)]">{{ stPreview.mvu.regexScriptCount }}</span></div>
                </div>
              </div>

              <div v-if="stPreviewWarnings.length" class="settings-readout">
                <div class="settings-label">导入警告</div>
                <ul class="mt-1 list-disc space-y-1 pl-4 text-[var(--color-text)]">
                  <li v-for="(warning, idx) in stPreviewWarnings" :key="idx">
                    {{ coerceImportWarningText(warning) }}
                  </li>
                </ul>
              </div>

              <div v-if="stPreview.mvu.characterBookCandidates.length" class="settings-readout">
                <div class="settings-label">世界书 MVU 候选</div>
                <div class="mt-1 space-y-1">
                  <div
                    v-for="candidate in stPreview.mvu.characterBookCandidates"
                    :key="candidate.title"
                    class="flex items-center justify-between gap-3"
                  >
                    <span class="min-w-0 truncate text-[var(--color-text)]">{{ candidate.title }}</span>
                    <span class="shrink-0 whitespace-nowrap">{{ candidate.enabled ? '启用' : '禁用' }}</span>
                  </div>
                </div>
              </div>

              <SettingsSwitch
                label="启用 MVU 兼容"
                :model-value="stEnableMvuCompatibility"
                @update:model-value="stEnableMvuCompatibility = $event"
              />
              <SettingsField
                label="MVU 模式"
                more="正则兼容模式尝试转换卡内正则。指令模式将完整角色卡交给 MVU 模型，用于生成指令和初始状态。"
              >
                <ModernSelect
                  :model-value="stMvuMode"
                  :options="stMvuModeOptions"
                  placeholder="选择 MVU 模式"
                  @update:model-value="updateStMvuMode"
                />
              </SettingsField>
              <div class="flex flex-wrap items-center justify-between gap-2">
                <span v-if="stExpiresAt" class="settings-hint">预览暂存至：{{ stExpiresAt }}</span>
                <button class="btn btn-sm btn-primary ml-auto" :disabled="!stPendingId || stConfirming" @click="confirmStImport">
                  {{ stConfirmLabel }}
                </button>
              </div>
            </template>
          </section>

          <section class="settings-group">
            <div class="settings-group-title">JanitorAI 聊天迁移</div>
            <div v-if="bridgeStatus !== 'ready'" class="settings-readout space-y-2" role="status">
              <p class="font-medium text-[var(--color-warning-text)]">
                {{ bridgeStatus === 'missing' ? '未检测到 SimpleTavern Janitor Bridge 扩展' : '请更新 SimpleTavern Janitor Bridge 扩展' }}
              </p>
              <p v-if="bridgeStatus === 'outdated'">当前版本：{{ bridgeVersion || '旧版（未报告版本）' }}。需要 {{ JANITOR_BRIDGE_MIN_VERSION }} 或更新版本。</p>
              <p>在浏览器扩展管理页加载或重新加载扩展，再刷新 SimpleTavern。</p>
              <p class="break-all">扩展目录 <code>{{ JANITOR_BRIDGE_EXT_REL_PATH }}</code>，Windows 安装版位于 <code>current/</code> 下。</p>
              <div class="flex flex-wrap items-center gap-2">
                <a :href="JANITOR_BRIDGE_INSTALL_URL" target="_blank" rel="noopener noreferrer" class="btn btn-xs btn-secondary">查看安装步骤</a>
                <button type="button" class="btn btn-xs btn-ghost" @click="copyExtensionManagerUrl">
                  {{ copiedExtensionUrl ? '已复制扩展管理地址' : '复制扩展管理地址' }}
                </button>
                <code>{{ getExtensionsManageUrlHint() }}</code>
              </div>
            </div>
            <div class="flex flex-wrap gap-2">
              <input
                v-model="janitorLink"
                class="input min-w-[12rem] flex-1"
                placeholder="https://janitorai.com/chats/..."
              />
              <button class="btn btn-sm btn-secondary" :disabled="bridgeStatus !== 'ready'" @click="openJanitorLinkAndTryCapture">打开并尝试获取</button>
            </div>

            <div class="settings-readout">
              <div>
                {{ pendingLoading ? '正在读取待导入预览...' : (pendingPreview ? '已检测到待导入数据' : '尚未检测到待导入数据') }}
              </div>
              <div v-if="pendingError" class="mt-2 text-[var(--color-error)]">{{ pendingError }}</div>
              <div v-if="pendingPreview" class="mt-2 space-y-2">
                <div>角色名：<span class="text-[var(--color-text)]">{{ pendingPreview.botName || '未知' }}</span></div>
                <div>消息数：<span class="text-[var(--color-text)]">{{ pendingPreview.messageCount }}</span></div>
                <div v-if="pendingPreview.sampleMessages?.length">
                  <div class="settings-label">预览</div>
                  <div class="mt-1 flex gap-2 items-stretch overflow-x-auto overflow-y-hidden custom-scrollbar pb-1">
                    <div
                      v-for="(item, idx) in pendingPreview.sampleMessages"
                      :key="`${item.role}_${idx}`"
                      class="settings-item shrink-0 flex flex-col w-[200px] h-[140px] min-h-0 min-w-0 text-left"
                    >
                      <span class="settings-label shrink-0 mb-1">{{ item.role === 'assistant' ? '角色' : '用户' }}</span>
                      <div class="min-h-0 flex-1 overflow-hidden line-clamp-6 break-words">{{ item.content }}</div>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <SettingsField label="目标角色">
              <ModernSelect
                :key="characterListKey"
                :model-value="selectedCharacterId"
                :options="characterOptions"
                placeholder="选择角色"
                @update:model-value="(v) => selectedCharacterId = v"
              />
            </SettingsField>
            <SettingsField label="Persona（用户身份）">
              <ModernSelect
                :model-value="selectedPersonaId"
                :options="personaOptions"
                placeholder="选择 Persona"
                @update:model-value="(v) => selectedPersonaId = v"
              />
            </SettingsField>
            <SettingsSwitch
              label="导入后打开该会话"
              :model-value="openAfterImport"
              @update:model-value="openAfterImport = $event"
            />
            <div class="flex justify-end">
              <button
                class="btn btn-sm btn-primary"
                :disabled="!pendingPreview || !selectedCharacterId || janitorConfirming"
                @click="confirmJanitorImport"
              >
                {{ janitorConfirming ? '导入中...' : '确认导入 Janitor 聊天' }}
              </button>
            </div>
          </section>

          <section class="settings-group">
            <div class="settings-group-title">导入 JAI 角色（链接）</div>
            <div class="flex flex-wrap gap-2">
              <input
                v-model="jaiCharacterUrl"
                class="input min-w-[12rem] flex-1"
                placeholder="https://janitorai.com/characters/..."
              />
              <button class="btn btn-sm btn-secondary" :disabled="bridgeStatus !== 'ready'" @click="openJaiCharacterUrlAndCapture">打开并抓取</button>
            </div>
          </section>
        </div>
      </div>
    </div>
  </Transition>
</template>
