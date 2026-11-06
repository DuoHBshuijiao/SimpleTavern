<script setup lang="ts">
/**
 * 设置项说明：默认只显示一句短说明；更长的解释收进 ⓘ，点开才出现。
 * 全部设置页共用这一种写法，不要再单独写说明文字的样式。
 */
import { ref } from 'vue'
import { Info } from 'lucide-vue-next'

defineProps<{
  /** 长说明，点 ⓘ 展开 */
  more?: string
}>()

const open = ref(false)
</script>

<template>
  <div class="settings-hint">
    <p>
      <slot />
      <button
        v-if="more"
        type="button"
        class="settings-hint-toggle"
        :aria-expanded="open"
        :aria-label="open ? '收起说明' : '展开说明'"
        @click="open = !open"
      >
        <Info class="h-3 w-3" />
      </button>
    </p>
    <div v-if="more" class="settings-hint-more" :class="{ 'settings-hint-more--open': open }">
      <p class="min-h-0 overflow-hidden">
        <span class="block pt-1">{{ more }}</span>
      </p>
    </div>
  </div>
</template>
