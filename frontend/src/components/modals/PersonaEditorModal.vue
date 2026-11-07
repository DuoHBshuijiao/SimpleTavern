<script setup lang="ts">
import { X } from 'lucide-vue-next'
import type { UserPersona } from '../../types/models'
import ModernAvatar from '../ModernAvatar.vue'
import SettingsField from '../settings-drawer/SettingsField.vue'
import { useDialogBehavior } from '../../composables/useDialogBehavior'
import { dialogAria } from '../../utils/uiPrimitives'

const props = defineProps<{
  show: boolean
  isNewPersona: boolean
  persona: UserPersona | null
  avatarUrl: string | null
  userName: string
}>()

const emit = defineEmits<{
  cancel: []
  save: []
  'open-avatar-cropper': []
}>()

const titleId = 'persona-editor-title'
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
      <div ref="dialogRef" v-bind="dialogAttrs" tabindex="-1" class="modal-content modal-surface chat-modal-width-500-90">
        <div class="modal-header">
          <h3 :id="titleId" class="modal-title">{{ isNewPersona ? '新建身份' : '编辑身份' }}</h3>
          <button type="button" class="modal-close" aria-label="关闭身份编辑弹窗" @click="emit('cancel')">
            <X class="w-5 h-5" />
          </button>
        </div>
        <div class="modal-body">
          <div v-if="persona" class="settings-group">
            <div class="flex items-center gap-4">
              <ModernAvatar
                :src="avatarUrl"
                :size="80"
                aspect="1"
                rounded="rounded-xl"
              />
              <button type="button" class="btn btn-sm btn-secondary" @click="emit('open-avatar-cropper')">更换头像</button>
            </div>
            <SettingsField :label="`姓名（${userName}）`">
              <input v-model="persona.name" class="input w-full" placeholder="你的角色名称" />
            </SettingsField>
            <SettingsField label="简介">
              <textarea
                v-model="persona.description"
                class="input textarea h-32 w-full"
                placeholder="你的角色身份、背景等"
              ></textarea>
            </SettingsField>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-secondary" @click="emit('cancel')">取消</button>
          <button class="btn btn-primary" @click="emit('save')">保存</button>
        </div>
      </div>
    </div>
  </Transition>
</template>
