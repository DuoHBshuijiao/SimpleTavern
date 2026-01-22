<script setup lang="ts">
/**
 * ChatInput - 输入区域组件
 * 
 * 包含：消息输入框、模型选择、发送按钮、群聊状态显示、插话面板等
 */
import { computed } from 'vue'
import type { CharacterCard, GroupMemberSettings } from '../../types/models'
import ModernAvatar from '../ModernAvatar.vue'
import ModernSelect from '../ModernSelect.vue'

const props = defineProps<{
  // 输入状态
  modelValue: string
  isGenerating: boolean
  streamError: string | null
  
  // 群聊相关
  isGroup: boolean
  groupMembers: CharacterCard[]
  currentSpeakerIndex: number
  isPaused: boolean
  showContinueButton: boolean
  pendingMembersCount: number
  canInterject: boolean
  showInterjectPanel: boolean
  isInterjecting: boolean
  effectivePureAiMode: boolean
  isStreamingActive: boolean
  
  // 用户信息
  userAvatarUrl: string | null
  userName: string
  
  // 模型选择
  currentModel: string
  modelOptions: any[]
  
  // 辅助函数
  getMemberSettings: (memberId: string) => GroupMemberSettings
}>()

const emit = defineEmits<{
  'update:modelValue': [value: string]
  'send': []
  'primary-action': []
  'pause-group': []
  'continue-group': []
  'trigger-interject': [characterId: string]
  'hide-interject': []
  'select-model': [option: any]
  'toggle-assistant': []
}>()

// 计算属性
const hasDraftMessage = computed(() => !!props.modelValue.trim())

const primaryActionLabel = computed(() => {
  if (props.isStreamingActive) return '停止'
  if (props.showContinueButton && props.isGroup) {
    return hasDraftMessage.value ? '插话' : '继续轮次'
  }
  if (props.isGroup && !hasDraftMessage.value) {
    return '开始下一轮'
  }
  return props.isGenerating && !props.isPaused && !props.showContinueButton ? '生成中...' : '发送'
})

const primaryActionDisabled = computed(() => {
  if (props.isStreamingActive) return false
  if (props.showContinueButton && props.isGroup) return false
  if (props.isGroup && !hasDraftMessage.value) return props.isGenerating
  return !hasDraftMessage.value || (props.isGenerating && !props.isPaused && !props.showContinueButton)
})

const primaryActionClass = computed(() => {
  if (props.isStreamingActive) return 'chat-action-button--stop'
  if (props.showContinueButton && props.isGroup) {
    return hasDraftMessage.value ? 'chat-action-button--primary' : 'chat-action-button--continue'
  }
  if (props.isGroup && !hasDraftMessage.value) {
    return 'chat-action-button--next'
  }
  return 'chat-action-button--primary'
})

const inputPlaceholder = computed(() => {
  if (props.isGenerating && props.isGroup && !props.isPaused) {
    return '等待角色发言完成...'
  }
  if (props.showContinueButton) {
    return '输入消息插话，或点击继续轮次...'
  }
  return '发送消息...'
})

const inputDisabled = computed(() => {
  return props.isGenerating && !props.isPaused && !props.showContinueButton
})

function handleKeydown(e: KeyboardEvent) {
  if (e.ctrlKey && e.key === 'Enter') {
    emit('send')
  }
}
</script>

<template>
  <div class="shrink-0 p-4 pb-6 w-full max-w-4xl mx-auto z-20 relative overflow-visible">
    <div class="relative bg-[#18181c] border border-white/10 rounded-2xl shadow-xl p-3 flex flex-col gap-2 transition-colors focus-within:border-brand/40 focus-within:ring-1 focus-within:ring-brand/20">
      <textarea
        :value="modelValue"
        @input="emit('update:modelValue', ($event.target as HTMLTextAreaElement).value)"
        :placeholder="inputPlaceholder"
        :disabled="inputDisabled"
        class="input textarea !bg-transparent !border-0 text-base resize-none min-h-[80px]"
        :class="inputDisabled ? 'opacity-50' : ''"
        @keydown="handleKeydown"
      ></textarea>
      
      <div class="flex items-center justify-between pt-2 border-t border-white/5">
        <div class="flex-1 min-w-0">
          <!-- 群聊发言状态指示器 -->
          <div v-if="isGroup && isGenerating && currentSpeakerIndex >= 0" class="flex items-center gap-2 text-xs text-purple-400">
            <span class="animate-pulse">●</span>
            <span>{{ groupMembers[currentSpeakerIndex]?.name || '角色' }} 正在发言...</span>
            <span class="text-gray-500">({{ currentSpeakerIndex + 1 }}/{{ groupMembers.length }})</span>
            <button 
              class="ml-2 px-2 py-0.5 text-xs bg-yellow-500/20 hover:bg-yellow-500/30 text-yellow-400 rounded transition-colors"
              @click="emit('pause-group')"
            >
              暂停
            </button>
          </div>
          
          <!-- 继续轮次按钮 -->
          <div v-else-if="showContinueButton && pendingMembersCount > 0" class="flex items-center gap-2 text-xs text-green-400">
            <span>轮次已暂停，还有 {{ pendingMembersCount }} 位角色待发言</span>
            <button 
              class="px-3 py-1 text-xs bg-green-500/20 hover:bg-green-500/30 text-green-400 rounded transition-colors font-medium"
              @click="emit('continue-group')"
            >
              继续轮次
            </button>
          </div>
          
          <!-- 插话面板 -->
          <div v-else-if="canInterject && isGroup && !isInterjecting" class="flex items-center gap-2 text-xs">
            <span class="text-purple-400">💬 点击角色插话：</span>
            <div class="flex items-center gap-1">
              <div 
                v-for="member in groupMembers"
                :key="member.id"
                class="cursor-pointer hover:scale-110 transition-transform"
                :title="`让 ${member.name} 插话`"
                @click="emit('trigger-interject', member.id)"
              >
                <ModernAvatar 
                  :src="member.avatar ? `/api/avatars/${member.avatar}` : null" 
                  :name="member.name" 
                  :size="24" 
                  aspect="1"
                  rounded="rounded"
                  class="ring-2 ring-purple-500/50 hover:ring-purple-500"
                />
              </div>
            </div>
            <button 
              class="ml-2 px-2 py-0.5 text-xs bg-gray-500/20 hover:bg-gray-500/30 text-gray-400 rounded transition-colors"
              @click="emit('hide-interject')"
            >
              关闭
            </button>
          </div>
          
          <!-- 插话中状态 -->
          <div v-else-if="isInterjecting" class="flex items-center gap-2 text-xs text-purple-400">
            <span class="animate-pulse">●</span>
            <span>正在插话...</span>
          </div>
          
          <!-- 错误信息 -->
          <div v-else-if="streamError" class="text-xs text-red-400 truncate">{{ streamError }}</div>
        </div>
        
        <div class="flex items-center gap-3">
          <ModernSelect
            :model-value="currentModel"
            :options="modelOptions"
            placement="top"
            placeholder="选择模型 (自动关联预设)..."
            class="!w-[200px] !text-xs"
            dropdown-width="410"
            searchable
            allow-create
            @select="emit('select-model', $event)"
          />
          <button 
            class="chat-action-button"
            :class="primaryActionClass"
            :disabled="primaryActionDisabled"
            @click="emit('primary-action')"
          >
            {{ primaryActionLabel }}
          </button>
        </div>
      </div>
    </div>
    
    <div class="text-center mt-2 text-xs text-gray-600">
      Markdown 支持 · Ctrl + Enter 发送
    </div>
    
    <!-- 助理按钮 -->
    <button
      class="absolute -right-16 bottom-10 w-12 h-12 rounded-xl bg-[#b76e79] text-white font-bold shadow-lg shadow-[#b76e79]/30 hover:bg-[#c27a85] transition-colors border border-white/10"
      title="聊天助手"
      @click="emit('toggle-assistant')"
    >
      助理
    </button>
  </div>
</template>

<style scoped>
/* 组件特有样式，保持 scoped */
.textarea {
  scrollbar-width: none;
}
.textarea::-webkit-scrollbar {
  display: none;
}
</style>
