/**
 * TTS 播放队列 composable
 *
 * 管理：
 * - 合成请求队列（按消息顺序）
 * - 流式/非流式播放
 * - 下载 abort 控制
 * - 播放间隔（readGapSeconds）
 * - 手动朗读插队 / 打断 playNext
 */
import { ref, shallowRef } from 'vue'
import { apiPost } from '../api/http'

/** DOM Audio.paused 不会触发 Vue 追踪，用事件同步到 ref 供 UI 使用 */
function syncAudioPausedRef(audio: HTMLAudioElement | null, target: { value: boolean }) {
  target.value = audio?.paused ?? true
}

export type QueueItemStatus =
  | 'preprocessing'
  | 'pending'
  | 'downloading'
  | 'ready'
  | 'playing'
  | 'done'
  | 'error'
  | 'aborted'

export interface QueueItem {
  messageId: string
  /** 消息正文前 5 字等，供队列面板展示 */
  previewLabel: string
  assetId?: string
  status: QueueItemStatus
  abortController?: AbortController
  gapSeconds?: number
}

export type EnqueueMode = 'auto' | 'manual'
export type ManualPlacement = 'tail' | 'cachedJump' | 'second'

export function useTtsPlaybackQueue() {
  const queue = ref<QueueItem[]>([])
  const isPlaying = ref(false)
  const isDownloading = ref(false)
  const currentAudio = shallowRef<HTMLAudioElement | null>(null)
  /** 与 currentAudio.paused 一致，经 play/pause 事件更新，供模板绑定 */
  const audioPaused = ref(true)
  let unbindAudioListeners: (() => void) | null = null

  /** 打断进行中的 playNext（gap / 出声） */
  let playGeneration = 0
  let gapTimer: ReturnType<typeof setTimeout> | null = null
  /** 与 gapTimer 配对，打断时 resolve，避免 clearTimeout 后 Promise 永不结束 */
  let gapResolve: (() => void) | null = null
  /** 出声阶段 await 的 resolve，打断时调用以结束 wait */
  let audioWaitResolve: (() => void) | null = null
  /** gap 与出声阶段当前处理的 messageId */
  const currentPlaybackMessageId = ref<string | null>(null)

  function clearGapTimer() {
    if (gapTimer != null) {
      clearTimeout(gapTimer)
      gapTimer = null
    }
    if (gapResolve) {
      const r = gapResolve
      gapResolve = null
      r()
    }
  }

  function bindAudioElement(audio: HTMLAudioElement | null) {
    unbindAudioListeners?.()
    unbindAudioListeners = null
    if (!audio) {
      syncAudioPausedRef(null, audioPaused)
      return
    }
    const sync = () => syncAudioPausedRef(audio, audioPaused)
    audio.addEventListener('play', sync)
    audio.addEventListener('playing', sync)
    audio.addEventListener('pause', sync)
    audio.addEventListener('ended', sync)
    sync()
    unbindAudioListeners = () => {
      audio.removeEventListener('play', sync)
      audio.removeEventListener('playing', sync)
      audio.removeEventListener('pause', sync)
      audio.removeEventListener('ended', sync)
    }
  }

  /**
   * 手动缓存插队：停 gap/音频；正在出声则移除该条；仅 gap 则改回 ready。
   * 随后由 enqueue 头插并 playNext。
   */
  function interruptPlaybackForManualJump() {
    playGeneration++
    clearGapTimer()

    const msgId = currentPlaybackMessageId.value

    if (currentAudio.value) {
      currentAudio.value.pause()
      if (audioWaitResolve) {
        const r = audioWaitResolve
        audioWaitResolve = null
        r()
      }
      bindAudioElement(null)
      currentAudio.value = null
      if (msgId) {
        const idx = queue.value.findIndex((i) => i.messageId === msgId && i.status === 'playing')
        if (idx >= 0) queue.value.splice(idx, 1)
      }
    } else if (msgId) {
      const item = queue.value.find((i) => i.messageId === msgId && i.status === 'playing')
      if (item) item.status = 'ready'
    }

    currentPlaybackMessageId.value = null
    isPlaying.value = false
  }

  /** 后处理进行中（在 enqueue 之前），用于队列面板红点 */
  function beginPreprocessing(messageId: string, previewLabel: string) {
    queue.value.push({
      messageId,
      status: 'preprocessing',
      previewLabel,
      gapSeconds: 0,
    })
  }

  function endPreprocessing(messageId: string) {
    const idx = queue.value.findIndex((i) => i.messageId === messageId && i.status === 'preprocessing')
    if (idx >= 0) queue.value.splice(idx, 1)
  }

  /** 添加一条消息到队列并开始处理 */
  async function enqueue(
    messageId: string,
    text: string,
    voiceId: string,
    opts: {
      previewLabel: string
      model?: string
      stream?: boolean
      existingAssetId?: string
      chatId?: string
      contentText?: string
      presetId?: string | null
      gapSeconds?: number
      onReady?: (assetId: string) => void
      /** 合成失败时回调（如接入主聊天 errorStack） */
      onSynthesizeError?: (err: unknown) => void
      /** auto：队尾 push；manual + cachedJump：头插缓存；manual + second：下标 1 插入（空队列为 0） */
      enqueueMode?: EnqueueMode
      manualPlacement?: ManualPlacement
    },
  ) {
    const previewLabel = opts.previewLabel
    const gapSeconds = opts.gapSeconds ?? 0
    const enqueueMode = opts.enqueueMode ?? 'auto'
    const manualPlacement = opts.manualPlacement ?? 'tail'

    const newItemBase = { messageId, gapSeconds, previewLabel }

    if (opts.existingAssetId) {
      const readyItem: QueueItem = {
        ...newItemBase,
        assetId: opts.existingAssetId,
        status: 'ready',
      }
      if (enqueueMode === 'manual' && manualPlacement === 'cachedJump') {
        interruptPlaybackForManualJump()
        queue.value.splice(0, 0, readyItem)
      } else {
        queue.value.push(readyItem)
      }
    } else {
      const pendingItem: QueueItem = {
        ...newItemBase,
        status: 'pending',
      }
      if (enqueueMode === 'manual' && manualPlacement === 'second') {
        const idx = queue.value.length === 0 ? 0 : 1
        queue.value.splice(idx, 0, pendingItem)
      } else {
        queue.value.push(pendingItem)
      }
      const inserted = pendingItem
      await downloadItem(inserted, text, voiceId, opts)
    }

    if (!isPlaying.value) void playNext()
  }

  async function downloadItem(
    item: QueueItem,
    text: string,
    voiceId: string,
    opts?: {
      model?: string
      stream?: boolean
      chatId?: string
      contentText?: string
      presetId?: string | null
      onReady?: (assetId: string) => void
      onSynthesizeError?: (err: unknown) => void
    },
  ) {
    item.status = 'downloading'
    isDownloading.value = true
    const controller = new AbortController()
    item.abortController = controller

    try {
      const res = await apiPost<{ assetId: string }>(
        '/api/tts/synthesize',
        {
          text,
          content_text: opts?.contentText ?? text,
          voice_id: voiceId,
          model: opts?.model ?? 'speech-2.8-hd',
          stream: false,
          message_id: item.messageId,
          chat_id: opts?.chatId ?? null,
          preset_id: opts?.presetId ?? null,
        },
        controller.signal,
      )

      if (controller.signal.aborted) {
        item.status = 'aborted'
        return
      }
      item.assetId = res.assetId
      item.status = 'ready'
      opts?.onReady?.(res.assetId)
    } catch (e: any) {
      if (e?.name === 'AbortError' || controller.signal.aborted) {
        item.status = 'aborted'
      } else {
        item.status = 'error'
        console.error('[TTS] download error', e)
        opts?.onSynthesizeError?.(e)
        const errIdx = queue.value.findIndex((i) => i === item)
        if (errIdx >= 0) queue.value.splice(errIdx, 1)
      }
    } finally {
      isDownloading.value = queue.value.some((i) => i.status === 'downloading')
    }
  }

  async function playNext(gapSeconds?: number) {
    const next = queue.value.find((i) => i.status === 'ready')
    if (!next) {
      isPlaying.value = false
      currentPlaybackMessageId.value = null
      return
    }

    const myGen = playGeneration
    const resolvedGapSeconds = gapSeconds ?? next.gapSeconds ?? 0

    next.status = 'playing'
    isPlaying.value = true
    currentPlaybackMessageId.value = next.messageId

    if (resolvedGapSeconds > 0) {
      await new Promise<void>((resolve) => {
        gapResolve = resolve
        gapTimer = setTimeout(() => {
          gapTimer = null
          gapResolve = null
          resolve()
        }, resolvedGapSeconds * 1000)
      })
    }

    if (myGen !== playGeneration) {
      return
    }

    try {
      const audio = new Audio(`/api/tts/audio/${next.assetId}`)
      currentAudio.value = audio
      bindAudioElement(audio)

      await new Promise<void>((resolve, reject) => {
        const finish = () => {
          audioWaitResolve = null
          resolve()
        }
        audioWaitResolve = finish
        audio.onended = () => finish()
        audio.onerror = () => {
          audioWaitResolve = null
          reject(new Error('Audio playback error'))
        }
        audio.play().catch((e) => {
          audioWaitResolve = null
          reject(e)
        })
      })

      if (myGen !== playGeneration) return

      next.status = 'done'
    } catch (e) {
      if (myGen === playGeneration) {
        console.error('[TTS] playback error', e)
        const idx = queue.value.findIndex((i) => i === next)
        if (idx >= 0) queue.value.splice(idx, 1)
      }
    } finally {
      if (myGen === playGeneration) {
        bindAudioElement(null)
        currentAudio.value = null
        currentPlaybackMessageId.value = null
      }
    }

    if (myGen !== playGeneration) return

    void playNext(next.gapSeconds)
  }

  function pause() {
    if (currentAudio.value && !currentAudio.value.paused) {
      currentAudio.value.pause()
      syncAudioPausedRef(currentAudio.value, audioPaused)
    }
  }

  function resume() {
    if (currentAudio.value?.paused) {
      void currentAudio.value.play()
    }
  }

  function togglePlayPause() {
    if (currentAudio.value) {
      if (currentAudio.value.paused) resume()
      else pause()
    }
  }

  /** 停止所有下载 */
  function abortAllDownloads() {
    for (const item of queue.value) {
      if (item.status === 'downloading' && item.abortController) {
        item.abortController.abort()
        item.status = 'aborted'
      }
      if (item.status === 'pending') {
        item.status = 'aborted'
      }
    }
    isDownloading.value = false
  }

  /** 停止播放并清空队列 */
  function stopAll() {
    playGeneration++
    clearGapTimer()
    if (audioWaitResolve) {
      const r = audioWaitResolve
      audioWaitResolve = null
      r()
    }
    abortAllDownloads()
    if (currentAudio.value) {
      currentAudio.value.pause()
      bindAudioElement(null)
      currentAudio.value = null
    }
    isPlaying.value = false
    audioPaused.value = true
    currentPlaybackMessageId.value = null
    queue.value = []
  }

  /** 恢复被 abort 的项目 */
  function resumeDownloads(
    text: string,
    voiceId: string,
    opts?: {
      chatId?: string
      presetId?: string | null
      model?: string
      onReady?: (assetId: string) => void
      onSynthesizeError?: (err: unknown) => void
    },
  ) {
    for (const item of queue.value) {
      if (item.status === 'aborted') {
        downloadItem(item, text, voiceId, opts)
      }
    }
  }

  return {
    queue,
    isPlaying,
    isDownloading,
    currentAudio,
    audioPaused,
    beginPreprocessing,
    endPreprocessing,
    enqueue,
    pause,
    resume,
    togglePlayPause,
    abortAllDownloads,
    stopAll,
    resumeDownloads,
  }
}
