<script setup lang="ts">
/**
 * TtsPlaybackFab - TTS 播放/下载双按钮浮动控件
 *
 * 竖排两颗 w-12 h-12 按钮：
 * 1. 队列（仅开关队列面板；终止下载在面板内）
 * 2. 播放控制（暂停/播放 二态）
 *
 * 整个容器可拖动，与助手 FAB 互斥（碰撞弹开）。
 * 侧栏收起且顶栏 morph 时：与输入栏同步下沉，按贴边滑出视口；顶栏全宽动画结束后在顶栏下展示替代控制条。
 */
import type { QueueItem, QueueItemStatus } from '../../composables/useTtsPlaybackQueue'
import { computed, nextTick, onUnmounted, ref, watch } from 'vue'
import { useTtsFabPosition } from '../../composables/useTtsFabPosition'

const props = withDefaults(
  defineProps<{
    isDownloading: boolean
    isPlaying: boolean
    audioPaused: boolean
    /** 面板展示用（已过滤 done/aborted） */
    queueItems: QueueItem[]
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
  (e: 'abort-download'): void
  (e: 'toggle-play-pause'): void
}>()

const ttsFabRootRef = ref<HTMLElement | null>(null)
const queueBtnFabRef = ref<HTMLButtonElement | null>(null)
const queueBtnTopRef = ref<HTMLButtonElement | null>(null)
const panelRef = ref<HTMLElement | null>(null)
const queuePanelOpen = ref(false)
const panelStyle = ref<Record<string, string>>({})

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

const PANEL_MIN_W = 110
const PANEL_MAX_W = 160
const PANEL_GAP = 8

/** 贴左时面板在按钮右侧，贴右时在按钮左侧，避免在下方展开压住暂停键 */
function updatePanelPosition() {
  const btn = props.showTopBarControls ? queueBtnTopRef.value : queueBtnFabRef.value
  if (!btn) return
  const r = btn.getBoundingClientRect()
  const w = Math.min(PANEL_MAX_W, Math.max(PANEL_MIN_W, window.innerWidth - 24))
  const maxPanelH = Math.min(window.innerHeight * 0.4, 280)

  const dockLeft = side.value === 'left'
  let left: number
  if (dockLeft) {
    left = r.right + PANEL_GAP
  } else {
    left = r.left - w - PANEL_GAP
  }
  left = Math.min(Math.max(8, left), window.innerWidth - w - 8)

  let top = r.top
  top = Math.min(Math.max(8, top), window.innerHeight - maxPanelH - 8)

  panelStyle.value = {
    top: `${top}px`,
    left: `${left}px`,
    width: `${w}px`,
  }
}

function onOutsidePointerDown(e: PointerEvent) {
  if (!queuePanelOpen.value) return
  const t = e.target as Node
  if (panelRef.value?.contains(t)) return
  if (queueBtnFabRef.value?.contains(t)) return
  if (queueBtnTopRef.value?.contains(t)) return
  queuePanelOpen.value = false
}

function handleReposition() {
  if (queuePanelOpen.value) updatePanelPosition()
}

let outsideBound = false
function bindOutside() {
  if (outsideBound) return
  document.addEventListener('pointerdown', onOutsidePointerDown, true)
  window.addEventListener('scroll', handleReposition, true)
  window.addEventListener('resize', handleReposition)
  outsideBound = true
}
function unbindOutside() {
  if (!outsideBound) return
  document.removeEventListener('pointerdown', onOutsidePointerDown, true)
  window.removeEventListener('scroll', handleReposition, true)
  window.removeEventListener('resize', handleReposition)
  outsideBound = false
}

watch(queuePanelOpen, (open) => {
  if (open) {
    nextTick(() => {
      if (!queuePanelOpen.value) return
      updatePanelPosition()
      bindOutside()
    })
  } else {
    unbindOutside()
  }
})

watch(
  () => props.showTopBarControls,
  () => {
    if (queuePanelOpen.value) nextTick(() => updatePanelPosition())
  },
)

watch(
  () => props.queueItems.length,
  () => {
    if (queuePanelOpen.value) nextTick(() => updatePanelPosition())
  },
)

watch(
  () => props.isDownloading,
  () => {
    if (queuePanelOpen.value) nextTick(() => updatePanelPosition())
  },
)

watch(side, () => {
  if (queuePanelOpen.value) nextTick(() => updatePanelPosition())
})

onUnmounted(() => {
  unbindOutside()
})

function statusDotClass(status: QueueItemStatus): string {
  switch (status) {
    case 'preprocessing':
      return 'tts-queue-dot tts-queue-dot--red'
    case 'pending':
    case 'downloading':
      return 'tts-queue-dot tts-queue-dot--amber'
    case 'ready':
      return 'tts-queue-dot tts-queue-dot--blue'
    case 'playing':
      return 'tts-queue-dot tts-queue-dot--green'
    case 'error':
      return 'tts-queue-dot tts-queue-dot--gray'
    default:
      return 'tts-queue-dot tts-queue-dot--muted'
  }
}

function handleQueueAction(e: MouseEvent) {
  if (onFabClick(e)) return
  queuePanelOpen.value = !queuePanelOpen.value
}

function handlePlayClick(e: MouseEvent) {
  if (onFabClick(e)) return
  emit('toggle-play-pause')
}

function handleTopQueueClick(e: MouseEvent) {
  e.stopPropagation()
  queuePanelOpen.value = !queuePanelOpen.value
}

function handleAbortInPanel(e: MouseEvent) {
  e.stopPropagation()
  emit('abort-download')
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
      <!-- 队列（仅开关面板） -->
      <button
        ref="queueBtnFabRef"
        type="button"
        class="chat-fab-surface w-12 h-12 rounded-xl font-bold shadow-lg transition-[transform,background-color,box-shadow] border border-[var(--color-border)] hover:scale-105 active:scale-95 flex items-center justify-center cursor-pointer"
        aria-label="打开 TTS 队列"
        @click="handleQueueAction"
      >
        <svg
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
      </button>

      <!-- 播放控制按钮 -->
      <button
        type="button"
        class="chat-fab-surface w-12 h-12 rounded-xl font-bold shadow-lg transition-[transform,background-color,box-shadow] border border-[var(--color-border)] hover:scale-105 active:scale-95 flex items-center justify-center cursor-pointer"
        :aria-label="isPlaying && !audioPaused ? '暂停播放' : '播放'"
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

    <!-- 不挂 body：顶栏 TTS 条保持 z-9，低于 header 区域，避免挡「更多」菜单。队列面板单独 z-[11]，高于主内容壳 z-10，避免被消息气泡压住 -->
    <Transition name="tts-top-bar-fade">
      <div
        v-if="showTopBarControls"
        class="tts-top-bar-stack fixed z-10 flex flex-col gap-2 pointer-events-none"
        :style="topBarStackStyle"
      >
        <div class="pointer-events-auto flex flex-col gap-2">
          <button
            ref="queueBtnTopRef"
            type="button"
            class="tts-top-bar-btn tts-top-bar-btn--queue"
            aria-label="打开 TTS 队列"
            @click="handleTopQueueClick"
          >
            <span class="tts-top-bar-btn__glow tts-top-bar-btn__glow--queue" aria-hidden="true" />
            <svg
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
            <span class="tts-top-bar-btn__label">队列</span>
          </button>
          <button
            type="button"
            class="tts-top-bar-btn tts-top-bar-btn--transport"
            :aria-label="isPlaying && !audioPaused ? '暂停播放' : '播放'"
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

    <Teleport to="body">
      <Transition name="tts-queue-panel-fade">
        <div
          v-if="queuePanelOpen"
          ref="panelRef"
          class="tts-queue-panel chat-fab-panel fixed z-floating rounded-xl shadow-lg max-h-[min(40vh,280px)] flex flex-col overflow-hidden"
          :style="panelStyle"
          role="region"
          aria-label="TTS 队列"
        >
          <div
            class="tts-queue-panel__inner max-h-[min(40vh,280px)] flex flex-col overflow-hidden px-2 py-2"
          >
            <div
              v-if="isDownloading"
              class="flex items-center justify-end gap-2 pb-2 mb-1 border-b border-[var(--color-border)] shrink-0"
            >
              <button
                type="button"
                class="btn btn-xs btn-danger"
                aria-label="终止传输"
                @click.stop="handleAbortInPanel"
              >
                终止传输
              </button>
            </div>
            <div class="min-h-0 flex-1 overflow-y-auto">
              <p
                v-if="queueItems.length === 0"
                class="text-xs text-muted px-1 py-2 text-center"
              >
                队列为空
              </p>
              <ul v-else class="flex flex-col gap-1.5 list-none m-0 p-0">
                <li
                  v-for="(item, idx) in queueItems"
                  :key="`${item.messageId}-${idx}-${item.status}`"
                  class="flex items-center justify-between gap-2 min-h-[1.75rem] px-1.5 py-1 rounded-lg bg-surface-muted"
                >
                  <span class="text-xs text-[var(--color-text)] truncate flex-1 min-w-0">
                    {{ item.previewLabel || '…' }}
                  </span>
                  <span
                    class="shrink-0 w-2 h-2 rounded-full"
                    :class="statusDotClass(item.status)"
                    aria-hidden="true"
                  />
                </li>
              </ul>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>
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

.tts-queue-dot {
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--color-border) 40%, transparent);
}

.tts-queue-dot--red {
  background: var(--color-error);
}

.tts-queue-dot--amber {
  background: var(--color-warning);
}

.tts-queue-dot--blue {
  background: var(--color-info);
}

.tts-queue-dot--green {
  background: var(--color-success);
}

.tts-queue-dot--gray {
  background: var(--color-text-muted);
}

.tts-queue-dot--muted {
  background: var(--color-text-muted);
}

/* 顶栏 chip：尺寸与 ChatInput Agent 胶囊一致 */
.tts-top-bar-btn {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  min-height: 1.75rem;
  padding: 0.3rem 0.6rem;
  border-radius: 0.75rem;
  border: 1px solid var(--color-border-subtle);
  background: color-mix(in srgb, var(--color-surface-overlay) 88%, transparent);
  color: var(--color-text-secondary);
  font-size: 0.6875rem;
  line-height: 1;
  cursor: pointer;
  overflow: hidden;
  box-shadow: var(--shadow-glass-panel);
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
  background-color: var(--color-brand-a20);
}

.tts-top-bar-btn__glow--transport {
  background-color: var(--color-purple-bg);
}

.tts-top-bar-btn__icon {
  width: 0.875rem;
  height: 0.875rem;
  flex-shrink: 0;
  color: var(--color-text);
  position: relative;
  z-index: 1;
}

.tts-top-bar-btn__label {
  position: relative;
  z-index: 1;
  font-weight: 400;
  letter-spacing: 0.04em;
  color: var(--color-text);
}

.tts-top-bar-btn--queue {
  border-color: color-mix(in srgb, var(--color-border-subtle) 70%, var(--color-brand) 30%);
}

.tts-top-bar-btn--transport {
  border-color: color-mix(in srgb, var(--color-border-subtle) 72%, var(--color-purple) 28%);
}

.tts-top-bar-btn:hover {
  background: color-mix(in srgb, var(--color-surface-overlay) 96%, var(--color-border-subtle) 4%);
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

.tts-queue-panel-fade-enter-active,
.tts-queue-panel-fade-leave-active {
  transition: opacity 0.18s cubic-bezier(0.25, 1, 0.5, 1);
}

.tts-queue-panel-fade-enter-from,
.tts-queue-panel-fade-leave-to {
  opacity: 0;
}

@media (prefers-reduced-motion: reduce) {
  .tts-top-bar-btn {
    animation: none;
  }

  .tts-top-bar-fade-enter-active,
  .tts-top-bar-fade-leave-active,
  .tts-queue-panel-fade-enter-active,
  .tts-queue-panel-fade-leave-active {
    transition-duration: 0.01ms !important;
  }
}
</style>
