// @vitest-environment happy-dom
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import ErrorModal from './ErrorModal.vue'

beforeEach(() => {
  setActivePinia(createPinia())
})


describe('ErrorModal', () => {
  it('展示建议操作和 requestId，并在复制时包含定位信息', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText },
    })
    const wrapper = mount(ErrorModal, {
      props: {
        item: {
          id: 'error-1',
          message: '上游服务鉴权失败',
          source: 'main',
          title: '聊天错误',
          createdAt: Date.now(),
          timeoutMs: 6000,
          code: 'provider_auth_failed',
          suggestedAction: '检查 API Key',
          requestId: 'req_modal_123',
        },
        offsetY: 0,
        zIndex: 10,
      },
    })

    expect(wrapper.text()).toContain('检查 API Key')
    expect(wrapper.text()).toContain('req_modal_123')

    await wrapper.findAll('button')[1]?.trigger('click')
    expect(writeText).toHaveBeenCalledWith(
      '上游服务鉴权失败\n建议操作：检查 API Key\nrequestId：req_modal_123',
    )
  })

  it('有 open_settings 动作时渲染跳转按钮', () => {
    const wrapper = mount(ErrorModal, {
      props: {
        item: {
          id: 'error-2',
          message: '缺少 reasoning_content',
          source: 'main',
          title: '聊天错误',
          createdAt: Date.now(),
          timeoutMs: 6000,
          suggestedAction: '打开预设思考回传开关',
          action: {
            type: 'open_settings',
            tab: 'presets',
            presetId: 'p1',
            field: 'echoReasoning',
            label: '打开预设的思考回传开关',
          },
        },
        offsetY: 0,
        zIndex: 10,
      },
    })
    expect(wrapper.get('[data-testid="error-action-open-settings"]').text()).toContain('思考回传')
  })
})
