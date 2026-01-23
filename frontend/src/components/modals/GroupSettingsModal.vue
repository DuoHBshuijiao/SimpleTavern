<script setup lang="ts">
/**
 * GroupSettingsModal - 群聊设置弹窗组件
 * 风格：Swiss Modernism 2.0
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
  <div v-if="show && chat" class="modal-overlay">
    <div class="modal-backdrop" @click="close"></div>
    <div class="modal-container max-w-2xl h-[80vh] flex flex-col">
      <div class="modal-header">
        <h3 class="modal-title">Group Protocol Settings</h3>
        <button class="modal-close" @click="close">✕</button>
      </div>
      
      <div class="modal-content flex-1 overflow-y-auto custom-scrollbar space-y-8">
        <!-- 群聊发言延迟 -->
        <div class="form-group">
          <label class="label text-brand">Auto-Reply Delay (ms)</label>
          <input 
            v-model.number="groupDelayDraft"
            type="number"
            class="input font-mono text-xl"
            step="100"
            min="0"
          />
          <div class="form-hint uppercase text-[10px] tracking-widest mt-2">Interval between character messages</div>
        </div>

        <!-- 成员列表与排序 -->
        <div class="form-group">
          <label class="label text-brand">Members & Speaking Order</label>
          <div class="form-hint mb-4 uppercase text-[10px] tracking-widest">Drag to reorder speaking queue</div>
          
          <div class="space-y-1">
            <div 
              v-for="(id, idx) in memberIdsDraft" 
              :key="id"
              class="flex items-center gap-4 bg-surface p-4 rounded-sm border border-subtle transition-all group/item"
              :class="draggingIdx === idx ? 'opacity-20 scale-95 border-brand' : 'hover:border-strong'"
              draggable="true"
              @dragstart="handleDragStart(idx)"
              @dragover="handleDragOver($event, idx)"
              @dragend="handleDragEnd"
            >
              <!-- 拖动手柄 -->
              <div class="cursor-move text-text-muted hover:text-brand transition-colors px-1">
                <span class="text-xl font-bold">::</span>
              </div>

              <!-- 序号 -->
              <div class="w-8 h-8 rounded-sm bg-dark-bg flex items-center justify-center text-xs text-text-muted font-black border border-subtle">
                {{ String(idx + 1).padStart(2, '0') }}
              </div>

              <!-- 头像 -->
              <ModernAvatar 
                :src="getCharacter(id)?.avatar ? `/api/avatars/${getCharacter(id)?.avatar}` : null" 
                :name="getCharacter(id)?.name || '?'" 
                :size="40" 
                aspect="1" 
                rounded="rounded-sm" 
                class="bg-black/20"
              />

              <!-- 名称 -->
              <div class="flex-1 min-w-0">
                <div class="font-black text-sm text-text-primary truncate uppercase tracking-tight">{{ getCharacter(id)?.name || 'Unknown' }}</div>
                <div v-if="chat.memberSettings?.[id]?.probability !== undefined && chat.memberSettings[id].probability < 1" class="text-[10px] text-accent font-bold uppercase tracking-widest">
                  Probability: {{ Math.round(chat.memberSettings![id]!.probability * 100) }}%
                </div>
              </div>

              <!-- 操作 -->
              <button 
                class="text-[10px] font-black text-brand hover:underline px-2 py-1 uppercase tracking-widest"
                @click="emit('open-member-settings', id)"
              >
                Settings
              </button>
            </div>
          </div>
        </div>
      </div>

      <div class="modal-footer">
        <button class="btn btn-secondary font-bold uppercase tracking-widest text-[10px]" @click="close">Cancel</button>
        <button class="btn btn-primary font-bold uppercase tracking-widest text-[10px] px-8" @click="save">Save & Apply</button>
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
