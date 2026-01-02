<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useChatsStore, useSettingsStore } from '../stores'
import type { Chat, ChatOverrides, Settings } from '../types/models'
import ModernSelect from './ModernSelect.vue'

const props = defineProps<{
  show: boolean
  chat: Chat | null
}>()

const emit = defineEmits<{
  (e: 'update:show', v: boolean): void
}>()

const settingsStore = useSettingsStore()
const chatsStore = useChatsStore()

const tab = ref<'global' | 'chat'>('global')
const globalDraft = ref<Settings | null>(null)
const chatDraft = ref<ChatOverrides | null>(null)
const modelOptions = ref<string[]>([])
const modelsLoading = ref(false)
const showApiKey = ref(false)

function close() {
  emit('update:show', false)
}

function clone<T>(v: T): T {
  return JSON.parse(JSON.stringify(v)) as T
}

function ensureOverrides(v?: Partial<ChatOverrides> | null): ChatOverrides {
  return {
    prompt: v?.prompt ?? null,
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
    if (s.streamEnabled === undefined) {
      s.streamEnabled = true
    }
    globalDraft.value = s
    chatDraft.value = props.chat ? clone(props.chat.overrides) : ensureOverrides()
  },
)

async function refreshModels() {
  modelOptions.value = []
  modelsLoading.value = true
  try {
    const r = await fetch('/api/llm/models')
    if (!r.ok) throw new Error(await r.text())
    const models = (await r.json()) as string[]
    modelOptions.value = models
  } catch {
    modelOptions.value = []
  } finally {
    modelsLoading.value = false
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
    <div class="relative w-full max-w-md bg-[#18181c] border-l border-white/10 shadow-2xl flex flex-col h-full transform transition-transform duration-300">
      
      <!-- Header -->
      <div class="flex items-center justify-between px-6 py-4 border-b border-white/5 bg-[#141418]">
        <h2 class="text-lg font-bold text-gray-100">高级设置</h2>
        <button class="text-gray-400 hover:text-white transition-colors" @click="close">
          ✕
        </button>
      </div>

      <!-- Tabs -->
      <div class="flex border-b border-white/5 bg-[#141418]">
        <button
          class="flex-1 py-3 text-sm font-medium transition-colors relative"
          :class="tab === 'global' ? 'text-brand' : 'text-gray-400 hover:text-gray-200'"
          @click="tab = 'global'"
        >
          全局设置
          <div v-if="tab === 'global'" class="absolute bottom-0 left-0 right-0 h-0.5 bg-brand"></div>
        </button>
        <button
          class="flex-1 py-3 text-sm font-medium transition-colors relative"
          :class="tab === 'chat' ? 'text-brand' : 'text-gray-400 hover:text-gray-200'"
          @click="tab = 'chat'"
        >
          当前会话
          <div v-if="tab === 'chat'" class="absolute bottom-0 left-0 right-0 h-0.5 bg-brand"></div>
        </button>
      </div>

      <!-- Content -->
      <div class="flex-1 overflow-y-auto p-6 custom-scrollbar">
        
        <!-- Global Settings -->
        <div v-if="tab === 'global'" class="space-y-6">
          <div v-if="!globalDraft" class="text-center text-gray-500 py-8">加载中...</div>
          <div v-else class="space-y-5">
            <div class="text-xs text-gray-500 bg-white/5 p-3 rounded-lg border border-white/5">
              这些设置将保存到本地配置文件中。API Key 以明文存储。
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
                  {{ globalDraft.streamEnabled ? '已开启：逐字显示回复' : '已关闭：等待完整回复后显示' }}
                </span>
              </button>
            </div>

            <!-- Base URL -->
            <div class="space-y-1.5">
              <label class="block text-sm font-medium text-gray-300">API Base URL</label>
              <input 
                v-model="globalDraft.llm.baseUrl" 
                type="text" 
                placeholder="https://api.openai.com"
                class="w-full bg-black/20 border border-white/10 rounded-lg px-3 py-2 text-sm text-gray-200 focus:border-brand/50 focus:ring-1 focus:ring-brand/50 outline-none transition-colors"
              />
            </div>

            <!-- API Key -->
            <div class="space-y-1.5">
              <label class="block text-sm font-medium text-gray-300">API Key</label>
              <div class="relative">
                <input 
                  v-model="globalDraft.llm.apiKey" 
                  :type="showApiKey ? 'text' : 'password'"
                  class="w-full bg-black/20 border border-white/10 rounded-lg px-3 py-2 pr-10 text-sm text-gray-200 focus:border-brand/50 focus:ring-1 focus:ring-brand/50 outline-none transition-colors"
                />
                <button 
                  class="absolute right-2 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-300 p-1"
                  @click="showApiKey = !showApiKey"
                  title="显示/隐藏 API Key"
                >
                  <span v-if="showApiKey">👁️</span>
                  <span v-else>🔒</span>
                </button>
              </div>
            </div>

            <!-- Model Selection -->
            <div class="space-y-1.5">
              <label class="block text-sm font-medium text-gray-300">默认模型</label>
              <div class="flex gap-2 items-start">
                <ModernSelect
                  v-model="globalDraft.llm.defaultModel"
                  :options="modelOptions"
                  :loading="modelsLoading"
                  searchable
                  allow-create
                  placeholder="选择或输入模型..."
                />
                <button 
                  class="px-3 py-2 bg-white/5 hover:bg-white/10 border border-white/10 rounded-lg text-sm text-gray-300 transition-colors h-[38px] flex items-center justify-center min-w-[60px]"
                  :disabled="modelsLoading"
                  @click="refreshModels"
                >
                  <span v-if="modelsLoading" class="animate-spin text-brand">⟳</span>
                  <span v-else>刷新</span>
                </button>
              </div>
            </div>

            <!-- Global System Prompt -->
            <div class="space-y-1.5">
              <label class="block text-sm font-medium text-gray-300">全局 System Prompt</label>
              <textarea 
                v-model="globalDraft.prompts.globalSystem" 
                rows="4"
                class="w-full bg-black/20 border border-white/10 rounded-lg px-3 py-2 text-sm text-gray-200 focus:border-brand/50 focus:ring-1 focus:ring-brand/50 outline-none transition-colors resize-none"
              ></textarea>
            </div>

            <div class="h-px bg-white/5 my-4"></div>

            <!-- Parameters -->
            <div class="grid grid-cols-2 gap-4">
              <div class="space-y-1.5">
                <label class="block text-sm font-medium text-gray-300">Temperature</label>
                <input 
                  v-model.number="globalDraft.generationDefaults.temperature" 
                  type="number" 
                  step="0.1" min="0" max="2"
                  placeholder="默认"
                  class="w-full bg-black/20 border border-white/10 rounded-lg px-3 py-2 text-sm text-gray-200 focus:border-brand/50 outline-none"
                />
              </div>
              <div class="space-y-1.5">
                <label class="block text-sm font-medium text-gray-300">Top P</label>
                <input 
                  v-model.number="globalDraft.generationDefaults.top_p" 
                  type="number" 
                  step="0.1" min="0" max="1"
                  placeholder="默认"
                  class="w-full bg-black/20 border border-white/10 rounded-lg px-3 py-2 text-sm text-gray-200 focus:border-brand/50 outline-none"
                />
              </div>
              <div class="space-y-1.5">
                <label class="block text-sm font-medium text-gray-300">Max Tokens</label>
                <input 
                  v-model.number="globalDraft.generationDefaults.max_tokens" 
                  type="number" 
                  step="128" min="1"
                  placeholder="默认"
                  class="w-full bg-black/20 border border-white/10 rounded-lg px-3 py-2 text-sm text-gray-200 focus:border-brand/50 outline-none"
                />
              </div>
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

        <!-- Chat Specific Settings -->
        <div v-else class="space-y-6">
          <div v-if="!chat" class="text-center text-gray-500 py-8">请先选择一个会话</div>
          <div v-else-if="chatDraft && globalDraft" class="space-y-5">
             <div class="text-xs text-gray-500 bg-white/5 p-3 rounded-lg border border-white/5">
              这些设置仅应用于当前会话，并会覆盖全局设置。
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
                :options="modelOptions"
                :loading="modelsLoading"
                searchable
                allow-create
                placeholder="留空使用全局默认"
              />
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
