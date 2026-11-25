<script setup lang="ts">
import { computed, ref, watch } from 'vue'

interface Props {
  src?: string | null
  name?: string
  size?: number | string
  aspect?: number | string
  rounded?: string
  bordered?: boolean
  objectFit?: 'cover' | 'contain' | 'fill' | 'scale-down' | 'none'
  objectPosition?: string
}

const props = withDefaults(defineProps<Props>(), {
  src: null,
  name: '?',
  size: 40,
  aspect: 1,
  rounded: 'rounded-xl',
  bordered: false,
  objectFit: 'cover',
  objectPosition: '50% 50%',
})

const segmenter = typeof Intl.Segmenter === 'function' ? new Intl.Segmenter() : null
const palette = [
  'bg-brand-a20 text-brand',
  'bg-[var(--color-info-bg)] text-[var(--color-info-text)]',
  'bg-[var(--color-success-bg)] text-[var(--color-success-text)]',
  'bg-[var(--color-warning-bg)] text-[var(--color-warning-text)]',
  'bg-[var(--color-purple-bg)] text-[var(--color-purple-text)]',
  'bg-[var(--color-assistant-bg)] text-[var(--color-text)]',
]

const revision = ref(0)
const status = ref<'loading' | 'ready' | 'error'>('loading')
watch(() => props.src, () => {
  revision.value++
  status.value = 'loading'
}, { flush: 'sync' })

const ready = computed(() => !!props.src && status.value === 'ready')
const name = computed(() => props.name.trim() || '?')
const initial = computed(() => {
  const graphemes = segmenter
    ? Array.from(segmenter.segment(name.value), ({ segment }) => segment)
    : Array.from(name.value)
  const first = graphemes.find(grapheme => /[^\p{Format}\p{Control}\p{White_Space}]/u.test(grapheme))
  return first?.replace(/^\p{Script=Latin}/u, letter => {
    const upper = letter.toUpperCase()
    return Array.from(upper).length === 1 ? upper : letter
  }) ?? '?'
})

const colorIndex = computed(() => {
  let hash = 0
  for (let index = 0; index < name.value.length; index++) {
    hash = name.value.charCodeAt(index) + ((hash << 5) - hash)
  }
  return Math.abs(hash) % palette.length
})

const style = computed(() => {
  const width = typeof props.size === 'number' ? props.size + 'px' : props.size
  const height = typeof props.aspect === 'number'
    ? 'calc(' + width + ' / ' + props.aspect + ')'
    : props.aspect === 'auto' ? 'auto' : width
  return {
    width,
    height,
    fontSize: typeof props.size === 'number' ? (props.size * 0.4) + 'px' : '1rem',
  }
})

function settle(event: Event, result: 'ready' | 'error') {
  const image = event.currentTarget as HTMLImageElement
  if (Number(image.dataset.revision) === revision.value) status.value = result
}
</script>

<template>
  <div
    class="modern-avatar relative overflow-hidden shrink-0 flex items-center justify-center select-none border border-[var(--color-border-subtle)] shadow-sm"
    :class="[rounded, palette[colorIndex], bordered && 'dark-ui:ring-2 dark-ui:ring-brand-a40']"
    :style="style"
  >
    <img
      v-if="src && status !== 'error'"
      v-show="ready"
      :key="revision"
      :src="src"
      :data-revision="revision"
      class="w-full"
      :class="aspect === 'auto' ? 'h-auto' : 'h-full'"
      :style="{ objectFit, objectPosition }"
      alt=""
      @load="settle($event, 'ready')"
      @error="settle($event, 'error')"
    />
    <span
      v-if="!ready"
      class="modern-avatar__initial flex w-full items-center justify-center self-stretch font-bold"
      :data-color="colorIndex"
      aria-hidden="true"
    >{{ initial }}</span>
    <slot v-if="ready" />
  </div>
</template>
