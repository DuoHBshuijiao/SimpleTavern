<script setup lang="ts">
/**
 * ModernSelect - 现代化选择器组件
 *
 * 组件职责：
 * - 提供下拉选择功能，支持单选
 * - 支持搜索过滤选项
 * - 支持分组选项
 * - 支持允许创建新选项
 * - 支持自定义下拉位置和宽度
 *
 * Props说明：
 * - modelValue: 当前选中的值（v-model）
 * - options: 选项列表，可以是字符串数组、选项对象数组或分组选项数组
 * - placeholder: 占位符文本
 * - searchable: 是否可搜索
 * - loading: 是否加载中
 * - disabled: 是否禁用
 * - allowCreate: 是否允许创建新选项
 * - placement: 下拉位置（'top'或'bottom'）
 * - dropdownWidth: 下拉框宽度（数字或字符串）
 *
 * Emits说明：
 * - update:modelValue: 更新选中值（v-model）
 * - change: 值改变时触发
 * - select: 选择选项时触发，传递完整选项对象
 *
 * 使用的Composables：
 * 无
 *
 * 使用的Stores：
 * 无
 *
 * 文件关系：
 *    - 被导入：被views/ChatPage.vue等组件使用
 *    - 导入：导入vue的computed、ref、onMounted、onUnmounted、nextTick
 *    - 依赖：依赖vue
 *    - 位置：组件层，提供选择器功能
 */
import { computed, ref, onMounted, onUnmounted, nextTick } from 'vue'
import { Check, Loader2, ChevronDown } from 'lucide-vue-next'

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
  dropdownWidth?: string | number
}>(), {
  modelValue: '',
  options: () => [],
  placeholder: '请选择...',
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
  (e: 'select', option: Option): void // 新增，方便上层获取完整option对象(包含presetId等)
}>()

const isOpen = ref(false)
const searchQuery = ref('')
const containerRef = ref<HTMLElement | null>(null)
const inputRef = ref<HTMLInputElement | null>(null)

/**
 * 计算规范化后的选项列表
 *
 * 统一处理options格式，将字符串转换为选项对象，将分组选项规范化。
 */
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

/**
 * 计算过滤后的选项列表
 *
 * 如果可搜索且有搜索查询，则根据查询过滤选项（不区分大小写）。
 * 支持分组选项的过滤。
 */
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

/**
 * 计算选中项的标签
 *
 * 根据modelValue从选项列表中查找对应的标签文本。
 * 如果未找到，则返回modelValue本身。
 */
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

/**
 * 切换下拉框状态
 *
 * 如果禁用则不执行。如果已打开则关闭，否则打开。
 */
function toggle() {
  if (props.disabled) return
  if (isOpen.value) {
    close()
  } else {
    open()
  }
}

/**
 * 打开下拉框
 *
 * 设置打开状态，清空搜索查询，如果可搜索则聚焦输入框。
 */
function open() {
  isOpen.value = true
  searchQuery.value = ''
  nextTick(() => {
    if (props.searchable && inputRef.value) {
      inputRef.value.focus()
    }
  })
}

/**
 * 关闭下拉框
 *
 * 设置关闭状态。
 */
function close() {
  isOpen.value = false
}

/**
 * 选择选项
 *
 * 触发update:modelValue、change和select事件，然后关闭下拉框。
 *
 * @param {Option} opt - 选中的选项
 */
function select(opt: Option) {
  emit('update:modelValue', opt.value)
  emit('change', opt.value)
  emit('select', opt)
  close()
}

/**
 * 处理输入框回车事件
 *
 * 如果有第一个匹配项则选择它，如果允许创建且输入框有内容则创建新选项。
 */
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

/**
 * 处理点击外部事件
 *
 * 当点击下拉框外部时关闭下拉框。
 *
 * @param {MouseEvent} event - 鼠标事件
 */
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
      class="flex items-center justify-between w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-gray-200 transition-all cursor-pointer shadow-sm"
      :class="[
        disabled ? 'opacity-50 cursor-not-allowed' : 'hover:bg-white/10 hover:border-brand/30',
        isOpen ? '!border-brand/50 ring-1 ring-brand/20' : ''
      ]"
      @click="toggle"
    >
      <div class="truncate select-none" :class="!modelValue ? 'text-gray-500' : ''">
        {{ selectedLabel || placeholder }}
      </div>
      <div class="flex items-center gap-2 ml-2 text-gray-500">
         <Loader2 v-if="loading" class="animate-spin text-brand w-3 h-3" />
         <ChevronDown v-else class="w-3 h-3 transition-transform duration-200" :class="isOpen ? 'rotate-180' : ''" />
      </div>
    </div>

    <!-- Dropdown Menu -->
    <div 
      v-if="isOpen"
      class="absolute z-dropdown mt-1 glass-panel rounded-xl shadow-2xl overflow-hidden flex flex-col max-h-[260px] animate-in fade-in zoom-in-95 duration-200"
      :class="[
        placement === 'top' ? 'bottom-full mb-1' : 'top-full mt-1',
        dropdownWidth ? 'right-0' : 'left-0 right-0'
      ]"
      :style="dropdownWidth ? { width: typeof dropdownWidth === 'number' ? dropdownWidth + 'px' : dropdownWidth } : {}"
    >
      <!-- Search Input -->
      <div v-if="searchable || allowCreate" class="p-2 border-b border-white/5">
        <input 
          ref="inputRef"
          v-model="searchQuery"
          type="text"
          class="w-full bg-white/5 border border-white/10 rounded-lg px-2 py-1.5 text-xs text-gray-200 focus:border-brand/50 focus:outline-none placeholder-gray-500 focus:bg-white/10 transition-colors"
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
                :class="modelValue === opt.value ? 'bg-brand/20 text-brand' : 'text-gray-300 hover:bg-white/5'"
                @click="select(opt)"
              >
                <span class="truncate">{{ opt.label }}</span>
                <Check v-if="modelValue === opt.value" class="text-brand w-3 h-3" />
              </div>
           </div>
           
           <!-- Single Option -->
            <div 
              v-else 
              class="px-3 py-2 rounded-lg text-sm cursor-pointer transition-colors flex items-center justify-between group/item"
              :class="modelValue === (item as Option).value ? 'bg-brand/20 text-brand' : 'text-gray-300 hover:bg-white/5'"
              @click="select(item as Option)"
            >
              <span class="truncate">{{ (item as Option).label }}</span>
              <Check v-if="modelValue === (item as Option).value" class="text-brand w-3 h-3" />
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
