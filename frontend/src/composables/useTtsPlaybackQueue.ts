/**
 * TTS 播放队列 composable
 *
 * 管理：
 * - 合成请求队列（按消息顺序）
 * - 流式/非流式播放
 * - 下载 abort 控制
 * - 播放间隔（readGapSeconds）
 */
import { ref, shallowRef } from 'vue'
import { apiPost } from '../api/http'

/** DOM Audio.paused 不会触发 Vue 追踪，用事件同步到 ref 供 UI 使用 */
function syncAudioPausedRef(audio: HTMLAudioElement | null, target: { value: boolean }) {
  target.value = audio?.paused ?? true
}

export type QueueItemStatus = 'pending' | 'downloading' | 'ready' | 'playing' | 'done' | 'error' | 'aborted'

export interface QueueItem {
  messageId: string
  assetId?: string
  status: QueueItemStatus
  abortController?: AbortController
  gapSeconds?: number
}

export function useTtsPlaybackQueue() {
  const queue = ref<QueueItem[]>([])
  const isPlaying = ref(false)
  const isDownloading = ref(false)
  const currentAudio = shallowRef<HTMLAudioElement | null>(null)
  /** 与 currentAudio.paused 一致，经 play/pause 事件更新，供模板绑定 */
  const audioPaused = ref(true)
  let unbindAudioListeners: (() => void) | null = null

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

  /** 添加一条消息到队列并开始处理 */
  async function enqueue(messageId: string, text: string, voiceId: string, opts?: {
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
  }) {
    // 如果已有缓存，直接标记 ready
    if (opts?.existingAssetId) {
      queue.value.push({ messageId, assetId: opts.existingAssetId, status: 'ready', gapSeconds: opts.gapSeconds ?? 0 })
    } else {
      queue.value.push({ messageId, status: 'pending', gapSeconds: opts?.gapSeconds ?? 0 })
      await downloadItem(queue.value[queue.value.length - 1]!, text, voiceId, opts)
    }
    // 如果没在播放，启动播放循环
    if (!isPlaying.value) playNext()
  }

  async function downloadItem(item: QueueItem, text: string, voiceId: string, opts?: {
    model?: string
    stream?: boolean
    chatId?: string
    contentText?: string
    presetId?: string | null
    onReady?: (assetId: string) => void
    onSynthesizeError?: (err: unknown) => void
  }) {
    item.status = 'downloading'
    isDownloading.value = true
    const controller = new AbortController()
    item.abortController = controller

    try {
      const res = await apiPost<{ assetId: string }>('/api/tts/synthesize', {
        text,
        content_text: opts?.contentText ?? text,
        voice_id: voiceId,
        model: opts?.model ?? 'speech-2.8-hd',
        stream: false,
        message_id: item.messageId,
        chat_id: opts?.chatId ?? null,
        preset_id: opts?.presetId ?? null,
      }, controller.signal)

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
      }
    } finally {
      isDownloading.value = queue.value.some(i => i.status === 'downloading')
    }
  }

  async function playNext(gapSeconds?: number) {
    const next = queue.value.find(i => i.status === 'ready')
    if (!next) {
      isPlaying.value = false
      return
    }

    const resolvedGapSeconds = gapSeconds ?? next.gapSeconds ?? 0

    // 在 readGap 等待前就标记为 playing 并置 isPlaying，否则间隙内并发 enqueue 会再次启动 playNext，
    // 两条协程会先后从 find(ready) 取到同一条目，导致双 Audio 叠加播放。
    next.status = 'playing'
    isPlaying.value = true

    if (resolvedGapSeconds > 0) {
      await new Promise(resolve => setTimeout(resolve, resolvedGapSeconds * 1000))
    }

    try {
      const audio = new Audio(`/api/tts/audio/${next.assetId}`)
      currentAudio.value = audio
      bindAudioElement(audio)

      await new Promise<void>((resolve, reject) => {
        audio.onended = () => resolve()
        audio.onerror = () => reject(new Error('Audio playback error'))
        audio.play().catch(reject)
      })

      next.status = 'done'
    } catch (e) {
      next.status = 'error'
      console.error('[TTS] playback error', e)
    } finally {
      bindAudioElement(null)
      currentAudio.value = null
    }

    // 继续下一条
    playNext(next.gapSeconds)
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
    abortAllDownloads()
    if (currentAudio.value) {
      currentAudio.value.pause()
      bindAudioElement(null)
      currentAudio.value = null
    }
    isPlaying.value = false
    audioPaused.value = true
    queue.value = []
  }

  /** 恢复被 abort 的项目 */
  function resumeDownloads(text: string, voiceId: string, opts?: { chatId?: string; presetId?: string | null; model?: string; onReady?: (assetId: string) => void; onSynthesizeError?: (err: unknown) => void }) {
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
    enqueue,
    pause,
    resume,
    togglePlayPause,
    abortAllDownloads,
    stopAll,
    resumeDownloads,
  }
}
