<script setup lang="ts">
import { ref, watch, nextTick } from 'vue'

const props = defineProps<{
  show: boolean
  target: HTMLElement | null
  title?: string
  message: string
  confirmText?: string
  cancelText?: string
}>()

const emit = defineEmits<{
  'confirm': []
  'cancel': []
  'update:show': [value: boolean]
}>()

const popoverRef = ref<HTMLElement | null>(null)
const position = ref({ top: 0, left: 0 })
const transformOrigin = ref('center bottom')

// Update position based on target element
const updatePosition = () => {
  if (!props.target || !popoverRef.value) return
  
  const targetRect = props.target.getBoundingClientRect()
  const popoverRect = popoverRef.value.getBoundingClientRect()
  const padding = 8
  
  // Default: Top centered
  let top = targetRect.top - popoverRect.height - padding
  let left = targetRect.left + (targetRect.width - popoverRect.width) / 2
  let origin = 'center bottom'
  
  // Check top overflow
  if (top < padding) {
    // Flip to bottom
    top = targetRect.bottom + padding
    origin = 'center top'
  }
  
  // Check horizontal overflow
  if (left < padding) {
    left = padding
    origin = 'left bottom' // simplified origin
  } else if (left + popoverRect.width > window.innerWidth - padding) {
    left = window.innerWidth - popoverRect.width - padding
    origin = 'right bottom'
  }
  
  // If flipped to bottom, adjust origin vertical
  if (top > targetRect.bottom) {
    origin = origin.replace('bottom', 'top')
  }

  position.value = { top, left }
  transformOrigin.value = origin
}

watch(() => props.show, async (newVal) => {
  if (newVal) {
    await nextTick()
    updatePosition()
    // Add event listeners for cleanup/reposition
    window.addEventListener('resize', updatePosition)
    window.addEventListener('scroll', updatePosition, true)
    document.addEventListener('mousedown', handleClickOutside)
  } else {
    window.removeEventListener('resize', updatePosition)
    window.removeEventListener('scroll', updatePosition, true)
    document.removeEventListener('mousedown', handleClickOutside)
  }
})

function handleClickOutside(e: MouseEvent) {
  // If clicking inside popover or on the target, don't close
  if (popoverRef.value && popoverRef.value.contains(e.target as Node)) return
  if (props.target && props.target.contains(e.target as Node)) return
  
  emit('update:show', false)
}
</script>

<template>
  <Teleport to="body">
    <Transition name="popover">
      <div 
        v-if="show"
        ref="popoverRef"
        class="fixed z-[100] min-w-[240px] max-w-[300px] p-4 rounded-xl bg-gradient-to-br from-slate-800/70 to-slate-700/50 backdrop-blur-xl backdrop-saturate-[1.8] border border-white/10 shadow-[0_8px_32px_rgba(0,0,0,0.3)] flex flex-col gap-3"
        :style="{ 
          top: `${position.top}px`, 
          left: `${position.left}px`,
          transformOrigin: transformOrigin
        }"
      >
        <div class="flex flex-col gap-1">
          <div v-if="title" class="text-sm font-bold text-gray-200">{{ title }}</div>
          <div class="text-xs text-gray-400 leading-relaxed">{{ message }}</div>
        </div>
        
        <div class="flex justify-end gap-2 pt-1">
          <button 
            class="px-3 py-1.5 text-xs font-medium rounded-lg hover:bg-white/10 text-gray-400 transition-colors" 
            @click="emit('cancel')"
          >
            {{ cancelText || '取消' }}
          </button>
          <button 
            class="px-3 py-1.5 text-xs font-medium rounded-lg bg-red-500/20 hover:bg-red-500/30 text-red-300 transition-colors shadow-sm shadow-red-900/20 border border-red-500/20" 
            @click="emit('confirm')"
          >
            {{ confirmText || '确认删除' }}
          </button>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.popover-enter-active,
.popover-leave-active {
  transition: opacity 0.2s cubic-bezier(0.16, 1, 0.3, 1), transform 0.2s cubic-bezier(0.16, 1, 0.3, 1);
}

.popover-enter-from,
.popover-leave-to {
  opacity: 0;
  transform: scale(0.95);
}
</style>
