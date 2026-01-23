<script setup lang="ts">
/**
 * ModernSelect - 现代化选择器组件
 * 风格：Swiss Modernism 2.0 (Bold, Sharp)
 */
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
  allowCreate?: boolean 
  placement?: 'top' | 'bottom'
  dropdownWidth?: string | number
}>(), {
  modelValue: '',
  options: () => [],
  placeholder: 'SELECT...',
  searchable: false,
  loading: false,
  disabled: false,
  allowCreate: false,
  placement: 'bottom',
  dropdownWidth: ''
})

const emit = defineEmits<{
  (e: 'update:modelValue', value: string): void
  (e: 'change', value: string): void
  (e: 'select', option: Option): void 
}>()

const isOpen = ref(false)
const searchQuery = ref('')
const containerRef = ref<HTMLElement | null>(null)
const inputRef = ref<HTMLInputElement | null>(null)

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
       const filteredSub = opt.options.filter((sub: Option) => 
         sub.label.toLowerCase().includes(query) || 
         sub.value.toLowerCase().includes(query)
       )
       if (filteredSub.length > 0) {
         result.push({ ...opt, options: filteredSub })
       }
    } else {
       if (opt.label.toLowerCase().includes(query) || opt.value.toLowerCase().includes(query)) {
         result.push(opt)
       }
    }
  }
  return result
})

const selectedLabel = computed(() => {
  if (!props.modelValue) return ''
  
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
    <!-- Trigger - Sharp, Bold -->
    <div 
      class="flex items-center justify-between w-full bg-surface border border-strong rounded-sm px-4 py-2 text-xs font-black uppercase tracking-widest text-text-primary transition-all cursor-pointer"
      :class="[
        disabled ? 'opacity-30 cursor-not-allowed' : 'hover:border-brand',
        isOpen ? '!border-brand ring-4 ring-brand/5' : ''
      ]"
      @click="toggle"
    >
      <div class="truncate select-none" :class="!modelValue ? 'text-text-muted' : ''">
        {{ selectedLabel || placeholder }}
      </div>
      <div class="flex items-center gap-2 ml-2 text-brand">
         <span v-if="loading" class="animate-spin">⟳</span>
         <span v-else class="text-[8px] transition-transform duration-200" :class="isOpen ? 'rotate-180' : ''">▼</span>
      </div>
    </div>

    <!-- Dropdown Menu - Radical Swiss -->
    <div 
      v-if="isOpen"
      class="absolute z-50 mt-1 bg-dark-bg border-2 border-brand rounded-sm shadow-xl overflow-hidden flex flex-col max-h-[300px]"
      :class="[
        placement === 'top' ? 'bottom-full mb-2' : 'top-full mt-2',
        dropdownWidth ? 'right-0' : 'left-0 right-0'
      ]"
      :style="dropdownWidth ? { width: typeof dropdownWidth === 'number' ? dropdownWidth + 'px' : dropdownWidth } : {}"
    >
      <!-- Search Input -->
      <div v-if="searchable || allowCreate" class="p-3 border-b border-subtle">
        <input 
          ref="inputRef"
          v-model="searchQuery"
          type="text"
          class="w-full bg-surface border border-strong rounded-sm px-3 py-2 text-xs font-bold uppercase tracking-widest text-text-primary focus:border-brand focus:outline-none placeholder-text-muted"
          :placeholder="allowCreate ? 'ENTER VALUE...' : 'SEARCH...'"
          @keydown.enter.prevent="handleInputEnter"
        />
      </div>

      <!-- Options List -->
      <div class="overflow-y-auto custom-scrollbar p-1">
        <template v-for="(item, idx) in filteredOptions" :key="idx">
           <!-- Group Header - Bold Swiss -->
           <div v-if="'options' in item" class="mt-4 first:mt-0 mb-2">
              <div class="text-[8px] font-black text-brand uppercase tracking-[0.3em] px-4 py-1 bg-brand/5 border-y border-brand/10">{{ item.label }}</div>
              <div 
                v-for="opt in item.options" 
                :key="opt.value"
                class="px-4 py-3 text-[10px] font-bold uppercase tracking-widest cursor-pointer transition-colors flex items-center justify-between group/item"
                :class="modelValue === opt.value ? 'bg-brand text-text-inverse' : 'text-text-secondary hover:bg-white/5'"
                @click="select(opt)"
              >
                <span class="truncate">{{ opt.label }}</span>
                <span v-if="modelValue === opt.value" class="font-black">SELECTED</span>
              </div>
           </div>
           
           <!-- Single Option -->
           <div 
              v-else 
              class="px-4 py-3 text-[10px] font-bold uppercase tracking-widest cursor-pointer transition-colors flex items-center justify-between group/item"
              :class="modelValue === (item as Option).value ? 'bg-brand text-text-inverse' : 'text-text-secondary hover:bg-white/5'"
              @click="select(item as Option)"
            >
              <span class="truncate">{{ (item as Option).label }}</span>
              <span v-if="modelValue === (item as Option).value" class="font-black">SELECTED</span>
            </div>
        </template>

        <div v-if="filteredOptions.length === 0" class="px-4 py-8 text-center text-[10px] font-black text-text-muted uppercase tracking-[0.2em]">
           <span v-if="allowCreate && searchQuery">PRESS ENTER TO USE: "{{ searchQuery }}"</span>
           <span v-else>PROTOCOL NOT FOUND</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.custom-scrollbar::-webkit-scrollbar {
  width: 2px;
}
.custom-scrollbar::-webkit-scrollbar-track {
  background: transparent;
}
.custom-scrollbar::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.1);
}
</style>
