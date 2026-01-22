<script setup lang="ts">
/**
 * GroupSettingsModal - 群聊设置弹窗
 * 
 * 管理群成员列表、发言顺序、群聊延迟等
 */
import { ref, watch } from 'vue'
import type { Chat, CharacterCard } from '../../types/models'
import ModernAvatar from '../ModernAvatar.vue'

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

function getCharacter(id: string) {
  return props.characters.find(c => c.id === id)
}

function handleDragStart(idx: number) {
  draggingIdx.value = idx
}

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

function handleDragEnd() {
  draggingIdx.value = null
}

function close() {
  emit('update:show', false)
}

function save() {
  emit('update:member-ids', memberIdsDraft.value)
  emit('update:group-delay', groupDelayDraft.value)
  emit('save')
}
</script>

<template>
  <div v-if="show && chat" class="modal">
    <div class="modal-backdrop" @click="close"></div>
    <div class="modal-content chat-modal-width-600-90">
      <div class="modal-header">
        <h3 class="modal-title">群聊设置 - {{ chat.title }}</h3>
        <button class="modal-close" @click="close">×</button>
      </div>
      
      <div class="modal-body space-y-6">
        <!-- 群聊发言延迟 -->
        <div class="form-group">
          <label class="label text-purple-400">发言延迟 (ms)</label>
          <input 
            v-model.number="groupDelayDraft"
            type="number"
            class="input"
            step="100"
            min="0"
          />
          <div class="form-hint">角色连续发言之间的间隔时间</div>
        </div>

        <!-- 成员列表与排序 -->
        <div class="form-group">
          <label class="label text-purple-400">成员与发言顺序</label>
          <div class="form-hint mb-3">拖动成员卡片可更改在“自动发言”模式下的发言顺序</div>
          
          <div class="space-y-2">
            <div 
              v-for="(id, idx) in memberIdsDraft" 
              :key="id"
              class="flex items-center gap-3 bg-white/5 p-3 rounded-xl border border-white/5 transition-all group/item"
              :class="draggingIdx === idx ? 'opacity-40 scale-95 border-brand/50' : 'hover:border-white/20'"
              draggable="true"
              @dragstart="handleDragStart(idx)"
              @dragover="handleDragOver($event, idx)"
              @dragend="handleDragEnd"
            >
              <!-- 拖动手柄 -->
              <div class="cursor-move text-gray-600 hover:text-gray-400 px-1">
                <span class="text-xl">⋮⋮</span>
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
        <button class="btn btn-secondary" @click="close">取消</button>
        <button class="btn btn-primary" @click="save">保存并应用</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.cursor-move {
  cursor: grab;
}
.cursor-move:active {
  cursor: grabbing;
}
</style>
