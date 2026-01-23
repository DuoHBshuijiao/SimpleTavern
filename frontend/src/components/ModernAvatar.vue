<script setup lang="ts">
/**
 * ModernAvatar - 现代化头像组件
 * 风格：Swiss Modernism 2.0 (Sharp, Geometric)
 */
import { computed, ref } from 'vue'

interface Props {
  src?: string | null
  name?: string
  size?: number | string 
  aspect?: number | string 
  rounded?: string 
  bordered?: boolean
  objectFit?: 'cover' | 'contain' | 'fill' | 'scale-down' | 'none'
}

const props = withDefaults(defineProps<Props>(), {
  src: null,
  name: '?',
  size: 40,
  aspect: 1,
  rounded: 'rounded-sm', // Default to sharp Swiss corners
  bordered: false,
  objectFit: 'cover'
})

const hasError = ref(false)
const isLoaded = ref(false)

const style = computed(() => {
  const width = typeof props.size === 'number' ? `${props.size}px` : props.size
  let height: string | undefined = undefined
  
  if (props.aspect === 'auto') {
    height = 'auto'
  } else if (typeof props.aspect === 'number') {
    height = typeof props.size === 'number' 
      ? `${props.size / props.aspect}px` 
      : `calc(${props.size} / ${props.aspect})`
  } else {
    height = width
  }

  return {
    width,
    height,
    fontSize: typeof props.size === 'number' ? `${props.size * 0.5}px` : '1rem'
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
  const name = props.name || '?'
  return name.length > 0 ? name.charAt(0).toUpperCase() : '?'
})

const bgColor = computed(() => {
  // Desaturated Swiss Palette
  const colors = [
    'bg-brand text-text-inverse',
    'bg-accent text-text-inverse',
    'bg-dark-lighter text-text-primary',
    'bg-neutral-600 text-white',
    'bg-neutral-800 text-brand',
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
    class="relative overflow-hidden shrink-0 flex items-center justify-center select-none transition-all duration-200"
    :class="[
      rounded,
      bgColor,
      bordered ? 'border border-strong' : ''
    ]"
    :style="style"
  >
    <img
      v-if="src && !hasError"
      :src="src"
      class="w-full transition-opacity duration-200"
      :class="[
        { 'opacity-0': !isLoaded, 'opacity-100': isLoaded },
        props.aspect === 'auto' ? 'h-auto' : 'h-full',
        `object-${objectFit}`
      ]"
      @error="handleError"
      @load="handleLoad"
      alt=""
    />
    <span v-else class="font-black italic uppercase">
      {{ initials }}
    </span>
    
    <!-- Skeleton loader -->
    <div 
      v-if="src && !isLoaded && !hasError" 
      class="absolute inset-0 bg-white/5 animate-pulse"
    ></div>
  </div>
</template>
