<script setup lang="ts">
/**
 * GroupCreatorModal - 群聊创建弹窗组件
 *
 * 组件职责：
 * - 提供群聊创建界面，选择成员、设置标题等
 * - 支持选择多个角色作为群聊成员
 * - 支持设置纯AI模式
 * - 支持设置首句发言角色
 * - 支持设置每个成员的包含项（性格、场景）
 *
 * Props说明：
 * - show: 是否显示弹窗（v-model:show）
 * - characters: 角色列表（来自types/models.ts的CharacterCard[]类型）
 *
 * Emits说明：
 * - update:show: 更新显示状态（v-model:show）
 * - create: 创建群聊，传递创建数据（标题、成员ID列表、纯AI模式、首句角色ID、成员包含项）
 *
 * 使用的Composables：
 * 无
 *
 * 使用的Stores：
 * 无
 *
 * 文件关系：
 *    - 被导入：被views/ChatPage.vue使用
 *    - 导入：导入vue的ref、computed、watch、types/models.ts的CharacterCard类型、components/ModernAvatar.vue、components/ModernSelect.vue
 *    - 依赖：依赖vue
 *    - 位置：组件层，提供群聊创建功能
 */
import { ref, computed, watch } from 'vue'
import type { CharacterCard } from '../../types/models'
import ModernAvatar from '../ModernAvatar.vue'
import ModernSelect from '../ModernSelect.vue'

const props = defineProps<{
  show: boolean
  characters: CharacterCard[]
  /** 非空时表示从单聊迁移：预选成员、锁定不可移除、隐藏首句块 */
  migrateFromChatId?: string | null
  initialMemberIds?: string[]
  initialTitle?: string
  lockedMemberIds?: string[]
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

const isMigrateMode = computed(() => !!(props.migrateFromChatId && (props.initialMemberIds?.length ?? 0) > 0))

// 打开时重置或载入迁移预设
watch(() => props.show, (newVal) => {
  if (!newVal) return
  if (isMigrateMode.value) {
    const ids = [...(props.initialMemberIds as string[])]
    selectedMemberIds.value = ids
    groupTitle.value = props.initialTitle ?? ''
    groupPureAiMode.value = false
    groupFirstMessageEnabled.value = false
    groupFirstMessageCharacterId.value = ids[0] ?? null
    groupMemberInclusions.value = {}
    for (const id of ids) {
      groupMemberInclusions.value[id] = { includePersonality: true, includeScenario: true }
    }
    return
  }
  selectedMemberIds.value = []
  groupTitle.value = ''
  groupPureAiMode.value = false
  groupFirstMessageEnabled.value = true
  groupFirstMessageCharacterId.value = null
  groupMemberInclusions.value = {}
})

/**
 * 计算首句发言角色选项
 *
 * 根据已选中的成员生成首句发言角色的选项列表。
 */
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

/**
 * 切换成员选择
 *
 * 切换指定角色的选中状态。
 * 如果取消选中，则删除该成员的包含项设置；如果首句角色被取消，则选择第一个成员。
 * 如果选中，则创建默认的包含项设置；如果还没有首句角色，则设置为该角色。
 *
 * @param {string} characterId - 角色ID
 */
function toggleMemberSelection(characterId: string) {
  const locked = props.lockedMemberIds ?? []
  if (locked.includes(characterId)) {
    return
  }
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

/**
 * 处理创建群聊
 *
 * 验证成员数量（至少2个），然后触发create事件，传递群聊创建数据。
 */
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
  <Transition name="modal">
    <div v-if="show" class="modal">
      <div class="modal-backdrop" @click="emit('update:show', false)"></div>
      <div class="modal-content chat-modal-width-600-90 glass-panel">
        <div class="modal-header">
          <h3 class="modal-title text-slate-50">{{ isMigrateMode ? '从单聊转为群聊' : '创建群聊' }}</h3>
          <button class="modal-close" @click="emit('update:show', false)">×</button>
        </div>
        <div class="modal-body">
          <div class="space-y-6">
            <div class="form-group">
              <label class="label">群聊名称</label>
              <input 
                v-model="groupTitle" 
                class="input bg-black/20 border-white/10 focus:border-brand-a50" 
                placeholder="新群聊" 
              />
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

            <div v-if="!isMigrateMode" class="bg-white/5 border border-white/10 rounded-xl p-3">
              <div class="text-sm text-gray-300 font-medium mb-2">群聊首句（故事背景）</div>
              <div class="flex items-center justify-between mb-2">
                <div class="text-sm text-gray-400">启用某角色的 First Message 作为开场</div>
                <button class="flex items-center gap-2" @click="groupFirstMessageEnabled = !groupFirstMessageEnabled">
                  <div class="w-10 h-5 rounded-full relative transition-colors duration-200" :class="groupFirstMessageEnabled ? 'bg-brand' : 'bg-gray-700'">
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
              <div class="text-sm text-gray-400 mb-3">
                {{ isMigrateMode ? '当前单聊角色已固定为首位，请再选择至少一名其他角色：' : '选择群成员 (至少选择2个角色):' }}
              </div>
              <div class="grid grid-cols-2 sm:grid-cols-3 gap-3 max-h-[300px] overflow-y-auto pr-2 custom-scrollbar">
                <div 
                  v-for="c in characters"
                  :key="c.id"
                  class="flex items-start gap-3 p-3 rounded-xl cursor-pointer transition-all border-2"
                  :class="selectedMemberIds.includes(c.id) ? 'bg-brand-a10 border-brand-a20' : 'bg-white/5 border-transparent hover:bg-white/10'"
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
                      class="absolute -top-1 -right-1 w-5 h-5 bg-brand rounded-full flex items-center justify-center text-white text-xs font-bold"
                    >
                      {{ selectedMemberIds.indexOf(c.id) + 1 }}
                    </div>
                  </div>
                  <div class="flex-1 min-w-0">
                    <div class="font-medium text-sm truncate" :class="selectedMemberIds.includes(c.id) ? 'text-brand-light' : 'text-gray-300'">{{ c.name }}</div>
                    <div class="text-xs text-gray-500 truncate">{{ c.description || '暂无简介' }}</div>
                    <div v-if="selectedMemberIds.includes(c.id)" class="mt-2 space-y-1" @click.stop>
                      <div class="text-[10px] text-gray-500">system prompt 插入：</div>
                      <div class="flex flex-wrap gap-3 text-xs text-gray-300">
                        <label class="flex items-center gap-1 cursor-pointer">
                          <input
                            type="checkbox"
                            class="accent-brand"
                            :checked="(groupMemberInclusions[c.id]?.includePersonality ?? true)"
                            @change="(e) => { const checked = (e.target as HTMLInputElement).checked; const inc = groupMemberInclusions[c.id] ?? { includePersonality: true, includeScenario: true }; groupMemberInclusions[c.id] = inc; inc.includePersonality = checked }"
                          />
                          Personality
                        </label>
                        <label class="flex items-center gap-1 cursor-pointer">
                          <input
                            type="checkbox"
                            class="accent-brand"
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
          <button class="btn btn-secondary bg-white/5 hover:bg-white/10 text-gray-300 border border-white/5" @click="emit('update:show', false)">取消</button>
          <button class="btn btn-primary" :disabled="selectedMemberIds.length < 2" @click="handleCreate">
            创建群聊
          </button>
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
</style>
