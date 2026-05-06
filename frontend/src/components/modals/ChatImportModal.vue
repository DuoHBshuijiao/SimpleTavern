<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { apiGet } from '../../api/http'
import { useSettingsImport } from '../../composables/useSettingsImport'
import { notifyMessage } from '../../composables/useNotify'
import type { CharacterCard, Chat, MvuMode, UserPersona } from '../../types/models'
import ModernSelect from '../ModernSelect.vue'
import ThemedCheckbox from '../ThemedCheckbox.vue'

declare global {
  interface Window {
    __ST_JANITOR_BRIDGE_INSTALLED__?: boolean
  }
}

/** 由仓库内 Janitor Bridge 扩展在应用页注入，用于判断是否已安装并启用该扩展。 */
function isJanitorBridgeInstalled(): boolean {
  return typeof window !== 'undefined' && window.__ST_JANITOR_BRIDGE_INSTALLED__ === true
}

const JANITOR_BRIDGE_EXT_REL_PATH = 'extensions/simpletavern-janitor-bridge'

function getExtensionsManageUrlHint(): string {
  const ua = navigator.userAgent
  if (/\bEdg\//.test(ua) || /\bEdgA\//.test(ua) || /\bEdgiOS\//.test(ua)) return 'edge://extensions'
  return 'chrome://extensions'
}

function buildJanitorBridgeMissingMessage(): string {
  const addr = getExtensionsManageUrlHint()
  return [
    '未检测到「SimpleTavern Janitor Bridge」浏览器扩展，无法从 Janitor 页面抓取数据。',
    '',
    '请在本地仓库中「加载已解压的扩展」，目录为（相对仓库根）：',
    JANITOR_BRIDGE_EXT_REL_PATH,
    '',
    '在浏览器地址栏输入并打开以下地址以进入扩展管理页：',
    addr,
  ].join('\n')
}

/** 未检测到扩展时走与主聊天一致的错误栈（ErrorModal），无回调时退回全局通知。 */
function notifyJanitorBridgeMissingIfNeeded(): void {
  if (isJanitorBridgeInstalled()) return
  const message = buildJanitorBridgeMissingMessage()
  const title = '未安装 Janitor Bridge 扩展'
  if (props.pushError) {
    props.pushError({ message, source: 'main', title })
  } else {
    void notifyMessage(message, { title })
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
  warnings: string[]
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
  { label: 'Regex 兼容', value: 'regex' },
  { label: '指令模式', value: 'directive' },
]

const stDetectedMvu = computed(() => {
  const mvu = stPreview.value?.mvu
  return Boolean(mvu?.hasTavernHelper || mvu?.hasRegexScripts || mvu?.characterBookCandidateCount)
})

const stConfirmLabel = computed(() => {
  if (!stConfirming.value) return '确认导入 ST 角色'
  return stEnableMvuCompatibility.value && stMvuMode.value === 'directive'
    ? 'MVU Agent 分析中...'
    : '导入中...'
})

const characterListKey = computed(() => props.characters.map((c) => c.id).join(','))

watch(
  () => props.show,
  (visible) => {
    if (!visible) return
    if (!selectedCharacterId.value) {
      const firstCharacter = props.characters[0]
      if (firstCharacter) selectedCharacterId.value = firstCharacter.id
    }
    if (props.pendingId) {
      void loadPendingPreview(props.pendingId)
    }
  },
  { immediate: true },
)

watch(
  () => props.pendingId,
  (pendingId) => {
    if (props.show && pendingId) {
      void loadPendingPreview(pendingId)
    }
  },
)

watch(
  () => props.pendingReloadNonce,
  (n, prev) => {
    if (n == null || n === prev) return
    if (props.show && props.pendingId) {
      void loadPendingPreview(props.pendingId)
    }
  },
)

function close() {
  emit('update:show', false)
}

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
  notifyJanitorBridgeMissingIfNeeded()
  window.open(parsed.toString(), '_blank')
}

async function openJaiCharacterUrlAndCapture() {
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
  notifyJanitorBridgeMissingIfNeeded()
  window.open(parsed.toString(), '_blank')
}

async function loadPendingPreview(pendingId: string) {
  pendingLoading.value = true
  pendingError.value = ''
  try {
    const data = await apiGet<{ preview: JanitorPendingPreview }>(`/api/import/janitor/pending/${pendingId}`)
    pendingPreview.value = data.preview
  } catch (err) {
    pendingPreview.value = null
    pendingError.value = err instanceof Error ? err.message : String(err)
  } finally {
    pendingLoading.value = false
  }
}

async function confirmJanitorImport() {
  if (!props.pendingId) {
    await notifyMessage('未检测到待导入的数据。')
    return
  }
  if (!selectedCharacterId.value) {
    await notifyMessage('请选择角色。')
    return
  }
  janitorConfirming.value = true
  try {
    const r = await fetch('/api/import/janitor/confirm', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        pendingId: props.pendingId,
        characterId: selectedCharacterId.value,
        userPersonaId: selectedPersonaId.value || null,
      }),
    })
    if (!r.ok) {
      throw new Error(await r.text())
    }
    const result = (await r.json()) as JanitorConfirmResult
    await refreshDataAfterImport()
    await notifyMessage(
      `导入完成：${(result.imported || []).join(', ') || '无'}${result.warnings?.length ? '\n警告：' + result.warnings.join('; ') : ''}`,
    )
    emit('janitor-imported', {
      chatId: result.chat.id,
      characterId: result.chat.characterId ?? null,
      openAfterImport: openAfterImport.value,
    })
    close()
  } catch (err) {
    await notifyMessage(err instanceof Error ? err.message : String(err))
  } finally {
    janitorConfirming.value = false
  }
}
</script>

<template>
  <Transition name="modal">
    <div v-if="show" class="modal">
      <!-- 背景模糊须用 Tailwind backdrop-*（见 README / glass.css：手写 backdrop-filter 经 esbuild 压缩可能失效） -->
      <div class="modal-backdrop backdrop-blur-[var(--blur-heavy)]" @click="close"></div>
      <div
        class="modal-content chat-modal-width-568-90 min-w-0 glass-panel theme-panel-bg backdrop-blur-[var(--blur-heavy)] backdrop-saturate-[1.8] border border-[var(--color-border)]"
      >
        <div class="modal-header border-b border-[var(--color-border-subtle)]">
          <h3 class="modal-title text-[var(--color-text)]">导入</h3>
          <button class="modal-close text-[var(--color-text-muted)] hover:text-[var(--color-text)]" @click="close">×</button>
        </div>
        <div class="modal-body">
          <div class="max-h-[65vh] space-y-4 overflow-y-auto pr-1">
            <section class="rounded-xl border border-[var(--color-border-subtle)] bg-[var(--color-surface-muted)] p-4">
              <h4 class="text-sm font-medium text-[var(--color-text-secondary)]">本地文件导入</h4>
              <p class="mt-2 text-xs text-[var(--color-text-muted)]">
                支持 txt/json/jsonl/zip；其中 PNG 或 SillyTavern 形状 JSON 会先进入下方预览（含 MVU 选项），与设置里「仅备份 JSON」区分。
              </p>
              <p class="mt-1 text-xs text-[var(--color-text-muted)]">专用按钮同样仅用于 PNG / ST 角色 JSON；不支持 ST 聊天记录导入。</p>
              <div class="mt-3 flex flex-wrap gap-2">
                <button class="btn btn-sm btn-secondary" @click="triggerImport">选择文件导入</button>
                <button class="btn btn-sm btn-secondary" :disabled="stPreviewLoading" @click="triggerStImport">
                  {{ stPreviewLoading ? '读取预览中...' : '导入 SillyTavern 数据' }}
                </button>
                <input ref="importInputRef" type="file" class="hidden" accept=".txt,.json,.jsonl,.zip,.png" @change="handleImportChange" />
                <input ref="stImportInputRef" type="file" class="hidden" accept=".png,.json" @change="handleStImportChange" />
              </div>
              <div
                v-if="stPreview"
                class="mt-3 rounded-lg border border-[var(--color-border-subtle)] bg-[var(--color-surface-overlay)] p-3 text-xs text-[var(--color-text-muted)]"
              >
                <div class="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <div class="text-[var(--color-text-secondary)]">SillyTavern 预览</div>
                    <div class="mt-1">
                      角色名：<span class="text-[var(--color-text)]">{{ stPreview.characterName || '未知' }}</span>
                    </div>
                  </div>
                  <button class="btn btn-xs btn-secondary" :disabled="stConfirming" @click="resetStPreview">重新选择</button>
                </div>
                <div class="mt-2 grid grid-cols-1 gap-2 md:grid-cols-2">
                  <div>世界书：<span class="text-[var(--color-text)]">{{ stPreview.worldBookName || '未检测到' }}</span></div>
                  <div>世界书条目：<span class="text-[var(--color-text)]">{{ stPreview.worldBookEntryCount }}</span></div>
                  <div>tavern_helper：<span class="text-[var(--color-text)]">{{ stPreview.mvu.hasTavernHelper ? '已检测到' : '未检测到' }}</span></div>
                  <div>regex_scripts：<span class="text-[var(--color-text)]">{{ stPreview.mvu.regexScriptCount }}</span></div>
                </div>
                <p v-if="stPreview.worldBookEntryCount" class="mt-2 text-[var(--color-text-muted)]">
                  ST 世界书将作为 SimpleTavern 世界书完整保留；MVU 兼容只生成指令或正文正则，不删除原条目。
                </p>
                <p class="mt-1 text-[var(--color-text-muted)]">
                  Regex 模式会尝试转换可表达的 regex_scripts；指令模式会把完整 ST 卡上下文交给 MVU Agent，生成 MVU 指令与初始状态表，Tavern Helper JS 不会执行。
                </p>
                <div
                  v-if="stPreview.mvu.characterBookCandidates.length"
                  class="mt-2 rounded-md border border-[var(--color-border-subtle)] bg-[var(--color-surface-muted)] p-2"
                >
                  <div class="text-[var(--color-text-secondary)]">世界书 MVU 候选</div>
                  <div class="mt-1 space-y-1">
                    <div
                      v-for="candidate in stPreview.mvu.characterBookCandidates"
                      :key="candidate.title"
                      class="flex items-center justify-between gap-2"
                    >
                      <span class="truncate text-[var(--color-text)]">{{ candidate.title }}</span>
                      <span>{{ candidate.enabled ? '启用' : '禁用' }}</span>
                    </div>
                  </div>
                </div>
                <label class="mt-3 flex items-center gap-2 text-xs text-[var(--color-text-muted)]">
                  <ThemedCheckbox :checked="stEnableMvuCompatibility" @update:checked="stEnableMvuCompatibility = $event" />
                  启用 MVU 兼容
                  <span v-if="stDetectedMvu" class="text-[var(--color-text-secondary)]">已检测到候选结构</span>
                </label>
                <div class="mt-3 grid grid-cols-1 gap-3 md:grid-cols-[1fr_auto]">
                  <div>
                    <div class="mb-1 text-xs text-[var(--color-text-muted)]">MVU 模式</div>
                    <ModernSelect
                      :model-value="stMvuMode"
                      :options="stMvuModeOptions"
                      placeholder="选择 MVU 模式"
                      @update:model-value="updateStMvuMode"
                    />
                  </div>
                  <div class="flex items-end">
                    <button class="btn btn-sm btn-primary" :disabled="!stPendingId || stConfirming" @click="confirmStImport">
                      {{ stConfirmLabel }}
                    </button>
                  </div>
                </div>
                <div v-if="stExpiresAt" class="mt-2 text-[var(--color-text-muted)]">预览暂存至：{{ stExpiresAt }}</div>
              </div>
            </section>

            <section class="rounded-xl border border-[var(--color-border-subtle)] bg-[var(--color-surface-muted)] p-4">
              <h4 class="text-sm font-medium text-[var(--color-text-secondary)]">JanitorAI 聊天迁移</h4>
              <p class="mt-2 text-xs text-[var(--color-text-muted)]">
                填写 JanitorAI 聊天链接后打开页面，扩展会在该页面首次合法捕获时自动提交到本地。
              </p>
              <div class="mt-3 flex gap-2">
                <input
                  v-model="janitorLink"
                  class="input flex-1"
                  placeholder="https://janitorai.com/chats/..."
                />
                <button class="btn btn-sm btn-secondary" @click="openJanitorLinkAndTryCapture">打开并尝试获取</button>
              </div>

              <div class="mt-4 rounded-lg border border-[var(--color-border-subtle)] bg-[var(--color-surface-overlay)] p-3">
                <div class="text-xs text-[var(--color-text-muted)]">
                  {{ pendingLoading ? '正在读取待导入预览...' : (pendingPreview ? '已检测到待导入数据' : '尚未检测到待导入数据') }}
                </div>
                <div v-if="pendingError" class="mt-2 text-xs text-[var(--color-error)]">{{ pendingError }}</div>
                <div v-if="pendingPreview" class="mt-2 space-y-2 text-xs text-[var(--color-text-muted)]">
                  <div>角色名：<span class="text-[var(--color-text)]">{{ pendingPreview.botName || '未知' }}</span></div>
                  <div>消息数：<span class="text-[var(--color-text)]">{{ pendingPreview.messageCount }}</span></div>
                  <div v-if="pendingPreview.sampleMessages?.length" class="mt-1">
                    <div class="text-[var(--color-text-secondary)]">预览：</div>
                    <div
                      class="mt-1 flex gap-2 items-stretch rounded-lg border border-[var(--color-border)] bg-surface-overlay shadow-lg max-h-48 overflow-x-auto overflow-y-hidden px-2 py-1"
                    >
                      <div
                        v-for="(item, idx) in pendingPreview.sampleMessages"
                        :key="`${item.role}_${idx}`"
                        class="shrink-0 flex flex-col w-[200px] h-[140px] min-h-0 min-w-0 px-3 py-2 text-xs border border-[var(--color-border-subtle)] rounded-md bg-[var(--color-surface-muted)] text-left"
                      >
                        <span class="text-[var(--color-text-secondary)] shrink-0 mb-1">{{ item.role === 'assistant' ? '角色' : '用户' }}</span>
                        <div class="text-[var(--color-text-muted)] min-h-0 flex-1 overflow-hidden line-clamp-6 break-words">{{ item.content }}</div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              <div class="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2">
                <div>
                  <div class="mb-1 text-xs text-[var(--color-text-muted)]">目标角色</div>
                  <ModernSelect
                    :key="characterListKey"
                    :model-value="selectedCharacterId"
                    :options="characterOptions"
                    placeholder="选择角色"
                    @update:model-value="(v) => selectedCharacterId = v"
                  />
                </div>
                <div>
                  <div class="mb-1 text-xs text-[var(--color-text-muted)]">Persona（用户身份）</div>
                  <ModernSelect
                    :model-value="selectedPersonaId"
                    :options="personaOptions"
                    placeholder="选择 Persona"
                    @update:model-value="(v) => selectedPersonaId = v"
                  />
                </div>
              </div>
              <label class="mt-3 flex items-center gap-2 text-xs text-[var(--color-text-muted)]">
                <ThemedCheckbox :checked="openAfterImport" @update:checked="openAfterImport = $event" />
                导入后打开该会话
              </label>
              <div class="mt-3">
                <button
                  class="btn btn-sm btn-primary"
                  :disabled="!pendingId || !selectedCharacterId || janitorConfirming"
                  @click="confirmJanitorImport"
                >
                  {{ janitorConfirming ? '导入中...' : '确认导入 Janitor 聊天' }}
                </button>
              </div>
            </section>

            <section class="rounded-xl border border-[var(--color-border-subtle)] bg-[var(--color-surface-muted)] p-4">
              <h4 class="text-sm font-medium text-[var(--color-text-secondary)]">导入 JAI 角色（链接）</h4>
              <p class="mt-2 text-xs text-[var(--color-text-muted)]">
                填写 JanitorAI 公开角色页链接后在新标签页打开；已安装的「SimpleTavern Janitor Bridge」扩展会抓取页面 HTML 并提交到本地，自动提取名称、简介、Personality、Scenario、首句与角色图片。
              </p>
              <div class="mt-3 flex gap-2">
                <input
                  v-model="jaiCharacterUrl"
                  class="input flex-1"
                  placeholder="https://janitorai.com/characters/..."
                />
                <button class="btn btn-sm btn-secondary" @click="openJaiCharacterUrlAndCapture">打开并抓取</button>
              </div>
            </section>
          </div>
        </div>
      </div>
    </div>
  </Transition>
</template>
