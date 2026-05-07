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
import type { CharacterCard, ChatContentRegexRule, ChatMvuMode, GroupMvuPreset, StatusTableDef } from '../../types/models'
import ModernAvatar from '../ModernAvatar.vue'
import ModernSelect from '../ModernSelect.vue'
import ThemedCheckbox from '../ThemedCheckbox.vue'
import MvuCapabilityEditor from '../chat/MvuCapabilityEditor.vue'
import { characterHasMvuProfileData } from '../../utils/groupMvu'

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
    groupSystemInjectDepth: number
    groupSystemAlwaysAtBottom: boolean
    groupMvuPreset: GroupMvuPreset
    groupMvuPresetCharacterId: string | null
    mvuMode: ChatMvuMode
    mvuDirective: string | null
    contentRegexRules: ChatContentRegexRule[]
    initialStateTables: StatusTableDef[]
  }]
}>()

// 本地状态
const selectedMemberIds = ref<string[]>([])
const groupTitle = ref('')
const groupPureAiMode = ref(false)
const groupFirstMessageEnabled = ref(true)
const groupFirstMessageCharacterId = ref<string | null>(null)
const groupMemberInclusions = ref<Record<string, { includePersonality: boolean; includeScenario: boolean }>>({})
const groupSystemInjectDepth = ref(5)
const groupSystemAlwaysAtBottom = ref(true)
/** 群聊 MVU：总开关 + 单一来源选择（沿用成员 / 以成员为模板） */
const groupMvuEnabled = ref(false)
/** 空 | inherit:<id> | fork:<id> */
const groupMvuSourceKey = ref('')
/** 启用 MVU 时本地编辑的会话级 MVU 草稿（提交时通过 create 事件带回） */
const mvuModeDraft = ref<ChatMvuMode>(null)
const mvuDirectiveDraft = ref<string>('')
const contentRegexRulesDraft = ref<ChatContentRegexRule[]>([])
const initialStateTablesDraft = ref<StatusTableDef[]>([])

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
    groupSystemInjectDepth.value = 5
    groupSystemAlwaysAtBottom.value = true
    groupMvuEnabled.value = false
    groupMvuSourceKey.value = ''
    mvuModeDraft.value = null
    mvuDirectiveDraft.value = ''
    contentRegexRulesDraft.value = []
    initialStateTablesDraft.value = []
    return
  }
  selectedMemberIds.value = []
  groupTitle.value = ''
  groupPureAiMode.value = false
  groupFirstMessageEnabled.value = true
  groupFirstMessageCharacterId.value = null
  groupMemberInclusions.value = {}
  groupSystemInjectDepth.value = 5
  groupSystemAlwaysAtBottom.value = true
  groupMvuEnabled.value = false
  groupMvuSourceKey.value = ''
  mvuModeDraft.value = null
  mvuDirectiveDraft.value = ''
  contentRegexRulesDraft.value = []
  initialStateTablesDraft.value = []
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

const groupMvuSourceOptions = computed(() => {
  const head = [{ label: '（请选择 MVU 来源）', value: '' }]
  if (selectedMemberIds.value.length < 2) return head
  const inherit = selectedMemberIds.value
    .map((id) => props.characters.find((c) => c.id === id))
    .filter((c): c is CharacterCard => !!c && characterHasMvuProfileData(c))
    .map((c) => ({ label: `沿用「${c.name}」的 MVU`, value: `inherit:${c.id}` }))
  const fork = selectedMemberIds.value.map((id) => {
    const c = props.characters.find((x) => x.id === id)
    return { label: `以「${c?.name || id}」为模板的 MVU`, value: `fork:${id}` }
  })
  return [...head, ...inherit, ...fork]
})

/** 选定来源后：把对应角色卡的 MVU 配置预填到草稿，便于用户在弹窗里直接调整 */
function syncDraftFromSourceKey(key: string) {
  if (!key) {
    mvuModeDraft.value = null
    mvuDirectiveDraft.value = ''
    contentRegexRulesDraft.value = []
    initialStateTablesDraft.value = []
    return
  }
  const idx = key.indexOf(':')
  if (idx < 0) return
  const pid = key.slice(idx + 1)
  const card = props.characters.find((c) => c.id === pid)
  if (!card) return
  mvuModeDraft.value = (card.mvuMode === 'directive' ? 'directive' : 'regex')
  mvuDirectiveDraft.value = typeof card.mvuDirective === 'string' ? card.mvuDirective : ''
  contentRegexRulesDraft.value = (card.contentRegexRules || []).map((r) => ({ ...r }))
  initialStateTablesDraft.value = (card.initialStateTables || []).map((t) => ({
    name: t.name,
    columns: [...t.columns],
    rows: t.rows.map((r) => ({ field: r.field, cells: { ...r.cells } })),
  }))
}

watch(groupMvuEnabled, (on) => {
  if (!on) {
    groupMvuSourceKey.value = ''
    syncDraftFromSourceKey('')
    return
  }
  if (groupMvuSourceKey.value) return
  const pick = groupMvuSourceOptions.value.find((o) => o.value && o.value.startsWith('inherit:'))
  if (pick) {
    groupMvuSourceKey.value = pick.value
    syncDraftFromSourceKey(pick.value)
    return
  }
  const forkPick = groupMvuSourceOptions.value.find((o) => o.value && o.value.startsWith('fork:'))
  if (forkPick) {
    groupMvuSourceKey.value = forkPick.value
    syncDraftFromSourceKey(forkPick.value)
  }
})

watch(groupMvuSourceKey, (k) => {
  if (!groupMvuEnabled.value) return
  syncDraftFromSourceKey(k)
})

watch(
  () => [...selectedMemberIds.value],
  () => {
    const k = groupMvuSourceKey.value
    if (!k) return
    const idx = k.indexOf(':')
    if (idx < 0) return
    const id = k.slice(idx + 1)
    if (!selectedMemberIds.value.includes(id)) {
      groupMvuSourceKey.value = ''
      syncDraftFromSourceKey('')
    }
  },
)

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
  let groupMvuPreset: GroupMvuPreset = 'off'
  let groupMvuPresetCharacterId: string | null = null
  if (groupMvuEnabled.value) {
    const key = groupMvuSourceKey.value
    const idx = key.indexOf(':')
    if (idx < 0) return
    const kind = key.slice(0, idx)
    const pid = key.slice(idx + 1)
    if (!pid || !selectedMemberIds.value.includes(pid)) return
    if (kind === 'inherit') {
      const card = props.characters.find((c) => c.id === pid)
      if (!card || !characterHasMvuProfileData(card)) return
      groupMvuPreset = 'inherit_member'
      groupMvuPresetCharacterId = pid
    } else if (kind === 'fork') {
      groupMvuPreset = 'fork_session'
      groupMvuPresetCharacterId = pid
    } else {
      return
    }
  }

  const trimmedDirective = (mvuDirectiveDraft.value || '').trim()
  emit('create', {
    title: groupTitle.value || '新群聊',
    memberIds: selectedMemberIds.value,
    pureAiMode: groupPureAiMode.value,
    firstMessageCharacterId: groupFirstMessageEnabled.value ? groupFirstMessageCharacterId.value : null,
    memberInclusions: groupMemberInclusions.value,
    groupSystemInjectDepth: Math.max(0, Number(groupSystemInjectDepth.value) || 0),
    groupSystemAlwaysAtBottom: groupSystemAlwaysAtBottom.value,
    groupMvuPreset,
    groupMvuPresetCharacterId,
    mvuMode: groupMvuEnabled.value ? mvuModeDraft.value : null,
    mvuDirective: groupMvuEnabled.value && trimmedDirective ? trimmedDirective : null,
    contentRegexRules: groupMvuEnabled.value
      ? contentRegexRulesDraft.value.map((r, i) => ({ ...r, order: i }))
      : [],
    initialStateTables: groupMvuEnabled.value ? initialStateTablesDraft.value : [],
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
              <div class="flex items-center justify-between gap-3">
                <div class="min-w-0 flex-1 text-sm text-gray-400">纯 AI 模式（不注入 Persona，用户发言将以 system 影响世界）</div>
                <button
                  type="button"
                  class="flex shrink-0 items-center gap-2"
                  @click="groupPureAiMode = !groupPureAiMode"
                >
                  <div class="w-10 h-5 rounded-full relative transition-colors duration-200" :class="groupPureAiMode ? 'bg-brand' : 'bg-gray-700'">
                    <div class="absolute top-1 w-3 h-3 rounded-full bg-white transition-transform duration-200" :class="groupPureAiMode ? 'left-6' : 'left-1'"></div>
                  </div>
                  <span class="min-w-[2.5rem] text-center text-xs text-gray-400">{{ groupPureAiMode ? '开启' : '关闭' }}</span>
                </button>
              </div>
              <div class="mt-3 space-y-3 pt-2 border-t border-white/5">
                <div class="flex items-center justify-between gap-3">
                  <div class="min-w-0 flex-1 text-sm text-gray-400">永远在底部（默认）</div>
                  <button
                    type="button"
                    class="flex shrink-0 items-center gap-2"
                    @click="groupSystemAlwaysAtBottom = !groupSystemAlwaysAtBottom"
                  >
                    <div class="w-10 h-5 rounded-full relative transition-colors duration-200" :class="groupSystemAlwaysAtBottom ? 'bg-brand' : 'bg-gray-700'">
                      <div class="absolute top-1 w-3 h-3 rounded-full bg-white transition-transform duration-200" :class="groupSystemAlwaysAtBottom ? 'left-6' : 'left-1'"></div>
                    </div>
                    <span class="min-w-[2.5rem] text-center text-xs text-gray-400">{{ groupSystemAlwaysAtBottom ? '开启' : '关闭' }}</span>
                  </button>
                </div>
                <p class="text-xs text-gray-500">开启时整段 system 在首条，与旧版一致；关闭后可用下方「注入深度」将整段 system 插入历史。</p>
                <div :class="{ 'opacity-50 pointer-events-none': groupSystemAlwaysAtBottom }">
                  <label class="text-xs text-gray-500">系统提示词注入深度</label>
                  <input
                    v-model.number="groupSystemInjectDepth"
                    type="number"
                    min="0"
                    class="input mt-1 w-full bg-black/20 border-white/10 focus:border-brand-a50"
                    step="1"
                  />
                </div>
              </div>
            </div>

            <div v-if="!isMigrateMode" class="bg-white/5 border border-white/10 rounded-xl p-3">
              <div class="text-sm text-gray-300 font-medium mb-2">群聊首句（故事背景）</div>
              <div class="flex items-center justify-between gap-3 mb-2">
                <div class="min-w-0 flex-1 text-sm text-gray-400">启用某角色的 First Message 作为开场</div>
                <button type="button" class="flex shrink-0 items-center gap-2" @click="groupFirstMessageEnabled = !groupFirstMessageEnabled">
                  <div class="w-10 h-5 rounded-full relative transition-colors duration-200" :class="groupFirstMessageEnabled ? 'bg-brand' : 'bg-gray-700'">
                    <div class="absolute top-1 w-3 h-3 rounded-full bg-white transition-transform duration-200" :class="groupFirstMessageEnabled ? 'left-6' : 'left-1'"></div>
                  </div>
                  <span class="min-w-[2.5rem] text-center text-xs text-gray-400">{{ groupFirstMessageEnabled ? '启用' : '关闭' }}</span>
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

            <div v-if="!isMigrateMode" class="bg-white/5 border border-white/10 rounded-xl p-3 space-y-3">
              <div class="text-sm text-gray-300 font-medium">群聊 MVU</div>
              <div class="flex items-center justify-between gap-3">
                <div class="min-w-0 flex-1 text-sm text-gray-400">启用群聊 MVU（状态栏 / 指令 / 正则队列）</div>
                <button
                  type="button"
                  class="flex shrink-0 items-center gap-2"
                  @click="groupMvuEnabled = !groupMvuEnabled"
                >
                  <div
                    class="w-10 h-5 rounded-full relative transition-colors duration-200"
                    :class="groupMvuEnabled ? 'bg-brand' : 'bg-gray-700'"
                  >
                    <div
                      class="absolute top-1 w-3 h-3 rounded-full bg-white transition-transform duration-200"
                      :class="groupMvuEnabled ? 'left-6' : 'left-1'"
                    />
                  </div>
                  <span class="min-w-[2.5rem] text-center text-xs text-gray-400">{{ groupMvuEnabled ? '开启' : '关闭' }}</span>
                </button>
              </div>
              <div v-if="groupMvuEnabled" class="space-y-3 pt-2 border-t border-white/5">
                <div class="space-y-1.5">
                  <label class="block text-xs text-gray-500">MVU 来源</label>
                  <ModernSelect
                    :model-value="groupMvuSourceKey"
                    @update:model-value="(v) => (groupMvuSourceKey = v)"
                    :options="groupMvuSourceOptions"
                    :disabled="selectedMemberIds.length < 2"
                    placeholder="（请选择）"
                    class="w-full"
                  />
                  <p v-if="selectedMemberIds.length < 2" class="text-xs text-gray-500">请先选择至少两名群成员后再选择 MVU 来源。</p>
                </div>
                <MvuCapabilityEditor
                  v-if="groupMvuSourceKey"
                  :mvu-mode="mvuModeDraft"
                  :mvu-directive="mvuDirectiveDraft"
                  :content-regex-rules="contentRegexRulesDraft"
                  :initial-state-tables="initialStateTablesDraft"
                  :allow-inherit="true"
                  tables-empty-hint="暂无状态表格。点击「新建表格」开始配置。"
                  @update:mvu-mode="(v) => (mvuModeDraft = v)"
                  @update:mvu-directive="(v) => (mvuDirectiveDraft = v)"
                  @update:content-regex-rules="(v) => (contentRegexRulesDraft = v)"
                  @update:initial-state-tables="(v) => (initialStateTablesDraft = v)"
                />
              </div>
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
                          <ThemedCheckbox
                            :checked="(groupMemberInclusions[c.id]?.includePersonality ?? true)"
                            @update:checked="(checked) => { const inc = groupMemberInclusions[c.id] ?? { includePersonality: true, includeScenario: true }; groupMemberInclusions[c.id] = inc; inc.includePersonality = checked }"
                          />
                          Personality
                        </label>
                        <label class="flex items-center gap-1 cursor-pointer">
                          <ThemedCheckbox
                            :checked="(groupMemberInclusions[c.id]?.includeScenario ?? true)"
                            @update:checked="(checked) => { const inc = groupMemberInclusions[c.id] ?? { includePersonality: true, includeScenario: true }; groupMemberInclusions[c.id] = inc; inc.includeScenario = checked }"
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
          <button
            class="btn btn-primary"
            :disabled="selectedMemberIds.length < 2 || (groupMvuEnabled && !groupMvuSourceKey)"
            @click="handleCreate"
          >
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
