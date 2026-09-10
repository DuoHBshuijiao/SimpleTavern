// @vitest-environment happy-dom
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'
import ModelControlPanel from './ModelControlPanel.vue'

beforeEach(() => {
  setActivePinia(createPinia())
})

describe('ModelControlPanel', () => {
  it('触发胶囊展示模型名、思考深度与 Fast 徽标', () => {
    const wrapper = mount(ModelControlPanel, {
      props: {
        currentModel: 'claude-opus-4-6',
        modelOptions: ['claude-opus-4-6', 'deepseek-v4-flash'],
        reasoningEffort: 'high',
        globalReasoningEffort: 'none',
        fastMode: true,
      },
    })
    const trigger = wrapper.get('[data-testid="model-control-trigger"]')
    expect(trigger.text()).toContain('claude-opus-4-6')
    expect(trigger.attributes('aria-label')).toContain('Fast：开')
    expect(trigger.attributes('aria-label')).toContain('思考')
  })

  it('面板内有思考开关、Fast 约 2× 计费旁注', async () => {
    const wrapper = mount(ModelControlPanel, {
      attachTo: document.body,
      props: {
        currentModel: 'claude-opus-4-6',
        modelOptions: ['claude-opus-4-6'],
        reasoningEffort: 'high',
        globalReasoningEffort: 'none',
        fastMode: false,
      },
      global: {
        stubs: { teleport: true, transition: false },
      },
    })
    await wrapper.get('[data-testid="model-control-trigger"]').trigger('click')
    expect(wrapper.get('[data-testid="model-control-thinking"]').text()).toContain('思考')
    expect(wrapper.get('[data-testid="model-control-fast"]').text()).toContain('约 2× 计费')
    wrapper.unmount()
  })
})
