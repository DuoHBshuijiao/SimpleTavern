<script setup lang="ts">
import { computed, ref, watch } from 'vue'

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

const filteredModels = computed(() => {
  if (!searchQuery.value) return props.models
  const q = searchQuery.value.toLowerCase()
  return props.models.filter(m => m.toLowerCase().includes(q))
})

function toggle(m: string) {
  if (selectedModels.value.has(m)) {
    selectedModels.value.delete(m)
  } else {
    selectedModels.value.add(m)
  }
}

function selectAllFiltered() {
  filteredModels.value.forEach(m => selectedModels.value.add(m))
}

function deselectAllFiltered() {
  filteredModels.value.forEach(m => selectedModels.value.delete(m))
}

function close() {
  emit('update:show', false)
}

function confirm() {
  emit('confirm', Array.from(selectedModels.value))
  close()
}
</script>

<template>
  <div v-if="show" class="modal">
    <div class="modal-backdrop" @click="close"></div>
    <div class="modal-content chat-modal-width-520-92 max-h-[80vh]">
      <div class="modal-header">
        <h3 class="modal-title">筛选模型</h3>
        <button class="modal-close" @click="close">✕</button>
      </div>

      <div class="modal-body flex flex-col min-h-0">
        <div class="space-y-4 flex-1 flex flex-col min-h-0">
          <div class="form-group">
            <input 
              v-model="searchQuery"
              type="text"
              placeholder="搜索模型..."
              class="input"
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
              <span class="animate-spin mr-2">⟳</span> 加载中...
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
                  :class="selectedModels.has(m) ? 'bg-brand border-brand' : 'border-gray-600'"
                >
                  <span v-if="selectedModels.has(m)" class="text-white text-[10px] font-bold">✓</span>
                </div>
                <span class="text-sm text-gray-300 truncate">{{ m }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="modal-footer">
        <span class="text-xs text-gray-400 mr-auto">已选中 {{ selectedModels.size }} 个</span>
        <button class="btn btn-secondary" @click="close">取消</button>
        <button class="btn btn-primary" @click="confirm">添加选中项</button>
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
