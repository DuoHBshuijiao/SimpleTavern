<script setup lang="ts">
/**
 * GroupSettingsModal - 群聊设置弹窗组件
 *
 * 组件职责：
 * - 管理群聊设置，包括成员列表、发言顺序、群聊延迟等
 * - 支持拖拽调整成员发言顺序
 * - 支持添加和删除成员
 * - 支持设置群聊延迟时间
 * - 支持打开成员设置编辑
 *
 * Props说明：
 * - show: 是否显示弹窗（v-model:show）
 * - chat: 群聊数据（来自types/models.ts的Chat类型）
 * - characters: 角色列表（来自types/models.ts的CharacterCard[]类型）
 *
 * Emits说明：
 * - update:show: 更新显示状态（v-model:show）
 * - apply: 一次提交成员顺序、发言延迟、system 插入选项
 * - open-member-settings: 打开成员设置编辑，传递成员ID
 *
 * 使用的Composables：
 * 无
 *
 * 使用的Stores：
 * 无
 *
 * 文件关系：
 *    - 被导入：被views/ChatPage.vue使用
 *    - 导入：导入vue的ref和watch、types/models.ts的类型、components/ModernAvatar.vue
 *    - 依赖：依赖vue
 *    - 位置：组件层，提供群聊设置功能
 */
import { ref, watch, computed } from 'vue'
import type { Chat, CharacterCard, ChatContentRegexRule, ChatMvuMode, ChatOverrides, StatusTableDef } from '../../types/models'
import ModernAvatar from '../ModernAvatar.vue'
import ModernSelect from '../ModernSelect.vue'
import MvuCapabilityEditor from '../chat/MvuCapabilityEditor.vue'
import { GripVertical, X } from 'lucide-vue-next'
import { useDialogBehavior } from '../../composables/useDialogBehavior'
import { dialogAria } from '../../utils/uiPrimitives'

const props = defineProps<{
  show: boolean
  chat: Chat | null
  characters: CharacterCard[]
}>()

const emit = defineEmits<{
  'update:show': [value: boolean]
  apply: [payload: {
    memberIds: string[]
    groupDelay: number
    groupSystemInjectDepth: number
    groupSystemAlwaysAtBottom: boolean
    groupMvuEnabled: boolean
    groupMvuAnchorCharacterId: string | null
    groupMvuTemplateCharacterId: string | null
    mvuMode: ChatMvuMode
    mvuDirective: string | null
    contentRegexRules: ChatContentRegexRule[]
    stateTables: StatusTableDef[]
  }]
  'open-member-settings': [memberId: string]
}>()

const memberIdsDraft = ref<string[]>([])
const groupDelayDraft = ref<number>(1500)
const groupSystemInjectDepthDraft = ref<number>(5)
const groupSystemAlwaysAtBottomDraft = ref<boolean>(true)
const draggingIdx = ref<number | null>(null)

const groupMvuEnabledDraft = ref(false)
const groupMvuAnchorDraft = ref<string | null>(null)
const groupMvuTemplateDraft = ref<string | null>(null)
const mvuModeDraft = ref<ChatMvuMode>(null)
const mvuDirectiveDraft = ref('')
const contentRegexRulesDraft = ref<ChatContentRegexRule[]>([])
const stateTablesDraft = ref<StatusTableDef[]>([])

watch(() => props.show, (val) => {
  if (val && props.chat) {
    memberIdsDraft.value = [...props.chat.memberIds]
    groupDelayDraft.value = props.chat.groupDelay || 1500
    groupSystemInjectDepthDraft.value =
      typeof props.chat.groupSystemInjectDepth === 'number' ? props.chat.groupSystemInjectDepth : 5
    groupSystemAlwaysAtBottomDraft.value = props.chat.groupSystemAlwaysAtBottom !== false
    const ov = (props.chat.overrides || {}) as ChatOverrides
    groupMvuEnabledDraft.value = ov.groupMvuEnabled === true
    groupMvuAnchorDraft.value = ov.groupMvuAnchorCharacterId ?? null
    groupMvuTemplateDraft.value = ov.groupMvuTemplateCharacterId ?? null
    mvuModeDraft.value = (ov.mvuMode === 'directive' ? 'directive' : ov.mvuMode === 'regex' ? 'regex' : null) as ChatMvuMode
    mvuDirectiveDraft.value = typeof ov.mvuDirective === 'string' ? ov.mvuDirective : ''
    contentRegexRulesDraft.value = (ov.contentRegexRules || []).map((r) => ({ ...r }))
    const tables = props.chat.stateVariables?.tables ?? []
    stateTablesDraft.value = tables.map((t) => ({
      name: t.name,
      columns: [...t.columns],
      rows: t.rows.map((r) => ({ field: r.field, cells: { ...r.cells } })),
    }))
  }
})

/**
 * 获取角色信息
 *
 * 根据角色ID从角色列表中查找角色。
 *
 * @param {string} id - 角色ID
 * @returns {CharacterCard | undefined} 角色信息，如果未找到则返回undefined
 */
function getCharacter(id: string) {
  return props.characters.find(c => c.id === id)
}

const groupMvuAnchorOptions = computed(() => {
  const ids = [...memberIdsDraft.value]
  const anchor = groupMvuAnchorDraft.value
  if (anchor && !ids.includes(anchor)) {
    ids.unshift(anchor)
  }
  return ids.map((id) => ({
    label: getCharacter(id)?.name || id,
    value: id,
  }))
})

const groupMvuAnchorSelectOptions = computed(() => [
  { label: '（未选择）', value: '' },
  ...groupMvuAnchorOptions.value,
])

const groupMvuTemplateSelectOptions = computed(() => [
  { label: '（无）', value: '' },
  ...groupMvuAnchorOptions.value,
])

/**
 * 处理拖拽开始
 *
 * 记录开始拖拽的成员索引。
 *
 * @param {number} idx - 成员索引
 */
function handleDragStart(idx: number) {
  draggingIdx.value = idx
}

/**
 * 处理拖拽悬停
 *
 * 当拖拽到其他位置时，重新排列成员顺序。
 * 使用数组splice方法移动元素位置。
 *
 * @param {DragEvent} e - 拖拽事件
 * @param {number} idx - 目标索引
 */
function handleDragOver(e: DragEvent, idx: number) {
  e.preventDefault()
  if (draggingIdx.value === null || draggingIdx.value === idx) return
  
  const arr = [...memberIdsDraft.value]
  const item = arr.splice(draggingIdx.value, 1)[0]
  if (item) {
    arr.splice(idx, 0, item)
    memberIdsDraft.value = arr
  }
  draggingIdx.value = idx
}

/**
 * 处理拖拽结束
 *
 * 清空拖拽状态。
 */
function handleDragEnd() {
  draggingIdx.value = null
}

/**
 * 关闭弹窗
 *
 * 触发update:show事件，传递false。
 */
function close() {
  emit('update:show', false)
}

/**
 * 保存设置：一次 apply，由父级调用 API
 */
function save() {
  emit('apply', {
    memberIds: memberIdsDraft.value,
    groupDelay: groupDelayDraft.value,
    groupSystemInjectDepth: Math.max(0, Number(groupSystemInjectDepthDraft.value) || 0),
    groupSystemAlwaysAtBottom: groupSystemAlwaysAtBottomDraft.value,
    groupMvuEnabled: groupMvuEnabledDraft.value,
    groupMvuAnchorCharacterId: groupMvuAnchorDraft.value,
    groupMvuTemplateCharacterId: groupMvuTemplateDraft.value,
    mvuMode: mvuModeDraft.value,
    mvuDirective: mvuDirectiveDraft.value.trim() ? mvuDirectiveDraft.value : null,
    contentRegexRules: contentRegexRulesDraft.value.map((r, i) => ({ ...r, order: i })),
    stateTables: stateTablesDraft.value,
  })
}

const titleId = 'group-settings-title'
const dialogAttrs = dialogAria(titleId)
const { dialogRef } = useDialogBehavior(() => props.show && !!props.chat, close)
void dialogRef
</script>

<template>
  <Transition name="modal">
    <div v-if="show && chat" class="modal">
      <div class="modal-backdrop" @click="close"></div>
      <div ref="dialogRef" v-bind="dialogAttrs" tabindex="-1" class="modal-content modal-surface chat-modal-width-600-90">
        <div class="modal-header">
          <h3 :id="titleId" class="modal-title">群聊设置 - {{ chat.title }}</h3>
          <button type="button" class="modal-close" aria-label="关闭群聊设置弹窗" @click="close">
              <X class="w-5 h-5" />
          </button>
        </div>
        
        <div class="modal-body space-y-6">
          <!-- 群聊发言延迟 -->
          <div class="form-group">
            <label class="label">发言延迟 (ms)</label>
            <input 
              v-model.number="groupDelayDraft"
              type="number"
              class="input"
              step="100"
              min="0"
            />
            <div class="form-hint">角色连续发言之间的间隔时间</div>
          </div>

          <div class="form-group">
            <label class="label text-brand-light">永远在底部（默认）</label>
            <div class="flex items-start justify-between gap-3">
              <p class="min-w-0 flex-1 text-xs text-muted">
                开启时整段 system 在消息最前，与旧版一致；关闭后按下方深度将整段 system 插入历史，利于部分 KV 命中。
              </p>
              <button
                type="button"
                class="flex shrink-0 items-center gap-2"
                :aria-pressed="groupSystemAlwaysAtBottomDraft"
                @click="groupSystemAlwaysAtBottomDraft = !groupSystemAlwaysAtBottomDraft"
              >
                <div
                  class="w-10 h-5 rounded-full relative transition-colors duration-200"
                  :class="groupSystemAlwaysAtBottomDraft ? 'bg-brand' : 'bg-surface-muted'"
                >
                  <div
                    class="absolute top-1 w-3 h-3 rounded-full bg-[var(--color-text-primary)] transition-transform duration-200"
                    :class="groupSystemAlwaysAtBottomDraft ? 'left-6' : 'left-1'"
                  />
                </div>
                <span class="min-w-[2.5rem] text-center text-xs text-muted">{{ groupSystemAlwaysAtBottomDraft ? '开启' : '关闭' }}</span>
              </button>
            </div>
          </div>
          <div class="form-group" :class="{ 'opacity-50 pointer-events-none': groupSystemAlwaysAtBottomDraft }">
            <label class="label">系统提示词注入深度</label>
            <input
              v-model.number="groupSystemInjectDepthDraft"
              type="number"
              class="input"
              min="0"
              step="1"
            />
            <div class="form-hint">整段 system 将插在倒数第 N 条消息（含世界书产生条目）之前；仅关闭「永远在底部」时生效。</div>
          </div>

          <div class="form-group surface-muted p-3 space-y-3">
            <div class="text-sm font-medium text-brand">MVU</div>
            <div class="flex items-start justify-between gap-3">
              <p class="min-w-0 flex-1 text-xs text-muted">启用后由锚定成员的状态栏与 MVU 模式（指令 / 正则）驱动；与会话设置抽屉写入同一套 overrides。</p>
              <button
                type="button"
                class="flex shrink-0 items-center gap-2"
                :aria-pressed="groupMvuEnabledDraft"
                @click="groupMvuEnabledDraft = !groupMvuEnabledDraft"
              >
                <div
                  class="w-10 h-5 rounded-full relative transition-colors duration-200"
                  :class="groupMvuEnabledDraft ? 'bg-brand' : 'bg-surface-muted'"
                >
                  <div
                    class="absolute top-1 w-3 h-3 rounded-full bg-[var(--color-text-primary)] transition-transform duration-200"
                    :class="groupMvuEnabledDraft ? 'left-6' : 'left-1'"
                  />
                </div>
                <span class="min-w-[2.5rem] text-center text-xs text-muted">{{ groupMvuEnabledDraft ? '开启' : '关闭' }}</span>
              </button>
            </div>
            <div v-if="groupMvuEnabledDraft" class="space-y-3">
              <div class="space-y-1.5">
                <label class="block text-xs text-muted">锚定成员（须在成员列表内）</label>
                <ModernSelect
                  :model-value="groupMvuAnchorDraft || ''"
                  @update:model-value="(v) => (groupMvuAnchorDraft = v || null)"
                  :options="groupMvuAnchorSelectOptions"
                  placeholder="选择成员"
                  class="w-full"
                />
              </div>
              <div class="space-y-1.5">
                <label class="block text-xs text-muted">模板成员（可选，仅作记录）</label>
                <ModernSelect
                  :model-value="groupMvuTemplateDraft || ''"
                  @update:model-value="(v) => (groupMvuTemplateDraft = v || null)"
                  :options="groupMvuTemplateSelectOptions"
                  placeholder="可选"
                  class="w-full"
                />
              </div>
              <MvuCapabilityEditor
                :mvu-mode="mvuModeDraft"
                :mvu-directive="mvuDirectiveDraft"
                :content-regex-rules="contentRegexRulesDraft"
                :initial-state-tables="stateTablesDraft"
                :allow-inherit="true"
                tables-empty-hint="暂无状态表格。点击「新建表格」开始配置。"
                @update:mvu-mode="(v) => (mvuModeDraft = v)"
                @update:mvu-directive="(v) => (mvuDirectiveDraft = v)"
                @update:content-regex-rules="(v) => (contentRegexRulesDraft = v)"
                @update:initial-state-tables="(v) => (stateTablesDraft = v)"
              />
            </div>
          </div>

          <!-- 成员列表与排序 -->
          <div class="form-group">
            <label class="label">成员与发言顺序</label>
            <div class="form-hint mb-3">拖动成员卡片可更改在“自动发言”模式下的发言顺序</div>
            
            <div class="space-y-2">
              <div 
                v-for="(id, idx) in memberIdsDraft" 
                :key="id"
                class="surface-muted interactive-surface flex items-center gap-3 p-3 group/item"
                :class="draggingIdx === idx ? 'surface-selected opacity-40 scale-95' : ''"
                draggable="true"
                @dragstart="handleDragStart(idx)"
                @dragover="handleDragOver($event, idx)"
                @dragend="handleDragEnd"
              >
                <!-- 拖动手柄 -->
                <div class="cursor-move text-muted px-1">
                  <GripVertical class="w-5 h-5" />
                </div>

                <!-- 序号 -->
                <div class="surface-inset w-6 h-6 rounded-full flex items-center justify-center text-2xs text-muted font-bold">
                  {{ idx + 1 }}
                </div>

                <!-- 头像 -->
                <ModernAvatar 
                  :src="getCharacter(id)?.avatar ? `/api/avatars/${getCharacter(id)?.avatar}` : null" 
                  :name="getCharacter(id)?.name || '未知'" 
                  :size="32" 
                  aspect="1" 
                  rounded="rounded-lg" 
                />

                <!-- 名称 -->
                <div class="flex-1 min-w-0">
                  <div class="font-medium text-sm text-primary truncate">{{ getCharacter(id)?.name || '未知角色' }}</div>
                  <div v-if="chat.memberSettings?.[id]?.probability !== undefined && chat.memberSettings[id].probability < 1" class="text-2xs text-warning">
                    参与概率: {{ Math.round(Number(chat.memberSettings?.[id]?.probability) * 100) }}%
                  </div>
                </div>

                <!-- 操作 -->
                <button 
                  class="btn btn-xs btn-ghost"
                  @click="emit('open-member-settings', id)"
                >
                  详情设置
                </button>
              </div>
            </div>
          </div>
        </div>

        <div class="modal-footer">
          <button type="button" class="btn btn-secondary" @click="close">取消</button>
          <button type="button" class="btn btn-primary" @click="save">保存并应用</button>
        </div>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.cursor-move {
  cursor: grab;
}
.cursor-move:active {
  cursor: grabbing;
}
</style>
