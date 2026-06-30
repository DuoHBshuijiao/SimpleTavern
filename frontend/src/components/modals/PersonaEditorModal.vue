<script setup lang="ts">
import { X } from 'lucide-vue-next'
import type { UserPersona } from '../../types/models'
import ModernAvatar from '../ModernAvatar.vue'
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
  <div v-if="show" class="modal">
    <div class="modal-backdrop" @click="emit('cancel')"></div>
    <div ref="dialogRef" v-bind="dialogAttrs" tabindex="-1" class="modal-content modal-surface chat-modal-width-500-90">
      <div class="modal-header">
        <h3 :id="titleId" class="modal-title">{{ isNewPersona ? '新建身份' : '编辑身份' }}</h3>
        <button type="button" class="modal-close" aria-label="关闭身份编辑弹窗" @click="emit('cancel')">
          <X class="w-5 h-5" />
        </button>
      </div>
      <div class="modal-body">
        <div v-if="persona" class="space-y-6">
          <div class="flex items-center gap-4 mb-2">
            <ModernAvatar
              :src="avatarUrl"
              :size="80"
              aspect="1"
              rounded="rounded-xl"
              class="border-2 border-brand-a40"
            />
            <button class="btn btn-sm btn-secondary" @click="emit('open-avatar-cropper')">更换头像</button>
          </div>

          <div class="form-group">
            <label class="label">姓名（{{ userName }}）</label>
            <input v-model="persona.name" class="input" placeholder="你的角色名称" />
          </div>

          <div class="form-group">
            <label class="label">简介</label>
            <textarea
              v-model="persona.description"
              class="input textarea h-32"
              placeholder="你的角色身份、背景等"
            ></textarea>
          </div>
        </div>
      </div>
      <div class="modal-footer">
        <button class="btn btn-secondary" @click="emit('cancel')">取消</button>
        <button class="btn btn-primary" @click="emit('save')">保存</button>
      </div>
    </div>
  </div>
</template>
