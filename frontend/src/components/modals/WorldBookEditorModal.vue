<script setup lang="ts">
/**
 * 世界书整书编辑：书名、条目 CRUD、排序、PUT 保存。
 */
import { computed, ref, watch } from 'vue'
import { countTokensForText } from '../../utils/tokenEstimate'
import { ChevronDown, ChevronUp, Copy, Pencil, Plus, Trash2, X } from 'lucide-vue-next'
import { apiDelete, apiGet, apiPut } from '../../api/http'
import type { WorldBook, WorldBookEntry } from '../../types/models'
import { formatApiError, validateWorldBookEntry } from '../../utils/worldBookValidation'
import WorldBookEntryEditModal from './WorldBookEntryEditModal.vue'

const props = defineProps<{
  show: boolean
  worldBookId: string | null
}>()

const emit = defineEmits<{
  'update:show': [boolean]
  /** 保存成功后通知父级刷新列表 */
  saved: []
  /** 整书删除成功后（含 API 成功），父级刷新并移出会话顺序 */
  deleted: [worldbookId: string]
}>()

const book = ref<WorldBook | null>(null)
const loading = ref(false)
const saving = ref(false)
const saveError = ref('')
const bookName = ref('')

const entryEditShow = ref(false)
const editingEntry = ref<WorldBookEntry | null>(null)

const entryTokenCounts = ref<Record<string, number | null>>({})
let entryTokenDebounce: ReturnType<typeof setTimeout> | null = null

async function runEntryTokenCounts() {
  if (!book.value || !props.show) return
  const sorted = [...book.value.entries].sort((a, b) => a.orderIndex - b.orderIndex)
  const results = await Promise.all(
    sorted.map(async (e) => {
      const n = await countTokensForText(e.content || '')
      return [e.id, n] as const
    }),
  )
  const next: Record<string, number | null> = {}
  for (const [id, n] of results) next[id] = n
  entryTokenCounts.value = next
}

function scheduleEntryTokenCounts() {
  if (entryTokenDebounce) clearTimeout(entryTokenDebounce)
  entryTokenDebounce = setTimeout(() => {
    entryTokenDebounce = null
    void runEntryTokenCounts()
  }, 400)
}

function entryTokenHint(id: string): string {
  const v = entryTokenCounts.value[id]
  if (v === undefined) return '约 …'
  if (v === null) return '无法估算'
  return `约 ${v} tokens`
}

const sortedEntries = computed(() => {
  const list = book.value?.entries ?? []
  return [...list].sort((a, b) => a.orderIndex - b.orderIndex)
})

function newEntry(): WorldBookEntry {
  return {
    id: crypto.randomUUID().replace(/-/g, ''),
    title: '',
    regex: '',
    content: '',
    enabled: true,
    orderIndex: (book.value?.entries.length ?? 0),
  }
}

async function loadBook() {
  saveError.value = ''
  if (!props.worldBookId) {
    book.value = null
    bookName.value = ''
    return
  }
  loading.value = true
  try {
    const b = await apiGet<WorldBook>(`/api/worldbooks/${props.worldBookId}`)
    book.value = b
    bookName.value = b.name
  } catch (e) {
    saveError.value = formatApiError(e)
    book.value = null
  } finally {
    loading.value = false
  }
}

watch(
  () => [props.show, props.worldBookId] as const,
  ([open, id]) => {
    if (open && id) loadBook()
    if (!open) {
      book.value = null
      bookName.value = ''
      saveError.value = ''
      entryEditShow.value = false
      editingEntry.value = null
      entryTokenCounts.value = {}
      if (entryTokenDebounce) {
        clearTimeout(entryTokenDebounce)
        entryTokenDebounce = null
      }
    }
  },
)

watch(
  () => book.value?.entries,
  () => {
    if (book.value && props.show) scheduleEntryTokenCounts()
  },
  { deep: true },
)

function close() {
  emit('update:show', false)
}

function reindexEntries() {
  if (!book.value) return
  const sorted = [...book.value.entries].sort((a, b) => a.orderIndex - b.orderIndex)
  sorted.forEach((e, i) => {
    e.orderIndex = i
  })
  book.value.entries = sorted
}

function addEntry() {
  if (!book.value) return
  book.value.entries.push(newEntry())
  reindexEntries()
}

function removeEntry(id: string) {
  if (!book.value) return
  if (!confirm('删除该条目？')) return
  book.value.entries = book.value.entries.filter((e) => e.id !== id)
  reindexEntries()
}

function duplicateEntry(id: string) {
  if (!book.value) return
  const src = book.value.entries.find((e) => e.id === id)
  if (!src) return
  const copy = JSON.parse(JSON.stringify(src)) as WorldBookEntry
  copy.id = crypto.randomUUID().replace(/-/g, '')
  copy.title = copy.title ? `${copy.title}（副本）` : '副本'
  book.value.entries.push(copy)
  reindexEntries()
}

function moveEntry(id: string, dir: -1 | 1) {
  if (!book.value) return
  const sorted = [...book.value.entries].sort((a, b) => a.orderIndex - b.orderIndex)
  const i = sorted.findIndex((e) => e.id === id)
  if (i < 0) return
  const j = i + dir
  if (j < 0 || j >= sorted.length) return
  const tmp = sorted[i]!
  sorted[i] = sorted[j]!
  sorted[j] = tmp
  sorted.forEach((e, idx) => {
    e.orderIndex = idx
  })
  book.value.entries = sorted
}

function openEntryEdit(entry: WorldBookEntry) {
  editingEntry.value = JSON.parse(JSON.stringify(entry)) as WorldBookEntry
  entryEditShow.value = true
}

function onEntryApply(updated: WorldBookEntry) {
  if (!book.value) return
  const idx = book.value.entries.findIndex((e) => e.id === updated.id)
  if (idx >= 0) book.value.entries[idx] = updated
  reindexEntries()
}

function entrySummary(e: WorldBookEntry): string {
  const t = (e.title || '').trim() || '（无标题）'
  return e.enabled ? `${t} · 启用` : `${t} · 已禁用`
}

function validateAll(): string | null {
  if (!book.value) return '数据未加载'
  const name = bookName.value.trim()
  if (!name) return '请填写世界书名称'
  for (const e of book.value.entries) {
    const err = validateWorldBookEntry(e)
    if (err) return err
  }
  return null
}

const deleting = ref(false)

async function deleteWholeBook() {
  if (!props.worldBookId) return
  if (!confirm('确认删除该世界书？条目将一并删除，且不可恢复。')) return
  deleting.value = true
  saveError.value = ''
  const id = props.worldBookId
  try {
    await apiDelete(`/api/worldbooks/${id}`)
    emit('deleted', id)
    emit('update:show', false)
  } catch (e) {
    saveError.value = formatApiError(e)
  } finally {
    deleting.value = false
  }
}

async function save() {
  if (!book.value || !props.worldBookId) return
  const err = validateAll()
  if (err) {
    saveError.value = err
    return
  }
  reindexEntries()
  const now = new Date().toISOString()
  const payload: WorldBook = {
    ...book.value,
    id: props.worldBookId,
    name: bookName.value.trim(),
    entries: book.value.entries.map((e, i) => ({ ...e, orderIndex: i })),
    updatedAt: now,
  }
  saving.value = true
  saveError.value = ''
  try {
    const saved = await apiPut<WorldBook>(`/api/worldbooks/${props.worldBookId}`, payload)
    book.value = saved
    bookName.value = saved.name
    emit('saved')
    emit('update:show', false)
  } catch (e) {
    saveError.value = formatApiError(e)
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <Teleport to="body">
    <Transition name="modal">
      <div v-if="show" class="modal">
        <div class="modal-backdrop" @click="close"></div>
        <div
          class="modal-content w-[min(92vw,560px)] max-h-[90vh] theme-panel-bg border border-[var(--color-border)] rounded-2xl shadow-xl backdrop-saturate-[1.8]"
          style="backdrop-filter: blur(var(--blur-heavy)); -webkit-backdrop-filter: blur(var(--blur-heavy))"
        >
          <div class="modal-header shrink-0">
            <h3 class="modal-title">编辑世界书</h3>
            <button type="button" class="modal-close" aria-label="关闭" @click="close">
              <X class="w-5 h-5" />
            </button>
          </div>

          <div class="modal-body overflow-y-auto custom-scrollbar min-h-0 space-y-4">
            <div v-if="loading" class="text-center text-[var(--color-text-muted)] py-8">加载中…</div>
            <template v-else-if="book">
              <div
                v-if="saveError"
                class="text-sm text-[var(--color-error)] bg-[var(--color-surface-overlay)] border border-[var(--color-border)] rounded-lg px-3 py-2"
              >
                {{ saveError }}
              </div>

              <div class="space-y-1.5">
                <label class="text-xs font-medium text-[var(--color-text-secondary)]">书名</label>
                <input v-model="bookName" type="text" class="input w-full" placeholder="世界书名称" />
              </div>

              <div class="flex items-center justify-between gap-2 pt-2">
                <span class="text-sm font-medium text-[var(--color-text-secondary)]">条目</span>
                <button type="button" class="btn btn-sm btn-secondary inline-flex items-center gap-1" @click="addEntry">
                  <Plus class="w-4 h-4" />
                  新增条目
                </button>
              </div>

              <div class="space-y-2 max-h-[min(50vh,420px)] overflow-y-auto custom-scrollbar pr-1">
                <div
                  v-for="e in sortedEntries"
                  :key="e.id"
                  class="rounded-lg border border-[var(--color-border-subtle)] bg-surface-muted p-3 flex flex-col gap-2"
                >
                  <div class="flex items-start justify-between gap-2">
                    <div class="min-w-0 flex-1">
                      <div class="text-sm text-[var(--color-text)] font-medium truncate">{{ entrySummary(e) }}</div>
                      <div class="text-xs text-[var(--color-text-muted)] mt-0.5 truncate">
                        {{ (e.regex || '').trim() ? '已填正则' : '无正则' }}
                      </div>
                      <div class="text-[10px] text-[var(--color-text-muted)] mt-0.5">{{ entryTokenHint(e.id) }}</div>
                    </div>
                    <div class="flex flex-wrap items-center gap-1 shrink-0">
                      <button
                        type="button"
                        class="p-1.5 rounded-lg text-[var(--color-text-muted)] hover:text-[var(--color-text)] hover:bg-surface-hover"
                        title="上移"
                        @click="moveEntry(e.id, -1)"
                      >
                        <ChevronUp class="w-4 h-4" />
                      </button>
                      <button
                        type="button"
                        class="p-1.5 rounded-lg text-[var(--color-text-muted)] hover:text-[var(--color-text)] hover:bg-surface-hover"
                        title="下移"
                        @click="moveEntry(e.id, 1)"
                      >
                        <ChevronDown class="w-4 h-4" />
                      </button>
                      <button
                        type="button"
                        class="p-1.5 rounded-lg text-[var(--color-text-muted)] hover:text-brand hover:bg-surface-hover"
                        title="编辑"
                        @click="openEntryEdit(e)"
                      >
                        <Pencil class="w-4 h-4" />
                      </button>
                      <button
                        type="button"
                        class="p-1.5 rounded-lg text-[var(--color-text-muted)] hover:text-[var(--color-text)] hover:bg-surface-hover"
                        title="复制"
                        @click="duplicateEntry(e.id)"
                      >
                        <Copy class="w-4 h-4" />
                      </button>
                      <button
                        type="button"
                        class="p-1.5 rounded-lg text-[var(--color-text-muted)] hover:text-error hover:bg-surface-hover"
                        title="删除"
                        @click="removeEntry(e.id)"
                      >
                        <Trash2 class="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                </div>
                <div
                  v-if="sortedEntries.length === 0"
                  class="text-xs text-[var(--color-text-muted)] text-center py-6 border border-dashed border-[var(--color-border-subtle)] rounded-lg"
                >
                  暂无条目，点击「新增条目」添加。
                </div>
              </div>
            </template>
            <div v-else-if="!loading" class="text-center text-[var(--color-text-muted)] py-6">无法加载世界书</div>
          </div>

          <div class="modal-footer shrink-0 flex flex-wrap items-center justify-between gap-2">
            <button
              type="button"
              class="btn btn-secondary text-error"
              :disabled="saving || deleting || loading || !book"
              @click="deleteWholeBook"
            >
              {{ deleting ? '删除中…' : '删除世界书' }}
            </button>
            <div class="flex justify-end gap-3 ml-auto">
              <button type="button" class="btn btn-secondary" :disabled="saving || deleting" @click="close">取消</button>
              <button type="button" class="btn btn-primary" :disabled="saving || deleting || loading || !book" @click="save">
                {{ saving ? '保存中…' : '保存' }}
              </button>
            </div>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>

  <WorldBookEntryEditModal
    :show="entryEditShow"
    :entry="editingEntry"
    @update:show="(v) => (entryEditShow = v)"
    @apply="onEntryApply"
  />
</template>

<style scoped>
.custom-scrollbar::-webkit-scrollbar {
  width: 4px;
}
.custom-scrollbar::-webkit-scrollbar-thumb {
  background: var(--color-border, rgba(255, 255, 255, 0.2));
  border-radius: 2px;
}
</style>
