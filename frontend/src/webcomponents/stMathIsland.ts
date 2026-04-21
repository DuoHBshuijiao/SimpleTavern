/**
 * 块级/行内公式 Shadow 隔离：避免光 DOM 上 Tailwind preflight（border:0）与 #app * 字体覆盖破坏 KaTeX。
 */
import katex from 'katex'
import katexCssUrl from 'katex/dist/katex.min.css?url'

const TAG = 'st-math-island'

const HOST_STYLE = `
:host {
  font: initial;
  color: inherit;
}
:host([data-mode="inline"]) {
  display: inline-block;
  max-width: 100%;
  vertical-align: middle;
}
:host([data-mode="display"]) {
  display: block;
  width: 100%;
  text-align: center;
  margin: 0.75em 0;
}
`

function decodeTex(raw: string | null): string {
  if (raw == null || raw === '') return ''
  try {
    return decodeURIComponent(raw)
  } catch {
    return raw
  }
}

export function registerStMathIsland(): void {
  if (typeof customElements === 'undefined') return
  if (customElements.get(TAG)) return

  class StMathIsland extends HTMLElement {
    connectedCallback(): void {
      this.ensureShadow()
      void this.renderKatex()
    }

    attributeChangedCallback(): void {
      this.ensureShadow()
      void this.renderKatex()
    }

    private ensureShadow(): void {
      if (this.shadowRoot) return
      const root = this.attachShadow({ mode: 'open' })

      const hostStyleEl = document.createElement('style')
      hostStyleEl.textContent = HOST_STYLE
      root.appendChild(hostStyleEl)

      const link = document.createElement('link')
      link.rel = 'stylesheet'
      link.href = katexCssUrl
      root.appendChild(link)

      const mount = document.createElement('div')
      mount.className = 'katex-mount'
      root.appendChild(mount)
    }

    private renderKatex(): Promise<void> {
      return new Promise((resolve) => {
        const root = this.shadowRoot
        if (!root) {
          resolve()
          return
        }
        const mount = root.querySelector('.katex-mount') as HTMLElement | null
        if (!mount) {
          resolve()
          return
        }

        const tex = decodeTex(this.getAttribute('data-tex'))
        const displayMode = this.getAttribute('data-mode') === 'display'
        const link = root.querySelector('link[rel="stylesheet"]') as HTMLLinkElement | null

        const run = (): void => {
          mount.innerHTML = ''
          if (!tex) {
            resolve()
            return
          }
          try {
            katex.render(tex, mount, {
              displayMode,
              throwOnError: false,
              errorColor: '#e5e7eb',
            })
          } catch {
            mount.textContent = tex
          }
          resolve()
        }

        if (link && !link.sheet) {
          const done = (): void => {
            run()
          }
          link.addEventListener('load', done, { once: true })
          link.addEventListener('error', done, { once: true })
          return
        }
        run()
      })
    }

    static get observedAttributes(): string[] {
      return ['data-tex', 'data-mode']
    }
  }

  customElements.define(TAG, StMathIsland)
}
