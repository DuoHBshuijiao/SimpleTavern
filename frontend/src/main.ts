/**
 * Vue应用入口模块
 *
 * 本模块是前端应用的入口点，负责：
 * - 创建Vue应用实例
 * - 配置状态管理（Pinia）
 * - 配置路由
 * - 挂载应用到DOM
 *
 * 主要功能：
 *    - 初始化Vue应用
 *    - 注册Pinia状态管理插件
 *    - 注册Vue Router路由插件
 *    - 挂载应用到页面
 *
 * 文件关系：
 *    - 被导入：无（作为应用入口被直接运行）
 *    - 导入：导入App.vue根组件、router路由配置、styles样式入口
 *    - 依赖：依赖vue、pinia、vue-router
 *    - 位置：应用入口层，整合所有核心模块
 */

import { createApp } from 'vue'
import { createPinia } from 'pinia'
import './styles/index.css'
import App from './App.vue'
import { router } from './router'

/**
 * 创建Vue应用实例并配置插件
 *
 * 初始化应用所需的所有插件和中间件，然后挂载到DOM。
 */
const app = createApp(App)
app.use(createPinia())
app.use(router)
app.mount('#app')
