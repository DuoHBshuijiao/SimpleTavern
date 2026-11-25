<script setup lang="ts">
import { X } from 'lucide-vue-next'
import { useDialogBehavior } from '../../composables/useDialogBehavior'
import { dialogAria } from '../../utils/uiPrimitives'

const props = defineProps<{
  show: boolean
}>()

const emit = defineEmits<{
  cancel: []
  'continue-chat': []
  'new-session': []
}>()

const titleId = 'persona-switch-title'
const dialogAttrs = dialogAria(titleId)
const { dialogRef } = useDialogBehavior(
  () => props.show,
  () => emit('cancel'),
)
void dialogRef
</script>

<template>
  <Transition name="modal">
  <div v-if="show" class="modal">
    <div class="modal-backdrop backdrop-blur-[var(--glass-blur-soft)]" @click="emit('cancel')"></div>
    <div ref="dialogRef" v-bind="dialogAttrs" tabindex="-1" class="modal-content modal-surface chat-modal-width-520-92">
      <div class="modal-header">
        <h3 :id="titleId" class="modal-title">切换用户身份</h3>
        <button type="button" class="modal-close" aria-label="关闭身份切换确认弹窗" @click="emit('cancel')">
          <X class="w-5 h-5" />
        </button>
      </div>
      <div class="modal-body">
        <p class="text-sm text-[var(--color-text-secondary)]">继续对话时，接下来发送的消息使用新身份，历史消息保留原身份。</p>
      </div>
      <div class="modal-footer">
        <button class="btn btn-secondary" @click="emit('cancel')">取消</button>
        <button class="btn btn-secondary" @click="emit('continue-chat')">继续对话</button>
        <button class="btn btn-primary" @click="emit('new-session')">新建会话</button>
      </div>
    </div>
  </div>
  </Transition>
</template>
