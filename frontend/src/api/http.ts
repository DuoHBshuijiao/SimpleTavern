/**
 * HTTP请求封装模块
 *
 * 提供统一的HTTP请求方法，封装fetch API，简化API调用。
 *
 * 主要功能：
 *    - GET请求：获取资源
 *    - PUT请求：更新资源
 *    - POST请求：创建资源或执行操作
 *    - DELETE请求：删除资源
 *
 * 主要函数：
 *    - apiGet: 发送GET请求
 *    - apiPut: 发送PUT请求
 *    - apiPost: 发送POST请求
 *    - apiDelete: 发送DELETE请求
 *
 * 文件关系：
 *    - 被导入：被stores、composables、components等模块导入用于API调用
 *    - 导入：无
 *    - 依赖：依赖浏览器fetch API
 *    - 位置：API层，提供HTTP请求的基础封装
 */

/**
 * 发送GET请求
 *
 * 向指定路径发送GET请求，返回JSON格式的响应数据。
 *
 * @template T 响应数据的类型
 * @param {string} path - 请求路径
 * @returns {Promise<T>} 解析后的JSON响应数据
 * @throws {Error} 请求失败时抛出错误，错误信息为响应文本
 */
export async function apiGet<T>(path: string): Promise<T> {
  const r = await fetch(path, { method: 'GET' })
  if (!r.ok) throw new Error(await r.text())
  return (await r.json()) as T
}

/**
 * 发送PUT请求
 *
 * 向指定路径发送PUT请求，更新资源。请求体会被序列化为JSON。
 *
 * @template T 响应数据的类型
 * @param {string} path - 请求路径
 * @param {unknown} body - 请求体数据，会被序列化为JSON
 * @returns {Promise<T>} 解析后的JSON响应数据
 * @throws {Error} 请求失败时抛出错误，错误信息为响应文本
 */
export async function apiPut<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(path, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!r.ok) throw new Error(await r.text())
  return (await r.json()) as T
}

/**
 * 发送POST请求
 *
 * 向指定路径发送POST请求，创建资源或执行操作。请求体会被序列化为JSON。
 *
 * @template T 响应数据的类型
 * @param {string} path - 请求路径
 * @param {unknown} body - 请求体数据，会被序列化为JSON
 * @returns {Promise<T>} 解析后的JSON响应数据
 * @throws {Error} 请求失败时抛出错误，错误信息为响应文本
 */
export async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!r.ok) throw new Error(await r.text())
  return (await r.json()) as T
}

/**
 * 发送DELETE请求
 *
 * 向指定路径发送DELETE请求，删除资源。
 *
 * @param {string} path - 请求路径
 * @returns {Promise<void>} 请求成功时返回void
 * @throws {Error} 请求失败时抛出错误，错误信息为响应文本
 */
export async function apiDelete(path: string): Promise<void> {
  const r = await fetch(path, { method: 'DELETE' })
  if (!r.ok) throw new Error(await r.text())
}


