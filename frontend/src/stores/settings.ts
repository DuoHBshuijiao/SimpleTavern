/**
 * 设置Store模块
 *
 * 管理应用的全局设置状态，包括LLM配置、API预设、用户身份等。
 *
 * 主要功能：
 *    - 加载设置：从服务器获取设置数据
 *    - 保存设置：将设置数据保存到服务器
 *
 * 主要函数：
 *    - load: 加载设置
 *    - save: 保存设置
 *
 * 状态说明：
 *    - settings: 设置数据（来自types/models.ts的Settings类型）
 *    - loading: 加载状态
 *    - error: 错误信息
 *
 * 文件关系：
 *    - 被导入：被stores/index.ts导出，被composables、components、views等模块使用
 *    - 导入：导入types/models.ts的Settings类型、api/http.ts的apiGet和apiPut函数
 *    - 依赖：依赖pinia、api/http.ts
 *    - 位置：Store层，管理应用设置状态
 */

import { defineStore } from 'pinia'

import type { Settings } from '../types/models'
import { apiGet, apiPut } from '../api/http'

/**
 * 设置Store
 *
 * 使用Pinia定义设置相关的状态管理。
 */
export const useSettingsStore = defineStore('settings', {
  state: () => ({
    settings: null as Settings | null,
    loading: false,
    error: null as string | null,
  }),
  actions: {
    /**
     * 加载设置
     *
     * 从服务器获取应用设置数据。
     * 使用apiGet函数（来自api/http.ts）发送GET请求到/api/settings。
     *
     * @throws {Error} 请求失败时抛出错误，错误信息存储在error状态中
     */
    async load() {
      this.loading = true
      this.error = null
      try {
        this.settings = await apiGet<Settings>('/api/settings')
      } catch (e: any) {
        this.error = e?.message ?? String(e)
        throw e
      } finally {
        this.loading = false
      }
    },
    /**
     * 保存设置
     *
     * 将设置数据保存到服务器。
     * 使用apiPut函数（来自api/http.ts）发送PUT请求到/api/settings。
     *
     * @param {Settings} next - 要保存的设置数据
     * @throws {Error} 请求失败时抛出错误，错误信息存储在error状态中
     */
    async save(next: Settings) {
      this.loading = true
      this.error = null
      try {
        this.settings = await apiPut<Settings>('/api/settings', next)
      } catch (e: any) {
        this.error = e?.message ?? String(e)
        throw e
      } finally {
        this.loading = false
      }
    },
  },
})


