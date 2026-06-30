// @vitest-environment happy-dom
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createApp, type App } from 'vue'
import type { CharacterCard } from '../types/models'

const materializeSillyTavernPending = vi.fn()
const previewSillyTavernImport = vi.fn()
const apiPost = vi.fn()
const apiPut = vi.fn()

vi.mock('./useSettingsImport', () => ({
  useSettingsImport: () => ({
    previewSillyTavernImport,
    materializeSillyTavernPending,
  }),
}))

vi.mock('../api/http', () => ({
  apiPost: (...args: unknown[]) => apiPost(...args),
  apiPut: (...args: unknown[]) => apiPut(...args),
}))

vi.mock('./useNotify', () => ({
  notifyMessage: vi.fn(),
}))

import { useEmbeddedAvatarImport } from './useEmbeddedAvatarImport'

function baseCharacter(overrides: Partial<CharacterCard> = {}): CharacterCard {
  return {
    id: 'char-1',
    name: '当前',
    description: '',
    personality: '',
    scenario: '',
    firstMessage: '',
    exampleDialogue: '',
    systemPrompt: '',
    attachedWorldBookIds: [],
    ...overrides,
  } as CharacterCard
}

type Api = ReturnType<typeof useEmbeddedAvatarImport>

function withSetup(editing: CharacterCard | null): {
  api: Api
  app: App
  applyAssistantCard: ReturnType<typeof vi.fn>
  pushError: ReturnType<typeof vi.fn>
} {
  let api!: Api
  const applyAssistantCard = vi.fn()
  const pushError = vi.fn()
  const app = createApp({
    setup() {
      api = useEmbeddedAvatarImport({
        getEditingCharacter: () => editing,
        saveCharacterAvatar: vi.fn(),
        applyAssistantCard,
        reloadWorldbooks: vi.fn(),
        pushError,
      })
      return () => null
    },
  })
  app.mount(document.createElement('div'))
  return { api, app, applyAssistantCard, pushError }
}

describe('useEmbeddedAvatarImport', () => {
  beforeEach(() => {
    materializeSillyTavernPending.mockReset()
    previewSillyTavernImport.mockReset()
    apiPost.mockReset()
    apiPut.mockReset()
  })

  it('confirmImportEmbeddedCard 在 workspace 落库失败后关闭弹窗', async () => {
    const editing = baseCharacter()
    const saveCharacterAvatar = vi.fn().mockResolvedValue({
      card: baseCharacter({ name: '内嵌' }),
    })
    let api!: Api
    const applyAssistantCard = vi.fn()
    const pushError = vi.fn()
    const app = createApp({
      setup() {
        api = useEmbeddedAvatarImport({
          getEditingCharacter: () => editing,
          saveCharacterAvatar,
          applyAssistantCard,
          reloadWorldbooks: vi.fn(),
          pushError,
        })
        return () => null
      },
    })
    app.mount(document.createElement('div'))

    previewSillyTavernImport.mockResolvedValue({
      pendingId: 'pending-1',
      expiresAt: '2099',
      preview: {
        characterName: 'ST',
        worldBookName: '',
        worldBookEntryCount: 0,
        mvu: {
          hasTavernHelper: false,
          hasRegexScripts: false,
          regexScriptCount: 0,
          characterBookCandidateCount: 0,
          characterBookCandidates: [],
          suggestedMode: 'regex',
        },
      },
    })
    materializeSillyTavernPending.mockResolvedValue({
      character: { name: 'ST角色' },
      worldbook: null,
      warnings: [],
    })
    apiPut.mockRejectedValue(new Error('workspace save failed'))

    await api.handleCharacterAvatarSave({ imageData: 'data:image/png;base64,aa==' })
    expect(api.showEmbeddedCardConfirmModal.value).toBe(true)
    await api.confirmImportEmbeddedCard()

    expect(materializeSillyTavernPending).toHaveBeenCalledTimes(1)
    expect(api.showEmbeddedCardConfirmModal.value).toBe(false)
    expect(api.embeddedCardPreview.value).toBeNull()
    expect(applyAssistantCard).toHaveBeenCalledWith(
      expect.objectContaining({ name: 'ST角色' }),
    )
    expect(pushError).toHaveBeenCalled()
    app.unmount()
  })

  it('confirmImportEmbeddedCard 在世界书已创建但落库失败时绑定世界书到本地草稿', async () => {
    const editing = baseCharacter()
    const { api, app, applyAssistantCard } = withSetup(editing)
    api.embeddedCardPreview.value = {
      card: baseCharacter({ name: 'ST角色' }),
      worldbook: { id: 'wb-temp', name: '书', entries: [] } as never,
    }
    api.showEmbeddedCardConfirmModal.value = true

    apiPost.mockResolvedValue({ id: 'wb-saved', name: '书', entries: [] })
    apiPut.mockRejectedValue(new Error('workspace save failed'))

    await api.confirmImportEmbeddedCard()

    expect(applyAssistantCard).toHaveBeenCalledWith(
      expect.objectContaining({
        name: 'ST角色',
        attachedWorldBookIds: ['wb-saved'],
      }),
    )
    expect(api.showEmbeddedCardConfirmModal.value).toBe(false)
    app.unmount()
  })
})
