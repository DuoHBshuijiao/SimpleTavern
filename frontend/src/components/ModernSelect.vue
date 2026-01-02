<script setup lang="ts">
import { computed, ref, onMounted, onUnmounted, nextTick } from 'vue'

interface Option {
  label: string
  value: string
  [key: string]: any
}

interface OptionGroup {
  label: string
  options: Option[]
}

const props = withDefaults(defineProps<{
  modelValue?: string | null
  options: (Option | OptionGroup | string)[]
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
  (e: 'select', option: Option): void // 新增，方便上层获取完整option对象(包含presetId等)
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
    if ('options' in opt && Array.isArray(opt.options)) {
      return {
        label: opt.label,
        options: opt.options.map((sub: string | Option) => {
           if (typeof sub === 'string') return { label: sub, value: sub }
           return sub
        })
      } as OptionGroup
    }
    return opt as Option
  })
})

const filteredOptions = computed(() => {
  if (!props.searchable || !searchQuery.value) return normalizedOptions.value
  const query = searchQuery.value.toLowerCase()
  
  const result: (Option | OptionGroup)[] = []
  
  for (const opt of normalizedOptions.value) {
    if ('options' in opt) {
       // It's a group
       const filteredSub = opt.options.filter((sub: Option) => 
         sub.label.toLowerCase().includes(query) || 
         sub.value.toLowerCase().includes(query)
       )
       if (filteredSub.length > 0) {
         result.push({ ...opt, options: filteredSub })
       }
    } else {
       // It's a single option
       if (opt.label.toLowerCase().includes(query) || opt.value.toLowerCase().includes(query)) {
         result.push(opt)
       }
    }
  }
  return result
})

const selectedLabel = computed(() => {
  if (!props.modelValue) return ''
  
  // Flat search
  for (const opt of normalizedOptions.value) {
     if ('options' in opt) {
        const found = opt.options.find((sub: Option) => sub.value === props.modelValue)
        if (found) return found.label
     } else {
        if (opt.value === props.modelValue) return opt.label
     }
  }
  
  return props.modelValue
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
}

function select(opt: Option) {
  emit('update:modelValue', opt.value)
  emit('change', opt.value)
  emit('select', opt)
  close()
}

function handleInputEnter() {
  // If there is exactly one match (or first match in list), select it?
  // For safety, only select if we have filtered options.
  
  // Flatten filtered options to check first match
  let firstMatch: Option | null = null
  
  if (filteredOptions.value.length > 0) {
     const first = filteredOptions.value[0]
     if (first && 'options' in first) {
        if (first.options.length > 0) firstMatch = first.options[0] ?? null
     } else if (first) {
        firstMatch = first as Option
     }
  }

  if (firstMatch) {
    select(firstMatch)
  } else if (props.allowCreate && searchQuery.value) {
    const newOpt = { label: searchQuery.value, value: searchQuery.value }
    emit('update:modelValue', searchQuery.value)
    emit('change', searchQuery.value)
    emit('select', newOpt)
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
        <template v-for="(item, idx) in filteredOptions" :key="idx">
           <!-- Group Header -->
           <div v-if="'options' in item" class="px-2 py-1">
              <div class="text-[10px] font-bold text-gray-500 uppercase tracking-wider px-1 mb-1">{{ item.label }}</div>
              <div 
                v-for="opt in item.options" 
                :key="opt.value"
                class="px-3 py-2 rounded-lg text-sm cursor-pointer transition-colors flex items-center justify-between group/item pl-4"
                :class="modelValue === opt.value ? 'bg-brand/10 text-brand' : 'text-gray-300 hover:bg-white/5'"
                @click="select(opt)"
              >
                <span class="truncate">{{ opt.label }}</span>
                <span v-if="modelValue === opt.value" class="text-brand text-xs">✓</span>
              </div>
           </div>
           
           <!-- Single Option -->
           <div 
              v-else 
              class="px-3 py-2 rounded-lg text-sm cursor-pointer transition-colors flex items-center justify-between group/item"
              :class="modelValue === (item as Option).value ? 'bg-brand/10 text-brand' : 'text-gray-300 hover:bg-white/5'"
              @click="select(item as Option)"
            >
              <span class="truncate">{{ (item as Option).label }}</span>
              <span v-if="modelValue === (item as Option).value" class="text-brand text-xs">✓</span>
            </div>
        </template>

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
