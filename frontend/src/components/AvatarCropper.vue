<script setup lang="ts">
/**
 * AvatarCropper - 头像裁剪
 * 风格：Obsidian Brutalist
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

function handleFileSelect(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (!file) return
  const reader = new FileReader()
  reader.onload = (e) => imageSrc.value = e.target?.result as string
  reader.readAsDataURL(file)
}

watch(imageSrc, async (src) => {
  if (cropper.value) { cropper.value.destroy(); cropper.value = null }
  if (src) {
    await nextTick()
    setTimeout(() => {
      if (imageRef.value) {
        cropper.value = new Cropper(imageRef.value, {
          aspectRatio: 1, viewMode: 1, background: false,
        })
      }
    }, 150)
  }
})

function handleSave() {
  if (!cropper.value) return
  const canvas = cropper.value.getCroppedCanvas({ width: 256, height: 256 })
  emit('save', canvas.toDataURL('image/png'))
  emit('update:show', false)
}
</script>

<template>
  <div v-if="show" class="modal-overlay">
    <div class="modal-backdrop" @click="emit('update:show', false)"></div>
    <div class="modal-container max-w-xl h-auto">
      <div class="modal-header">
        <h3 class="modal-title">Neural Asset Editor</h3>
        <button class="modal-close" @click="emit('update:show', false)">✕</button>
      </div>
      <div class="modal-content">
        <input ref="fileInputRef" type="file" accept="image/*" class="hidden" @change="handleFileSelect" />
        
        <div v-if="!imageSrc" class="border-2 border-dashed border-strong p-16 text-center cursor-pointer hover:border-brand transition-all" @click="fileInputRef?.click()">
          <div class="text-xl font-black uppercase tracking-tighter text-brand">Select Neural Link Image</div>
          <div class="text-[10px] font-bold text-text-muted uppercase tracking-widest mt-2">JPG / PNG / WEBP SUPPORTED</div>
        </div>

        <div v-else class="bg-black border border-strong">
          <img ref="imageRef" :src="imageSrc" class="max-w-full block" />
        </div>
      </div>
      <div class="modal-footer">
        <button class="btn btn-secondary text-[10px]" @click="emit('update:show', false)">ABORT</button>
        <button v-if="imageSrc" class="btn btn-secondary text-[10px]" @click="imageSrc = null">RESELECT</button>
        <button class="btn btn-primary text-[10px] px-12" :disabled="!imageSrc" @click="handleSave">COMMIT ASSET</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
:deep(.cropper-view-box), :deep(.cropper-face) { border-radius: 0; outline: 1px solid var(--color-brand); }
</style>
