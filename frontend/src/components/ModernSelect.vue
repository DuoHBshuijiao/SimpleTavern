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
 *    - 导入：导入vue的computed、ref、watch、onMounted、onUnmounted、nextTick
 *    - 依赖：依赖vue
 *    - 位置：组件层，提供选择器功能
 */
import { computed, ref, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { Check, Loader2, ChevronDown } from 'lucide-vue-next'
import { useViewportNarrowPortrait } from '../composables/useViewportNarrowPortrait'

/** 窄竖屏下下拉横向铺满视口左右留白（与站内 calc(100vw - 2rem) 一类间距对齐） */
const NARROW_SELECT_GUTTER = '1rem'

const { isNarrowPortrait } = useViewportNarrowPortrait()

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
  selectedPresetId?: string | null
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
  selectedPresetId: null,
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
const triggerRef = ref<HTMLElement | null>(null)
const dropdownRef = ref<HTMLElement | null>(null)
const inputRef = ref<HTMLInputElement | null>(null)
const dropdownStyle = ref<Record<string, string>>({})

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

function optionPresetId(opt: Option): string {
  return opt.presetId == null ? '' : String(opt.presetId)
}

function isOptionSelected(opt: Option): boolean {
  if (props.modelValue !== opt.value) return false
  if (props.selectedPresetId == null || props.selectedPresetId === '') return true
  return optionPresetId(opt) === String(props.selectedPresetId)
}

/**
 * 计算选中项的标签
 *
 * 根据modelValue从选项列表中查找对应的标签文本。
 * 如果未找到，则返回modelValue本身。
 */
const selectedLabel = computed(() => {
  if (!props.modelValue) return ''
  const exactMatches: Option[] = []
  const valueMatches: Option[] = []
  
  for (const opt of normalizedOptions.value) {
     if ('options' in opt) {
        for (const sub of opt.options) {
          if (sub.value !== props.modelValue) continue
          valueMatches.push(sub)
          if (isOptionSelected(sub)) {
            exactMatches.push(sub)
          }
        }
     } else {
        if (opt.value === props.modelValue) {
          valueMatches.push(opt)
          if (isOptionSelected(opt)) {
            exactMatches.push(opt)
          }
        }
     }
  }
  if (exactMatches.length > 0) return exactMatches[0]?.label ?? props.modelValue
  if (valueMatches.length > 0) return valueMatches[0]?.label ?? props.modelValue
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
 * 计算并更新下拉框的 fixed 定位样式（用于 Teleport 到 body 时脱离父级 overflow 裁剪）。
 * 窄竖屏（isNarrowPortrait）：横向左右固定留白、宽度自动铺满，不再按触发器右对齐固定像素宽，
 * 避免窄屏下列表挤在一侧；纵向仍锚定触发器上下方。
 * （LlmPresetNameCombobox / TtsVoiceInput 等为输入框内 absolute，不走此 Teleport 逻辑，无需同步改 props。）
 */
function updateDropdownPosition() {
  const trigger = triggerRef.value
  if (!trigger) return
  const rect = trigger.getBoundingClientRect()
  const style: Record<string, string> = { position: 'fixed' }
  if (props.placement === 'top') {
    style.bottom = `${window.innerHeight - rect.top + 4}px`
    style.top = 'auto'
  } else {
    style.top = `${rect.bottom + 4}px`
    style.bottom = 'auto'
  }
  if (isNarrowPortrait.value) {
    style.left = NARROW_SELECT_GUTTER
    style.right = NARROW_SELECT_GUTTER
    style.width = 'auto'
  } else if (props.dropdownWidth) {
    const raw = props.dropdownWidth
    const w = typeof raw === 'number' ? `${raw}px` : (/^\d+$/.test(String(raw)) ? `${raw}px` : String(raw))
    style.width = w
    style.right = `${window.innerWidth - rect.right}px`
    style.left = 'auto'
  } else {
    style.left = `${rect.left}px`
    style.width = `${rect.width}px`
  }
  dropdownStyle.value = style
}

let positionRaf = 0
let removePositionListeners: (() => void) | null = null

function scheduleUpdateDropdownPosition() {
  if (positionRaf) return
  positionRaf = requestAnimationFrame(() => {
    positionRaf = 0
    updateDropdownPosition()
  })
}

function attachDropdownPositionListeners() {
  removePositionListeners?.()
  const schedule = () => scheduleUpdateDropdownPosition()

  const onScroll = () => schedule()
  const onWinResize = () => schedule()

  document.addEventListener('scroll', onScroll, true)
  window.addEventListener('resize', onWinResize)

  let ro: ResizeObserver | undefined
  const trigger = triggerRef.value
  if (trigger && typeof ResizeObserver !== 'undefined') {
    ro = new ResizeObserver(schedule)
    ro.observe(trigger)
  }

  const vv = typeof window !== 'undefined' ? window.visualViewport : null
  const onVvResize = () => schedule()
  const onVvScroll = () => schedule()
  if (vv) {
    vv.addEventListener('resize', onVvResize)
    vv.addEventListener('scroll', onVvScroll)
  }

  removePositionListeners = () => {
    document.removeEventListener('scroll', onScroll, true)
    window.removeEventListener('resize', onWinResize)
    ro?.disconnect()
    if (vv) {
      vv.removeEventListener('resize', onVvResize)
      vv.removeEventListener('scroll', onVvScroll)
    }
    removePositionListeners = null
  }
}

watch(isOpen, (open) => {
  if (open) {
    nextTick(() => {
      attachDropdownPositionListeners()
    })
  } else {
    removePositionListeners?.()
    if (positionRaf) {
      cancelAnimationFrame(positionRaf)
      positionRaf = 0
    }
  }
})

/**
 * 打开下拉框
 *
 * 设置打开状态，清空搜索查询，如果可搜索则聚焦输入框。
 * 使用 Teleport 时在 nextTick 中计算下拉的 fixed 定位。
 */
function open() {
  isOpen.value = true
  searchQuery.value = ''
  nextTick(() => {
    updateDropdownPosition()
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
  const target = event.target as Node
  if (containerRef.value?.contains(target) || dropdownRef.value?.contains(target)) return
  close()
}

onMounted(() => {
  document.addEventListener('click', handleClickOutside)
})

onUnmounted(() => {
  document.removeEventListener('click', handleClickOutside)
  removePositionListeners?.()
  if (positionRaf) {
    cancelAnimationFrame(positionRaf)
    positionRaf = 0
  }
})
</script>

<template>
  <div ref="containerRef" class="relative group w-full">
    <!-- Trigger -->
    <div
      ref="triggerRef"
      class="flex items-center justify-between w-full bg-surface-muted border border-[var(--color-border)] rounded-lg px-3 py-2 text-sm text-[var(--color-text)] transition-all cursor-pointer shadow-sm"
      :class="[
        disabled ? 'opacity-50 cursor-not-allowed' : 'hover:bg-surface-hover hover:border-brand-a30',
        isOpen ? '!border-brand-a50 ring-1 ring-brand-a20' : ''
      ]"
      @click="toggle"
    >
      <div class="truncate select-none" :class="!modelValue ? 'text-[var(--color-text-muted)]' : ''">
        {{ selectedLabel || placeholder }}
      </div>
        <div class="flex items-center gap-2 ml-2 text-[var(--color-text-muted)]">
         <Loader2 v-if="loading" class="animate-spin text-brand w-3 h-3" />
         <ChevronDown v-else class="w-3 h-3 transition-transform duration-200" :class="isOpen ? 'rotate-180' : ''" />
      </div>
    </div>

    <!-- Dropdown Menu（Teleport 到 body 避免被父级 overflow-hidden 裁剪） -->
    <Teleport to="body">
      <Transition name="select-dropdown-pop">
        <div
          v-if="isOpen"
          ref="dropdownRef"
          class="z-dropdown select-dropdown theme-panel-bg rounded-xl shadow-glass-panel overflow-hidden flex flex-col max-h-[320px] border border-[var(--color-border)] backdrop-blur-xl backdrop-saturate-[1.8]"
          :class="placement === 'top' ? 'select-dropdown-pop--top' : 'select-dropdown-pop--bottom'"
          :style="dropdownStyle"
        >
      <!-- Search Input -->
      <div v-if="searchable || allowCreate" class="p-2 border-b border-[var(--color-border-subtle)]">
        <input 
          ref="inputRef"
          v-model="searchQuery"
          type="text"
          class="input input-sm w-full"
          :placeholder="allowCreate ? '搜索或输入新值...' : '搜索...'"
          @keydown.enter.prevent="handleInputEnter"
        />
      </div>

      <!-- Options List -->
      <div class="select-dropdown-options overflow-y-auto custom-scrollbar p-1">
        <template v-for="(item, idx) in filteredOptions">
           <!-- Group Header -->
           <div v-if="'options' in item" :key="`group-${idx}`" class="px-2 py-1">
              <div class="text-[10px] font-bold text-[var(--color-text-muted)] uppercase tracking-wider px-1 mb-1">{{ item.label }}</div>
              <div 
                v-for="opt in item.options" 
                :key="opt.value"
                class="px-3 py-2 rounded-lg text-sm cursor-pointer transition-colors flex items-center justify-between group/item pl-4"
                :class="isOptionSelected(opt) ? 'bg-brand-a20 text-brand' : 'text-[var(--color-text-secondary)] hover:bg-surface-muted'"
                @click="select(opt)"
              >
                <span class="truncate">{{ opt.label }}</span>
                <Check v-if="isOptionSelected(opt)" class="text-brand w-3 h-3" />
              </div>
           </div>
           
           <!-- Single Option -->
            <div 
              v-else 
              :key="`single-${idx}`"
              class="px-3 py-2 rounded-lg text-sm cursor-pointer transition-colors flex items-center justify-between group/item"
              :class="isOptionSelected(item) ? 'bg-brand-a20 text-brand' : 'text-[var(--color-text-secondary)] hover:bg-surface-muted'"
              @click="select(item)"
            >
              <span class="truncate">{{ item.label }}</span>
              <Check v-if="isOptionSelected(item)" class="text-brand w-3 h-3" />
            </div>
        </template>

        <div v-if="filteredOptions.length === 0" class="px-3 py-4 text-center text-xs text-[var(--color-text-muted)]">
           <span v-if="allowCreate && searchQuery">按回车使用 "{{ searchQuery }}"</span>
           <span v-else>无匹配项</span>
        </div>
      </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<style scoped>
.select-dropdown {
  background:
    linear-gradient(
      to bottom right,
      color-mix(in srgb, var(--color-brand-a20) 55%, var(--app-panel-from)),
      color-mix(in srgb, var(--color-brand-a10) 45%, var(--app-panel-to))
    );
}

.select-dropdown-options {
  background:
    linear-gradient(
      to bottom,
      color-mix(in srgb, var(--color-brand-a10) 55%, transparent),
      transparent 18%,
      transparent 82%,
      color-mix(in srgb, var(--color-brand-a10) 35%, transparent)
    );
}

.custom-scrollbar::-webkit-scrollbar {
  width: 4px;
}
.custom-scrollbar::-webkit-scrollbar-track {
  background: transparent;
}
.custom-scrollbar::-webkit-scrollbar-thumb {
  background: var(--color-border);
  border-radius: 2px;
}
.custom-scrollbar:hover::-webkit-scrollbar-thumb {
  background: var(--color-border-strong);
}

/* 下拉：自上方滑入；上拉：自下方滑入（与 placement 一致） */
.select-dropdown-pop-enter-active,
.select-dropdown-pop-leave-active {
  transition:
    transform 0.2s cubic-bezier(0.33, 1, 0.68, 1),
    opacity 0.2s ease;
}

.select-dropdown-pop-enter-from.select-dropdown-pop--bottom,
.select-dropdown-pop-leave-to.select-dropdown-pop--bottom {
  transform: translateY(-0.5rem);
  opacity: 0;
}

.select-dropdown-pop-enter-to.select-dropdown-pop--bottom,
.select-dropdown-pop-leave-from.select-dropdown-pop--bottom {
  transform: translateY(0);
  opacity: 1;
}

.select-dropdown-pop-enter-from.select-dropdown-pop--top,
.select-dropdown-pop-leave-to.select-dropdown-pop--top {
  transform: translateY(0.5rem);
  opacity: 0;
}

.select-dropdown-pop-enter-to.select-dropdown-pop--top,
.select-dropdown-pop-leave-from.select-dropdown-pop--top {
  transform: translateY(0);
  opacity: 1;
}

@media (prefers-reduced-motion: reduce) {
  .select-dropdown-pop-enter-active,
  .select-dropdown-pop-leave-active {
    transition: opacity 0.15s ease;
  }

  .select-dropdown-pop-enter-from.select-dropdown-pop--bottom,
  .select-dropdown-pop-leave-to.select-dropdown-pop--bottom,
  .select-dropdown-pop-enter-from.select-dropdown-pop--top,
  .select-dropdown-pop-leave-to.select-dropdown-pop--top {
    transform: none;
  }
}
</style>
