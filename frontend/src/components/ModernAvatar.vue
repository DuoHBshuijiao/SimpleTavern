<script setup lang="ts">
import { computed, ref } from 'vue'

interface Props {
  src?: string | null
  name?: string
  size?: number | string // Base width
  aspect?: number | string // Aspect ratio, e.g., 1 (square), 0.75 (3:4), or 'auto'
  rounded?: string // Tailwind rounded class, e.g., 'rounded-xl'
  bordered?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  src: null,
  name: '?',
  size: 40,
  aspect: 1,
  rounded: 'rounded-xl',
  bordered: false,
})

const hasError = ref(false)
const isLoaded = ref(false)

const style = computed(() => {
  const width = typeof props.size === 'number' ? `${props.size}px` : props.size
  let height = width
  
  if (typeof props.aspect === 'number') {
    height = typeof props.size === 'number' 
      ? `${props.size / props.aspect}px` 
      : `calc(${props.size} / ${props.aspect})`
  }

  return {
    width,
    height,
    fontSize: typeof props.size === 'number' ? `${props.size * 0.4}px` : '1rem'
  }
})

function handleError() {
  hasError.value = true
  isLoaded.value = true
}

function handleLoad() {
  isLoaded.value = true
}

const initials = computed(() => {
  return (props.name || '?')[0].toUpperCase()
})

const bgColor = computed(() => {
  // Generate a consistent color based on name
  const colors = [
    'bg-brand/20 text-brand',
    'bg-blue-500/20 text-blue-400',
    'bg-emerald-500/20 text-emerald-400',
    'bg-orange-500/20 text-orange-400',
    'bg-pink-500/20 text-pink-400',
    'bg-cyan-500/20 text-cyan-400',
  ]
  let hash = 0
  const str = props.name || '?'
  for (let i = 0; i < str.length; i++) {
    hash = str.charCodeAt(i) + ((hash << 5) - hash)
  }
  return colors[Math.abs(hash) % colors.length]
})
</script>

<template>
  <div
    class="relative overflow-hidden shrink-0 flex items-center justify-center select-none transition-all duration-300"
    :class="[
      rounded,
      bgColor,
      bordered ? 'ring-1 ring-white/10' : ''
    ]"
    :style="style"
  >
    <img
      v-if="src && !hasError"
      :src="src"
      class="w-full h-full object-cover transition-opacity duration-300"
      :class="{ 'opacity-0': !isLoaded, 'opacity-100': isLoaded }"
      @error="handleError"
      @load="handleLoad"
      alt=""
    />
    <span v-else class="font-bold">
      {{ initials }}
    </span>
    
    <!-- Skeleton loader -->
    <div 
      v-if="src && !isLoaded && !hasError" 
      class="absolute inset-0 bg-white/5 animate-pulse"
    ></div>
  </div>
</template>

