import { describe, expect, it } from 'vitest'

// 以原始文本方式加载 src 下全部单文件组件，用于静态扫描。
const vueSources = import.meta.glob('../**/*.vue', {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>

/**
 * 扫描单文件组件的 <template>，返回所有在原生 HTML 元素上裸用 `title` 属性的开标签。
 *
 * 约束（见 DESIGN.md / PRODUCT.md）：原生 `title` 属性不会可靠地暴露给键盘与辅助技术，
 * 禁止用它给控件命名或做 tooltip，必须改用 `aria-label`（或可见文本 / `aria-labelledby`）。
 *
 * 自定义组件使用 PascalCase（首字母大写），其 `title` prop 会渲染成可见标题，属于合法用法；
 * 原生 HTML 元素使用小写标签名，本扫描只针对小写标签上的 `title` / `:title` / `v-bind:title`。
 */
export function findBareTitleViolations(source: string): string[] {
  const templateMatch = source.match(/<template[\s\S]*?>([\s\S]*)<\/template>/i)
  const template = templateMatch ? templateMatch[1] : ''
  if (!template) return []

  const violations: string[] = []
  // 匹配开标签：标签名 + 属性串（引号内容允许包含 `>`）。
  const tagPattern = /<([a-zA-Z][\w-]*)((?:"[^"]*"|'[^']*'|[^>])*?)\/?>/g
  let match: RegExpExecArray | null
  while ((match = tagPattern.exec(template)) !== null) {
    const tagName = match[1] ?? ''
    const attrs = match[2] ?? ''
    // 仅检查原生 HTML 元素（小写标签）；PascalCase 组件的 title prop 合法。
    if (!/^[a-z]/.test(tagName)) continue
    // 命中裸 title / :title / v-bind:title，借助前导空白排除 subtitle、editing-title 等子串。
    if (/(?:^|\s)(?::|v-bind:)?title\s*=/.test(attrs)) {
      const snippet = `${tagName} ${attrs.replace(/\s+/g, ' ').trim()}`.trim()
      violations.push(`<${snippet}>`)
    }
  }
  return violations
}

describe('禁止原生元素裸用 title 属性', () => {
  it('所有 .vue 均不在原生元素上使用 title 属性（改用 aria-label）', () => {
    const offenders: string[] = []
    for (const [path, source] of Object.entries(vueSources)) {
      for (const violation of findBareTitleViolations(source)) {
        offenders.push(`${path}: ${violation}`)
      }
    }
    expect(offenders).toEqual([])
  })

  it('能识别原生元素上的裸 title 属性', () => {
    const sample = '<template><button title="保存"><span>x</span></button></template>'
    expect(findBareTitleViolations(sample)).toEqual(['<button title="保存">'])
  })

  it('能识别原生元素上的动态 :title 绑定', () => {
    const sample = '<template><div :title="tip">x</div></template>'
    expect(findBareTitleViolations(sample)).toEqual(['<div :title="tip">'])
  })

  it('忽略 PascalCase 组件的 title prop', () => {
    const sample = '<template><ConfirmPopover :title="t" /><MyCard title="A" /></template>'
    expect(findBareTitleViolations(sample)).toEqual([])
  })

  it('忽略仅包含 title 子串的其它属性名', () => {
    const sample = '<template><div :data-subtitle="s" editing-title="x"></div></template>'
    expect(findBareTitleViolations(sample)).toEqual([])
  })
})
