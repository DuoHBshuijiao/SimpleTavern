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
 * - update:member-ids: 更新成员ID列表（拖拽排序后）
 * - update:group-delay: 更新群聊延迟时间
 * - open-member-settings: 打开成员设置编辑，传递成员ID
 * - save: 保存设置
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
import { ref, watch } from 'vue'
import type { Chat, CharacterCard } from '../../types/models'
import ModernAvatar from '../ModernAvatar.vue'
import { GripVertical, X } from 'lucide-vue-next'

const props = defineProps<{
  show: boolean
  chat: Chat | null
  characters: CharacterCard[]
}>()

const emit = defineEmits<{
  'update:show': [value: boolean]
  'update:member-ids': [memberIds: string[]]
  'update:group-delay': [delay: number]
  'open-member-settings': [memberId: string]
  'save': []
}>()

const memberIdsDraft = ref<string[]>([])
const groupDelayDraft = ref<number>(1500)
const draggingIdx = ref<number | null>(null)

watch(() => props.show, (val) => {
  if (val && props.chat) {
    memberIdsDraft.value = [...props.chat.memberIds]
    groupDelayDraft.value = props.chat.groupDelay || 1500
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
 * 保存设置
 *
 * 触发update:member-ids和update:group-delay事件，然后触发save事件。
 */
function save() {
  emit('update:member-ids', memberIdsDraft.value)
  emit('update:group-delay', groupDelayDraft.value)
  emit('save')
}
</script>

<template>
  <Transition name="modal">
    <div v-if="show && chat" class="modal">
      <div class="modal-backdrop" @click="close"></div>
      <div class="modal-content chat-modal-width-600-90 glass-panel bg-gradient-to-br from-slate-900/30 to-slate-800/25 backdrop-blur-2xl backdrop-saturate-[1.8] border border-white/10">
        <div class="modal-header">
          <h3 class="modal-title text-slate-50">群聊设置 - {{ chat.title }}</h3>
          <button class="modal-close" @click="close">
              <X class="w-5 h-5" />
          </button>
        </div>
        
        <div class="modal-body space-y-6">
          <!-- 群聊发言延迟 -->
          <div class="form-group">
            <label class="label text-brand-light">发言延迟 (ms)</label>
            <input 
              v-model.number="groupDelayDraft"
              type="number"
              class="input bg-white/5 border-white/10 focus:border-brand-a50"
              step="100"
              min="0"
            />
            <div class="form-hint">角色连续发言之间的间隔时间</div>
          </div>

          <!-- 成员列表与排序 -->
          <div class="form-group">
            <label class="label text-brand-light">成员与发言顺序</label>
            <div class="form-hint mb-3">拖动成员卡片可更改在“自动发言”模式下的发言顺序</div>
            
            <div class="space-y-2">
              <div 
                v-for="(id, idx) in memberIdsDraft" 
                :key="id"
                class="flex items-center gap-3 p-3 rounded-xl border transition-all group/item"
                :class="draggingIdx === idx ? 'bg-brand-a10 border-brand-a50 opacity-40 scale-95' : 'bg-white/5 border-white/5 hover:bg-white/10 hover:border-white/20'"
                draggable="true"
                @dragstart="handleDragStart(idx)"
                @dragover="handleDragOver($event, idx)"
                @dragend="handleDragEnd"
              >
                <!-- 拖动手柄 -->
                <div class="cursor-move text-gray-600 hover:text-gray-400 px-1">
                  <GripVertical class="w-5 h-5" />
                </div>

                <!-- 序号 -->
                <div class="w-6 h-6 rounded-full bg-black/40 flex items-center justify-center text-[10px] text-gray-500 font-bold">
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
                  <div class="font-medium text-sm text-gray-200 truncate">{{ getCharacter(id)?.name || '未知角色' }}</div>
                  <div v-if="chat.memberSettings?.[id]?.probability !== undefined && chat.memberSettings[id].probability < 1" class="text-[10px] text-yellow-500/80">
                    参与概率: {{ Math.round(chat.memberSettings![id]!.probability * 100) }}%
                  </div>
                </div>

                <!-- 操作 -->
                <button 
                  class="text-xs text-brand hover:text-brand-hover px-2 py-1"
                  @click="emit('open-member-settings', id)"
                >
                  详情设置
                </button>
              </div>
            </div>
          </div>
        </div>

        <div class="modal-footer">
          <button class="btn btn-secondary bg-white/5 hover:bg-white/10 text-gray-300 border border-white/5" @click="close">取消</button>
          <button class="btn btn-primary" @click="save">保存并应用</button>
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
