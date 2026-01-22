<script setup lang="ts">
/**
 * App - Vue应用根组件
 *
 * 组件职责：
 * - 作为应用的根组件，提供最外层容器
 * - 渲染路由视图，根据路由配置显示对应页面组件
 *
 * Props说明：
 * 无（根组件不接收props）
 *
 * Emits说明：
 * 无（根组件不发出事件）
 *
 * 使用的Composables：
 * 无
 *
 * 使用的Stores：
 * 无
 *
 * 文件关系：
 *    - 被导入：被main.ts导入作为应用根组件
 *    - 导入：导入vue-router的RouterView组件
 *    - 依赖：依赖vue-router
 *    - 位置：应用根组件层，作为所有页面的容器
 */

import { RouterView } from 'vue-router'
</script>

<template>
  <!-- 路由视图容器：根据路由配置渲染对应的页面组件 -->
  <RouterView />
</template>
