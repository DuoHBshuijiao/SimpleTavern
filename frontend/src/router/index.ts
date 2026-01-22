/**
 * 路由配置模块
 *
 * 提供Vue Router的路由配置，定义应用的所有路由规则。
 *
 * 主要功能：
 *    - 配置路由历史模式（HTML5 History模式）
 *    - 定义路由规则和重定向
 *    - 导出路由实例供应用使用
 *
 * 主要函数：
 *    - createRouter: 创建路由实例（来自vue-router）
 *
 * 路由规则：
 *    - /: 重定向到/chat
 *    - /characters: 重定向到/chat
 *    - /chat: 显示ChatPage聊天页面
 *
 * 文件关系：
 *    - 被导入：被main.ts导入用于注册路由插件
 *    - 导入：导入views/ChatPage.vue页面组件
 *    - 依赖：依赖vue-router
 *    - 位置：路由配置层，定义应用的路由结构
 */

import { createRouter, createWebHistory } from 'vue-router'

import ChatPage from '../views/ChatPage.vue'

/**
 * 创建并导出路由实例
 *
 * 使用HTML5 History模式，支持浏览器前进后退。
 * 配置所有路由规则，包括重定向和页面组件映射。
 *
 * @returns {Router} Vue Router实例
 */
export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/chat' },
    { path: '/characters', redirect: '/chat' },
    { path: '/chat', component: ChatPage },
  ],
})


