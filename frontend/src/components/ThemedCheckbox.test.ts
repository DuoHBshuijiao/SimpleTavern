// @vitest-environment happy-dom
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import ThemedCheckbox from './ThemedCheckbox.vue'

// 组件测试基座示例：验证 @vue/test-utils + happy-dom 可挂载并断言 SFC 的 props / emit / 键盘交互。
describe('ThemedCheckbox', () => {
  it('以 aria-checked 反映选中态并暴露 checkbox role', () => {
    const wrapper = mount(ThemedCheckbox, { props: { checked: true } })
    expect(wrapper.attributes('role')).toBe('checkbox')
    expect(wrapper.attributes('aria-checked')).toBe('true')
  })

  it('使用传入的 aria-label', () => {
    const wrapper = mount(ThemedCheckbox, { props: { checked: false, ariaLabel: '启用功能' } })
    expect(wrapper.attributes('aria-label')).toBe('启用功能')
  })

  it('点击时发出取反后的 update:checked', async () => {
    const wrapper = mount(ThemedCheckbox, { props: { checked: false } })
    await wrapper.trigger('click')
    expect(wrapper.emitted('update:checked')?.[0]).toEqual([true])
  })

  it('空格与回车键均触发切换', async () => {
    const wrapper = mount(ThemedCheckbox, { props: { checked: true } })
    await wrapper.trigger('keydown', { key: ' ' })
    await wrapper.trigger('keydown', { key: 'Enter' })
    const events = wrapper.emitted('update:checked')
    expect(events?.length).toBe(2)
    expect(events?.[0]).toEqual([false])
    expect(events?.[1]).toEqual([false])
  })

  it('禁用时不发出任何事件', async () => {
    const wrapper = mount(ThemedCheckbox, { props: { checked: false, disabled: true } })
    await wrapper.trigger('click')
    await wrapper.trigger('keydown', { key: 'Enter' })
    expect(wrapper.emitted('update:checked')).toBeUndefined()
  })
})
