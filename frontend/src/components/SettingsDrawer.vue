<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useChatsStore, useSettingsStore } from '../stores'
import type { Chat, ChatOverrides, Settings, ApiPreset } from '../types/models'
import ModernSelect from './ModernSelect.vue'
import { apiPost } from '../api/http'

const props = defineProps<{
  show: boolean
  chat: Chat | null
}>()

const emit = defineEmits<{
  (e: 'update:show', v: boolean): void
}>()

const settingsStore = useSettingsStore()
const chatsStore = useChatsStore()

const tab = ref<'global' | 'presets' | 'chat'>('global')
const globalDraft = ref<Settings | null>(null)
const chatDraft = ref<ChatOverrides | null>(null)

const modelsLoading = ref(false)
const showApiKey = ref(false)
const editingPresetId = ref<string | null>(null)
const editingPresetShowApiKey = ref(false)
const presetModelsLoading = ref(false)

function close() {
  emit('update:show', false)
}

function clone<T>(v: T): T {
  return JSON.parse(JSON.stringify(v)) as T
}

function ensureOverrides(v?: Partial<ChatOverrides> | null): ChatOverrides {
  return {
    prompt: v?.prompt ?? null,
    presetId: v?.presetId ?? null,
    params: {
      model: v?.params?.model ?? null,
      temperature: v?.params?.temperature ?? null,
      top_p: v?.params?.top_p ?? null,
      max_tokens: v?.params?.max_tokens ?? null,
    },
  }
}

watch(
  () => props.show,
  async (open) => {
    if (!open) return
    if (!settingsStore.settings) await settingsStore.load()
    const s = clone(settingsStore.settings!)
    if (s.streamEnabled === undefined) s.streamEnabled = true
    if (!s.apiPresets) s.apiPresets = []
    
    globalDraft.value = s
    chatDraft.value = props.chat ? clone(props.chat.overrides) : ensureOverrides()
    
    // 如果有预设，默认选中第一个编辑
    if (s.apiPresets.length > 0 && !editingPresetId.value) {
        editingPresetId.value = s.apiPresets[0].id
    }
  },
)

// 全局模型列表 (旧版兼容)
const globalModelOptions = computed(() => {
    return globalDraft.value?.llm.modelCandidates || []
})

async function refreshGlobalModels() {
  modelsLoading.value = true
  try {
    const r = await fetch('/api/llm/models')
    if (!r.ok) throw new Error(await r.text())
    const models = (await r.json()) as string[]
    if (globalDraft.value) {
        // 虽然接口返回的是当前配置的模型，但这里我们只更新列表展示，不强制覆盖
        // 实际上 /api/llm/models 逻辑比较简单，我们这里主要用于测试连接
    }
  } catch {
      // ignore
  } finally {
    modelsLoading.value = false
  }
}

// 预设相关
const editingPreset = computed(() => {
  if (!globalDraft.value) return null
  return globalDraft.value.apiPresets.find(p => p.id === editingPresetId.value) || null
})

function createPreset() {
  if (!globalDraft.value) return
  const newPreset: ApiPreset = {
    id: crypto.randomUUID().replace(/-/g, ''),
    name: '新 API 预设',
    baseUrl: 'https://api.openai.com',
    apiKey: '',
    models: []
  }
  globalDraft.value.apiPresets.push(newPreset)
  editingPresetId.value = newPreset.id
}

function deletePreset(id: string) {
  if (!globalDraft.value) return
  if (!confirm('确定删除此预设？')) return
  globalDraft.value.apiPresets = globalDraft.value.apiPresets.filter(p => p.id !== id)
  if (editingPresetId.value === id) {
    editingPresetId.value = globalDraft.value.apiPresets[0]?.id || null
  }
}

async function refreshPresetModels(preset: ApiPreset) {
  presetModelsLoading.value = true
  try {
    const models = await apiPost<string[]>('/api/llm/test-models', {
      baseUrl: preset.baseUrl,
      apiKey: preset.apiKey
    })
    preset.models = models
  } catch (e) {
    alert('获取模型失败: ' + String(e))
  } finally {
    presetModelsLoading.value = false
  }
}

// 聚合模型列表 (用于聊天设置)
const chatModelOptions = computed(() => {
  const options: any[] = []
  if (!globalDraft.value) return []

  // Global Models (Legacy)
  // 如果有配置全局模型，也加进去作为默认组
  // 这里简化处理，如果配置了 API Presets，主要展示 Presets 的模型
  
  for (const preset of globalDraft.value.apiPresets) {
      if (preset.models && preset.models.length > 0) {
          options.push({
              label: preset.name,
              options: preset.models.map(m => ({ label: m, value: m, presetId: preset.id }))
          })
      }
  }
  
  // 如果没有 presets 或者想提供全局 fallback
  // 可以添加一个 "Global Default" 组
  
  return options
})

function handleChatModelSelect(option: any) {
  if (chatDraft.value) {
     chatDraft.value.params.model = option.value
     if (option.presetId) {
         chatDraft.value.presetId = option.presetId
     }
  }
}

async function saveGlobal() {
  if (!globalDraft.value) return
  await settingsStore.save(globalDraft.value)
  close()
}

async function saveChatOverrides() {
  if (!props.chat || !chatDraft.value) return
  await chatsStore.updateOverrides(props.chat.id, chatDraft.value)
  close()
}
</script>

<template>
  <div v-if="show" class="fixed inset-0 z-50 flex justify-end">
    <!-- Backdrop -->
    <div class="absolute inset-0 bg-black/50 backdrop-blur-sm transition-opacity" @click="close"></div>

    <!-- Drawer Panel -->
    <div class="relative w-full max-w-xl bg-[#18181c] border-l border-white/10 shadow-2xl flex flex-col h-full transform transition-transform duration-300">
      
      <!-- Header -->
      <div class="flex items-center justify-between px-6 py-4 border-b border-white/5 bg-[#141418]">
        <h2 class="text-lg font-bold text-gray-100">设置</h2>
        <button class="text-gray-400 hover:text-white transition-colors" @click="close">
          ✕
        </button>
      </div>

      <!-- Tabs -->
      <div class="flex border-b border-white/5 bg-[#141418]">
        <button
          v-for="t in ['global', 'presets', 'chat']"
          :key="t"
          class="flex-1 py-3 text-sm font-medium transition-colors relative"
          :class="tab === t ? 'text-brand' : 'text-gray-400 hover:text-gray-200'"
          @click="tab = t as any"
        >
          {{ t === 'global' ? '全局设置' : t === 'presets' ? 'API 预设' : '当前会话' }}
          <div v-if="tab === t" class="absolute bottom-0 left-0 right-0 h-0.5 bg-brand"></div>
        </button>
      </div>

      <!-- Content -->
      <div class="flex-1 overflow-y-auto p-6 custom-scrollbar bg-[#18181c]">
        
        <!-- Global Settings -->
        <div v-if="tab === 'global'" class="space-y-6">
          <div v-if="!globalDraft" class="text-center text-gray-500 py-8">加载中...</div>
          <div v-else class="space-y-5">
            <div class="text-xs text-gray-500 bg-white/5 p-3 rounded-lg border border-white/5">
              这里配置全局默认的 API 参数。如果配置了 "API 预设"，建议优先使用预设功能以便管理不同服务商。
            </div>

            <!-- Stream Toggle -->
            <div class="space-y-2">
              <label class="block text-sm font-medium text-gray-300">流式传输 (Streaming)</label>
              <button 
                class="flex items-center gap-3 group cursor-pointer w-full text-left"
                @click="globalDraft.streamEnabled = !globalDraft.streamEnabled"
              >
                <div 
                  class="w-10 h-5 rounded-full relative transition-colors duration-200"
                  :class="globalDraft.streamEnabled ? 'bg-brand' : 'bg-gray-700'"
                >
                  <div 
                    class="absolute top-1 w-3 h-3 rounded-full bg-white transition-transform duration-200"
                    :class="globalDraft.streamEnabled ? 'left-6' : 'left-1'"
                  ></div>
                </div>
                <span class="text-xs text-gray-400">
                  {{ globalDraft.streamEnabled ? '已开启' : '已关闭' }}
                </span>
              </button>
            </div>

            <!-- Base URL -->
            <div class="space-y-1.5">
              <label class="block text-sm font-medium text-gray-300">默认 API Base URL</label>
              <input 
                v-model="globalDraft.llm.baseUrl" 
                type="text" 
                placeholder="https://api.openai.com"
                class="w-full bg-black/20 border border-white/10 rounded-lg px-3 py-2 text-sm text-gray-200 focus:border-brand/50 focus:ring-1 focus:ring-brand/50 outline-none transition-colors"
              />
            </div>

            <!-- API Key -->
            <div class="space-y-1.5">
              <label class="block text-sm font-medium text-gray-300">默认 API Key</label>
              <div class="relative">
                <input 
                  v-model="globalDraft.llm.apiKey" 
                  :type="showApiKey ? 'text' : 'password'"
                  class="w-full bg-black/20 border border-white/10 rounded-lg px-3 py-2 pr-10 text-sm text-gray-200 focus:border-brand/50 focus:ring-1 focus:ring-brand/50 outline-none transition-colors"
                />
                <button 
                  class="absolute right-2 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-300 p-1"
                  @click="showApiKey = !showApiKey"
                >
                  {{ showApiKey ? '👁️' : '🔒' }}
                </button>
              </div>
            </div>

            <div class="space-y-1.5">
               <label class="block text-sm font-medium text-gray-300">默认模型名称</label>
               <input 
                  v-model="globalDraft.llm.defaultModel" 
                  type="text" 
                  class="w-full bg-black/20 border border-white/10 rounded-lg px-3 py-2 text-sm text-gray-200 focus:border-brand/50 outline-none"
                  placeholder="例如: gpt-3.5-turbo"
               />
            </div>

            <div class="h-px bg-white/5 my-4"></div>

            <!-- Global System Prompt -->
            <div class="space-y-1.5">
              <label class="block text-sm font-medium text-gray-300">全局 System Prompt</label>
              <textarea 
                v-model="globalDraft.prompts.globalSystem" 
                rows="4"
                class="w-full bg-black/20 border border-white/10 rounded-lg px-3 py-2 text-sm text-gray-200 focus:border-brand/50 focus:ring-1 focus:ring-brand/50 outline-none transition-colors resize-none"
              ></textarea>
            </div>

             <div class="pt-4 flex justify-end">
              <button 
                class="px-6 py-2 bg-brand hover:bg-brand-hover text-white rounded-lg font-medium shadow-lg shadow-brand/20 transition-all"
                @click="saveGlobal"
              >
                保存全局设置
              </button>
            </div>
          </div>
        </div>

        <!-- Presets Management -->
        <div v-else-if="tab === 'presets'" class="space-y-6 h-full flex flex-col">
            <div v-if="!globalDraft" class="text-center text-gray-500 py-8">加载中...</div>
            <div v-else class="flex flex-1 min-h-0 gap-4">
                <!-- Preset List -->
                <div class="w-1/3 flex flex-col border-r border-white/5 pr-4">
                    <div class="flex justify-between items-center mb-3">
                        <span class="text-sm font-bold text-gray-400">预设列表</span>
                        <button class="text-xs bg-brand/20 text-brand px-2 py-1 rounded hover:bg-brand/30 transition-colors" @click="createPreset">+ 新建</button>
                    </div>
                    <div class="flex-1 overflow-y-auto space-y-1 custom-scrollbar">
                        <div 
                            v-for="p in globalDraft.apiPresets" 
                            :key="p.id"
                            class="px-3 py-2 rounded-lg cursor-pointer text-sm transition-colors flex justify-between items-center group"
                            :class="editingPresetId === p.id ? 'bg-brand/10 text-brand' : 'text-gray-400 hover:bg-white/5'"
                            @click="editingPresetId = p.id"
                        >
                            <span class="truncate">{{ p.name }}</span>
                            <button class="opacity-0 group-hover:opacity-100 text-gray-500 hover:text-red-400 px-1" @click.stop="deletePreset(p.id)">×</button>
                        </div>
                         <div v-if="globalDraft.apiPresets.length === 0" class="text-xs text-gray-600 text-center py-4">无预设</div>
                    </div>
                </div>

                <!-- Preset Editor -->
                <div class="flex-1 flex flex-col min-w-0" v-if="editingPreset">
                     <div class="space-y-4 overflow-y-auto custom-scrollbar pr-2 pb-4">
                        <div class="space-y-1.5">
                            <label class="block text-xs font-medium text-gray-400">预设名称</label>
                            <input 
                                v-model="editingPreset.name" 
                                type="text" 
                                class="w-full bg-black/20 border border-white/10 rounded-lg px-3 py-1.5 text-sm text-gray-200 focus:border-brand/50 outline-none"
                            />
                        </div>

                         <div class="space-y-1.5">
                            <label class="block text-xs font-medium text-gray-400">Base URL</label>
                            <input 
                                v-model="editingPreset.baseUrl" 
                                type="text" 
                                placeholder="https://api.openai.com"
                                class="w-full bg-black/20 border border-white/10 rounded-lg px-3 py-1.5 text-sm text-gray-200 focus:border-brand/50 outline-none"
                            />
                        </div>

                        <div class="space-y-1.5">
                            <label class="block text-xs font-medium text-gray-400">API Key</label>
                             <div class="relative">
                                <input 
                                    v-model="editingPreset.apiKey" 
                                    :type="editingPresetShowApiKey ? 'text' : 'password'"
                                    class="w-full bg-black/20 border border-white/10 rounded-lg px-3 py-1.5 pr-8 text-sm text-gray-200 focus:border-brand/50 outline-none"
                                />
                                <button 
                                    class="absolute right-2 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-300"
                                    @click="editingPresetShowApiKey = !editingPresetShowApiKey"
                                >
                                    {{ editingPresetShowApiKey ? '👁️' : '🔒' }}
                                </button>
                             </div>
                        </div>

                        <div class="space-y-2">
                             <div class="flex justify-between items-center">
                                 <label class="block text-xs font-medium text-gray-400">模型列表</label>
                                 <button 
                                    class="text-xs text-brand hover:text-brand-hover flex items-center gap-1" 
                                    :disabled="presetModelsLoading"
                                    @click="refreshPresetModels(editingPreset!)"
                                 >
                                    <span v-if="presetModelsLoading" class="animate-spin">⟳</span>
                                    <span>从 API 获取</span>
                                 </button>
                             </div>
                             <div class="bg-black/20 border border-white/10 rounded-lg p-2 min-h-[100px] max-h-[200px] overflow-y-auto custom-scrollbar">
                                 <div class="flex flex-wrap gap-2">
                                     <div v-for="(m, idx) in editingPreset.models" :key="m" class="bg-white/5 rounded px-2 py-1 text-xs text-gray-300 flex items-center gap-1">
                                         {{ m }}
                                         <button class="hover:text-red-400" @click="editingPreset!.models.splice(idx, 1)">×</button>
                                     </div>
                                      <div v-if="!editingPreset.models.length" class="text-xs text-gray-600 w-full text-center py-4">
                                          点击上方“从 API 获取”或手动添加
                                      </div>
                                 </div>
                             </div>
                             <!-- 手动添加模型 -->
                              <div class="flex gap-2">
                                 <input 
                                    type="text" 
                                    placeholder="手动输入模型名..."
                                    class="flex-1 bg-black/20 border border-white/10 rounded px-2 py-1 text-xs text-gray-200 outline-none focus:border-brand/50"
                                    @keydown.enter="(e) => {
                                        const val = (e.target as HTMLInputElement).value.trim();
                                        if(val && !editingPreset!.models.includes(val)) {
                                            editingPreset!.models.push(val);
                                            (e.target as HTMLInputElement).value = '';
                                        }
                                    }"
                                 />
                              </div>
                        </div>
                     </div>
                </div>
                <div v-else class="flex-1 flex items-center justify-center text-gray-600 text-sm">
                    选择或创建一个预设
                </div>
            </div>
            
             <div class="pt-2 flex justify-end">
              <button 
                class="px-6 py-2 bg-brand hover:bg-brand-hover text-white rounded-lg font-medium shadow-lg shadow-brand/20 transition-all"
                @click="saveGlobal"
              >
                保存所有配置
              </button>
            </div>
        </div>

        <!-- Chat Specific Settings -->
        <div v-else class="space-y-6">
          <div v-if="!chat" class="text-center text-gray-500 py-8">请先选择一个会话</div>
          <div v-else-if="chatDraft && globalDraft" class="space-y-5">
             <div class="text-xs text-gray-500 bg-white/5 p-3 rounded-lg border border-white/5">
              这些设置仅应用于当前会话，并会覆盖全局设置。模型选择将自动关联对应的 API 预设。
            </div>

            <div class="space-y-1.5">
              <label class="block text-sm font-medium text-gray-300">会话 System Prompt (Override)</label>
              <textarea 
                v-model="chatDraft.prompt" 
                rows="4"
                placeholder="留空则使用角色默认Prompt"
                class="w-full bg-black/20 border border-white/10 rounded-lg px-3 py-2 text-sm text-gray-200 focus:border-brand/50 focus:ring-1 focus:ring-brand/50 outline-none transition-colors resize-none"
              ></textarea>
            </div>

             <div class="space-y-1.5">
              <label class="block text-sm font-medium text-gray-300">模型覆盖</label>
              <ModernSelect
                v-model="chatDraft.params.model"
                :options="chatModelOptions"
                searchable
                allow-create
                placeholder="选择模型 (自动关联预设)..."
                @select="handleChatModelSelect"
              />
              <div v-if="chatDraft.presetId" class="text-xs text-brand mt-1 flex items-center gap-1">
                  <span>🔗 已关联 API 预设:</span>
                  <span class="font-bold">{{ globalDraft.apiPresets.find(p => p.id === chatDraft.presetId)?.name || 'Unknown' }}</span>
              </div>
            </div>

             <div class="grid grid-cols-2 gap-4">
              <div class="space-y-1.5">
                <label class="block text-sm font-medium text-gray-300">Temperature</label>
                <input 
                  v-model.number="chatDraft.params.temperature" 
                  type="number" 
                  step="0.1" min="0" max="2"
                  placeholder="使用全局"
                  class="w-full bg-black/20 border border-white/10 rounded-lg px-3 py-2 text-sm text-gray-200 focus:border-brand/50 outline-none"
                />
              </div>
              <div class="space-y-1.5">
                <label class="block text-sm font-medium text-gray-300">Top P</label>
                <input 
                  v-model.number="chatDraft.params.top_p" 
                  type="number" 
                  step="0.1" min="0" max="1"
                  placeholder="使用全局"
                  class="w-full bg-black/20 border border-white/10 rounded-lg px-3 py-2 text-sm text-gray-200 focus:border-brand/50 outline-none"
                />
              </div>
              <div class="space-y-1.5">
                <label class="block text-sm font-medium text-gray-300">Max Tokens</label>
                <input 
                  v-model.number="chatDraft.params.max_tokens" 
                  type="number" 
                  step="128" min="1"
                  placeholder="使用全局"
                  class="w-full bg-black/20 border border-white/10 rounded-lg px-3 py-2 text-sm text-gray-200 focus:border-brand/50 outline-none"
                />
              </div>
            </div>

             <div class="pt-4 flex justify-end gap-3">
              <button 
                class="px-4 py-2 text-gray-400 hover:text-white transition-colors"
                @click="close"
              >
                取消
              </button>
              <button 
                class="px-6 py-2 bg-brand hover:bg-brand-hover text-white rounded-lg font-medium shadow-lg shadow-brand/20 transition-all"
                @click="saveChatOverrides(); saveGlobal()"
              >
                保存设置
              </button>
            </div>
          </div>
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
