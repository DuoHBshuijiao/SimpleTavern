<script setup lang="ts">
import { ref, onUnmounted, watch, nextTick } from 'vue'
import Cropper from 'cropperjs'
import 'cropperjs/dist/cropper.css'
import { NButton, NModal, NSpace, NText } from 'naive-ui'

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
    // 等待 DOM 更新后再初始化 Cropper
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
    // 重置文件输入
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
  <NModal
    :show="show"
    preset="card"
    style="width: min(500px, 90vw)"
    title="设置头像"
    @update:show="(v) => emit('update:show', v)"
  >
    <NSpace vertical size="large">
      <!-- 隐藏的文件输入 -->
      <input
        ref="fileInputRef"
        type="file"
        accept="image/*"
        style="display: none"
        @change="handleFileSelect"
      />

      <div v-if="!imageSrc" class="upload-area" @click="triggerFileInput">
        <div class="upload-content">
          <NText style="font-size: 16px; color: rgba(255,255,255,0.8)">
            点击选择图片
          </NText>
          <br />
          <NText depth="3" style="font-size: 12px">
            支持 JPG、PNG、GIF、WebP 格式
          </NText>
        </div>
      </div>

      <div v-else class="cropper-container">
        <img ref="imageRef" :src="imageSrc" style="max-width: 100%; display: block" />
      </div>

      <NSpace justify="end">
        <NButton @click="handleCancel">取消</NButton>
        <NButton v-if="imageSrc" @click="resetSelection">重新选择</NButton>
        <NButton type="primary" :disabled="!imageSrc" @click="handleSave">
          保存头像
        </NButton>
      </NSpace>
    </NSpace>
  </NModal>
</template>

<style scoped>
.upload-area {
  border: 2px dashed rgba(162, 48, 237, 0.4);
  border-radius: 8px;
  padding: 40px 20px;
  text-align: center;
  cursor: pointer;
  transition: all 0.3s;
  background: rgba(162, 48, 237, 0.05);
}

.upload-area:hover {
  border-color: rgba(162, 48, 237, 0.8);
  background: rgba(162, 48, 237, 0.1);
}

.upload-content {
  pointer-events: none;
}

.cropper-container {
  max-height: 400px;
  overflow: hidden;
  border-radius: 8px;
  background: rgba(0, 0, 0, 0.3);
}

.cropper-container :deep(.cropper-view-box),
.cropper-container :deep(.cropper-face) {
  border-radius: 50%;
}
</style>
