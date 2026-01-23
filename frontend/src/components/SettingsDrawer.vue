<script setup lang="ts">
/**
 * SettingsDrawer - 设置面板
 * 风格：Obsidian Brutalist (High Density)
 */
import { computed, ref, watch } from 'vue'
import { useCharactersStore, useChatsStore, useSettingsStore } from '../stores'
import type { Chat, ChatOverrides, Settings, ApiPreset } from '../types/models'
import ModernSelect from './ModernSelect.vue'
import { apiPost } from '../api/http'

const props = defineProps<{
  show: boolean
  chat: Chat | null
  initialTab?: 'global' | 'presets' | 'chat'
}>()

const emit = defineEmits<{
  (e: 'update:show', v: boolean): void
  (e: 'open-member-settings', memberId: string): void
}>()

const settingsStore = useSettingsStore()
const chatsStore = useChatsStore()
const charactersStore = useCharactersStore()

const tab = ref<'global' | 'presets' | 'chat'>('global')
watch(() => props.initialTab, (newTab) => { if (newTab) tab.value = newTab }, { immediate: true })

const globalDraft = ref<Settings | null>(null)
const chatDraft = ref<ChatOverrides | null>(null)
const showApiKey = ref(false)
const editingPresetId = ref<string | null>(null)
const editingPresetShowApiKey = ref(false)
const presetModelsLoading = ref(false)
const importInputRef = ref<HTMLInputElement | null>(null)

const showModelSelector = ref(false)
const candidateModels = ref<string[]>([])
const selectedCandidateModels = ref<Set<string>>(new Set())
const modelSelectorQuery = ref('')

function close() { emit('update:show', false) }
function clone<T>(v: T): T { return JSON.parse(JSON.stringify(v)) }

function ensureOverrides(v?: Partial<ChatOverrides> | null): ChatOverrides {
  return {
    prompt: v?.prompt ?? null,
    longTermMemory: v?.longTermMemory ?? null,
    presetId: v?.presetId ?? null,
    params: {
      model: v?.params?.model ?? null,
      temperature: v?.params?.temperature ?? null,
      top_p: v?.params?.top_p ?? null,
      max_tokens: v?.params?.max_tokens ?? null,
    },
  }
}

watch(() => props.show, async (open) => {
  if (!open) return
  if (!settingsStore.settings) await settingsStore.load()
  const s = clone(settingsStore.settings!)
  globalDraft.value = s
  chatDraft.value = props.chat ? clone(props.chat.overrides) : ensureOverrides()
  if (s.apiPresets.length > 0 && !editingPresetId.value) editingPresetId.value = s.apiPresets[0].id
})

const editingPreset = computed(() => globalDraft.value?.apiPresets.find(p => p.id === editingPresetId.value) || null)

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

async function downloadSettingsBackup(scope: string) {
  const r = await fetch(`/api/settings/backup?scope=${scope}`)
  const blob = await r.blob()
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `backup-${scope}-${Date.now()}.zip`
  link.click()
}

async function handleImportChange(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (!file) return
  const fd = new FormData()
  fd.append('file', file)
  await fetch('/api/import', { method: 'POST', body: fd })
  location.reload()
}
</script>

<template>
  <Transition name="drawer">
    <div v-if="show" class="fixed inset-0 z-50 flex justify-end">
      <div class="absolute inset-0 bg-black/80 backdrop-blur-md" @click="close"></div>

      <div class="relative w-[600px] max-w-full bg-dark-bg border-l border-strong shadow-2xl flex flex-col h-full">
        <!-- Header -->
        <div class="flex items-center justify-between px-8 py-6 border-b border-strong bg-dark-surface">
          <h2 class="text-xl font-black uppercase tracking-tighter text-text-primary">System Config</h2>
          <button class="text-text-muted hover:text-error transition-colors" @click="close">✕</button>
        </div>

        <!-- Tabs -->
        <div class="flex border-b border-strong bg-dark-surface">
          <button
            v-for="t in ['global', 'presets', 'chat']"
            :key="t"
            class="flex-1 py-4 text-[10px] font-black uppercase tracking-[0.3em] transition-all relative"
            :class="tab === t ? 'text-brand bg-brand/5' : 'text-text-muted hover:text-text-secondary'"
            @click="tab = t as any"
          >
            {{ t }}
            <div v-if="tab === t" class="absolute bottom-0 left-0 right-0 h-1 bg-brand"></div>
          </button>
        </div>

        <!-- Content -->
        <div class="flex-1 overflow-y-auto p-8 custom-scrollbar space-y-12">
          
          <!-- GLOBAL TAB -->
          <div v-if="tab === 'global' && globalDraft" class="space-y-10">
            <div class="space-y-6">
              <label class="label text-brand">Core Engine Settings</label>
              
              <div class="grid grid-cols-1 gap-6 bg-dark-surface border border-strong p-6">
                <div class="flex items-center justify-between">
                  <span class="text-[10px] font-black uppercase tracking-widest">Streaming Engine</span>
                  <button @click="globalDraft.streamEnabled = !globalDraft.streamEnabled" class="w-10 h-5 border border-strong relative">
                    <div class="absolute top-0.5 left-0.5 w-3.5 h-3.5 bg-white transition-transform" :class="globalDraft.streamEnabled ? 'translate-x-5 bg-brand' : 'translate-x-0'"></div>
                  </button>
                </div>
                <div class="flex items-center justify-between">
                  <span class="text-[10px] font-black uppercase tracking-widest">Pure AI Protocol</span>
                  <button @click="globalDraft.pureAiMode = !globalDraft.pureAiMode" class="w-10 h-5 border border-strong relative">
                    <div class="absolute top-0.5 left-0.5 w-3.5 h-3.5 bg-white transition-transform" :class="globalDraft.pureAiMode ? 'translate-x-5 bg-brand' : 'translate-x-0'"></div>
                  </button>
                </div>
              </div>

              <div class="space-y-4">
                <div class="form-group">
                  <label class="label">Default API Base</label>
                  <input v-model="globalDraft.llm.baseUrl" class="input font-mono text-xs" />
                </div>
                <div class="form-group">
                  <label class="label">Default API Key</label>
                  <div class="relative">
                    <input v-model="globalDraft.llm.apiKey" :type="showApiKey ? 'text' : 'password'" class="input font-mono text-xs pr-10" />
                    <button class="absolute right-3 top-1/2 -translate-y-1/2 text-text-muted hover:text-text-primary" @click="showApiKey = !showApiKey">{{ showApiKey ? 'HIDE' : 'SHOW' }}</button>
                  </div>
                </div>
              </div>
            </div>

            <div class="space-y-6">
              <label class="label text-brand">Generation Parameters</label>
              <div class="grid grid-cols-3 gap-4">
                <div class="form-group">
                  <label class="label text-[8px]">Temperature</label>
                  <input v-model.number="globalDraft.generationDefaults.temperature" type="number" step="0.1" class="input font-mono text-xs" />
                </div>
                <div class="form-group">
                  <label class="label text-[8px]">Top P</label>
                  <input v-model.number="globalDraft.generationDefaults.top_p" type="number" step="0.05" class="input font-mono text-xs" />
                </div>
                <div class="form-group">
                  <label class="label text-[8px]">Max Tokens</label>
                  <input v-model.number="globalDraft.generationDefaults.max_tokens" type="number" class="input font-mono text-xs" />
                </div>
              </div>
            </div>

            <div class="space-y-6">
              <label class="label text-brand">Data Management</label>
              <div class="grid grid-cols-2 gap-2">
                <button class="btn btn-secondary text-[8px] py-3" @click="downloadSettingsBackup('basic')">BACKUP CONFIG</button>
                <button class="btn btn-secondary text-[8px] py-3" @click="downloadSettingsBackup('with_characters')">+ CHARACTERS</button>
                <button class="btn btn-secondary text-[8px] py-3" @click="downloadSettingsBackup('with_chats')">+ HISTORY</button>
                <button class="btn btn-accent text-[8px] py-3" @click="importInputRef?.click()">IMPORT DATA</button>
                <input ref="importInputRef" type="file" class="hidden" @change="handleImportChange" />
              </div>
            </div>
          </div>

          <!-- PRESETS TAB -->
          <div v-else-if="tab === 'presets' && globalDraft" class="space-y-8 flex flex-col h-full overflow-hidden">
             <div class="flex gap-6 h-full overflow-hidden">
                <div class="w-1/3 border-r border-strong pr-6 space-y-4">
                   <button class="btn btn-primary w-full text-[9px]" @click="globalDraft.apiPresets.push({id: Date.now().toString(), name: 'NEW PRESET', baseUrl:'', apiKey:'', models:[]})">ADD PRESET</button>
                   <div class="space-y-1 overflow-y-auto max-h-[500px] custom-scrollbar">
                      <div v-for="p in globalDraft.apiPresets" :key="p.id" 
                        class="p-3 border border-strong text-[10px] font-bold uppercase cursor-pointer hover:border-brand transition-all"
                        :class="editingPresetId === p.id ? 'bg-brand text-text-inverse border-brand' : 'text-text-muted'"
                        @click="editingPresetId = p.id"
                      >
                        {{ p.name }}
                      </div>
                   </div>
                </div>
                <div v-if="editingPreset" class="flex-1 space-y-6 overflow-y-auto pr-2 custom-scrollbar">
                   <div class="form-group">
                      <label class="label text-brand">Preset Name</label>
                      <input v-model="editingPreset.name" class="input uppercase font-black" />
                   </div>
                   <div class="form-group">
                      <label class="label">Base URL</label>
                      <input v-model="editingPreset.baseUrl" class="input font-mono text-xs" />
                   </div>
                   <div class="form-group">
                      <label class="label">API Key</label>
                      <input v-model="editingPreset.apiKey" type="password" class="input font-mono text-xs" />
                   </div>
                   <div class="space-y-4">
                      <div class="flex justify-between items-center">
                        <label class="label text-brand">Models</label>
                        <button class="text-[8px] font-black text-brand underline">FETCH FROM API</button>
                      </div>
                      <div class="flex flex-wrap gap-2">
                        <div v-for="(m, i) in editingPreset.models" :key="m" class="px-2 py-1 bg-dark-surface border border-strong text-[9px] font-mono flex items-center gap-2">
                          {{ m }}
                          <button class="text-error" @click="editingPreset.models.splice(i, 1)">✕</button>
                        </div>
                      </div>
                   </div>
                </div>
             </div>
          </div>

          <!-- CHAT TAB -->
          <div v-else-if="tab === 'chat' && chatDraft" class="space-y-10">
             <div class="space-y-6">
                <label class="label text-brand">Session Override</label>
                <div class="form-group">
                  <label class="label">System Prompt Override</label>
                  <textarea v-model="chatDraft.prompt" rows="6" class="input textarea font-mono text-xs" placeholder="LEAVE BLANK FOR DEFAULT..."></textarea>
                </div>
                <div class="form-group">
                  <label class="label">Long Term Memory</label>
                  <textarea v-model="chatDraft.longTermMemory" rows="4" class="input textarea font-mono text-xs" placeholder="INJECTED PERSISTENT CONTEXT..."></textarea>
                </div>
             </div>
             <div class="space-y-6">
                <label class="label text-brand">Session Engine</label>
                <ModernSelect v-model="chatDraft.params.model" :options="[]" placeholder="SELECT ENGINE..." />
                <div class="grid grid-cols-3 gap-4">
                  <input v-model.number="chatDraft.params.temperature" type="number" placeholder="TEMP" class="input font-mono text-xs" />
                  <input v-model.number="chatDraft.params.top_p" type="number" placeholder="TOP P" class="input font-mono text-xs" />
                  <input v-model.number="chatDraft.params.max_tokens" type="number" placeholder="MAX T" class="input font-mono text-xs" />
                </div>
             </div>
          </div>

        </div>

        <!-- Footer -->
        <div class="p-8 border-t border-strong bg-dark-surface flex justify-end gap-4">
          <button class="btn btn-secondary px-8" @click="close">CANCEL</button>
          <button class="btn btn-primary px-12" @click="tab === 'chat' ? saveChatOverrides() : saveGlobal()">SAVE ALL</button>
        </div>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.drawer-enter-active, .drawer-leave-active { transition: opacity 0.2s ease; }
.drawer-enter-from, .drawer-leave-to { opacity: 0; }
.drawer-enter-active .relative { transition: transform 0.2s cubic-bezier(0.16, 1, 0.3, 1); }
.drawer-enter-from .relative { transform: translateX(100%); }
.custom-scrollbar::-webkit-scrollbar { width: 1px; }
</style>
