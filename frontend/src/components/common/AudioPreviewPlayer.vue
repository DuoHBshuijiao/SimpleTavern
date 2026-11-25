<script setup lang="ts">
import { ref } from 'vue'
import { Download, Pause, Play, Volume2, VolumeX } from 'lucide-vue-next'
import ModernSelect from '../ModernSelect.vue'

defineProps<{
  src: string
  label: string
  autoplay?: boolean
}>()

const audio = ref<HTMLAudioElement | null>(null)
const playing = ref(false)
const elapsed = ref(0)
const duration = ref(0)
const muted = ref(false)
const volume = ref(1)
const failed = ref(false)
const rate = ref('1')
const rateOptions = ['0.25', '0.5', '0.75', '1', '1.25', '1.5', '1.75', '2'].map(value => ({ value, label: `${value}×` }))

function syncPlayback() {
  const media = audio.value
  if (!media) return
  playing.value = !media.paused && !media.ended
  elapsed.value = media.currentTime
  duration.value = Number.isFinite(media.duration) ? media.duration : 0
  muted.value = media.muted
  volume.value = media.volume
  rate.value = String(media.playbackRate)
}

async function togglePlayback() {
  const media = audio.value
  if (!media) return
  if (media.paused) {
    try {
      await media.play()
    } catch {
      failed.value = !!media.error
      syncPlayback()
    }
  } else {
    media.pause()
  }
}

function seek(event: Event) {
  if (audio.value && duration.value) audio.value.currentTime = (event.target as HTMLInputElement).valueAsNumber
  syncPlayback()
}

function setVolume(event: Event) {
  if (!audio.value) return
  audio.value.volume = (event.target as HTMLInputElement).valueAsNumber
  audio.value.muted = false
}

function setRate(value: string) {
  if (!audio.value) return
  audio.value.playbackRate = Number(value)
}

function formatTime(seconds: number) {
  const time = Math.floor(seconds)
  return `${Math.floor(time / 60)}:${String(time % 60).padStart(2, '0')}`
}
</script>

<template>
  <div class="settings-item flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1" role="group" :aria-label="label">
    <audio
      ref="audio"
      :src="src"
      :autoplay="autoplay"
      :aria-label="label"
      preload="metadata"
      @loadstart="failed = false; syncPlayback()"
      @loadedmetadata="syncPlayback"
      @durationchange="syncPlayback"
      @timeupdate="syncPlayback"
      @play="syncPlayback"
      @pause="syncPlayback"
      @ended="syncPlayback"
      @volumechange="syncPlayback"
      @ratechange="syncPlayback"
      @error="failed = true; syncPlayback()"
    />
    <button type="button" class="btn btn-xs btn-ghost btn-icon-sm" :aria-label="playing ? '暂停试听' : '播放试听'" :disabled="failed" @click="togglePlayback">
      <Pause v-if="playing" class="h-4 w-4" aria-hidden="true" />
      <Play v-else class="h-4 w-4" aria-hidden="true" />
    </button>
    <div class="flex min-w-[7rem] flex-1 items-center gap-2">
      <input type="range" class="input-range min-w-0 flex-1" min="0" :max="duration || 1" step="any" :value="elapsed" :disabled="!duration || failed" aria-label="播放进度" @input="seek" />
      <span class="shrink-0 text-2xs tabular-nums text-muted">{{ formatTime(elapsed) }} / {{ formatTime(duration) }}</span>
    </div>
    <div class="flex items-center gap-1">
      <button type="button" class="btn btn-xs btn-ghost btn-icon-sm" :aria-label="muted ? '取消静音' : '静音'" :disabled="failed" @click="audio && (audio.muted = !muted)">
        <VolumeX v-if="muted || !volume" class="h-4 w-4" aria-hidden="true" />
        <Volume2 v-else class="h-4 w-4" aria-hidden="true" />
      </button>
      <input type="range" class="input-range max-w-16" min="0" max="1" step="0.01" :value="muted ? 0 : volume" :disabled="failed" aria-label="试听音量" @input="setVolume" />
      <ModernSelect class="!w-auto" :model-value="rate" :options="rateOptions" :disabled="failed" placement="top" aria-label="试听播放速度" @update:model-value="setRate" />
      <a class="btn btn-xs btn-ghost btn-icon-sm" :href="src" download aria-label="下载试听音频">
        <Download class="h-4 w-4" aria-hidden="true" />
      </a>
    </div>
    <span v-if="failed" role="status" class="w-full text-xs text-error">无法播放试听音频。</span>
  </div>
</template>
