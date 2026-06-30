<script setup lang="ts">
import ModernSelect from '../ModernSelect.vue'
import ThemedCheckbox from '../ThemedCheckbox.vue'
import { useDialogBehavior } from '../../composables/useDialogBehavior'
import { dialogAria } from '../../utils/uiPrimitives'
import type { SillyTavernImportPreview } from '../../composables/useSettingsImport'
import type { EmbeddedCharacterCardPreview } from '../../composables/useEmbeddedAvatarImport'
import type { MvuMode } from '../../types/models'

const props = defineProps<{
  show: boolean
  embeddedCardPreview: EmbeddedCharacterCardPreview | null
  stPreview: SillyTavernImportPreview | null
  stExpiresAt: string
  enableMvu: boolean
  mvuMode: MvuMode
  mvuModeOptions: ReadonlyArray<{ label: string; value: string }>
  detectedMvu: boolean
  importing: boolean
  confirmLabel: string
}>()

const emit = defineEmits<{
  cancel: []
  confirm: []
  'update:enableMvu': [value: boolean]
  'update:mvuMode': [value: string]
}>()

const titleId = 'embedded-card-confirm-title'
const dialogAttrs = dialogAria(titleId)
const { dialogRef } = useDialogBehavior(
  () => props.show,
  () => emit('cancel'),
)
void dialogRef

const characterName = () =>
  props.stPreview?.characterName || props.embeddedCardPreview?.card?.name || '未命名角色'

const hasWorldbook = () =>
  Boolean(
    props.embeddedCardPreview?.worldbook
    || (props.stPreview && props.stPreview.worldBookEntryCount > 0),
  )
</script>

<template>
  <div v-if="show" class="modal">
    <div class="modal-backdrop" @click="emit('cancel')"></div>
    <div ref="dialogRef" v-bind="dialogAttrs" tabindex="-1" class="modal-content modal-surface chat-modal-width-568-90 min-w-0">
      <div class="modal-header border-b border-[var(--color-border-subtle)]">
        <h3 :id="titleId" class="modal-title text-[var(--color-text)]">检测到 PNG 内嵌角色卡</h3>
        <button type="button" class="modal-close" aria-label="关闭 PNG 内嵌角色卡确认弹窗" @click="emit('cancel')">×</button>
      </div>
      <div class="modal-body max-h-[min(70vh,520px)] overflow-y-auto pr-1 space-y-3">
        <div class="rounded-xl border border-[var(--color-border-subtle)] bg-[var(--color-surface-muted)] p-4 text-sm text-[var(--color-text-secondary)] space-y-2">
          <p>是否用内嵌角色数据覆盖当前编辑内容？</p>
          <p class="text-xs text-[var(--color-text-muted)]">
            确认后将覆盖简介、Personality、Scenario、首句、示例对话、系统提示词、额外首句与 MVU 相关字段，并重置世界书绑定为内嵌角色卡对应世界书（若存在）；当前上传图片会保留为头像。
          </p>
          <p class="text-xs text-[var(--color-text-muted)]">
            检测结果：角色名「{{ characterName() }}」，
            世界书：{{ hasWorldbook() ? '有（将新建并绑定）' : '无（将清空绑定）' }}。
          </p>
        </div>
        <div
          v-if="stPreview"
          class="rounded-xl border border-[var(--color-border-subtle)] bg-[var(--color-surface-overlay)] p-4 text-xs text-[var(--color-text-muted)] space-y-2"
        >
          <div class="text-[var(--color-text-secondary)]">SillyTavern / MVU 预览</div>
          <div class="grid grid-cols-1 gap-2 sm:grid-cols-2">
            <div>世界书条目：<span class="text-[var(--color-text)]">{{ stPreview.worldBookEntryCount }}</span></div>
            <div>tavern_helper：<span class="text-[var(--color-text)]">{{ stPreview.mvu.hasTavernHelper ? '已检测到' : '未检测到' }}</span></div>
            <div>regex_scripts：<span class="text-[var(--color-text)]">{{ stPreview.mvu.regexScriptCount }}</span></div>
          </div>
          <label class="flex items-center gap-2">
            <ThemedCheckbox :checked="enableMvu" @update:checked="emit('update:enableMvu', $event)" />
            启用 MVU 兼容
            <span v-if="detectedMvu" class="text-[var(--color-text-secondary)]">已检测到候选结构</span>
          </label>
          <p class="text-[var(--color-text-muted)]">
            指令模式会把完整 ST 卡上下文交给 MVU Agent，生成角色卡 MVU 指令与初始状态栏后再合并到当前编辑内容。
          </p>
          <div>
            <div class="mb-1 text-[var(--color-text-muted)]">MVU 模式</div>
            <ModernSelect
              :model-value="mvuMode"
              :options="[...mvuModeOptions]"
              placeholder="选择 MVU 模式"
              @update:model-value="emit('update:mvuMode', $event)"
            />
          </div>
          <p v-if="stExpiresAt" class="text-[var(--color-text-muted)]">预览暂存至：{{ stExpiresAt }}</p>
        </div>
      </div>
      <div class="modal-footer">
        <button class="btn btn-secondary" :disabled="importing" @click="emit('cancel')">仅使用头像</button>
        <button class="btn btn-primary" :disabled="importing" @click="emit('confirm')">
          {{ confirmLabel }}
        </button>
      </div>
    </div>
  </div>
</template>
