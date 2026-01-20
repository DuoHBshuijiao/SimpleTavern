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
      selectedModels.value = new Set() // 默认不全选，或者全选？通常全选比较方便，但如果几百个模型...
      // 考虑到可能有几百个模型，默认不选比较安全，或者让用户自己选
    }
  }
)

// 当模型列表加载完成后，如果没有选中项，是否要默认全选？
// 对于 OpenRouter 这种几百个模型的，默认全选是灾难。
// 对于本地 Ollama，默认全选是合理的。
// 折中方案：默认不选，提供“全选”按钮。

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
  <div v-if="show" class="fixed inset-0 z-[60] flex items-center justify-center p-4">
    <!-- Backdrop -->
    <div class="absolute inset-0 bg-black/60 backdrop-blur-sm" @click="close"></div>

    <!-- Modal -->
    <div class="relative w-full max-w-lg bg-[#18181c] border border-white/10 rounded-xl shadow-2xl flex flex-col max-h-[80vh]">
      <div class="flex items-center justify-between px-4 py-3 border-b border-white/5 bg-[#141418] rounded-t-xl">
        <h3 class="text-sm font-bold text-gray-200">筛选模型</h3>
        <button class="text-gray-400 hover:text-white" @click="close">✕</button>
      </div>

      <div class="p-4 space-y-3 flex-1 flex flex-col min-h-0">
        <div class="flex gap-2">
          <input 
            v-model="searchQuery"
            type="text"
            placeholder="搜索模型..."
            class="flex-1 bg-black/20 border border-white/10 rounded-lg px-3 py-1.5 text-sm text-gray-200 focus:border-brand/50 outline-none"
          />
        </div>

        <div class="flex items-center justify-between text-xs text-gray-400">
          <span>共 {{ props.models.length }} 个模型，当前显示 {{ filteredModels.length }} 个</span>
          <div class="flex gap-2">
            <button class="hover:text-brand" @click="selectAllFiltered">全选当前</button>
            <button class="hover:text-gray-200" @click="deselectAllFiltered">取消当前</button>
          </div>
        </div>

        <div class="flex-1 overflow-y-auto custom-scrollbar bg-black/20 rounded-lg border border-white/5 p-2">
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
              class="flex items-center gap-3 px-2 py-1.5 rounded hover:bg-white/5 cursor-pointer select-none"
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

      <div class="p-4 border-t border-white/5 bg-[#141418] rounded-b-xl flex justify-between items-center">
        <span class="text-xs text-gray-400">已选中 {{ selectedModels.size }} 个</span>
        <div class="flex gap-3">
          <button class="px-4 py-1.5 text-sm text-gray-400 hover:text-white" @click="close">取消</button>
          <button 
            class="px-4 py-1.5 text-sm bg-brand hover:bg-brand-hover text-white rounded-lg shadow-lg shadow-brand/20 transition-all"
            @click="confirm"
          >
            添加选中项
          </button>
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

