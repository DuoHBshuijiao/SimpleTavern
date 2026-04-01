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
</script>

<template>
  <Transition name="modal">
    <div v-if="show" class="modal">
      <div class="modal-backdrop" @click="emit('update:show', false)"></div>
      <div class="modal-content chat-modal-width-700-92 bg-gradient-to-br from-slate-800/70 to-slate-700/50 backdrop-blur-xl backdrop-saturate-[1.8] border border-white/10 shadow-glass-panel">
        <div class="modal-header border-b border-white/5">
          <h3 class="modal-title text-gray-100 font-semibold tracking-wide">编辑消息</h3>
          <button class="modal-close text-gray-400 hover:text-white transition-colors p-1 rounded-lg hover:bg-white/10" @click="emit('update:show', false)">
              <X class="w-5 h-5" />
          </button>
        </div>
        <div class="modal-body p-6">
          <div class="space-y-6">
            <div class="form-group">
              <label class="label text-xs font-bold text-gray-400 uppercase tracking-wider mb-2 block">发送者 / 头像</label>
              <div class="flex flex-wrap gap-3">
                <div 
                  class="cursor-pointer border rounded-xl p-2 px-4 flex items-center gap-2 transition-all duration-200"
                  :class="messageRole === 'system' ? 'border-brand bg-brand-a20 shadow-sm shadow-brand' : 'border-white/10 bg-white/5 hover:bg-white/10 hover:border-white/20'"
                  @click="emit('update:messageRole', 'system')"
                >
                  <Settings class="w-4 h-4" :class="messageRole === 'system' ? 'text-brand-fg-soft' : 'text-[var(--color-text-muted)]'" />
                  <span class="text-sm font-medium" :class="messageRole === 'system' ? 'text-brand-light' : 'text-[var(--color-text-secondary)]'">系统</span>
                </div>
                <div 
                  class="cursor-pointer border rounded-xl p-2 px-4 flex items-center gap-2 transition-all duration-200"
                  :class="messageRole === 'assistant' ? 'border-brand bg-brand-a20 shadow-sm shadow-brand' : 'border-white/10 bg-white/5 hover:bg-white/10 hover:border-white/20'"
                  @click="emit('update:messageRole', 'assistant')"
                >
                  <ModernAvatar :src="characterAvatarUrl" :size="20" aspect="1" rounded="rounded-sm" />
                  <span class="text-sm font-medium" :class="messageRole === 'assistant' ? 'text-brand-light' : 'text-[var(--color-text-secondary)]'">角色</span>
                </div>
                <div 
                  class="cursor-pointer border rounded-xl p-2 px-4 flex items-center gap-2 transition-all duration-200"
                  :class="messageRole === 'user' ? 'border-brand bg-brand-a20 shadow-sm shadow-brand' : 'border-white/10 bg-white/5 hover:bg-white/10 hover:border-white/20'"
                  @click="emit('update:messageRole', 'user')"
                >
                  <ModernAvatar :src="userAvatarUrl" :size="20" aspect="1" rounded="rounded-sm" />
                  <span class="text-sm font-medium" :class="messageRole === 'user' ? 'text-brand-light' : 'text-[var(--color-text-secondary)]'">用户</span>
                </div>
              </div>
            </div>

            <div class="form-group">
              <label class="label text-xs font-bold text-gray-400 uppercase tracking-wider mb-2 block">内容</label>
              <textarea
                :value="messageContent"
                @input="emit('update:messageContent', ($event.target as HTMLTextAreaElement).value)"
                class="input textarea h-64 w-full rounded-xl p-4 bg-black/20 border border-white/10 focus:border-brand-a50 text-gray-200 placeholder-gray-500/50 resize-none outline-none transition-all custom-scrollbar leading-relaxed"
                placeholder="输入消息内容（支持 Markdown）"
              ></textarea>
            </div>
          </div>
        </div>
        <div class="modal-footer p-4 border-t border-white/5 bg-black/20 flex justify-end gap-3">
          <button class="px-4 py-2 rounded-xl text-sm font-medium bg-white/5 hover:bg-white/10 text-gray-300 border border-white/5 transition-all whitespace-nowrap min-w-[80px]" @click="emit('update:show', false)">取消</button>
          <button class="px-4 py-2 rounded-xl text-sm font-medium bg-white/5 hover:bg-white/10 text-gray-300 border border-white/5 transition-all whitespace-nowrap min-w-[80px]" :disabled="isGenerating" @click="emit('save')">仅保存</button>
          <button 
            class="px-4 py-2 rounded-xl text-sm font-medium bg-brand hover:bg-brand-hover text-on-brand shadow-brand border border-brand-a20 transition-all flex items-center gap-2 whitespace-nowrap" 
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
