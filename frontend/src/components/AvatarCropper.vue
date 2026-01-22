<script setup lang="ts">
import { ref, onUnmounted, watch, nextTick } from 'vue'
import Cropper from 'cropperjs'
import 'cropperjs/dist/cropper.css'

const props = defineProps<{
  show: boolean
  currentAvatar?: string
}>()

const emit = defineEmits<{
  (e: 'update:show', v: boolean): void
  (e: 'save', imageData: string): void
}>()

const imageRef = ref<HTMLImageElement | null>(null)
const imageSrc = ref<string | null>(null)
const cropper = ref<Cropper | null>(null)
const fileInputRef = ref<HTMLInputElement | null>(null)

function handleFileSelect(event: Event) {
  const target = event.target as HTMLInputElement
  const file = target.files?.[0]
  if (!file) return

  const reader = new FileReader()
  reader.onload = (e) => {
    imageSrc.value = e.target?.result as string
  }
  reader.readAsDataURL(file)
}

function triggerFileInput() {
  fileInputRef.value?.click()
}

watch(imageSrc, async (src) => {
  if (cropper.value) {
    cropper.value.destroy()
    cropper.value = null
  }
  if (src) {
    await nextTick()
    setTimeout(() => {
      if (imageRef.value && imageSrc.value) {
        cropper.value = new Cropper(imageRef.value, {
          aspectRatio: 1,
          viewMode: 1,
          dragMode: 'move',
          autoCropArea: 1,
          cropBoxMovable: true,
          cropBoxResizable: true,
          background: false,
        })
      }
    }, 150)
  }
})

watch(() => props.show, (show) => {
  if (!show) {
    imageSrc.value = null
    if (cropper.value) {
      cropper.value.destroy()
      cropper.value = null
    }
    if (fileInputRef.value) {
      fileInputRef.value.value = ''
    }
  }
})

function handleSave() {
  if (!cropper.value) return

  const canvas = cropper.value.getCroppedCanvas({
    width: 256,
    height: 256,
    imageSmoothingEnabled: true,
    imageSmoothingQuality: 'high',
  })

  const imageData = canvas.toDataURL('image/png')
  emit('save', imageData)
  emit('update:show', false)
}

function handleCancel() {
  emit('update:show', false)
}

function resetSelection() {
  imageSrc.value = null
  if (fileInputRef.value) {
    fileInputRef.value.value = ''
  }
}

onUnmounted(() => {
  if (cropper.value) {
    cropper.value.destroy()
  }
})
</script>

<template>
  <div v-if="show" class="modal">
    <div class="modal-backdrop" @click="handleCancel"></div>
    <div class="modal-content chat-modal-width-500-90">
      <div class="modal-header">
        <h3 class="modal-title">设置头像</h3>
        <button class="modal-close" @click="handleCancel">×</button>
      </div>
      <div class="modal-body">
        <div class="space-y-6">
          <!-- 隐藏的文件输入 -->
          <input
            ref="fileInputRef"
            type="file"
            accept="image/*"
            class="hidden"
            @change="handleFileSelect"
          />

          <div v-if="!imageSrc" class="upload-area" @click="triggerFileInput">
            <div class="upload-content">
              <div class="text-lg font-bold text-brand mb-2">点击选择图片</div>
              <div class="text-xs text-gray-500">支持 JPG、PNG、GIF、WebP 格式</div>
            </div>
          </div>

          <div v-else class="cropper-container">
            <img ref="imageRef" :src="imageSrc" class="max-w-full block" />
          </div>
        </div>
      </div>
      <div class="modal-footer">
        <button class="btn btn-secondary" @click="handleCancel">取消</button>
        <button v-if="imageSrc" class="btn btn-secondary" @click="resetSelection">重新选择</button>
        <button class="btn btn-primary" :disabled="!imageSrc" @click="handleSave">
          保存头像
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.upload-area {
  border: 2px dashed var(--color-brand);
  border-radius: var(--radius-lg);
  padding: 40px 20px;
  text-align: center;
  cursor: pointer;
  transition: all var(--transition-normal);
  background: rgba(162, 48, 237, 0.05);
}

.upload-area:hover {
  border-color: var(--color-brand-hover);
  background: rgba(162, 48, 237, 0.1);
}

.upload-content {
  pointer-events: none;
}

.cropper-container {
  max-height: 400px;
  overflow: hidden;
  border-radius: var(--radius-lg);
  background: rgba(0, 0, 0, 0.3);
}

.cropper-container :deep(.cropper-view-box),
.cropper-container :deep(.cropper-face) {
  border-radius: 50%;
}
</style>
