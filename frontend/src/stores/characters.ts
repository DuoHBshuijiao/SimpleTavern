/**
 * 角色Store模块
 *
 * 管理角色卡片的状态，包括角色列表的CRUD操作。
 *
 * 主要功能：
 *    - 加载所有角色：获取角色列表
 *    - 创建角色：创建新角色卡片
 *    - 更新角色：更新现有角色卡片
 *    - 删除角色：删除角色卡片
 *    - 获取角色：根据ID获取单个角色
 *
 * 主要函数：
 *    - loadAll: 加载所有角色
 *    - create: 创建角色
 *    - update: 更新角色
 *    - remove: 删除角色
 *    - get: 获取单个角色
 *
 * 状态说明：
 *    - list: 角色列表（来自types/models.ts的CharacterCard[]类型）
 *    - loading: 加载状态
 *    - error: 错误信息
 *
 * 文件关系：
 *    - 被导入：被stores/index.ts导出，被composables、components、views等模块使用
 *    - 导入：导入types/models.ts的CharacterCard类型、api/http.ts的HTTP请求函数
 *    - 依赖：依赖pinia、api/http.ts
 *    - 位置：Store层，管理角色状态
 */

import { defineStore } from 'pinia'

import type { CharacterCard } from '../types/models'
import { apiDelete, apiGet, apiPost, apiPut } from '../api/http'

/**
 * 角色Store
 *
 * 使用Pinia定义角色相关的状态管理。
 */
export const useCharactersStore = defineStore('characters', {
  state: () => ({
    list: [] as CharacterCard[],
    loading: false,
    error: null as string | null,
  }),
  actions: {
    /**
     * 加载所有角色
     *
     * 从服务器获取所有角色列表。
     * 使用apiGet函数（来自api/http.ts）发送GET请求到/api/characters。
     *
     * @throws {Error} 请求失败时抛出错误，错误信息存储在error状态中
     */
    async loadAll() {
      this.loading = true
      this.error = null
      try {
        this.list = await apiGet<CharacterCard[]>('/api/characters')
      } catch (e: any) {
        this.error = e?.message ?? String(e)
        throw e
      } finally {
        this.loading = false
      }
    },
    /**
     * 创建角色
     *
     * 创建新的角色卡片。
     * 使用apiPost函数（来自api/http.ts）发送POST请求到/api/characters。
     * 创建成功后自动刷新角色列表。
     *
     * @param {CharacterCard} card - 角色卡片数据
     * @returns {Promise<CharacterCard>} 创建后的角色卡片
     */
    async create(card: CharacterCard) {
      const created = await apiPost<CharacterCard>('/api/characters', card)
      await this.loadAll()
      return created
    },
    /**
     * 更新角色
     *
     * 更新现有角色卡片。
     * 使用apiPut函数（来自api/http.ts）发送PUT请求到/api/characters/{id}。
     * 更新成功后自动刷新角色列表。
     *
     * @param {string} id - 角色ID
     * @param {CharacterCard} card - 更新的角色卡片数据
     * @returns {Promise<CharacterCard>} 更新后的角色卡片
     */
    async update(id: string, card: CharacterCard) {
      const updated = await apiPut<CharacterCard>(`/api/characters/${id}`, card)
      await this.loadAll()
      return updated
    },
    /**
     * 删除角色
     *
     * 删除指定角色卡片。
     * 使用apiDelete函数（来自api/http.ts）发送DELETE请求到/api/characters/{id}。
     * 删除成功后自动刷新角色列表。
     *
     * @param {string} id - 角色ID
     */
    async remove(id: string) {
      await apiDelete(`/api/characters/${id}`)
      await this.loadAll()
    },
    /**
     * 获取单个角色
     *
     * 根据ID获取单个角色卡片。
     * 使用apiGet函数（来自api/http.ts）发送GET请求到/api/characters/{id}。
     *
     * @param {string} id - 角色ID
     * @returns {Promise<CharacterCard>} 角色卡片数据
     */
    async get(id: string) {
      return await apiGet<CharacterCard>(`/api/characters/${id}`)
    },
  },
})


