<script setup lang="ts">
/**
 * MessageEditorModal - 消息编辑弹窗
 */
import type { ChatMessage } from '../../types/models'
import ModernAvatar from '../ModernAvatar.vue'

const props = defineProps<{
  show: boolean
  messageId: string | null
  messageRole: ChatMessage['role']
  messageContent: string
  characterAvatarUrl: string | null
  userAvatarUrl: string | null
  isGenerating: boolean
}>()

const emit = defineEmits<{
  'update:show': [value: boolean]
  'update:messageRole': [role: ChatMessage['role']]
  'update:messageContent': [content: string]
  'save': []
  'save-and-send': []
}>()
</script>

<template>
  <div v-if="show" class="modal">
    <div class="modal-backdrop" @click="emit('update:show', false)"></div>
    <div class="modal-content chat-modal-width-700-92">
      <div class="modal-header">
        <h3 class="modal-title">编辑消息</h3>
        <button class="modal-close" @click="emit('update:show', false)">×</button>
      </div>
      <div class="modal-body">
        <div class="space-y-6">
          <div class="form-group">
            <label class="label">发送者 / 头像</label>
            <div class="flex flex-wrap gap-3">
              <div 
                class="cursor-pointer border-2 rounded-xl p-1 px-3 flex items-center gap-2 transition-all"
                :class="messageRole === 'system' ? 'border-brand bg-brand/10' : 'border-transparent bg-white/5 hover:bg-white/10'"
                @click="emit('update:messageRole', 'system')"
              >
                <span class="text-lg">⚙</span>
                <span class="text-sm">系统</span>
              </div>
              <div 
                class="cursor-pointer border-2 rounded-xl p-1 px-3 flex items-center gap-2 transition-all"
                :class="messageRole === 'assistant' ? 'border-brand bg-brand/10' : 'border-transparent bg-white/5 hover:bg-white/10'"
                @click="emit('update:messageRole', 'assistant')"
              >
                <ModernAvatar :src="characterAvatarUrl" :size="24" aspect="1" rounded="rounded" />
                <span class="text-sm">角色</span>
              </div>
              <div 
                class="cursor-pointer border-2 rounded-xl p-1 px-3 flex items-center gap-2 transition-all"
                :class="messageRole === 'user' ? 'border-brand bg-brand/10' : 'border-transparent bg-white/5 hover:bg-white/10'"
                @click="emit('update:messageRole', 'user')"
              >
                <ModernAvatar :src="userAvatarUrl" :size="24" aspect="1" rounded="rounded" />
                <span class="text-sm">用户</span>
              </div>
            </div>
          </div>

          <div class="form-group">
            <label class="label">内容</label>
            <textarea
              :value="messageContent"
              @input="emit('update:messageContent', ($event.target as HTMLTextAreaElement).value)"
              class="input textarea h-64 !bg-black/20"
              placeholder="输入消息内容（支持 Markdown）"
            ></textarea>
          </div>
        </div>
      </div>
      <div class="modal-footer">
        <button class="btn btn-secondary" @click="emit('update:show', false)">取消</button>
        <button class="btn btn-secondary" :disabled="isGenerating" @click="emit('save')">保存</button>
        <button 
          class="btn btn-primary" 
          :disabled="isGenerating || messageRole === 'assistant'" 
          @click="emit('save-and-send')"
        >
          保存并发送
        </button>
      </div>
    </div>
  </div>
</template>
