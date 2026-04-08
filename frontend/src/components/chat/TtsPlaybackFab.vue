<script setup lang="ts">
/**
 * TtsPlaybackFab - TTS 播放/下载双按钮浮动控件
 *
 * 竖排两颗 w-12 h-12 按钮：
 * 1. 下载控制（停止/恢复 二态）
 * 2. 播放控制（暂停/播放 二态）
 *
 * 整个容器可拖动，与助手 FAB 互斥（碰撞弹开）。
 * 侧栏收起且顶栏 morph 时：与输入栏同步下沉，按贴边滑出视口；顶栏全宽动画结束后在顶栏下展示替代控制条。
 */
import { computed, ref } from 'vue'
import { useTtsFabPosition } from '../../composables/useTtsFabPosition'

const props = withDefaults(
  defineProps<{
    isDownloading: boolean
    isPlaying: boolean
    audioPaused: boolean
    contentAreaLeftPx: number
    minTopPx: number
    /** 与 ChatInput 输入栏下沉同相 */
    inputSinkActive?: boolean
    /** 顶栏 full + squeeze 结束后显示顶栏下替代按钮 */
    showTopBarControls?: boolean
    /** 非拖动持久化后，供与助手 FAB 碰撞分离 */
    onTtsFabLayout?: () => void
    /** 用户拖动 TTS 条松手后：只移动 TTS，助手保持不动 */
    onTtsFabDragEnd?: () => void
    /** 左右贴边 snap 结束后 */
    onTtsFabSnapEnd?: () => void
  }>(),
  {
    inputSinkActive: false,
    showTopBarControls: false,
  },
)

const emit = defineEmits<{
  (e: 'toggle-download'): void
  (e: 'toggle-play-pause'): void
}>()

const ttsFabRootRef = ref<HTMLElement | null>(null)

const {
  fabStyle,
  setTopPxFromSeparation,
  side,
  onPointerDown,
  onPointerMove,
  onPointerUp,
  onPointerCancel,
  onFabClick,
} = useTtsFabPosition(
  () => props.contentAreaLeftPx,
  () => props.minTopPx,
  {
    onLayoutStable: () => props.onTtsFabLayout?.(),
    onDragEnd: () => props.onTtsFabDragEnd?.(),
    onSnapEnd: () => props.onTtsFabSnapEnd?.(),
    getInputSinkActive: () => props.inputSinkActive,
  },
)

const topBarStackStyle = computed(() => {
  const top = `${props.minTopPx}px`
  if (side.value === 'left') {
    return {
      top,
      left: `${props.contentAreaLeftPx + 8}px`,
      right: 'auto' as const,
    }
  }
  return {
    top,
    right: '16px',
    left: 'auto' as const,
  }
})

function handleDownloadClick(e: MouseEvent) {
  if (onFabClick(e)) return
  emit('toggle-download')
}

function handlePlayClick(e: MouseEvent) {
  if (onFabClick(e)) return
  emit('toggle-play-pause')
}

function handleTopDownloadClick(e: MouseEvent) {
  e.stopPropagation()
  emit('toggle-download')
}

function handleTopPlayClick(e: MouseEvent) {
  e.stopPropagation()
  emit('toggle-play-pause')
}

function getTtsFabRect(): DOMRect | null {
  return ttsFabRootRef.value?.getBoundingClientRect() ?? null
}

defineExpose({ getRect: getTtsFabRect, setTtsTopPx: setTopPxFromSeparation })
</script>

<template>
  <div class="tts-fab-host">
  <div
    ref="ttsFabRootRef"
    class="flex flex-col gap-2 cursor-grab active:cursor-grabbing"
    :class="{ 'tts-fab-root--hidden': showTopBarControls }"
    :style="fabStyle"
    @pointerdown="onPointerDown"
    @pointermove="onPointerMove"
    @pointerup="onPointerUp"
    @pointercancel="onPointerCancel"
  >
    <!-- 下载控制按钮 -->
    <button
      type="button"
      class="w-12 h-12 rounded-xl bg-surface-elevated text-[var(--color-text)] font-bold shadow-lg hover:bg-surface-hover transition-[transform,background-color,box-shadow] border border-[var(--color-border)] hover:scale-105 active:scale-95 flex items-center justify-center backdrop-blur-sm cursor-pointer"
      :aria-label="isDownloading ? '停止下载' : '下载语音'"
      :title="isDownloading ? '停止下载' : '下载语音'"
      @click="handleDownloadClick"
    >
      <svg
        v-if="!isDownloading"
        class="tts-icon tts-icon--fab"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
        stroke-linecap="round"
        stroke-linejoin="round"
        aria-hidden="true"
      >
        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
        <polyline points="7 10 12 15 17 10" />
        <line x1="12" y1="15" x2="12" y2="3" />
      </svg>
      <svg
        v-else
        class="tts-icon tts-icon--fab tts-icon--fill"
        viewBox="0 0 24 24"
        aria-hidden="true"
      >
        <rect x="6" y="6" width="12" height="12" rx="1.5" />
      </svg>
    </button>

    <!-- 播放控制按钮 -->
    <button
      type="button"
      class="w-12 h-12 rounded-xl bg-surface-elevated text-[var(--color-text)] font-bold shadow-lg hover:bg-surface-hover transition-[transform,background-color,box-shadow] border border-[var(--color-border)] hover:scale-105 active:scale-95 flex items-center justify-center backdrop-blur-sm cursor-pointer"
      :aria-label="isPlaying && !audioPaused ? '暂停播放' : '播放'"
      :title="isPlaying && !audioPaused ? '暂停播放' : '播放'"
      @click="handlePlayClick"
    >
      <svg
        v-if="!(isPlaying && !audioPaused)"
        class="tts-icon tts-icon--fab tts-icon--fill"
        viewBox="0 0 24 24"
        aria-hidden="true"
      >
        <polygon points="8 5 19 12 8 19 8 5" />
      </svg>
      <svg v-else class="tts-icon tts-icon--fab tts-icon--fill" viewBox="0 0 24 24" aria-hidden="true">
        <rect x="6" y="5" width="4" height="14" rx="1" />
        <rect x="14" y="5" width="4" height="14" rx="1" />
      </svg>
    </button>
  </div>

  <!-- 不挂 body：与顶栏同属主内容 stacking，z 须低于 header 固定层 (z-10)，否则遮挡「更多」菜单 -->
    <Transition name="tts-top-bar-fade">
      <div
        v-if="showTopBarControls"
        class="tts-top-bar-stack fixed z-[9] flex flex-col gap-2 pointer-events-none"
        :style="topBarStackStyle"
      >
        <div class="pointer-events-auto flex flex-col gap-2">
          <button
            type="button"
            class="tts-top-bar-btn tts-top-bar-btn--queue"
            :aria-label="isDownloading ? '停止下载' : '下载语音'"
            :title="isDownloading ? '停止下载' : '下载语音'"
            @click="handleTopDownloadClick"
          >
            <span class="tts-top-bar-btn__glow tts-top-bar-btn__glow--queue" aria-hidden="true" />
            <svg
              v-if="!isDownloading"
              class="tts-top-bar-btn__icon"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
              stroke-linejoin="round"
              aria-hidden="true"
            >
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
              <polyline points="7 10 12 15 17 10" />
              <line x1="12" y1="15" x2="12" y2="3" />
            </svg>
            <svg v-else class="tts-top-bar-btn__icon tts-icon--fill" viewBox="0 0 24 24" aria-hidden="true">
              <rect x="6" y="6" width="12" height="12" rx="1.5" />
            </svg>
            <span class="tts-top-bar-btn__label">{{ isDownloading ? '停止' : '队列' }}</span>
          </button>
          <button
            type="button"
            class="tts-top-bar-btn tts-top-bar-btn--transport"
            :aria-label="isPlaying && !audioPaused ? '暂停播放' : '播放'"
            :title="isPlaying && !audioPaused ? '暂停播放' : '播放'"
            @click="handleTopPlayClick"
          >
            <span class="tts-top-bar-btn__glow tts-top-bar-btn__glow--transport" aria-hidden="true" />
            <svg
              v-if="!(isPlaying && !audioPaused)"
              class="tts-top-bar-btn__icon tts-icon--fill"
              viewBox="0 0 24 24"
              aria-hidden="true"
            >
              <polygon points="8 5 19 12 8 19 8 5" />
            </svg>
            <svg v-else class="tts-top-bar-btn__icon tts-icon--fill" viewBox="0 0 24 24" aria-hidden="true">
              <rect x="6" y="5" width="4" height="14" rx="1" />
              <rect x="14" y="5" width="4" height="14" rx="1" />
            </svg>
            <span class="tts-top-bar-btn__label">{{ isPlaying && !audioPaused ? '暂停' : '播放' }}</span>
          </button>
        </div>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.tts-fab-host {
  display: contents;
}

.tts-fab-root--hidden {
  visibility: hidden;
}

.tts-icon {
  display: block;
}

.tts-icon--fab {
  width: 1.25rem;
  height: 1.25rem;
}

.tts-icon--fill {
  fill: currentColor;
  stroke: none;
}

/* 顶栏 chip 气质 + 两键独立点缀（与 ChatPage .header-action-chip 对齐） */
.tts-top-bar-btn {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 0.45rem;
  min-height: 2rem;
  padding: 0.4rem 0.75rem;
  border-radius: 0.85rem;
  border: 1px solid var(--color-border-subtle);
  background: color-mix(in srgb, var(--color-surface-overlay, rgba(18, 22, 30, 0.72)) 88%, transparent);
  color: var(--color-text-secondary);
  font-size: 0.75rem;
  line-height: 1;
  cursor: pointer;
  overflow: hidden;
  backdrop-filter: blur(var(--blur-light));
  -webkit-backdrop-filter: blur(var(--blur-light));
  box-shadow: var(--shadow-glass-panel, 0 8px 24px rgba(0, 0, 0, 0.18));
  transition:
    background-color 200ms cubic-bezier(0.25, 1, 0.5, 1),
    border-color 200ms cubic-bezier(0.25, 1, 0.5, 1),
    color 200ms cubic-bezier(0.25, 1, 0.5, 1),
    transform 180ms cubic-bezier(0.25, 1, 0.5, 1);
  animation: ttsTopBarSlideIn 0.38s cubic-bezier(0.25, 1, 0.5, 1) backwards;
}

.tts-top-bar-btn--transport {
  animation-delay: 0.07s;
}

.tts-top-bar-btn__glow {
  position: absolute;
  inset: 0;
  opacity: 0.35;
  pointer-events: none;
}

.tts-top-bar-btn__glow--queue {
  background: radial-gradient(
    120% 80% at 0% 50%,
    color-mix(in srgb, var(--color-brand, #6366f1) 28%, transparent),
    transparent 62%
  );
}

.tts-top-bar-btn__glow--transport {
  background: radial-gradient(
    120% 80% at 100% 40%,
    color-mix(in srgb, var(--color-purple, #a855f7) 26%, transparent),
    transparent 62%
  );
}

.tts-top-bar-btn__icon {
  width: 1rem;
  height: 1rem;
  flex-shrink: 0;
  color: var(--color-text);
  position: relative;
  z-index: 1;
}

.tts-top-bar-btn__label {
  position: relative;
  z-index: 1;
  font-weight: 600;
  letter-spacing: 0.02em;
  color: var(--color-text);
}

.tts-top-bar-btn--queue {
  border-color: color-mix(in srgb, var(--color-border-subtle) 70%, var(--color-brand, #6366f1) 30%);
}

.tts-top-bar-btn--transport {
  border-color: color-mix(in srgb, var(--color-border-subtle) 72%, var(--color-purple, #a855f7) 28%);
}

.tts-top-bar-btn:hover {
  background: color-mix(in srgb, var(--color-surface-overlay, rgba(18, 22, 30, 0.72)) 96%, var(--color-border-subtle) 4%);
  border-color: var(--color-border);
  color: var(--color-text);
}

.tts-top-bar-btn:active {
  transform: scale(0.97);
}

@keyframes ttsTopBarSlideIn {
  from {
    opacity: 0;
    transform: translateY(-14px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.tts-top-bar-fade-enter-active,
.tts-top-bar-fade-leave-active {
  transition: opacity 0.22s cubic-bezier(0.25, 1, 0.5, 1);
}

.tts-top-bar-fade-enter-from,
.tts-top-bar-fade-leave-to {
  opacity: 0;
}

@media (prefers-reduced-motion: reduce) {
  .tts-top-bar-btn {
    animation: none;
  }

  .tts-top-bar-fade-enter-active,
  .tts-top-bar-fade-leave-active {
    transition-duration: 0.01ms !important;
  }
}
</style>
