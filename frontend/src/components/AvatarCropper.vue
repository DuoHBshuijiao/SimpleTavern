<script setup lang="ts">
/**
 * AvatarCropper - 头像裁剪组件
 *
 * 组件职责：
 * - 提供头像图片选择和裁剪功能
 * - 使用cropperjs库实现图片裁剪
 * - 支持圆形裁剪（用于头像）
 * - 将裁剪后的图片转换为base64格式
 *
 * Props说明：
 * - show: 是否显示弹窗（v-model:show）
 * - currentAvatar: 当前头像URL（可选，用于预览）
 *
 * Emits说明：
 * - update:show: 更新显示状态（v-model:show）
 * - save: 保存裁剪后的图片，传递base64编码的图片数据
 *
 * 使用的Composables：
 * 无
 *
 * 使用的Stores：
 * 无
 *
 * 文件关系：
 *    - 被导入：被views/ChatPage.vue使用用于裁剪角色和身份头像
 *    - 导入：导入vue的ref、onUnmounted、watch、nextTick，cropperjs库
 *    - 依赖：依赖vue、cropperjs
 *    - 位置：组件层，提供头像裁剪功能
 */
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

/**
 * 处理文件选择
 *
 * 当用户选择图片文件时，使用FileReader读取文件并转换为base64格式。
 *
 * @param {Event} event - 文件选择事件
 */
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

/**
 * 触发文件输入
 *
 * 程序化触发隐藏的文件输入框点击事件。
 */
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

/**
 * 处理保存
 *
 * 获取裁剪后的画布，转换为256x256的PNG格式base64数据，然后触发save事件并关闭弹窗。
 */
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

/**
 * 处理取消
 *
 * 关闭弹窗，不保存裁剪结果。
 */
function handleCancel() {
  emit('update:show', false)
}

/**
 * 重置选择
 *
 * 清空已选择的图片，允许重新选择。
 */
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
  <Transition name="modal">
    <div v-if="show" class="modal">
      <div class="modal-backdrop" @click="handleCancel"></div>
      <div class="modal-content chat-modal-width-500-90 glass-panel">
        <div class="modal-header">
          <h3 class="modal-title text-slate-50">设置头像</h3>
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

            <div 
              v-if="!imageSrc" 
              class="upload-area border-2 border-dashed border-white/20 bg-white/5 hover:bg-white/10 hover:border-white/30 transition-all rounded-xl p-10 text-center cursor-pointer" 
              @click="triggerFileInput"
            >
              <div class="upload-content pointer-events-none">
                <div class="text-lg font-bold text-brand mb-2">点击选择图片</div>
                <div class="text-xs text-gray-500">支持 JPG、PNG、GIF、WebP 格式</div>
              </div>
            </div>

            <div v-else class="cropper-container bg-black/20 rounded-xl overflow-hidden max-h-[400px]">
              <img ref="imageRef" :src="imageSrc" class="max-w-full block" />
            </div>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-secondary bg-white/5 hover:bg-white/10 text-gray-300 border border-white/5" @click="handleCancel">取消</button>
          <button v-if="imageSrc" class="btn btn-secondary bg-white/5 hover:bg-white/10 text-gray-300 border border-white/5" @click="resetSelection">重新选择</button>
          <button class="btn btn-primary bg-brand hover:bg-brand-hover text-white shadow-lg shadow-brand/20" :disabled="!imageSrc" @click="handleSave">
            保存头像
          </button>
        </div>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
/* Removed styles replaced by Tailwind classes */
.cropper-container :deep(.cropper-view-box),
.cropper-container :deep(.cropper-face) {
  border-radius: 50%;
}
</style>
