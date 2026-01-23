<script setup lang="ts">
/**
 * HelloWorld - 示例组件
 *
 * 组件职责：
 * - 作为Vue示例组件，用于测试和学习
 * - 显示消息和计数器
 *
 * Props说明：
 * - msg: 要显示的消息文本
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
 *    - 被导入：可能被其他组件或示例使用
 *    - 导入：导入vue的ref
 *    - 依赖：依赖vue
 *    - 位置：组件层，示例组件
 */
import { ref } from 'vue'

defineProps<{ msg: string }>()

const count = ref(0)
</script>

<template>
  <h1>{{ msg }}</h1>

  <div class="card">
    <button type="button" @click="count++">count is {{ count }}</button>
    <p>
      Edit
      <code>components/HelloWorld.vue</code> to test HMR
    </p>
  </div>

  <p>
    Check out
    <a href="https://vuejs.org/guide/quick-start.html#local" target="_blank"
      >create-vue</a
    >, the official Vue + Vite starter
  </p>
  <p>
    Learn more about IDE Support for Vue in the
    <a
      href="https://vuejs.org/guide/scaling-up/tooling.html#ide-support"
      target="_blank"
      >Vue Docs Scaling up Guide</a
    >.
  </p>
  <p class="read-the-docs">Click on the Vite and Vue logos to learn more</p>
</template>

<style scoped>
.read-the-docs {
  color: #888;
}
</style>
