<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { apiGet } from '../../api/http'
import { useSettingsImport } from '../../composables/useSettingsImport'
import type { CharacterCard, Chat, UserPersona } from '../../types/models'
import ModernSelect from '../ModernSelect.vue'

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
}>()

const emit = defineEmits<{
  (e: 'update:show', value: boolean): void
  (e: 'janitor-imported', payload: { chatId: string; characterId: string | null; openAfterImport: boolean }): void
}>()

const { importSettingsFile, refreshDataAfterImport, formatImportResultMessage } = useSettingsImport()

const importInputRef = ref<HTMLInputElement | null>(null)
const htmlInputRef = ref<HTMLInputElement | null>(null)

const janitorLink = ref('')
const openAfterImport = ref(true)
const pendingLoading = ref(false)
const pendingError = ref('')
const pendingPreview = ref<JanitorPendingPreview | null>(null)
const selectedCharacterId = ref('')
const selectedPersonaId = ref('')
const janitorConfirming = ref(false)
const htmlImporting = ref(false)

const personaOptions = computed(() => [
  { label: '（不指定 Persona）', value: '' },
  ...props.personas.map((p) => ({ label: p.name || p.id, value: p.id })),
])

const characterOptions = computed(() =>
  props.characters.map((c) => ({ label: c.name || c.id, value: c.id })),
)

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

function close() {
  emit('update:show', false)
}

function triggerImport() {
  importInputRef.value?.click()
}

function triggerHtmlImport() {
  htmlInputRef.value?.click()
}

async function handleImportChange(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  try {
    const result = await importSettingsFile(file)
    await refreshDataAfterImport()
    alert(formatImportResultMessage(result))
  } catch (err) {
    alert(err instanceof Error ? err.message : String(err))
  } finally {
    input.value = ''
  }
}

async function openJanitorLinkAndTryCapture() {
  const raw = janitorLink.value.trim()
  if (!raw) {
    alert('请先填写 JanitorAI 聊天链接。')
    return
  }
  let parsed: URL
  try {
    parsed = new URL(raw)
  } catch {
    alert('链接格式无效。')
    return
  }
  if (!/(\.|^)janitorai\.com$/i.test(parsed.hostname)) {
    alert('仅支持 JanitorAI 链接。')
    return
  }
  parsed.searchParams.set('_st_import', '1')
  parsed.searchParams.set('_st_ts', String(Date.now()))
  parsed.searchParams.set('_st_app_base', window.location.origin)
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
    alert('未检测到待导入的数据。')
    return
  }
  if (!selectedCharacterId.value) {
    alert('请选择角色。')
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
    alert(`导入完成：${(result.imported || []).join(', ') || '无'}${result.warnings?.length ? '\n警告：' + result.warnings.join('; ') : ''}`)
    emit('janitor-imported', {
      chatId: result.chat.id,
      characterId: result.chat.characterId ?? null,
      openAfterImport: openAfterImport.value,
    })
    close()
  } catch (err) {
    alert(err instanceof Error ? err.message : String(err))
  } finally {
    janitorConfirming.value = false
  }
}

async function handleCharacterHtmlChange(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  htmlImporting.value = true
  try {
    const fd = new FormData()
    fd.append('file', file)
    const r = await fetch('/api/import/janitor/character-html', {
      method: 'POST',
      body: fd,
    })
    if (!r.ok) {
      throw new Error(await r.text())
    }
    const result = (await r.json()) as { characterName?: string; warnings?: string[] }
    await refreshDataAfterImport()
    alert(`角色导入完成：${result.characterName || '已创建角色'}${result.warnings?.length ? '\n警告：' + result.warnings.join('; ') : ''}`)
  } catch (err) {
    alert(err instanceof Error ? err.message : String(err))
  } finally {
    htmlImporting.value = false
    input.value = ''
  }
}
</script>

<template>
  <Transition name="modal">
    <div v-if="show" class="modal">
      <div class="modal-backdrop" @click="close"></div>
      <div class="modal-content chat-modal-width-900-90 glass-panel theme-panel-bg backdrop-blur-2xl backdrop-saturate-[1.8] border border-[var(--color-border)]">
        <div class="modal-header border-b border-[var(--color-border-subtle)]">
          <h3 class="modal-title text-[var(--color-text)]">导入</h3>
          <button class="modal-close text-[var(--color-text-muted)] hover:text-[var(--color-text)]" @click="close">×</button>
        </div>
        <div class="modal-body">
          <div class="max-h-[65vh] space-y-4 overflow-y-auto pr-1">
            <section class="rounded-xl border border-[var(--color-border-subtle)] bg-[var(--color-surface-muted)] p-4">
              <h4 class="text-sm font-medium text-[var(--color-text-secondary)]">本地文件导入</h4>
              <p class="mt-2 text-xs text-[var(--color-text-muted)]">支持 txt/json/zip，逻辑与设置中的“导入数据”一致。</p>
              <div class="mt-3">
                <button class="btn btn-sm btn-secondary" @click="triggerImport">选择文件导入</button>
                <input ref="importInputRef" type="file" class="hidden" accept=".txt,.json,.zip" @change="handleImportChange" />
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
                  <div v-if="pendingPreview.sampleMessages?.length" class="space-y-1">
                    <div class="text-[var(--color-text-secondary)]">预览：</div>
                    <div
                      v-for="(item, idx) in pendingPreview.sampleMessages"
                      :key="`${item.role}_${idx}`"
                      class="rounded-md border border-[var(--color-border-subtle)] bg-[var(--color-surface-muted)] px-2 py-1"
                    >
                      <span class="text-[var(--color-text-secondary)]">{{ item.role === 'assistant' ? '角色' : '用户' }}：</span>
                      <span>{{ item.content }}</span>
                    </div>
                  </div>
                </div>
              </div>

              <div class="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2">
                <div>
                  <div class="mb-1 text-xs text-[var(--color-text-muted)]">目标角色</div>
                  <ModernSelect
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
                <input v-model="openAfterImport" type="checkbox" />
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
              <h4 class="text-sm font-medium text-[var(--color-text-secondary)]">导入 JAI 角色 HTML</h4>
              <p class="mt-2 text-xs text-[var(--color-text-muted)]">
                上传完整角色页 HTML，自动提取名称、简介、Personality、Scenario、首句与角色图片。
              </p>
              <div class="mt-3">
                <button class="btn btn-sm btn-secondary" :disabled="htmlImporting" @click="triggerHtmlImport">
                  {{ htmlImporting ? '导入中...' : '选择 HTML 文件' }}
                </button>
                <input ref="htmlInputRef" type="file" class="hidden" accept=".html,.htm,text/html" @change="handleCharacterHtmlChange" />
              </div>
            </section>
          </div>
        </div>
      </div>
    </div>
  </Transition>
</template>
