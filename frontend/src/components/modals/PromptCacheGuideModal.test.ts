// @vitest-environment happy-dom
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import PromptCacheGuideModal from './PromptCacheGuideModal.vue'
import type { PromptCacheConfig } from '../../types/models'

describe('PromptCacheGuideModal', () => {
  it('近全屏 7 步教学，完成时写回当前连接的 promptCache', async () => {
    const connection = { promptCache: { mode: 'auto' } as PromptCacheConfig, protocol: 'auto' }
    const wrapper = mount(PromptCacheGuideModal, {
      attachTo: document.body,
      props: { show: true, connection },
      global: {
        stubs: {
          teleport: true,
          transition: false,
        },
      },
    })
    expect(wrapper.get('[data-testid="prompt-cache-guide"]').classes().join(' ')).toContain('max-w-5xl')
    expect(wrapper.get('[data-testid="prompt-cache-guide"]').classes().join(' ')).toContain('h-[92vh]')
    expect(wrapper.text()).toContain('第 1 / 7 步')

    const next = wrapper.get('[data-testid="cache-guide-next"]')
    for (let i = 0; i < 5; i += 1) {
      await next.trigger('click')
    }
    expect(wrapper.text()).toContain('应用到当前预设')
    const explicit = wrapper.findAll('button').find((b) => b.text().includes('显式写入'))
    await explicit?.trigger('click')
    await next.trigger('click')
    expect(wrapper.text()).toContain('第 7 / 7 步')
    await next.trigger('click')
    expect(connection.promptCache?.mode).toBe('explicit')
    wrapper.unmount()
  })
})
