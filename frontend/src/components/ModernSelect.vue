<script setup lang="ts">
import { computed, ref, onMounted, onUnmounted, nextTick } from 'vue'

interface Option {
  label: string
  value: string
  [key: string]: any
}

const props = withDefaults(defineProps<{
  modelValue?: string | null
  options: Option[] | string[]
  placeholder?: string
  searchable?: boolean
  loading?: boolean
  disabled?: boolean
  allowCreate?: boolean // 允许输入不存在的选项
  placement?: 'top' | 'bottom'
}>(), {
  modelValue: '',
  options: () => [],
  placeholder: '请选择...',
  searchable: false,
  loading: false,
  disabled: false,
  allowCreate: false,
  placement: 'bottom'
})

const emit = defineEmits<{
  (e: 'update:modelValue', value: string): void
  (e: 'change', value: string): void
}>()

const isOpen = ref(false)
const searchQuery = ref('')
const containerRef = ref<HTMLElement | null>(null)
const inputRef = ref<HTMLInputElement | null>(null)

// 统一处理 options 格式
const normalizedOptions = computed(() => {
  return props.options.map(opt => {
    if (typeof opt === 'string') {
      return { label: opt, value: opt }
    }
    return opt
  })
})

const filteredOptions = computed(() => {
  if (!props.searchable || !searchQuery.value) return normalizedOptions.value
  const query = searchQuery.value.toLowerCase()
  return normalizedOptions.value.filter(opt => 
    opt.label.toLowerCase().includes(query) || 
    opt.value.toLowerCase().includes(query)
  )
})

const selectedLabel = computed(() => {
  if (!props.modelValue) return ''
  const opt = normalizedOptions.value.find(o => o.value === props.modelValue)
  return opt ? opt.label : props.modelValue
})

function toggle() {
  if (props.disabled) return
  if (isOpen.value) {
    close()
  } else {
    open()
  }
}

function open() {
  isOpen.value = true
  searchQuery.value = ''
  nextTick(() => {
    if (props.searchable && inputRef.value) {
      inputRef.value.focus()
    }
  })
}

function close() {
  isOpen.value = false
  // 如果允许创建且有搜索内容，且没有选中项，则尝试使用搜索内容
  if (props.allowCreate && searchQuery.value && searchQuery.value !== props.modelValue) {
      // 这里的逻辑可以根据需求调整，比如是否要在 blur 时自动应用
  }
}

function select(opt: Option) {
  emit('update:modelValue', opt.value)
  emit('change', opt.value)
  close()
}

function handleInputEnter() {
  if (filteredOptions.value.length > 0) {
    select(filteredOptions.value[0])
  } else if (props.allowCreate && searchQuery.value) {
    emit('update:modelValue', searchQuery.value)
    emit('change', searchQuery.value)
    close()
  }
}

// Click outside to close
function handleClickOutside(event: MouseEvent) {
  if (containerRef.value && !containerRef.value.contains(event.target as Node)) {
    close()
  }
}

onMounted(() => {
  document.addEventListener('click', handleClickOutside)
})

onUnmounted(() => {
  document.removeEventListener('click', handleClickOutside)
})
</script>

<template>
  <div ref="containerRef" class="relative group w-full">
    <!-- Trigger -->
    <div 
      class="flex items-center justify-between w-full bg-black/20 border border-white/10 rounded-lg px-3 py-2 text-sm text-gray-200 transition-colors cursor-pointer"
      :class="[
        disabled ? 'opacity-50 cursor-not-allowed' : 'hover:bg-white/5 hover:border-brand/30',
        isOpen ? '!border-brand/50 ring-1 ring-brand/20' : ''
      ]"
      @click="toggle"
    >
      <div class="truncate select-none" :class="!modelValue ? 'text-gray-500' : ''">
        {{ selectedLabel || placeholder }}
      </div>
      <div class="flex items-center gap-2 ml-2 text-gray-500">
         <span v-if="loading" class="animate-spin text-brand">⟳</span>
         <span v-else class="text-[10px] transition-transform duration-200" :class="isOpen ? 'rotate-180' : ''">▼</span>
      </div>
    </div>

    <!-- Dropdown Menu -->
    <div 
      v-if="isOpen"
      class="absolute left-0 right-0 z-50 mt-1 bg-[#18181c] border border-white/10 rounded-xl shadow-xl overflow-hidden flex flex-col max-h-[260px]"
      :class="placement === 'top' ? 'bottom-full mb-1' : 'top-full mt-1'"
    >
      <!-- Search Input -->
      <div v-if="searchable || allowCreate" class="p-2 border-b border-white/5">
        <input 
          ref="inputRef"
          v-model="searchQuery"
          type="text"
          class="w-full bg-black/20 border border-white/5 rounded-lg px-2 py-1.5 text-xs text-gray-200 focus:border-brand/50 focus:outline-none placeholder-gray-600"
          :placeholder="allowCreate ? '搜索或输入新值...' : '搜索...'"
          @keydown.enter.prevent="handleInputEnter"
        />
      </div>

      <!-- Options List -->
      <div class="overflow-y-auto custom-scrollbar p-1">
        <div 
          v-for="opt in filteredOptions" 
          :key="opt.value"
          class="px-3 py-2 rounded-lg text-sm cursor-pointer transition-colors flex items-center justify-between group/item"
          :class="modelValue === opt.value ? 'bg-brand/10 text-brand' : 'text-gray-300 hover:bg-white/5'"
          @click="select(opt)"
        >
          <span class="truncate">{{ opt.label }}</span>
          <span v-if="modelValue === opt.value" class="text-brand text-xs">✓</span>
        </div>

        <div v-if="filteredOptions.length === 0" class="px-3 py-4 text-center text-xs text-gray-500">
           <span v-if="allowCreate && searchQuery">按回车使用 "{{ searchQuery }}"</span>
           <span v-else>无匹配项</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.custom-scrollbar::-webkit-scrollbar {
  width: 4px;
}
.custom-scrollbar::-webkit-scrollbar-track {
  background: transparent;
}
.custom-scrollbar::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.1);
  border-radius: 2px;
}
.custom-scrollbar:hover::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.2);
}
</style>

