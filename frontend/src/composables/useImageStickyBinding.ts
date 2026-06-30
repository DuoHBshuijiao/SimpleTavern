import { computed, ref, watch } from 'vue'
import type { Chat } from '../types/models'

export interface ImageStickyBinding {
  chatId: string
  model: string
  presetId: string | null
}

export interface UseImageStickyBindingOptions {
  /** 当前会话 getter */
  getActiveChat: () => Chat | null | undefined
  /** 全局默认模型 getter（会话未覆盖 model 时回退） */
  getDefaultModel: () => string | undefined
}

type ImageStickyPersistRow = { model: string; presetId: string | null }

/**
 * 图片占位符「粘性绑定」与生成失败回退对话框。提炼自 ChatPage.vue，行为不变。
 *
 * 占位符重试成功后：在同一会话且同模型 + 同 API 预设下自动对上游使用 [image] 占位，
 * 直到切换模型/预设或换会话（localStorage 按 chatId 持久化）。
 */
export function useImageStickyBinding(options: UseImageStickyBindingOptions) {
  const { getActiveChat, getDefaultModel } = options

  const IMAGE_STICKY_STORAGE_KEY = 'SimpleTavern:imageStickyBinding:v1'

  function loadImageStickyMap(): Record<string, ImageStickyPersistRow> {
    if (typeof window === 'undefined') return {}
    try {
      const raw = localStorage.getItem(IMAGE_STICKY_STORAGE_KEY)
      if (!raw) return {}
      const o = JSON.parse(raw) as unknown
      if (!o || typeof o !== 'object' || Array.isArray(o)) return {}
      return o as Record<string, ImageStickyPersistRow>
    } catch {
      return {}
    }
  }

  function persistImageStickyMap(map: Record<string, ImageStickyPersistRow>) {
    if (typeof window === 'undefined') return
    try {
      localStorage.setItem(IMAGE_STICKY_STORAGE_KEY, JSON.stringify(map))
    } catch {
      /* quota / 隐私模式 */
    }
  }

  function saveImageStickyBindingRow(bind: ImageStickyBinding) {
    const map = loadImageStickyMap()
    map[bind.chatId] = { model: bind.model, presetId: bind.presetId }
    persistImageStickyMap(map)
  }

  function removeImageStickyBindingRow(chatId: string) {
    const map = loadImageStickyMap()
    if (!(chatId in map)) return
    delete map[chatId]
    persistImageStickyMap(map)
  }

  function parseImageBindingWatchKey(key: string): { chatId: string; model: string; preset: string } | null {
    if (!key) return null
    const parts = key.split('\0')
    if (parts.length < 2) return null
    const chatId = parts[0] ?? ''
    const model = parts[1] ?? ''
    const preset = parts[2] ?? ''
    return { chatId, model, preset }
  }

  const imageStickyBinding = ref<ImageStickyBinding | null>(null)

  function resolveImageBindingKey(): ImageStickyBinding | null {
    const chat = getActiveChat()
    if (!chat?.id) return null
    const model = chat.overrides?.params?.model || getDefaultModel() || ''
    const presetId = chat.overrides?.presetId ?? null
    return { chatId: chat.id, model, presetId }
  }

  function isImageStickyActive(): boolean {
    const cur = resolveImageBindingKey()
    const sticky = imageStickyBinding.value
    if (!cur || !sticky) return false
    return sticky.chatId === cur.chatId && sticky.model === cur.model && sticky.presetId === cur.presetId
  }

  function hydrateImageStickyFromStorage() {
    if (typeof window === 'undefined') return
    const cur = resolveImageBindingKey()
    if (!cur) return
    const map = loadImageStickyMap()
    const row = map[cur.chatId]
    if (!row || typeof row.model !== 'string') return
    const p = row.presetId == null || row.presetId === '' ? null : String(row.presetId)
    if (cur.model === row.model && cur.presetId === p) {
      imageStickyBinding.value = { chatId: cur.chatId, model: row.model, presetId: p }
    } else {
      delete map[cur.chatId]
      persistImageStickyMap(map)
    }
  }

  const imageBindingWatchKey = computed(() => {
    const chat = getActiveChat()
    if (!chat) return ''
    return `${chat.id}\0${chat.overrides?.params?.model ?? ''}\0${chat.overrides?.presetId ?? ''}`
  })

  watch(imageBindingWatchKey, (newKey, oldKey) => {
    imageStickyBinding.value = null
    const oldP = oldKey ? parseImageBindingWatchKey(oldKey) : null
    const newP = newKey ? parseImageBindingWatchKey(newKey) : null
    if (
      oldP &&
      newP &&
      oldP.chatId === newP.chatId &&
      (oldP.model !== newP.model || oldP.preset !== newP.preset)
    ) {
      removeImageStickyBindingRow(newP.chatId)
    }
    hydrateImageStickyFromStorage()
  })

  const imageFallbackDialog = ref<{
    visible: boolean
    error: string
    retryAction: null | (() => Promise<void>)
  }>({
    visible: false,
    error: '',
    retryAction: null,
  })

  function openImageFallback(error: string, retryAction: () => Promise<void>) {
    imageFallbackDialog.value = { visible: true, error, retryAction }
  }

  return {
    imageStickyBinding,
    resolveImageBindingKey,
    isImageStickyActive,
    saveImageStickyBindingRow,
    imageFallbackDialog,
    openImageFallback,
  }
}
