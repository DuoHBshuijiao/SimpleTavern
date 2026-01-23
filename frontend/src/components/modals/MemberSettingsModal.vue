<script setup lang="ts">
/**
 * MemberSettingsModal - 成员设置弹窗
 * 风格：Obsidian Brutalist
 */
import type { GroupMemberSettings, CharacterCard } from '../../types/models'
import ModernAvatar from '../ModernAvatar.vue'
import ModernSelect from '../ModernSelect.vue'

const props = defineProps<{
  show: boolean
  memberId: string | null
  settings: GroupMemberSettings
  character: CharacterCard | null
  modelOptions: Array<{ label: string; value: string; presetId?: string }>
}>()

const emit = defineEmits<{
  'update:show': [value: boolean]
  'update:settings': [settings: GroupMemberSettings]
  'save': []
}>()

function updateField<K extends keyof GroupMemberSettings>(field: K, value: GroupMemberSettings[K]) {
  emit('update:settings', { ...props.settings, [field]: value })
}

function handleModelSelect(opt: { value: string; presetId?: string }) {
  emit('update:settings', { 
    ...props.settings, 
    model: opt.value || null,
    presetId: opt.presetId ?? null 
  })
}

function close() { emit('update:show', false) }
function save() { emit('save') }
</script>

<template>
  <div v-if="show && memberId" class="modal-overlay">
    <div class="modal-backdrop" @click="close"></div>
    <div class="modal-container max-w-xl h-auto">
      <div class="modal-header">
        <h3 class="modal-title">Member Protocol</h3>
        <button class="modal-close" @click="close">✕</button>
      </div>
      
      <div class="modal-content space-y-8">
        <!-- 角色概览 -->
        <div v-if="character" class="flex items-center gap-6 pb-6 border-b border-strong">
          <ModernAvatar 
            :src="character.avatar ? `/api/avatars/${character.avatar}` : null" 
            :name="character.name" 
            :size="64" 
            rounded="rounded-none"
            class="border border-brand"
          />
          <div class="flex flex-col">
            <div class="font-black text-xl uppercase tracking-tighter text-text-primary">{{ character.name }}</div>
            <div class="text-[10px] font-bold text-brand uppercase tracking-widest mt-1">Override Logic Active</div>
          </div>
        </div>

        <div class="grid grid-cols-1 gap-6">
          <div class="form-group">
            <label class="label text-brand">Binding Engine</label>
            <ModernSelect
              :model-value="settings.model"
              :options="modelOptions"
              placement="bottom"
              placeholder="GLOBAL DEFAULT..."
              class="w-full"
              searchable
              allow-create
              @select="handleModelSelect"
            />
          </div>

          <div class="grid grid-cols-2 gap-4">
            <div class="form-group">
              <label class="label">Temperature</label>
              <input 
                type="number"
                :value="settings.temperature ?? ''"
                @input="updateField('temperature', ($event.target as HTMLInputElement).value ? parseFloat(($event.target as HTMLInputElement).value) : null)"
                class="input font-mono"
                placeholder="DEFAULT"
                step="0.1"
              />
            </div>
            <div class="form-group">
              <label class="label">Top P</label>
              <input 
                type="number"
                :value="settings.top_p ?? ''"
                @input="updateField('top_p', ($event.target as HTMLInputElement).value ? parseFloat(($event.target as HTMLInputElement).value) : null)"
                class="input font-mono"
                placeholder="DEFAULT"
                step="0.05"
              />
            </div>
          </div>

          <div class="form-group">
            <label class="label text-brand">Probability Engine: {{ Math.round((settings.probability ?? 1) * 100) }}%</label>
            <div class="flex items-center gap-4">
              <input 
                type="range"
                :value="settings.probability"
                @input="updateField('probability', parseFloat(($event.target as HTMLInputElement).value) || 1)"
                class="flex-1 accent-brand h-1 bg-strong appearance-none cursor-pointer"
                min="0"
                max="1"
                step="0.05"
              />
            </div>
          </div>

          <div class="form-group">
            <label class="label">Injection Protocol</label>
            <div class="flex gap-6">
              <label class="flex items-center gap-3 cursor-pointer group">
                <input 
                  type="checkbox" 
                  class="w-4 h-4 rounded-none border-2 border-strong bg-transparent checked:bg-brand checked:border-brand appearance-none transition-all" 
                  :checked="settings.includePersonality !== false"
                  @change="updateField('includePersonality', ($event.target as HTMLInputElement).checked)"
                />
                <span class="text-[10px] font-black uppercase tracking-widest text-text-secondary group-hover:text-text-primary">Personality</span>
              </label>
              <label class="flex items-center gap-3 cursor-pointer group">
                <input 
                  type="checkbox" 
                  class="w-4 h-4 rounded-none border-2 border-strong bg-transparent checked:bg-brand checked:border-brand appearance-none transition-all" 
                  :checked="settings.includeScenario !== false"
                  @change="updateField('includeScenario', ($event.target as HTMLInputElement).checked)"
                />
                <span class="text-[10px] font-black uppercase tracking-widest text-text-secondary group-hover:text-text-primary">Scenario</span>
              </label>
            </div>
          </div>
        </div>
      </div>

      <div class="modal-footer">
        <button class="btn btn-secondary text-[10px] px-8" @click="close">CANCEL</button>
        <button class="btn btn-primary text-[10px] px-12" @click="save">COMMIT</button>
      </div>
    </div>
  </div>
</template>
