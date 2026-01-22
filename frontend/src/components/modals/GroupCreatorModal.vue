<script setup lang="ts">
/**
 * GroupCreatorModal - 群聊创建弹窗
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

// 本地状态
const selectedMemberIds = ref<string[]>([])
const groupTitle = ref('')
const groupPureAiMode = ref(false)
const groupFirstMessageEnabled = ref(true)
const groupFirstMessageCharacterId = ref<string | null>(null)
const groupMemberInclusions = ref<Record<string, { includePersonality: boolean; includeScenario: boolean }>>({})

// 重置状态
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
    return {
      label: char?.name || id,
      value: id
    }
  })
  return [
    { label: '（未选择）', value: '' },
    ...opts
  ]
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
    title: groupTitle.value || '新群聊',
    memberIds: selectedMemberIds.value,
    pureAiMode: groupPureAiMode.value,
    firstMessageCharacterId: groupFirstMessageEnabled.value ? groupFirstMessageCharacterId.value : null,
    memberInclusions: groupMemberInclusions.value,
  })
  emit('update:show', false)
}
</script>

<template>
  <div v-if="show" class="modal">
    <div class="modal-backdrop" @click="emit('update:show', false)"></div>
    <div class="modal-content chat-modal-width-600-90">
      <div class="modal-header">
        <h3 class="modal-title">创建群聊</h3>
        <button class="modal-close" @click="emit('update:show', false)">×</button>
      </div>
      <div class="modal-body">
        <div class="space-y-6">
          <div class="form-group">
            <label class="label">群聊名称</label>
            <input v-model="groupTitle" class="input" placeholder="新群聊" />
          </div>

          <div class="bg-white/5 border border-white/10 rounded-xl p-3">
            <div class="text-sm text-gray-300 font-medium mb-2">本次聊天设置</div>
            <div class="flex items-center justify-between">
              <div class="text-sm text-gray-400">纯 AI 模式（不注入 Persona，用户发言将以 system 影响世界）</div>
              <button
                class="flex items-center gap-2"
                @click="groupPureAiMode = !groupPureAiMode"
              >
                <div class="w-10 h-5 rounded-full relative transition-colors duration-200" :class="groupPureAiMode ? 'bg-brand' : 'bg-gray-700'">
                  <div class="absolute top-1 w-3 h-3 rounded-full bg-white transition-transform duration-200" :class="groupPureAiMode ? 'left-6' : 'left-1'"></div>
                </div>
                <span class="text-xs text-gray-400">{{ groupPureAiMode ? '开启' : '关闭' }}</span>
              </button>
            </div>
          </div>

          <div class="bg-white/5 border border-white/10 rounded-xl p-3">
            <div class="text-sm text-gray-300 font-medium mb-2">群聊首句（故事背景）</div>
            <div class="flex items-center justify-between mb-2">
              <div class="text-sm text-gray-400">启用某角色的 First Message 作为开场</div>
              <button class="flex items-center gap-2" @click="groupFirstMessageEnabled = !groupFirstMessageEnabled">
                <div class="w-10 h-5 rounded-full relative transition-colors duration-200" :class="groupFirstMessageEnabled ? 'bg-purple-500' : 'bg-gray-700'">
                  <div class="absolute top-1 w-3 h-3 rounded-full bg-white transition-transform duration-200" :class="groupFirstMessageEnabled ? 'left-6' : 'left-1'"></div>
                </div>
                <span class="text-xs text-gray-400">{{ groupFirstMessageEnabled ? '启用' : '关闭' }}</span>
              </button>
            </div>
            <div v-if="groupFirstMessageEnabled" class="flex items-center gap-2">
              <span class="text-xs text-gray-500 shrink-0">选择角色：</span>
              <ModernSelect
                :model-value="groupFirstMessageCharacterId || ''"
                @update:model-value="(v) => groupFirstMessageCharacterId = v || null"
                :options="groupFirstMessageOptions"
                :disabled="selectedMemberIds.length === 0"
                placeholder="（未选择）"
                class="flex-1"
              />
            </div>
            <div class="text-xs text-gray-500 mt-2">创建后会在聊天窗口内直接插入该角色的首句（会写入聊天记录）。</div>
          </div>
          
          <div>
            <div class="text-sm text-gray-400 mb-3">选择群成员 (至少选择2个角色):</div>
            <div class="grid grid-cols-2 sm:grid-cols-3 gap-3 max-h-[300px] overflow-y-auto pr-2 custom-scrollbar">
              <div 
                v-for="c in characters"
                :key="c.id"
                class="flex items-start gap-3 p-3 rounded-xl cursor-pointer transition-all border-2"
                :class="selectedMemberIds.includes(c.id) ? 'bg-purple-500/10 border-purple-500/50' : 'bg-white/5 border-transparent hover:bg-white/10'"
                @click="toggleMemberSelection(c.id)"
              >
                <div class="relative shrink-0">
                  <ModernAvatar 
                    :src="c.avatar ? `/api/avatars/${c.avatar}` : null" 
                    :name="c.name" 
                    :size="40" 
                    aspect="auto"
                    object-fit="contain"
                    rounded="rounded-lg"
                  />
                  <div 
                    v-if="selectedMemberIds.includes(c.id)"
                    class="absolute -top-1 -right-1 w-5 h-5 bg-purple-500 rounded-full flex items-center justify-center text-white text-xs font-bold"
                  >
                    {{ selectedMemberIds.indexOf(c.id) + 1 }}
                  </div>
                </div>
                <div class="flex-1 min-w-0">
                  <div class="font-medium text-sm truncate" :class="selectedMemberIds.includes(c.id) ? 'text-purple-300' : 'text-gray-300'">{{ c.name }}</div>
                  <div class="text-xs text-gray-500 truncate">{{ c.description || '暂无简介' }}</div>
                  <div v-if="selectedMemberIds.includes(c.id)" class="mt-2 space-y-1" @click.stop>
                    <div class="text-[10px] text-gray-500">system prompt 插入：</div>
                    <div class="flex flex-wrap gap-3 text-xs text-gray-300">
                      <label class="flex items-center gap-1 cursor-pointer">
                        <input
                          type="checkbox"
                          class="accent-purple-500"
                          :checked="(groupMemberInclusions[c.id]?.includePersonality ?? true)"
                          @change="(e) => { const checked = (e.target as HTMLInputElement).checked; const inc = groupMemberInclusions[c.id] ?? { includePersonality: true, includeScenario: true }; groupMemberInclusions[c.id] = inc; inc.includePersonality = checked }"
                        />
                        Personality
                      </label>
                      <label class="flex items-center gap-1 cursor-pointer">
                        <input
                          type="checkbox"
                          class="accent-purple-500"
                          :checked="(groupMemberInclusions[c.id]?.includeScenario ?? true)"
                          @change="(e) => { const checked = (e.target as HTMLInputElement).checked; const inc = groupMemberInclusions[c.id] ?? { includePersonality: true, includeScenario: true }; groupMemberInclusions[c.id] = inc; inc.includeScenario = checked }"
                        />
                        Scenario
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
        <div class="text-sm text-gray-500 mr-auto">
          已选择 {{ selectedMemberIds.length }} 个角色
          <span v-if="selectedMemberIds.length < 2" class="text-yellow-500">(至少需要2个)</span>
        </div>
        <button class="btn btn-secondary" @click="emit('update:show', false)">取消</button>
        <button class="btn btn-primary" :disabled="selectedMemberIds.length < 2" @click="handleCreate">
          创建群聊
        </button>
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
</style>
