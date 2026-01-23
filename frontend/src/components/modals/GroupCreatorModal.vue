<script setup lang="ts">
/**
 * GroupCreatorModal - 群聊创建弹窗
 * 风格：Obsidian Brutalist
 */
import { ref, computed, watch } from 'vue'
import type { CharacterCard } from '../../types/models'
import ModernAvatar from '../ModernAvatar.vue'
import ModernSelect from '../ModernSelect.vue'

const props = defineProps<{
  show: boolean
  characters: CharacterCard[]
}>()

const emit = defineEmits<{
  'update:show': [value: boolean]
  'create': [data: {
    title: string
    memberIds: string[]
    pureAiMode: boolean
    firstMessageCharacterId: string | null
    memberInclusions: Record<string, { includePersonality: boolean; includeScenario: boolean }>
  }]
}>()

const selectedMemberIds = ref<string[]>([])
const groupTitle = ref('')
const groupPureAiMode = ref(false)
const groupFirstMessageEnabled = ref(true)
const groupFirstMessageCharacterId = ref<string | null>(null)
const groupMemberInclusions = ref<Record<string, { includePersonality: boolean; includeScenario: boolean }>>({})

watch(() => props.show, (newVal) => {
  if (newVal) {
    selectedMemberIds.value = []
    groupTitle.value = ''
    groupPureAiMode.value = false
    groupFirstMessageEnabled.value = true
    groupFirstMessageCharacterId.value = null
    groupMemberInclusions.value = {}
  }
})

const groupFirstMessageOptions = computed(() => {
  const opts = selectedMemberIds.value.map(id => {
    const char = props.characters.find(c => c.id === id)
    return { label: char?.name || id, value: id }
  })
  return [{ label: 'NONE', value: '' }, ...opts]
})

function toggleMemberSelection(characterId: string) {
  const idx = selectedMemberIds.value.indexOf(characterId)
  if (idx >= 0) {
    selectedMemberIds.value.splice(idx, 1)
    delete groupMemberInclusions.value[characterId]
    if (groupFirstMessageCharacterId.value === characterId) {
      groupFirstMessageCharacterId.value = selectedMemberIds.value[0] ?? null
    }
  } else {
    selectedMemberIds.value.push(characterId)
    if (!groupMemberInclusions.value[characterId]) {
      groupMemberInclusions.value[characterId] = { includePersonality: true, includeScenario: true }
    }
    if (!groupFirstMessageCharacterId.value) {
      groupFirstMessageCharacterId.value = characterId
    }
  }
}

function handleCreate() {
  if (selectedMemberIds.value.length < 2) return
  emit('create', {
    title: groupTitle.value || 'NEW GROUP',
    memberIds: selectedMemberIds.value,
    pureAiMode: groupPureAiMode.value,
    firstMessageCharacterId: groupFirstMessageEnabled.value ? groupFirstMessageCharacterId.value : null,
    memberInclusions: groupMemberInclusions.value,
  })
  emit('update:show', false)
}
</script>

<template>
  <div v-if="show" class="modal-overlay">
    <div class="modal-backdrop" @click="emit('update:show', false)"></div>
    <div class="modal-container max-w-4xl h-[90vh]">
      <div class="modal-header">
        <h3 class="modal-title">Initialize Group Protocol</h3>
        <button class="modal-close" @click="emit('update:show', false)">✕</button>
      </div>
      
      <div class="modal-content flex flex-col h-full overflow-hidden p-0">
        <div class="flex-1 overflow-y-auto p-8 custom-scrollbar space-y-12">
          <!-- 基本信息 -->
          <div class="grid grid-cols-1 md:grid-cols-2 gap-12">
            <div class="space-y-8">
              <div class="form-group">
                <label class="label text-brand">Group Designation</label>
                <input v-model="groupTitle" class="input text-xl font-black uppercase" placeholder="NAME YOUR GROUP..." />
              </div>

              <div class="bg-dark-surface border border-strong p-6 space-y-6">
                <div class="flex items-center justify-between">
                  <div class="flex flex-col">
                    <span class="text-[10px] font-black uppercase text-text-primary tracking-widest">Pure AI Mode</span>
                    <span class="text-[8px] text-text-muted uppercase tracking-widest mt-1">User as System entity</span>
                  </div>
                  <button @click="groupPureAiMode = !groupPureAiMode" class="w-12 h-6 border-2 border-strong relative transition-colors" :class="groupPureAiMode ? 'bg-brand border-brand' : 'bg-transparent'">
                    <div class="absolute top-0.5 left-0.5 w-4 h-4 bg-white transition-transform" :class="groupPureAiMode ? 'translate-x-6' : 'translate-x-0'"></div>
                  </button>
                </div>

                <div class="pt-6 border-t border-strong">
                  <div class="flex items-center justify-between mb-4">
                    <div class="flex flex-col">
                      <span class="text-[10px] font-black uppercase text-text-primary tracking-widest">Initialization Msg</span>
                      <span class="text-[8px] text-text-muted uppercase tracking-widest mt-1">Start with character line</span>
                    </div>
                    <button @click="groupFirstMessageEnabled = !groupFirstMessageEnabled" class="w-12 h-6 border-2 border-strong relative transition-colors" :class="groupFirstMessageEnabled ? 'bg-brand border-brand' : 'bg-transparent'">
                      <div class="absolute top-0.5 left-0.5 w-4 h-4 bg-white transition-transform" :class="groupFirstMessageEnabled ? 'translate-x-6' : 'translate-x-0'"></div>
                    </button>
                  </div>
                  <div v-if="groupFirstMessageEnabled">
                    <ModernSelect
                      :model-value="groupFirstMessageCharacterId || ''"
                      @update:model-value="(v) => groupFirstMessageCharacterId = v || null"
                      :options="groupFirstMessageOptions"
                      :disabled="selectedMemberIds.length === 0"
                      class="w-full"
                    />
                  </div>
                </div>
              </div>
            </div>

            <!-- 成员选择 -->
            <div class="space-y-6">
              <label class="label text-brand">Select Entities ({{ selectedMemberIds.length }}/2+)</label>
              <div class="grid grid-cols-1 gap-2 max-h-[400px] overflow-y-auto pr-2 custom-scrollbar">
                <div 
                  v-for="c in characters"
                  :key="c.id"
                  class="group flex items-start gap-4 p-4 border transition-all cursor-pointer"
                  :class="selectedMemberIds.includes(c.id) ? 'bg-brand/5 border-brand' : 'bg-dark-surface border-strong hover:border-text-secondary'"
                  @click="toggleMemberSelection(c.id)"
                >
                  <div class="relative shrink-0">
                    <ModernAvatar 
                      :src="c.avatar ? `/api/avatars/${c.avatar}` : null" 
                      :name="c.name" 
                      :size="40" 
                      rounded="rounded-none"
                      class="border border-subtle"
                    />
                    <div v-if="selectedMemberIds.includes(c.id)" class="absolute -top-2 -right-2 w-5 h-5 bg-brand text-text-inverse text-[10px] font-black flex items-center justify-center">
                      {{ selectedMemberIds.indexOf(c.id) + 1 }}
                    </div>
                  </div>
                  <div class="flex-1 min-w-0">
                    <div class="font-black text-xs truncate uppercase" :class="selectedMemberIds.includes(c.id) ? 'text-brand' : 'text-text-primary'">{{ c.name }}</div>
                    <div class="text-[8px] text-text-muted truncate uppercase tracking-widest mt-1">{{ c.description || 'NO LOGS' }}</div>
                    
                    <div v-if="selectedMemberIds.includes(c.id)" class="mt-4 flex gap-4" @click.stop>
                      <label class="flex items-center gap-2 cursor-pointer">
                        <input type="checkbox" class="w-3 h-3 border border-strong bg-transparent checked:bg-brand appearance-none" :checked="(groupMemberInclusions[c.id]?.includePersonality ?? true)" @change="(e) => { groupMemberInclusions[c.id].includePersonality = (e.target as HTMLInputElement).checked }" />
                        <span class="text-[8px] font-bold text-text-muted uppercase">Pers.</span>
                      </label>
                      <label class="flex items-center gap-2 cursor-pointer">
                        <input type="checkbox" class="w-3 h-3 border border-strong bg-transparent checked:bg-brand appearance-none" :checked="(groupMemberInclusions[c.id]?.includeScenario ?? true)" @change="(e) => { groupMemberInclusions[c.id].includeScenario = (e.target as HTMLInputElement).checked }" />
                        <span class="text-[8px] font-bold text-text-muted uppercase">Scen.</span>
                      </label>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="modal-footer">
        <div v-if="selectedMemberIds.length < 2" class="text-[9px] font-black text-error uppercase tracking-widest mr-auto flex items-center gap-2">
          <span class="w-1.5 h-1.5 bg-error animate-pulse"></span> Min. 2 entities required
        </div>
        <button class="btn btn-secondary text-[10px] px-8" @click="emit('update:show', false)">ABORT</button>
        <button class="btn btn-primary text-[10px] px-12" :disabled="selectedMemberIds.length < 2" @click="handleCreate">INITIALIZE</button>
      </div>
    </div>
  </div>
</template>
