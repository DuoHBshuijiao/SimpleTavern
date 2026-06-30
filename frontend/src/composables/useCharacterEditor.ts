import { computed, ref, watch, type MaybeRefOrGetter, toValue } from 'vue'
import { apiGet } from '../api/http'
import type { CharacterCard, ExtraFirstMessageEntry, WorldBook } from '../types/models'

export interface UseCharacterEditorOptions {
  editingCharacter: MaybeRefOrGetter<CharacterCard | null>
  showEditor: MaybeRefOrGetter<boolean>
}

/** 角色编辑弹窗：额外首句、绑定世界书等局部状态（不含助手工作区）。 */
export function useCharacterEditor(options: UseCharacterEditorOptions) {
  const characterEditorWorldbooks = ref<WorldBook[]>([])
  const addCharacterEditorWbId = ref('')
  const characterEditorWbDraggingIdx = ref<number | null>(null)
  const extraFirstMessageDraft = ref('')

  const extraFirstMessageEntriesIndexed = computed(() => {
    const ec = toValue(options.editingCharacter)
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
    const ec = toValue(options.editingCharacter)
    if (!ec) return
    const t = extraFirstMessageDraft.value.trim()
    if (!t) return
    if (!Array.isArray(ec.extraFirstMessageEntries)) ec.extraFirstMessageEntries = []
    ec.extraFirstMessageEntries.push({ text: t, chip: false })
  }

  function appendExtraFirstMessagePlus() {
    const ec = toValue(options.editingCharacter)
    if (!ec) return
    const t = extraFirstMessageDraft.value.trim()
    if (!t) return
    if (!Array.isArray(ec.extraFirstMessageEntries)) ec.extraFirstMessageEntries = []
    ec.extraFirstMessageEntries.push({ text: t, chip: true })
    extraFirstMessageDraft.value = ''
  }

  function removeExtraFirstMessageAt(index: number) {
    const ec = toValue(options.editingCharacter)
    if (!ec?.extraFirstMessageEntries) return
    ec.extraFirstMessageEntries.splice(index, 1)
  }

  function fillExtraFirstDraft(text: string) {
    extraFirstMessageDraft.value = text
  }

  function avatarObjectPositionByFocus(focusX?: number | null, focusY?: number | null): string {
    const x = typeof focusX === 'number' ? focusX : 50
    const y = typeof focusY === 'number' ? focusY : 50
    return `${x}% ${y}%`
  }

  async function loadCharacterEditorWorldbooks() {
    try {
      characterEditorWorldbooks.value = await apiGet<WorldBook[]>('/api/worldbooks')
    } catch {
      characterEditorWorldbooks.value = []
    }
  }

  function ensureCharacterAttachedWbIds() {
    const c = toValue(options.editingCharacter)
    if (!c) return
    if (!Array.isArray(c.attachedWorldBookIds)) c.attachedWorldBookIds = []
  }

  function characterEditorWorldBookName(id: string) {
    return characterEditorWorldbooks.value.find((b) => b.id === id)?.name || id
  }

  const characterEditorWorldBookSelectOptions = computed(() => {
    const c = toValue(options.editingCharacter)
    if (!c) return []
    const taken = new Set(c.attachedWorldBookIds || [])
    return characterEditorWorldbooks.value
      .filter((b) => !taken.has(b.id))
      .map((b) => ({ label: b.name || b.id, value: b.id }))
  })

  function addCharacterEditorWorldBook() {
    const ec = toValue(options.editingCharacter)
    if (!ec || !addCharacterEditorWbId.value) return
    ensureCharacterAttachedWbIds()
    const ids = ec.attachedWorldBookIds!
    if (!ids.includes(addCharacterEditorWbId.value)) ids.push(addCharacterEditorWbId.value)
    addCharacterEditorWbId.value = ''
  }

  function removeCharacterEditorWorldBook(worldbookId: string) {
    const ec = toValue(options.editingCharacter)
    if (!ec?.attachedWorldBookIds) return
    ec.attachedWorldBookIds = ec.attachedWorldBookIds.filter((id) => id !== worldbookId)
  }

  function moveCharacterEditorWorldBook(worldbookId: string, direction: -1 | 1) {
    const c = toValue(options.editingCharacter)
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
    const c = toValue(options.editingCharacter)
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

  function resetEditorTransientState() {
    characterEditorWbDraggingIdx.value = null
    addCharacterEditorWbId.value = ''
    extraFirstMessageDraft.value = ''
  }

  function onEditorOpened() {
    ensureCharacterAttachedWbIds()
    void loadCharacterEditorWorldbooks()
    extraFirstMessageDraft.value = ''
  }

  watch(
    () => toValue(options.showEditor),
    (open, wasOpen) => {
      if (open && toValue(options.editingCharacter)) {
        onEditorOpened()
      } else if (!open && wasOpen) {
        resetEditorTransientState()
      }
    },
  )

  return {
    characterEditorWorldbooks,
    addCharacterEditorWbId,
    characterEditorWbDraggingIdx,
    extraFirstMessageDraft,
    extraFirstMessageEntriesIndexed,
    hasAnyExtraFirstEntries,
    displayExtraEntryLabel,
    extraEntryIsEmpty,
    appendExtraFirstMessageCheck,
    appendExtraFirstMessagePlus,
    removeExtraFirstMessageAt,
    fillExtraFirstDraft,
    avatarObjectPositionByFocus,
    loadCharacterEditorWorldbooks,
    ensureCharacterAttachedWbIds,
    characterEditorWorldBookName,
    characterEditorWorldBookSelectOptions,
    addCharacterEditorWorldBook,
    removeCharacterEditorWorldBook,
    moveCharacterEditorWorldBook,
    handleCharacterEditorWbDragStart,
    handleCharacterEditorWbDragOver,
    handleCharacterEditorWbDragEnd,
    resetEditorTransientState,
    onEditorOpened,
  }
}
