<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { apiGet } from '../../api/http'
import { useSettingsImport } from '../../composables/useSettingsImport'
import { notifyMessage } from '../../composables/useNotify'
import type { CharacterCard, Chat, UserPersona } from '../../types/models'
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

const { importSettingsFile, refreshDataAfterImport, formatImportResultMessage } = useSettingsImport()

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

const personaOptions = computed(() => [
  { label: '（不指定 Persona）', value: '' },
  ...props.personas.map((p) => ({ label: p.name || p.id, value: p.id })),
])

const characterOptions = computed(() =>
  props.characters.map((c) => ({ label: c.name || c.id, value: c.id })),
)

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
  } finally {
    input.value = ''
  }
}

async function handleStImportChange(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  try {
    const result = await importSettingsFile(file)
    await refreshDataAfterImport()
    await notifyMessage(formatImportResultMessage(result))
  } catch (err) {
    if (props.pushError) {
      props.pushError({ message: err instanceof Error ? err.message : String(err), source: 'main', title: 'SillyTavern 导入失败' })
    } else {
      await notifyMessage(err instanceof Error ? err.message : String(err))
    }
  } finally {
    input.value = ''
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
              <p class="mt-2 text-xs text-[var(--color-text-muted)]">支持 txt/json/zip，逻辑与设置中的“导入数据”一致。</p>
              <p class="mt-1 text-xs text-[var(--color-text-muted)]">SillyTavern 专用按钮仅支持 PNG/JSON 角色卡，不支持聊天记录导入。</p>
              <div class="mt-3 flex flex-wrap gap-2">
                <button class="btn btn-sm btn-secondary" @click="triggerImport">选择文件导入</button>
                <button class="btn btn-sm btn-secondary" @click="triggerStImport">导入 SillyTavern 数据</button>
                <input ref="importInputRef" type="file" class="hidden" accept=".txt,.json,.zip" @change="handleImportChange" />
                <input ref="stImportInputRef" type="file" class="hidden" accept=".png,.json" @change="handleStImportChange" />
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
