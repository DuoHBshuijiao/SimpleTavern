<script setup lang="ts">
/**
 * ModelSelectorModal - 模型选择器弹窗组件
 *
 * 组件职责：
 * - 提供模型筛选和选择功能
 * - 支持搜索过滤模型
 * - 支持多选模型
 * - 支持全选/取消全选当前筛选结果
 *
 * Props说明：
 * - show: 是否显示弹窗（v-model:show）
 * - models: 模型列表
 * - loading: 是否加载中
 *
 * Emits说明：
 * - update:show: 更新显示状态（v-model:show）
 * - confirm: 确认选择，传递选中的模型列表
 *
 * 使用的Composables：
 * 无
 *
 * 使用的Stores：
 * 无
 *
 * 文件关系：
 *    - 被导入：被components/SettingsDrawer.vue使用
 *    - 导入：导入vue的computed、ref、watch
 *    - 依赖：依赖vue
 *    - 位置：组件层，提供模型选择功能
 */
import { computed, ref, watch } from 'vue'
import { X, Check, Loader2 } from 'lucide-vue-next'

const props = defineProps<{
  show: boolean
  models: string[]
  loading?: boolean
}>()

const emit = defineEmits<{
  (e: 'update:show', v: boolean): void
  (e: 'confirm', selected: string[]): void
}>()

const searchQuery = ref('')
const selectedModels = ref<Set<string>>(new Set())

watch(
  () => props.show,
  (val) => {
    if (val) {
      searchQuery.value = ''
      selectedModels.value = new Set()
    }
  }
)

/**
 * 计算过滤后的模型列表
 *
 * 根据搜索查询过滤模型列表，不区分大小写。
 */
const filteredModels = computed(() => {
  if (!searchQuery.value) return props.models
  const q = searchQuery.value.toLowerCase()
  return props.models.filter(m => m.toLowerCase().includes(q))
})

/**
 * 切换模型选择
 *
 * 切换指定模型的选中状态（选中/取消选中）。
 *
 * @param {string} m - 模型名称
 */
function toggle(m: string) {
  if (selectedModels.value.has(m)) {
    selectedModels.value.delete(m)
  } else {
    selectedModels.value.add(m)
  }
}

/**
 * 全选当前筛选结果
 *
 * 将当前筛选结果中的所有模型添加到选中集合。
 */
function selectAllFiltered() {
  filteredModels.value.forEach(m => selectedModels.value.add(m))
}

/**
 * 取消全选当前筛选结果
 *
 * 从选中集合中移除当前筛选结果中的所有模型。
 */
function deselectAllFiltered() {
  filteredModels.value.forEach(m => selectedModels.value.delete(m))
}

/**
 * 关闭弹窗
 *
 * 触发update:show事件，传递false。
 */
function close() {
  emit('update:show', false)
}

/**
 * 确认选择
 *
 * 触发confirm事件，传递选中的模型列表，然后关闭弹窗。
 */
function confirm() {
  emit('confirm', Array.from(selectedModels.value))
  close()
}
</script>

<template>
  <Transition name="modal">
    <div v-if="show" class="modal">
      <div class="modal-backdrop" @click="close"></div>
      <div class="modal-content chat-modal-width-520-92 max-h-[80vh] glass-panel">
        <div class="modal-header">
          <h3 class="modal-title text-slate-50">筛选模型</h3>
          <button class="modal-close" @click="close">
              <X class="w-5 h-5" />
          </button>
        </div>

        <div class="modal-body flex flex-col min-h-0">
          <div class="space-y-4 flex-1 flex flex-col min-h-0">
            <div class="form-group">
              <input 
                v-model="searchQuery"
                type="text"
                placeholder="搜索模型..."
                class="input bg-black/20 border-white/10 focus:border-brand-a50"
              />
            </div>

            <div class="flex items-center justify-between text-xs text-gray-400">
              <span>共 {{ props.models.length }} 个模型，当前显示 {{ filteredModels.length }} 个</span>
              <div class="flex gap-2">
                <button class="hover:text-brand transition-colors" @click="selectAllFiltered">全选当前</button>
                <button class="hover:text-gray-200 transition-colors" @click="deselectAllFiltered">取消当前</button>
              </div>
            </div>

            <div class="flex-1 overflow-y-auto custom-scrollbar bg-black/20 rounded-lg border border-white/5 p-2 min-h-[200px]">
              <div v-if="loading" class="flex items-center justify-center h-full text-gray-500">
                <Loader2 class="animate-spin w-4 h-4 mr-2" /> 加载中...
              </div>
              <div v-else-if="filteredModels.length === 0" class="text-center text-gray-600 py-8">
                未找到匹配模型
              </div>
              <div v-else class="space-y-1">
                <div 
                  v-for="m in filteredModels" 
                  :key="m"
                  class="flex items-center gap-3 px-2 py-1.5 rounded hover:bg-white/5 cursor-pointer select-none transition-colors"
                  @click="toggle(m)"
                >
                  <div 
                    class="w-4 h-4 rounded border flex items-center justify-center transition-colors"
                    :class="selectedModels.has(m) ? 'bg-brand border-brand' : 'border-[var(--color-border-strong)]'"
                  >
                    <Check v-if="selectedModels.has(m)" class="text-white w-2.5 h-2.5" />
                  </div>
                  <span class="text-sm text-gray-300 truncate">{{ m }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div class="modal-footer">
          <span class="text-xs text-gray-400 mr-auto">已选中 {{ selectedModels.size }} 个</span>
          <button class="btn btn-secondary bg-white/5 hover:bg-white/10 text-gray-300 border border-white/5" @click="close">取消</button>
          <button class="btn btn-primary" @click="confirm">添加选中项</button>
        </div>
      </div>
    </div>
  </Transition>
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
