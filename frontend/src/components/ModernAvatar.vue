<script setup lang="ts">
/**
 * ModernAvatar - 现代化头像组件
 *
 * 组件职责：
 * - 显示用户或角色的头像图片
 * - 当图片加载失败或未提供时，显示名称首字母
 * - 支持自定义尺寸、宽高比、圆角等样式
 * - 根据名称生成一致的颜色背景
 *
 * Props说明：
 * - src: 头像图片URL（可选）
 * - name: 名称，用于显示首字母和生成背景色
 * - size: 头像尺寸（数字或字符串，如40或"40px"）
 * - aspect: 宽高比（数字如1表示正方形，或"auto"表示自适应）
 * - rounded: Tailwind圆角类名（如"rounded-xl"）
 * - bordered: 是否显示边框
 * - objectFit: 图片对象适应方式（cover/contain/fill等）
 *
 * Emits说明：
 * 无
 *
 * 使用的Composables：
 * 无
 *
 * 使用的Stores：
 * 无
 *
 * 文件关系：
 *    - 被导入：被components/chat/ChatSidebar.vue、views/ChatPage.vue等组件使用
 *    - 导入：导入vue的computed和ref
 *    - 依赖：依赖vue
 *    - 位置：组件层，提供头像显示功能
 */
import { computed, ref } from 'vue'

interface Props {
  src?: string | null
  name?: string
  size?: number | string // Base width
  aspect?: number | string // Aspect ratio, e.g., 1 (square), 0.75 (3:4), or 'auto'
  rounded?: string // Tailwind rounded class, e.g., 'rounded-xl'
  bordered?: boolean
  objectFit?: 'cover' | 'contain' | 'fill' | 'scale-down' | 'none'
}

const props = withDefaults(defineProps<Props>(), {
  src: null,
  name: '?',
  size: 40,
  aspect: 1,
  rounded: 'rounded-xl',
  bordered: false,
  objectFit: 'cover'
})

const hasError = ref(false)
const isLoaded = ref(false)

/**
 * 计算样式对象
 *
 * 根据size和aspect计算头像容器的宽度、高度和字体大小。
 * 如果aspect为'auto'，则高度自适应；如果为数字，则根据宽高比计算高度。
 */
const style = computed(() => {
  const width = typeof props.size === 'number' ? `${props.size}px` : props.size
  let height: string | undefined = undefined
  
  if (props.aspect === 'auto') {
    height = 'auto'
  } else if (typeof props.aspect === 'number') {
    height = typeof props.size === 'number' 
      ? `${props.size / props.aspect}px` 
      : `calc(${props.size} / ${props.aspect})`
  } else {
    height = width
  }

  return {
    width,
    height,
    fontSize: typeof props.size === 'number' ? `${props.size * 0.4}px` : '1rem'
  }
})

/**
 * 处理图片加载错误
 *
 * 当图片加载失败时，标记错误状态，显示首字母。
 */
function handleError() {
  hasError.value = true
  isLoaded.value = true
}

/**
 * 处理图片加载成功
 *
 * 当图片加载成功时，标记加载完成状态。
 */
function handleLoad() {
  isLoaded.value = true
}

/**
 * 计算首字母
 *
 * 获取名称的首字母并转换为大写，如果名称为空则返回"?"。
 */
const initials = computed(() => {
  const name = props.name || '?'
  return name.length > 0 ? name.charAt(0).toUpperCase() : '?'
})

/**
 * 计算背景颜色
 *
 * 根据名称生成一致的颜色（使用简单的哈希算法）。
 * 从预定义的颜色列表中选择一个颜色，确保相同名称总是得到相同颜色。
 */
const bgColor = computed(() => {
  const colors = [
    'bg-brand-a20 text-brand',
    'bg-blue-500/20 text-blue-400',
    'bg-emerald-500/20 text-emerald-400',
    'bg-orange-500/20 text-orange-400',
    'bg-pink-500/20 text-pink-400',
    'bg-cyan-500/20 text-cyan-400',
  ]
  let hash = 0
  const str = props.name || '?'
  for (let i = 0; i < str.length; i++) {
    hash = str.charCodeAt(i) + ((hash << 5) - hash)
  }
  return colors[Math.abs(hash) % colors.length]
})
</script>

<template>
  <div
    class="relative overflow-hidden shrink-0 flex items-start justify-center select-none transition-all duration-300 shadow-sm"
    :class="[
      rounded,
      bgColor,
      // Liquid Glass enhancement: default subtle border for glass feel
      'border border-white/10', 
      bordered ? 'ring-2 ring-white/20' : ''
    ]"
    :style="style"
  >
    <img
      v-if="src && !hasError"
      :src="src"
      class="w-full transition-opacity duration-300"
      :class="[
        { 'opacity-0': !isLoaded, 'opacity-100': isLoaded },
        props.aspect === 'auto' ? 'h-auto' : 'h-full',
        `object-${objectFit}`
      ]"
      @error="handleError"
      @load="handleLoad"
      alt=""
    />
    <span v-else class="font-bold self-center">
      {{ initials }}
    </span>
    
    <!-- Skeleton loader -->
    <div 
      v-if="src && !isLoaded && !hasError" 
      class="absolute inset-0 bg-white/5 animate-pulse"
    ></div>
    
    <!-- Glass overlay for shine effect -->
    <div class="absolute inset-0 bg-gradient-to-tr from-white/5 to-transparent pointer-events-none"></div>
  </div>
</template>
