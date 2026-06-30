import { computed, ref } from 'vue'
import { apiPost, apiPut } from '../api/http'
import {
  useSettingsImport,
  type SillyTavernImportPreview,
} from './useSettingsImport'
import { notifyMessage } from './useNotify'
import type { CharacterCard, MvuMode, WorldBook } from '../types/models'

export interface EmbeddedCharacterCardPreview {
  card: CharacterCard
  worldbook?: WorldBook | null
}

export interface AvatarCropSavePayload {
  imageData: string
  focusX?: number
  focusY?: number
}

export interface UseEmbeddedAvatarImportOptions {
  getEditingCharacter: () => CharacterCard | null
  saveCharacterAvatar: (
    imageData: string,
    focusX?: number | null,
    focusY?: number | null,
  ) => Promise<EmbeddedCharacterCardPreview | null>
  applyAssistantCard: (card: CharacterCard) => void
  reloadWorldbooks: () => void | Promise<void>
  pushError: (payload: { message: unknown; source: 'assistant' | 'main'; title?: string }) => void
}

const AVATAR_EMBEDDED_MVU_MODE_OPTIONS = [
  { label: 'Regex 兼容', value: 'regex' },
  { label: '指令模式', value: 'directive' },
] as const

function imageDataUrlToPngFile(imageData: string, filename: string): File {
  const base64 = imageData.includes(',') ? imageData.split(',')[1]! : imageData
  const bin = atob(base64)
  const bytes = new Uint8Array(bin.length)
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i)
  return new File([bytes], filename, { type: 'image/png' })
}

/** PNG 头像内嵌角色卡 / ST 预览确认流（角色编辑弹窗内使用）。 */
export function useEmbeddedAvatarImport(options: UseEmbeddedAvatarImportOptions) {
  const { previewSillyTavernImport, materializeSillyTavernPending } = useSettingsImport()
  const showEmbeddedCardConfirmModal = ref(false)
  const embeddedCardPreview = ref<EmbeddedCharacterCardPreview | null>(null)
  const embeddedCardImporting = ref(false)
  const avatarEmbeddedStPendingId = ref('')
  const avatarEmbeddedStExpiresAt = ref('')
  const avatarEmbeddedStPreview = ref<SillyTavernImportPreview | null>(null)
  const avatarEmbeddedEnableMvu = ref(false)
  const avatarEmbeddedMvuMode = ref<MvuMode>('regex')

  const avatarEmbeddedDetectedMvu = computed(() => {
    const mvu = avatarEmbeddedStPreview.value?.mvu
    return Boolean(mvu?.hasTavernHelper || mvu?.hasRegexScripts || mvu?.characterBookCandidateCount)
  })

  const embeddedCardConfirmLabel = computed(() => {
    if (!embeddedCardImporting.value) return '覆盖当前编辑'
    return avatarEmbeddedEnableMvu.value && avatarEmbeddedMvuMode.value === 'directive'
      ? 'MVU Agent 分析中...'
      : '导入中...'
  })

  function resetAvatarEmbeddedStState() {
    avatarEmbeddedStPendingId.value = ''
    avatarEmbeddedStExpiresAt.value = ''
    avatarEmbeddedStPreview.value = null
    avatarEmbeddedEnableMvu.value = false
    avatarEmbeddedMvuMode.value = 'regex'
  }

  function updateAvatarEmbeddedMvuMode(value: string) {
    avatarEmbeddedMvuMode.value = value === 'directive' ? 'directive' : 'regex'
  }

  function clearEmbeddedCardPreviewState() {
    showEmbeddedCardConfirmModal.value = false
    embeddedCardPreview.value = null
    embeddedCardImporting.value = false
    resetAvatarEmbeddedStState()
  }

  async function handleCharacterAvatarSave(payload: AvatarCropSavePayload) {
    resetAvatarEmbeddedStState()
    const embedded = await options.saveCharacterAvatar(
      payload.imageData,
      payload.focusX ?? null,
      payload.focusY ?? null,
    )
    if (embedded?.card) {
      embeddedCardPreview.value = embedded
      try {
        const file = imageDataUrlToPngFile(payload.imageData, 'avatar.png')
        const prev = await previewSillyTavernImport(file)
        avatarEmbeddedStPendingId.value = prev.pendingId
        avatarEmbeddedStExpiresAt.value = prev.expiresAt
        avatarEmbeddedStPreview.value = prev.preview
        avatarEmbeddedMvuMode.value = prev.preview.mvu.suggestedMode || 'regex'
        avatarEmbeddedEnableMvu.value = Boolean(
          prev.preview.mvu.hasTavernHelper
          || prev.preview.mvu.hasRegexScripts
          || prev.preview.mvu.characterBookCandidateCount,
        )
      } catch {
        resetAvatarEmbeddedStState()
      }
      showEmbeddedCardConfirmModal.value = true
    }
  }

  async function confirmImportEmbeddedCard() {
    if (!options.getEditingCharacter() || !embeddedCardPreview.value?.card) {
      clearEmbeddedCardPreviewState()
      return
    }
    embeddedCardImporting.value = true
    try {
      const current = options.getEditingCharacter()!
      let incoming: CharacterCard
      let worldbookPayload: WorldBook | undefined
      let mergeWarnings: string[] | undefined

      if (avatarEmbeddedStPendingId.value) {
        const built = await materializeSillyTavernPending({
          pendingId: avatarEmbeddedStPendingId.value,
          enableMvuCompatibility: avatarEmbeddedEnableMvu.value,
          mvuMode: avatarEmbeddedMvuMode.value,
          avatarFilename: current.avatar || null,
        })
        incoming = built.character as unknown as CharacterCard
        worldbookPayload = built.worldbook ? (built.worldbook as unknown as WorldBook) : undefined
        mergeWarnings = built.warnings
      } else {
        incoming = embeddedCardPreview.value.card
        worldbookPayload = embeddedCardPreview.value.worldbook ?? undefined
      }

      let attachedWorldBookIds: string[] = []
      if (worldbookPayload) {
        const savedBook = await apiPost<WorldBook>('/api/worldbooks', worldbookPayload)
        attachedWorldBookIds = [savedBook.id]
        await options.reloadWorldbooks()
      }
      const mergedCard: CharacterCard = {
        ...current,
        name: incoming.name,
        description: incoming.description,
        personality: incoming.personality,
        scenario: incoming.scenario,
        firstMessage: incoming.firstMessage,
        exampleDialogue: incoming.exampleDialogue,
        systemPrompt: incoming.systemPrompt,
        extraFirstMessageEntries: Array.isArray(incoming.extraFirstMessageEntries) ? incoming.extraFirstMessageEntries : [],
        mvuEnabled: incoming.mvuEnabled === true,
        mvuMode: incoming.mvuMode === 'directive' ? 'directive' : 'regex',
        mvuDirective: typeof incoming.mvuDirective === 'string' ? incoming.mvuDirective : null,
        contentRegexRules: Array.isArray(incoming.contentRegexRules) ? incoming.contentRegexRules : [],
        initialStateTables: Array.isArray(incoming.initialStateTables)
          ? incoming.initialStateTables
          : current.initialStateTables,
        attachedWorldBookIds,
        avatar: current.avatar || incoming.avatar,
        avatarFocusX: current.avatarFocusX ?? incoming.avatarFocusX ?? null,
        avatarFocusY: current.avatarFocusY ?? incoming.avatarFocusY ?? null,
      }
      await apiPut<CharacterCard>('/api/assistant/workspace/character-card', mergedCard)
      options.applyAssistantCard(mergedCard)
      clearEmbeddedCardPreviewState()
      if (mergeWarnings?.length) {
        void notifyMessage(mergeWarnings.join('；'), { title: '内嵌卡合并提示' })
      }
    } catch (error) {
      options.pushError({ message: error, source: 'main', title: '导入 PNG 内嵌角色数据失败' })
      embeddedCardImporting.value = false
    }
  }

  return {
    showEmbeddedCardConfirmModal,
    embeddedCardPreview,
    embeddedCardImporting,
    avatarEmbeddedStPreview,
    avatarEmbeddedStExpiresAt,
    avatarEmbeddedEnableMvu,
    avatarEmbeddedMvuMode,
    avatarEmbeddedMvuModeOptions: AVATAR_EMBEDDED_MVU_MODE_OPTIONS,
    avatarEmbeddedDetectedMvu,
    embeddedCardConfirmLabel,
    clearEmbeddedCardPreviewState,
    handleCharacterAvatarSave,
    confirmImportEmbeddedCard,
    updateAvatarEmbeddedMvuMode,
  }
}
