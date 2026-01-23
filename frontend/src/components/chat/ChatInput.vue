<script setup lang="ts">
/**
 * ChatInput - 聊天输入
 * 风格：Obsidian Brutalist (Command Line Style)
 */
import { computed } from 'vue'
import type { CharacterCard, GroupMemberSettings } from '../../types/models'
import ModernAvatar from '../ModernAvatar.vue'
import ModernSelect from '../ModernSelect.vue'

const props = defineProps<{
  modelValue: string
  isGenerating: boolean
  streamError: string | null
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
  userAvatarUrl: string | null
  userName: string
  currentModel: string
  modelOptions: any[]
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

const hasDraftMessage = computed(() => !!props.modelValue.trim())

const primaryActionLabel = computed(() => {
  if (props.isStreamingActive) return 'ABORT'
  if (props.showContinueButton && props.isGroup) return hasDraftMessage.value ? 'INTERJECT' : 'RESUME'
  if (props.isGroup && !hasDraftMessage.value) return 'NEXT ROUND'
  return props.isGenerating ? 'SYNCING...' : 'DISPATCH'
})

const primaryActionClass = computed(() => {
  if (props.isStreamingActive) return 'btn-danger'
  if (props.showContinueButton && props.isGroup) return hasDraftMessage.value ? 'btn-primary' : 'btn-accent'
  return 'btn-primary'
})

function handleKeydown(e: KeyboardEvent) {
  if (e.ctrlKey && e.key === 'Enter') emit('send')
}
</script>

<template>
  <div class="shrink-0 p-8 pt-0 w-full max-w-5xl mx-auto z-20 relative">
    <!-- Obsidian Input Container -->
    <div class="relative bg-dark-surface border border-strong transition-all focus-within:border-brand shadow-2xl">
      
      <!-- Status Line -->
      <div class="flex items-center px-4 py-2 border-b border-strong bg-dark-bg/50 overflow-hidden">
        <div v-if="isGroup && isGenerating && currentSpeakerIndex >= 0" class="flex items-center gap-3">
          <span class="w-1.5 h-1.5 bg-brand animate-pulse"></span>
          <span class="text-[8px] font-black uppercase text-brand tracking-widest">Active Node: {{ groupMembers[currentSpeakerIndex]?.name }}</span>
          <button class="text-[8px] font-black text-text-muted hover:text-warning underline" @click="emit('pause-group')">PAUSE_SEQUENCE</button>
        </div>
        <div v-else-if="showContinueButton && pendingMembersCount > 0" class="flex items-center gap-3">
          <span class="w-1.5 h-1.5 bg-success"></span>
          <span class="text-[8px] font-black uppercase text-success tracking-widest">Sequence Paused: {{ pendingMembersCount }} Nodes Remaining</span>
          <button class="text-[8px] font-black text-text-muted hover:text-success underline" @click="emit('continue-group')">RESUME_PROTOCOL</button>
        </div>
        <div v-else-if="streamError" class="text-[8px] font-black uppercase text-error tracking-widest truncate">SYNC_ERROR: {{ streamError }}</div>
        <div v-else class="text-[8px] font-black uppercase text-text-muted tracking-[0.3em]">Neural Link Established // Dispatch Ready</div>
      </div>

      <textarea
        :value="modelValue"
        @input="emit('update:modelValue', ($event.target as HTMLTextAreaElement).value)"
        placeholder="ENTER DATA FOR DISPATCH..."
        :disabled="isGenerating && !isPaused && !showContinueButton"
        class="w-full bg-transparent p-6 text-lg font-bold uppercase tracking-tight resize-none min-h-[120px] outline-none placeholder:text-text-muted/30"
        @keydown="handleKeydown"
      ></textarea>
      
      <!-- Bottom Control Bar -->
      <div class="flex items-center justify-between p-4 border-t border-strong bg-dark-bg/30">
        <div class="flex items-center gap-6">
          <ModernSelect
            :model-value="currentModel"
            :options="modelOptions"
            placement="top"
            searchable
            allow-create
            class="!w-[220px] !text-[9px] font-black border-none !bg-transparent"
            @select="emit('select-model', $event)"
          />
          
          <div v-if="canInterject && isGroup" class="flex items-center gap-2 border-l border-strong pl-6">
            <span class="text-[8px] font-black text-text-muted uppercase tracking-widest mr-2">Interject Node:</span>
            <div class="flex gap-1">
              <div v-for="m in groupMembers" :key="m.id" 
                class="w-6 h-6 border border-subtle hover:border-brand cursor-pointer transition-all"
                @click="emit('trigger-interject', m.id)"
              >
                <ModernAvatar :name="m.name" :src="m.avatar ? `/api/avatars/${m.avatar}` : null" :size="24" rounded="rounded-none" />
              </div>
            </div>
          </div>
        </div>

        <div class="flex items-center gap-4">
          <div class="hidden sm:flex flex-col items-end text-[8px] font-black text-text-muted uppercase tracking-widest pr-4 border-r border-strong leading-none">
            <span>Markdown Enabled</span>
            <span class="mt-1">Ctrl + Enter</span>
          </div>
          <button 
            class="btn px-12 py-3 text-[10px] tracking-[0.3em]"
            :class="primaryActionClass"
            :disabled="!hasDraftMessage && !isStreamingActive && !(isGroup && (showContinueButton || !isGenerating))"
            @click="emit('primary-action')"
          >
            {{ primaryActionLabel }}
          </button>
        </div>
      </div>
    </div>

    <!-- Floating Assistant Core -->
    <button
      class="absolute -right-20 bottom-12 w-12 h-12 bg-dark-bg border border-brand/50 flex flex-col items-center justify-center gap-1 group hover:bg-brand transition-all shadow-xl"
      @click="emit('toggle-assistant')"
    >
      <span class="text-[10px] font-black text-brand group-hover:text-text-inverse leading-none">A.I.</span>
      <div class="w-4 h-0.5 bg-brand group-hover:bg-text-inverse"></div>
    </button>
  </div>
</template>

<style scoped>
textarea { scrollbar-width: none; }
</style>
