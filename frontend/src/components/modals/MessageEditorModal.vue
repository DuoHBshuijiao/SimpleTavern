<script setup lang="ts">
/**
 * MessageEditorModal - 消息编辑弹窗组件
 *
 * 组件职责：
 * - 提供消息编辑界面，允许修改消息角色和内容
 * - 支持选择消息发送者（系统/角色/用户）
 * - 支持保存或保存并发送（重新生成）
 *
 * Props说明：
 * - show: 是否显示弹窗（v-model:show）
 * - messageId: 消息ID
 * - messageRole: 消息角色（来自types/models.ts的ChatRole类型）
 * - messageContent: 消息内容（v-model:messageContent）
 * - characterAvatarUrl: 角色头像URL
 * - userAvatarUrl: 用户头像URL
 * - isGenerating: 是否正在生成
 *
 * Emits说明：
 * - update:show: 更新显示状态（v-model:show）
 * - update:messageRole: 更新消息角色（v-model:messageRole）
 * - update:messageContent: 更新消息内容（v-model:messageContent）
 * - save: 保存消息
 * - save-and-send: 保存并发送（重新生成）
 *
 * 使用的Composables：
 * 无
 *
 * 使用的Stores：
 * 无
 *
 * 文件关系：
 *    - 被导入：被views/ChatPage.vue使用
 *    - 导入：导入types/models.ts的ChatMessage类型、components/ModernAvatar.vue
 *    - 依赖：依赖vue
 *    - 位置：组件层，提供消息编辑功能
 */
import type { MainChatRole } from '../../types/models'
import ModernAvatar from '../ModernAvatar.vue'
import { Settings, X } from 'lucide-vue-next'
import { useDialogBehavior } from '../../composables/useDialogBehavior'
import { dialogAria } from '../../utils/uiPrimitives'

const props = defineProps<{
  show: boolean
  messageId: string | null
  messageRole: MainChatRole
  messageContent: string
  characterAvatarUrl: string | null
  userAvatarUrl: string | null
  isGenerating: boolean
}>()

const emit = defineEmits<{
  'update:show': [value: boolean]
  'update:messageRole': [role: MainChatRole]
  'update:messageContent': [content: string]
  'save': []
  'save-and-send': []
}>()

const titleId = 'message-editor-title'
const dialogAttrs = dialogAria(titleId)

function close() {
  emit('update:show', false)
}

function updateMessageContent(event: Event) {
  emit('update:messageContent', (event.target as HTMLTextAreaElement | null)?.value ?? '')
}

const { dialogRef } = useDialogBehavior(() => props.show, close)
void dialogRef
</script>

<template>
  <Transition name="modal">
    <div v-if="show" class="modal">
      <div class="modal-backdrop" @click="close"></div>
      <div ref="dialogRef" v-bind="dialogAttrs" tabindex="-1" class="modal-content modal-surface chat-modal-width-700-92">
        <div class="modal-header">
          <h3 :id="titleId" class="modal-title">编辑消息</h3>
          <button type="button" class="modal-close" aria-label="关闭编辑消息弹窗" @click="close">
              <X class="w-5 h-5" />
          </button>
        </div>
        <div class="modal-body p-6">
          <div class="space-y-6">
            <div class="form-group">
              <label class="label text-xs font-bold uppercase tracking-wider mb-2 block">发送者 / 头像</label>
              <div class="flex flex-wrap gap-3">
                <div 
                  class="surface-muted interactive-surface cursor-pointer p-2 px-4 flex items-center gap-2"
                  :class="messageRole === 'system' ? 'surface-selected' : ''"
                  @click="emit('update:messageRole', 'system')"
                >
                  <Settings class="w-4 h-4" :class="messageRole === 'system' ? 'text-brand-fg-soft' : 'text-[var(--color-text-muted)]'" />
                  <span class="text-sm font-medium" :class="messageRole === 'system' ? 'text-brand-light' : 'text-[var(--color-text-secondary)]'">系统</span>
                </div>
                <div 
                  class="surface-muted interactive-surface cursor-pointer p-2 px-4 flex items-center gap-2"
                  :class="messageRole === 'assistant' ? 'surface-selected' : ''"
                  @click="emit('update:messageRole', 'assistant')"
                >
                  <ModernAvatar :src="characterAvatarUrl" :size="20" aspect="1" rounded="rounded-sm" />
                  <span class="text-sm font-medium" :class="messageRole === 'assistant' ? 'text-brand-light' : 'text-[var(--color-text-secondary)]'">角色</span>
                </div>
                <div 
                  class="surface-muted interactive-surface cursor-pointer p-2 px-4 flex items-center gap-2"
                  :class="messageRole === 'user' ? 'surface-selected' : ''"
                  @click="emit('update:messageRole', 'user')"
                >
                  <ModernAvatar :src="userAvatarUrl" :size="20" aspect="1" rounded="rounded-sm" />
                  <span class="text-sm font-medium" :class="messageRole === 'user' ? 'text-brand-light' : 'text-[var(--color-text-secondary)]'">用户</span>
                </div>
              </div>
            </div>

            <div class="form-group">
              <label class="label text-xs font-bold uppercase tracking-wider mb-2 block">内容</label>
              <textarea
                :value="messageContent"
                @input="updateMessageContent"
                class="input textarea h-64 w-full resize-none custom-scrollbar leading-relaxed"
                placeholder="输入消息内容（支持 Markdown）"
              ></textarea>
            </div>
          </div>
        </div>
        <div class="modal-footer">
          <button type="button" class="btn btn-secondary min-w-[80px]" @click="close">取消</button>
          <button type="button" class="btn btn-secondary min-w-[80px]" :disabled="isGenerating" @click="emit('save')">仅保存</button>
          <button 
            type="button"
            class="btn btn-primary" 
            :disabled="isGenerating || messageRole === 'assistant'" 
            @click="emit('save-and-send')"
          >
            保存并发送
          </button>
        </div>
      </div>
    </div>
  </Transition>
</template>
