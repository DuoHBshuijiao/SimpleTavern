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
import type { ChatMessage } from '../../types/models'
import ModernAvatar from '../ModernAvatar.vue'
import { Settings, X } from 'lucide-vue-next'

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
  <Transition name="modal">
    <div v-if="show" class="modal">
      <div class="modal-backdrop" @click="emit('update:show', false)"></div>
      <div class="modal-content chat-modal-width-700-92 glass-panel">
        <div class="modal-header">
          <h3 class="modal-title text-slate-50">编辑消息</h3>
          <button class="modal-close" @click="emit('update:show', false)">
              <X class="w-5 h-5" />
          </button>
        </div>
        <div class="modal-body">
          <div class="space-y-6">
            <div class="form-group">
              <label class="label">发送者 / 头像</label>
              <div class="flex flex-wrap gap-3">
                <div 
                  class="cursor-pointer border rounded-xl p-1 px-3 flex items-center gap-2 transition-all"
                  :class="messageRole === 'system' ? 'border-brand bg-brand/10' : 'border-transparent bg-white/5 hover:bg-white/10'"
                  @click="emit('update:messageRole', 'system')"
                >
                  <Settings class="w-5 h-5" />
                  <span class="text-sm">系统</span>
                </div>
                <div 
                  class="cursor-pointer border rounded-xl p-1 px-3 flex items-center gap-2 transition-all"
                  :class="messageRole === 'assistant' ? 'border-brand bg-brand/10' : 'border-transparent bg-white/5 hover:bg-white/10'"
                  @click="emit('update:messageRole', 'assistant')"
                >
                  <ModernAvatar :src="characterAvatarUrl" :size="24" aspect="1" rounded="rounded" />
                  <span class="text-sm">角色</span>
                </div>
                <div 
                  class="cursor-pointer border rounded-xl p-1 px-3 flex items-center gap-2 transition-all"
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
                class="input textarea h-64 !bg-black/20 !border-white/10 focus:!border-brand/50"
                placeholder="输入消息内容（支持 Markdown）"
              ></textarea>
            </div>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-secondary bg-white/5 hover:bg-white/10 text-gray-300 border border-white/5" @click="emit('update:show', false)">取消</button>
          <button class="btn btn-secondary bg-white/5 hover:bg-white/10 text-gray-300 border border-white/5" :disabled="isGenerating" @click="emit('save')">保存</button>
          <button 
            class="btn btn-primary bg-brand hover:bg-brand-hover text-white shadow-lg shadow-brand/20" 
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
