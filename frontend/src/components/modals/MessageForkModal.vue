<script setup lang="ts">
import { ref, watch } from 'vue'
import { X } from 'lucide-vue-next'

const show = defineModel<boolean>('show', { default: false })

const props = defineProps<{
  messagePreview: string
  defaultTitle: string
  isSubmitting?: boolean
}>()

const emit = defineEmits<{
  confirm: [newChatName: string]
}>()

const nameDraft = ref('')

watch(show, (open) => {
  if (open) nameDraft.value = ''
})

function onConfirm() {
  if (props.isSubmitting) return
  emit('confirm', nameDraft.value.trim())
}

function onClose() {
  if (props.isSubmitting) return
  show.value = false
}
</script>

<template>
  <Transition name="modal">
    <div v-if="show" class="modal">
      <div class="modal-backdrop" @click="onClose"></div>
      <div
        class="modal-content chat-modal-width-700-92 bg-gradient-to-br from-slate-800/70 to-slate-700/50 backdrop-blur-xl backdrop-saturate-[1.8] border border-white/10 shadow-glass-panel"
      >
        <div class="modal-header border-b border-white/5">
          <h3 class="modal-title text-gray-100 font-semibold tracking-wide">从此处分叉到新会话</h3>
          <button
            type="button"
            class="modal-close text-gray-400 hover:text-white transition-colors p-1 rounded-lg hover:bg-white/10"
            aria-label="关闭"
            @click="onClose"
          >
            <X class="w-5 h-5" />
          </button>
        </div>
        <div class="modal-body p-6 space-y-4">
          <p class="text-sm text-[var(--color-text-secondary)]">
            将复制该消息及之前的全部对话到新会话；源会话不受影响。
          </p>
          <div class="rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-[var(--color-text-muted)] line-clamp-3">
            {{ messagePreview }}
          </div>
          <div class="form-group">
            <label class="label text-xs font-bold text-gray-400 uppercase tracking-wider mb-2 block">
              新会话名称（可选）
            </label>
            <input
              v-model="nameDraft"
              type="text"
              class="input w-full bg-surface-overlay border border-white/10 rounded-lg px-3 py-2 text-sm text-[var(--color-text)]"
              :placeholder="defaultTitle"
              :disabled="isSubmitting"
              @keyup.enter="onConfirm"
            />
          </div>
        </div>
        <div class="modal-footer border-t border-white/5 flex justify-end gap-2 p-4">
          <button
            type="button"
            class="btn btn-secondary"
            :disabled="isSubmitting"
            @click="onClose"
          >
            取消
          </button>
          <button
            type="button"
            class="btn btn-primary"
            :disabled="isSubmitting"
            @click="onConfirm"
          >
            {{ isSubmitting ? '创建中…' : '确认分叉' }}
          </button>
        </div>
      </div>
    </div>
  </Transition>
</template>
