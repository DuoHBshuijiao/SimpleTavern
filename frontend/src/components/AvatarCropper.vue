<script setup lang="ts">
import { ref, onUnmounted, watch } from 'vue'
import { X } from 'lucide-vue-next'
import Cropper from 'cropperjs'
import 'cropperjs/dist/cropper.css'
import { useDialogBehavior } from '../composables/useDialogBehavior'
import type { AvatarDisplay } from '../types/models'
import { dialogAria } from '../utils/uiPrimitives'

const props = defineProps<{
  show: boolean
  saveAvatar: (imageData: string, display: AvatarDisplay) => Promise<void>
}>()

const emit = defineEmits<{
  'update:show': [show: boolean]
  saved: []
}>()

const titleId = 'avatar-cropper-title'
const dialogAttrs = dialogAria(titleId)
const imageRef = ref<HTMLImageElement | null>(null)
const imageSrc = ref<string | null>(null)
const fileInputRef = ref<HTMLInputElement | null>(null)
const imageLoaded = ref(false)
const isDragging = ref(false)
const isCropping = ref(false)
const cropperReady = ref(false)
const saving = ref(false)
const errorText = ref('')
let cropper: Cropper | null = null
let reader: FileReader | null = null
let saved = false

function close() {
  if (!saving.value) emit('update:show', false)
}

function afterClose() {
  if (!saved) return
  saved = false
  emit('saved')
}

const { dialogRef } = useDialogBehavior(() => props.show, close)
void dialogRef

function resetSelection() {
  reader?.abort()
  reader = null
  isCropping.value = false
  imageLoaded.value = false
  imageSrc.value = null
  errorText.value = ''
  if (fileInputRef.value) fileInputRef.value.value = ''
}

function loadImageFile(file: File) {
  if (saving.value) return
  resetSelection()
  if (!file.type.startsWith('image/') && !/\.(png|jpe?g|gif|webp|bmp|svg)$/i.test(file.name)) {
    errorText.value = '请选择图片文件。'
    return
  }
  const currentReader = new FileReader()
  reader = currentReader
  currentReader.onload = () => {
    if (reader !== currentReader) return
    reader = null
    imageSrc.value = currentReader.result as string
  }
  currentReader.onerror = () => {
    if (reader !== currentReader) return
    resetSelection()
    errorText.value = '无法读取图片，请重新选择。'
  }
  currentReader.readAsDataURL(file)
}

function handleFileSelect(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (file) loadImageFile(file)
}

function handleImageError() {
  resetSelection()
  errorText.value = '无法打开这张图片，请重新选择。'
}

function handleDragOver(event: DragEvent) {
  if (event.dataTransfer) event.dataTransfer.dropEffect = saving.value ? 'none' : 'copy'
  isDragging.value = !saving.value
}

function handleDragLeave(event: DragEvent) {
  const current = event.currentTarget as HTMLElement
  if (event.relatedTarget instanceof Node && current.contains(event.relatedTarget)) return
  isDragging.value = false
}

function handleDrop(event: DragEvent) {
  isDragging.value = false
  const file = event.dataTransfer?.files?.[0]
  if (file) loadImageFile(file)
}

watch(isCropping, (enabled, _, onCleanup) => {
  if (!enabled || !imageRef.value) return
  cropper = new Cropper(imageRef.value, {
    aspectRatio: 1,
    viewMode: 1,
    dragMode: 'move',
    autoCropArea: 1,
    background: false,
    checkOrientation: false,
    minContainerWidth: 0,
    minContainerHeight: 0,
    ready: () => { cropperReady.value = true },
  })
  onCleanup(() => {
    cropper?.destroy()
    cropper = null
    cropperReady.value = false
  })
}, { flush: 'post' })

watch(() => props.show, (show) => {
  if (show) {
    saved = false
  } else {
    isDragging.value = false
    resetSelection()
  }
})

async function handleSave() {
  if (!imageSrc.value || !imageLoaded.value || saving.value) return

  let display: AvatarDisplay = 'full'
  if (isCropping.value) {
    if (!cropper || !cropperReady.value) return
    const { x, y, width, height } = cropper.getData()
    const { naturalWidth, naturalHeight } = cropper.getImageData()
    const left = Math.max(0, x)
    const top = Math.max(0, y)
    const right = Math.min(naturalWidth, x + width)
    const bottom = Math.min(naturalHeight, y + height)
    if (!(right > left && bottom > top)) {
      errorText.value = '请框选头像的显示范围。'
      return
    }
    display = {
      x: left / naturalWidth,
      y: top / naturalHeight,
      width: (right - left) / naturalWidth,
      height: (bottom - top) / naturalHeight,
    }
  }

  saving.value = true
  errorText.value = ''
  try {
    await props.saveAvatar(imageSrc.value, display)
    saved = true
    emit('update:show', false)
  } catch {
    errorText.value = '头像保存失败，请重试。'
  } finally {
    saving.value = false
  }
}

onUnmounted(() => reader?.abort())
</script>

<template>
  <Transition name="modal" @after-leave="afterClose">
    <div v-if="show" class="modal">
      <div class="modal-backdrop backdrop-blur-[var(--glass-blur-soft)]" @click="close"></div>
      <div
        ref="dialogRef"
        v-bind="dialogAttrs"
        tabindex="-1"
        class="modal-content modal-surface chat-modal-width-500-90"
      >
        <div class="modal-header">
          <h3 :id="titleId" class="modal-title">设置头像</h3>
          <button type="button" class="modal-close" aria-label="关闭头像设置弹窗" :disabled="saving" @click="close">
            <X class="w-5 h-5" />
          </button>
        </div>
        <div
          class="modal-body transition-colors"
          :class="isDragging ? 'bg-brand-a10' : ''"
          @dragenter.prevent="handleDragOver"
          @dragover.prevent="handleDragOver"
          @dragleave.prevent="handleDragLeave"
          @drop.prevent="handleDrop"
        >
          <input
            ref="fileInputRef"
            type="file"
            accept="image/*"
            class="hidden"
            @change="handleFileSelect"
          />

          <button
            v-if="!imageSrc"
            type="button"
            class="btn btn-secondary w-full flex-col whitespace-normal border-dashed p-10 text-center"
            @click="fileInputRef?.click()"
          >
            <span class="text-lg font-bold text-brand">点击选择图片</span>
            <span class="text-xs text-muted">支持 JPG、PNG、GIF、WebP 格式（可拖拽到此区域）</span>
          </button>

          <template v-else>
            <div class="avatar-image-preview bg-[var(--color-surface-inset)] rounded-xl overflow-hidden p-2">
              <div>
                <img
                  ref="imageRef"
                  :src="imageSrc"
                  class="mx-auto block max-w-full max-h-[min(400px,45dvh)] object-contain"
                  alt="待保存的头像"
                  @load="imageLoaded = true"
                  @error="handleImageError"
                />
              </div>
            </div>
            <div class="mt-3 flex min-h-8 items-center justify-between gap-3">
              <p class="text-xs text-muted">
                {{ isCropping ? '拖动方框或调整大小，选择头像的显示范围。' : '保存后显示整张图片。' }}
              </p>
              <button
                type="button"
                class="btn btn-sm btn-secondary shrink-0"
                :disabled="!imageLoaded || saving"
                @click="isCropping = !isCropping"
              >{{ isCropping ? '使用全图' : '裁剪' }}</button>
            </div>
          </template>

          <p v-if="errorText" class="mt-3 text-sm text-[var(--color-error-text)]" role="alert">{{ errorText }}</p>
        </div>
        <div class="modal-footer">
          <button type="button" class="btn btn-secondary" :disabled="saving" @click="close">取消</button>
          <button v-if="imageSrc" type="button" class="btn btn-secondary" :disabled="saving" @click="resetSelection">重新选择</button>
          <button
            type="button"
            class="btn btn-primary"
            :disabled="!imageLoaded || (isCropping && !cropperReady) || saving"
            @click="handleSave"
          >{{ saving ? '保存中…' : '保存头像' }}</button>
        </div>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.avatar-image-preview :deep(.cropper-container img) {
  image-orientation: from-image;
}
</style>
