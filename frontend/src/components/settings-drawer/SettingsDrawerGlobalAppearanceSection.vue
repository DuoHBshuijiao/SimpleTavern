<script setup lang="ts">
import { ref } from 'vue'
import ModernSelect from '../ModernSelect.vue'
import ThemedCheckbox from '../ThemedCheckbox.vue'
import SettingsDrawerGlobalAccordion from './SettingsDrawerGlobalAccordion.vue'
import SettingsField from './SettingsField.vue'
import SettingsHint from './SettingsHint.vue'
import SettingsSwitch from './SettingsSwitch.vue'
import { THEME_OPTIONS, type MvuMode, type Settings } from '../../types/models'
import type { SillyTavernImportPreview } from '../../composables/useSettingsImport'
import type { CSSProperties } from 'vue'

type WebgpuPreset = NonNullable<Settings['webgpuBackgroundPresets']>[number]

defineProps<{
  draft: Settings
  isNarrowPortrait: boolean
  pageBackgroundImageUrl: string | null | undefined
  pageBackgroundImageStyle: CSSProperties
  webgpuPresets: WebgpuPreset[]
  webgpuTargetFpsOptions: Array<{ label: string; value: string }>
  webgpuAvailability: 'unknown' | 'available' | 'unavailable'
  webgpuHasRuntimeOverride: boolean
  webgpuPresetSourceDirty: boolean
  webgpuPresetCompileDiagnosticsCount: number
  webgpuPresetCompileMessage: string | null
  webgpuPresetCreateBusy: boolean
  webgpuPresetDeleteBusy: boolean
  fontOptions: Array<{ label: string; value: string }>
  stPreview: SillyTavernImportPreview | null
  stPreviewLoading: boolean
  stDetectedMvu: boolean
  stMvuModeOptions: Array<{ label: string; value: string }>
  stPendingId: string
  stConfirming: boolean
  stImportConfirmLabel: string
  stExpiresAt: string
}>()

const open = defineModel<boolean>('open', { required: true })
const pageBackgroundOpacity = defineModel<number>('pageBackgroundOpacity', { required: true })
const pageBackgroundBlur = defineModel<number>('pageBackgroundBlur', { required: true })
const activeWebgpuPresetId = defineModel<string | null>('activeWebgpuPresetId', { required: true })
const webgpuTargetFps = defineModel<string>('webgpuTargetFps', { required: true })
const fontModel = defineModel<string>('fontModel', { required: true })
const messageFontSizeModel = defineModel<number | string>('messageFontSizeModel', { required: true })
const stEnableMvuCompatibility = defineModel<boolean>('stEnableMvuCompatibility', { required: true })
const stMvuMode = defineModel<MvuMode>('stMvuMode', { required: true })

const emit = defineEmits<{
  'clear-page-background': []
  'page-background-file': [event: Event]
  'create-webgpu-preset': []
  'open-webgpu-editor': [presetId: string]
  'run-webgpu-preset': []
  'delete-webgpu-preset': []
  'step-font-size': [delta: number]
  'font-file': [event: Event]
  'background-adjust': [active: boolean]
  backup: [mode: 'basic' | 'with_characters' | 'with_chats']
  'import-file': [event: Event]
  'st-import-file': [event: Event]
  'reset-st-preview': []
  'confirm-st-import': []
}>()

/** 正在拖的背景滑块：抽屉其余部分让位给背景，只留这一个 */
const activeBackgroundSlider = ref<'opacity' | 'blur' | null>(null)

function startBackgroundAdjust(slider: 'opacity' | 'blur') {
  activeBackgroundSlider.value = slider
  emit('background-adjust', true)
  const end = () => {
    window.removeEventListener('pointerup', end)
    window.removeEventListener('pointercancel', end)
    activeBackgroundSlider.value = null
    emit('background-adjust', false)
  }
  window.addEventListener('pointerup', end)
  window.addEventListener('pointercancel', end)
}

const pageBackgroundInputRef = ref<HTMLInputElement | null>(null)
const fontInputRef = ref<HTMLInputElement | null>(null)
const importInputRef = ref<HTMLInputElement | null>(null)
const stImportInputRef = ref<HTMLInputElement | null>(null)

function triggerPageBackgroundImport() {
  pageBackgroundInputRef.value?.click()
}

function triggerFontImport() {
  fontInputRef.value?.click()
}

function triggerImport() {
  importInputRef.value?.click()
}

function triggerStImport() {
  stImportInputRef.value?.click()
}
</script>

<template>
  <SettingsDrawerGlobalAccordion v-model:open="open" title="外观与数据">
    <div class="settings-group">
      <SettingsHint title="页面背景" more="图片叠在主题底色之上，调低透明度会透出底色，100% 为完整显示图片。模糊只作用于图片层。" />
      <div class="flex flex-wrap gap-2">
        <button type="button" class="btn btn-sm btn-secondary" @click="triggerPageBackgroundImport">导入图片</button>
        <button
          v-if="draft.pageBackgroundImage"
          type="button"
          class="btn btn-sm btn-secondary"
          @click="emit('clear-page-background')"
        >
          清除
        </button>
      </div>
      <input
        ref="pageBackgroundInputRef"
        type="file"
        class="hidden"
        accept="image/*,.png,.jpg,.jpeg,.webp,.gif"
        @change="emit('page-background-file', $event)"
      />
      <div
        v-if="pageBackgroundImageUrl"
        class="w-1/2 min-w-[12rem] max-w-[22rem] overflow-hidden rounded-lg"
      >
        <div class="h-32 overflow-hidden">
          <img
            :src="pageBackgroundImageUrl || ''"
            alt="页面背景预览"
            class="h-full w-full object-cover object-center"
            :style="pageBackgroundImageStyle"
          />
        </div>
      </div>
      <p v-else class="settings-hint">还未导入页面背景，聊天页仅使用主题底色。</p>
      <div class="grid gap-3 md:grid-cols-2">
        <label class="settings-field" :class="{ 'settings-slider-active': activeBackgroundSlider === 'opacity' }">
          <span class="settings-field-head">
            <span class="settings-label">透明度</span>
            <span class="settings-hint">{{ pageBackgroundOpacity }}%</span>
          </span>
          <input v-model="pageBackgroundOpacity" type="range" min="0" max="100" step="1" class="input-range" @pointerdown="startBackgroundAdjust('opacity')" />
        </label>
        <label class="settings-field" :class="{ 'settings-slider-active': activeBackgroundSlider === 'blur' }">
          <span class="settings-field-head">
            <span class="settings-label">模糊</span>
            <span class="settings-hint">{{ pageBackgroundBlur }} px</span>
          </span>
          <input v-model="pageBackgroundBlur" type="range" min="0" max="64" step="1" class="input-range" @pointerdown="startBackgroundAdjust('blur')" />
        </label>
      </div>
    </div>

    <div class="settings-group">
      <div class="settings-group-title">WebGPU 着色器背景</div>
      <SettingsSwitch
        :model-value="!!draft.webgpuBackgroundEnabled"
        label="启用着色器背景"
        hint="点「保存设置」才持久化。"
        more="运行态可先编译并应用，不会自动写入后端；仅「保存设置」才持久化。"
        @update:model-value="(v) => { draft.webgpuBackgroundEnabled = v }"
      />
      <div class="flex flex-wrap gap-2">
        <button
          type="button"
          class="btn btn-xs btn-secondary"
          :disabled="webgpuPresetCreateBusy"
          @click="emit('create-webgpu-preset')"
        >
          新建预设
        </button>
      </div>

      <div class="space-y-2">
        <div class="flex items-center justify-between gap-3">
          <span class="settings-label">活动预设</span>
          <div class="flex shrink-0 items-center gap-1.5">
            <span class="settings-hint whitespace-nowrap">渲染性能</span>
            <ModernSelect
              v-model="webgpuTargetFps"
              :options="webgpuTargetFpsOptions"
              placement="top"
              class="w-[96px] min-w-0"
            />
          </div>
        </div>
        <div class="settings-hint flex flex-wrap items-center gap-x-2 gap-y-1">
          <span>适配器：{{ webgpuAvailability === 'available' ? '可用' : webgpuAvailability === 'unavailable' ? '不可用' : '检测中' }}</span>
          <span v-if="webgpuHasRuntimeOverride">· 运行态覆盖</span>
          <span v-if="webgpuPresetSourceDirty">· 未保存</span>
        </div>
        <p
          v-if="webgpuPresetCompileDiagnosticsCount > 0 || webgpuPresetCompileMessage"
          class="text-xs text-[var(--color-error-text)]"
        >
          编译失败，请使用对应预设行的「编辑」查看详情。
        </p>
        <div class="space-y-1">
          <template v-for="item in webgpuPresets" :key="item.id">
            <div
              class="flex min-h-9 w-full flex-wrap items-center gap-1.5 rounded-md px-1 py-0.5 text-xs outline-none transition-colors focus-visible:ring-2 focus-visible:ring-brand-a40"
              :class="
                item.id === activeWebgpuPresetId
                  ? 'cursor-pointer bg-brand-a20 text-brand ring-1 ring-brand-a30'
                  : 'cursor-pointer hover:bg-surface-hover/40'
              "
              tabindex="0"
              @click="activeWebgpuPresetId = item.id"
              @keydown.enter.prevent="activeWebgpuPresetId = item.id"
              @keydown.space.prevent="activeWebgpuPresetId = item.id"
            >
              <div class="flex min-h-9 min-w-0 flex-1 basis-[min(100%,10rem)] items-center px-2 py-1">
                <span class="truncate">{{ item.name }}</span>
              </div>
              <div class="flex flex-wrap items-center gap-1.5" @click.stop>
                <button
                  type="button"
                  class="min-h-8 shrink-0 rounded-md border border-[var(--color-border-subtle)] px-2 py-1 text-2xs text-[var(--color-text-secondary)] transition-colors hover:bg-surface-hover/40 hover:text-[var(--color-text)]"
                  :class="item.id === activeWebgpuPresetId ? 'border-[var(--color-border-subtle)]/80' : ''"
                  @click="emit('open-webgpu-editor', item.id)"
                >
                  编辑
                </button>
                <template v-if="item.id === activeWebgpuPresetId">
                  <button
                    type="button"
                    class="min-h-8 shrink-0 rounded-md border border-[var(--color-border-subtle)] px-2 py-1 text-2xs transition-colors hover:bg-surface-hover/30"
                    @click="emit('run-webgpu-preset')"
                  >
                    运行
                  </button>
                  <button
                    type="button"
                    class="min-h-8 shrink-0 rounded-md border border-[color-mix(in_srgb,var(--color-error)_40%,transparent)] px-2 py-1 text-2xs text-[var(--color-error-text)] transition-colors hover:bg-[var(--color-danger-hover)] disabled:opacity-50"
                    :disabled="webgpuPresetDeleteBusy"
                    @click="emit('delete-webgpu-preset')"
                  >
                    删除
                  </button>
                </template>
              </div>
            </div>
          </template>
          <div v-if="webgpuPresets.length === 0" class="settings-hint">
            暂无预设
          </div>
        </div>
      </div>
    </div>

    <div class="settings-group">
      <div class="settings-group-title">界面与字体</div>
      <SettingsField label="界面色系">
        <ModernSelect
          v-model="draft.themeId"
          :options="[...THEME_OPTIONS]"
          placeholder="选择色系..."
          class="w-full"
        />
      </SettingsField>
      <SettingsField label="字体">
        <div class="gap-2" :class="isNarrowPortrait ? 'flex flex-col' : 'flex flex-wrap items-center'">
        <div class="relative min-w-0 group" :class="isNarrowPortrait ? 'w-full' : 'max-w-[172px] flex-1'">
          <ModernSelect
            v-model="fontModel"
            :options="fontOptions"
            placement="top"
            searchable
            placeholder="选择字体..."
            class="w-full min-w-0"
          />
        </div>
        <div class="flex flex-wrap items-center gap-2" :class="isNarrowPortrait ? 'w-full' : ''">
          <div class="flex h-10 items-center gap-0.5 rounded-lg border border-[var(--color-border)] bg-surface-muted px-1 py-0.5">
            <button
              type="button"
              class="flex min-h-9 min-w-9 items-center justify-center rounded-md p-2 text-[var(--color-text-muted)] transition-colors hover:bg-surface-hover hover:text-[var(--color-text)]"
              aria-label="减小字号"
              @click="emit('step-font-size', -1)"
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="5" y1="12" x2="19" y2="12"/></svg>
            </button>
            <input
              v-model.number="messageFontSizeModel"
              type="number"
              min="8"
              max="72"
              placeholder=""
              class="w-10 border-0 bg-transparent text-center text-sm text-[var(--color-text)] [appearance:textfield] focus:outline-none focus:ring-0 [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none"
            />
            <button
              type="button"
              class="flex min-h-9 min-w-9 items-center justify-center rounded-md p-2 text-[var(--color-text-muted)] transition-colors hover:bg-surface-hover hover:text-[var(--color-text)]"
              aria-label="增大字号"
              @click="emit('step-font-size', 1)"
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
            </button>
          </div>
          <button
            type="button"
            class="btn btn-sm btn-secondary"
            @click="triggerFontImport"
          >
            导入字体
          </button>
          <input
            ref="fontInputRef"
            type="file"
            class="hidden"
            accept=".ttf,.otf,.woff,.woff2"
            @change="emit('font-file', $event)"
          />
        </div>
      </div>
      </SettingsField>
      <SettingsField label="阅读字体" more="只作用于消息正文，默认跟随界面字体。">
        <ModernSelect
          :model-value="draft.readingFont ?? ''"
          :options="[{ label: '跟随界面字体', value: '' }, ...fontOptions.filter((option) => option.value)]"
          placement="top"
          searchable
          placeholder="跟随界面字体"
          class="w-full min-w-0"
          @update:model-value="(value) => { draft.readingFont = value || null }"
        />
      </SettingsField>
      <SettingsField label="消息行高">
        <template #actions>
          <span class="flex items-center gap-2">
            <span class="settings-hint">{{ draft.messageLineHeight == null ? '默认' : draft.messageLineHeight.toFixed(2) }}</span>
            <button
              type="button"
              class="btn btn-xs btn-ghost"
              :disabled="draft.messageLineHeight == null"
              @click="draft.messageLineHeight = null"
            >
              恢复默认
            </button>
          </span>
        </template>
        <input
          :value="draft.messageLineHeight ?? 1.7"
          type="range"
          min="1.2"
          max="2.4"
          step="0.05"
          class="input-range"
          aria-label="消息行高"
          @input="draft.messageLineHeight = Number(($event.target as HTMLInputElement).value)"
        />
      </SettingsField>
    </div>

    <div class="settings-group">
      <div class="settings-group-title">数据备份与导入</div>
      <div class="flex flex-col gap-2">
        <div class="grid grid-cols-2 gap-2">
          <button
            type="button"
            class="btn btn-sm btn-secondary min-w-0"
            @click="emit('backup', 'basic')"
          >
            基本设置
          </button>
          <button
            type="button"
            class="btn btn-sm btn-secondary min-w-0"
            @click="emit('backup', 'with_characters')"
          >
            包含角色卡
          </button>
        </div>
        <div class="grid grid-cols-2 gap-2">
          <button
            type="button"
            class="btn btn-sm btn-secondary min-w-0"
            @click="emit('backup', 'with_chats')"
          >
            包含全部聊天记录
          </button>
          <button
            type="button"
            class="btn btn-sm btn-secondary min-w-0"
            :disabled="stPreviewLoading"
            @click="triggerImport"
          >
            {{ stPreviewLoading ? '读取预览中…' : '导入数据' }}
          </button>
        </div>
        <button
          type="button"
          class="btn btn-sm btn-secondary w-full"
          :disabled="stPreviewLoading"
          @click="triggerStImport"
        >
          {{ stPreviewLoading ? '读取预览中…' : '仅选择 SillyTavern 角色卡（PNG / JSON）' }}
        </button>
        <input
          ref="importInputRef"
          type="file"
          class="hidden"
          accept=".txt,.json,.jsonl,.zip,.png"
          @change="emit('import-file', $event)"
        />
        <input ref="stImportInputRef" type="file" class="hidden" accept=".png,.json" @change="emit('st-import-file', $event)" />
        <div
          v-if="stPreview"
          class="settings-readout"
        >
          <div class="flex flex-wrap items-center justify-between gap-2">
            <div class="font-medium text-[var(--color-text-secondary)]">SillyTavern 预览</div>
            <button
              type="button"
              class="btn btn-xs btn-secondary"
              @click="emit('reset-st-preview')"
            >
              清除
            </button>
          </div>
          <div class="mt-2">
            角色名：<span class="text-[var(--color-text)]">{{ stPreview.characterName || '未知' }}</span>
          </div>
          <div class="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
            <div>世界书：<span class="text-[var(--color-text)]">{{ stPreview.worldBookName || '未检测到' }}</span></div>
            <div>世界书条目：<span class="text-[var(--color-text)]">{{ stPreview.worldBookEntryCount }}</span></div>
            <div>tavern_helper：<span class="text-[var(--color-text)]">{{ stPreview.mvu.hasTavernHelper ? '已检测到' : '未检测到' }}</span></div>
            <div>regex_scripts：<span class="text-[var(--color-text)]">{{ stPreview.mvu.regexScriptCount }}</span></div>
          </div>
          <label class="mt-3 flex items-center gap-2 text-[var(--color-text-muted)]">
            <ThemedCheckbox :checked="stEnableMvuCompatibility" @update:checked="stEnableMvuCompatibility = $event" />
            启用 MVU 兼容
            <span v-if="stDetectedMvu" class="text-[var(--color-text-secondary)]">已检测到候选结构</span>
          </label>
          <p class="text-[var(--color-text-muted)]">
            指令模式会把完整 ST 卡上下文交给 MVU Agent，生成角色卡 MVU 指令与初始状态栏后再完成导入。
          </p>
          <div class="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-[1fr_auto] sm:items-end">
            <div>
              <div class="mb-1 text-[var(--color-text-muted)]">MVU 模式</div>
              <ModernSelect
                v-model="stMvuMode"
                :options="stMvuModeOptions"
                placeholder="选择 MVU 模式"
              />
            </div>
            <button
              type="button"
              class="btn btn-sm btn-primary min-h-10 w-full sm:w-auto"
              :disabled="!stPendingId || stConfirming"
              @click="emit('confirm-st-import')"
            >
              {{ stImportConfirmLabel }}
            </button>
          </div>
          <div v-if="stExpiresAt" class="mt-2 text-[var(--color-text-muted)]">预览暂存至：{{ stExpiresAt }}</div>
        </div>
      </div>
      <SettingsHint more="PNG 或 SillyTavern 形状 JSON 会先显示预览并可勾选 MVU；普通备份 JSON 仍走一键导入。备份会导出全部系统设置（含用户 Persona 头像）；“包含角色卡/包含全部聊天记录”同时包含世界书数据。">
        备份含全部系统设置；角色卡和聊天记录备份同时含世界书。
      </SettingsHint>
    </div>
  </SettingsDrawerGlobalAccordion>
</template>
